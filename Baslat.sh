#!/bin/bash
# ============================================================
#  ERP + Sanal Fabrika Simülasyonu — Linux çift tıkla başlatıcı
#  İlk seferde bir kez:  chmod +x Baslat.sh
# ============================================================
cd "$(dirname "$0")" || exit 1

echo "=================================================="
echo "  ERP + Sanal Fabrika Simülasyonu"
echo "=================================================="
echo ""

PY=""
command -v python3 >/dev/null 2>&1 && PY="python3"
[ -z "$PY" ] && { echo " HATA: python3 bulunamadı. Kur: sudo apt install python3 python3-venv"; read -r -p "Enter…"; exit 1; }

if [ ! -d .venv ]; then
  echo " İlk kurulum yapılıyor, bu 1-3 dakika sürebilir…"
  "$PY" -m venv .venv || { echo " HATA: sanal ortam kurulamadı (sudo apt install python3-venv)"; read -r; exit 1; }
  .venv/bin/python -m pip install --upgrade pip --quiet
  .venv/bin/python -m pip install --quiet -r requirements.txt || { echo " HATA: paketler kurulamadı"; read -r; exit 1; }
  echo " Kurulum tamam."
  echo ""
fi

echo " Sunucu başlatılıyor, tarayıcı birazdan açılacak…"
echo " Kapatmak için: bu pencereyi kapat veya Ctrl+C"
echo ""
exec .venv/bin/python -m erp_backend.launcher
