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

# ---- Python 3.10+ gerekli ----
py_uygun() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; }

if ! py_uygun "$PY"; then
  for aday in python3.13 python3.12 python3.11 python3.10; do
    if command -v "$aday" >/dev/null 2>&1 && py_uygun "$aday"; then PY="$aday"; break; fi
  done
fi

if ! py_uygun "$PY"; then
  echo " HATA: Python 3.10 veya üzeri gerekiyor."
  echo "   Bilgisayarındaki: $("$PY" -V 2>&1)"
  echo ""
  echo " ÇÖZÜM (Ubuntu/Debian):"
  echo "   sudo apt update && sudo apt install python3.12 python3.12-venv"
  echo ""
  read -r -p " Kapatmak için Enter'a bas…"
  exit 1
fi

# ---- Sanal ortam (eski Python ile kurulmuşsa yenile) ----
venv_uygun() { [ -x .venv/bin/python ] && py_uygun .venv/bin/python; }
if [ -d .venv ] && ! venv_uygun; then
  echo " Eski sanal ortam bulundu, yenisini kuruyorum…"
  rm -rf .venv
fi

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
