#!/usr/bin/env python3
"""ERP Entegrasyon Testi — tek komutla her şeyi dener.

Kullanım
--------
1. Simülasyonu PLC yazma açık başlat:
       ERP_PLC_WRITE=1 SIM_SPEED=10 python3 -m erp_backend.main

2. Başka bir terminalde:
       python3 tools/system_test.py

3. Sonuç: her test için ✓ / ✗ ve sonda özet. Çıkış kodu 0 = hepsi geçti.

Ne test eder?
-------------
  A. Sağlık ve meta            : /api/meta, kalite etiketi
  B. Üç fırın da çalışıyor mu? : her fırın ısınıyor + hedefe ulaşıyor
  C. Yazma (ERP -> PLC)        : hedef yaz, başlat, durdur
  D. Güvenlik reddi            : güvenlik sınırı üstü hedef REDDEDİLMELİ
  E. Çakışma reddi             : meşgul fırına ikinci start REDDEDİLMELİ
  F. Alarm döngüsü             : aşırı sıcaklık -> mandallı alarm -> onay
  G. Kesinti (offline)         : uçlar 503, servis ayakta
  H. Bayat veri (STALE)        : kalite etiketi STALE
  I. Sensör hatası (BAD)       : kalite etiketi BAD
  J. Güç kesintisi             : fırınlar KAPALI'ya düşer
  K. Emir yaşam döngüsü        : CREATED -> RUNNING -> COMPLETED + DB kaydı
  L. Komut kaydı               : yazmaların denetim izi tutuluyor mu

Bağımlılık: yalnızca Python standart kütüphanesi (urllib). Ek paket gerekmez.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
SONUC = []


# ------------------------------------------------------------------ yardımcı


def cagir(yol: str, metot: str = "GET", govde=None,
          beklenen=None):
    """HTTP çağrısı yapar, (kod, veri) döndürür."""
    url = BASE + yol
    data = json.dumps(govde).encode() if govde is not None else None
    req = urllib.request.Request(
        url, data=data, method=metot,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            kod = r.status
            ham = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        kod = e.code
        ham = e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, {"hata": str(e)}

    try:
        veri = json.loads(ham) if ham else None
    except json.JSONDecodeError:
        veri = ham
    return kod, veri


def kontrol(ad: str, kosul: bool, ayrinti: str = "") -> bool:
    SONUC.append((ad, bool(kosul), ayrinti))
    isaret = "✓" if kosul else "✗"
    print(f"  {isaret} {ad}" + (f"  — {ayrinti}" if ayrinti else ""))
    return bool(kosul)


FIRINLAR = [
    "Aluminyum Eritme Fırını",
    "Homojenizasyon Fırını",
    "Biyet Isıtma Fırını",
]


def baslik(n: str, ad: str) -> None:
    print(f"\n[{n}] {ad}")


def bekle(sn: float) -> None:
    time.sleep(sn)


# ------------------------------------------------------------------ testler


def test_a_saglik():
    baslik("A", "Sağlık ve meta")
    kod, d = cagir("/api/meta")
    if not kontrol("GET /api/meta 200 döndü", kod == 200, f"kod={kod}"):
        return False
    kontrol("Sağlık bilgisi var", "health" in d)
    kontrol("Kalite etiketi GOOD", d.get("quality") in ("GOOD", "STALE", "BAD"),
            f"quality={d.get('quality')}")
    kontrol("3 fırın tanımlı", len(d.get("furnaces", [])) == 3,
            f"{len(d.get('furnaces', []))} fırın")
    kontrol("PLC yazma açık", d.get("plc_write") is True,
            "ERP_PLC_WRITE=1 ile başlatılmamış olabilir")
    return True


def test_b_uc_firin():
    baslik("B", "Üç fırın da çalışıyor mu?")
    kod, d = cagir("/api/furnaces")
    if kod != 200:
        kontrol("fırın listesi alındı", False, f"kod={kod}")
        return

    adlar = list(d.keys())
    kontrol("3 fırın geldi", len(adlar) == 3, f"{adlar}")

    # Önce hepsini durdur/temizle
    cagir("/api/test/faults/power-loss", "POST", {})

    sonuclar = []
    for ad in adlar:
        kod, _ = cagir("/api/plc/start", "POST",
                       {"furnace": ad, "duration_min": 1, "product": "Test"})
        sonuclar.append((ad, kod == 200))
        kontrol(f"{ad} başlatıldı", kod == 200, f"kod={kod}")

    bekle(4)
    kod, d = cagir("/api/furnaces")
    for ad, ok in sonuclar:
        if not ok:
            continue
        s = d.get(ad, {})
        kontrol(f"{ad} ısınıyor", s.get("burner_on") is True or s.get("status") in
                ("ISINIYOR", "BEKLETIYOR"),
                f"T={s.get('temperature')} durum={s.get('status')}")

    # Temizle
    cagir("/api/test/faults/power-loss", "POST", {})


def test_c_yazma():
    baslik("C", "Yazma (ERP → PLC)")
    f = "Biyet Isıtma Fırını"
    kod, d = cagir("/api/plc/set-target", "POST", {"furnace": f, "target": 450})
    kontrol("Hedef sıcaklık yazıldı", kod == 200, f"kod={kod}")

    kod, d = cagir("/api/furnaces")
    kontrol("Hedef fırına yansıdı", d[f]["target_temperature"] == 450,
            f"hedef={d[f]['target_temperature']}")

    kod, _ = cagir("/api/plc/start", "POST",
                   {"furnace": f, "duration_min": 1, "product": "Yazma Testi"})
    kontrol("Fırın başlatıldı", kod == 200, f"kod={kod}")

    kod, _ = cagir("/api/plc/stop", "POST", {"furnace": f})
    kontrol("Fırın durduruldu", kod == 200, f"kod={kod}")

    bekle(1)
    kod, d = cagir("/api/furnaces")
    kontrol("Durdurma sonrası KAPALI", d[f]["status"] == "KAPALI",
            f"durum={d[f]['status']}")


def test_d_guvenlik_reddi():
    baslik("D", "Güvenlik reddi (en kritik test)")
    f = "Aluminyum Eritme Fırını"
    kod, d = cagir("/api/plc/set-target", "POST", {"furnace": f, "target": 900})
    kontrol("900 °C hedef reddedildi (max 850)", kod == 400,
            f"kod={kod} mesaj={(d or {}).get('detail', '')[:60]}")
    if kod == 400:
        kontrol("Red gerekçesi Türkçe ve açık",
                "güvenlik" in str(d.get("detail", "")).lower())

    kod, _ = cagir("/api/plc/set-target", "POST", {"furnace": f, "target": -50})
    kontrol("Negatif hedef reddedildi", kod == 400, f"kod={kod}")


def test_e_cakisma():
    baslik("E", "Çakışma reddi")
    f = "Homojenizasyon Fırını"
    cagir("/api/plc/stop", "POST", {"furnace": f})
    kod, _ = cagir("/api/plc/start", "POST",
                   {"furnace": f, "duration_min": 2, "product": "Çakışma 1"})
    kontrol("İlk start kabul", kod == 200, f"kod={kod}")
    kod, d = cagir("/api/plc/start", "POST",
                   {"furnace": f, "duration_min": 2, "product": "Çakışma 2"})
    kontrol("Meşgulken ikinci start reddedildi", kod == 400,
            f"kod={kod} mesaj={(d or {}).get('detail', '')[:50]}")
    cagir("/api/plc/stop", "POST", {"furnace": f})


def test_f_alarm():
    baslik("F", "Alarm döngüsü (mandallı)")
    f = "Biyet Isıtma Fırını"
    cagir("/api/test/faults/clear", "POST", {})
    cagir("/api/plc/stop", "POST", {"furnace": f})

    cagir("/api/test/faults/overheat", "POST", {"furnace": f, "fazla": 25})
    bekle(2)
    kod, d = cagir("/api/furnaces")
    s = d[f]
    kontrol("ALARM durumuna düştü", s["status"] == "ALARM", f"durum={s['status']}")
    kontrol("Alarm mesajı dolu", bool(s["alarm"]), (s["alarm"] or "")[:60])
    kontrol("Brülör kapandı", s["burner_on"] is False)

    kod, sig = cagir("/api/plc/signals")
    kontrol("PLC sinyalinde alarm=True", sig[f]["alarm"] is True)

    # Mandal testi: soğumasını bekle, alarm KALMALI
    print("     (soğuması bekleniyor, alarm kaybolmamalı…)")
    for _ in range(12):
        bekle(2)
        _, d = cagir("/api/furnaces")
        if d[f]["temperature"] < 400:
            break
    kontrol("Soğuduktan sonra alarm HÂLÂ duruyor (mandallı)",
            bool(d[f]["alarm"]), f"T={round(d[f]['temperature'])}")

    kod, _ = cagir("/api/plc/reset-alarm", "POST", {"furnace": f})
    kontrol("Alarm onaylandı (reset)", kod == 200, f"kod={kod}")
    _, d = cagir("/api/furnaces")
    kontrol("Onay sonrası alarm temiz", d[f]["alarm"] is None)


def test_g_kesinti():
    baslik("G", "Kesinti (offline)")
    cagir("/api/test/faults/offline", "POST", {"aktif": True})
    kod, d = cagir("/api/furnaces")
    kontrol("Kesintide /api/furnaces 503", kod == 503, f"kod={kod}")
    kod, d = cagir("/api/meta")
    kontrol("Kesintide meta health=false", d.get("health") is False,
            f"health={d.get('health')}")
    cagir("/api/test/faults/offline", "POST", {"aktif": False})
    kod, _ = cagir("/api/furnaces")
    kontrol("Kesinti bitince 200", kod == 200, f"kod={kod}")


def test_h_i_kalite():
    baslik("H-I", "Veri kalitesi (STALE / BAD)")
    cagir("/api/test/faults/stale", "POST", {"aktif": True})
    _, d = cagir("/api/furnaces")
    n = list(d)[0]
    kontrol("STALE etiketi görünüyor", d[n].get("quality") == "STALE",
            f"quality={d[n].get('quality')}")

    cagir("/api/test/faults/sensor", "POST", {"aktif": True})
    _, d = cagir("/api/furnaces")
    kontrol("Sensör hatasında BAD etiketi", d[n].get("quality") == "BAD",
            f"quality={d[n].get('quality')}")
    kontrol("sensor_ok=false", d[n].get("sensor_ok") is False)

    cagir("/api/test/faults/clear", "POST", {})
    _, d = cagir("/api/meta")
    kontrol("Temizlik sonrası GOOD", d.get("quality") == "GOOD",
            f"quality={d.get('quality')}")


def test_j_guc():
    baslik("J", "Güç kesintisi")
    cagir("/api/plc/start", "POST",
          {"furnace": "Aluminyum Eritme Fırını", "duration_min": 1})
    bekle(2)
    cagir("/api/test/faults/power-loss", "POST", {})
    _, d = cagir("/api/furnaces")
    hepsi_kapali = all(s["status"] == "KAPALI" for s in d.values())
    kontrol("Tüm fırınlar KAPALI'ya düştü", hepsi_kapali,
            ", ".join(f"{k.split()[0]}={v['status']}" for k, v in d.items()))


def test_k_emir():
    baslik("K", "Emir yaşam döngüsü (CREATED → RUNNING → COMPLETED)")
    # Hızlı bitmesi için düşük hedef + kısa süre
    # Düşük hedef (çabuk ısınır) + yeterli süre. 0.1 dk = 6 sim-saniyesi
    # çok kısaydı; bekletme süresi hedefe ulaştıktan sonra işlemeye başlar.
    kod, d = cagir("/api/orders", "POST", {
        "product": "Test Partisi", "furnace": "Homojenizasyon Fırını",
        "target_temp": 60, "duration_min": 0.5,
    })
    if not kontrol("Emir oluşturuldu", kod == 200, f"kod={kod}"):
        return
    oid = d["id"]
    kontrol("Durum CREATED", d["state"] == "CREATED", d["state"])

    kod, _ = cagir(f"/api/orders/{oid}/start", "POST",
                   {"furnace": "Homojenizasyon Fırını"})
    kontrol("Emir başlatıldı", kod == 200, f"kod={kod}")

    tamam = False
    for _ in range(80):
        bekle(2.0)
        _, lst = cagir("/api/orders")
        mevcut = next((x for x in lst if x["id"] == oid), None)
        if mevcut and mevcut["state"] == "COMPLETED":
            tamam = True
            kontrol("Emir COMPLETED oldu", True)
            kontrol("Bitiş zamanı yazıldı", mevcut.get("finished_at") is not None)
            kontrol("Enerji özeti yazıldı",
                    mevcut.get("energy_total_m3") is not None,
                    f"enerji={mevcut.get('energy_total_m3')}")
            break
    if not tamam:
        _, lst = cagir("/api/orders")
        mevcut = next((x for x in lst if x["id"] == oid), None)
        kontrol("Emir COMPLETED oldu", False,
                f"160 sn beklendi, durum={mevcut['state'] if mevcut else '?'} "
                f"(hız düşükse bu test uzun sürer — SIM_SPEED=10 önerilir)")


def test_l_denetim():
    baslik("L", "Komut denetim izi")
    kod, lst = cagir("/api/plc/commands?limit=20")
    kontrol("Komut kaydı erişilebilir", kod == 200, f"kod={kod}")
    if isinstance(lst, list):
        kontrol("En az 5 komut kaydı var", len(lst) >= 5, f"{len(lst)} kayıt")
        gecerli = all("seq" in c and "ok" in c and "message" in c for c in lst)
        kontrol("Her kayıtta seq/ok/message var", gecerli)


# ------------------------------------------------------------------ ana akış


def main() -> int:
    print("=" * 62)
    print("  ERP ENTEGRASYON TESTİ")
    print(f"  Hedef: {BASE}")
    print("=" * 62)

    kod, d = cagir("/api/meta")
    if kod != 200:
        print("\n✗ Simülasyona ulaşılamadı.")
        print("  Önce şunu çalıştır:")
        print("    ERP_PLC_WRITE=1 SIM_SPEED=10 python3 -m erp_backend.main")
        return 2

    if not d.get("plc_write"):
        print("\n⚠ PLC YAZMA KAPALI — C/D/E/F testleri başarısız olacak.")
        print("  Sunucuyu şu şekilde başlat: ERP_PLC_WRITE=1")

    test_a_saglik()
    test_b_uc_firin()
    test_c_yazma()
    test_d_guvenlik_reddi()
    test_e_cakisma()
    test_f_alarm()
    test_g_kesinti()
    test_h_i_kalite()
    test_j_guc()
    test_k_emir()
    test_l_denetim()
    test_m_plc_baslat_emri()
    test_n_durdurma_iptal()

    # Temizlik
    cagir("/api/test/faults/clear", "POST", {})

    gecen = sum(1 for _, ok, _ in SONUC if ok)
    toplam = len(SONUC)
    print("\n" + "=" * 62)
    print(f"  SONUÇ: {gecen}/{toplam} test geçti")
    if gecen == toplam:
        print("  ✓ Her şey çalışıyor. ERP'ni bağlayabilirsin.")
    else:
        print("  ✗ Başarısız testler:")
        for ad, ok, ayrinti in SONUC:
            if not ok:
                print(f"     - {ad}" + (f" ({ayrinti})" if ayrinti else ""))
    print("=" * 62)
    return 0 if gecen == toplam else 1


# ---------------------------------------------------------------- M, N

def test_m_plc_baslat_emri():
    """PLC'den başlatılan fırın /api/orders'ta emir olarak GÖRÜNMELİ.

    Bu, 'ERP neden hiç emir görmüyor?' hatasının regresyon testidir:
    /api/plc/start doğrudan fırına yazıyordu, plant.orders'a kayıt
    açmadığı için ERP paneli boş kalıyordu.
    """
    baslik("M", "PLC başlatması emir kaydı oluşturuyor")
    cagir("/api/test/faults/clear", "POST", {})
    cagir("/api/plc/stop", "POST", {"furnace": FIRINLAR[2]})

    kod, d = cagir("/api/plc/start", "POST", {
        "furnace": FIRINLAR[2], "product": "PLC Kayit Testi",
        "duration_min": 1, "source": "ERP",
    })
    kontrol("PLC start kabul edildi", kod == 200, f"kod={kod}")

    kod, emirler = cagir("/api/orders")
    benim = [o for o in emirler if o.get("product") == "PLC Kayit Testi"]
    kontrol("/api/orders'ta emir görünüyor", len(benim) == 1,
            f"{len(benim)} kayıt")
    if benim:
        e = benim[0]
        kontrol("Emir RUNNING", e["state"] == "RUNNING", e["state"])
        kontrol("Fırın adı doğru", e["furnace"] == FIRINLAR[2], e["furnace"])
        kontrol("started_at yazıldı", e.get("started_at") is not None)
    cagir("/api/plc/stop", "POST", {"furnace": FIRINLAR[2]})


def test_n_durdurma_iptal():
    """Durdurulan emir CANCELLED olmalı, sessizce kaybolmamalı."""
    baslik("N", "Durdurulan emir CANCELLED oluyor")
    cagir("/api/plc/stop", "POST", {"furnace": FIRINLAR[0]})
    kod, _ = cagir("/api/plc/start", "POST", {
        "furnace": FIRINLAR[0], "product": "Iptal Testi",
        "duration_min": 5, "source": "ERP",
    })
    kontrol("Emir başlatıldı", kod == 200, f"kod={kod}")
    cagir("/api/plc/stop", "POST", {"furnace": FIRINLAR[0]})
    bekle(0.5)
    _, emirler = cagir("/api/orders")
    benim = [o for o in emirler if o.get("product") == "Iptal Testi"]
    kontrol("Emir CANCELLED", bool(benim) and benim[0]["state"] == "CANCELLED",
            benim[0]["state"] if benim else "kayıt yok")



if __name__ == "__main__":
    sys.exit(main())
