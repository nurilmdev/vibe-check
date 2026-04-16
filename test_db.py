from database.connection import get_db
from loguru import logger
from database.repository import  get_list_url, get_reviews_for_shop

# Import fungsi upsert yang sudah kita buat
# Asumsi kamu menyimpan fungsi tersebut di file bernama db_handler.py
# from db_handler import upsert_to_database

# (Jika kamu menyatukannya dalam satu file, abaikan import di atas)

def test_upsert():
    print("Mempersiapkan data dummy...")
    
    # Membuat Data Dummy yang menyerupai hasil scraping
    dummy_shop_data = {
        "name": "Kedai Kopi Dummy Kemang",
        "info": "Kafe · Jl. Kemang Raya No.99, Jakarta Selatan",
        "rating": "5.0",
        "reviews": "1024",
        "url": "http://googleusercontent.com/maps.google.com/dummy_kemang_01",
        "image_url": "http://googleusercontent.com/profile/picture/dummy_cafe.jpg",
        "reviews_data": [
            {
                "review_id": "REV_DUMMY_001",
                "reviewer": "Nuril Developer",
                "rating": "5",
                "time": "1 minggu lalu",
                "text": "Tempatnya sangat nyaman buat WFH, wifi kenceng, colokan banyak. Kopinya juga enak banget!"
            },
            {
                "review_id": "REV_DUMMY_002",
                "reviewer": "Tester Bot",
                "rating": "4",
                "time": "3 bulan lalu",
                "text": "Vibesnya enak buat nongkrong sama teman. Sayang parkirannya agak sempit kalau bawa mobil."
            },
            {
                # Simulasi user yang tidak memberikan rating (N/A)
                "review_id": "REV_DUMMY_003",
                "reviewer": "Anonymous User",
                "rating": "N/A", 
                "time": "setahun lalu",
                "text": "Lumayan lah buat mampir sebentar beli es kopi susu."
            },
            {
                # Simulasi user yang tidak memberikan rating (N/A)
                "review_id": "REV_DUMMY_004",
                "reviewer": "Anonymous User 1",
                "rating": "N/A", 
                "time": "setahun lalu",
                "text": "Lumayan lah buat mampir sebentar beli es kopi susu."
            }
        ]
    }

    print("Mengeksekusi upsert ke PostgreSQL...")
    
    # Memanggil fungsi upsert yang sudah kita buat
    # shop_uuid = upsert_shop_profile(dummy_shop_data)
    # if shop_uuid:
    #     upsert_shop_reviews(shop_uuid, dummy_shop_data["reviews_data"])
    # else:
    #     print("❌ Gagal menyimpan data profil kedai kopi. Ulasan tidak akan disimpan.")
    
    # print("\n✅ Test eksekusi selesai. Silakan periksa database Anda.")
    
    reviews = get_reviews_for_shop("e9854745-1a1b-4824-8ff1-23fb2d45c757")
    logger.info(f"Ulasan untuk shop_id 'e9854745-1a1b-4824-8ff1-23fb2d45c757': {reviews}")

if __name__ == "__main__":
    test_upsert()
    
# try:
#     with get_db() as db:
#         db.execute("SELECT version()")
#         result = db.fetchone()
#         logger.success("DB connected! Version: {}", result["version"])
#     logger.info("Daftar URL coffeeshop:")
#     for shop in get_list_url():
#         logger.info(" - {}: {} ({})", shop['name'], shop['url'], shop['id'])
#     # upsert_token_expiry("API_TOKEN_2026", "token value", "Mar 26, 2027", "Mar 26, 2027")
#     # logger.debug(get_token("API_TOKEN_2026"))
#     # mark_token_renewed("API_TOKEN_2026")
# except Exception as e:
#     logger.error("DB connection failed: {}", e)