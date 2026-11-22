"""Cafeee - tag lokasi NFC/QR dinamis + menu digital + kasir untuk cafe & warmindo."""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import qrgen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("CAFEEE_DATA", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "cafeee.db")
os.makedirs(DATA_DIR, exist_ok=True)
WIB = timezone(timedelta(hours=7))
CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"

app = Flask(__name__)


def _secret_key():
    path = os.path.join(DATA_DIR, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    with open(path) as f:
        return f.read().strip()


app.secret_key = os.environ.get("CAFEEE_SECRET") or _secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("CAFEEE_HTTPS") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=1024 * 1024,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS cafes(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL,
  address TEXT DEFAULT '', phone TEXT DEFAULT '', review_url TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended')),
  receipt_footer TEXT DEFAULT 'Terima kasih sudah berkunjung!',
  paper_mm INTEGER DEFAULT 58, tax_pct REAL DEFAULT 0, service_pct REAL DEFAULT 0,
  notes TEXT DEFAULT '', created_at TEXT);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE,
  password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','cafe')),
  cafe_id INTEGER REFERENCES cafes(id) ON DELETE CASCADE, created_at TEXT);
CREATE TABLE IF NOT EXISTS tags(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('basic','pro')), label TEXT DEFAULT '',
  target_url TEXT DEFAULT '', cafe_id INTEGER REFERENCES cafes(id) ON DELETE SET NULL,
  active INTEGER DEFAULT 1, price INTEGER DEFAULT 0, buyer_name TEXT DEFAULT '',
  buyer_phone TEXT DEFAULT '', sold_at TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS scans(
  id INTEGER PRIMARY KEY, tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  ts TEXT NOT NULL, src TEXT, device TEXT, ip_hash TEXT);
CREATE INDEX IF NOT EXISTS scans_tag_ts ON scans(tag_id, ts);
CREATE TABLE IF NOT EXISTS categories(
  id INTEGER PRIMARY KEY, cafe_id INTEGER NOT NULL REFERENCES cafes(id) ON DELETE CASCADE,
  name TEXT NOT NULL, sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY, cafe_id INTEGER NOT NULL REFERENCES cafes(id) ON DELETE CASCADE,
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  name TEXT NOT NULL, description TEXT DEFAULT '', price INTEGER NOT NULL DEFAULT 0,
  available INTEGER DEFAULT 1, sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY, cafe_id INTEGER NOT NULL REFERENCES cafes(id) ON DELETE CASCADE,
  number TEXT NOT NULL, table_no TEXT DEFAULT '', payment TEXT DEFAULT 'Tunai',
  subtotal INTEGER, tax INTEGER, service INTEGER, total INTEGER,
  paid INTEGER DEFAULT 0, change_amt INTEGER DEFAULT 0, note TEXT DEFAULT '', created_at TEXT);
CREATE TABLE IF NOT EXISTS order_items(
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  name TEXT NOT NULL, price INTEGER NOT NULL, qty INTEGER NOT NULL);
"""

# --------------------------------------------------------------------------- db
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def q(sql, args=(), one=False):
    rows = db().execute(sql, args).fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def ex(sql, args=()):
    cur = db().execute(sql, args)
    db().commit()
    return cur


def now():
    return datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now(WIB).strftime("%Y-%m-%d")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def get_setting(key, default=""):
    row = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return row["value"] if row else default


def set_setting(key, value):
    ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
       (key, value))


def ensure_admin():
    """Create the first owner account. Returns (username, password) if created."""
    conn = sqlite3.connect(DB_PATH)
    has = conn.execute("SELECT 1 FROM users WHERE role='admin'").fetchone()
    created = None
    if not has:
        user = os.environ.get("CAFEEE_ADMIN_USER", "admin")
        pw = os.environ.get("CAFEEE_ADMIN_PASS") or secrets.token_urlsafe(9)
        conn.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                     (user, generate_password_hash(pw), "admin", now()))
        conn.commit()
        created = (user, pw)
    conn.close()
    return created


# ------------------------------------------------------------------ helpers
@app.template_filter("rp")
def rp(v):
    try:
        return "Rp " + f"{int(v):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "Rp 0"


@app.template_filter("num")
def num(v):
    try:
        return f"{int(v):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


@app.template_filter("tgl")
def tgl(v):
    if not v:
        return "-"
    try:
        d = datetime.strptime(v[:19], "%Y-%m-%d %H:%M:%S")
        return d.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return v


def clean(s, n=200):
    return (s or "").strip()[:n]


def to_int(v, default=0, lo=0, hi=10**9):
    try:
        return max(lo, min(hi, int(float(str(v).replace(".", "").replace(",", ".") or default))))
    except (TypeError, ValueError):
        return default


def to_pct(v):
    try:
        return max(0.0, min(100.0, float(str(v).replace(",", ".") or 0)))
    except ValueError:
        return 0.0


def valid_url(u):
    p = urlparse(u or "")
    return p.scheme in ("http", "https") and bool(p.netloc)


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:40] or "cafe"


def unique_slug(base):
    slug, n = base, 2
    while q("SELECT 1 FROM cafes WHERE slug=?", (slug,), one=True):
        slug = f"{base}-{n}"
        n += 1
    return slug


def new_code():
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not q("SELECT 1 FROM tags WHERE code=?", (code,), one=True):
            return code


def base_url():
    b = get_setting("base_url") or os.environ.get("CAFEEE_BASE_URL", "")
    return (b or request.host_url).rstrip("/")


def tag_link(code, src="n"):
    return f"{base_url()}/c/{code}?s={src}"


app.jinja_env.globals["tag_link"] = tag_link


# ----------------------------------------------------------------- security
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def csrf_protect():
    if request.method == "POST":
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
        if not session.get("csrf") or not secrets.compare_digest(session["csrf"], sent):
            abort(400, "Sesi kedaluwarsa. Muat ulang halaman lalu coba lagi.")


@app.after_request
def secure_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp


_attempts = {}


def too_many_attempts(key):
    t = time.time()
    _attempts[key] = [x for x in _attempts.get(key, []) if t - x < 600]
    return len(_attempts[key]) >= 8


def user_now():
    if "user" not in g:
        uid = session.get("uid")
        g.user = q("SELECT * FROM users WHERE id=?", (uid,), one=True) if uid else None
    return g.user


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        u = user_now()
        if not u or u["role"] != "admin":
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapper


def cafe_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        u = user_now()
        if not u:
            return redirect(url_for("login", next=request.path))
        cafe_id = None
        if u["role"] == "cafe":
            cafe_id = u["cafe_id"]
        elif u["role"] == "admin":
            cafe_id = session.get("view_cafe")
            if not cafe_id:
                return redirect(url_for("admin_cafes"))
        cafe = q("SELECT * FROM cafes WHERE id=?", (cafe_id,), one=True)
        if not cafe:
            session.clear()
            return redirect(url_for("login"))
        if cafe["status"] != "active" and u["role"] != "admin":
            session.clear()
            flash("Akun cafe ini sedang dinonaktifkan. Hubungi admin Cafeee.", "err")
            return redirect(url_for("login"))
        g.cafe = cafe
        return f(*a, **kw)
    return wrapper


@app.context_processor
def inject():
    u = user_now()
    return {"me": u, "viewing": session.get("view_cafe") if u and u["role"] == "admin" else None}


# ------------------------------------------------------------------- public
@app.route("/")
def landing():
    return render_template("landing.html")


def _device(ua):
    ua = (ua or "").lower()
    if "iphone" in ua or "ipad" in ua:
        return "ios"
    if "android" in ua:
        return "android"
    return "lain"


def _is_bot(ua):
    ua = (ua or "").lower()
    return any(x in ua for x in ("bot", "crawler", "spider", "preview", "facebookexternalhit", "whatsapp", "telegram", "slurp"))


def log_scan(tag):
    ua = request.headers.get("User-Agent", "")
    if _is_bot(ua):
        return
    src = request.args.get("s", "")[:1]
    src = src if src in ("n", "q") else "x"
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    iph = hashlib.sha256(f"{app.secret_key}{ip}{today()}".encode()).hexdigest()[:12]
    ex("INSERT INTO scans(tag_id,ts,src,device,ip_hash) VALUES(?,?,?,?,?)",
       (tag["id"], now(), src, _device(ua), iph))


def info_page(title, text, status=200):
    return render_template("message.html", title=title, text=text), status


def menu_for(cafe_id):
    cats = q("SELECT * FROM categories WHERE cafe_id=? ORDER BY sort, id", (cafe_id,))
    items = q("SELECT * FROM items WHERE cafe_id=? ORDER BY sort, name COLLATE NOCASE", (cafe_id,))
    groups = []
    for c in cats:
        groups.append({"cat": c, "items": [i for i in items if i["category_id"] == c["id"]]})
    loose = [i for i in items if i["category_id"] is None]
    if loose:
        groups.append({"cat": {"id": 0, "name": "Lainnya"}, "items": loose})
    return [gr for gr in groups if gr["items"]]


@app.route("/c/<code>")
def tag_public(code):
    tag = q("SELECT * FROM tags WHERE code=?", (code.lower(),), one=True)
    if not tag:
        return info_page("Kartu tidak dikenali", "Link ini tidak terdaftar di Cafeee. Periksa kembali kartu atau QR yang dipindai.", 404)
    if not tag["active"]:
        return info_page("Kartu dinonaktifkan", "Kartu ini sedang tidak aktif. Silakan hubungi pemilik tempat.", 410)
    log_scan(tag)
    if tag["kind"] == "basic":
        if not valid_url(tag["target_url"]):
            return info_page("Link belum diatur", "Kartu ini belum diarahkan ke tujuan. Hubungi penjual kartu.")
        resp = redirect(tag["target_url"], code=302)
        resp.headers["Cache-Control"] = "no-store"
        return resp
    cafe = q("SELECT * FROM cafes WHERE id=?", (tag["cafe_id"],), one=True)
    if not cafe or cafe["status"] != "active":
        return info_page("Menu belum tersedia", "Menu untuk kartu ini belum tersedia saat ini.")
    resp = app.make_response(render_template("public_menu.html", cafe=cafe, groups=menu_for(cafe["id"]), tag=tag))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/qr/<code>.<fmt>")
def qr_image(code, fmt):
    tag = q("SELECT code FROM tags WHERE code=?", (code.lower(),), one=True)
    if not tag or fmt not in ("svg", "png"):
        abort(404)
    src = "n" if request.args.get("s") == "n" else "q"
    m = qrgen.make_qr(tag_link(tag["code"], src), ecl="Q")
    if fmt == "svg":
        return Response(qrgen.to_svg(m), mimetype="image/svg+xml")
    scale = to_int(request.args.get("px"), 12, 4, 40)
    resp = Response(qrgen.to_png(m, scale=scale), mimetype="image/png")
    if request.args.get("dl"):
        resp.headers["Content-Disposition"] = f'attachment; filename="cafeee-{tag["code"]}.png"'
    return resp


# --------------------------------------------------------------------- auth
@app.route("/login", methods=["GET", "POST"])
def login():
    cafe_hint = None
    if request.args.get("cafe"):
        cafe_hint = q("SELECT name, slug FROM cafes WHERE slug=?", (request.args["cafe"],), one=True)
    back = request.args.get("back", "")
    back = back if back.startswith("/c/") else ""
    if request.method == "POST":
        username = clean(request.form.get("username"), 60)
        key = f"{request.remote_addr}|{username.lower()}"
        if too_many_attempts(key):
            flash("Terlalu banyak percobaan. Tunggu beberapa menit lalu coba lagi.", "err")
            return render_template("login.html", cafe=cafe_hint, back=back), 429
        u = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
            _attempts.pop(key, None)
            session.clear()
            session.permanent = True
            session["uid"] = u["id"]
            nxt = request.args.get("next", "")
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = ""
            if u["role"] == "admin":
                return redirect(nxt or url_for("admin_home"))
            return redirect(nxt or url_for("dash_home"))
        _attempts.setdefault(key, []).append(time.time())
        flash("Username atau kata sandi salah.", "err")
    return render_template("login.html", cafe=cafe_hint, back=back)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------- cafe dashboard
def _sales(cafe_id, since):
    r = q("SELECT COUNT(*) n, COALESCE(SUM(total),0) s FROM orders WHERE cafe_id=? AND created_at>=?", (cafe_id, since), one=True)
    return r["n"], r["s"]


@app.route("/dashboard")
@cafe_required
def dash_home():
    cid = g.cafe["id"]
    t = today()
    n_today, s_today = _sales(cid, t)
    week = (datetime.now(WIB) - timedelta(days=6)).strftime("%Y-%m-%d")
    days = []
    for i in range(7):
        d = (datetime.now(WIB) - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        r = q("SELECT COALESCE(SUM(total),0) s FROM orders WHERE cafe_id=? AND substr(created_at,1,10)=?", (cid, d), one=True)
        days.append({"d": d[8:], "s": r["s"]})
    mx = max([x["s"] for x in days] + [1])
    for x in days:
        x["h"] = round(x["s"] / mx * 100)
    best = q("""SELECT oi.name, SUM(oi.qty) qty FROM order_items oi JOIN orders o ON o.id=oi.order_id
                WHERE o.cafe_id=? AND o.created_at>=? GROUP BY oi.name ORDER BY qty DESC LIMIT 5""", (cid, week))
    tags = q("SELECT t.*, (SELECT COUNT(*) FROM scans s WHERE s.tag_id=t.id AND s.ts>=?) week_scans FROM tags t WHERE cafe_id=?", (week, cid))
    n_items = q("SELECT COUNT(*) c FROM items WHERE cafe_id=?", (cid,), one=True)["c"]
    return render_template("dash_home.html", n_today=n_today, s_today=s_today, days=days, best=best, tags=tags, n_items=n_items)


@app.route("/dashboard/menu")
@cafe_required
def dash_menu():
    cid = g.cafe["id"]
    cats = q("SELECT * FROM categories WHERE cafe_id=? ORDER BY sort, id", (cid,))
    items = q("SELECT * FROM items WHERE cafe_id=? ORDER BY sort, name COLLATE NOCASE", (cid,))
    return render_template("dash_menu.html", cats=cats, items=items)


@app.route("/dashboard/menu/kategori", methods=["POST"])
@cafe_required
def cat_save():
    cid = g.cafe["id"]
    name = clean(request.form.get("name"), 40)
    cat_id = to_int(request.form.get("id"))
    if not name:
        flash("Nama kategori wajib diisi.", "err")
    elif cat_id:
        ex("UPDATE categories SET name=? WHERE id=? AND cafe_id=?", (name, cat_id, cid))
        flash("Kategori diperbarui.", "ok")
    else:
        mx = q("SELECT COALESCE(MAX(sort),0) m FROM categories WHERE cafe_id=?", (cid,), one=True)["m"]
        ex("INSERT INTO categories(cafe_id,name,sort) VALUES(?,?,?)", (cid, name, mx + 1))
        flash("Kategori ditambahkan.", "ok")
    return redirect(url_for("dash_menu"))


@app.route("/dashboard/menu/kategori/<int:cat_id>/hapus", methods=["POST"])
@cafe_required
def cat_delete(cat_id):
    ex("DELETE FROM categories WHERE id=? AND cafe_id=?", (cat_id, g.cafe["id"]))
    flash("Kategori dihapus. Menu di dalamnya dipindah ke 'Lainnya'.", "ok")
    return redirect(url_for("dash_menu"))


@app.route("/dashboard/menu/item", methods=["POST"])
@cafe_required
def item_save():
    cid = g.cafe["id"]
    item_id = to_int(request.form.get("id"))
    name = clean(request.form.get("name"), 80)
    if not name:
        flash("Nama menu wajib diisi.", "err")
        return redirect(url_for("dash_menu"))
    cat = to_int(request.form.get("category_id"))
    if cat and not q("SELECT 1 FROM categories WHERE id=? AND cafe_id=?", (cat, cid), one=True):
        cat = 0
    vals = (cat or None, name, clean(request.form.get("description"), 200),
            to_int(request.form.get("price"), 0, 0, 100_000_000), 1 if request.form.get("available") else 0)
    if item_id:
        ex("UPDATE items SET category_id=?, name=?, description=?, price=?, available=? WHERE id=? AND cafe_id=?",
           vals + (item_id, cid))
        flash(f"{name} diperbarui.", "ok")
    else:
        ex("INSERT INTO items(category_id,name,description,price,available,cafe_id) VALUES(?,?,?,?,?,?)", vals + (cid,))
        flash(f"{name} ditambahkan ke menu.", "ok")
    return redirect(url_for("dash_menu"))


@app.route("/dashboard/menu/item/<int:item_id>/harga", methods=["POST"])
@cafe_required
def item_price(item_id):
    price = to_int(request.form.get("price"), 0, 0, 100_000_000)
    cur = ex("UPDATE items SET price=? WHERE id=? AND cafe_id=?", (price, item_id, g.cafe["id"]))
    return jsonify(ok=cur.rowcount == 1, price=price)


@app.route("/dashboard/menu/item/<int:item_id>/stok", methods=["POST"])
@cafe_required
def item_stock(item_id):
    cur = ex("UPDATE items SET available=1-available WHERE id=? AND cafe_id=?", (item_id, g.cafe["id"]))
    row = q("SELECT available FROM items WHERE id=?", (item_id,), one=True)
    return jsonify(ok=cur.rowcount == 1, available=row["available"] if row else 0)


@app.route("/dashboard/menu/item/<int:item_id>/hapus", methods=["POST"])
@cafe_required
def item_delete(item_id):
    ex("DELETE FROM items WHERE id=? AND cafe_id=?", (item_id, g.cafe["id"]))
    flash("Menu dihapus.", "ok")
    return redirect(url_for("dash_menu"))


# ------------------------------------------------------------- kasir & nota
@app.route("/dashboard/kasir")
@cafe_required
def dash_pos():
    groups = menu_for(g.cafe["id"])
    for gr in groups:
        gr["items"] = [i for i in gr["items"] if i["available"]]
    groups = [gr for gr in groups if gr["items"]]
    return render_template("dash_pos.html", groups=groups)


@app.route("/dashboard/kasir/simpan", methods=["POST"])
@cafe_required
def pos_save():
    cafe = g.cafe
    data = request.get_json(silent=True) or {}
    lines = []
    for row in (data.get("items") or [])[:100]:
        qty = to_int(row.get("qty"), 0, 0, 999)
        if qty < 1:
            continue
        if row.get("id"):
            it = q("SELECT name, price FROM items WHERE id=? AND cafe_id=?", (to_int(row["id"]), cafe["id"]), one=True)
            if not it:
                continue
            lines.append((it["name"], it["price"], qty))
        else:
            name = clean(row.get("name"), 60)
            if name:
                lines.append((name, to_int(row.get("price"), 0, 0, 100_000_000), qty))
    if not lines:
        return jsonify(ok=False, error="Pesanan masih kosong."), 400
    subtotal = sum(p * n for _, p, n in lines)
    service = int(subtotal * cafe["service_pct"] / 100 + 0.5)
    tax = int((subtotal + service) * cafe["tax_pct"] / 100 + 0.5)
    total = subtotal + service + tax
    payment = clean(data.get("payment"), 20) or "Tunai"
    paid = to_int(data.get("paid"), 0, 0, 1_000_000_000) if payment == "Tunai" else total
    if payment == "Tunai" and paid and paid < total:
        return jsonify(ok=False, error="Uang yang dibayar kurang dari total."), 400
    paid = paid or total
    cur = db().cursor()
    seq = q("SELECT COUNT(*) c FROM orders WHERE cafe_id=? AND substr(created_at,1,10)=?", (cafe["id"], today()), one=True)["c"] + 1
    number = f"{datetime.now(WIB).strftime('%y%m%d')}-{seq:03d}"
    cur.execute("""INSERT INTO orders(cafe_id,number,table_no,payment,subtotal,tax,service,total,paid,change_amt,note,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (cafe["id"], number, clean(data.get("table"), 20), payment, subtotal, tax, service, total,
                 paid, max(0, paid - total), clean(data.get("note"), 100), now()))
    oid = cur.lastrowid
    cur.executemany("INSERT INTO order_items(order_id,name,price,qty) VALUES(?,?,?,?)", [(oid, n, p, k) for n, p, k in lines])
    db().commit()
    return jsonify(ok=True, id=oid, url=url_for("dash_receipt", order_id=oid, auto=1))


@app.route("/dashboard/nota")
@cafe_required
def dash_orders():
    day = request.args.get("tgl") or today()
    orders = q("SELECT * FROM orders WHERE cafe_id=? AND substr(created_at,1,10)=? ORDER BY id DESC", (g.cafe["id"], day))
    return render_template("dash_orders.html", orders=orders, day=day, total=sum(o["total"] for o in orders))


@app.route("/dashboard/nota/<int:order_id>")
@cafe_required
def dash_receipt(order_id):
    order = q("SELECT * FROM orders WHERE id=? AND cafe_id=?", (order_id, g.cafe["id"]), one=True)
    if not order:
        abort(404)
    lines = q("SELECT * FROM order_items WHERE order_id=?", (order_id,))
    return render_template("dash_receipt.html", order=order, lines=lines, auto=request.args.get("auto"))


@app.route("/dashboard/nota/<int:order_id>/hapus", methods=["POST"])
@cafe_required
def order_delete(order_id):
    ex("DELETE FROM orders WHERE id=? AND cafe_id=?", (order_id, g.cafe["id"]))
    flash("Nota dihapus.", "ok")
    return redirect(url_for("dash_orders"))


@app.route("/dashboard/pengaturan", methods=["GET", "POST"])
@cafe_required
def dash_settings():
    cafe = g.cafe
    if request.method == "POST":
        form = request.form.get("form")
        if form == "profil":
            name = clean(request.form.get("name"), 60)
            review = clean(request.form.get("review_url"), 500)
            if not name:
                flash("Nama tempat wajib diisi.", "err")
            elif review and not valid_url(review):
                flash("Link ulasan harus diawali http:// atau https://", "err")
            else:
                ex("""UPDATE cafes SET name=?, address=?, phone=?, review_url=?, receipt_footer=?, paper_mm=?,
                      tax_pct=?, service_pct=? WHERE id=?""",
                   (name, clean(request.form.get("address"), 160), clean(request.form.get("phone"), 30), review,
                    clean(request.form.get("receipt_footer"), 120),
                    80 if request.form.get("paper_mm") == "80" else 58,
                    to_pct(request.form.get("tax_pct")), to_pct(request.form.get("service_pct")), cafe["id"]))
                flash("Pengaturan disimpan.", "ok")
        elif form == "sandi":
            u = user_now()
            if u["role"] != "cafe":
                flash("Ganti kata sandi hanya untuk akun cafe.", "err")
            elif not check_password_hash(u["password_hash"], request.form.get("old", "")):
                flash("Kata sandi lama salah.", "err")
            elif len(request.form.get("new", "")) < 8:
                flash("Kata sandi baru minimal 8 karakter.", "err")
            else:
                ex("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(request.form["new"]), u["id"]))
                flash("Kata sandi diganti.", "ok")
        return redirect(url_for("dash_settings"))
    tags = q("SELECT * FROM tags WHERE cafe_id=?", (cafe["id"],))
    return render_template("dash_settings.html", c=cafe, tags=tags)


# -------------------------------------------------------------------- admin
@app.route("/admin")
@admin_required
def admin_home():
    st = q("""SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN sold_at IS NOT NULL THEN price END),0) rev,
              SUM(CASE WHEN sold_at IS NOT NULL THEN 1 ELSE 0 END) sold,
              SUM(CASE WHEN kind='pro' THEN 1 ELSE 0 END) pro FROM tags""", one=True)
    n_cafes = q("SELECT COUNT(*) c FROM cafes", (), one=True)["c"]
    total_scans = q("SELECT COUNT(*) c FROM scans", (), one=True)["c"]
    days = []
    for i in range(14):
        d = (datetime.now(WIB) - timedelta(days=13 - i)).strftime("%Y-%m-%d")
        c = q("SELECT COUNT(*) c FROM scans WHERE substr(ts,1,10)=?", (d,), one=True)["c"]
        days.append({"d": d[8:], "c": c})
    mx = max([x["c"] for x in days] + [1])
    for x in days:
        x["h"] = round(x["c"] / mx * 100)
    src = {r["src"]: r["c"] for r in q("SELECT src, COUNT(*) c FROM scans GROUP BY src")}
    top = q("""SELECT t.code, t.label, t.kind, COUNT(s.id) c FROM tags t JOIN scans s ON s.tag_id=t.id
               GROUP BY t.id ORDER BY c DESC LIMIT 6""")
    todo = q("""SELECT * FROM tags WHERE active=1 AND ((kind='basic' AND target_url='') OR (kind='pro' AND cafe_id IS NULL))
                ORDER BY id DESC LIMIT 8""")
    recent = q("""SELECT s.*, t.code, t.label FROM scans s JOIN tags t ON t.id=s.tag_id ORDER BY s.id DESC LIMIT 8""")
    return render_template("admin_home.html", st=st, n_cafes=n_cafes, total_scans=total_scans, days=days,
                           src=src, top=top, todo=todo, recent=recent)


@app.route("/admin/tags")
@admin_required
def admin_tags():
    kind = request.args.get("kind", "")
    qs = clean(request.args.get("q"), 60)
    sql = """SELECT t.*, c.name cafe_name, (SELECT COUNT(*) FROM scans s WHERE s.tag_id=t.id) scans
             FROM tags t LEFT JOIN cafes c ON c.id=t.cafe_id WHERE 1=1"""
    args = []
    if kind in ("basic", "pro"):
        sql += " AND t.kind=?"
        args.append(kind)
    if qs:
        sql += " AND (t.code LIKE ? OR t.label LIKE ? OR t.buyer_name LIKE ? OR c.name LIKE ?)"
        args += [f"%{qs}%"] * 4
    tags = q(sql + " ORDER BY t.id DESC LIMIT 500", args)
    cafes = q("SELECT id, name FROM cafes ORDER BY name")
    return render_template("admin_tags.html", tags=tags, cafes=cafes, kind=kind, qs=qs,
                           price_basic=get_setting("price_basic", "100000"), price_pro=get_setting("price_pro", "200000"))


@app.route("/admin/tags/baru", methods=["POST"])
@admin_required
def admin_tags_create():
    kind = "pro" if request.form.get("kind") == "pro" else "basic"
    count = to_int(request.form.get("count"), 1, 1, 200)
    label = clean(request.form.get("label"), 80)
    target = clean(request.form.get("target_url"), 500)
    cafe_id = to_int(request.form.get("cafe_id")) or None
    if target and not valid_url(target):
        flash("Link tujuan harus diawali http:// atau https://", "err")
        return redirect(url_for("admin_tags"))
    if kind == "pro" and cafe_id and not q("SELECT 1 FROM cafes WHERE id=?", (cafe_id,), one=True):
        cafe_id = None
    std = get_setting("price_pro", "200000") if kind == "pro" else get_setting("price_basic", "100000")
    price = to_int(request.form.get("price"), to_int(std))
    ids = []
    for _ in range(count):
        cur = ex("""INSERT INTO tags(code,kind,label,target_url,cafe_id,price,created_at) VALUES(?,?,?,?,?,?,?)""",
                 (new_code(), kind, label, target if kind == "basic" else "", cafe_id if kind == "pro" else None, price, now()))
        ids.append(cur.lastrowid)
    flash(f"{count} kartu {'Pro' if kind == 'pro' else 'Basic'} dibuat. Siap dicetak sebagai stiker QR dan ditulis ke NFC.", "ok")
    return redirect(url_for("admin_qrsheet", ids=",".join(map(str, ids))))


@app.route("/admin/tags/<int:tag_id>", methods=["GET", "POST"])
@admin_required
def admin_tag(tag_id):
    tag = q("SELECT * FROM tags WHERE id=?", (tag_id,), one=True)
    if not tag:
        abort(404)
    if request.method == "POST":
        target = clean(request.form.get("target_url"), 500)
        if target and not valid_url(target):
            flash("Link tujuan harus diawali http:// atau https://", "err")
            return redirect(url_for("admin_tag", tag_id=tag_id))
        kind = "pro" if request.form.get("kind") == "pro" else "basic"
        cafe_id = to_int(request.form.get("cafe_id")) or None
        if cafe_id and not q("SELECT 1 FROM cafes WHERE id=?", (cafe_id,), one=True):
            cafe_id = None
        sold = bool(request.form.get("sold"))
        sold_at = (tag["sold_at"] or now()) if sold else None
        ex("""UPDATE tags SET kind=?, label=?, target_url=?, cafe_id=?, active=?, price=?, buyer_name=?, buyer_phone=?, sold_at=?
              WHERE id=?""",
           (kind, clean(request.form.get("label"), 80), target, cafe_id, 1 if request.form.get("active") else 0,
            to_int(request.form.get("price")), clean(request.form.get("buyer_name"), 80),
            clean(request.form.get("buyer_phone"), 30), sold_at, tag_id))
        flash("Kartu disimpan. Perubahan langsung berlaku tanpa menulis ulang NFC.", "ok")
        return redirect(url_for("admin_tag", tag_id=tag_id))
    cafes = q("SELECT id, name FROM cafes ORDER BY name")
    scans = q("SELECT * FROM scans WHERE tag_id=? ORDER BY id DESC LIMIT 15", (tag_id,))
    total = q("SELECT COUNT(*) c FROM scans WHERE tag_id=?", (tag_id,), one=True)["c"]
    return render_template("admin_tag.html", t=tag, cafes=cafes, scans=scans, total=total)


@app.route("/admin/tags/<int:tag_id>/hapus", methods=["POST"])
@admin_required
def admin_tag_delete(tag_id):
    ex("DELETE FROM tags WHERE id=?", (tag_id,))
    flash("Kartu dihapus. Link-nya tidak akan berfungsi lagi.", "ok")
    return redirect(url_for("admin_tags"))


@app.route("/admin/stiker")
@admin_required
def admin_qrsheet():
    ids = [to_int(x) for x in request.args.get("ids", "").split(",") if x.strip()]
    if not ids:
        flash("Pilih kartu yang ingin dicetak dari daftar kartu.", "err")
        return redirect(url_for("admin_tags"))
    marks = ",".join("?" * len(ids))
    tags = q(f"SELECT * FROM tags WHERE id IN ({marks}) ORDER BY id", ids)
    size = to_int(request.args.get("cm"), 4, 2, 10)
    return render_template("admin_qrsheet.html", tags=tags, size=size, ids=",".join(map(str, ids)))


@app.route("/admin/cafe")
@admin_required
def admin_cafes():
    cafes = q("""SELECT c.*, u.username,
                 (SELECT COUNT(*) FROM tags t WHERE t.cafe_id=c.id) n_tags,
                 (SELECT COUNT(*) FROM items i WHERE i.cafe_id=c.id) n_items,
                 (SELECT COUNT(*) FROM orders o WHERE o.cafe_id=c.id) n_orders
                 FROM cafes c LEFT JOIN users u ON u.cafe_id=c.id AND u.role='cafe' ORDER BY c.id DESC""")
    return render_template("admin_cafes.html", cafes=cafes)


@app.route("/admin/cafe/baru", methods=["POST"])
@admin_required
def admin_cafe_create():
    name = clean(request.form.get("name"), 60)
    username = clean(request.form.get("username"), 40).replace(" ", "")
    pw = request.form.get("password", "")
    if not name or not username:
        flash("Nama cafe dan username wajib diisi.", "err")
    elif len(pw) < 8:
        flash("Kata sandi minimal 8 karakter.", "err")
    elif q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
        flash("Username sudah dipakai. Pilih yang lain.", "err")
    else:
        cur = ex("INSERT INTO cafes(name, slug, created_at) VALUES(?,?,?)", (name, unique_slug(slugify(name)), now()))
        ex("INSERT INTO users(username,password_hash,role,cafe_id,created_at) VALUES(?,?,?,?,?)",
           (username, generate_password_hash(pw), "cafe", cur.lastrowid, now()))
        ex("INSERT INTO categories(cafe_id,name,sort) VALUES(?,?,?)", (cur.lastrowid, "Menu", 1))
        flash(f"Cafe {name} dibuat. Berikan username dan kata sandinya ke pemilik.", "ok")
    return redirect(url_for("admin_cafes"))


@app.route("/admin/cafe/<int:cafe_id>", methods=["POST"])
@admin_required
def admin_cafe_update(cafe_id):
    c = q("SELECT * FROM cafes WHERE id=?", (cafe_id,), one=True)
    if not c:
        abort(404)
    action = request.form.get("action")
    if action == "status":
        ex("UPDATE cafes SET status=? WHERE id=?", ("active" if c["status"] == "suspended" else "suspended", cafe_id))
        flash("Status cafe diubah.", "ok")
    elif action == "reset":
        pw = request.form.get("password", "")
        if len(pw) < 8:
            flash("Kata sandi baru minimal 8 karakter.", "err")
        else:
            ex("UPDATE users SET password_hash=? WHERE cafe_id=? AND role='cafe'", (generate_password_hash(pw), cafe_id))
            flash("Kata sandi cafe diganti.", "ok")
    elif action == "notes":
        ex("UPDATE cafes SET notes=? WHERE id=?", (clean(request.form.get("notes"), 300), cafe_id))
        flash("Catatan disimpan.", "ok")
    elif action == "delete":
        ex("DELETE FROM users WHERE cafe_id=?", (cafe_id,))
        ex("DELETE FROM cafes WHERE id=?", (cafe_id,))
        if session.get("view_cafe") == cafe_id:
            session.pop("view_cafe")
        flash("Cafe dan seluruh datanya dihapus.", "ok")
    return redirect(url_for("admin_cafes"))


@app.route("/admin/cafe/<int:cafe_id>/masuk", methods=["POST"])
@admin_required
def admin_cafe_enter(cafe_id):
    if not q("SELECT 1 FROM cafes WHERE id=?", (cafe_id,), one=True):
        abort(404)
    session["view_cafe"] = cafe_id
    return redirect(url_for("dash_home"))


@app.route("/admin/keluar-cafe", methods=["POST"])
@admin_required
def admin_cafe_leave():
    session.pop("view_cafe", None)
    return redirect(url_for("admin_cafes"))


@app.route("/admin/pengaturan", methods=["GET", "POST"])
@admin_required
def admin_settings():
    if request.method == "POST":
        form = request.form.get("form")
        if form == "umum":
            b = clean(request.form.get("base_url"), 200).rstrip("/")
            if b and not valid_url(b):
                flash("Alamat situs harus diawali https://", "err")
            else:
                set_setting("base_url", b)
                set_setting("price_basic", str(to_int(request.form.get("price_basic"), 100000)))
                set_setting("price_pro", str(to_int(request.form.get("price_pro"), 200000)))
                flash("Pengaturan disimpan.", "ok")
        elif form == "sandi":
            u = user_now()
            if not check_password_hash(u["password_hash"], request.form.get("old", "")):
                flash("Kata sandi lama salah.", "err")
            elif len(request.form.get("new", "")) < 8:
                flash("Kata sandi baru minimal 8 karakter.", "err")
            else:
                ex("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(request.form["new"]), u["id"]))
                flash("Kata sandi diganti.", "ok")
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html", base=get_setting("base_url"), effective=base_url(),
                           price_basic=get_setting("price_basic", "100000"), price_pro=get_setting("price_pro", "200000"))


# ------------------------------------------------------------------- errors
@app.errorhandler(400)
def bad_request(e):
    return info_page("Permintaan tidak valid", getattr(e, "description", "Coba muat ulang halaman."), 400)


@app.errorhandler(404)
def not_found(_e):
    return info_page("Halaman tidak ditemukan", "Alamat yang Anda buka tidak ada.", 404)


init_db()
_first = ensure_admin()
if _first:
    print("=" * 56)
    print(" Akun pemilik Cafeee dibuat (simpan, hanya tampil sekali):")
    print(f"   username : {_first[0]}")
    print(f"   password : {_first[1]}")
    print("=" * 56)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("CAFEEE_DEBUG") == "1")
