#!/usr/bin/env bash
# ERP + Fabrika Simülasyonu - tek komutla başlatıcı
set -euo pipefail

cd "$(dirname "$0")"

echo "=================================================="
echo " ERP + Sanal Fabrika Simülasyonu"
echo "=================================================="
echo "Sanal ortam kontrol ediliyor / oluşturuluyor..."
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/pip install -q -r requirements.txt

echo ""
echo "Hizmetler başlatılıyor:"
echo "  - ERP arayüzü:     http://localhost:8000"
echo "  - OPC UA sunucusu: opc.tcp://localhost:4840/freeopcua/server/"
echo ""
echo "Test senaryosu:"
echo "  1. Arayüzden bir üretim siparişi oluşturun (ürün, fırın, hedef sıcaklık, süre)."
echo "  2. 'Baslat' ile fırını çalıştırın. Sıcaklık hedefe yükselir, bekletir,"
echo "     sure dolunca emir TAMAMLANDI olarak kaydedilir."
echo "  3. Sıcaklık 850 °C'yi aşarsa ALARM düşer ve brülör kapanır."
echo ""

exec .venv/bin/python -m erp_backend.main
