import re
import time
import urllib.parse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from loguru import logger


# Pusat Kota Bandung (sekitar Alun-alun) + zoom yang mencakup Bandung Raya.
# Dipakai untuk memaksa viewport pencarian ke Bandung meski IP pengguna berada
# di kota lain (mis. Jakarta) - mencegah Google fallback ke hasil sekitar IP.
BANDUNG_CENTER = (-6.9144, 107.6098)
BANDUNG_ZOOM = 13


def navigate_gmaps_search(page: Page, search_query: str, location_override: tuple | None = None) -> str:
    """
    Navigasi generik ke halaman hasil pencarian Google Maps untuk query bebas.
    Dipakai oleh pipeline UMKM FnB (misal: "warung makan Bandung").

    Args:
        search_query      : query teks pencarian.
        location_override : tuple (lat, lng) opsional. Jika diberikan, URL
                            menyertakan '/@lat,lng,<zoom>z' sehingga viewport
                            peta dipaksa berpusat di koordinat itu (anti-drift
                            lokasi IP). Jika None, perilaku lama (tanpa koordinat).

    Return string status:
      "place"   -> Google mengalihkan ke halaman detail tunggal (1 hasil); page
                   sudah berada di place page, caller langsung ekstrak dari situ.
      "results" -> halaman daftar hasil termuat normal (selector feed ditemukan).
    Raise: jika halaman blokir/CAPTCHA terdeteksi, atau timeout tanpa redirect.
    """
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://www.google.com/maps/search/{encoded_query}"
    if location_override is not None:
        lat, lng = location_override
        url += f"/@{lat},{lng},{BANDUNG_ZOOM}z"

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)  # 2 menit: toleran rate-limit Google
        page.wait_for_selector("a[href*='/maps/place/']", timeout=60_000)  # 1 menit: toleran rate-limit
        return "results"
    except PlaywrightTimeoutError as timeout_err:
        # Google mengalihkan query niche (1 hasil) langsung ke halaman detail
        # -> tidak ada daftar hasil -> selector feed timeout. Itu BUKAN error:
        # page sudah berada di place page yang valid dan siap diekstrak.
        current_url = page.url or ""
        if "/maps/place/" in current_url:
            logger.info("ℹ️ Redirect ke halaman detail tunggal (1 hasil): {}", current_url[:100])
            return "place"

        logger.error("Timeout menunggu elemen hasil. Mungkin tidak ada hasil atau struktur DOM berubah.")
        # Diagnosa throttle/consent wall: rekam URL, title, dan screenshot bukti
        try:
            from core.browser import save_screenshot  # lazy import: navigate.py tetap ringan diimpor
            logger.error(f"   URL saat gagal   : {current_url}")
            logger.error(f"   Title saat gagal : {page.title()}")
            save_screenshot(page, f"nav_timeout_{int(time.time())}")
        except Exception as diag_err:
            logger.debug(f"Gagal menyimpan diagnosa navigasi: {diag_err}")
        raise timeout_err


def navigate_gmaps(page: Page, area_query: str):
    """
    (Legacy) Navigasi pencarian coffeeshop untuk sebuah area — dipakai main.py.
    Didelegasikan ke navigate_gmaps_search() agar DRY. Perilaku tidak berubah.
    """
    navigate_gmaps_search(page, f"coffeeshop in {area_query}")


def extract_place_details_from_page(page: Page) -> dict | None:
    """
    Ekstrak Name, Category, Reviews_Count dari halaman detail Google Maps yang
    sedang terbuka. Dipakai untuk "bonus capture": query niche yang dialihkan
    Google langsung ke place page tunggal (bukan daftar hasil).

    Return: dict {name, category, reviews_count}, atau None jika gagal.
    Phone/Website sengaja TIDAK diekstrak di sini — caller memakai
    extract_place_contacts() yang sudah ada (DRY) untuk itu.

    Strategi reviews_count berlapis (selector Google Maps sering berubah):
      1. span[role='img'] aria-label berisi "4,5 bintang 2.998 ulasan" -> angka ke-2
         (pola yang sama dipakai parse_place_card — terbukti andal)
      2. elemen [aria-label*='ulasan'/'reviews'] (button/div/span) -> angka pertama
      3. regex "(2.998)" atau "2.998 ulasan" pada teks header halaman
    Parsing angka memakai parse_reviews_count (strip semua non-digit) agar konsisten
    dengan pipeline utama (mis. "2.998" -> 2998, "1,234" -> 1234).
    """
    # Import lokal agar navigate.py tetap ringan & hindari circular import
    # (modules.scrape_umkm mengimpor navigate.py).
    from modules.scrape_umkm import parse_reviews_count

    try:
        name = page.locator("h1").first.inner_text(timeout=5000).strip()
        if not name:
            return None

        # --- Kategori: tombol kategori utama (mis. "Restoran Bakso") ---
        category = ""
        try:
            cat_el = page.locator("button[jsaction*='category']").first
            if cat_el.count() > 0:
                category = (cat_el.inner_text(timeout=3000) or "").strip()
        except Exception:
            pass
        if not category:
            try:
                category = (page.locator("div.fontBodyMedium").first.inner_text(timeout=3000) or "").strip()
            except Exception:
                category = ""

        # --- Reviews_Count: strategi berlapis ---
        reviews_count = 0

        # Strategi 1: aria-label span[role='img'] -> "4,5 bintang 2.998 ulasan"
        try:
            rating_el = page.locator("span[role='img']").first
            if rating_el.count() > 0:
                raw_aria = rating_el.get_attribute("aria-label") or ""
                numbers = re.findall(r"[\d.,]+", raw_aria)
                # Angka TERAKHIR = jumlah ulasan (numbers[0] = rating bintang).
                # Aman untuk ID ("4,5 bintang 2.998 ulasan") & EN ("4.5 stars 1,234 reviews").
                if len(numbers) >= 2:
                    reviews_count = parse_reviews_count(numbers[-1])
        except Exception:
            pass

        # Strategi 2: elemen ber-aria-label "ulasan"/"reviews" (button/div/span)
        if reviews_count == 0:
            try:
                rev_el = page.locator(
                    "button[aria-label*='ulasan'], button[aria-label*='reviews'], "
                    "div[aria-label*='ulasan'], div[aria-label*='reviews'], "
                    "span[aria-label*='ulasan'], span[aria-label*='reviews']"
                ).first
                if rev_el.count() > 0:
                    rev_text = (rev_el.get_attribute("aria-label") or rev_el.inner_text(timeout=3000) or "")
                    reviews_count = parse_reviews_count(rev_text)
            except Exception:
                pass

        # Strategi 3: regex pada teks header — "(2.998)" atau "2.998 ulasan"
        if reviews_count == 0:
            try:
                header_text = page.locator("div[role='main']").first.inner_text(timeout=3000) or ""
                m = re.search(r"\(([\d.,]+)\)", header_text) or \
                    re.search(r"([\d.,]+)\s*(?:ulasan|reviews)", header_text, re.IGNORECASE)
                if m:
                    reviews_count = parse_reviews_count(m.group(1))
            except Exception:
                pass

        return {"name": name, "category": category, "reviews_count": reviews_count}
    except Exception as e:
        logger.warning(f"⚠️ Gagal ekstrak place page tunggal: {e}")
        return None


def is_blocked_page(page: Page) -> bool:
    """
    Deteksi halaman blokir/CAPTCHA Google (sorry page, reCAPTCHA, unusual traffic).
    Mengembalikan False untuk halaman normal maupun jika inspeksi gagal.
    """
    # Strategi 1: URL khas halaman blokir Google
    try:
        url = (page.url or "").lower()
        if any(token in url for token in ("/sorry/", "ipv4", "captcha", "consent.google")):
            return True
    except Exception:
        pass

    # Strategi 2: elemen reCAPTCHA pada DOM
    try:
        captcha_locator = page.locator("iframe[src*='recaptcha'], form#captcha-form, div#recaptcha")
        if captcha_locator.count() > 0:
            return True
    except Exception:
        pass

    # Strategi 3: teks indikator pada body (EN + ID)
    try:
        body_text = (page.locator("body").inner_text() or "").lower()
        indicators = (
            "unusual traffic", "lalu lintas yang tidak biasa",
            "bukan robot", "not a robot",
            "before you continue", "sebelum melanjutkan",  # consent wall Google
        )
        return any(k in body_text for k in indicators)
    except Exception:
        return False
