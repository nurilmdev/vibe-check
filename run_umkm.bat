@echo off
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

REM ============================================================
REM  UMKM FnB Bandung - Pipeline Runner (one-click)
REM  Auto-resume dari scrape_progress.txt - Ctrl+C aman
REM ============================================================

REM --- Cek instance ganda: profile browser bentrok jika 2x jalan ---
tasklist /FI "WINDOWTITLE eq UMKM-Scraper" 2>nul | find /I "cmd.exe" >nul
if %errorlevel%==0 (
    echo [PERINGATAN] Scraper sudah berjalan di window lain!
    echo Tutup dulu window tersebut sebelum menjalankan lagi.
    pause
    exit /b 1
)

if not exist venv\Scripts\python.exe (
    echo [ERROR] venv tidak ditemukan di folder ini.
    echo Setup dulu: python -m venv venv lalu pip install -r requirements.txt
    pause
    exit /b 1
)

title UMKM-Scraper

:MENU
echo.
echo ============================================================
echo   UMKM FnB Bandung - Pipeline Runner
echo   Auto-resume dari scrape_progress.txt - Ctrl+C aman
echo ============================================================
echo.
echo   PHASE 1 - SCRAPING:
echo   [1] Dengan batas tempat per query (pilih sendiri, default 15)
echo   [2] FULL DATA - tanpa batas (estimasi 4-8 hari!)
echo   [3] Smoke test - 2 query x 3 tempat
echo.
echo   PHASE 2 - FILTER:
echo   [4] Filter raw_umkm_leads.csv menjadi clean_umkm_bandung.csv
echo.
echo   [0] Batal
echo.
set /p choice=Pilihan: 

if "%choice%"=="1" goto MODE_CAP
if "%choice%"=="2" goto MODE_FULL
if "%choice%"=="3" goto MODE_TEST
if "%choice%"=="4" goto MODE_FILTER
if "%choice%"=="0" goto BATAL
echo Pilihan tidak dikenal: "%choice%"
goto MENU

:MODE_CAP
set /p MAXQ=Max tempat per query [default 15]: 
if "%MAXQ%"=="" set MAXQ=15
echo %MAXQ%| findstr /r "^[1-9][0-9]*$" >nul
if errorlevel 1 (
    echo [ERROR] Input harus angka bulat positif, bukan: "%MAXQ%"
    goto MENU
)
set "ARGS=--max-per-query %MAXQ%"
goto RUN_SCRAPE

:MODE_FULL
set "ARGS="
goto RUN_SCRAPE

:MODE_TEST
set "ARGS=--max-queries 2 --max-per-query 3"
goto RUN_SCRAPE

:RUN_SCRAPE
echo.
echo ------------------------------------------------------------
echo Menjalankan: python -m modules.scrape_umkm_multiplier %ARGS%
echo ------------------------------------------------------------
venv\Scripts\python.exe -m modules.scrape_umkm_multiplier %ARGS%
goto END

:MODE_FILTER
echo.
echo ------------------------------------------------------------
echo Menjalankan: python filter_umkm_leads.py
echo ------------------------------------------------------------
venv\Scripts\python.exe filter_umkm_leads.py
goto END

:END
echo.
echo ============================================================
echo   Selesai. Jalankan lagi file ini untuk resume/langkah lanjut.
echo ============================================================
pause
exit /b 0

:BATAL
exit /b 0
