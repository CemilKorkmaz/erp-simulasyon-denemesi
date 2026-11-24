@echo off
cd /d "%~dp0"

echo ==============================================
echo   Alüminyum Fabrika Simülasyonu (Windows)
echo ==============================================
echo.
echo Python paketleri yükleniyor…
python -m venv .venv 2>nul || true
.venv\Scripts\pip install -q -r requirements_simulation.txt

echo.
echo Sunucu başlatılıyor:
echo   ERP Arayüzü:  http://localhost:8000
echo   OPC UA:       opc.tcp://localhost:4840/freeopcua/server/
echo.
echo Test senaryosu:
echo   1. Arayüzden sipariş oluştur.
echo   2. 'Başlat' ile fırını çalıştır.
echo   3. 850 °C üzeri alarm testi yapabilirsin.
echo.

.venv\Scripts\python -m erp_simulation.main
