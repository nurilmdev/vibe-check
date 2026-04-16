from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
import os
import base64
from loguru import logger
from database.repository import get_detail_cafe_by_id, get_top_cafes_by_vibe, fetch_reviews_by_cafe  # Pastikan fungsi ini sudah Anda buat di repository.py

# Import fungsi database Anda (sesuaikan dengan nama file/fungsi asli Anda)
# from repository import get_latest_active_token 

app = FastAPI(title="Cafe Vibe API", description="API untuk mencari kafe berdasarkan Vibe dan Sentimen")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Saat produksi nanti, ganti dengan URL domain asli Frontend Anda
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- KEAMANAN SEDERHANA ---
# Klien (aplikasi Anda yang lain) harus mengirim header: X-API-KEY: rahasia_internal_123
API_KEY = os.getenv("INTERNAL_API_KEY", "rahasia_internal_123")  # Pastikan untuk mengganti dengan nilai yang lebih aman di produksi
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    raise HTTPException(
        status_code=403, 
        detail="Akses Ditolak: API Key tidak valid atau tidak ada."
    )

# --- RESPONSE SCHEMA ---
class TokenResponse(BaseModel):
    status: str
    success: str
    data: str

# --- ENDPOINT UTAMA ---
@app.get("/api/token/latest", response_model=TokenResponse, tags=["Token"])
async def get_token(api_key: str = Security(get_api_key)):
    """Mengambil token Atlassian terbaru yang masih aktif dari Database."""
    
    try:
        data = get_latest_active_token()
        
        if not data or not data.get("token_value"):
            raise HTTPException(status_code=404, detail="Token aktif tidak ditemukan di database.")
        logger.debug("Token aktif ditemukan: {}", data)    
        return {
            "tokenName": data["token_name"],
            "tokenValue": base64.urlsafe_b64encode(data["token_value"].encode('utf-8')),
            "status": "Active" if data["is_active"] else "Inactive"
        }
    except Exception as e:
        logger.error("Error saat mengambil token dari database: {}", e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
@app.get("/")
def read_root():
    return {"message": "Selamat datang di Cafe Vibe API!"}

@app.get("/api/cafes")
def get_top_cafes(vibe: str = None, limit: int = 10):
    """
    Mengambil daftar kafe terbaik. Bisa difilter berdasarkan vibe.
    """
    
    if vibe:
        cafes = get_top_cafes_by_vibe(vibe_tag=vibe, limit=limit)
        logger.info(f"🔍 Mencari kafe dengan vibe '{vibe}'... Ditemukan {len(cafes)} kafe.")
    else:
        cafes = get_top_cafes_by_vibe(vibe_tag=None, limit=limit)
        logger.info(f"🔍 Mengambil semua kafe terbaik... Ditemukan {len(cafes)} kafe.")

    # RealDictCursor sudah otomatis membuat datanya berbentuk dictionary!
    return {"status": "success", "data": cafes}

@app.get("/api/cafes/{shop_id}")
def get_cafe_detail(shop_id: str):
    """
    Mengambil detail lengkap sebuah kafe berdasarkan ID-nya.
    """
    cafe_detail = get_detail_cafe_by_id(shop_id)
    if not cafe_detail:
        raise HTTPException(status_code=404, detail="Kafe tidak ditemukan.")
    return {"status": "success", "data": cafe_detail}

@app.get("/api/cafes/{cafe_uuid}/reviews")
def get_cafe_reviews(
    cafe_uuid: str,
    aspect: Optional[str] = Query(None, description="Pilih: fasilitas_kerja, kopi_dan_makanan, suasana"),
    sentiment: Optional[str] = Query(None, description="Pilih: positif, negatif, netral"),
    limit: int = Query(10, ge=1, le=50, description="Maksimal ulasan per halaman (Max 50)"),
    skip: int = Query(0, ge=0, description="Jumlah data yang dilewati (untuk pagination)")
):
    """
    Mengambil daftar ulasan untuk satu kafe. 
    Fitur Canggih: Bisa mencari ulasan yang spesifik memuji/mengkritik aspek tertentu!
    """
    # Validasi logika ringan: Jika isi aspect, harus isi sentiment juga
    if (aspect and not sentiment):
        raise HTTPException(
            status_code=400, 
            detail="Jika menggunakan filter aspek, anda harus mengisi parameter 'sentiment'."
        )

    # Panggil fungsi dari layer repository
    try:
        reviews = fetch_reviews_by_cafe(
            cafe_uuid=cafe_uuid,
            aspect=aspect,
            sentiment_label=sentiment,
            limit=limit,
            offset=skip
        )
        
        # Jika kosong dan ini page pertama, mungkin kafenya tidak ada
        if not reviews and skip == 0:
            return {"status": "success", "message": "Belum ada ulasan untuk filter ini.", "data": []}
            
        return {
            "status": "success", 
            "metadata": {
                "returned_count": len(reviews),
                "limit": limit,
                "skip": skip
            },
            "data": reviews
        }
        
    except Exception as e:
        # Tangkap error database jika ada yang salah
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan pada server: {str(e)}")