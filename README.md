# Atlassian Admin Automation

Automation tool berbasis browser (Playwright) untuk:

1. **Scraping data** — ambil value dari kolom tertentu di Atlassian Admin
2. **Token Renewal** — otomatis hapus token lama & buat token baru

> Tool ini mengotomasi browser layaknya manusia — tidak menggunakan Atlassian REST API.

---

## 📁 Struktur Project

```
atlassian-automation/
├── .env                      ← credentials (buat dari .env.example)
├── .env.example              ← template konfigurasi
├── requirements.txt
├── main.py                   ← entry point
│
├── config/
│   └── settings.py           ← load env vars
│
├── core/
│   ├── browser.py            ← setup Playwright browser
│   ├── exceptions.py         ← custom exceptions
│   └── logger.py             ← konfigurasi loguru
│
├── modules/
│   ├── login.py              ← login + MFA handler
│   ├── scraper.py            ← ambil data kolom dari tabel
│   └── token_renewal.py      ← create/delete API token via UI
│
├── scheduler/
│   └── jobs.py               ← scheduled jobs (harian/bulanan)
│
├── tests/
│   ├── test_scraper.py
│   └── test_token_renewal.py
│
├── logs/                     ← auto-generated log files
└── screenshots/              ← auto-saved saat ada error
```

---

## ⚙️ Setup & Instalasi

### 1. Prasyarat

- Python 3.10 atau lebih baru
- pip

### 2. Clone / Extract project

```bash
cd atlassian-automation
```

### 3. Buat virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Install Playwright browser

```bash
playwright install chromium
```

### 6. Setup konfigurasi

```bash
cp .env.example .env
```

Buka file `.env` dan isi dengan nilai yang sesuai:

```env
ATLASSIAN_EMAIL=kamu@perusahaan.com
ATLASSIAN_PASSWORD=password_kamu
ATLASSIAN_TOTP_SECRET=secret_dari_authenticator_app  # jika pakai MFA
HEADLESS=false  # ganti true untuk mode background
```

---

## 🚀 Cara Menjalankan

### Jalankan semua job sekali

```bash
python main.py
```

### Hanya scraping

```bash
python main.py --scrape
```

### Hanya renewal token

```bash
python main.py --renew-token
```

### Mode scheduler (berjalan terus-menerus)

```bash
python main.py --schedule
```

---

## 🔧 Kustomisasi Selector

> ⚠️ **PENTING:** Selector HTML di file `modules/scraper.py` dan `modules/token_renewal.py`
> perlu disesuaikan dengan struktur HTML aktual halaman Atlassian kamu.

### Cara menemukan selector yang tepat:

1. Set `HEADLESS=false` di `.env`
2. Jalankan script
3. Saat browser terbuka, klik kanan elemen → **Inspect**
4. Perhatikan atribut `data-testid`, `id`, atau `class` pada elemen tersebut
5. Update selector di file module yang sesuai

### Contoh selector yang umum di Atlassian:

```python
# Tabel users
page.wait_for_selector("[data-testid='user-table']")

# Tombol create token
page.click("button:has-text('Create API token')")

# Field input label token
page.fill("input[name='label']", "nama-token")
```

---

# Gmail API Setup — Atlassian OTP Integration

## Prasyarat

- Akun Google / Gmail yang digunakan untuk login Atlassian
- Project sudah terinstall dan virtual environment aktif
- File `modules/gmail_otp.py` sudah ada di project

---

## Step 1 — Buat Project di Google Cloud Console

1. Buka **https://console.cloud.google.com**
2. Login dengan Gmail yang sama dengan akun Atlassian
3. Klik dropdown project di navbar atas → **"New Project"**
4. Isi nama project: `atlassian-automation` → klik **Create**
5. Tunggu selesai, lalu pastikan project `atlassian-automation` **aktif/terpilih** di dropdown

---

## Step 2 — Aktifkan Gmail API

1. Menu kiri → **"APIs & Services"** → **"Library"**
2. Pada kolom pencarian ketik `Gmail API`
3. Klik hasil **Gmail API** → klik tombol **"Enable"**
4. Tunggu hingga status berubah menjadi **Enabled**

---

## Step 3 — Setup OAuth Consent Screen

1. Menu kiri → **"APIs & Services"** → **"OAuth consent screen"**
2. Klik get started lalu isi form berikut
   - **App name**: `atlassian-automation`
   - **User support email**: pilih email Gmail kamu
   - **Developer contact information**: isi email Gmail kamu
3. Pada section **Audience** pilih **External**
4. Isi contact information dengan email yang digunakan lalu klik **Create**

---

## Step 4 — Buat OAuth Credentials

1. Menu kiri → **"APIs & Services"** → **"Credentials"**
2. Klik **"+ Create Credentials"** → pilih **"OAuth client ID"**
3. Pada **Application type** pilih **Desktop app**
4. Isi **Name**: `atlassian-automation` → klik **Create**
5. Pada dialog yang muncul klik **"Download JSON"**
6. Rename file hasil download menjadi **`credentials.json`**
7. Pindahkan file `credentials.json` ke **root folder project** (sejajar dengan `main.py`)

---

## Step 5 - Tambahkan User Email sebagai tester

1. Menu kiri → **"APIs & Services"** → **"Credentials"**
2. Pilih dan klik nama OAuth 2.0 Client IDs -> `atlassian-automation`
3. Pada bagian kiri, pilih **"Audience"** -> **"Add Users"** pada bagian **"Test Users"**
4. Masukkan email Gmail kamu → klik **Add** → klik **Save**

---

## Step 6 — Generate `token.json`

Pastikan virtual environment sudah aktif, lalu jalankan:

```bash
python -c "from modules.gmail_otp import get_gmail_service; get_gmail_service()"
```

Browser Google akan terbuka secara otomatis:

1. Pilih akun Gmail kamu
2. Jika muncul warning **"unverified app"** → klik **"Advanced"** → klik **"Go to atlassian-automation (unsafe)"**
3. Klik **"Allow"**
4. Browser akan menampilkan pesan sukses

File `token.json` akan otomatis tersimpan di root folder project.

---

## Verifikasi

Jalankan perintah berikut untuk memastikan koneksi Gmail API berhasil:

```bash
python -c "from modules.gmail_otp import get_gmail_service; get_gmail_service(); print('Gmail API OK')"
```

Output yang diharapkan:

```
SUCCESS | Gmail API connected successfully.
Gmail API OK
```

---

## Troubleshooting

| Error                        | Penyebab                                  | Solusi                                           |
| ---------------------------- | ----------------------------------------- | ------------------------------------------------ |
| `Access blocked`             | Email belum ditambahkan sebagai test user | Kembali ke Step 3, tambahkan email di Test users |
| `credentials.json not found` | File tidak ada di root folder             | Pastikan file ada sejajar dengan `main.py`       |
| `invalid_grant`              | `token.json` expired atau di-revoke       | Hapus `token.json`, jalankan ulang Step 5        |
| `ModuleNotFoundError`        | Jalankan dari folder yang salah           | Pastikan berada di root folder project           |

---

## Catatan Penting

- Jangan commit `credentials.json` dan `token.json` ke Git
- Pastikan kedua file sudah ada di `.gitignore`:
  ```
  credentials.json
  token.json
  ```
- Token akan **expired dalam 7 hari** jika app masih dalam mode Testing setelah mencapai 7 hari akan mengalami Error Gmail API invalid_grant: Token has been expired or revoked.
- Untuk token yang lebih tahan lama, publish app ke Production di OAuth consent screen → klik **"Publish App"**

---

## 🧪 Menjalankan API

Pastikan `INTERNAL_API_KEY` pada file `.env` sudah ada dan terisi.

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

### Untuk jalankan secara service di server linux

Buat file konfigurasi terlebih dahulu

```bash
sudo nano /etc/systemd/system/token-api.service
```

```bash
[Unit]
Description=Atlassian Token API (FastAPI)
After=network.target

[Service]
User=nama_user_anda
WorkingDirectory=/opt/atlassian-automation
EnvironmentFile=/opt/atlassian-automation/.env
# Memanggil uvicorn langsung dari dalam virtual environment
ExecStart=/opt/atlassian-automation/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Command menyalakan API

```bash
sudo systemctl daemon-reload
sudo systemctl start token-api
sudo systemctl enable token-api
```

Setiap ada perubahan pada file api.py atau .env yang berkaitan dengan API harus dilakukan **Restart**

```bash
sudo systemctl restart token-api
```

Untuk cek log API, gunakan perintah

```bash
sudo journalctl -u token-api -f
```

Akses API dengan URL

```bash
http://IP_SERVER:8000/api/token/latest
```

Atau jika ingin melihat dokumentasi swagger bisa akses melalui URL

```bash
http://IP_SERVER:8000/docs
```

---

## 📋 Konfigurasi Lengkap `.env`

| Variable                       | Keterangan                                    | Default                        |
| ------------------------------ | --------------------------------------------- | ------------------------------ |
| `ATLASSIAN_EMAIL`              | Email login Atlassian                         | _(wajib)_                      |
| `ATLASSIAN_PASSWORD`           | Password Atlassian                            | _(wajib)_                      |
| `ATLASSIAN_TOKEN_URL`          | URL halaman API Token                         | `https://id.atlassian.com/...` |
| `HEADLESS`                     | Mode headless browser                         | `false`                        |
| `TOKEN_RENEWAL_INTERVAL_DAYS`  | Interval renewal token (hari)                 | `30`                           |
| `PAGE_WITH_SESSION`            | Login dengan sesi yang sudah ada              | `false`                        |
| `TOKEN_RENEWAL_THRESHOLD_DAYS` | Ambang batas sisa waktu token akan diperbarui | `0`                            |
| `LOG_LEVEL`                    | Level logging                                 | `INFO`                         |

---

## ⚠️ Catatan Penting

- **Jangan commit file `.env`** ke Git — sudah ada di `.gitignore`
- **Simpan token baru** yang muncul di log segera setelah renewal — Atlassian hanya menampilkan sekali
- **Dedicated account** — disarankan membuat akun Atlassian khusus untuk automation, bukan akun personal
- **Selector bisa berubah** — Atlassian sering update UI mereka, selector perlu dicek berkala

---

## 🐛 Troubleshooting

| Masalah                            | Solusi                                                                                               |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Login gagal                        | Cek `.env`, pastikan email & password benar                                                          |
| Selector tidak ditemukan           | Set `HEADLESS=false`, inspect element, update selector, cek file error_dom_dump.html                 |
| Browser tidak terbuka              | Jalankan `playwright install chromium`                                                               |
| Screenshot error tersimpan         | Cek folder `screenshots/` untuk debug visual                                                         |
| Atlassian meminta OTP Code 6 digit | Cek email 6 digit kombinasi angka & huruf, input melalui console. jika gagal, jalankan ulang main.py |
