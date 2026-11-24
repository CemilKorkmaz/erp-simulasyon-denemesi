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
  echo  Bu program icin Python 3.10+ gerekiyor.
  echo  1^) https://www.python.org/downloads/ adresinden indir
  echo  2^) Kurulumda "Add Python to PATH" kutusunu ISARETLE
  echo  3^) Bu dosyaya tekrar cift tikla
  echo.
  echo  Alternatif: ERP_Simulasyon.exe varsa ona cift tikla ^(Python gerekmez^).
  echo.
  pause
  exit /b 1
)

REM ---- 2) Python 3.10+ kontrolu ----
if not "%PY%"=="" (
  %PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
  if errorlevel 1 (
    echo  HATA: Python surumu cok eski.
    %PY% -V
    echo  Gereken: Python 3.10 veya uzeri.
    echo.
    echo  1^) https://www.python.org/downloads/ adresinden Python 3.12 indir
    echo  2^) Kurulumda "Add Python to PATH" kutusunu ISARETLE
    echo  3^) Bu dosyaya tekrar cift tikla
    echo.
    pause
    exit /b 1
  )
)

REM ---- 3) Sanal ortam (eski Python ile kurulmussa yenile) ----
set VENV_OK=0
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
  if not errorlevel 1 set VENV_OK=1
)
if "%VENV_OK%"=="0" (
  if exist ".venv" (
    echo  Eski sanal ortam bulundu, yenisi kuruluyor...
    rmdir /s /q .venv
  )
)

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

REM ---- 4) Calistir (tarayiciyi kendisi acar) ----
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
