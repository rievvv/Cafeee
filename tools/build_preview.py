"""Buat pratinjau statis tampilan Cafeee untuk GitHub Pages.

  python tools/build_preview.py

Hasil: index.html (galeri) + folder preview/ di akar proyek. Aktifkan GitHub Pages
(Settings > Pages > Deploy from a branch > main > /root) lalu buka alamat Pages Anda.
Ini hanya TAMPILAN. Tombol/formulir tidak berfungsi; untuk mencoba alur penuh
gunakan Codespaces atau Render (lihat README).
"""
import html as htmllib
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp(prefix="cafeee-preview-")
os.environ.update(CAFEEE_DATA=tmp, CAFEEE_ADMIN_PASS="preview-pass-123", CAFEEE_BASE_URL="https://cafeee.example")
sys.path.insert(0, ROOT)

import app as cafeee  # noqa: E402
import manage  # noqa: E402

OUT = os.path.join(ROOT, "preview")
manage.demo()

# ---- data contoh yang lebih ramai (pemindaian 14 hari, nota beberapa hari)
with cafeee.app.app_context():
    now = datetime.now(cafeee.WIB)
    pro = cafeee.q("SELECT * FROM tags WHERE kind='pro'", one=True)
    basics = cafeee.q("SELECT * FROM tags WHERE kind='basic'")
    cafe = cafeee.q("SELECT * FROM cafes", one=True)
    cafeee.ex("DELETE FROM scans")
    pattern = [3, 5, 4, 8, 6, 9, 12, 7, 10, 14, 11, 9, 15, 13]
    for i, n in enumerate(pattern):
        day = now - timedelta(days=13 - i)
        for k in range(n):
            tag = pro if k % 3 else basics[k % len(basics)]
            ts = day.replace(hour=8 + (k * 7) % 13, minute=(k * 11) % 60).strftime("%Y-%m-%d %H:%M:%S")
            cafeee.ex("INSERT INTO scans(tag_id,ts,src,device,ip_hash) VALUES(?,?,?,?,?)",
                      (tag["id"], ts, "n" if k % 2 else "q", "android" if k % 3 else "ios", f"h{i}{k}"))
    items = cafeee.q("SELECT * FROM items WHERE cafe_id=? AND available=1", (cafe["id"],))
    for d in range(7):
        day = now - timedelta(days=6 - d)
        for o in range(3 + d % 3):
            picks = [(items[(d + o + j) % len(items)], 1 + (j + o) % 2) for j in range(2 + o % 2)]
            sub = sum(it["price"] * qty for it, qty in picks)
            ts = day.replace(hour=9 + o * 3, minute=15).strftime("%Y-%m-%d %H:%M:%S")
            oid = cafeee.ex("""INSERT INTO orders(cafe_id,number,table_no,payment,subtotal,tax,service,total,paid,change_amt,note,created_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (cafe["id"], f"{day.strftime('%y%m%d')}-{o + 1:03d}", f"Meja {o + 1}", ["Tunai", "QRIS", "Tunai"][o % 3],
                  sub, 0, 0, sub, sub, 0, "", ts)).lastrowid
            for it, qty in picks:
                cafeee.ex("INSERT INTO order_items(order_id,name,price,qty) VALUES(?,?,?,?)", (oid, it["name"], it["price"], qty))
    PRO_CODE, TAG_ID = pro["code"], pro["id"]
    LAST_ORDER = cafeee.q("SELECT id FROM orders ORDER BY id DESC LIMIT 1", one=True)["id"]
    TAG_IDS = ",".join(str(t["id"]) for t in cafeee.q("SELECT id FROM tags LIMIT 4"))

# (path, nama berkas, sebagai, judul, keterangan)
PAGES = [
    ("/", "beranda", None, "Beranda", "Halaman depan Cafeee"),
    ("/login", "login", None, "Halaman masuk", "Login pemilik"),
    (f"/c/{PRO_CODE}", "menu-pelanggan", None, "Menu digital pelanggan", "Yang dilihat pelanggan setelah memindai (tampilan HP)"),
    ("/admin", "admin-ringkasan", "admin", "Admin: ringkasan", "Statistik pemindaian dan pendapatan"),
    ("/admin/tags", "admin-kartu", "admin", "Admin: kartu dan QR", "Daftar kartu NFC/QR"),
    (f"/admin/tags/{TAG_ID}", "admin-kartu-detail", "admin", "Admin: detail kartu", "QR, link NFC, data penjualan"),
    (f"/admin/stiker?ids={TAG_IDS}", "admin-stiker", "admin", "Admin: lembar cetak QR", "Lembar stiker QR siap cetak"),
    ("/admin/cafe", "admin-cafe", "admin", "Admin: cafe pelanggan", "Kelola cafe paket Pro"),
    ("/admin/pengaturan", "admin-pengaturan", "admin", "Admin: pengaturan", "Alamat situs dan akun"),
    ("/dashboard", "cafe-ringkasan", "berkah", "Cafe: ringkasan", "Dashboard pemilik cafe"),
    ("/dashboard/kasir", "cafe-kasir", "berkah", "Cafe: kasir", "Kasir (ketuk menu untuk mencoba keranjang)"),
    ("/dashboard/menu", "cafe-menu", "berkah", "Cafe: kelola menu", "Ubah harga dan stok"),
    ("/dashboard/nota", "cafe-nota", "berkah", "Cafe: daftar nota", "Riwayat penjualan"),
    (f"/dashboard/nota/{LAST_ORDER}", "cafe-nota-detail", "berkah", "Cafe: nota", "Tampilan nota untuk printer struk"),
    ("/dashboard/pengaturan", "cafe-pengaturan", "berkah", "Cafe: pengaturan", "Profil tempat dan nota"),
]
FILES = {p: f"{n}.html" for p, n, *_ in PAGES}
FILES.update({p.split("?")[0]: f"{n}.html" for p, n, *_ in PAGES})
FILES["/dashboard/menu/"] = "cafe-menu.html"
FILES["/admin/pengaturan"] = "admin-pengaturan.html"

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(os.path.join(OUT, "static"))
os.makedirs(os.path.join(OUT, "assets"))
for f in ("cafeee.css", "cafeee.js"):
    shutil.copy(os.path.join(ROOT, "static", f), os.path.join(OUT, "static", f))

BANNER = ('<div style="position:fixed;left:0;right:0;bottom:0;z-index:9999;background:#2A1B14;color:#F1E4D2;'
          'font:600 13px/1.3 system-ui,sans-serif;padding:8px 12px;display:flex;gap:12px;justify-content:center;'
          'align-items:center;flex-wrap:wrap" class="noprint">Pratinjau statis: tombol dan formulir tidak berfungsi. '
          '<a href="../index.html" style="color:#E8C088">Kembali ke galeri</a></div>')
assets = {}


def asset_for(client, url):
    if url not in assets:
        r = client.get(url)
        name = re.sub(r"[^A-Za-z0-9._-]", "_", url.strip("/")) or "x"
        if "." not in name.rsplit("_", 1)[-1]:
            name += ".png"
        with open(os.path.join(OUT, "assets", name), "wb") as fh:
            fh.write(r.data)
        assets[url] = "assets/" + name
    return assets[url]


def rewrite(page, client):
    def repl(m):
        attr, url = m.group(1), htmllib.unescape(m.group(2))
        if url.startswith("/static/"):
            return f'{attr}="static/{url[8:].split("?")[0]}"'
        if attr == "src" and url.startswith("/qr/"):
            return f'{attr}="{asset_for(client, url)}"'
        if attr == "action":
            return f'{attr}="#"'
        target = FILES.get(url) or FILES.get(url.split("?")[0])
        return f'{attr}="{target or "#"}"'
    page = re.sub(r'\b(href|src|action)="(/[^"]*)"', repl, page)
    page = re.sub(r'\bhref="(https?://cafeee\.example[^"]*)"', 'href="#"', page)
    return page.replace("</body>", BANNER + "</body>")


def login(user, pw):
    c = cafeee.app.test_client()
    c.get("/login")
    with c.session_transaction() as s:
        tok = s["csrf"]
    c.post("/login", data={"username": user, "password": pw, "csrf_token": tok})
    return c


clients = {None: cafeee.app.test_client(), "admin": login("admin", "preview-pass-123"), "berkah": login("berkah", "berkah123")}
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/126"}
for path, name, role, *_ in PAGES:
    c = clients[role]
    r = c.get(path, headers=UA)
    assert r.status_code == 200, (path, r.status_code)
    with open(os.path.join(OUT, f"{name}.html"), "w", encoding="utf-8") as fh:
        fh.write(rewrite(r.get_data(as_text=True), c))

# ---- galeri
cards = "\n".join(
    f'<a class="gcard" href="preview/{n}.html"><b>{t}</b><span>{d}</span></a>' for _, n, _, t, d in PAGES)
open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cafeee: pratinjau tampilan</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lora:wght@500;600;700&family=Nunito+Sans:wght@400;600;700&display=swap">
<link rel="stylesheet" href="preview/static/cafeee.css">
<style>
body{{background:radial-gradient(900px 520px at 88% 0,rgba(217,165,91,.25),transparent 60%),var(--grad-dark) fixed;min-height:100vh;color:#fff;padding:2.5rem 1.2rem}}
.wrap{{max-width:980px;margin:0 auto}} h1{{font-size:clamp(2.6rem,8vw,4.5rem);font-weight:700}} h1 i{{font-style:normal;color:var(--caramel)}}
.lead{{color:#EADBC6;max-width:60ch;margin:.8rem 0 2rem}} .note{{background:rgba(255,255,255,.08);border-left:4px solid var(--caramel);padding:.7rem 1rem;border-radius:0 8px 8px 0;margin-bottom:2rem;color:#F1E4D2}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:.9rem}}
.gcard{{display:flex;flex-direction:column;gap:.25rem;background:var(--card);color:var(--ink);text-decoration:none;border-radius:12px;padding:1rem 1.1rem;border:2px solid transparent}}
.gcard:hover{{border-color:var(--caramel)}} .gcard b{{font:600 1.05rem var(--serif)}} .gcard span{{color:var(--ink2);font-size:.88rem}}
</style></head><body><div class="wrap">
<h1>Cafee<i>e</i></h1>
<p class="lead">Pratinjau tampilan tema kopi. Pilih halaman di bawah untuk melihat rancangannya.</p>
<div class="note">Ini tangkapan tampilan dengan data contoh. Tombol simpan dan formulir tidak berfungsi di sini. Untuk mencoba alur lengkap, jalankan aplikasi lewat Codespaces atau Render (lihat README).</div>
<div class="grid">
{cards}
</div></div></body></html>""")
open(os.path.join(ROOT, ".nojekyll"), "w").close()
print(f"Selesai: index.html + preview/ ({len(PAGES)} halaman, {len(assets)} gambar QR)")
