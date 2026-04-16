"""
Atlassian Admin Automation
==========================
Entry point utama. Jalankan dengan:

    python main.py                  → jalankan semua job sekali (mode: run-once)
    python main.py --scrape         → hanya scraping
    python main.py --renew-token    → hanya renewal token
    python main.py --schedule       → jalankan scheduler terus-menerus
"""

import json
import random
import re
import time

from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from core.browser import get_page, close_browser, get_page_with_session
from core.args_parser import parse_args
from core.logger import setup_logger
from database.repository import get_list_url, get_reviews_for_shop, simpan_hasil_nlp_ke_database, upsert_shop_profile, upsert_shop_reviews, update_coffeeshop_aggregation
from modules.analysis_sentiment import extract_vibe_with_gemini
from modules.navigate import navigate_gmaps
import urllib.parse

from modules.scrape_review import scrape_single_place_reviews

from modules.scrape_coffeeshops import scrape_with_virtual_scroll

def merge_data():
    input_file = "coffeeshops_kemang_jakarta_selatan.json"
    output_file = "coffeeshops_kemang_FULL.json"
    
    # 1. BACA DATA LIST MUKA
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            shops = json.load(f)
    except Exception as e:
        print(f"Gagal membaca {input_file}: {e}")
        return

    print(f"Membaca {len(shops)} coffeeshop dari database lokal...")
    
    page = get_page_with_session()
    # 2. LOOPING KESELURUH COFFEESHOP
    try:
        for index, shop in enumerate(shops):
            print(f"\n[{index + 1}/{len(shops)}] Memproses: {shop.get('name')}")
            
            url = shop.get("url")
            if not url:
                print("❌ URL tidak ditemukan, melewati...")
                continue
                
            # Kita batasi target 40 ulasan per cafe agar tidak terlalu lama saat testing
            # Nanti bisa kamu naikkan jadi 100 atau 200
            reviews = scrape_single_place_reviews(page, url, target_review_count=15)
            
            # Masukkan data ulasan ke dalam dictionary utama
            shop["reviews_data"] = reviews

            # 3. PROGRESSIVE SAVING (Simpan ke file setiap kali 1 cafe selesai)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(shops, f, ensure_ascii=False, indent=4)
                
            # Jeda untuk bernapas agar tidak dicurigai Google sebagai serangan DDoS
            page.wait_for_timeout(2000)

        print(f"\n🎉 INTEGRASI SELESAI! Semua data telah tersimpan di {output_file}")
    finally:
        page.context.close()
        close_browser()
def main():
    setup_logger()
    area_query = "Kemang Jakarta Selatan"
    args = parse_args()
    page = get_page_with_session() if (args.scrape_places or args.scrape_reviews) else None

    try:
        if args.scrape_places:
            logger.info(f"Memulai proses scraping coffeeshop di area: {area_query}")
            navigate_gmaps(page, area_query)
            count = 0
            for shop_dict in scrape_with_virtual_scroll(page):
                count += 1
                shop_uuid = upsert_shop_profile(shop_dict)
                
                if shop_uuid:
                    logger.success(f"[{count}] 💾 Tersimpan: '{shop_dict.get('name')}' (UUID: {shop_uuid})")
                else:
                    logger.error(f"[{count}] ❌ Gagal simpan: '{shop_dict.get('name')}'.")
                    
            logger.success(f"\n✅ Proses selesai. Total data diamankan: {count}")
            
        elif args.scrape_reviews:
            coffeeshops = get_list_url()
            counter = 0
            for shop in coffeeshops:
                shop_id = shop['id']
                url = shop['url']
                name = shop['name']
                
                logger.info(f"Mengekstrak ulasan untuk: {name}")
                
                try:
                    # 3. Jalankan bot Playwright ke URL spesifik
                    reviews = scrape_single_place_reviews(page, url, target_review_count=10)
                    
                    # 4. Upsert hasilnya ke database
                    if reviews:
                        upsert_shop_reviews(shop_id, reviews)
                    counter += 1    
                except Exception as e:
                    logger.error(f"Gagal memproses {name}: {e}")
                    continue
            logger.info(f"Proses selesai. Total coffeeshop yang berhasil disimpan: {counter} dari {len(coffeeshops)} coffeeshop.")
        elif args.analyze_sentiment:
            logger.info("Memulai proses analisis sentimen ulasan...")
            
            # Ambil daftar coffeeshop id dari database
            coffeeshops = get_list_url()
            coffeeshop_ids = [shop['id'] for shop in coffeeshops]
            for shop_id in coffeeshop_ids:
                logger.info(f"Memproses analisis untuk shop_id: {shop_id}")
                # Ambil ulasan dari database (Pastikan Anda hanya mengambil yang is_analyzed = FALSE)
                reviews_list = get_reviews_for_shop(shop_id, is_analyzed=False)

                batch_size = 5
                
                for i in range(0, len(reviews_list), batch_size):
                    # 1. Potong data menjadi 5 ulasan
                    batch_review = reviews_list[i : i+batch_size]
                    
                    # 2. Kirim ke Gemini (Hasilnya adalah LIST berisi maksimal 5 dict)
                    # (Pastikan fungsi yang dipanggil adalah fungsi batch yang sudah kita buat)
                    start_time = time.time() # Catat waktu mulai untuk pacing
                    batch_hasil = extract_vibe_with_gemini(batch_review) 
                    
                    if batch_hasil:
                        # 3. BONGKAR LIST-nya, lalu langsung simpan ke Database (Progressive Saving)
                        for dict_hasil in batch_hasil:
                            simpan_hasil_nlp_ke_database(dict_hasil)
                            
                        logger.info(f"✅ Batch {i//batch_size + 1} berhasil dianalisis & disimpan ke DB.")
                    else:
                        logger.error(f"❌ Batch {i//batch_size + 1} gagal dianalisis.")
                        
                    # 4. Proactive Pacing: Jeda 4.2 detik agar tidak kena Rate Limit 429
                    elapsed_time = time.time() - start_time
                    safe_interval = 6.0  # Jaminan mutlak maksimal hanya 10 request per menit

                    if elapsed_time < safe_interval:
                        waktu_tunggu = safe_interval - elapsed_time
                        time.sleep(waktu_tunggu) 
                update_coffeeshop_aggregation(shop_id) # Tandai coffeeshop ini sudah selesai dianalisis setelah semua batch selesai
                
            logger.info("🎉 Seluruh ulasan untuk coffeeshop ini telah selesai dianalisis!")
                
            

        
    finally:
        if page:
            page.context.close()
            close_browser()
        

if __name__ == "__main__":
    main()
    
    
