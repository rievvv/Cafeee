"""Uji alur lengkap Cafeee. Jalankan:  python tests/test_flow.py"""
import io
import os
import re
import sys
import tempfile

tmp = tempfile.mkdtemp(prefix="cafeee-test-")
os.environ["CAFEEE_DATA"] = tmp
os.environ["CAFEEE_ADMIN_PASS"] = "admin-pass-123"
os.environ["CAFEEE_BASE_URL"] = "https://cafeee.test"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import app as cafeee  # noqa: E402

try:
    import cv2
except ImportError:  # decoder opsional
    cv2 = None

UA_PHONE = "Mozilla/5.0 (Linux; Android 14) Chrome/126"
passed = 0


def check(cond, msg):
    global passed
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    passed += 1
    print("  ok  ", msg)


def token(c):
    c.get("/login")
    with c.session_transaction() as s:
        return s["csrf"]


def post(c, url, data=None, **kw):
    d = dict(data or {})
    d["csrf_token"] = token(c)
    return c.post(url, data=d, **kw)


def login(c, user, pw):
    return post(c, "/login", {"username": user, "password": pw})


admin = cafeee.app.test_client()
print("Akun & akses")
check(admin.get("/").status_code == 200, "beranda terbuka")
check(admin.get("/admin").status_code == 302, "panel admin butuh login")
check(admin.get("/dashboard").status_code == 302, "dashboard cafe butuh login")
r = admin.post("/login", data={"username": "admin", "password": "x"})
check(r.status_code == 400, "POST tanpa token CSRF ditolak")
r = login(admin, "admin", "salah")
check("Username atau kata sandi salah" in r.get_data(as_text=True), "kata sandi salah ditolak")
r = login(admin, "admin", "admin-pass-123")
check(r.status_code == 302 and r.headers["Location"].endswith("/admin"), "admin berhasil masuk")

print("Admin: cafe dan kartu")
post(admin, "/admin/cafe/baru", {"name": "Warmindo Berkah", "username": "berkah", "password": "berkah-pass-1"})
post(admin, "/admin/cafe/baru", {"name": "Kopi Senja", "username": "senja", "password": "senja-pass-12"})
post(admin, "/admin/cafe/baru", {"name": "Dobel", "username": "berkah", "password": "berkah-pass-1"})
with cafeee.app.app_context():
    cafes = {r["slug"]: r["id"] for r in cafeee.q("SELECT id, slug FROM cafes")}
check(set(cafes) == {"warmindo-berkah", "kopi-senja"}, "dua cafe dibuat, username ganda ditolak")
A, B = cafes["warmindo-berkah"], cafes["kopi-senja"]

post(admin, "/admin/tags/baru", {"kind": "basic", "count": "2", "label": "Review Kopi Senja",
                                  "target_url": "https://g.page/r/abc123/review"})
post(admin, "/admin/tags/baru", {"kind": "pro", "count": "1", "cafe_id": str(A)})
post(admin, "/admin/tags/baru", {"kind": "pro", "count": "1", "cafe_id": str(B)})
r = post(admin, "/admin/tags/baru", {"kind": "basic", "count": "1", "target_url": "javascript:alert(1)"})
with cafeee.app.app_context():
    tags = cafeee.q("SELECT * FROM tags ORDER BY id")
check(len(tags) == 4, "4 kartu dibuat, link javascript: ditolak")
basic, proA, proB = tags[0], tags[2], tags[3]
check(basic["price"] == 100000 and proA["price"] == 200000, "harga standar Basic 100rb dan Pro 200rb")
check(all(len(t["code"]) == 6 for t in tags) and len({t["code"] for t in tags}) == 4, "kode unik 6 karakter")

print("Scan kartu Basic (langsung ke Google Review)")
pub = cafeee.app.test_client()
r = pub.get(f"/c/{basic['code']}?s=n", headers={"User-Agent": UA_PHONE})
check(r.status_code == 302 and r.headers["Location"] == "https://g.page/r/abc123/review", "scan NFC diarahkan ke tujuan")
pub.get(f"/c/{basic['code'].upper()}?s=q", headers={"User-Agent": UA_PHONE})
pub.get(f"/c/{basic['code']}?s=n", headers={"User-Agent": "WhatsApp/2.23 bot preview"})
with cafeee.app.app_context():
    rows = cafeee.q("SELECT src, device FROM scans WHERE tag_id=?", (basic["id"],))
check([r["src"] for r in rows] == ["n", "q"] and rows[0]["device"] == "android", "scan dicatat NFC dan QR, bot diabaikan")
post(admin, f"/admin/tags/{basic['id']}", {"kind": "basic", "target_url": "https://g.page/r/BARU/review", "active": "on", "price": "100000"})
r = pub.get(f"/c/{basic['code']}")
check(r.headers["Location"] == "https://g.page/r/BARU/review", "ganti tujuan di admin langsung berlaku tanpa tulis ulang NFC")
post(admin, f"/admin/tags/{basic['id']}", {"kind": "basic", "target_url": "https://g.page/r/BARU/review", "price": "100000"})
check(pub.get(f"/c/{basic['code']}").status_code == 410, "kartu nonaktif menampilkan pesan")
check(pub.get("/c/zzzzzz").status_code == 404, "kode tidak dikenal 404")

print("QR bawaan")
png = pub.get(f"/qr/{proA['code']}.png?px=8").data
check(png[:4] == b"\x89PNG", "QR PNG dibuat")
svg = pub.get(f"/qr/{proA['code']}.svg")
check(svg.mimetype == "image/svg+xml" and b"<svg" in svg.data, "QR SVG dibuat")
if cv2:
    img = np.array(Image.open(io.BytesIO(png)).convert("L"))
    val = ""
    for scale in (8,):
        val, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    check(val == f"https://cafeee.test/c/{proA['code']}?s=q", "QR terbaca dan mengarah ke link kartu")

print("Menu publik dengan gembok (paket Pro)")
r = pub.get(f"/c/{proA['code']}")
html = r.get_data(as_text=True)
check(r.status_code == 200 and "Warmindo Berkah" in html, "pelanggan melihat menu cafe")
check(f"/login?cafe=warmindo-berkah&amp;back=/c/{proA['code']}" in html or f"/login?cafe=warmindo-berkah&back=/c/{proA['code']}" in html, "ada tombol gembok menuju login pemilik")
check("Menu belum diisi" in html, "menu kosong menampilkan petunjuk")

print("Dashboard cafe")
owner = cafeee.app.test_client()
r = owner.get(f"/login?cafe=warmindo-berkah&back=/c/{proA['code']}")
check("Warmindo Berkah" in r.get_data(as_text=True) and "Kembali ke menu" in r.get_data(as_text=True), "halaman login menyebut cafe dan bisa kembali ke menu")
r = login(owner, "berkah", "berkah-pass-1")
check(r.headers["Location"].endswith("/dashboard"), "pemilik cafe masuk ke dashboard")
check(owner.get("/admin").status_code == 302, "pemilik cafe tidak bisa membuka panel admin")
post(owner, "/dashboard/menu/kategori", {"name": "Mie"})
post(owner, "/dashboard/menu/kategori", {"name": "Minuman"})
with cafeee.app.app_context():
    cats = {r["name"]: r["id"] for r in cafeee.q("SELECT * FROM categories WHERE cafe_id=?", (A,))}
post(owner, "/dashboard/menu/item", {"name": "Indomie goreng telur", "price": "12000", "category_id": cats["Mie"], "available": "on", "description": "Pakai sawi"})
post(owner, "/dashboard/menu/item", {"name": "Es teh manis", "price": "4.000", "category_id": cats["Minuman"], "available": "on"})
with cafeee.app.app_context():
    items = {r["name"]: r for r in cafeee.q("SELECT * FROM items WHERE cafe_id=?", (A,))}
check(items["Es teh manis"]["price"] == 4000, "tambah menu, harga '4.000' terbaca 4000")
r = owner.post(f"/dashboard/menu/item/{items['Es teh manis']['id']}/harga", data={"price": "5000", "csrf_token": token(owner)})
check(r.get_json()["price"] == 5000, "ubah harga langsung dari tabel")
r = owner.post(f"/dashboard/menu/item/{items['Es teh manis']['id']}/stok", data={"csrf_token": token(owner)})
check(r.get_json()["available"] == 0, "tandai menu habis")
html = pub.get(f"/c/{proA['code']}").get_data(as_text=True)
check("Indomie goreng telur" in html and "5.000" in html and 'class="out"' in html, "pelanggan melihat menu baru, harga baru, dan tanda Habis")
check("Pakai sawi" in html, "keterangan menu tampil")
html_owner = owner.get(f"/c/{proA['code']}").get_data(as_text=True)
check("lock open" in html_owner, "gembok terbuka untuk pemilik yang sudah masuk")

print("Kasir dan nota")
import json  # noqa: E402
def pos(c, payload):
    return c.post("/dashboard/kasir/simpan", data=json.dumps(payload), content_type="application/json",
                  headers={"X-CSRF-Token": token(c)})
r = pos(owner, {"items": [{"id": items["Indomie goreng telur"]["id"], "qty": 2}, {"name": "Kerupuk", "price": 2000, "qty": 1}],
                "table": "Meja 4", "payment": "Tunai", "paid": "30000"})
j = r.get_json()
check(r.status_code == 200 and j["ok"], "pesanan disimpan")
with cafeee.app.app_context():
    o = cafeee.q("SELECT * FROM orders WHERE id=?", (j["id"],), one=True)
check(o["total"] == 26000 and o["change_amt"] == 4000, "total dihitung server (26.000), kembalian 4.000")
r = pos(owner, {"items": [{"id": items["Indomie goreng telur"]["id"], "qty": 1, "price": 1}], "payment": "Tunai", "paid": "5000"})
check(r.status_code == 400, "uang kurang ditolak; harga dari klien tidak dipercaya")
r = pos(owner, {"items": []})
check(r.status_code == 400, "pesanan kosong ditolak")
r = owner.get(j["url"])
html = r.get_data(as_text=True)
check("Warmindo Berkah" in html and "Meja 4" in html and "TOTAL" in html and "window.print()" in html, "nota termal tampil dan otomatis cetak")
check("@page { size: 58mm auto" in html, "ukuran kertas struk 58mm")
owner.post("/dashboard/pengaturan", data={"form": "profil", "name": "Warmindo Berkah", "paper_mm": "80", "tax_pct": "10", "service_pct": "5",
                                          "csrf_token": token(owner), "receipt_footer": "Makasih!"})
r = pos(owner, {"items": [{"id": items["Indomie goreng telur"]["id"], "qty": 1}], "payment": "QRIS"})
with cafeee.app.app_context():
    o2 = cafeee.q("SELECT * FROM orders ORDER BY id DESC LIMIT 1", one=True)
check((o2["service"], o2["tax"], o2["total"]) == (600, 1260, 13860), "service 5% dan pajak 10% terhitung (13.860)")
check("size: 80mm auto" in owner.get(f"/dashboard/nota/{o2['id']}").get_data(as_text=True), "ukuran kertas bisa diganti ke 80mm")
check("Rp 39.860" in owner.get("/dashboard").get_data(as_text=True), "ringkasan penjualan hari ini benar")
check(owner.get("/dashboard/nota").get_data(as_text=True).count("<tr>") >= 3, "riwayat nota tampil")

print("Isolasi antar cafe")
other = cafeee.app.test_client()
login(other, "senja", "senja-pass-12")
check(other.get(f"/dashboard/nota/{o['id']}").status_code == 404, "cafe lain tidak bisa membuka nota")
other.post(f"/dashboard/menu/item/{items['Es teh manis']['id']}/harga", data={"price": "1", "csrf_token": token(other)})
with cafeee.app.app_context():
    check(cafeee.q("SELECT price FROM items WHERE id=?", (items['Es teh manis']['id'],), one=True)["price"] == 5000, "cafe lain tidak bisa mengubah harga")
other.post(f"/dashboard/menu/item/{items['Es teh manis']['id']}/hapus", data={"csrf_token": token(other)})
with cafeee.app.app_context():
    check(cafeee.q("SELECT 1 FROM items WHERE id=?", (items['Es teh manis']['id'],), one=True) is not None, "cafe lain tidak bisa menghapus menu")
check("Warmindo Berkah" not in other.get(f"/c/{proB['code']}").get_data(as_text=True), "menu publik tiap kartu hanya milik cafenya")

print("Panel admin")
for path in ("/admin", "/admin/tags", f"/admin/tags/{proA['id']}", f"/admin/stiker?ids={proA['id']},{proB['id']}", "/admin/cafe", "/admin/pengaturan"):
    check(admin.get(path).status_code == 200, f"halaman {path} terbuka")
html = admin.get("/admin/tags").get_data(as_text=True)
check(f"https://cafeee.test/c/{proA['code']}?s=n" in html, "link NFC memakai alamat situs yang diatur")
r = admin.post("/admin/cafe/%d/masuk" % A, data={"csrf_token": token(admin)})
check("Mode admin" in admin.get("/dashboard").get_data(as_text=True), "admin bisa 'masuk sebagai' cafe untuk bantuan")
admin.post("/admin/keluar-cafe", data={"csrf_token": token(admin)})

print("Nonaktifkan cafe")
post(admin, f"/admin/cafe/{A}", {"action": "status"})
check("belum tersedia" in pub.get(f"/c/{proA['code']}").get_data(as_text=True).lower(), "menu cafe nonaktif tidak tampil ke pelanggan")
check(owner.get("/dashboard").status_code == 302, "pemilik cafe nonaktif dikeluarkan")
post(admin, f"/admin/cafe/{A}", {"action": "status"})

print("Batas percobaan login")
brute = cafeee.app.test_client()
codes = [login(brute, "berkah", f"salah{i}").status_code for i in range(10)]
check(429 in codes, "percobaan login berulang dikunci sementara")

print(f"\nSEMUA LULUS ({passed} pemeriksaan)")
