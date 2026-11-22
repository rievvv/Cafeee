"""Perintah bantu Cafeee.

  python manage.py demo                 isi data contoh (cafe, menu, kartu)
  python manage.py reset-admin SANDI    ganti kata sandi akun admin
"""
import sys

from werkzeug.security import generate_password_hash

import app as cafeee

MENU = {
    "Mie": [("Indomie goreng telur", 12000, "Pakai sawi dan cabai"), ("Mie kuah rawit", 11000, ""),
            ("Indomie goreng double", 15000, "Dua bungkus"), ("Mie nyemek", 13000, "Kuah sedikit, pedas")],
    "Nasi": [("Nasi telur", 10000, ""), ("Nasi sarden", 12000, ""), ("Nasi ayam geprek", 16000, "Sambal bawang")],
    "Minuman": [("Es teh manis", 4000, ""), ("Kopi susu", 10000, ""), ("Es jeruk", 6000, ""), ("Susu jahe", 7000, "Hangat")],
    "Camilan": [("Kerupuk", 2000, ""), ("Gorengan (3 pcs)", 5000, "")],
}


def demo():
    with cafeee.app.app_context():
        if cafeee.q("SELECT 1 FROM cafes WHERE slug='warmindo-berkah'", one=True):
            print("Data demo sudah ada.")
            return
        cur = cafeee.ex("INSERT INTO cafes(name,slug,address,phone,review_url,paper_mm,created_at) VALUES(?,?,?,?,?,?,?)",
                        ("Warmindo Berkah", "warmindo-berkah", "Jl. Melati No. 12, Pasarkemis", "0812-3456-7890",
                         "https://g.page/r/contoh/review", 58, cafeee.now()))
        cid = cur.lastrowid
        cafeee.ex("INSERT INTO users(username,password_hash,role,cafe_id,created_at) VALUES(?,?,?,?,?)",
                  ("berkah", generate_password_hash("berkah123"), "cafe", cid, cafeee.now()))
        for n, (cat, rows) in enumerate(MENU.items(), 1):
            cat_id = cafeee.ex("INSERT INTO categories(cafe_id,name,sort) VALUES(?,?,?)", (cid, cat, n)).lastrowid
            for name, price, desc in rows:
                cafeee.ex("INSERT INTO items(cafe_id,category_id,name,description,price,available) VALUES(?,?,?,?,?,?)",
                          (cid, cat_id, name, desc, price, 0 if name == "Kopi susu" else 1))
        code = cafeee.new_code()
        cafeee.ex("INSERT INTO tags(code,kind,label,cafe_id,price,buyer_name,sold_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (code, "pro", "Meja kasir", cid, 200000, "Pak Budi", cafeee.now(), cafeee.now()))
        for label, buyer in (("Kopi Senja", "Mbak Rina"), ("Bakso Pak Slamet", "Pak Slamet"), ("", "")):
            cafeee.ex("INSERT INTO tags(code,kind,label,target_url,price,buyer_name,sold_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (cafeee.new_code(), "basic", label, "https://g.page/r/contoh/review" if label else "", 100000, buyer,
                       cafeee.now() if buyer else None, cafeee.now()))
        print(f"Demo siap. Cafe: username 'berkah', sandi 'berkah123'. Link menu: /c/{code}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "demo":
        demo()
    elif cmd == "reset-admin" and len(sys.argv) > 2:
        if len(sys.argv[2]) < 8:
            sys.exit("Kata sandi minimal 8 karakter.")
        with cafeee.app.app_context():
            cafeee.ex("UPDATE users SET password_hash=? WHERE role='admin'", (generate_password_hash(sys.argv[2]),))
        print("Kata sandi admin diganti.")
    else:
        print(__doc__)
