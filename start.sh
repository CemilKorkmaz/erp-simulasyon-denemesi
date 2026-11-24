#!/usr/bin/env bash
# ERP + Fabrika Simülasyonu - tek komutla başlatıcı
#
# Kullanım:
#   ./start.sh              # gerçek zamanlı (1x) — sıcaklık gerçekçi hızda yükselir
#   ./start.sh 10           # 10 kat hızlı — demo/test için ÖNERİLEN
#   SIM_SPEED=25 ./start.sh # çok hızlı
#
set -euo pipefail

cd "$(dirname "$0")"

SIM_SPEED="${1:-${SIM_SPEED:-1}}"
export SIM_SPEED

echo "=================================================="
echo " ERP + Sanal Fabrika Simülasyonu"
echo "=================================================="
echo "Sanal ortam kontrol ediliyor / oluşturuluyor..."
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/pip install -q -r requirements.txt

echo ""
echo "Hizmetler başlatılıyor:"
echo "  - ERP arayüzü :  http://localhost:8000   <-- TARAYICIDA BUNU AÇ"
echo "  - OPC UA      :  opc.tcp://localhost:4840/freeopcua/server/"
echo "  - Simülasyon hızı: ${SIM_SPEED}x"
echo ""
if [ "$SIM_SPEED" = "1" ]; then
  echo "  NOT: 1x hızda bir fırının 750 °C'ye çıkması ~10 dakika, alarm testi"
  echo "       ~30 dakika sürer. Hızlı denemek için:  ./start.sh 10"
  echo ""
fi
echo "İlk 60 saniyede yapman gerekenler:"
echo "  1. Tarayıcıda http://localhost:8000 aç."
echo "  2. Üstteki nokta YEŞİL olmalı ('Canlı veri akışı aktif')."
echo "     Gri/turuncu ise sayfa yenilenmez; panoya yine veri gelir."
echo "  3. Ürün adı yaz, hedef sıcaklık + süre gir, fırın seç, 'Sipariş Oluştur'."
echo "  4. Tablodaki 'Başlat' ile fırını çalıştır."
echo "  5. Hızlı sonuç için düşük hedef (ör. 50 °C) + kısa süre (0.1 dk) kullan."
echo ""
echo "Detaylı rehber: BAGLANTI_REHBERI.md"
echo "Durdurmak için: Ctrl+C"
echo "=================================================="
echo ""

exec .venv/bin/python -m erp_backend.main
