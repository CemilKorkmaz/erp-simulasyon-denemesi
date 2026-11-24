"""ERP + Fabrika Simülasyonu — tek dosyalık, çift tıklanabilir başlatıcı.

AMAÇ
----
Terminal açmadan, komut yazmadan uygulamayı çalıştırmak:

    Windows : ERP_Simulasyon.exe  (çift tıkla)
    macOS   : ERP_Simulasyon.command (çift tıkla)
    Linux   : ./ERP_Simulasyon  veya ./Baslat.sh

YAPTIĞI İŞ
----------
1. 8000 portu boş mu diye bakar; doluysa (uygulama zaten açık) tarayıcıyı
   açar ve kendini kapatır — "address already in use" hatası görmezsin.
2. Simülasyonu + OPC UA sunucusunu + arayüzü başlatır.
3. Birkaç saniye içinde varsayılan tarayıcıda http://localhost:8000 açar.
4. Pencereyi KAPATINCA sunucu da kapanır (temiz kapanış, Ctrl+C gerekmez).

Veritabanı (erp_sim.db) her zaman EXE'nin/DOSYANIN YANINDA oluşur — geçici
klasörde değil. Böylece programı kapatıp açsan da verilerin durur.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

# ------------------------------------------------------------------ yol ayarları


def _base_dir() -> str:
    """Veritabanı ve dosyaların yazılacağı klasör.

    PyInstaller --onefile ile çalışırken sys.executable EXE'nin yoludur;
    dosyaları oraya (yanına) yazarız ki kalıcı olsun. _MEIPASS ise içeriğe
    açılan GEÇİCİ klasördür — oraya yazılan dosya program kapanınca silinir.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # Geliştirme modu: bu dosya erp_backend/ içinde, proje kökü bir üst dizin.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bundle_dir() -> str:
    """Salt-okunur paket içeriğinin (frontend/) bulunduğu klasör."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    # Geliştirme modu: proje kökü (içinde frontend/ klasörü var).
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = _base_dir()
BUNDLE_DIR = _bundle_dir()

# Çalışma dizinini kendi klasörümüze çek: "frontend/..." ve "erp_sim.db"
# göreli yolları doğru yere düşsün.
os.chdir(BASE_DIR)

# Paketlenmiş uygulamada frontend klasörü _MEIPASS içindedir; erp_backend
# oradan okur. Geliştirme modunda ise repo kökünden çalışır.
if BUNDLE_DIR != BASE_DIR:
    os.environ.setdefault("ERP_FRONTEND_DIR", os.path.join(BUNDLE_DIR, "frontend"))

PORT = 8000
URL = f"http://localhost:{PORT}"


# ------------------------------------------------------------------ yardımcılar


def port_dolu(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def bekle_ve_ac(url: str, port: int, sure: float = 40.0) -> None:
    """Sunucu portu dinlemeye başlayınca tarayıcıyı açar."""
    baslangic = time.time()
    while time.time() - baslangic < sure:
        if port_dolu(port):
            try:
                webbrowser.open(url)
            except Exception:
                pass
            return
        time.sleep(0.3)


def bilgi(mesaj: str) -> None:
    print(mesaj, flush=True)


# ------------------------------------------------------------------ ana akış


def main() -> int:
    bilgi("=" * 52)
    bilgi("  ERP + Sanal Fabrika Simülasyonu")
    bilgi("=" * 52)
    bilgi(f"  Klasör : {BASE_DIR}")
    bilgi(f"  Arayüz : {URL}")
    bilgi(f"  OPC UA : opc.tcp://localhost:4840/freeopcua/server/")
    bilgi("")

    if port_dolu(PORT):
        bilgi("  Bu uygulama zaten çalışıyor gibi görünüyor.")
        bilgi("  Tarayıcı açılıyor…")
        try:
            webbrowser.open(URL)
        except Exception:
            pass
        bilgi("")
        bilgi("  Yeni bir kopya başlatmak istersen önce açık olanı kapat.")
        time.sleep(3)
        return 0

    bilgi("  Simülasyon başlatılıyor, tarayıcı birkaç saniye içinde açılacak…")
    bilgi("  (Pencereyi kapatınca sunucu durur. Ctrl+C de yeter.)")
    bilgi("")

    threading.Thread(
        target=bekle_ve_ac, args=(URL, PORT), daemon=True
    ).start()

    # Simülasyon çekirdeği (FastAPI + OPC UA) — ana thread'de çalışır ki
    # pencere kapanınca / Ctrl+C gelince birlikte dursun.
    from erp_backend.main import run

    try:
        run(port=PORT)
    except KeyboardInterrupt:
        bilgi("\n  Durduruldu.")
    except Exception as exc:  # pragma: no cover - kullanıcıya anlamlı mesaj
        bilgi("")
        bilgi("  HATA: Uygulama başlatılamadı.")
        bilgi(f"  Ayrıntı: {type(exc).__name__}: {exc}")
        bilgi("")
        bilgi("  8000 portu başka bir program tarafından kullanılıyor olabilir.")
        bilgi("  Çözüm: açık olan diğer programı kapat veya bilgisayarı yeniden")
        bilgi("  başlat, sonra bu dosyayı tekrar çift tıkla.")
        if sys.stdin and sys.stdin.isatty():
            try:
                input("\n  Kapatmak için Enter'a bas…")
            except Exception:
                pass
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
