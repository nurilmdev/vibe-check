from datetime import datetime, date
import json
from sqlite3 import DatabaseError
from loguru import logger
from database.connection import get_db
from psycopg2.extras import execute_values

def upsert_shop_profile(shop_data: dict) -> str | None:
    """
    Digunakan oleh Worker A. 
    Hanya mengurus profil utama coffeeshop.
    Mengembalikan UUID dari shop tersebut.
    """
    try:
        with get_db() as cursor:
            upsert_shop_query = """
                INSERT INTO coffeeshops 
                    (name, address, rating, review_count, google_maps_url, image_url, last_scraped_at)
                VALUES 
                    (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (google_maps_url) 
                DO UPDATE SET 
                    rating = EXCLUDED.rating,
                    review_count = EXCLUDED.review_count,
                    last_scraped_at = CURRENT_TIMESTAMP
                RETURNING id;
            """
            cursor.execute(upsert_shop_query, (
                shop_data.get('name'),
                shop_data.get('info'), 
                float(shop_data['rating'].replace(',', '.')) if shop_data.get('rating') != "N/A" else None,
                int(shop_data['reviews'].replace('.', '')) if shop_data.get('reviews') not in ("N/A", None) else 0,
                shop_data.get('url'),
                shop_data.get('image_url')
            ))
            
            result = cursor.fetchone()
            shop_uuid = result['id']
            logger.info(f"   💾 Worker A: Profil '{shop_data.get('name')}' berhasil di-upsert (ID: {shop_uuid}).")
            return shop_uuid

    except Exception as e:
        logger.error(f"   ❌ Worker A Database Error pada '{shop_data.get('name')}': {e}")
        return None
    
def upsert_shop_reviews(shop_uuid, reviews_list):
    """
    Digunakan oleh Worker B.
    Hanya fokus memasukkan ribuan baris ulasan menggunakan UUID yang sudah ada.
    """
    if not reviews_list:
        logger.warning("   ⚠️ Worker B: Tidak ada ulasan untuk di-insert.")
        return

    try:
        with get_db() as cursor:
            reviews_to_insert = []
            for rev in reviews_list:
                reviews_to_insert.append((
                    shop_uuid,
                    rev.get('review_id'),
                    rev.get('reviewer'),
                    rev.get('text'),
                    int(rev['rating']) if rev.get('rating') != "N/A" else None,
                    rev.get('time')
                ))

            upsert_review_query = """
                INSERT INTO coffeeshop_reviews 
                    (coffeeshop_id, review_id, reviewer_name, review_text, reviewer_rating, review_time_raw)
                VALUES %s
                ON CONFLICT (review_id) DO NOTHING;
            """
            
            execute_values(cursor, upsert_review_query, reviews_to_insert)
            print(f"   💾 Worker B: Berhasil memproses {len(reviews_to_insert)} ulasan ke database.")

    except Exception as e:
        logger.error(f"   ❌ Worker B Database Error: {e}")
        
def get_list_url() -> list[dict]:
    """Mengambil daftar URL coffeeshop yang sudah tersimpan di database."""
    try:
        with get_db() as cursor:
            cursor.execute("SELECT id, google_maps_url, name FROM coffeeshops")
            urls = [{'id': row['id'], 'url': row['google_maps_url'], 'name': row['name']} for row in cursor.fetchall()]
            logger.info(f"   🔍 Database: Ditemukan {len(urls)} URL coffeeshop yang sudah tersimpan.")
            return urls
    except Exception as e:
        logger.error(f"   ❌ Database Error saat mengambil URL: {e}")
        return []

def get_reviews_for_shop(shop_id, is_analyzed=False) -> list[dict]:
    """Mengambil daftar ulasan untuk coffeeshop tertentu berdasarkan shop_id."""
    try:
        with get_db() as cursor:
            cursor.execute("SELECT review_id, review_text FROM coffeeshop_reviews WHERE coffeeshop_id = %s AND is_analyzed = %s", (shop_id, is_analyzed))
            reviews = [{
                'review_id': row['review_id'],
                'text': row['review_text'],
            } for row in cursor.fetchall()]
            logger.info(f"   🔍 Database: Ditemukan {len(reviews)} ulasan untuk shop_id {shop_id}.")
            return reviews
    except Exception as e:
        logger.error(f"   ❌ Database Error saat mengambil ulasan untuk shop_id {shop_id}: {e}")
        return []

def simpan_hasil_nlp_ke_database(nlp_result):
    """
    Fungsi untuk melakukan UPDATE pada ulasan yang sudah ada di database 
    dengan hasil analisis sentimen dari Gemini.
    """
    try:
        with get_db() as cursor:
            update_query = """
                UPDATE coffeeshop_reviews 
                SET 
                    ai_sentiment_score = %s,
                    ai_vibe_tags = %s,
                    ai_aspects = %s,
                    ai_summary = %s,
                    is_analyzed = TRUE
                WHERE review_id = %s;
            """
            
            # Kita menggunakan psycopg2 untuk memastikan tipe datanya cocok
            cursor.execute(update_query, (
                nlp_result.get('overall_sentiment'),
                nlp_result.get('vibe_tags', []), # Array di Python otomatis jadi Array di Postgres
                json.dumps(nlp_result.get('extracted_aspects')), # Convert dict ke JSON string untuk tipe data JSONB
                nlp_result.get('summary_reason'),
                nlp_result.get('review_id')
            ))
            
            print(f"✅ Berhasil mengupdate NLP untuk review_id: {nlp_result.get('review_id')[:10]}...")

    except Exception as e:
        print(f"❌ Database Error saat update NLP: {e}")
            
def update_coffeeshop_aggregation(shop_uuid):
    """
    Menghitung rata-rata sentimen dan tag paling populer dari tabel ulasan,
    lalu menyimpan hasilnya ke profil utama coffeeshops.
    """
    try:
        with get_db() as cursor:
            # Query menggunakan CTE (Common Table Expressions / klausa WITH)
            # agar lebih mudah dibaca dan dieksekusi secara efisien oleh PostgreSQL
            aggregation_query = """
                WITH 
                -- 1. Hitung rata-rata sentimen keseluruhan
                avg_stats AS (
                    SELECT 
                        coffeeshop_id, 
                        ROUND(AVG(ai_sentiment_score), 2) AS avg_score
                    FROM coffeeshop_reviews
                    WHERE coffeeshop_id = %s AND ai_sentiment_score IS NOT NULL
                    GROUP BY coffeeshop_id
                ),
                -- 2. Pecah Array Vibe Tags menjadi baris tunggal
                unnested_tags AS (
                    SELECT unnest(ai_vibe_tags) AS tag
                    FROM coffeeshop_reviews
                    WHERE coffeeshop_id = %s AND ai_vibe_tags IS NOT NULL
                ),
                -- 3. Hitung kemunculan tiap tag, urutkan, ambil 3 teratas
                top_tags AS (
                    SELECT tag, COUNT(*) AS tag_count
                    FROM unnested_tags
                    GROUP BY tag
                    ORDER BY tag_count DESC
                    LIMIT 3
                )
                
                -- 4. Eksekusi UPDATE ke tabel profil utama
                UPDATE coffeeshops c
                SET 
                    sentiment_analytics = (SELECT avg_score FROM avg_stats),
                    vibe_tags = (SELECT array_agg(tag) FROM top_tags) -- Gabungkan kembali jadi Array
                WHERE c.id = %s;
            """
            
            # Kita melempar shop_uuid 3 kali karena dibutuhkan di klausa WHERE pada CTE di atas
            cursor.execute(aggregation_query, (shop_uuid, shop_uuid, shop_uuid))
            
            print(f"🔄 Berhasil menghitung ulang (Aggregate) metrik untuk ID Kafe: {shop_uuid}")

    except Exception as e:
        print(f"❌ Error saat melakukan agregasi data kafe: {e}")
        
def get_top_cafes_by_vibe(vibe_tag, limit=10):
    """
    Mengambil daftar kafe terbaik berdasarkan tag vibe tertentu.
    Hasilnya diurutkan berdasarkan sentimen tertinggi.
    """
    try:
        with get_db() as cursor:
            query = """
                SELECT id, name, rating, sentiment_analytics, vibe_tags 
                FROM coffeeshops 
                WHERE array_to_string(vibe_tags, ', ') ILIKE %s
                ORDER BY sentiment_analytics DESC NULLS LAST
                LIMIT %s;
            """
            
            search_pattern = f"%{vibe_tag if vibe_tag else ''}%"
            
            cursor.execute(query, (search_pattern, limit))
            raw_sql = cursor.query.decode('utf-8')
            
            logger.debug(f"\n🔍 [DEBUG] Raw SQL dieksekusi:\n{raw_sql}\n")
            
            cafes = cursor.fetchall()
            logger.debug(f"📊 [DEBUG] Ditemukan {len(cafes)} baris data.")
            return cafes
    except Exception as e:
        logger.error(f"❌ Error saat mengambil kafe berdasarkan vibe: {e}")
        return []
    
def get_detail_cafe_by_id(cafe_id):
    """
    Mengambil detail lengkap sebuah kafe berdasarkan ID-nya.
    Detail ini mencakup semua informasi dasar + analitik sentimen + tag vibe.
    """
    try:
        with get_db() as cursor:
            query = """
                SELECT id, name, address, rating, review_count, google_maps_url, image_url, sentiment_analytics, vibe_tags 
                FROM coffeeshops 
                WHERE id = %s;
            """
            cursor.execute(query, (cafe_id,))
            cafe_detail = cursor.fetchone()
            return cafe_detail
    except Exception as e:
        logger.error(f"❌ Error saat mengambil detail kafe dengan ID {cafe_id}: {e}")
        return None
    
def fetch_reviews_by_cafe(
    cafe_uuid: str, 
    aspect: str = None, 
    sentiment_label: str = None, 
    limit: int = 10, 
    offset: int = 0
):
    """
    Mengambil ulasan spesifik. Mendukung filter dinamis JSONB.
    """
    with get_db() as cursor:
        # Query dasar
        query = """
            SELECT 
                review_id, 
                ai_sentiment_score, 
                ai_vibe_tags, 
                ai_aspects, 
                ai_summary
            FROM coffeeshop_reviews
            WHERE coffeeshop_id = %s
        """
        
        # Parameter dasar
        params = [cafe_uuid]
        
        # 🚨 THE MAGIC: Filter dinamis ke dalam objek JSONB
        if aspect and sentiment_label:
            # Operator ->> mengambil value dari key JSON sebagai teks
            query += " AND ai_aspects ->> %s = %s"
            params.extend([aspect, sentiment_label])
        elif sentiment_label:
            # Skenario 2: Filter Sentimen Keseluruhan (Misal: Pokoknya cari ulasan positif)
            # Kita mapping teks ke rentang angka (score)
            if sentiment_label == 'positif':
                query += " AND ai_sentiment_score >= 0.7"
            elif sentiment_label == 'netral':
                query += " AND ai_sentiment_score >= 0.4 AND ai_sentiment_score < 0.7"
            elif sentiment_label == 'negatif':
                query += " AND ai_sentiment_score < 0.4"
            
        # Tambahkan urutan dan paginasi (WAJIB untuk endpoint list)
        query += " ORDER BY ai_sentiment_score DESC NULLS LAST LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        # Debugging: Cetak Raw SQL yang terbentuk
        # print("🔮 SQL:", cursor.mogrify(query, tuple(params)).decode('utf-8'))
        
        cursor.execute(query, tuple(params))
        raw_sql = cursor.query.decode('utf-8')
        logger.debug(f"\n🔍 [DEBUG] Raw SQL dieksekusi:\n{raw_sql}\n")
        return cursor.fetchall()
