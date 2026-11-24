"""ERP hesap motorları — doküman §7'deki saf fonksiyonların karşılığı.

Bu modül **simülasyonun** hesap motorudur; senin ERP'ndeki fonksiyonların
aynısı değildir, aynı **sözleşmeyi** uygular. Amaç: ERP'nin ekranlarında,
raporlarında ve muhasebe fişlerinde kullandığı aritmetiği buradaki bilinen
sayılarla karşılaştırabilmen. Dokümanda verilen örnek sonuçlar
(doküman §7.1 tablosu) burada **test beklentisi** olarak kullanılıyor:

    6300 mm döküm  -> 423,29 kg
    6000 mm mamul  -> 403,13 kg
     300 mm kafa   ->  20,16 kg
       3 mm talaş  ->   0,202 kg

Saf fonksiyonlar: hiçbiri global durum okumaz/yazmaz, aynı girdi aynı çıktıyı
verir. Böylece aynı sayıyı ekranda, testte ve fişte kullanabilirsin.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

# ---------------------------------------------------------------- varsayılanlar

VARSAYILAN_CAP_MM = 178.0
VARSAYILAN_DOKUM_BOYU_MM = 6300.0
VARSAYILAN_MAMUL_BOYU_MM = 6000.0
VARSAYILAN_KAFA_MM = 300.0
VARSAYILAN_BICAK_MM = 3.0
VARSAYILAN_YOGUNLUK = 2700.0     # kg/m³ (alüminyum)
VARSAYILAN_KDV = 0.20
VARSAYILAN_TOLERANS = 0.02        # %2

# Hesap planı — doküman §7.3
HESAP_PLANI = {
    "100": "Kasa",
    "102": "Banka",
    "120": "Alıcılar",
    "150": "İlk Madde ve Malzeme",
    "153": "Ticari Mal",
    "191": "İndirilecek KDV",
    "320": "Satıcılar",
    "391": "Hesaplanan KDV",
    "600": "Yurt İçi Satışlar",
    "620": "Satılan Malın Maliyeti",
    "730": "Üretim Maliyeti",
    "740": "Genel Giderler",
}


def _yuvarla(x: float, n: int = 2) -> float:
    return round(float(x) + 0.0, n)


# ---------------------------------------------------------------- §7.1 kesim

def cylinder_mass_kg(cap_mm: float = VARSAYILAN_CAP_MM,
                     boy_mm: float = VARSAYILAN_DOKUM_BOYU_MM,
                     yogunluk: float = VARSAYILAN_YOGUNLUK,
                     adet: int = 1) -> float:
    """Silindir kütlesi (kg) — doküman §7.1 formülü.

    Kütle = π × (çap/2000)² × (uzunluk/1000) × yoğunluk × adet
    """
    if cap_mm <= 0 or boy_mm <= 0 or yogunluk <= 0 or adet <= 0:
        raise ValueError("çap, boy, yoğunluk ve adet pozitif olmalı")
    yaricap_m = cap_mm / 2000.0
    boy_m = boy_mm / 1000.0
    return math.pi * (yaricap_m ** 2) * boy_m * yogunluk * adet


def cutting_report(cap_mm: float = VARSAYILAN_CAP_MM,
                   dokum_boyu_mm: float = VARSAYILAN_DOKUM_BOYU_MM,
                   mamul_boyu_mm: float = VARSAYILAN_MAMUL_BOYU_MM,
                   kafa_mm: float = VARSAYILAN_KAFA_MM,
                   bicak_mm: float = VARSAYILAN_BICAK_MM,
                   yogunluk: float = VARSAYILAN_YOGUNLUK,
                   kafa_adedi: int = 2,
                   kesim_sayisi: int = 2,
                   tolerans: float = VARSAYILAN_TOLERANS,
                   tonaj_kg: Optional[float] = None) -> dict:
    """Kafa, talaş, fire, net biyet — tek raporda (doküman §7.2 `cuttingReport`).

    `tonaj_kg` verilirse geometriden beklenen tonajla karşılaştırılır
    (`geometryCheck`, varsayılan tolerans %2).
    """
    dokum = cylinder_mass_kg(cap_mm, dokum_boyu_mm, yogunluk, 1)
    mamul = cylinder_mass_kg(cap_mm, mamul_boyu_mm, yogunluk, 1)
    kafa_birim = cylinder_mass_kg(cap_mm, kafa_mm, yogunluk, 1)
    talas_birim = cylinder_mass_kg(cap_mm, bicak_mm, yogunluk, 1)

    kafa_toplam = kafa_birim * kafa_adedi
    talas_toplam = talas_birim * kesim_sayisi
    net = dokum - kafa_toplam - talas_toplam
    fire = dokum - net          # kafa + talaş

    # Bıçak döküm boyunun içinde sayılırsa gerçek kafa payı kısalır (§7.1).
    gercek_kafa_mm = dokum_boyu_mm - mamul_boyu_mm - bicak_mm

    rapor = {
        "cap_mm": cap_mm,
        "dokum_boyu_mm": dokum_boyu_mm,
        "dokum_kg": _yuvarla(dokum),
        "mamul_kg": _yuvarla(mamul),
        "kafa_mm": kafa_mm,
        "kafa_birim_kg": _yuvarla(kafa_birim, 3),
        "kafa_adedi": kafa_adedi,
        "kafa_toplam_kg": _yuvarla(kafa_toplam),
        "bicak_mm": bicak_mm,
        "talas_birim_kg": _yuvarla(talas_birim, 3),
        "kesim_sayisi": kesim_sayisi,
        "talas_toplam_kg": _yuvarla(talas_toplam),
        "fire_kg": _yuvarla(fire),
        "fire_orani_yuzde": _yuvarla(fire / dokum * 100.0),
        "net_biyet_kg": _yuvarla(net),
        "net_biyet_ton": _yuvarla(net / 1000.0, 3),
        "gercek_kafa_payi_mm": _yuvarla(gercek_kafa_mm, 1),
        "yogunluk": yogunluk,
    }
    if tonaj_kg is not None:
        rapor["geometry_check"] = geometry_check(tonaj_kg, net, tolerans)
    return rapor


def geometry_check(kayitli_kg: float, beklenen_kg: float,
                   tolerans: float = VARSAYILAN_TOLERANS) -> dict:
    """Kayıtlı tonaj ile geometriden beklenen tonajı karşılaştırır (§7.2)."""
    if beklenen_kg <= 0:
        raise ValueError("beklenen tonaj pozitif olmalı")
    fark = kayitli_kg - beklenen_kg
    oran = abs(fark) / beklenen_kg
    return {
        "kayitli_kg": _yuvarla(kayitli_kg),
        "beklenen_kg": _yuvarla(beklenen_kg),
        "fark_kg": _yuvarla(fark),
        "fark_yuzde": _yuvarla(oran * 100.0),
        "tolerans_yuzde": _yuvarla(tolerans * 100.0),
        "uygun": oran <= tolerans,
    }


def mass_balance_chain(olaylar: Iterable[float]) -> dict:
    """21 → 18 → 17 → 14 ton gibi ardışık olaylardan yürüyen bakiye (§7.2).

    `olaylar` birbirini izleyen kütle değerleridir (kg). Her adımda kayıp
    hesaplanır; zincir sonunda toplam kayıp ve denge farkı verilir.
    """
    degerler = [float(v) for v in olaylar]
    if not degerler:
        raise ValueError("en az bir olay gerekli")
    adimlar = []
    for onceki, sonraki in zip(degerler, degerler[1:]):
        adimlar.append({
            "onceki_kg": _yuvarla(onceki),
            "sonraki_kg": _yuvarla(sonraki),
            "kayip_kg": _yuvarla(onceki - sonraki),
            "kayip_yuzde": _yuvarla((onceki - sonraki) / onceki * 100.0, 3)
            if onceki else 0.0,
        })
    toplam_kayip = degerler[0] - degerler[-1]
    return {
        "baslangic_kg": _yuvarla(degerler[0]),
        "bitis_kg": _yuvarla(degerler[-1]),
        "adimlar": adimlar,
        "toplam_kayip_kg": _yuvarla(toplam_kayip),
        "toplam_kayip_yuzde": _yuvarla(toplam_kayip / degerler[0] * 100.0, 3)
        if degerler[0] else 0.0,
        "denge": _yuvarla(degerler[0] - toplam_kayip) == _yuvarla(degerler[-1]),
    }


# ---------------------------------------------------------------- §7.2 bakım

def maintenance_status(kullanilan: float, limit: float) -> dict:
    """Yağ/bıçak kullanımını limite oranlar (§7.2 `maintenanceStatus`).

    Seviyeler: `normal` (< %80), `yaklasiyor` (%80–99), `esik_doldu` (>= %100)
    """
    if limit <= 0:
        raise ValueError("limit pozitif olmalı")
    oran = kullanilan / limit
    if oran >= 1.0:
        seviye = "esik_doldu"
    elif oran >= 0.8:
        seviye = "yaklasiyor"
    else:
        seviye = "normal"
    return {
        "kullanilan": _yuvarla(kullanilan, 1),
        "limit": _yuvarla(limit, 1),
        "kalan": _yuvarla(max(0.0, limit - kullanilan), 1),
        "yuzde": _yuvarla(oran * 100.0, 1),
        "seviye": seviye,
        "bakim_gerekli": oran >= 1.0,
    }


def duration_check(planlanan_dk: float, gerceklesen_dk: float) -> dict:
    """Planlanan ve gerçekleşen süreyi karşılaştırır (§7.2 `durationCheck`)."""
    fark = gerceklesen_dk - planlanan_dk
    return {
        "planlanan_dk": _yuvarla(planlanan_dk, 1),
        "gerceklesen_dk": _yuvarla(gerceklesen_dk, 1),
        "fark_dk": _yuvarla(fark, 1),
        "asildi": fark > 0,
        "sapma_yuzde": _yuvarla(fark / planlanan_dk * 100.0, 2)
        if planlanan_dk else 0.0,
    }


# ---------------------------------------------------------------- §7.2/7.3 muhasebe

def amounts(net: float, kdv_orani: float = VARSAYILAN_KDV) -> dict:
    """Net tutardan KDV ve genel toplam (§7.2 `amounts`)."""
    kdv = net * kdv_orani
    return {
        "net": _yuvarla(net),
        "kdv_orani": kdv_orani,
        "kdv": _yuvarla(kdv),
        "genel_toplam": _yuvarla(net + kdv),
    }


def sum_lines(satirlar: list[dict]) -> dict:
    """Fiş satırlarının borç/alacak toplamı (§7.2 `sumLines`)."""
    borc = sum(float(s.get("borc", 0) or 0) for s in satirlar)
    alacak = sum(float(s.get("alacak", 0) or 0) for s in satirlar)
    return {"borc": _yuvarla(borc), "alacak": _yuvarla(alacak),
            "fark": _yuvarla(borc - alacak)}


def is_balanced(satirlar: list[dict], tolerans: float = 0.01) -> bool:
    """Borç = alacak mı (§7.2 `isBalanced`)."""
    return abs(sum_lines(satirlar)["fark"]) <= tolerans


def build_entry(aciklama: str, satirlar: list[dict],
                tarih: Optional[str] = None,
                source_id: Optional[str] = None,
                tutar: Optional[dict] = None) -> dict:
    """Dengeli borç/alacak fişi kurar (§7.2 `buildEntry`).

    Dengesiz fiş `balanced: false` ile işaretlenir — sessizce kaydedilmez.
    """
    temiz = []
    for s in satirlar:
        hesap = str(s.get("hesap", ""))
        temiz.append({
            "hesap": hesap,
            "hesap_adi": HESAP_PLANI.get(hesap, "?"),
            "borc": _yuvarla(s.get("borc", 0) or 0),
            "alacak": _yuvarla(s.get("alacak", 0) or 0),
        })
    toplam = sum_lines(temiz)
    return {
        "aciklama": aciklama,
        "tarih": tarih,
        "source_id": source_id,
        "satirlar": temiz,
        "toplam_borc": toplam["borc"],
        "toplam_alacak": toplam["alacak"],
        "balanced": abs(toplam["fark"]) <= 0.01,
        "fark": toplam["fark"],
        "tutar": tutar or {"net": toplam["alacak"] - 0.0,
                           "kdv": 0.0,
                           "genel_toplam": toplam["borc"]},
    }


def sales_entry(net: float, kdv_orani: float = VARSAYILAN_KDV,
                aciklama: str = "Satış faturası",
                source_id: Optional[str] = None) -> dict:
    """Satış faturası fişi: 120 borç; 600 ve 391 alacak (§7.2 `salesEntry`)."""
    t = amounts(net, kdv_orani)
    return build_entry(aciklama, [
        {"hesap": "120", "borc": t["genel_toplam"]},
        {"hesap": "600", "alacak": t["net"]},
        {"hesap": "391", "alacak": t["kdv"]},
    ], source_id=source_id, tutar=t)


def purchase_entry(net: float, kdv_orani: float = VARSAYILAN_KDV,
                   aciklama: str = "Alış faturası",
                   source_id: Optional[str] = None) -> dict:
    """Alış faturası fişi: 150 ve 191 borç; 320 alacak (§7.2 `purchaseEntry`)."""
    t = amounts(net, kdv_orani)
    return build_entry(aciklama, [
        {"hesap": "150", "borc": t["net"]},
        {"hesap": "191", "borc": t["kdv"]},
        {"hesap": "320", "alacak": t["genel_toplam"]},
    ], source_id=source_id, tutar=t)


def trial_balance(fisler: Iterable[dict]) -> dict:
    """Hesap bazında borç, alacak ve bakiye mizanı (§7.2 `trialBalance`)."""
    hesaplar: dict[str, dict] = {}
    for fis in fisler:
        for s in fis.get("satirlar", []):
            hesap = s["hesap"]
            h = hesaplar.setdefault(hesap, {
                "hesap": hesap,
                "hesap_adi": HESAP_PLANI.get(hesap, "?"),
                "borc": 0.0, "alacak": 0.0,
            })
            h["borc"] += float(s.get("borc", 0) or 0)
            h["alacak"] += float(s.get("alacak", 0) or 0)
    satirlar = []
    for h in sorted(hesaplar.values(), key=lambda x: x["hesap"]):
        bakiye = h["borc"] - h["alacak"]
        satirlar.append({
            "hesap": h["hesap"],
            "hesap_adi": h["hesap_adi"],
            "borc": _yuvarla(h["borc"]),
            "alacak": _yuvarla(h["alacak"]),
            "bakiye": _yuvarla(bakiye),
            "taraf": "BORC" if bakiye > 0 else ("ALACAK" if bakiye < 0 else "SIFIR"),
        })
    tb = sum_lines([{"borc": s["borc"], "alacak": s["alacak"]} for s in satirlar])
    return {
        "satirlar": satirlar,
        "toplam_borc": tb["borc"],
        "toplam_alacak": tb["alacak"],
        "denk": abs(tb["fark"]) <= 0.01,
    }


# ---------------------------------------------------------------- §7.4 maliyet

MALIYET_KALEMLERI = ("hammadde", "enerji", "sarf", "iscilik", "fire")


def lot_cost(hammadde: float = 0.0, enerji: float = 0.0, sarf: float = 0.0,
             iscilik: float = 0.0, fire: float = 0.0,
             net_ton: float = 1.0) -> dict:
    """Döküm kodu maliyeti (§7.4 `lotCost`).

    Beş kalem toplanır; ton ve kg başı maliyet verilir.
    """
    if net_ton <= 0:
        raise ValueError("net ton pozitif olmalı")
    kalemler = {"hammadde": hammadde, "enerji": enerji, "sarf": sarf,
                "iscilik": iscilik, "fire": fire}
    toplam = sum(kalemler.values())
    return {
        "kalemler": {k: _yuvarla(v) for k, v in kalemler.items()},
        "toplam": _yuvarla(toplam),
        "net_ton": _yuvarla(net_ton, 3),
        "ton_maliyet": _yuvarla(toplam / net_ton),
        "kg_maliyet": _yuvarla(toplam / (net_ton * 1000.0), 4),
        "kalem_paylari": {
            k: _yuvarla(v / toplam * 100.0, 1) if toplam else 0.0
            for k, v in kalemler.items()
        },
    }


def sales_margin(gelir: float, maliyet: float) -> dict:
    """Satış geliri ile üretim maliyetinden brüt kâr ve marj (§7.2)."""
    kar = gelir - maliyet
    return {
        "gelir": _yuvarla(gelir),
        "maliyet": _yuvarla(maliyet),
        "brut_kar": _yuvarla(kar),
        "marj_yuzde": _yuvarla(kar / gelir * 100.0, 2) if gelir else 0.0,
        "karli": kar > 0,
    }


def credit_check(limit: float, kullanilan: float, yeni_tutar: float) -> dict:
    """Müşteri limiti, kullanılan bakiye ve yeni sipariş tutarı (§7.2).

    Sipariş kabul edilirse `onay: true`; limit aşılırsa `onay: false` ve
    `asilan` tutar bildirilir. Bu, ERP'nin sipariş ekranında uygulaması
    gereken kuralın aynısıdır.
    """
    toplam = kullanilan + yeni_tutar
    kalan = limit - toplam
    return {
        "limit": _yuvarla(limit),
        "kullanilan": _yuvarla(kullanilan),
        "yeni_tutar": _yuvarla(yeni_tutar),
        "yeni_bakiye": _yuvarla(toplam),
        "kalan_limit": _yuvarla(max(0.0, kalan)),
        "asilan": _yuvarla(max(0.0, -kalan)),
        "onay": toplam <= limit,
        "kullanim_yuzde": _yuvarla(toplam / limit * 100.0, 1) if limit else 0.0,
    }


def kpi_snapshot(ciro: float = 0.0, alacak: float = 0.0, borc: float = 0.0,
                 acik_siparis: int = 0, zamaninda_teslim_orani: float = 0.0,
                 uretim_ton: float = 0.0, fire_ton: float = 0.0,
                 butce_plan: float = 0.0, butce_gercek: float = 0.0) -> dict:
    """Panel KPI'ları (§7.2 `kpiSnapshot`)."""
    fire_orani = (fire_ton / uretim_ton * 100.0) if uretim_ton else 0.0
    butce_kullanim = (butce_gercek / butce_plan * 100.0) if butce_plan else 0.0
    return {
        "ciro": _yuvarla(ciro),
        "alacak": _yuvarla(alacak),
        "borc": _yuvarla(borc),
        "net_pozisyon": _yuvarla(alacak - borc),
        "acik_siparis": acik_siparis,
        "zamaninda_teslim_yuzde": _yuvarla(zamaninda_teslim_orani, 1),
        "uretim_ton": _yuvarla(uretim_ton, 2),
        "fire_ton": _yuvarla(fire_ton, 3),
        "fire_orani_yuzde": _yuvarla(fire_orani, 2),
        "butce_plan": _yuvarla(butce_plan),
        "butce_gercek": _yuvarla(butce_gercek),
        "butce_kullanim_yuzde": _yuvarla(butce_kullanim, 1),
    }


def posting_effects(belge_tipi: str, tutar: float,
                    kdv_orani: float = VARSAYILAN_KDV,
                    net_ton: float = 0.0, ton_maliyet: float = 0.0) -> dict:
    """Onaylanan belgeden doğacak kayıtların listesi (§7.2 `postingEffects`).

    `belge_tipi`: `satis`, `alis`, `sevkiyat`, `uretim`, `sayim`.
    Fonksiyon yalnızca **ne doğacağını** söyler; yazmayı çağıran taraf yapar.
    Doküman §6.3'teki "tek kayıt, çok etki" tablosunun fonksiyon hâlidir.
    """
    t = amounts(tutar, kdv_orani)
    if belge_tipi == "satis":
        kayitlar = ["stok_cikis", "satis_faturasi", "muhasebe_fisi",
                    "cari_hareket", "bildirim", "outbox", "olay"]
        fis = sales_entry(tutar, kdv_orani)
    elif belge_tipi == "sevkiyat":
        kayitlar = ["stok_cikis", "satis_faturasi", "muhasebe_fisi",
                    "cari_hareket", "maliyet_yansimasi", "bildirim",
                    "outbox", "olay"]
        fis = sales_entry(tutar, kdv_orani)
    elif belge_tipi == "alis":
        kayitlar = ["stok_giris", "alis_faturasi", "muhasebe_fisi",
                    "cari_hareket", "fiyat_gecmisi", "olay"]
        fis = purchase_entry(tutar, kdv_orani)
    elif belge_tipi == "uretim":
        kayitlar = ["mamul_stok", "yan_urun", "maliyet_kaydi", "olay"]
        fis = build_entry("Üretim maliyeti", [
            {"hesap": "730", "borc": tutar},
            {"hesap": "150", "alacak": tutar},
        ])
    elif belge_tipi == "sayim":
        kayitlar = ["stok_duzeltme", "muhasebe_fisi", "denetim_izi", "olay"]
        fis = build_entry("Sayım düzeltmesi", [
            {"hesap": "150", "borc": max(tutar, 0)},
            {"hesap": "740", "alacak": abs(min(tutar, 0)) or max(tutar, 0)},
        ])
    else:
        raise ValueError(f"bilinmeyen belge tipi: {belge_tipi}")

    sonuc = {
        "belge_tipi": belge_tipi,
        "tutar": t,
        "uretilen_kayitlar": kayitlar,
        "kayit_sayisi": len(kayitlar),
        "fis": fis,
        "fis_dengeli": fis["balanced"],
    }
    if net_ton and ton_maliyet:
        sonuc["maliyet_yansimasi"] = _yuvarla(net_ton * ton_maliyet)
        sonuc["brut_kar"] = sales_margin(t["net"], sonuc["maliyet_yansimasi"])
    return sonuc


# ---------------------------------------------------------------- doğrulama

def self_check() -> dict:
    """Doküman §7.1'deki sayıları yeniden üretir; sapma varsa bildirir."""
    dokum = cylinder_mass_kg(178, 6300)
    mamul = cylinder_mass_kg(178, 6000)
    kafa = cylinder_mass_kg(178, 300)
    talas = cylinder_mass_kg(178, 3)
    return {
        "dokum_6300_kg": _yuvarla(dokum),
        "mamul_6000_kg": _yuvarla(mamul),
        "kafa_300_kg": _yuvarla(kafa),
        "talas_3_kg": _yuvarla(talas, 3),
        "dokuman_bekliyor": {"dokum_6300_kg": 423.29, "mamul_6000_kg": 403.13,
                             "kafa_300_kg": 20.16, "talas_3_kg": 0.202},
        "uyumlu": (
            abs(dokum - 423.29) < 0.02
            and abs(mamul - 403.13) < 0.02
            and abs(kafa - 20.16) < 0.02
            and abs(talas - 0.202) < 0.001
        ),
    }
