@echo off
title Nebula Enterprise Server
color 0B
echo =====================================================
echo   NEBULA ENTERPRISE - FastAPI Sunucusu Baslatiliyor
echo =====================================================
echo.

REM --- Sanal Ortam Kontrol ---
if not exist venv (
    echo [1/3] Sanal ortam olusturuluyor...
    python -m venv venv
    if errorlevel 1 (
        echo HATA: Python bulunamadi. Python 3.10+ yukleyin.
        pause
        exit /b 1
    )
)

REM --- Sanal Ortami Aktif Et ---
echo [2/3] Sanal ortam aktif ediliyor...
call venv\Scripts\activate.bat

REM --- Bagimliliklari Yukle ---
echo [3/3] Bagimlilıklar kontrol ediliyor / yukleniyor...
pip install -r requirements.txt --quiet

REM --- .env Kontrol ---
if not exist .env (
    echo.
    echo UYARI: .env dosyasi bulunamadi!
    echo       .env.example dosyasini kopyalayip .env olarak yeniden adlandirin
    echo       ve PostgreSQL bilgilerini doldurun.
    echo.
    copy .env.example .env
    echo .env.example dosyasi .env olarak kopyalandi. Lutfen duzenleyin.
    pause
)

REM --- Sunucuyu Baslat ---
echo.
echo =====================================================
echo   Sunucu: http://127.0.0.1:8000
echo   API Dokumanlar: http://127.0.0.1:8000/docs
echo =====================================================
echo.
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
