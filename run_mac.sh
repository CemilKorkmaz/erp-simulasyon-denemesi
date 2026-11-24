#!/usr/bin/env bash
set -euo pipefail
# Bu scripti reponun KÖKÜNDEN çalıştır: ./erp_simulation/run_mac.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "=============================================="
echo "  Alüminyum Fabrika Simülasyonu (Mac)"
echo "=============================================="
echo "Python paketleri yükleniyor…"
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -r requirements_simulation.txt

echo ""
echo "Sunucu başlatılıyor:"
echo "  ERP Arayüzü:  http://localhost:8000"
echo "  OPC UA:       opc.tcp://localhost:4840/freeopcua/server/"
echo ""
echo "Test senaryosu:"
echo "  1. Arayüzden sipariş oluştur (ürün, fırın, hedef °C, süre)."
echo "  2. 'Başlat' ile fırını çalıştır. Sıcaklık yükselir, bekletir,"
echo "     süre dolunca TAMAMLANDI olur."
echo "  3. Hedef 850 °C'yi aşarsa ALARM düşer, brülör kapanır."
echo ""

exec .venv/bin/python -m erp_simulation.main
