"""
filter_umkm_leads.py — Phase 2 (Transform & Load)
=================================================
Membaca raw_umkm_leads.csv (hasil Phase 1: modules/scrape_umkm.py atau
modules/scrape_umkm_multiplier.py), membuang duplikat berdasarkan kolom Name,
menerapkan aturan heuristik ketat, lalu menyimpan leads yang lolos SEMUA
aturan ke clean_umkm_bandung.csv.

Tahapan: baca CSV mentah -> dedup by Name -> 4 aturan heuristik -> simpan.

Aturan (semua harus lolos):
1. Exclude Coffee   : Name & Category TIDAK boleh mengandung keyword kopi
                      (case-insensitive).
2. MSME Scale       : Reviews_Count >= 1 DAN <= 1000 (batas atas inklusif).
3. WhatsApp Target  : Phone_Number tidak kosong DAN diawali "08" / "+628".
4. Instagram Target : Website_URL tidak kosong DAN mengandung
                      "instagram.com" / "linktr.ee".

Murni stdlib csv — TANPA pandas, TANPA database.

Jalankan dari root project:
    venv\\Scripts\\python filter_umkm_leads.py
    venv\\Scripts\\python filter_umkm_leads.py --input raw_umkm_leads.csv --output clean_umkm_bandung.csv
"""

import argparse
import csv
import os
import re

from loguru import logger

COFFEE_KEYWORDS = ["kopi", "coffee", "cafe", "roastery", "kopitiam"]
WHATSAPP_PREFIXES = ("08", "+628")
INSTAGRAM_DOMAINS = ("instagram.com", "linktr.ee")

# Greater Bandung Raya bounding box (kota + Cimahi + Kab. Bandung/Barat).
# Baris dengan koordinat di luar box ini (mis. Jakarta) dibuang.
BANDUNG_LAT_RANGE = (-7.15, -6.75)
BANDUNG_LNG_RANGE = (107.35, 107.75)

DEFAULT_INPUT = "raw_umkm_leads.csv"
DEFAULT_OUTPUT = "clean_umkm_bandung.csv"


def parse_reviews_count(raw_value) -> int:
    """
    Konversi Reviews_Count mentah menjadi integer (default 0 jika tidak valid).
    Catatan: sengaja digandakan dari modules/scrape_umkm.py agar script ini
    tetap standalone (impor scrape_umkm akan menarik dependency browser/config).
    """
    try:
        return int(str(raw_value).strip())
    except (TypeError, ValueError):
        return 0


def is_coffee_related(name: str, category: str) -> bool:
    """True jika Name ATAU Category mengandung keyword kopi (case-insensitive)."""
    haystack = f"{name or ''} {category or ''}".lower()
    return any(keyword in haystack for keyword in COFFEE_KEYWORDS)


def is_msme_scale(reviews_count: int) -> bool:
    """True jika 1 <= Reviews_Count <= 1000 (skala UMKM, batas atas inklusif)."""
    return 1 <= reviews_count <= 1000


def deduplicate_by_name(rows: list) -> tuple:
    """
    Drop baris duplikat berdasarkan kolom Name (keep first occurrence).
    Return: (baris_unik, jumlah_duplikat_yang_dibuang)
    """
    seen_names = set()
    unique_rows = []
    for row in rows:
        name = (row.get("Name") or "").strip()
        if name in seen_names:
            continue
        seen_names.add(name)
        unique_rows.append(row)
    return unique_rows, len(rows) - len(unique_rows)


def is_whatsapp_target(phone_number: str) -> bool:
    """True jika nomor tidak kosong dan diawali '08' atau '+628'."""
    phone = (phone_number or "").strip()
    return bool(phone) and phone.startswith(WHATSAPP_PREFIXES)


def is_instagram_target(website_url: str) -> bool:
    """True jika URL tidak kosong dan mengandung instagram.com / linktr.ee."""
    url = (website_url or "").strip().lower()
    return bool(url) and any(domain in url for domain in INSTAGRAM_DOMAINS)


def extract_coords_from_url(url: str):
    """Ambil (lat, lng) dari pola '!3d<lat>!4d<lng>' pada Google_Maps_URL."""
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


def evaluate_row(row: dict) -> dict:
    """Evaluasi seluruh aturan untuk satu baris. Return dict hasil per aturan."""
    return {
        "exclude_coffee": not is_coffee_related(row.get("Name", ""), row.get("Category", "")),
        "msme_scale": is_msme_scale(parse_reviews_count(row.get("Reviews_Count"))),
        "whatsapp_target": is_whatsapp_target(row.get("Phone_Number", "")),
        "instagram_target": is_instagram_target(row.get("Website_URL", "")),
        "in_bandung": is_in_bandung(row.get("Google_Maps_URL", "")),
    }


def passes_all_rules(row: dict) -> bool:
    """True hanya jika baris lolos KEEMPAT aturan."""
    return all(evaluate_row(row).values())


def apply_heuristic_filters(rows: list) -> tuple:
    """
    Terapkan seluruh aturan ke daftar baris.
    Return: (baris_lolos, statistik_penolakan_per_aturan)
    """
    passed = []
    rejection_stats = {
        "coffee_related": 0,
        "not_msme_scale": 0,
        "no_whatsapp_number": 0,
        "no_instagram_website": 0,
        "outside_bandung": 0,
    }

    for row in rows:
        result = evaluate_row(row)
        if all(result.values()):
            passed.append(row)
            continue

        if not result["exclude_coffee"]:
            rejection_stats["coffee_related"] += 1
        if not result["msme_scale"]:
            rejection_stats["not_msme_scale"] += 1
        if not result["whatsapp_target"]:
            rejection_stats["no_whatsapp_number"] += 1
        if not result["instagram_target"]:
            rejection_stats["no_instagram_website"] += 1
        if not result["in_bandung"]:
            rejection_stats["outside_bandung"] += 1

    return passed, rejection_stats


def load_rows(input_file: str) -> tuple:
    """Baca CSV mentah. Return (list_of_rows, fieldnames)."""
    with open(input_file, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


def save_rows(output_file: str, fieldnames: list, rows: list):
    """Simpan baris yang lolos filter ke CSV bersih (skema kolom dipertahankan)."""
    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Filter heuristik leads UMKM FnB Bandung — Phase 2 (CSV-only)")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="CSV mentah dari Phase 1 (default: raw_umkm_leads.csv)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="CSV bersih hasil filter (default: clean_umkm_bandung.csv)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        logger.error(f"File input '{args.input}' tidak ditemukan. Jalankan dulu Phase 1: python -m modules.scrape_umkm")
        raise SystemExit(1)

    rows, fieldnames = load_rows(args.input)
    logger.info(f"📥 Membaca {len(rows)} baris dari {args.input}")

    rows, dropped = deduplicate_by_name(rows)
    if dropped:
        logger.info(f"🧹 Dedup by Name: {dropped} baris duplikat dibuang, sisa {len(rows)} baris.")

    passed, stats = apply_heuristic_filters(rows)

    save_rows(args.output, fieldnames, passed)

    logger.info("===== 📊 LAPORAN FILTER =====")
    logger.info(f"Total baris mentah           : {len(rows)}")
    logger.info(f"❌ Ditolak - terkait kopi    : {stats['coffee_related']}")
    logger.info(f"❌ Ditolak - skala review    : {stats['not_msme_scale']}")
    logger.info(f"❌ Ditolak - tanpa no. WA    : {stats['no_whatsapp_number']}")
    logger.info(f"❌ Ditolak - tanpa IG/linktree: {stats['no_instagram_website']}")
    logger.info(f"[X] Ditolak - di luar Bandung   : {stats['outside_bandung']}")
    logger.success(f"✅ Lolos SEMUA aturan        : {len(passed)} baris → {args.output}")


if __name__ == "__main__":
    main()
