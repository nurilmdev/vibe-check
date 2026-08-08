# ⚙️ Setup & Instalasi

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

### Cara menemukan selector yang tepat:

1. Set `HEADLESS=false` di `.env`
2. Jalankan script
3. Saat browser terbuka, klik kanan elemen → **Inspect**
4. Perhatikan atribut `data-testid`, `id`, atau `class` pada elemen tersebut
5. Update selector di file module yang sesuai

## 🍜 Pipeline UMKM FnB Bandung (CSV-only, tanpa database)

Pipeline ETL terpisah (branch `fnb-umkm-crawl`) untuk mengumpulkan leads UMKM Food & Beverage di Bandung. **Tidak menggunakan PostgreSQL** — output murni file CSV.

### Phase 1 — Extract (scraping leads mentah)

**Full crawl — Query Multiplier** (29 keyword F&B viral × 39 area Bandung Raya = 1.131 query):

```bash
venv\Scripts\python -m modules.scrape_umkm_multiplier                                        # full crawl (auto-resume)
venv\Scripts\python -m modules.scrape_umkm_multiplier --max-queries 2 --max-per-query 3      # smoke test
venv\Scripts\python -m modules.scrape_umkm_multiplier --fresh                                # mulai dari nol
```

- Job berjalan puluhan jam: progress tersimpan di `scrape_progress.txt` — aman di-stop, jalankan lagi untuk resume (query selesai di-skip, URL duplikat di-skip)
- Guard anti-blokir: deteksi CAPTCHA → cooldown 10–20 menit → restart session → retry 1×; jika tetap terblokir, run berhenti rapi (tinggal resume). Browser auto-restart tiap 100 query selesai
- Setiap record langsung disimpan real-time (append) ke `raw_umkm_leads.csv`, dengan random delay 2–5 detik antar aksi
- Kolom: `Name, Category, Reviews_Count, Phone_Number, Website_URL, Google_Maps_URL, Source_Query`

Versi ringkas 4-query (smoke test cepat):

```bash
venv\Scripts\python -m modules.scrape_umkm                      # 4 query umum
venv\Scripts\python -m modules.scrape_umkm --max-per-query 10   # tes cepat
```

### Phase 2 — Transform & Load (filter heuristik)

```bash
venv\Scripts\python filter_umkm_leads.py
```

Tahapan: dedup baris berdasarkan `Name`, lalu baris hanya lolos jika memenuhi SEMUA aturan: bukan kopi/kafe, `1 <= Reviews_Count <= 1000`, nomor HP berawalan `08`/`+628` (target WhatsApp), dan website mengandung `instagram.com`/`linktr.ee`. Hasilnya disimpan ke `clean_umkm_bandung.csv`.

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

## Docker

docker compose start / stop: Hanya menyalakan atau mematikan layanan tanpa menghapus container. Digunakan jika Anda ingin menghentikan sementara aktivitas server.
docker compose restart <nama_service>: Mematikan dan menyalakan kembali container. Sangat cepat karena tidak mengubah apa pun pada sistem file.

docker compose up -d: Perintah "pintar" yang akan mengecek perubahan pada docker-compose.yml. Jika tidak ada perubahan, ia tidak akan melakukan apa-apa.

docker compose down: Menghentikan dan menghapus container serta jaringan internalnya. Data database aman selama Anda menggunakan volumes.
