import json
from google import genai
from google.genai import types
import time
from loguru import logger
from config import settings  

# 1. Inisialisasi Client
# Ganti dengan API Key milikmu

client = genai.Client(api_key=settings.API_KEY_GEMINI)

def extract_vibe_with_gemini(reviews_list):
    # 2. System Instruction (Persona & Rules)
    # Di SDK baru, instruksi sistem dipisah agar AI lebih fokus mematuhinya
    system_prompt = """
    Anda adalah "Cafe Vibe Data Extractor", sebuah sistem AI ahli yang dirancang untuk membedah ulasan kedai kopi di Indonesia.
    
    ATURAN KLASIFIKASI VIBE:
    1. "WFH / Produktif": wifi kencang, banyak colokan, sepi, nyaman untuk nugas/laptopan.
    2. "Skena / Nongkrong": asik buat ngobrol, smoking area luas, musik, ramai, cocok bareng teman, kalcer, area smoking banyak, barista humble.
    3. "Aesthetic": spot foto, instagramable, desain interior bagus, unik.
    4. "Family Friendly": luas, cocok untuk keluarga, ramah anak, tidak ramai, tidak banyak asap rokok.
    5. "Hidden Gem": masuk gang, sulit dicari, tapi tempat/kopinya bagus.
    6. "Kopi Enak": kopinya enak, rekomen buat yang suka ngopi, creamy, strong, bold, arabica, robusta.
    7. "Pet friendly": boleh bawa hewan peliharaan, ada fasilitas untuk hewan, ramah hewan, ada kucing/anjing lucu.
    
    FORMAT OUTPUT WAJIB:
    Anda harus mengembalikan sebuah ARRAY dari JSON Objects. 
    Setiap objek HARUS memiliki "review_id" yang sama persis dengan input.
    
    [
      {
        "review_id": "string",
        "overall_sentiment": float (0.0 - 1.0),
        "vibe_tags": ["tag1", "tag2"],
        "extracted_aspects": {
          "kopi_dan_makanan": "positif/negatif/netral/tidak_disebutkan",
          "fasilitas_kerja": "positif/negatif/netral/tidak_disebutkan",
          "suasana": "positif/negatif/netral/tidak_disebutkan"
        },
        "summary_reason": "alasan maksimal 15 kata"
      }
    ]
    """
    
    # 2. Membangun String Input (Menggabungkan Ulasan dengan ID-nya)
    combined_text = "Berikut adalah daftar ulasan yang harus dianalisis:\n\n"
    for rev in reviews_list:
        combined_text += f"--- START ULASAN ---\n"
        combined_text += f"Review ID: {rev['review_id']}\n"
        combined_text += f"Teks: {rev['text']}\n"
        combined_text += f"--- END ULASAN ---\n\n"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 3. Panggil API
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                # model='gemini-3.1-flash',
                contents=combined_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            
            # 4. Parse output (Sekarang hasilnya adalah sebuah List Python)
            data_array = json.loads(response.text)
            return data_array
            
        except Exception as e:
            error_msg = str(e)
            
            # --- PENANGANAN KHUSUS ERROR 429 (RATE LIMIT) ---
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                print("⚠️ [Peringatan 429] Kuota menit ini habis! Mesin istirahat selama 65 detik...")
                # Tidur 65 detik untuk memastikan menit benar-benar berganti
                time.sleep(65)
                
                # ganti token
                # client = genai.Client(api_key=generate 
                
            # --- PENANGANAN ERROR 503 (SERVER GOOGLE SIBUK) ---
            elif "503" in error_msg:
                wait_time = 2 ** (attempt + 1)
                print(f"⚠️ Server sibuk (503). Menunggu {wait_time} detik...")
                time.sleep(wait_time)
                
            else:
                print(f"❌ Error fatal API: {e}")
                return None
    logger.warning("🛑 Gagal memanggil API setelah batas maksimal percobaan. Batch ini dilewati.")
    

# --- CARA TESTNYA ---
if __name__ == "__main__":
    test_review = "Tempatnya nyempil banget di belakang ruko, tapi pas masuk gila estetik parah ala jepang gitu. Kopinya enak, colokan banyak buat buka laptop, sayangnya agak berisik kalo sore soalnya banyak bocil."

    logger.info("Mengirim ulasan ke Gemini...")
    # hasil = extract_vibe_with_gemini(test_review)
    hasil =  client.models.list()
    
    if hasil:
        logger.success("\n✅ Hasil Ekstraksi:")
        import pprint
        pprint.pprint(hasil)