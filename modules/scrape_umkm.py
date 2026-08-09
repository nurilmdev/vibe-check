"""
UMKM FnB Bandung Scraper — Phase 1 (Extract)
============================================
Pipeline CSV-only (TANPA database PostgreSQL) untuk mengumpulkan leads
UMKM Food & Beverage di Bandung dari Google Maps.

Query pencarian yang diiterasi:
    - warung makan Bandung
    - kedai makanan Bandung
    - seblak Bandung
    - rumah makan Sunda Bandung

Untuk setiap kartu tempat, URL-nya dikunjungi via page.goto() (pola yang sudah
terpakai di modules/scrape_review.py — lebih robust dibanding klik kartu di feed
yang terus berganti saat virtual scroll) untuk mengekstrak:
    Name, Category, Reviews_Count, Phone_Number, Website_URL

Setiap record LANGSUNG disimpan (real-time, flush per baris) ke:
    raw_umkm_leads.csv

Prinsip DRY — modul ini TIDAK membuat ulang logika browser maupun scrolling:
    - core.browser               : get_page_with_session(), close_browser()
    - modules.navigate           : navigate_gmaps_search()
    - modules.scrape_coffeeshops : scroll_place_feed()

Jalankan dari root project:
    venv\\Scripts\\python -m modules.scrape_umkm                      # full run
    venv\\Scripts\\python -m modules.scrape_umkm --max-per-query 10   # tes cepat
"""

import argparse
import csv
import re

from loguru import logger
from playwright.sync_api import Page

from core.browser import get_page_with_session, close_browser
from core.logger import setup_logger
from modules.navigate import navigate_gmaps_search, PageCorruptedError, is_page_corruption_error
from modules.scrape_coffeeshops import scroll_place_feed

TARGET_QUERIES = [
    "warung makan Bandung",
    "kedai makanan Bandung",
    "seblak Bandung",
    "rumah makan Sunda Bandung",
]

RAW_OUTPUT_FILE = "raw_umkm_leads.csv"

CSV_FIELDNAMES = [
    "Name",
    "Category",
    "Reviews_Count",
    "Phone_Number",
    "Website_URL",
    "Google_Maps_URL",  # kolom provenance/audit (tidak dipakai filter Phase 2)
    "Source_Query",     # kolom provenance/audit (tidak dipakai filter Phase 2)
]


def parse_reviews_count(raw_value) -> int:
    """
    Normalisasi jumlah ulasan mentah ("1.234", "523", "N/A", "", None) menjadi integer.
    Default 0 sesuai spesifikasi.
    """
    if raw_value is None:
        return 0
    digits = re.sub(r"[^\d]", "", str(raw_value))
    return int(digits) if digits else 0


def normalize_phone_number(raw_phone: str) -> str:
    """
    Normalisasi nomor telepon: buang spasi, tanda kurung, titik, dan strip.
    Contoh: "+62 812-3456-7890" -> "+6281234567890" ; "(022) 750-1234" -> "0227501234"
    """
    if not raw_phone:
        return ""
    return re.sub(r"[\s().\-]", "", raw_phone.strip())


def extract_phone_number(page: Page) -> str:
    """Ekstraksi nomor telepon dari halaman detail tempat (ikon telepon / href tel:)."""
    # Strategi 1: anchor dengan href="tel:..."
    try:
        tel_locator = page.locator("a[href^='tel:']")
        if tel_locator.count() > 0:
            href = tel_locator.first.get_attribute("href") or ""
            number = normalize_phone_number(href.replace("tel:", ""))
            if number:
                return number
    except Exception as e:
        logger.debug(f"Strategi href tel: gagal: {e}")

    # Strategi 2: tombol dengan data-item-id="phone:tel:..." (format desktop Google Maps)
    try:
        phone_button = page.locator("button[data-item-id^='phone:']")
        if phone_button.count() > 0:
            item_id = phone_button.first.get_attribute("data-item-id") or ""
            match = re.search(r"tel:(\+?[\d\s().\-]+)", item_id)
            if match:
                number = normalize_phone_number(match.group(1))
                if number:
                    return number

            # Fallback: aria-label, misal "Telepon: 0812-3456-7890"
            aria_label = phone_button.first.get_attribute("aria-label") or ""
            match = re.search(r"(\+?\d[\d\s().\-]{5,}\d)", aria_label)
            if match:
                return normalize_phone_number(match.group(1))
    except Exception as e:
        logger.debug(f"Strategi tombol phone gagal: {e}")

    return ""


def extract_website_url(page: Page) -> str:
    """Ekstraksi URL website eksternal dari halaman detail tempat."""
    # Strategi 1: tombol website resmi Google Maps (data-item-id="authority")
    try:
        site_locator = page.locator("a[data-item-id='authority']")
        if site_locator.count() > 0:
            href = site_locator.first.get_attribute("href") or ""
            if href.startswith("http") and "google." not in href:
                return href
    except Exception as e:
        logger.debug(f"Strategi data-item-id authority gagal: {e}")

    # Strategi 2: anchor dengan aria-label mengandung kata website/situs
    try:
        site_locator = page.locator("a[aria-label*='website' i], a[aria-label*='situs' i]")
        for i in range(min(site_locator.count(), 5)):
            href = site_locator.nth(i).get_attribute("href") or ""
            if href.startswith("http") and "google." not in href:
                return href
    except Exception as e:
        logger.debug(f"Strategi aria-label website gagal: {e}")

    return ""


def extract_place_contacts(page: Page, place_url: str) -> dict:
    """
    Kunjungi halaman detail satu tempat, ambil Phone_Number & Website_URL.
    Kegagalan navigasi TIDAK melempar exception — kontak dikembalikan kosong
    agar record tetap tersimpan dan loop berlanjut ke tempat berikutnya.
    """
    contacts = {"Phone_Number": "", "Website_URL": ""}
    try:
        page.goto(place_url, wait_until="domcontentloaded", timeout=120_000)  # 2 menit: toleran rate-limit
        page.wait_for_timeout(2500)  # beri waktu panel detail merender info kontak
    except Exception as e:
        if is_page_corruption_error(e):
            logger.error(f"Objek page rusak saat buka detail: {e}")
            raise PageCorruptedError(str(e)) from e
        logger.warning(f"⚠️ Gagal membuka halaman detail ({place_url}): {e}")
        return contacts

    contacts["Phone_Number"] = extract_phone_number(page)
    contacts["Website_URL"] = extract_website_url(page)
    return contacts


def run_extraction(queries=None, output_file=RAW_OUTPUT_FILE, max_per_query=None):
    """Orkestrasi Phase 1: scroll feed per query -> ekstrak kontak -> simpan CSV real-time."""
    queries = queries or TARGET_QUERIES

    setup_logger()
    logger.info(f"🚀 Mulai ekstraksi leads UMKM FnB Bandung -> {output_file}")
    logger.info(f"Target query ({len(queries)}): {queries}")

    page = get_page_with_session()
    seen_urls = set()
    total_written = 0

    # File raw dibuat fresh per run; setiap baris di-flush seketika (real-time save)
    with open(output_file, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        csv_file.flush()

        try:
            for query in queries:
                logger.info(f"\n🔎 Memproses query: '{query}'")
                try:
                    navigate_gmaps_search(page, query)
                except Exception as e:
                    logger.error(f"❌ Navigasi gagal untuk query '{query}': {e}. Lanjut ke query berikutnya.")
                    continue

                # --- Tahap A: kumpulkan kartu tempat unik via virtual scroll (reuse) ---
                cards = []
                for card in scroll_place_feed(page, max_results=max_per_query):
                    if card["url"] in seen_urls:
                        continue
                    seen_urls.add(card["url"])
                    cards.append(card)
                logger.info(f"📋 '{query}' -> {len(cards)} tempat unik ditemukan. Mulai ekstraksi kontak...")

                # --- Tahap B: kunjungi tiap tempat, ekstrak kontak, simpan real-time ---
                for idx, card in enumerate(cards, start=1):
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
                        csv_file.flush()  # real-time save per record
                        total_written += 1
                        logger.info(
                            f"[{total_written}] 💾 {row['Name']} | 🏷️ {row['Category'] or '-'} "
                            f"| 💬 {row['Reviews_Count']} ulasan | 📞 {row['Phone_Number'] or '-'} "
                            f"| 🌐 {row['Website_URL'] or '-'}"
                        )
                    except Exception as e:
                        logger.error(f"❌ Gagal memproses '{card.get('name')}': {e}. Lanjut ke tempat berikutnya.")
                        continue

                    page.wait_for_timeout(1000)  # jeda sopan antar kunjungan detail
        finally:
            page.context.close()
            close_browser()

    logger.success(f"\n✅ Ekstraksi selesai. Total {total_written} leads mentah tersimpan di {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Scraper UMKM FnB Bandung — Phase 1 Extract (CSV-only, tanpa database)")
    parser.add_argument("--output", default=RAW_OUTPUT_FILE, help="File CSV output mentah (default: raw_umkm_leads.csv)")
    parser.add_argument("--max-per-query", type=int, default=None, help="Batas maksimal tempat per query (untuk tes cepat)")
    args = parser.parse_args()

    run_extraction(output_file=args.output, max_per_query=args.max_per_query)


if __name__ == "__main__":
    main()
