"""
backfill_reviews.py

Script untuk mengisi kolom total_reviews_gmaps pada tabel coffeeshops
dengan cara scraping jumlah total ulasan dari halaman Google Maps masing-masing.
"""

import re
import time
from playwright.sync_api import sync_playwright
from database.connection import get_db


DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def fetch_coffeeshops_to_backfill():
    """Ambil semua coffeeshop yang belum punya data total_reviews_gmaps."""
    with get_db() as db:
        db.execute("""
            SELECT id, name, google_maps_url
            FROM coffeeshops
            WHERE total_reviews_gmaps IS NULL
              AND google_maps_url IS NOT NULL
        """)
        rows = db.fetchall()
    return rows


def parse_review_count(raw_text: str) -> int:
    """
    Parse teks mentah menjadi integer jumlah ulasan.
    Contoh input: "(4.205 ulasan)", "4,205 reviews", "(1.234)", "523"
    """
    # Hapus semua karakter non-digit kecuali titik dan koma
    # Pertama, ambil angka-angka yang ada
    numbers = re.findall(r'[\d.,]+', raw_text)
    if not numbers:
        return 0

    # Ambil angka pertama yang ditemukan
    num_str = numbers[0]

    # Hapus separator ribuan (titik atau koma tergantung locale)
    # Jika formatnya "4.205" (titik sebagai separator ribuan, umum di ID)
    # atau "4,205" (koma sebagai separator ribuan, umum di EN)
    cleaned = num_str.replace('.', '').replace(',', '')

    try:
        return int(cleaned)
    except ValueError:
        return 0


def extract_total_reviews(page, url: str) -> int:
    """
    Navigasi ke URL Google Maps dan ekstrak jumlah total ulasan.
    Return integer > 0 jika berhasil, 0 jika gagal.
    """
    page.goto(url, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # Strategi 1: Cari tombol/link yang mengandung teks "ulasan" atau "reviews"
    # Biasanya ada elemen seperti: <button>4.205 ulasan</button> atau <span>(4,205)</span>
    review_locator = page.locator(
        "button[jsaction*='review'], "
        "button[aria-label*='ulasan'], "
        "button[aria-label*='reviews'], "
        "span[aria-label*='ulasan'], "
        "span[aria-label*='reviews']"
    )

    if review_locator.count() > 0:
        for i in range(review_locator.count()):
            element = review_locator.nth(i)
            # Cek aria-label dulu
            aria = element.get_attribute("aria-label") or ""
            if aria and re.search(r'\d', aria):
                count = parse_review_count(aria)
                if count > 0:
                    return count
            # Cek inner text
            text = element.inner_text() or ""
            if text and re.search(r'\d', text):
                count = parse_review_count(text)
                if count > 0:
                    return count

    # Strategi 2: Cari elemen dengan teks yang cocok pola "X ulasan" atau "(X)"
    review_text_locator = page.locator(
        ":is(button, span, a):has-text('ulasan'), "
        ":is(button, span, a):has-text('reviews'), "
        ":is(button, span, a):has-text('review')"
    )

    if review_text_locator.count() > 0:
        for i in range(min(review_text_locator.count(), 10)):
            try:
                text = review_text_locator.nth(i).inner_text() or ""
                if re.search(r'\d', text):
                    count = parse_review_count(text)
                    if count > 0:
                        return count
            except Exception:
                continue

    # Strategi 3: Cari pola angka dalam kurung dekat rating, misal "(4.205)"
    paren_locator = page.locator("span")
    all_spans = paren_locator.all()
    for span in all_spans[:50]:  # Batasi pencarian agar tidak terlalu lama
        try:
            text = span.inner_text() or ""
            match = re.match(r'^\(?([\d.,]+)\)?$', text.strip())
            if match:
                count = parse_review_count(match.group(1))
                if count > 0:
                    return count
        except Exception:
            continue

    return 0


def update_total_reviews(coffeeshop_id: int, total_reviews: int):
    """Update kolom total_reviews_gmaps berdasarkan ID."""
    with get_db() as db:
        db.execute(
            "UPDATE coffeeshops SET total_reviews_gmaps = %s WHERE id = %s",
            (total_reviews, coffeeshop_id)
        )


def main():
    print("=" * 60)
    print("  BACKFILL: total_reviews_gmaps dari Google Maps")
    print("=" * 60)

    # 1. Fetch data target
    shops = fetch_coffeeshops_to_backfill()
    if not shops:
        print("\n✅ Tidak ada coffeeshop yang perlu di-backfill.")
        return

    print(f"\n📋 Ditemukan {len(shops)} coffeeshop yang perlu di-backfill.\n")

    # 2. Launch Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DESKTOP_USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="id-ID"
        )
        page = context.new_page()

        success_count = 0
        fail_count = 0

        # 3. Loop scraping
        for idx, shop in enumerate(shops, start=1):
            shop_id = shop["id"]
            shop_name = shop["name"]
            google_maps_url = shop["google_maps_url"]

            print(f"[{idx}/{len(shops)}] Navigating to: {shop_name}")

            try:
                total_reviews = extract_total_reviews(page, google_maps_url)

                if total_reviews > 0:
                    update_total_reviews(shop_id, total_reviews)
                    print(f"   ✅ Successfully updated: {total_reviews} reviews")
                    success_count += 1
                else:
                    print(f"   ⚠️ Failed to find review count element")
                    fail_count += 1

            except Exception as e:
                print(f"   ❌ Error: {e}")
                fail_count += 1

            # Rate limiting
            time.sleep(3)

        # Cleanup
        context.close()
        browser.close()

    # Summary
    print("\n" + "=" * 60)
    print(f"  SELESAI | Berhasil: {success_count} | Gagal: {fail_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
