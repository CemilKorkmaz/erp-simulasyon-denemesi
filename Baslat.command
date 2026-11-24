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

# ---- Python sürümü: 3.10+ gerekli ----------------------------------------
# Sistem python3'ü eski olabilir (macOS'ta genelde 3.9). Yeni bir sürüm
# kurulmuşsa onu bulmaya çalış; bulamazsak anlaşılır mesaj ver.
py_uygun() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null
}

# Sırayla adayları dene: python3.13 → 3.12 → 3.11 → 3.10 → python3
if ! py_uygun "$PY"; then
  for aday in python3.13 python3.12 python3.11 python3.10 \
              /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$aday" >/dev/null 2>&1 && py_uygun "$aday"; then
      PY="$aday"
      break
    fi
  done
fi

if ! py_uygun "$PY"; then
  echo " HATA: Python 3.10 veya üzeri gerekiyor."
  echo "   Bilgisayarındaki: $("$PY" -V 2>&1)"
  echo ""
  echo " ÇÖZÜM:"
  echo "   1. https://www.python.org/downloads/ adresinden Python 3.12 indir"
  echo "   2. Kur, sonra bu dosyaya tekrar çift tıkla"
  echo ""
  echo " (Homebrew varsa:  brew install python@3.12 )"
  echo ""
  read -r -p " Kapatmak için Enter'a bas…"
  exit 1
fi

# ---- Sanal ortam -----------------------------------------------------------
# .venv eski bir Python ile kurulmuşsa silip yeniden kuruyoruz; aksi hâlde
# Python'u güncellesen bile eski yorumlayıcı kullanılmaya devam eder.
venv_uygun() {
  [ -x .venv/bin/python ] && py_uygun .venv/bin/python
}

if [ -d .venv ] && ! venv_uygun; then
  echo " Eski sanal ortam (Python 3.9) bulundu, yenisini kuruyorum…"
  rm -rf .venv
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
