import urllib.parse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from loguru import logger

def navigate_gmaps(page: Page, area_query: str):
    encoded_query = urllib.parse.quote(f"coffeeshop in {area_query}")
    url = f"https://www.google.com/maps/search/{encoded_query}"
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_selector("a[href*='/maps/place/']", timeout=15000)
    except PlaywrightTimeoutError:
        logger.error("Timeout menunggu elemen hasil. Mungkin tidak ada hasil atau struktur DOM berubah.")
        raise
    