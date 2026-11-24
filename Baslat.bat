@echo off
REM ============================================================
REM  ERP + Sanal Fabrika Simulasyonu - cift tikla baslatici
REM  Terminale komut yazmana gerek yok. Bu dosyaya cift tikla.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

title ERP Simulasyonu

echo ==================================================
echo   ERP + Sanal Fabrika Simulasyonu
echo ==================================================
echo.

REM ---- 1) Python var mi? ----
set PY=
where py >nul 2>&1 && set PY=py -3
if "%PY%"=="" ( where python >nul 2>&1 && set PY=python )

if "%PY%"=="" (
  echo  HATA: Python bulunamadi.
  echo.
  echo  Bu program icin Python 3.9+ gerekiyor.
  echo  1^) https://www.python.org/downloads/ adresinden indir
  echo  2^) Kurulumda "Add Python to PATH" kutusunu ISARETLE
  echo  3^) Bu dosyaya tekrar cift tikla
  echo.
  echo  Alternatif: ERP_Simulasyon.exe varsa ona cift tikla ^(Python gerekmez^).
  echo.
  pause
  exit /b 1
)

REM ---- 2) Sanal ortam ----
if not exist ".venv\Scripts\python.exe" (
  echo  Ilk kurulum yapiliyor, bu 1-3 dakika surebilir...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo  HATA: Sanal ortam olusturulamadi.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo  HATA: Paketler kurulamadi. Internet baglantisini kontrol et.
    pause
    exit /b 1
  )
  echo  Kurulum tamam.
  echo.
)

REM ---- 3) Calistir (tarayiciyi kendisi acar) ----
echo  Sunucu baslatiliyor, tarayici birazdan acilacak...
echo  Kapatmak icin: bu pencereyi kapat veya Ctrl+C
echo.
".venv\Scripts\python.exe" -m erp_backend.launcher

if errorlevel 1 (
  echo.
  echo  Program beklenmedik sekilde kapandi.
  pause
)
endlocal
