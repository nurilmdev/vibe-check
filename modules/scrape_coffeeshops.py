from playwright.sync_api import Page
from loguru import logger
import re


def parse_place_card(container):
    """
    Ekstraksi data mentah dari satu kartu tempat (div[role='article'])
    pada feed hasil pencarian Google Maps.

    Return dict {name, rating, reviews, category, address, status, image_url, url}
    atau None jika kartu tidak memiliki link/nama yang valid.
    """
    link_locator = container.locator("a[href*='/maps/place/']")
    if link_locator.count() == 0:
        return None

    link = link_locator.first.get_attribute("href")
    if not link:
        return None

    name = link_locator.first.get_attribute("aria-label")
    if not name:
        return None

    # --- Ekstraksi Rating & Ulasan ---
    rating_score = "N/A"
    review_count = "N/A"
    rating_element = container.locator("span[role='img']")

    if rating_element.count() > 0:
        raw_aria = rating_element.first.get_attribute("aria-label") or ""
        numbers_from_aria = re.findall(r'[\d.,]+', raw_aria)
        if numbers_from_aria:
            rating_score = numbers_from_aria[0]
            if len(numbers_from_aria) >= 2:
                review_count = numbers_from_aria[1]
            else:
                full_card_text = container.text_content() or ""
                review_match = re.search(r'\(([\d.,]+)\)', full_card_text)
                if review_match:
                    review_count = review_match.group(1)

    # --- Ekstraksi Gambar ---
    image_url = ""
    img_locator = container.locator("img[src*='googleusercontent']")
    if img_locator.count() > 0:
        image_url = img_locator.first.get_attribute("src") or ""

    # --- Ekstraksi Info (Kategori, Alamat, Status) ---
    category = ""
    address = ""
    status = ""

    # Mengambil teks yang dirender visual secara utuh
    visible_text = container.inner_text()

    # Memecah teks berdasarkan enter/baris baru
    lines = visible_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Kita HANYA mencari baris yang mengandung titik pemisah "·"
        if '·' in line:
            # 1. Bypass baris Rating & Harga (misal: "4,6 · $" atau "· Rp 25 rb")
            # Jika ada simbol uang atau kata bintang, kita lewati
            if '$' in line or 'Rp' in line or 'bintang' in line.lower():
                continue

            # 2. Deteksi Baris Status Operasional
            # Biasanya mengandung kata kunci waktu/status operasional
            elif any(keyword in line.lower() for keyword in ["buka", "tutup", "pukul", "jam", "open", "close"]):
                status = line

            # 3. Jika bukan harga dan bukan status, ini PASTI baris Kategori & Alamat
            # Contoh: "Kafe · Jl. Kemang Timur No.63 7"
            else:
                parts = line.split('·')
                if len(parts) >= 2:
                    category = parts[0].strip()
                    # Menggabungkan kembali sisa array jika alamatnya secara tidak sengaja mengandung titik tengah
                    address = '·'.join(parts[1:]).strip()
                else:
                    address = line

    return {
        "name": name,
        "rating": rating_score,
        "reviews": review_count,
        "category": category,
        "address": address,
        "status": status,
        "image_url": image_url,
        "url": link,
    }


def scroll_place_feed(page: Page, feed_selector="div[role='feed']", max_results=None, max_attempts=5):
    """
    Generator inti virtual-scroll pada feed hasil pencarian Google Maps.

    Scroll berulang ke bawah hingga daftar habis (atau max_results tercapai),
    me-yield dict kartu tempat unik (dedup berdasarkan URL).

    Reusable scrolling primitive — dipakai oleh:
    - scrape_with_virtual_scroll()  -> pipeline coffeeshop (main.py)
    - modules/scrape_umkm.py        -> pipeline UMKM FnB Bandung (CSV-only)
    """
    seen_urls = set()

    try:
        page.wait_for_selector(feed_selector, timeout=15000)
    except Exception as e:
        print("Timeout/Gagal memuat halaman utama Maps:", e)
        return

    previous_height = 0
    scroll_attempts = 0
    total_yielded = 0

    while True:
        containers = page.locator("div[role='article']").all()

        for container in containers:
            card = parse_place_card(container)
            if card is None or card["url"] in seen_urls:
                continue

            seen_urls.add(card["url"])
            total_yielded += 1
            yield card

            if max_results is not None and total_yielded >= max_results:
                return

        # Injeksi JS untuk scroll down
        page.evaluate("selector => document.querySelector(selector).scrollBy(0, 1500)", feed_selector)

        # Jeda 2 detik agar Google merender data baru
        page.wait_for_timeout(2000)

        current_height = page.evaluate("selector => document.querySelector(selector).scrollHeight", feed_selector)

        if current_height == previous_height:
            scroll_attempts += 1
            if scroll_attempts >= max_attempts:
                if page.locator("text='You\\'ve reached the end'").is_visible() or page.locator("text='Anda telah mencapai akhir'").is_visible():
                    print("\n🏁 Penanda akhir daftar ditemukan.")
                else:
                    print(f"\n🛑 Mentok (DOM tidak bertambah panjang setelah {max_attempts} kali percobaan).")
                break
        else:
            scroll_attempts = 0
            previous_height = current_height


def scrape_with_virtual_scroll(page: Page, feed_selector="div[role='feed']", max_results=15):
    """
    (Legacy wrapper — dipakai main.py pipeline coffeeshop)

    Mempertahankan bentuk output lama: dict {name, rating, reviews, info, image_url, url}
    dengan 'info' = "kategori | alamat | status" serta batas default 15 tempat.
    Logika scrolling didelegasikan ke scroll_place_feed() agar DRY.
    """
    count = 0
    for card in scroll_place_feed(page, feed_selector, max_results=max_results):
        count += 1
        shop_data = {
            "name": card["name"],
            "rating": card["rating"],
            "reviews": card["reviews"],
            "info": card["category"] + " | " + card["address"] + " | " + card["status"],
            "image_url": card["image_url"],
            "url": card["url"]
        }
        print(f"✅ {card['name']} | ⭐ {card['rating']} ({card['reviews']})")
        yield shop_data

    logger.info(f"Jumlah coffeeshop unik yang ditemukan sejauh ini: {count}")
    if max_results is not None and count >= max_results:
        print(f"\n⚠️ Target {max_results} coffeeshop tercapai, menghentikan scroll.")
