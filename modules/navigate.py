import urllib.parse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from loguru import logger


def navigate_gmaps_search(page: Page, search_query: str):
    """
    Navigasi generik ke halaman hasil pencarian Google Maps untuk query bebas.
    Dipakai oleh pipeline UMKM FnB (misal: "warung makan Bandung").
    """
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://www.google.com/maps/search/{encoded_query}"

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_selector("a[href*='/maps/place/']", timeout=15000)
    except PlaywrightTimeoutError:
        logger.error("Timeout menunggu elemen hasil. Mungkin tidak ada hasil atau struktur DOM berubah.")
        raise


def navigate_gmaps(page: Page, area_query: str):
    """
    (Legacy) Navigasi pencarian coffeeshop untuk sebuah area — dipakai main.py.
    Didelegasikan ke navigate_gmaps_search() agar DRY. Perilaku tidak berubah.
    """
    navigate_gmaps_search(page, f"coffeeshop in {area_query}")


def is_blocked_page(page: Page) -> bool:
    """
    Deteksi halaman blokir/CAPTCHA Google (sorry page, reCAPTCHA, unusual traffic).
    Mengembalikan False untuk halaman normal maupun jika inspeksi gagal.
    """
    # Strategi 1: URL khas halaman blokir Google
    try:
        url = (page.url or "").lower()
        if any(token in url for token in ("/sorry/", "ipv4", "captcha")):
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
        indicators = ("unusual traffic", "lalu lintas yang tidak biasa", "bukan robot", "not a robot")
        return any(k in body_text for k in indicators)
    except Exception:
        return False
