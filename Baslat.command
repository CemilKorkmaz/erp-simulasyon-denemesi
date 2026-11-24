#!/bin/bash
# ============================================================
#  ERP + Sanal Fabrika Simülasyonu — macOS çift tıkla başlatıcı
#  İlk seferde bir kez:  chmod +x Baslat.command
#  Sonra bu dosyaya çift tıkla.
# ============================================================
cd "$(dirname "$0")" || exit 1

echo "=================================================="
echo "  ERP + Sanal Fabrika Simülasyonu"
echo "=================================================="
echo ""

PY=""
command -v python3 >/dev/null 2>&1 && PY="python3"
if [ -z "$PY" ]; then
  echo " HATA: python3 bulunamadı."
  echo ""
  echo " macOS'ta Python kurmak için terminalde şunu çalıştır:"
  echo "   xcode-select --install"
  echo " veya https://www.python.org/downloads/ adresinden indir."
  echo ""
  read -r -p " Kapatmak için Enter'a bas…"
  exit 1
fi

if [ ! -d .venv ]; then
  echo " İlk kurulum yapılıyor, bu 1-3 dakika sürebilir…"
  "$PY" -m venv .venv || { echo " HATA: sanal ortam kurulamadı"; read -r; exit 1; }
  .venv/bin/python -m pip install --upgrade pip --quiet
  .venv/bin/python -m pip install --quiet -r requirements.txt || {
    echo " HATA: paketler kurulamadı (internet bağlantısını kontrol et)"; read -r; exit 1; }
  echo " Kurulum tamam."
  echo ""
fi

echo " Sunucu başlatılıyor, tarayıcı birazdan açılacak…"
echo " Kapatmak için: bu pencereyi kapat veya Ctrl+C"
echo ""
exec .venv/bin/python -m erp_backend.launcher
