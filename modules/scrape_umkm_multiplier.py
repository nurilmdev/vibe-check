"""
UMKM FnB Greater Bandung Scraper — Phase 1 (Extract) dengan Query Multiplier
=============================================================================
Strategi "Micro-Location & Keyword Multiplier": nested loop 29 keyword F&B viral
x 39 distrik/area Bandung Raya = 1.131 kombinasi query, untuk menembus batas
tampilan 120 hasil Google Maps dan menjangkau UMKM niche/viral.

Pipeline CSV-only (TANPA database PostgreSQL). Setiap record LANGSUNG disimpan
(APPEND mode, flush per baris) ke: raw_umkm_leads.csv

Fitur tahan-putus (job ini bisa berjalan puluhan jam):
- Checkpoint scrape_progress.txt: query yang selesai penuh dicatat & di-skip
  saat resume.
- Dedup Google_Maps_URL lintas query, di-rebuild dari CSV saat start.
- Random delay 2-5 detik antar aksi (anti rate-limit).
- Guard CAPTCHA/blokir: deteksi otomatis -> cooldown 10-20 menit -> restart
  session -> retry 1x; jika masih terblokir, berhenti rapi (tinggal resume).
- Auto-restart browser tiap 100 query selesai (memory hygiene).

Prinsip DRY — TIDAK ada logika browser/scroll/ekstraksi yang dibuat ulang:
    - core.browser               : get_page_with_session(), close_browser()
    - modules.navigate           : navigate_gmaps_search()
    - modules.scrape_coffeeshops : scroll_place_feed()
    - modules.scrape_umkm        : extract_place_contacts(), parse_reviews_count(), CSV_FIELDNAMES

Jalankan dari root project:
    venv\\Scripts\\python -m modules.scrape_umkm_multiplier                          # full crawl (resume otomatis)
    venv\\Scripts\\python -m modules.scrape_umkm_multiplier --max-queries 2 --max-per-query 3   # smoke test
    venv\\Scripts\\python -m modules.scrape_umkm_multiplier --fresh                  # mulai dari nol (hapus checkpoint & CSV lama)
"""

import argparse
import csv
import os
import random
import time

from loguru import logger

from core.browser import get_page_with_session, close_browser, close_session_browser
from core.logger import setup_logger
from modules.navigate import navigate_gmaps_search, is_blocked_page
from modules.scrape_coffeeshops import scroll_place_feed
from modules.scrape_umkm import (
    CSV_FIELDNAMES,
    extract_place_contacts,
    parse_reviews_count,
)

# Viral & Modern F&B Keywords (Strictly NO Coffee/Cafe)
FOOD_KEYWORDS = [
    "Dimsum", "Baso Aci", "Seblak", "Takoyaki", "Croffle",
    "Corndog", "Dessert Box", "Roti Bakar", "Martabak", "Kue Balok",
    "Cilok", "Batagor", "Siomay", "Jajanan Korea", "Tteokbokki",
    "Rice Bowl", "Ayam Geprek", "Seafood Kiloan", "Mie Pedas", "Burger",
    "Sate Taichan", "Bebek Goreng", "Iga Bakar", "Nasi Kulit",
    "Es Coklat", "Thai Tea", "Boba", "Gelato", "Susu Murni"
]

# Greater Bandung Districts & Strategic Spots
AREAS = [
    "Andir", "Antapani", "Arcamanik", "Astanaanyar", "Babakanciparay",
    "Bandung Kidul", "Bandung Kulon", "Bandung Wetan", "Batununggal",
    "Bojongloa", "Buahbatu", "Cibeunying", "Cibiru", "Cicendo",
    "Cidadap", "Cinambo", "Coblong", "Gedebage", "Kiaracondong",
    "Lengkong", "Mandalajati", "Panyileukan", "Rancasari", "Regol",
    "Sukajadi", "Sukasari", "Sumurbandung", "Ujungberung",
    "Dago", "Dipatiukur", "Braga", "Ciumbuleuit", "Setiabudi",
    "Cibaduyut", "Kopo", "Pasteur", "Surapati", "Burangrang", "Cimahi"
]

RAW_OUTPUT_FILE = "raw_umkm_leads.csv"
PROGRESS_FILE = "scrape_progress.txt"

TOTAL_QUERIES = len(FOOD_KEYWORDS) * len(AREAS)  # 29 x 39 = 1131

# --- Guard anti-blokir & memory hygiene ---
CAPTCHA_COOLDOWN_RANGE = (600, 1200)   # cooldown saat terdeteksi blokir: 10-20 menit (detik)
MAX_CONSECUTIVE_NAV_FAILURES = 3       # N kegagalan navigasi beruntun dianggap terblokir
BROWSER_RESTART_INTERVAL = 100         # restart browser tiap N query selesai (memory hygiene)


def build_queries() -> list:
    """
    Nested loop keyword x area (keyword outer, area inner) sesuai prompt:
    "Dimsum Andir", "Dimsum Antapani", ..., "Susu Murni Cimahi".
    """
    return [f"{keyword} {area}" for keyword in FOOD_KEYWORDS for area in AREAS]


def load_completed_queries(progress_file=PROGRESS_FILE) -> set:
    """Baca checkpoint: kumpulan query yang sudah selesai penuh (untuk resume)."""
    if not os.path.exists(progress_file):
        return set()
    with open(progress_file, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def mark_query_completed(query: str, progress_file=PROGRESS_FILE):
    """Catat query yang selesai penuh ke checkpoint (append + flush seketika)."""
    with open(progress_file, "a", encoding="utf-8") as f:
        f.write(query + "\n")


def load_seen_urls(output_file: str) -> set:
    """Rebuild set dedup Google_Maps_URL dari CSV existing (untuk resume)."""
    seen = set()
    if not os.path.exists(output_file):
        return seen
    try:
        with open(output_file, "r", newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                url = (row.get("Google_Maps_URL") or "").strip()
                if url:
                    seen.add(url)
    except Exception as e:
        logger.warning(f"⚠️ Gagal membaca CSV existing untuk dedup resume: {e}")
    return seen


def human_delay(min_seconds=2.0, max_seconds=5.0):
    """Jeda acak antar aksi (interpretasi dari 'random time.sleep(2, 5)' di prompt)."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def navigate_with_guard(page, query: str, nav_state: dict):
    """
    Navigasi dengan guard anti-blokir (CAPTCHA/rate-limit Google).

    nav_state: dict mutable penampung counter kegagalan beruntun (key "failures").

    Return: (page, status)
      "ok"    -> navigasi berhasil, lanjutkan query seperti biasa
      "retry" -> kegagalan biasa, skip query ini (lanjut query berikutnya)
      "stop"  -> masih terblokir setelah cooldown + restart session; hentikan run
                 secara rapi (checkpoint & CSV aman; solve CAPTCHA manual lalu resume)
    Catatan: page bisa berupa instance BARU bila session direstart saat cooldown.
    """
    try:
        navigate_gmaps_search(page, query)
        nav_state["failures"] = 0
        return page, "ok"
    except Exception as e:
        nav_state["failures"] += 1
        blocked = is_blocked_page(page)

        if not blocked and nav_state["failures"] < MAX_CONSECUTIVE_NAV_FAILURES:
            logger.error(f"❌ Navigasi gagal untuk '{query}': {e}. Lanjut ke query berikutnya.")
            human_delay()
            return page, "retry"

        reason = ("CAPTCHA/halaman blokir terdeteksi" if blocked
                  else f"{MAX_CONSECUTIVE_NAV_FAILURES} kegagalan navigasi beruntun")
        cooldown = random.uniform(*CAPTCHA_COOLDOWN_RANGE)
        logger.warning(f"🛡️ {reason}. Cooldown {cooldown / 60:.1f} menit sebelum retry...")
        time.sleep(cooldown)

        logger.info("♻️ Restart session browser pasca-cooldown...")
        close_session_browser()
        human_delay()
        page = get_page_with_session()

        try:
            navigate_gmaps_search(page, query)
            nav_state["failures"] = 0
            logger.success("✅ Akses pulih setelah cooldown. Lanjut scraping.")
            return page, "ok"
        except Exception as e2:
            logger.error(
                f"🛑 Masih terblokir setelah cooldown ({e2}). Berhenti rapi — "
                "solve CAPTCHA manual di profile browser_session_gmaps, lalu jalankan lagi untuk resume."
            )
            return page, "stop"


def run_extraction(output_file=RAW_OUTPUT_FILE, max_per_query=None, max_queries=None, fresh=False):
    """
    Orkestrasi Phase 1 multiplier: nested loop query -> scroll feed -> ekstrak kontak
    -> simpan CSV (append, flush per baris). Resume via checkpoint + dedup URL.
    """
    setup_logger()
    logger.info(f"🚀 Mulai Query Multiplier UMKM FnB Bandung Raya -> {output_file}")

    queries = build_queries()
    total_queries = len(queries)

    if fresh:
        # Mode fresh: mulai dari nol — hapus checkpoint & CSV lama
        for path in (PROGRESS_FILE, output_file):
            if os.path.exists(path):
                os.remove(path)
                logger.warning(f"🗑️ --fresh: menghapus {path}")

    completed_queries = load_completed_queries()
    seen_urls = load_seen_urls(output_file)
    already_done = sum(1 for q in queries if q in completed_queries)

    logger.info(f"Total kombinasi query: {total_queries} ({len(FOOD_KEYWORDS)} keyword x {len(AREAS)} area)")
    if already_done:
        logger.info(f"⏭️ Resume: {already_done} query sudah selesai sebelumnya dan akan di-skip.")
    if seen_urls:
        logger.info(f"🔗 Dedup: {len(seen_urls)} URL dari CSV existing dimuat.")

    is_new_file = not os.path.exists(output_file) or os.path.getsize(output_file) == 0
    page = get_page_with_session()
    total_written = 0
    queries_done_this_run = 0
    nav_state = {"failures": 0}  # counter kegagalan navigasi beruntun (untuk deteksi blokir)

    # APPEND mode: data lama aman; header hanya ditulis jika file baru/kosong
    with open(output_file, "a", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES)
        if is_new_file:
            writer.writeheader()
            csv_file.flush()

        try:
            for idx, query in enumerate(queries, start=1):
                if max_queries is not None and queries_done_this_run >= max_queries:
                    logger.info(f"🛑 Batas --max-queries {max_queries} tercapai.")
                    break

                if query in completed_queries:
                    continue  # resume: skip query yang sudah selesai penuh

                logger.info(f"\n🔎 Scraping query {idx}/{total_queries}: {query}...")
                page, nav_status = navigate_with_guard(page, query, nav_state)
                if nav_status == "stop":
                    break  # berhenti rapi: checkpoint & CSV sudah tersimpan, tinggal resume
                if nav_status == "retry":
                    continue

                # --- Tahap A: scroll panel hasil & kumpulkan kartu tempat baru (reuse) ---
                new_cards = []
                try:
                    for card in scroll_place_feed(page, max_results=max_per_query):
                        if card["url"] in seen_urls:
                            continue
                        seen_urls.add(card["url"])
                        new_cards.append(card)
                except Exception as e:
                    logger.error(f"❌ Scroll feed gagal untuk '{query}': {e}. Lanjut ke query berikutnya.")
                    human_delay()
                    continue

                logger.info(f"📋 '{query}' -> {len(new_cards)} tempat baru. Mulai ekstraksi kontak...")

                # --- Tahap B: kunjungi tiap tempat, ekstrak kontak, simpan real-time ---
                for card in new_cards:
                    try:
                        contacts = extract_place_contacts(page, card["url"])
                        row = {
                            "Name": card["name"],
                            "Category": card["category"],
                            "Reviews_Count": parse_reviews_count(card["reviews"]),
                            "Phone_Number": contacts["Phone_Number"],
                            "Website_URL": contacts["Website_URL"],
                            "Google_Maps_URL": card["url"],
                            "Source_Query": query,
                        }
                        writer.writerow(row)
                        csv_file.flush()  # real-time save per record (append)
                        total_written += 1
                        logger.info(
                            f"[{total_written}] 💾 {row['Name']} | 🏷️ {row['Category'] or '-'} "
                            f"| 💬 {row['Reviews_Count']} ulasan | 📞 {row['Phone_Number'] or '-'} "
                            f"| 🌐 {row['Website_URL'] or '-'}"
                        )
                    except Exception as e:
                        logger.error(f"❌ Gagal memproses '{card.get('name')}': {e}. Lanjut ke tempat berikutnya.")
                        continue

                    human_delay()  # random 2-5 detik antar aksi (anti rate-limit)

                # Query selesai penuh -> catat checkpoint agar resume bisa skip
                mark_query_completed(query)
                completed_queries.add(query)
                queries_done_this_run += 1

                # Auto-restart browser berkala: memory hygiene untuk run puluhan jam
                if queries_done_this_run % BROWSER_RESTART_INTERVAL == 0:
                    logger.info(f"♻️ Restart browser berkala (setiap {BROWSER_RESTART_INTERVAL} query selesai)...")
                    close_session_browser()
                    human_delay()
                    page = get_page_with_session()

                human_delay()  # jeda antar query
        finally:
            close_session_browser()  # menutup context + browser + driver Playwright session
            close_browser()

    logger.success(
        f"\n✅ Selesai. {queries_done_this_run} query diproses pada run ini, "
        f"{total_written} leads baru ditambahkan ke {output_file}."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Scraper UMKM FnB Bandung Raya — Query Multiplier (CSV-only, tanpa database)"
    )
    parser.add_argument("--output", default=RAW_OUTPUT_FILE, help="File CSV output mentah (default: raw_umkm_leads.csv)")
    parser.add_argument("--max-per-query", type=int, default=None, help="Batas maksimal tempat per query (default: semaksimal mungkin)")
    parser.add_argument("--max-queries", type=int, default=None, help="Batas jumlah query yang diproses pada run ini (untuk tes)")
    parser.add_argument("--fresh", action="store_true", help="Mulai dari nol: hapus checkpoint & CSV lama")
    args = parser.parse_args()

    run_extraction(
        output_file=args.output,
        max_per_query=args.max_per_query,
        max_queries=args.max_queries,
        fresh=args.fresh,
    )


if __name__ == "__main__":
    main()
