import json
from google import genai
from google.genai import types
import time
from loguru import logger
from config import settings  


# ============================================================
#  GeminiKeyManager — Rotasi API Key secara dinamis
# ============================================================
class GeminiKeyManager:
    """
    Mengelola daftar API key Gemini dan merotasinya secara otomatis
    ketika salah satu key terkena rate limit (error 429).
    
    Urutan prioritas key:
      1. API_KEY_GEMINI_MAIN  (dari .env)
      2. API_KEY_GEMINI_ALT   (dari .env)
      3. API_KEY_GEMINI       (fallback legacy, dari .env)
    """

    def __init__(self):
        # Kumpulkan semua key yang tersedia, buang yang None/kosong
        raw_keys = [
            settings.API_KEY_GEMINI_MAIN,
            settings.API_KEY_GEMINI_ALT,
            settings.API_KEY_GEMINI,  # fallback jika MAIN/ALT tidak di-set
        ]
        self._keys = list(dict.fromkeys(k for k in raw_keys if k))  # deduplikasi & hapus None

        if not self._keys:
            raise EnvironmentError(
                "[GeminiKeyManager] Tidak ada API key yang ditemukan! "
                "Pastikan API_KEY_GEMINI_MAIN atau API_KEY_GEMINI_ALT sudah diisi di .env"
            )

        self._index = 0
        self._client = self._build_client()
        logger.info(f"[GeminiKeyManager] {len(self._keys)} API key tersedia. Menggunakan key ke-1.")

    # ----------------------------------------------------------
    #  Internal helpers
    # ----------------------------------------------------------
    def _build_client(self) -> genai.Client:
        return genai.Client(api_key=self._keys[self._index])

    # ----------------------------------------------------------
    #  Public API
    # ----------------------------------------------------------
    @property
    def client(self) -> genai.Client:
        """Kembalikan client Gemini aktif saat ini."""
        return self._client

    @property
    def current_key_label(self) -> str:
        """Label informatif untuk logging (index berbasis 1)."""
        return f"key-{self._index + 1}/{len(self._keys)}"

    def rotate(self) -> bool:
        """
        Putar ke key berikutnya.
        Return True  → berhasil pindah ke key baru.
        Return False → sudah mencoba semua key (balik ke key pertama).
        """
        next_index = (self._index + 1) % len(self._keys)
        rotated = next_index != 0  # False berarti sudah muter penuh satu putaran

        self._index = next_index
        self._client = self._build_client()

        if rotated:
            logger.warning(
                f"🔄 [GeminiKeyManager] Key dirotasi → sekarang menggunakan {self.current_key_label}"
            )
        else:
            logger.warning(
                f"🔄 [GeminiKeyManager] Semua key sudah dicoba. Kembali ke {self.current_key_label}"
            )

        return rotated


# Singleton — satu instance dipakai bersama di seluruh modul
_key_manager = GeminiKeyManager()


# ============================================================
#  Fungsi utama analisis sentimen
# ============================================================
def extract_vibe_with_gemini(reviews_list):
    # 1. System Instruction (Persona & Rules)
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
    all_keys_exhausted_wait = False  # Flag: apakah kita sudah pernah menunggu 65 detik di putaran ini?

    for attempt in range(max_retries):
        try:
            logger.debug(
                f"[Gemini] Attempt {attempt + 1}/{max_retries} menggunakan {_key_manager.current_key_label}"
            )

            # 3. Panggil API menggunakan client aktif dari key manager
            response = _key_manager.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=combined_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )

            # 4. Parse output
            data_array = json.loads(response.text)
            return data_array

        except Exception as e:
            error_msg = str(e)

            # --- PENANGANAN KHUSUS ERROR 429 (RATE LIMIT) ---
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                logger.warning(
                    f"⚠️ [429] Rate limit pada {_key_manager.current_key_label}. "
                    f"Mencoba rotasi key..."
                )

                # Coba rotasi ke key berikutnya
                rotated = _key_manager.rotate()

                if rotated:
                    # Ada key baru → langsung retry tanpa delay panjang
                    logger.info(
                        f"✅ Key dirotasi ke {_key_manager.current_key_label}. Langsung retry..."
                    )
                    # Jeda singkat agar tidak spam terlalu cepat
                    time.sleep(2)
                else:
                    # Semua key sudah habis / sudah satu putaran penuh
                    if not all_keys_exhausted_wait:
                        logger.warning(
                            "🛑 Semua API key terkena rate limit! "
                            "Menunggu 65 detik agar kuota per-menit reset..."
                        )
                        time.sleep(65)
                        all_keys_exhausted_wait = True
                        logger.info(
                            f"⏰ Selesai menunggu. Melanjutkan dengan {_key_manager.current_key_label}..."
                        )
                    else:
                        # Sudah tunggu 65 detik tapi masih 429 → skip batch ini
                        logger.error(
                            "❌ Masih rate limit setelah menunggu 65 detik. Batch ini dilewati."
                        )
                        return None

            # --- PENANGANAN ERROR 503 (SERVER GOOGLE SIBUK) ---
            elif "503" in error_msg:
                wait_time = 2 ** (attempt + 1)
                logger.warning(f"⚠️ Server sibuk (503). Menunggu {wait_time} detik...")
                time.sleep(wait_time)

            else:
                logger.error(f"❌ Error fatal API: {e}")
                return None

    logger.warning("🛑 Gagal memanggil API setelah batas maksimal percobaan. Batch ini dilewati.")
    return None


# ============================================================
#  Test / Debug
# ============================================================
if __name__ == "__main__":
    test_review = "Tempatnya nyempil banget di belakang ruko, tapi pas masuk gila estetik parah ala jepang gitu. Kopinya enak, colokan banyak buat buka laptop, sayangnya agak berisik kalo sore soalnya banyak bocil."

    logger.info("Mengirim ulasan ke Gemini...")
    hasil = _key_manager.client.models.list()

    if hasil:
        logger.success("\n✅ Hasil:")
        import pprint
        pprint.pprint(hasil)
