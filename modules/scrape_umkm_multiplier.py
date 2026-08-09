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
- Guard CAPTCHA/blokir: deteksi otomatis (termasuk consent wall) -> cooldown
  berjenjang 10-60 menit per episode -> restart session -> retry; jika tidak
  pulih setelah 3 episode, berhenti rapi (tinggal resume). Screenshot bukti
  otomatis tersimpan di folder screenshots/ saat navigasi timeout.
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
from modules.navigate import navigate_gmaps_search, is_blocked_page, extract_place_details_from_page, BANDUNG_CENTER
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
CAPTCHA_COOLDOWN_RANGE = (600, 1200)   # cooldown dasar saat terdeteksi blokir: 10-20 menit (detik)
MAX_CONSECUTIVE_NAV_FAILURES = 3       # N kegagalan navigasi beruntun dianggap terblokir
MAX_BLOCK_EPISODES = 3                 # berhenti rapi setelah N episode blokir beruntun (cooldown berjenjang per episode)
BROWSER_RESTART_INTERVAL = 100         # restart browser tiap N query selesai (memory hygiene)
STUCK_THRESHOLD = 300                # detik tanpa progress -> restart session (anti-hang/throttling halus)


def build_queries() -> list:
    """
    Nested loop keyword x area (keyword outer, area inner) sesuai prompt:
    "Dimsum Andir", "Dimsum Antapani", ..., "Susu Murni Cimahi".
    """
    return [f"{keyword} {area}" for keyword in FOOD_KEYWORDS for area in AREAS]


# --- Geo-anchor & drift guard (Fix: hasil search lari ke luar Bandung) ---
# Greater Bandung Raya bounding box (kota + Cimahi + Kab. Bandung/Barat).
# Jakarta (lat -6.1..-6.3, lng 106.6..106.9) berada DI LUAR box ini.
BANDUNG_LAT_RANGE = (-7.15, -6.75)
BANDUNG_LNG_RANGE = (107.35, 107.75)
SEARCH_LOCATION_ANCHOR = "Bandung"


def to_search_query(query: str) -> str:
    """
    Ubah kunci query (checkpoint) menjadi query pencarian Google Maps yang
    dijangkar ke Bandung, untuk mencegah Google menjatuhkan filter lokasi dan
    menampilkan hasil dari kota lain pada query niche.

    Kunci checkpoint TIDAK berubah (resume kompatibel); hanya query yang
    dikirim ke Google yang ditambah anchor. Idempoten (tidak dobel anchor).
    """
    q = (query or "").strip()
    if not q:
        return q
    return q if SEARCH_LOCATION_ANCHOR.lower() in q.lower() else f"{q} {SEARCH_LOCATION_ANCHOR}"


def extract_coords_from_url(url: str):
    """Ambil (lat, lng) dari pola '!3d<lat>!4d<lng>' pada Google_Maps_URL."""
    import re
    if not url:
        return None
    m = re.search(r"!3d(-?[0-9.]+)!4d(-?[0-9.]+)", url)
    if not m:
        return None
    try:
        return float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None


def is_in_bandung(url: str) -> bool:
    """
    True jika koordinat pada URL berada di dalam bounding box Bandung Raya.
    Jika koordinat tidak ter-parse, kembalikan True (jangan buang data yang
    tidak bisa diverifikasi - biarkan aturan lain yang menilai).
    """
    coords = extract_coords_from_url(url)
    if coords is None:
        return True
    lat, lng = coords
    return (BANDUNG_LAT_RANGE[0] <= lat <= BANDUNG_LAT_RANGE[1]
            and BANDUNG_LNG_RANGE[0] <= lng <= BANDUNG_LNG_RANGE[1])


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
    Navigasi dengan guard anti-blokir (CAPTCHA/rate-limit/throttle Google).

    nav_state: dict mutable penampung state antar-query:
      - "failures": kegagalan navigasi beruntun
      - "blocks"  : episode blokir beruntun (cooldown berjenjang per episode)

    Return: (page, status)
      "ok"     -> halaman daftar hasil termuat, lanjutkan scroll-feed seperti biasa
      "place"  -> Google redirect ke place page tunggal; caller ekstrak langsung
      "retry"  -> kegagalan biasa, skip query ini (lanjut query berikutnya)
      "stop"   -> blokir tidak pulih setelah MAX_BLOCK_EPISODES episode cooldown;
                  hentikan run secara rapi (checkpoint & CSV aman, tinggal resume)
    Catatan: page bisa berupa instance BARU bila session direstart saat cooldown.
    """
    search_query = to_search_query(query)  # jangkar ke Bandung (anti-drift lokasi)
    while True:
        try:
            result = navigate_gmaps_search(page, search_query, location_override=BANDUNG_CENTER)
            nav_state["failures"] = 0
            nav_state["blocks"] = 0
            # Teruskan status navigate_gmaps_search: "results" -> "ok", "place" -> "place"
            return page, ("place" if result == "place" else "ok")
        except Exception as e:
            nav_state["failures"] += 1
            blocked = is_blocked_page(page)

            if not blocked and nav_state["failures"] < MAX_CONSECUTIVE_NAV_FAILURES:
                logger.error(f"❌ Navigasi gagal untuk '{query}': {e}. Lanjut ke query berikutnya.")
                human_delay()
                return page, "retry"

            # Episode blokir baru -> cooldown berjenjang (episode 1: 10-20 mnt,
            # episode 2: 20-40 mnt, episode 3: 30-60 mnt) lalu retry query yg sama
            nav_state["blocks"] += 1
            episode = nav_state["blocks"]

            if episode > MAX_BLOCK_EPISODES:
                logger.error(
                    f"🛑 Blokir tidak pulih setelah {MAX_BLOCK_EPISODES} episode cooldown ({e}). "
                    "Berhenti rapi — istirahatkan IP beberapa jam, lalu jalankan lagi untuk resume."
                )
                return page, "stop"

            reason = ("CAPTCHA/halaman blokir terdeteksi" if blocked
                      else f"{MAX_CONSECUTIVE_NAV_FAILURES} kegagalan navigasi beruntun")
            cooldown = random.uniform(*CAPTCHA_COOLDOWN_RANGE) * episode
            logger.warning(
                f"🛡️ {reason} (episode {episode}/{MAX_BLOCK_EPISODES}). "
                f"Cooldown {cooldown / 60:.1f} menit sebelum retry..."
            )
            time.sleep(cooldown)

            logger.info("♻️ Restart session browser pasca-cooldown...")
            close_session_browser()
            human_delay()
            page = get_page_with_session()
            # while loop -> retry query yang sama dengan session baru


def scrape_single_place(page, query, writer, csv_file, seen_urls):
    """
    Bonus capture: query niche dialihkan Google langsung ke halaman detail tunggal.
    Ekstrak tempat itu dari page yang sedang terbuka dan simpan real-time.

    Return: jumlah baris yang ditulis (0 atau 1).
    """
    place_url = page.url or ""
    if not place_url or place_url in seen_urls:
        logger.info(f"⏭️ Tempat tunggal untuk '{query}' sudah ada di CSV / URL kosong — skip.")
        return 0

    # Geo-guard: abaikan tempat tunggal yang koordinatnya di luar Bandung Raya
    if not is_in_bandung(place_url):
        logger.warning(f"[geo-skip] Tempat tunggal '{query}' di luar Bandung Raya -> tidak disimpan. URL: {place_url[:80]}")
        return 0

    details = extract_place_details_from_page(page)
    if not details:
        logger.warning(f"⚠️ Gagal membaca place page tunggal untuk '{query}' — skip.")
        return 0

    # Phone & Website: pakai extractor yang sudah ada (DRY). Page SUDAH di place
    # page -> panggil dengan URL kosong agar extractor tidak goto ulang (cukup baca
    # halaman yang terbuka). Jika implementasi extractor tetap goto, itu no-op aman.
    contacts = extract_place_contacts(page, place_url)

    row = {
        "Name": details["name"],
        "Category": details["category"],
        "Reviews_Count": details["reviews_count"],
        "Phone_Number": contacts["Phone_Number"],
        "Website_URL": contacts["Website_URL"],
        "Google_Maps_URL": place_url,
        "Source_Query": query,
    }
    writer.writerow(row)
    csv_file.flush()  # real-time save
    seen_urls.add(place_url)
    logger.info(
        f"💾 [single] {row['Name']} | 🏷️ {row['Category'] or '-'} "
        f"| 💬 {row['Reviews_Count']} ulasan | 📞 {row['Phone_Number'] or '-'} "
        f"| 🌐 {row['Website_URL'] or '-'}"
    )
    return 1


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
    nav_state = {"failures": 0, "blocks": 0}  # state guard anti-blokir (lihat navigate_with_guard)
    last_progress_time = time.time()  # stuck detector: di-update tiap ada progress

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

                # --- Stuck detector: tidak ada progress > STUCK_THRESHOLD -> restart session ---
                if time.time() - last_progress_time > STUCK_THRESHOLD:
                    logger.warning(
                        f"[stuck] Tidak ada progress selama {(time.time() - last_progress_time)/60:.1f} menit "
                        "(kemungkinan throttling halus Google). Restart session browser..."
                    )
                    close_session_browser()
                    human_delay()
                    page = get_page_with_session()
                    last_progress_time = time.time()

                logger.info(f"\n🔎 Scraping query {idx}/{total_queries}: {query}...")
                page, nav_status = navigate_with_guard(page, query, nav_state)
                if nav_status == "stop":
                    break  # berhenti rapi: checkpoint & CSV sudah tersimpan, tinggal resume
                if nav_status == "retry":
                    last_progress_time = time.time()  # ada respons (walau gagal) -> reset stuck timer
                    continue
                last_progress_time = time.time()  # navigasi sukses -> reset stuck timer

                # --- Bonus capture: query niche -> Google redirect ke place page tunggal ---
                if nav_status == "place":
                    try:
                        total_written += scrape_single_place(page, query, writer, csv_file, seen_urls)
                        last_progress_time = time.time()  # reset stuck timer
                    except Exception as e:
                        logger.error(f"❌ Bonus capture gagal untuk '{query}': {e}. Lanjut ke query berikutnya.")
                    mark_query_completed(query)
                    completed_queries.add(query)
                    queries_done_this_run += 1
                    human_delay()
                    continue

                # --- Tahap A: scroll panel hasil & kumpulkan kartu tempat baru (reuse) ---
                new_cards = []
                geo_skipped = 0
                try:
                    for card in scroll_place_feed(page, max_results=max_per_query):
                        if card["url"] in seen_urls:
                            continue
                        seen_urls.add(card["url"])
                        # Geo-guard: buang kartu yang koordinatnya di luar Bandung Raya
                        if not is_in_bandung(card["url"]):
                            geo_skipped += 1
                            continue
                        new_cards.append(card)
                except Exception as e:
                    logger.error(f"❌ Scroll feed gagal untuk '{query}': {e}. Lanjut ke query berikutnya.")
                    human_delay()
                    continue

                logger.info(f"[{query}] -> {len(new_cards)} tempat baru (geo-skip: {geo_skipped}). Mulai ekstraksi kontak...")

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
                        last_progress_time = time.time()  # progress nyata -> reset stuck timer
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
