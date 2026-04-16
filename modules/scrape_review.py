import os
import re
import time
import json
from loguru import logger
from playwright.sync_api import Page, sync_playwright

def scrape_single_place_reviews(page, place_url, target_review_count=50):
    # KITA UBAH MENJADI DICTIONARY UNTUK SMART UPDATE
    reviews_dict = {}
    
    print(f"Membuka halaman tempat: {place_url}")
    page.goto(place_url)
    page.wait_for_timeout(3000)

    # --- 1. CARI DAN KLIK TAB "ULASAN" ---
    try:
        tab_locator = page.locator("button[role='tab']", has_text=re.compile(r"Ulasan|Reviews", re.IGNORECASE))
        if tab_locator.count() > 0:
            print("Mengklik Tab Ulasan...")
            tab_locator.first.click()
            page.wait_for_timeout(2000)
        else:
            print("❌ Tab ulasan tidak ditemukan.")
            return []
    except Exception as e:
        print(f"Gagal berpindah ke tab ulasan: {e}")
        return []

    previous_height = 0
    scroll_attempts = 0
    max_attempts = 5

    print(f"🚀 Memulai ekstraksi hingga ~{target_review_count} ulasan...")

    while len(reviews_dict) < target_review_count:
        # --- 2. KLIK SEMUA TOMBOL "LAINNYA" ---
        try:
            more_buttons = page.locator("button[aria-expanded='false']", has_text=re.compile(r"Selengkapnya|Lainnya|More", re.IGNORECASE)).all()
            clicked_any = False
            for btn in more_buttons:
                try:
                    if btn.is_visible():
                        btn.click()
                        clicked_any = True
                except Exception:
                    continue
            if clicked_any:
                page.wait_for_timeout(1000) # Tunggu animasi mekar selesai
        except Exception:
            pass

        # --- 3. EKSTRAKSI BLOK ULASAN (SMART UPSERT) ---
        review_blocks = page.locator("div[data-review-id]").all()
        
        for block in review_blocks:
            review_id = block.get_attribute("data-review-id")
            if not review_id:
                continue
                
            # Kita targetkan container .MyEned agar menangkap seluruh teks dengan lebih solid
            review_text = ""
            text_locator = block.locator(".MyEned")
            if text_locator.count() > 0:
                review_text = text_locator.first.inner_text().strip()
                # Bersihkan kata "Lainnya" jika tidak sengaja ikut ter-copy
                review_text = re.sub(r'\n?Lainnya$|\n?More$', '', review_text).strip()
            
            # Ekstrak Rating, Nama, Waktu
            rating = "N/A"
            rating_locator = block.locator("span[role='img'][aria-label*='bintang'], span[role='img'][aria-label*='stars']")
            if rating_locator.count() > 0:
                match = re.search(r'([\d.,]+)', rating_locator.first.get_attribute("aria-label") or "")
                if match: rating = match.group(1)

            reviewer_name = "N/A"
            name_locator = block.locator("div.d4r55, button.al6Kxe")
            if name_locator.count() > 0: reviewer_name = name_locator.first.inner_text().strip()
            
            time_raw = "N/A"
            time_locator = block.locator("span.rsqaWe")
            if time_locator.count() > 0: time_raw = time_locator.first.inner_text().strip()

            if review_text:
                review_data = {
                    "review_id": review_id,
                    "reviewer": reviewer_name,
                    "rating": rating,
                    "time": time_raw,
                    "text": review_text
                }
                
                # --- LOGIKA SMART UPSERT (ANTI-RACE CONDITION) ---
                if review_id not in reviews_dict:
                    # Ulasan baru, langsung simpan
                    reviews_dict[review_id] = review_data
                    print(f"[{len(reviews_dict)}] ⭐ {rating} | {reviewer_name} | {review_text[:40]}...")
                else:
                    # Ulasan sudah ada! Cek apakah teks yang baru dibaca LEBIH PANJANG
                    old_text = reviews_dict[review_id]["text"]
                    if len(review_text) > len(old_text):
                        reviews_dict[review_id]["text"] = review_text
                        print(f"   🔄 UPDATE (Mekar): {reviewer_name} | {review_text[:40]}...")
                        
                if len(reviews_dict) >= target_review_count:
                    break

        if len(reviews_dict) >= target_review_count:
            break

        # --- 4. AUTO-SCROLL JANGKAR EMAS ---
        current_height = page.evaluate("""() => {
            const anchor = document.querySelector("div[aria-label*='Saring ulasan'], div[aria-label*='Sort reviews'], div[aria-label*='Filter reviews']");
            if (!anchor) return 0;
            const scrollPane = anchor.parentElement;
            scrollPane.scrollBy(0, 2000);
            return scrollPane.scrollHeight;
        }""")
        
        page.wait_for_timeout(3500) 
        
        if current_height == previous_height:
            scroll_attempts += 1
            if scroll_attempts >= max_attempts:
                print("\n🛑 Mentok di bawah.")
                break
        else:
            scroll_attempts = 0
            previous_height = current_height

    # Kembalikan tipe data menjadi List sebelum di-return
    return list(reviews_dict.values())


def main():
    # Contoh URL dari hasil scraper list sebelumnya (Ganti dengan URL yang valid dari JSON-mu)
    sample_url = "https://www.google.com/maps/place/Toko+Kopi+Tuku+-+Kemang/data=!4m7!3m6!1s0x2e69f1a7d65bd131:0xc85926cbf534e7c3!8m2!3d-6.2625904!4d106.8155551!16s%2Fg%2F11f01p3m_x!19sChIJMdFb1qfxaS4Rw-c09csmWcg?authuser=0&hl=id&rclk=1"
    
    user_data_dir = os.path.join(os.getcwd(), "browser_session_gmaps")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # Ambil maksimal 30 ulasan sebagai tes
        reviews_data = scrape_single_place_reviews(page, sample_url, target_review_count=30)
        
        output_file = "sample_reviews.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(reviews_data, f, ensure_ascii=False, indent=4)
            
        print(f"\n🎉 SELESAI! Mengekstrak {len(reviews_data)} ulasan.")
        
        context.close()

if __name__ == "__main__":
    main()