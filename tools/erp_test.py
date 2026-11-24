#!/usr/bin/env python3
"""ERP fonksiyon testleri — doküman §5 (35 ekran), §6 (iş akışları), §7 (hesaplar).

Fırın testlerinden (`tools/system_test.py`) bağımsız çalışır: burada ERP'nin
ticari/operasyonel zinciri sınanır. Sunucu ayakta olmalı:

    ERP_PLC_WRITE=1 SIM_SPEED=25 python3 -m erp_backend.main
    python3 tools/erp_test.py

Her test dokümandaki bir kuralı doğrular; başlıklar doküman bölüm numarası
taşır, böylece "hangi fonksiyon test edildi" sorusu tek bakışta yanıtlanır.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/erp"
SONUC: list[tuple[str, bool, str]] = []
# Her çalıştırma kendi clientId uzayını kullanır; önceki çalıştırmadan kalan
# kayıtlar idempotency testlerini yanlışlıkla "tekrar" durumuna düşürmesin.
RUN_ID = str(int(time.time()))


def cagir(yol: str, metot: str = "GET", govde=None):
    url = BASE + yol
    veri = None
    basliklar = {}
    if govde is not None:
        veri = json.dumps(govde).encode()
        basliklar["Content-Type"] = "application/json"
    istek = urllib.request.Request(url, data=veri, headers=basliklar,
                                   method=metot)
    try:
        with urllib.request.urlopen(istek, timeout=15) as y:
            return y.status, json.loads(y.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:  # bağlantı yok
        print(f"\n  ✗ Sunucuya ulaşılamadı: {e}\n"
              f"    Önce: python3 -m erp_backend.main")
        sys.exit(2)


def kontrol(ad: str, ok: bool, ayrinti: str = "") -> bool:
    SONUC.append((ad, bool(ok), ayrinti))
    isaret = "✓" if ok else "✗"
    print(f"  {isaret} {ad}" + (f"  — {ayrinti}" if ayrinti else ""))
    return ok


def baslik(kod: str, ad: str) -> None:
    print(f"\n[{kod}] {ad}")


# =================================================================== A: meta

def test_a_meta():
    baslik("A", "Meta: 59 varlık, 35 ekran, 15 modül, 18 hesap motoru")
    kod, d = cagir("/meta")
    kontrol("GET /api/erp/meta", kod == 200, f"kod={kod}")
    if kod == 200:
        kontrol("59 varlık", d["varlik_sayisi"] == 59, f"{d['varlik_sayisi']}")
        kontrol("35 ekran", d["ekran_sayisi"] == 35, f"{d['ekran_sayisi']}")
        kontrol("15 modül", d["modul_sayisi"] == 15, f"{d['modul_sayisi']}")
        kontrol("18 hesap motoru", len(d["hesap_motorlari"]) == 18,
                f"{len(d['hesap_motorlari'])}")


# =================================================================== B: hesaplar

def test_b_hesaplar():
    baslik("B", "Hesap motorları — doküman §7.1 sayıları birebir")
    kod, d = cagir("/hesap/self-check")
    kontrol("self-check erişilebilir", kod == 200, f"kod={kod}")
    if kod != 200:
        return
    kontrol("6300 mm döküm = 423,29 kg", abs(d["dokum_6300_kg"] - 423.29) < 0.02,
            f"{d['dokum_6300_kg']}")
    kontrol("6000 mm mamul = 403,13 kg", abs(d["mamul_6000_kg"] - 403.13) < 0.02,
            f"{d['mamul_6000_kg']}")
    kontrol("300 mm kafa = 20,16 kg", abs(d["kafa_300_kg"] - 20.16) < 0.02,
            f"{d['kafa_300_kg']}")
    kontrol("3 mm talaş = 0,202 kg", abs(d["talas_3_kg"] - 0.202) < 0.001,
            f"{d['talas_3_kg']}")
    kontrol("dokümanla uyumlu", d["uyumlu"])

    # Kesim raporu
    kod, r = cagir("/hesap/kesim", "POST", {"kafa_adedi": 2, "kesim_sayisi": 2})
    kontrol("cutting_report çalışıyor", kod == 200, f"kod={kod}")
    if kod == 200:
        kontrol("net biyet < döküm", r["net_biyet_kg"] < r["dokum_kg"],
                f"{r['net_biyet_kg']} < {r['dokum_kg']}")
        kontrol("gerçek kafa payı 297 mm",
                abs(r["gercek_kafa_payi_mm"] - 297.0) < 0.5,
                f"{r['gercek_kafa_payi_mm']}")

    # Geometri toleransı
    # Net ~382,6 kg; %2 dışına çıkmak için 420 kg kaydedelim (%9,8 fark).
    kod, g = cagir("/hesap/kesim", "POST",
                   {"tonaj_kg": 420.0, "kafa_adedi": 2, "kesim_sayisi": 2})
    if kod == 200:
        gc = g["geometry_check"]
        kontrol("geometry_check %2 tolerans dışı → uygun değil",
                gc["uygun"] is False, f"fark={gc['fark_yuzde']}%")

    # Maliyet
    kod, m = cagir("/hesap/maliyet", "POST", {
        "hammadde": 12000, "enerji": 3500, "sarf": 800,
        "iscilik": 2200, "fire": 1500, "net_ton": 14})
    kontrol("lot_cost çalışıyor", kod == 200, f"kod={kod}")
    if kod == 200:
        kontrol("toplam maliyet 20.000", abs(m["toplam"] - 20000) < 0.01,
                f"{m['toplam']}")
        kontrol("ton maliyeti 1.428,57", abs(m["ton_maliyet"] - 1428.57) < 0.05,
                f"{m['ton_maliyet']}")

    # Kredi kontrolü — limit aşımı
    kod, k = cagir("/hesap/kredi", "POST",
                   {"limit": 50000, "kullanilan": 30000, "yeni_tutar": 25000})
    kontrol("limit aşımı reddedildi", kod == 200 and k["onay"] is False,
            f"onay={k.get('onay')} aşılan={k.get('asilan')}")
    kod, k2 = cagir("/hesap/kredi", "POST",
                    {"limit": 50000, "kullanilan": 30000, "yeni_tutar": 15000})
    kontrol("limit içi kabul", k2["onay"] is True, f"onay={k2['onay']}")

    # KDV
    kod, a = cagir("/hesap/maliyet", "POST", {"hammadde": 1000, "net_ton": 1})
    kontrol("maliyet kalem payları %100",
            abs(sum(m["kalem_paylari"].values()) - 100.0) < 0.5,
            f"{sum(m['kalem_paylari'].values()):.1f}%")

    # posting effects
    kod, pe = cagir("/hesap/posting-effects", "POST",
                    {"belge_tipi": "sevkiyat", "tutar": 10000})
    kontrol("sevkiyat 8 kayıt üretiyor",
            kod == 200 and pe["kayit_sayisi"] == 8,
            f"{pe.get('kayit_sayisi')} kayıt")
    if kod == 200:
        kontrol("fiş dengeli", pe["fis_dengeli"] is True)

    kod, pe2 = cagir("/hesap/posting-effects", "POST",
                     {"belge_tipi": "bilinmeyen", "tutar": 100})
    kontrol("bilinmeyen belge tipi 400", kod == 400, f"kod={kod}")


# =================================================================== C: malzeme/tedarikçi

def test_c_tanimlar():
    baslik("C", "Malzeme, tedarikçi, müşteri, makine tanımları")
    for koleksiyon, min_adet in [("materials", 5), ("suppliers", 3),
                                 ("customers", 3), ("machines", 8),
                                 ("machineTypes", 6), ("recipes", 1),
                                 ("warehouses", 2), ("accounts", 12),
                                 ("integrationRules", 10)]:
        kod, d = cagir(f"/{koleksiyon}")
        kontrol(f"{koleksiyon} listeleniyor",
                kod == 200 and d["toplam"] >= min_adet,
                f"{d.get('toplam')} kayıt")

    kod, d = cagir("/materials/MAT-0001")
    kontrol("tek kayıt sorgusu", kod == 200, d.get("ad", ""))
    kod, _ = cagir("/materials/YOK-9999")
    kontrol("olmayan kayıt 404", kod == 404, f"kod={kod}")
    kod, _ = cagir("/bilinmeyen-varlik")
    kontrol("bilinmeyen varlık 404", kod == 404, f"kod={kod}")


# =================================================================== D: satın alma

def test_d_satin_alma():
    baslik("D", "§6.1 Satın alma → mal kabul → fatura")
    # Talep
    kod, talep = cagir("/satin-alma/talep", "POST", {
        "malzeme": "MAT-0001", "miktar": 5000, "gerekce": "Test partisi"})
    kontrol("talep açıldı", kod == 200, talep.get("id", ""))
    if kod != 200:
        return

    # Hatalı talep
    kod, _ = cagir("/satin-alma/talep", "POST",
                   {"malzeme": "YOK-1", "miktar": 10})
    kontrol("olmayan malzeme reddedildi", kod == 400, f"kod={kod}")
    kod, _ = cagir("/satin-alma/talep", "POST",
                   {"malzeme": "MAT-0001", "miktar": -5})
    kontrol("negatif miktar reddedildi", kod == 400, f"kod={kod}")

    # Teklifler — 2 tedarikçi
    kod, t1 = cagir("/satin-alma/teklif", "POST", {
        "talep_id": talep["id"], "tedarikci": "SUP-0001", "birim_fiyat": 2.40})
    kontrol("teklif 1 alındı", kod == 200, f"{t1.get('birimFiyat')} TL")
    kod, t2 = cagir("/satin-alma/teklif", "POST", {
        "talep_id": talep["id"], "tedarikci": "SUP-0002", "birim_fiyat": 2.25})
    kontrol("teklif 2 alındı", kod == 200, f"{t2.get('birimFiyat')} TL")

    # Ucuz olanı seç
    kod, emir = cagir("/satin-alma/teklif-sec", "POST",
                      {"teklif_id": t2["id"]})
    kontrol("teklif seçildi", kod == 200, emir.get("id", ""))
    kontrol("emir TASLAK", emir.get("durum") == "TASLAK", emir.get("durum"))
    kontrol("emir toplamı doğru (5000 × 2,25 = 11.250)",
            abs(emir.get("toplam", 0) - 11250) < 0.1, f"{emir.get('toplam')}")

    # Onaysız mal kabul reddedilmeli
    kod, _ = cagir("/satin-alma/mal-kabul", "POST", {
        "emir_id": emir["id"], "brut": 1000})
    kontrol("onaysız emre mal kabul reddedildi", kod == 400, f"kod={kod}")

    # Onayla
    kod, _ = cagir("/satin-alma/onayla", "POST", {"emir_id": emir["id"]})
    kontrol("emir onaylandı", kod == 200, f"kod={kod}")

    # Mal kabul — fire oranı kontrolü
    kod, mk = cagir("/satin-alma/mal-kabul", "POST", {
        "emir_id": emir["id"], "brut": 5200, "fire": 200})
    kontrol("mal kabul yapıldı", kod == 200, mk.get("id", ""))
    if kod == 200:
        kontrol("net = brüt - fire", abs(mk["net"] - 5000) < 0.01,
                f"{mk['net']}")
        kontrol("fire oranı %3,85",
                abs(mk["fireOraniYuzde"] - 3.85) < 0.05,
                f"%{mk['fireOraniYuzde']}")

    # Fire > brüt reddedilmeli
    kod, _ = cagir("/satin-alma/mal-kabul", "POST", {
        "emir_id": emir["id"], "brut": 100, "fire": 150})
    kontrol("fire > brüt reddedildi", kod == 400, f"kod={kod}")

    # Fiyat geçmişi oluştu mu
    kod, fh = cagir("/priceHistory")
    kontrol("fiyat geçmişi yazıldı", kod == 200 and fh["toplam"] > 0,
            f"{fh.get('toplam')} kayıt")

    # Alış faturası
    kod, f = cagir("/satin-alma/fatura", "POST", {"emir_id": emir["id"]})
    kontrol("alış faturası kesildi", kod == 200, f.get("fatura", {}).get("id", ""))
    if kod == 200:
        kontrol("fiş dengeli", f["fis"]["balanced"] is True)
        kontrol("KDV %20", abs(f["fatura"]["kdv"] - f["fatura"]["net"] * 0.2) < 0.1,
                f"KDV={f['fatura']['kdv']}")


# =================================================================== E: üretim

def test_e_uretim():
    baslik("E", "§6.2 Üretim: reçete → lot → 8 aşama → mamul stok")
    kod, lot = cagir("/uretim/lot", "POST", {
        "recete_id": "RCP-0001", "firin_makine": "MCH-01"})
    kontrol("lot açıldı", kod == 200, lot.get("kod", ""))
    if kod != 200:
        return
    kontrol("lot Ergitme aşamasında", lot["asama"] == "Ergitme", lot["asama"])

    # Aşama atlanamaz
    kod, _ = cagir("/uretim/asama", "POST",
                   {"lot_id": lot["id"], "asama": "Testere"})
    kontrol("aşama atlama reddedildi", kod == 400, f"kod={kod}")

    # 7 kez ilerlet
    asamalar = []
    for _ in range(7):
        kod, d = cagir("/uretim/asama", "POST", {"lot_id": lot["id"]})
        if kod == 200:
            asamalar.append(d["asama"])
    kontrol("7 aşama ilerledi", len(asamalar) == 7, " → ".join(asamalar))
    kontrol("son aşama Sevkiyat", asamalar and asamalar[-1] == "Sevkiyat",
            asamalar[-1] if asamalar else "-")

    # 8. kez hata
    kod, _ = cagir("/uretim/asama", "POST", {"lot_id": lot["id"]})
    kontrol("sonrası ilerletme reddedildi", kod == 400, f"kod={kod}")

    # Hedef tonaj aşımı
    kod, _ = cagir("/uretim/tamamla", "POST",
                   {"lot_id": lot["id"], "net_ton": 20})
    kontrol("hedef tonaj aşımı reddedildi", kod == 400, f"kod={kod}")

    # Tamamla
    kod, lt = cagir("/uretim/tamamla", "POST", {
        "lot_id": lot["id"], "net_ton": 14, "fire_ton": 0.4})
    kontrol("lot tamamlandı", kod == 200, f"{lt.get('netTon')} ton")
    kontrol("lot TAMAMLANDI", lt.get("durum") == "TAMAMLANDI", lt.get("durum"))

    # Mamul stok
    kod, stok = cagir("/stok/durum")
    mamul = [s for s in stok if "MAMUL" in s["malzeme"]]
    kontrol("mamul stoğa girdi", len(mamul) > 0,
            f"{mamul[0]['mevcut']} TON" if mamul else "stok yok")

    # Yan ürün
    kod, yan = cagir("/byProductFates")
    kontrol("yan ürün kaydı", yan["toplam"] > 0, f"{yan['toplam']} kayıt")
    kod, kir = cagir("/crusher")
    kontrol("kırıcı kaydı", kir["toplam"] > 0, f"{kir['toplam']} kayıt")

    # Maliyet
    kod, ml = cagir("/uretim/maliyet", "POST", {
        "lot_id": lot["id"], "enerji": 3500, "sarf": 800, "iscilik": 2200})
    kontrol("lot maliyeti hesaplandı", kod == 200,
            f"ton={ml.get('ton_maliyet')} TL")
    if kod == 200:
        kontrol("5 kalem var", len(ml["kalemler"]) == 5,
                ", ".join(ml["kalemler"]))
        kontrol("kalem payları toplamı %100",
                abs(sum(ml["kalem_paylari"].values()) - 100.0) < 0.5)


# =================================================================== F: homojenizasyon

def test_f_homojenizasyon():
    baslik("F", "§5/13 Homojenizasyon: plan → süre sapması")
    kod, lot = cagir("/uretim/lot", "POST", {
        "recete_id": "RCP-0001", "firin_makine": "MCH-10"})
    kod, parti = cagir("/uretim/homojenizasyon", "POST", {
        "lot_id": lot["id"], "recete_id": "HRC-0001",
        "hedef_sicaklik": 560, "hedef_sure_dk": 8})
    kontrol("parti planlandı", kod == 200, parti.get("id", ""))
    kod, tam = cagir("/uretim/homojenizasyon-tamamla", "POST", {
        "parti_id": parti["id"], "gercek_sure_dk": 9.5,
        "gercek_sicaklik": 558})
    kontrol("parti tamamlandı", kod == 200, f"kod={kod}")
    if kod == 200:
        k = tam["sure_kontrol"]
        kontrol("süre sapması +1,5 dk", abs(k["fark_dk"] - 1.5) < 0.05,
                f"{k['fark_dk']} dk")
        kontrol("süre aşıldı işaretlendi", k["asildi"] is True)
    kod, _ = cagir("/uretim/homojenizasyon-tamamla", "POST", {
        "parti_id": parti["id"], "gercek_sure_dk": 8, "gercek_sicaklik": 560})
    kontrol("ikinci tamamlama reddedildi", kod == 400, f"kod={kod}")


# =================================================================== G: stok/sayım

def test_g_stok():
    baslik("G", "§6.4 Sayım farkı, kırıcı, stok hareketleri")
    kod, once = cagir("/materials/MAT-0003")
    kod, stok = cagir("/stok/durum")
    m3 = next((s for s in stok if s["malzeme"] == "MAT-0003"), None)
    mevcut = m3["mevcut"] if m3 else 0

    # Sayım: eksik çıksın
    kod, sy = cagir("/stok/sayim", "POST", {
        "malzeme": "MAT-0003", "sayilan": mevcut - 12})
    kontrol("sayım yapıldı", kod == 200, sy.get("id", ""))
    if kod == 200:
        kontrol("fark -12 tespit", abs(sy["fark"] + 12) < 0.01, f"{sy['fark']}")
        kontrol("FARK_VAR durumu", sy["durum"] == "FARK_VAR", sy["durum"])

    # Stok düzeltildi mi
    kod, stok2 = cagir("/stok/durum")
    m3y = next((s for s in stok2 if s["malzeme"] == "MAT-0003"), None)
    kontrol("stok düzeltildi", m3y and abs(m3y["mevcut"] - (mevcut - 12)) < 0.01,
            f"{m3y['mevcut'] if m3y else '?'}")

    # Uygun sayım
    kod, sy2 = cagir("/stok/sayim", "POST", {
        "malzeme": "MAT-0004", "sayilan": 24})
    kontrol("farksız sayım UYGUN",
            kod == 200 and sy2["durum"] == "UYGUN", sy2.get("durum"))

    # Kırıcı — geçersiz kader
    kod, lot = cagir("/uretim/lot", "POST", {
        "recete_id": "RCP-0001", "firin_makine": "MCH-01"})
    kod, _ = cagir("/stok/kirici", "POST", {
        "lot_id": lot["id"], "miktar_ton": 1, "kader": "UZAYA_GONDER"})
    kontrol("geçersiz kader reddedildi", kod == 400, f"kod={kod}")
    for kader in ("TEKRAR_FIRIN", "DONGUSEL", "SATIS", "ATIK"):
        kod, _ = cagir("/stok/kirici", "POST", {
            "lot_id": lot["id"], "miktar_ton": 0.1, "kader": kader})
        kontrol(f"kader {kader} kabul", kod == 200, f"kod={kod}")

    # Stok hareketleri
    kod, hr = cagir("/movements")
    kontrol("stok hareketleri var", kod == 200 and hr["toplam"] > 5,
            f"{hr.get('toplam')} hareket")


# =================================================================== H: satış

def test_h_satis():
    baslik("H", "§6.3 Satış siparişi, kredi kontrolü, teklif")
    # Teklif
    kod, teklif = cagir("/satis/teklif", "POST", {
        "musteri": "CUS-0003", "urun": "6063 Alüminyum Biyet",
        "miktar_ton": 2, "birim_fiyat": 3500})
    kontrol("satış teklifi oluştu", kod == 200, teklif.get("id", ""))
    if kod == 200:
        kontrol("teklif KDV %20",
                abs(teklif["kdv"] - teklif["tutar"] * 0.2) < 0.1,
                f"KDV={teklif['kdv']}")

    # Yetersiz stok
    kod, _ = cagir("/satis/siparis", "POST", {
        "musteri": "CUS-0001", "urun": "6063 Alüminyum Biyet",
        "miktar_ton": 999, "birim_fiyat": 3000})
    kontrol("yetersiz stok reddedildi", kod == 400, f"kod={kod}")

    # Kredi limiti aşımı — CUS-0003 limit 150.000, bakiye 142.000
    kod, _ = cagir("/satis/siparis", "POST", {
        "musteri": "CUS-0003", "urun": "6063 Alüminyum Biyet",
        "miktar_ton": 8, "birim_fiyat": 3500})
    kontrol("kredi limiti aşımı reddedildi", kod == 400, f"kod={kod}")

    # Normal sipariş
    kod, sip = cagir("/satis/siparis", "POST", {
        "musteri": "CUS-0002", "urun": "6063 Alüminyum Biyet",
        "miktar_ton": 3, "birim_fiyat": 3400})
    kontrol("satış siparişi açıldı", kod == 200, sip.get("id", ""))
    if kod == 200:
        kontrol("kredi kontrolü geçti", sip["krediKontrol"]["onay"] is True)
        kontrol("sipariş ACIK", sip["durum"] == "ACIK", sip["durum"])
        # Rezervasyon
        kod, rez = cagir("/reservations")
        ilgili = [r for r in rez["kayitlar"] if r["siparisId"] == sip["id"]]
        kontrol("rezervasyon oluştu", len(ilgili) == 1, f"{len(ilgili)} kayıt")


# =================================================================== I: sevkiyat

def test_i_sevkiyat():
    baslik("I", "§6.3 Sevkiyat: iki onay, tek kayıt çok etki, idempotency")
    # Stoklu ürün bulalım
    kod, stok = cagir("/stok/durum")
    mamul = [s for s in stok if "MAMUL" in s["malzeme"] and s["mevcut"] > 1]
    if not mamul:
        kontrol("mamul stok mevcut", False, "önce E testini çalıştır")
        return
    urun = mamul[0]["ad"]

    kod, sip = cagir("/satis/siparis", "POST", {
        "musteri": "CUS-0001", "urun": urun, "miktar_ton": 1,
        "birim_fiyat": 4000})
    kontrol("sipariş açıldı", kod == 200, sip.get("id", ""))
    if kod != 200:
        return

    kod, sev = cagir("/sevkiyat/hazirla", "POST", {"siparis_id": sip["id"]})
    kontrol("sevkiyat hazırlandı", kod == 200, sev.get("id", ""))
    if kod != 200:
        return
    kontrol("durum HAZIRLANIYOR", sev["durum"] == "HAZIRLANIYOR", sev["durum"])

    # 1. onay
    kod, r1 = cagir("/sevkiyat/onayla", "POST", {"sevkiyat_id": sev["id"]})
    kontrol("1. onay alındı", kod == 200 and r1.get("asama") == 1,
            r1.get("mesaj", r1.get("detail", "")))
    kontrol("henüz sevk edilmedi",
            r1.get("sevkiyat", {}).get("durum") == "ONAY1_TAMAM",
            str(r1.get("sevkiyat", {}).get("durum")))

    # 2. onay — 8 kayıt
    sevk_cid = f"SEVK-{RUN_ID}"
    kod, r2 = cagir("/sevkiyat/onayla", "POST", {
        "sevkiyat_id": sev["id"], "plaka": "34 TEST 01",
        "client_id": sevk_cid})
    kontrol("2. onay alındı", kod == 200 and r2.get("asama") == 2,
            r2.get("mesaj", r2.get("detail", "")))
    if kod == 200:
        kontrol("8 kayıt üretildi", r2["kayit_sayisi"] == 8,
                f"{r2['kayit_sayisi']} kayıt")
        u = r2["uretilen"]
        kontrol("stok çıkışı", u["stok_cikis"] is True)
        kontrol("fatura kesildi", bool(u["fatura"]), u["fatura"])
        kontrol("muhasebe fişi", bool(u["fis"]), u["fis"])
        kontrol("cari bakiye güncellendi", u["cari_bakiye"] is not None,
                str(u["cari_bakiye"]))
        kontrol("bildirim üretildi", u["bildirim"] is True)
        kontrol("outbox üretildi", u["outbox"] is True)
        kontrol("olay yazıldı", u["olay"] is True)

    # Idempotency — aynı clientId
    kod, r3 = cagir("/sevkiyat/onayla", "POST", {
        "sevkiyat_id": sev["id"], "client_id": sevk_cid})
    kontrol("aynı clientId ikinci kez yazmıyor",
            kod == 200 and r3.get("tekrar") is True, r3.get("mesaj", ""))

    # Fatura sayısı artmadı mı
    kod, ft = cagir("/invoices?limit=2000")
    ayni = [f for f in ft["kayitlar"] if f.get("clientId") == sevk_cid]
    kontrol("tek fatura oluştu", len(ayni) == 1, f"{len(ayni)} fatura")

    # Stok düştü mü
    kod, stok2 = cagir("/stok/durum")
    yeni = next((s for s in stok2 if s["malzeme"] == mamul[0]["malzeme"]), None)
    kontrol("stoktan düşüldü",
            yeni and abs(yeni["mevcut"] - (mamul[0]["mevcut"] - 1)) < 0.01,
            f"{mamul[0]['mevcut']} → {yeni['mevcut'] if yeni else '?'}")


# =================================================================== J: muhasebe

def test_j_muhasebe():
    baslik("J", "§7.3 Muhasebe: fiş dengesi, mizan, dönem kapanışı, ödeme")
    kod, tb = cagir("/finans/mizan")
    kontrol("mizan alındı", kod == 200, f"kod={kod}")
    if kod == 200:
        kontrol("mizan denk (borç = alacak)", tb["denk"] is True,
                f"borç={tb['toplam_borc']} alacak={tb['toplam_alacak']}")
        kontrol("mizanda hesap var", len(tb["satirlar"]) > 0,
                f"{len(tb['satirlar'])} hesap")
        toplam_b = sum(s["borc"] for s in tb["satirlar"])
        kontrol("satır toplamı = başlık toplamı",
                abs(toplam_b - tb["toplam_borc"]) < 0.01)

    # Dengesiz fiş engeli — dönem kapanışı mizan denk olmalı
    kod, dk = cagir("/finans/donem-kapat", "POST", {
        "donem": time.strftime("%Y-%m"), "onay": True})
    kontrol("dönem kapatıldı", kod == 200, dk.get("id", ""))

    kod, _ = cagir("/finans/donem-kapat", "POST",
                   {"donem": time.strftime("%Y-%m"), "onay": False})
    kontrol("onaysız kapanış reddedildi", kod == 400, f"kod={kod}")

    # Tahsilat
    kod, mus = cagir("/customers/CUS-0002")
    bakiye = mus["bakiye"]
    if bakiye > 1000:
        kod, od = cagir("/finans/odeme", "POST", {
            "tip": "TAHSILAT", "taraf": "CUS-0002", "tutar": 1000})
        kontrol("tahsilat kaydedildi", kod == 200, od.get("id", ""))
        kod, mus2 = cagir("/customers/CUS-0002")
        kontrol("bakiye düştü", abs(mus2["bakiye"] - (bakiye - 1000)) < 0.01,
                f"{bakiye} → {mus2['bakiye']}")

        # Fazla tahsilat reddi
        kod, _ = cagir("/finans/odeme", "POST", {
            "tip": "TAHSILAT", "taraf": "CUS-0002",
            "tutar": mus2["bakiye"] + 5000})
        kontrol("bakiye üstü tahsilat reddedildi", kod == 400, f"kod={kod}")

    # Ödeme
    kod, sup = cagir("/suppliers/SUP-0001")
    if sup.get("bakiye", 0) > 100:
        kod, od2 = cagir("/finans/odeme", "POST", {
            "tip": "ODEME", "taraf": "SUP-0001", "tutar": 100})
        kontrol("tedarikçi ödemesi", kod == 200, od2.get("id", ""))

    # Geçersiz tip
    kod, _ = cagir("/finans/odeme", "POST",
                   {"tip": "HEDIYE", "taraf": "CUS-0001", "tutar": 10})
    kontrol("geçersiz ödeme tipi reddedildi", kod == 400, f"kod={kod}")


# =================================================================== K: bakım

def test_k_bakim():
    baslik("K", "§5/18 Yağ & bakım: eşik, kalan ömür, sayaç sıfırlama")
    kod, d = cagir("/bakim/durum")
    kontrol("bakım durumu alındı", kod == 200, f"{len(d)} sayaç")
    if kod != 200 or not d:
        return
    kontrol("seviye alanı var", all("seviye" in x for x in d))
    kontrol("yüzde 0-200 arası",
            all(0 <= x.get("yuzde", -1) <= 200 for x in d),
            str([x.get("yuzde") for x in d]))
    kontrol("geçerli seviye değerleri",
            all(x.get("seviye") in ("normal", "yaklasiyor", "esik_doldu")
                for x in d),
            ", ".join(sorted({str(x.get("seviye")) for x in d})))

    # Bakım kaydı + sayaç sıfırlama (MCH-30'un bıçak sayacı dolu olsun)
    kod, bk = cagir("/bakim/kaydet", "POST", {
        "makine_kod": "MCH-30", "tip": "bıçak değişimi",
        "notu": "Test bakımı", "kesim": 1900})
    kontrol("bakım kaydedildi", kod == 200, bk.get("id", ""))
    kod, d2 = cagir("/bakim/durum")
    mch30 = [x for x in d2 if x["makineKod"] == "MCH-30"]
    kontrol("sayaç sıfırlandı",
            mch30 and all(x.get("yuzde") == 0.0 for x in mch30),
            str([x.get("yuzde") for x in mch30]))

    # Eşik mantığı: hesap motoru sözleşmesi (maintenance_status)
    # %50 → normal, %85 → yaklaşıyor, %100 → eşik doldu
    kod, d3 = cagir("/bakim/durum")
    kontrol("eşik aritmetiği doğru (yüzde = kullanilan/limit×100)",
            all(abs(x["yuzde"] - (x["kullanilan"] / x["limit"] * 100)) < 0.2
                for x in d3 if x["limit"]),
            f"{len(d3)} sayaç")

    # Olmayan makine
    kod, _ = cagir("/bakim/kaydet", "POST",
                   {"makine_kod": "MCH-99", "tip": "x"})
    kontrol("olmayan makine reddedildi", kod == 400, f"kod={kod}")


# =================================================================== L: personel

def test_l_personel():
    baslik("L", "§5/25 Personel & vardiya (bordro kapsam dışı)")
    kod, d = cagir("/personel/vardiya")
    kontrol("vardiya planı alındı", kod == 200,
            f"{d.get('toplam_personel')} personel")
    if kod == 200:
        kontrol("bordro kapsam dışı", d["bordro_kapsam"] is False)
        kontrol("en az 1 vardiya", len(d["vardiyalar"]) >= 1,
                ", ".join(d["vardiyalar"].keys()))

    kod, yeni = cagir("/personel", "POST", {
        "ad": "Test Personel", "rol": "Operatör", "vardiya": "00:00-08:00"})
    kontrol("personel eklendi", kod == 200, yeni.get("id", ""))
    kod, d2 = cagir("/personel/vardiya")
    kontrol("personel sayısı arttı",
            d2["toplam_personel"] == d["toplam_personel"] + 1,
            f"{d['toplam_personel']} → {d2['toplam_personel']}")


# =================================================================== M: KPI/rapor

def test_m_kpi():
    baslik("M", "§13 Panel KPI ve raporlama göstergeleri")
    kod, k = cagir("/kpi")
    kontrol("KPI alındı", kod == 200, f"kod={kod}")
    if kod != 200:
        return
    zorunlu = ["ciro", "alacak", "borc", "net_pozisyon", "acik_siparis",
               "uretim_ton", "fire_orani_yuzde", "butce_kullanim_yuzde",
               "tedarikci_sayisi", "musteri_sayisi", "sevkiyat_sayisi",
               "stok_degeri", "outbox_kuyruk", "acik_bildirim"]
    eksik = [x for x in zorunlu if x not in k]
    kontrol("§13 tüm göstergeler var", not eksik,
            f"eksik: {eksik}" if eksik else f"{len(zorunlu)} gösterge")
    kontrol("ciro > 0 (sevkiyat yapıldı)", k["ciro"] > 0, f"{k['ciro']} TL")
    kontrol("üretim tonu > 0", k["uretim_ton"] > 0, f"{k['uretim_ton']} ton")
    kontrol("stok değeri > 0", k["stok_degeri"] > 0, f"{k['stok_degeri']} TL")
    kontrol("net pozisyon hesaplanabilir",
            abs(k["net_pozisyon"] - (k["alacak"] - k["borc"])) < 0.01)


# =================================================================== N: olay/kuyruk

def test_n_olay_kuyruk():
    baslik("N", "§4.1 Olay günlüğü, bildirim, outbox kuyruğu")
    kod, olay = cagir("/events")
    kontrol("olay günlüğü dolu", kod == 200 and olay["toplam"] > 5,
            f"{olay.get('toplam')} olay")
    if kod == 200:
        tipler = {o["tip"] for o in olay["kayitlar"]}
        kontrol("birden çok olay tipi", len(tipler) >= 4,
                ", ".join(sorted(tipler)[:6]))

    kod, bil = cagir("/notifications")
    kontrol("bildirimler var", kod == 200 and bil["toplam"] > 0,
            f"{bil.get('toplam')} bildirim")

    kod, ob = cagir("/outbox")
    kontrol("outbox kuyruğu var", kod == 200 and ob["toplam"] > 0,
            f"{ob.get('toplam')} kayıt")
    if kod == 200:
        kontrol("outbox durumu kuyrukta",
                any(o["durum"] == "kuyrukta" for o in ob["kayitlar"]))


# =================================================================== O: ekran doluluk

def test_o_ekranlar():
    baslik("O", "35 ekranın tamamı veriyle doluyor mu?")
    kod, d = cagir("/ekranlar")
    kontrol("ekran durumu alındı", kod == 200, f"kod={kod}")
    if kod != 200:
        return
    kontrol("35 ekran sayıldı", d["toplam"] == 35, f"{d['toplam']}")
    bos = [e for e in d["ekranlar"] if not e["dolu"]]
    kontrol("tüm ekranlar dolu", not bos,
            "boş: " + ", ".join(f"{e['no']} {e['ekran']}" for e in bos)
            if bos else f"{d['dolu']}/35")


# =================================================================== P: idempotency

def test_p_idempotency():
    baslik("P", "§4.1 Çift yazım engeli (clientId idempotency)")
    cid = f"IDEM-{RUN_ID}"
    kod, a = cagir("/satin-alma/talep", "POST", {
        "malzeme": "MAT-0001", "miktar": 100, "gerekce": "Idem test",
        "client_id": cid})
    kontrol("ilk istek kayıt açtı", kod == 200 and not a.get("_tekrar"),
            a.get("id", ""))
    kod, b = cagir("/satin-alma/talep", "POST", {
        "malzeme": "MAT-0001", "miktar": 100, "gerekce": "Idem test",
        "client_id": cid})
    kontrol("ikinci istek aynı kaydı döndürdü",
            kod == 200 and b.get("_tekrar") is True,
            b.get("id", ""))
    kontrol("aynı id", a.get("id") == b.get("id"))

    # Kaç kayıt oluştu
    kod, tl = cagir("/purchaseRequests")
    ayni = [x for x in tl["kayitlar"] if x.get("clientId") == cid]
    kontrol("tek kayıt oluştu", len(ayni) == 1, f"{len(ayni)} kayıt")


# =================================================================== main

def main() -> int:
    print("=" * 64)
    print("  ERP FONKSİYON TESTLERİ")
    print("  Doküman §4 (59 varlık) §5 (35 ekran) §6 (akışlar) §7 (hesaplar)")
    print("=" * 64)
    try:
        test_a_meta()
        test_b_hesaplar()
        test_c_tanimlar()
        test_d_satin_alma()
        test_e_uretim()
        test_f_homojenizasyon()
        test_g_stok()
        test_h_satis()
        test_i_sevkiyat()
        test_j_muhasebe()
        test_k_bakim()
        test_l_personel()
        test_m_kpi()
        test_n_olay_kuyruk()
        test_p_idempotency()
        test_o_ekranlar()
    except Exception as exc:  # noqa: BLE001
        print(f"\n  ✗ Beklenmeyen hata: {exc.__class__.__name__}: {exc}")
        import traceback
        traceback.print_exc()
        SONUC.append(("beklenmeyen hata", False, str(exc)))

    gecen = sum(1 for _, ok, _ in SONUC if ok)
    toplam = len(SONUC)
    print("\n" + "=" * 64)
    print(f"  SONUÇ: {gecen}/{toplam} test geçti")
    if gecen == toplam:
        print("  ✓ ERP'nin her fonksiyonu test edildi.")
    else:
        print("  ✗ Başarısız testler:")
        for ad, ok, ayrinti in SONUC:
            if not ok:
                print(f"     - {ad}" + (f" ({ayrinti})" if ayrinti else ""))
    print("=" * 64)
    return 0 if gecen == toplam else 1


if __name__ == "__main__":
    sys.exit(main())
