import os
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from loguru import logger
from config import settings


_playwright_instance = None
_browser: Browser = None
_session_playwright = None  # driver Playwright milik get_page_with_session()


def get_browser() -> Browser:
    """Launch dan return browser instance (singleton)."""
    global _playwright_instance, _browser

    if _browser is None:
        logger.info("Launching browser... (headless={})", settings.HEADLESS)
        _playwright_instance = sync_playwright().start()
        _browser = _playwright_instance.chromium.launch(
            headless=settings.HEADLESS,
            slow_mo=100,  # delay antar aksi (ms) agar lebih natural/human-like
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        logger.success("Browser launched successfully.")

    return _browser


def get_context() -> BrowserContext:
    """Buat browser context baru dengan profil human-like."""
    browser = get_browser()
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 720},
        locale="en-US",
        timezone_id="Asia/Jakarta",
    )
    return context


def get_page() -> Page:
    """Buat page baru dari context."""
    context = get_context()
    page = context.new_page()

    # Sembunyikan property webdriver agar tidak terdeteksi bot
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    return page
def get_page_with_session():
    """Membuat browser dengan session yang tersimpan di lokal."""
    global _session_playwright
    # Tentukan lokasi folder session (jangan lupa masukkan folder ini ke .gitignore)
    user_data_dir = os.path.join(os.getcwd(), "browser_session_gmaps")
    logger.info("Launching browser with user data dir: {}", user_data_dir)
    _session_playwright = sync_playwright().start()
    
    windows_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # 1. Launch Browser sekaligus Context
    context = _session_playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=settings.HEADLESS,
        user_agent=windows_user_agent,
        args=["--disable-blink-features=AutomationControlled"]
    )
    
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # 2. Ambil page yang otomatis terbuka atau buat baru
    if len(context.pages) > 0:
        page = context.pages[0]
    else:
        page = context.new_page()
        
    return page


def close_session_browser():
    """
    Tutup browser persistent-session (milik get_page_with_session) beserta driver
    Playwright-nya. Dipakai untuk restart browser di tengah run panjang
    (memory hygiene / pemulihan CAPTCHA). Aman dipanggil walau belum ada session.
    """
    global _session_playwright
    if _session_playwright is not None:
        try:
            _session_playwright.stop()  # menghentikan driver sekaligus menutup context & browser-nya
            logger.info("Session browser closed.")
        except Exception as e:
            logger.debug(f"Error saat menutup session browser: {e}")
        _session_playwright = None


def close_browser():
    """Tutup browser dan bersihkan resources."""
    global _playwright_instance, _browser

    if _browser:
        logger.info("Closing browser...")
        _browser.close()
        _browser = None

    if _playwright_instance:
        _playwright_instance.stop()
        _playwright_instance = None
        logger.info("Browser closed.")


def save_screenshot(page: Page, filename: str):
    """Simpan screenshot ke folder screenshots/ (berguna saat debug/error)."""
    import os
    os.makedirs("screenshots", exist_ok=True)
    path = f"screenshots/{filename}.png"
    page.screenshot(path=path, full_page=True)
    logger.debug("Screenshot saved: {}", path)
