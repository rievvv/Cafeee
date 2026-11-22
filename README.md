# Cafeee

Sistem tag lokasi NFC dan QR untuk cafe dan warmindo.

- **Paket Basic (Rp100.000)**: kartu NFC dan stiker QR yang langsung membuka link ulasan Google toko.
- **Paket Pro (Rp200.000)**: pelanggan yang memindai melihat **menu digital**. Ada ikon **gembok** di pojok menu; pemilik menekannya untuk masuk ke dashboard (kelola menu, ubah harga, kasir, cetak nota). Pelanggan cukup melanjutkan melihat menu.
- **Panel pemilik Cafeee (Anda)**: buat kartu massal, cetak QR, atur tujuan link, kelola cafe pelanggan, lihat statistik pemindaian dan pendapatan.

Kunci sistem ini: kartu NFC dan QR hanya berisi link pendek (`https://domain-anda/c/kode`). Tujuannya disimpan di server, jadi bisa diganti kapan saja tanpa menulis ulang kartu.

## Menjalankan di komputer sendiri

Butuh Python 3.10 ke atas.

```bash
pip install -r requirements.txt
python app.py
```

Pada saat pertama dijalankan, akun admin dibuat dan **kata sandinya tampil sekali di layar**. Catat. Buka `http://localhost:5000/login`.

Ingin mencoba dengan data contoh?

```bash
python manage.py demo        # cafe "Warmindo Berkah", login: berkah / berkah123
python manage.py reset-admin SANDIBARU
```

Uji otomatis: `python tests/test_flow.py`

## Wajib sebelum menulis kartu NFC: pasang di internet dengan domain tetap

Link yang ditulis ke kartu memuat nama domain. **Domain tidak bisa diubah setelah kartu dibagikan**, jadi:

1. Beli domain yang akan dipakai selamanya (misalnya `cafeee.id`).
2. Pasang di VPS atau layanan hosting Python. Contoh produksi:
   ```bash
   pip install gunicorn
   CAFEEE_HTTPS=1 gunicorn -w 2 -b 127.0.0.1:8000 app:app
   ```
   Letakkan di belakang Caddy atau Nginx agar ada HTTPS otomatis.
3. Masuk ke **Pengaturan** di panel admin, isi **Alamat situs** (`https://cafeee.id`). Baru setelah itu buat dan tulis kartu.

| Variabel | Fungsi |
|---|---|
| `CAFEEE_DATA` | Folder database dan kunci rahasia (default `./data`) |
| `CAFEEE_BASE_URL` | Alamat situs bila belum diisi di Pengaturan |
| `CAFEEE_ADMIN_USER`, `CAFEEE_ADMIN_PASS` | Akun admin pertama |
| `CAFEEE_HTTPS=1` | Cookie hanya lewat HTTPS (aktifkan di produksi) |
| `PORT` | Port saat `python app.py` |

**Cadangan data**: salin folder `data/` secara rutin (terutama `cafeee.db`). Seluruh menu, nota, dan kartu ada di sana.

## Alur kerja Anda

### Paket Basic (100rb)
1. Panel admin, **Kartu dan QR**, **Buat kartu baru**: pilih Basic, isi jumlah dan link Google Review toko.
2. Sistem membuka **lembar cetak QR**. Cetak untuk stiker, atau unduh PNG/SVG satuan untuk dimasukkan ke desain stiker custom.
3. Salin **link NFC** kartu, lalu tulis dengan NFC Tools:
   - Write, Add a record, URL/URI, tempel link, Write, tempelkan kartu NTAG215.
4. Tes dengan HP. Jika benar, **kunci kartu** (NFC Tools: Other, Lock tag). Kartu NTAG215 yang tidak dikunci bisa ditimpa siapa saja yang membawa HP, jadi langkah ini penting. Kunci bersifat permanen, dan karena tujuan diatur dari server Anda tidak pernah perlu menulis ulang kartu.
5. Jika link Google Review pelanggan berubah, cukup edit di halaman kartu.

### Paket Pro (200rb)
1. **Cafe pelanggan**, **Tambah cafe baru**: isi nama, username pemilik, kata sandi awal.
2. **Kartu dan QR**, buat kartu Pro dan pilih cafe-nya (atau hubungkan nanti di halaman kartu).
3. Tulis NFC dan cetak QR seperti Basic. Serahkan username dan kata sandi ke pemilik.
4. Pemilik memindai kartunya, menekan **gembok**, masuk, lalu mengisi menu. Pelanggan yang memindai melihat menu terbaru.

Tombol **Buka dashboard** di daftar cafe memungkinkan Anda masuk sebagai cafe tersebut untuk membantu pelanggan.

## Cetak nota ke printer struk

Nota dibuat sebagai halaman struk dengan ukuran kertas 58 mm atau 80 mm (diatur per cafe). Pasang printer struk di komputer atau HP seperti printer biasa, lalu tekan **Simpan dan cetak nota** di kasir. Agar langsung tercetak tanpa jendela konfirmasi, jalankan Chrome dengan opsi `--kiosk-printing`.

## Keamanan yang sudah ada

- Kata sandi disimpan terenkripsi (hash), login dibatasi 8 percobaan per 10 menit.
- Perlindungan CSRF pada semua perubahan data; cookie `HttpOnly` dan `SameSite`.
- Data tiap cafe terpisah: cafe lain tidak bisa membuka atau mengubah menu dan notanya.
- Harga nota selalu dihitung ulang di server, bukan dari browser.
- Link tujuan hanya menerima `http://` atau `https://`.
- Log pemindaian hanya menyimpan sidik IP harian yang teracak, bukan alamat IP asli. Pratinjau link dari WhatsApp dan bot tidak dihitung.

## Struktur

```
app.py        server, database, semua halaman
qrgen.py      pembuat QR (tanpa library tambahan)
manage.py     data demo dan reset sandi admin
templates/    tampilan
static/       CSS dan JS
tests/        uji otomatis alur lengkap
```
