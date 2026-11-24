"""ERP iş akışı motoru — doküman §4 (59 varlık) ve §6 (uçtan uca akışlar).

Bu modül simülasyonun **ERP tarafı**dır: fırın simülasyonunun yanında, senin
ERP'ndeki ticari/operasyonel zinciri taklit eder. Amaç, ERP'ni bu sisteme
bağlayıp **her fonksiyonu** gerçek veriyle sınaman:

    satın alma → mal kabul → stok → üretim (reçete/lot/aşama)
        → kalite/fire → maliyet → satış siparişi → sevkiyat (2 onay)
        → fatura + fiş + cari + stok çıkışı + maliyet yansıması

Tasarım ilkeleri (doküman §4.1'den birebir):

* **Tek kimlik:** Bir sevkiyat, faturası, fişi ve stok hareketi aynı
  `sourceId` ile bağlanır.
* **Çift yazım engeli:** Aynı `clientId` ikinci kez gelirse yeni kayıt
  üretilmez; işlem idempotent.
* **Silme yerine doğrulama:** Kayıt silinmez; düzeltme/gerekçe eklenir.
* **Fabrika ayrımı:** Her kayıt `plantId` taşır.
* **Kalite etiketi:** Sensör verisi GOOD/SIMULATED/STALE/BAD.

Depolama: tek JSON dosyası (`erp_sim_data.json`). Prototip ölçeğinde
yeterli; gerçek ERP'ye geçerken bu sınıfın arkasına PostgreSQL koyabilirsin —
arayüz (REST) aynı kalır.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Optional

from simulator import erp_math as M

VARSAYILAN_DOSYA = os.environ.get("ERP_DATA_FILE", "erp_sim_data.json")

# Kayıt kimliklerinde kullanılan kısa önekler (PURCHA-0001 yerine TLP-0001).
ONEKLER = {
    "purchaseRequests": "TLP", "purchaseQuotes": "TKF", "purchaseOrders": "SAE",
    "receipts": "MKB", "priceHistory": "FYT", "lots": "LOT", "movements": "HRK",
    "byProductFates": "YAN", "crusher": "KRC", "costRecords": "MLY",
    "salesOrders": "SSP", "reservations": "REZ", "shipments": "SVK",
    "invoices": "FTR", "journalEntries": "FIS", "payments": "ODM",
    "periodClosures": "DKN", "quotations": "TKF2", "stockCounts": "SYM",
    "maintenanceEvents": "BKM", "notifications": "BIL", "outbox": "OBX",
    "events": "OLY", "customers": "MUS", "suppliers": "TED",
    "materials": "MAL", "machines": "MCH", "recipes": "RCP", "users": "PRS",
    "telemetry": "TLM", "qualityLabels": "QLT", "homogenizationBatches": "HOM",
    "coolingBatches": "SOG", "accounts": "HSP", "budgets": "BTC",
    "warehouses": "DEP", "pdks": "PDK",
}

# Doküman §4: 59 varlık. Anahtar = koleksiyon adı.
VARLIKLAR = [
    # Fabrika ve makine
    "plants", "machines", "machineTypes", "furnaces", "castingPaths",
    "plcConnections", "plcTags", "machineAliases",
    # Üretim
    "recipes", "lots", "signalStates", "oilRules", "bladeRules",
    "maintenanceEvents", "homogenizationRecipes", "homogenizationBatches",
    "coolingBatches", "byProductFates",
    # Satın alma
    "materials", "categories", "units", "suppliers", "purchaseRequests",
    "purchaseQuotes", "purchaseOrders", "priceHistory",
    # Stok
    "receipts", "crusher", "movements", "stockCounts", "warehouses",
    "reservations",
    # Ticari
    "customers", "quotations", "salesOrders", "invoices",
    # Finans
    "accounts", "journalEntries", "payments", "costRecords", "budgets",
    "periodClosures",
    # Sevkiyat ve arşiv
    "shipments", "events",
    # Yönetim ve sistem
    "users", "moduleRegistry", "plantModules", "profilePackages",
    "adapterContracts", "setupDrafts", "vendorUpdates", "settings",
    "notifications", "outbox", "inboxQueue", "activity", "integrationRules",
    # Doküman §4'te sayılan ama satırda adı geçmeyen iki varlık:
    "telemetry", "qualityLabels",
]

# Doküman §9.2: 15 modül
MODULLER = [
    {"id": "core", "ad": "Çekirdek", "ekranlar": ["Panel", "Bildirimler", "Ayarlar"], "kosul": "her fabrikada"},
    {"id": "purchasing", "ad": "Satın Alma", "ekranlar": ["Malzeme", "Emirler", "Fiyatlar", "Tedarikçiler", "Talepler"], "kosul": None},
    {"id": "stock", "ad": "Hammadde & Stok", "ekranlar": ["Stok", "Mal Kabul", "Kırıcı", "Hareketler"], "kosul": None},
    {"id": "production", "ad": "Üretim", "ekranlar": ["Üretim Akışı", "Reçeteler", "Partiler", "Olaylar"], "kosul": "en az bir ergitme ocağı"},
    {"id": "machines", "ad": "Makine Parkı", "ekranlar": ["Makineler", "Yollar", "Kesim", "Bakım"], "kosul": None},
    {"id": "rotary", "ad": "Döner Ocak / Cüruf", "ekranlar": [], "kosul": "döner ocak varsa"},
    {"id": "plc", "ad": "PLC Durum", "ekranlar": ["PLC Durum"], "kosul": "fabrika modu PLC ise"},
    {"id": "sales", "ad": "Satış & Müşteri", "ekranlar": ["Satış", "Müşteriler"], "kosul": None},
    {"id": "accounting", "ad": "Muhasebe & Maliyet", "ekranlar": ["Muhasebe", "Maliyet"], "kosul": None},
    {"id": "warehouse", "ad": "Depo & Sayım", "ekranlar": ["Depo"], "kosul": None},
    {"id": "personnel", "ad": "Personel & Vardiya", "ekranlar": ["Personel"], "kosul": "bordro hariç"},
    {"id": "shipping", "ad": "Sevkiyat", "ekranlar": ["Sevkiyat", "Arşiv"], "kosul": None},
    {"id": "reporting", "ad": "Raporlama", "ekranlar": ["Raporlar"], "kosul": None},
    {"id": "integration", "ad": "Entegrasyon", "ekranlar": ["Entegrasyon Matrisi", "Simülasyon"], "kosul": None},
    {"id": "admin", "ad": "Merkezi Yönetim", "ekranlar": ["Sihirbaz", "Modül Kaydı", "Merkezi Yönetim"], "kosul": "yalnızca geliştirici ekibi"},
]

# Doküman §7.3 hesap planı
HESAPLAR = [
    {"kod": "100", "ad": "Kasa", "tip": "AKTIF"},
    {"kod": "102", "ad": "Banka", "tip": "AKTIF"},
    {"kod": "120", "ad": "Alıcılar", "tip": "AKTIF"},
    {"kod": "150", "ad": "İlk Madde ve Malzeme", "tip": "AKTIF"},
    {"kod": "153", "ad": "Ticari Mal", "tip": "AKTIF"},
    {"kod": "191", "ad": "İndirilecek KDV", "tip": "AKTIF"},
    {"kod": "320", "ad": "Satıcılar", "tip": "PASIF"},
    {"kod": "391", "ad": "Hesaplanan KDV", "tip": "PASIF"},
    {"kod": "600", "ad": "Yurt İçi Satışlar", "tip": "GELIR"},
    {"kod": "620", "ad": "Satılan Malın Maliyeti", "tip": "GIDER"},
    {"kod": "730", "ad": "Üretim Maliyeti", "tip": "GIDER"},
    {"kod": "740", "ad": "Genel Giderler", "tip": "GIDER"},
]

# Doküman §5: üretim akışı 8 aşama
ASAMALAR = ["Ergitme", "Döküm", "Testere", "Homojenizasyon",
            "Soğutma", "Paketleme", "Mamul Stok", "Sevkiyat"]

# Doküman §5: 35 ekran
EKRANLAR = [
    ("1", "Panel", "Genel"), ("2", "Malzeme Tanımları", "Satın Alma"),
    ("3", "Satın Alma Emirleri", "Satın Alma"), ("4", "Fiyat Takibi", "Satın Alma"),
    ("5", "Tedarikçiler", "Satın Alma"), ("6", "Talep & Teklif Akışı", "Satın Alma"),
    ("7", "Stok Durumu", "Hammadde & Stok"), ("8", "Mal Kabul", "Hammadde & Stok"),
    ("9", "Kırıcı & Fire", "Hammadde & Stok"), ("10", "Stok Hareketleri", "Hammadde & Stok"),
    ("11", "Üretim Akışı", "Üretim"), ("12", "Reçeteler", "Üretim"),
    ("13", "Homojenizasyon Partisi", "Üretim"), ("14", "Olay & Arşiv", "Üretim"),
    ("15", "Makine Parkı", "Makine & Kurulum"), ("16", "Döküm Yolları", "Makine & Kurulum"),
    ("17", "Kesim Hesap Motoru", "Makine & Kurulum"), ("18", "Yağ & Bakım", "Makine & Kurulum"),
    ("19", "PLC Durum", "Makine & Kurulum"), ("20", "Satış Siparişleri", "Ticari & Finans"),
    ("21", "Müşteriler & Cari", "Ticari & Finans"), ("22", "Muhasebe & Fişler", "Ticari & Finans"),
    ("23", "Maliyet & Kârlılık", "Ticari & Finans"), ("24", "Depo, Rezervasyon & Sayım", "Depolama & Personel"),
    ("25", "Personel & Vardiya", "Depolama & Personel"), ("26", "Sevkiyat & Onaylar", "Sevkiyat"),
    ("27", "Arşiv", "Sevkiyat"), ("28", "Raporlar & İstatistik", "Raporlama"),
    ("29", "Entegrasyon Matrisi", "Entegrasyon"), ("30", "Simülasyon Bağlantısı", "Entegrasyon"),
    ("31", "Saha Kurulum Sihirbazı", "Yönetim"), ("32", "Modül Kaydı", "Yönetim"),
    ("33", "Merkezi Yönetim", "Yönetim"), ("34", "Bildirimler & Kuyruk", "Sistem"),
    ("35", "Ayarlar", "Sistem"),
]


class ErpHatası(Exception):
    """İş kuralı ihlali. HTTP katmanı bunu 400'e çevirir."""


class ErpModel:
    """59 varlıklı ERP veri modeli + iş akışları."""

    def __init__(self, path: str = VARSAYILAN_DOSYA):
        self.path = path
        self.lock = threading.RLock()
        self.data: dict[str, list] = {k: [] for k in VARLIKLAR}
        self.data["settings"] = [{
            "id": "settings-1",
            "plantId": "PLANT-1",
            "sirket": "Örnek Alüminyum A.Ş.",
            "para_birimi": "TRY",
            "kdv_orani": M.VARSAYILAN_KDV,
            "tema": "koyu",
            "fire_tolerans_yuzde": 3.0,
            "createdAt": time.time(),
        }]
        self._sayaclar: dict[str, int] = {}
        self._seed_modu = False
        self._yukle()

    # ------------------------------------------------------------ depolama

    def _yukle(self) -> None:
        if not os.path.exists(self.path):
            self._seed()
            self._kaydet()
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                yuklenen = json.load(fh)
            for k in VARLIKLAR:
                if k in yuklenen:
                    self.data[k] = yuklenen[k]
            self._sayaclar = yuklenen.get("_sayaclar", {})
        except (json.JSONDecodeError, OSError):
            self._seed()
            self._kaydet()

    def _kaydet(self) -> None:
        # RLock: _ekle() içinden çağrıldığı için yeniden giriş gerekir.
        with self.lock:
            gecici = self.path + ".tmp"
            with open(gecici, "w", encoding="utf-8") as fh:
                json.dump({**self.data, "_sayaclar": self._sayaclar}, fh,
                          ensure_ascii=False, indent=1)
            os.replace(gecici, self.path)

    def sifirla(self) -> None:
        """Demo verisini sıfırlar (doküman §5 ekran 35: 'demo verisini sıfırlama')."""
        with self.lock:
            self.data = {k: [] for k in VARLIKLAR}
            self.data["settings"] = [{
                "id": "settings-1", "plantId": "PLANT-1",
                "sirket": "Örnek Alüminyum A.Ş.", "para_birimi": "TRY",
                "kdv_orani": M.VARSAYILAN_KDV, "tema": "koyu",
                "fire_tolerans_yuzde": 3.0, "createdAt": time.time(),
            }]
            self._sayaclar = {}
            self._seed()
            self._kaydet()

    # ------------------------------------------------------------ yardımcılar

    def _id(self, onek: str) -> str:
        with self.lock:
            n = self._sayaclar.get(onek, 0) + 1
            self._sayaclar[onek] = n
        return f"{onek}-{n:04d}"

    def _ekle(self, koleksiyon: str, kayit: dict, client_id: Optional[str] = None) -> dict:
        """Kayıt ekler; `client_id` verilmişse çift yazımı engeller (§4.1)."""
        with self.lock:
            if client_id:
                for mevcut in self.data[koleksiyon]:
                    if mevcut.get("clientId") == client_id:
                        # Idempotent: aynı istek ikinci kez geldi.
                        mevcut = dict(mevcut)
                        mevcut["_tekrar"] = True
                        return mevcut
                kayit["clientId"] = client_id
            kayit.setdefault("id", self._id(ONEKLER.get(koleksiyon, koleksiyon[:4].upper())))
            kayit.setdefault("createdAt", time.time())
            kayit.setdefault("updatedAt", kayit["createdAt"])
            kayit.setdefault("plantId", "PLANT-1")
            self.data[koleksiyon].append(kayit)
            # Kalıcılık: her yazma diske iner. Prototip ölçeğinde yeterli;
            # gerçek ERP'de burada transaction commit olur.
            # Seed sırasında tek tek yazmıyoruz (yüzlerce kayıt yavaşlatırdı).
            if not self._seed_modu:
                self._kaydet()
            return kayit

    def _bul(self, koleksiyon: str, kid: str) -> Optional[dict]:
        for k in self.data[koleksiyon]:
            if k.get("id") == kid:
                return k
        return None

    def _zorunlu(self, koleksiyon: str, kid: str, ad: str) -> dict:
        k = self._bul(koleksiyon, kid)
        if not k:
            raise ErpHatası(f"{ad} bulunamadı: {kid}")
        return k

    def _olay(self, tip: str, aciklama: str, ref: Optional[str] = None) -> dict:
        return self._ekle("events", {
            "tip": tip, "aciklama": aciklama, "kaynakId": ref,
            "kullanici": "simulasyon",
        })

    def _bildir(self, baslik: str, metin: str, seviye: str = "bilgi") -> dict:
        return self._ekle("notifications", {
            "baslik": baslik, "metin": metin, "seviye": seviye, "okundu": False,
        })

    def _outbox(self, kanal: str, alici: str, konu: str, icerik: str) -> dict:
        return self._ekle("outbox", {
            "kanal": kanal, "alici": alici, "konu": konu, "icerik": icerik,
            "durum": "kuyrukta", "deneme": 0,
        })

    def _hareket(self, malzeme: str, tip: str, miktar: float, birim: str,
                 depo: str, kaynak: str, lot: Optional[str] = None) -> dict:
        """Stok hareketi (§5 ekran 10). `tip`: GIRIS / CIKIS / DUZELTME."""
        return self._ekle("movements", {
            "malzeme": malzeme, "tip": tip, "miktar": miktar, "birim": birim,
            "depo": depo, "kaynakBelge": kaynak, "lot": lot,
            "kullanici": "simulasyon",
        })

    def _stok_miktar(self, malzeme: str) -> float:
        toplam = 0.0
        for h in self.data["movements"]:
            if h.get("malzeme") != malzeme:
                continue
            if h["tip"] == "GIRIS":
                toplam += h["miktar"]
            elif h["tip"] == "CIKIS":
                toplam -= h["miktar"]
            else:
                toplam += h["miktar"]      # DUZELTME: + veya -
        return round(toplam, 3)

    # ------------------------------------------------------------ seed (§4)

    def _seed(self) -> None:
        """Dokümana uygun gerçekçi başlangıç verisi."""
        p = "PLANT-1"
        self.data["plants"] = [{
            "id": p, "kod": "ALB-01", "ad": "Örnek Alüminyum Dökümhanesi",
            "sehir": "İstanbul", "mod": "PLC", "aktif": True,
            "createdAt": time.time(),
        }]

        # Birimler, kategoriler
        for i, (kod, ad) in enumerate([
            ("KG", "Kilogram"), ("TON", "Ton"), ("AD", "Adet"),
            ("LT", "Litre"), ("MT", "Metre"),
        ], 1):
            self.data["units"].append({"id": f"UNT-{i:04d}", "kod": kod,
                                       "ad": ad, "plantId": p})
        for i, ad in enumerate(["Alüminyum Hurda", "Ana Metal", "Yardımcı Malzeme",
                                "Sarf Malzeme", "Enerji"], 1):
            self.data["categories"].append({"id": f"CAT-{i:04d}", "ad": ad,
                                            "plantId": p})

        # Makine tipleri (§4) + 20 makine (§5 ekran 15)
        tipler = [
            ("MT-ERG", "Ergitme Ocağı", "ERGITME"),
            ("MT-HOM", "Homojenizasyon Fırını", "HOMOJENIZASYON"),
            ("MT-YAS", "Yaşlandırma Fırını", "YASLANDIRMA"),
            ("MT-TAB", "Döküm Tablası", "DOKUM"),
            ("MT-TES", "Testere", "TESTERE"),
            ("MT-PAK", "Paketleme", "PAKETLEME"),
        ]
        for kod, ad, tip in tipler:
            self.data["machineTypes"].append({
                "id": kod, "ad": ad, "kod": tip, "plantId": p,
                "parametreler": {"sicaklik_uyari": 800, "sicaklik_kritik": 850},
            })
        makineler = [
            ("MCH-01", "Ergitme Ocağı 1", "MT-ERG", 14.0, "PLC", True),
            ("MCH-02", "Yaşlandırma Fırını", "MT-YAS", 6.0, "PLC", True),
            ("MCH-10", "Homojenizasyon Fırını", "MT-HOM", 8.0, "PLC", True),
            ("MCH-20", "Döküm Tablası 1", "MT-TAB", 14.0, "MANUAL", True),
            ("MCH-21", "Döküm Tablası 2", "MT-TAB", 10.0, "MANUAL", True),
            ("MCH-30", "Testere 1", "MT-TES", 14.0, "MANUAL", True),
            ("MCH-31", "Testere 2", "MT-TES", 8.0, "MANUAL", False),
            ("MCH-40", "Paketleme 1", "MT-PAK", 20.0, "MANUAL", True),
        ]
        for kod, ad, tip, kap, mod, aktif in makineler:
            self.data["machines"].append({
                "id": kod, "ad": ad, "tipId": tip, "kapasiteTon": kap,
                "mod": mod, "aktif": aktif, "plantId": p,
                "createdAt": time.time(),
            })

        # Fırınlar (simülasyon fırınlarıyla eşleşir)
        for i, (ad, tip, mn, mx) in enumerate([
            ("Aluminyum Eritme Fırını", "MT-ERG", 700, 850),
            ("Homojenizasyon Fırını", "MT-HOM", 560, 620),
            ("Biyet Isıtma Fırını", "MT-YAS", 480, 540),
        ], 1):
            self.data["furnaces"].append({
                "id": f"FRN-{i:04d}", "ad": ad, "makineKod": ["MCH-01", "MCH-10", "MCH-02"][i - 1],
                "tipId": tip, "minSicaklik": 25.0, "maxSicaklik": mx,
                "nominalHedef": mn, "plantId": p,
            })

        # Döküm yolları (§5 ekran 16)
        self.data["castingPaths"].append({
            "id": "CPT-0001", "ad": "Ana Yol 1", "firin": "MCH-01",
            "tabla": "MCH-20", "testere": "MCH-30", "tutmaTon": 14.0,
            "aktif": True, "plantId": p,
        })

        # PLC bağlantısı ve tag'leri (§4, §8)
        self.data["plcConnections"].append({
            "id": "PLC-0001", "ad": "Simülasyon OPC UA", "protokol": "OPCUA",
            "host": "127.0.0.1", "port": 4840, "aktif": True,
            "mod": "PLC", "plantId": p,
        })
        for sinyal in ("door", "casting", "alarm", "running"):
            self.data["plcTags"].append({
                "id": self._id("TAG"), "sinyal": sinyal,
                "adres": f"ns=2;s=Fabrika.{sinyal}", "connectionId": "PLC-0001",
                "plantId": p,
            })

        # Malzemeler (§5 ekran 2)
        malzemeler = [
            ("MAT-0001", "Alüminyum Hurda", "Alüminyum Hurda", "KG", 2.35, 5000.0),
            ("MAT-0002", "Alaşım Katkısı (Mg)", "Ana Metal", "KG", 18.50, 500.0),
            ("MAT-0003", "Döküm Yağı", "Sarf Malzeme", "LT", 42.00, 200.0),
            ("MAT-0004", "Testere Bıçağı", "Sarf Malzeme", "AD", 850.0, 10.0),
            ("MAT-0005", "Doğal Gaz", "Enerji", "MT", 12.00, 10000.0),
        ]
        for kod, ad, kat, birim, fiyat, kritik in malzemeler:
            self.data["materials"].append({
                "id": kod, "ad": ad, "kategori": kat, "birim": birim,
                "birimFiyat": fiyat, "kritikEsik": kritik, "aktif": True,
                "plantId": p, "createdAt": time.time(),
            })

        # Tedarikçiler (§5 ekran 5)
        for i, (kod, ad, tel, odeme, performans) in enumerate([
            ("SUP-0001", "Marmara Metal Geri Dönüşüm", "0212 555 0101", "30 gün", 92.0),
            ("SUP-0002", "Anadolu Alaşım Ltd.", "0216 555 0202", "60 gün", 87.0),
            ("SUP-0003", "Ege Sarf Malzeme", "0232 555 0303", "peşin", 95.0),
        ], 1):
            self.data["suppliers"].append({
                "id": kod, "ad": ad, "telefon": tel, "odemeKosulu": odeme,
                "performans": performans, "bakiye": 0.0,
                "plantId": p, "createdAt": time.time(),
            })

        # Müşteriler (§5 ekran 21)
        for kod, ad, limit, bakiye in [
            ("CUS-0001", "Beyaz Eşya A.Ş.", 500000.0, 125000.0),
            ("CUS-0002", "Otomotiv Yan Sanayi Ltd.", 300000.0, 98000.0),
            ("CUS-0003", "İnşaat Profil San.", 150000.0, 142000.0),
        ]:
            self.data["customers"].append({
                "id": kod, "ad": ad, "krediLimiti": limit, "bakiye": bakiye,
                "riskDurumu": "normal" if bakiye < limit * 0.8 else "yüksek",
                "plantId": p, "createdAt": time.time(),
            })

        # Depolar
        for kod, ad in [("DEP-0001", "Hammadde Deposu"), ("DEP-0002", "Mamul Deposu")]:
            self.data["warehouses"].append({"id": kod, "ad": ad, "plantId": p})

        # Reçete (§5 ekran 12)
        self.data["recipes"].append({
            "id": "RCP-0001", "ad": "6063 Biyet Reçetesi", "makineKod": "MCH-01",
            "urun": "6063 Alüminyum Biyet", "hedefTonaj": 14.0,
            "yogunluk": 2700.0, "malzemeOranlari": [
                {"malzeme": "MAT-0001", "oran": 0.94},
                {"malzeme": "MAT-0002", "oran": 0.06},
            ],
            "aktif": True, "plantId": p,
        })
        self.data["homogenizationRecipes"].append({
            "id": "HRC-0001", "ad": "6063 Homojenizasyon", "hedefSicaklik": 560.0,
            "hedefSureDk": 8, "toleransDk": 1, "plantId": p,
        })

        # Yağ/bıçak kuralları (§5 ekran 18)
        # İki makinede sayaç: MCH-30 demo bakımda sıfırlanır, MCH-01 eşikte kalır
        # (arayüzde "yaklaşan bakım" uyarısı her zaman görünsün).
        self.data["oilRules"].append({"id": "OIL-0001", "makineKod": "MCH-30",
                                      "limitSaat": 500.0, "kullanilanSaat": 412.0,
                                      "plantId": p})
        self.data["oilRules"].append({"id": "OIL-0002", "makineKod": "MCH-01",
                                      "limitSaat": 600.0, "kullanilanSaat": 528.0,
                                      "plantId": p})
        self.data["bladeRules"].append({"id": "BLD-0001", "makineKod": "MCH-30",
                                        "limitKesim": 2000, "kullanilanKesim": 1680,
                                        "plantId": p})

        # Personel (§5 ekran 25)
        for i, (ad, rol, vardiya) in enumerate([
            ("Mehmet Yılmaz", "Fırın Operatörü", "08:00-16:00"),
            ("Ayşe Demir", "Kalite Sorumlusu", "08:00-16:00"),
            ("Hasan Kaya", "Vardiya Şefi", "16:00-00:00"),
            ("Elif Şahin", "Depo Sorumlusu", "08:00-16:00"),
        ], 1):
            self.data["users"].append({
                "id": f"USR-{i:04d}", "ad": ad, "rol": rol, "vardiya": vardiya,
                "aktif": True, "bordroKapsam": False, "plantId": p,
            })

        # Modüller (§9.2)
        for m in MODULLER:
            self.data["moduleRegistry"].append({"id": m["id"], **m,
                                                "plantId": p})
            self.data["plantModules"].append({
                "id": f"PM-{m['id']}", "modulId": m["id"], "aktif": True,
                "plantId": p,
            })

        # Hesap planı (§7.3)
        for h in HESAPLAR:
            self.data["accounts"].append({**h, "id": f"ACC-{h['kod']}", "plantId": p})

        # Entegrasyon kuralları (§5 ekran 29: 10 kural)
        kurallar = [
            ("sevkiyat-onay", "Sevkiyat 2. onayı", ["stok_cikis", "satis_faturasi", "muhasebe_fisi", "cari_hareket", "maliyet_yansimasi", "bildirim", "outbox", "olay"]),
            ("mal-kabul", "Mal kabul", ["stok_giris", "fiyat_gecmisi", "emir_karsilama", "olay"]),
            ("alis-faturasi", "Alış faturası", ["muhasebe_fisi", "cari_hareket", "odeme_vadesi"]),
            ("satis-faturasi", "Satış faturası", ["muhasebe_fisi", "cari_hareket"]),
            ("uretim-tamamla", "Üretim tamamlama", ["mamul_stok", "yan_urun", "maliyet_kaydi", "olay"]),
            ("sayim-farki", "Sayım farkı", ["stok_duzeltme", "muhasebe_fisi", "denetim_izi"]),
            ("kırıcı-fire", "Kırıcı fire", ["by_urun_kaderi", "stok_duzeltme", "olay"]),
            ("bakim-tamamla", "Bakım tamamlama", ["bakim_kaydi", "sayac_sifirla", "olay"]),
            ("alarm", "Alarm", ["bildirim", "olay", "signal_states"]),
            ("edge-ingest", "Edge batch", ["signal_states", "telemetri", "bakim_bildirimi"]),
        ]
        for kod, ad, kayitlar in kurallar:
            self.data["integrationRules"].append({
                "id": kod, "ad": ad, "uretilenKayitlar": kayitlar,
                "clientIdZorunlu": True, "plantId": p,
            })

        # Bütçe (§5 ekran 23 / raporlama)
        self.data["budgets"].append({
            "id": "BUD-0001", "donem": time.strftime("%Y-%m"),
            "plan": 2500000.0, "gercek": 0.0, "plantId": p,
        })

        # Saha kurulum sihirbazı taslağı (§9.3 — 5 adım)
        self.data["setupDrafts"].append({
            "id": "SET-0001", "ad": "Örnek fabrika kurulumu",
            "adim": 5, "adimSayisi": 5,
            "adimlar": [
                {"no": 1, "ad": "Fabrika", "tamam": True,
                 "ozet": "ALB-01 / İstanbul / PLC modu"},
                {"no": 2, "ad": "Makine", "tamam": True,
                 "ozet": "2 ergitme, 1 tabla, 1 testere"},
                {"no": 3, "ad": "Yol", "tamam": True,
                 "ozet": "MCH-01 → MCH-20 → MCH-30"},
                {"no": 4, "ad": "Bağlantı", "tamam": True,
                 "ozet": "OPC UA 127.0.0.1:4840"},
                {"no": 5, "ad": "Modül", "tamam": True,
                 "ozet": "13 modül açık"},
            ],
            "durum": "TASLAK", "plantId": p,
        })

        # Başlangıç stoğu
        self._hareket("MAT-0001", "GIRIS", 25000.0, "KG", "DEP-0001", "ACILIS")
        self._hareket("MAT-0002", "GIRIS", 1500.0, "KG", "DEP-0001", "ACILIS")
        self._hareket("MAT-0003", "GIRIS", 400.0, "LT", "DEP-0001", "ACILIS")
        self._hareket("MAT-0004", "GIRIS", 24.0, "AD", "DEP-0001", "ACILIS")

        self._bildir("Sistem hazır", "Simülasyon ERP test ortamı başlatıldı.", "bilgi")

        # Arayüz ilk açıldığında 35 ekranın hepsi dolu görünsün: örnek bir
        # uçtan uca iş zinciri çalıştır (tümü demo verisi, plantId PLANT-1).
        self._ornek_zincir()

    def _ornek_zincir(self) -> None:
        """Demo: satın alma → üretim → satış → sevkiyat → muhasebe → bakım.

        `_seed()` sonunda bir kez çalışır. Hata olursa sessizce geçilir;
        demo verisi eksik kalır ama sunucu açılır.
        """
        try:
            self._seed_modu = True

            # --- §6.1 satın alma
            talep = self.talep_olustur("MAT-0001", 12000, "Aylık hurda alımı")
            teklif1 = self.teklif_ver(talep["id"], "SUP-0001", 2.32)
            teklif2 = self.teklif_ver(talep["id"], "SUP-0002", 2.28)
            emir = self.teklif_sec(teklif2["id"])
            self.satin_alma_onayla(emir["id"])
            self.mal_kabul(emir["id"], brut=12200, fire=200)
            self.alis_faturasi(emir["id"])

            # --- §6.2 üretim (2 lot)
            for fire, enerji in ((0.4, 3500), (0.35, 3200)):
                lot = self.lot_ac("RCP-0001", "MCH-01")
                for _ in range(7):
                    self.asama_ilerlet(lot["id"])
                self.lot_tamamla(lot["id"], net_ton=14.0, fire_ton=fire)
                self.lot_maliyet(lot["id"], enerji=enerji, sarf=800, iscilik=2200)

            # --- homojenizasyon partisi (§5/13)
            lot2 = [l for l in self.data["lots"] if l["durum"] == "TAMAMLANDI"][-1]
            parti = self.homojenizasyon_plani(lot2["id"], "HRC-0001", 560, 8)
            self.homojenizasyon_tamamla(parti["id"], 8.6, 559)

            # --- §6.4 sayım + kırıcı
            self.sayim_yap("MAT-0003", 396)
            self.kirici_kaydet(lot2["id"], 0.35, "TEKRAR_FIRIN")

            # --- §6.3 satış + iki onaylı sevkiyat (2 sevkiyat)
            for musteri, ton, fiyat in (("CUS-0001", 5.0, 3400),
                                        ("CUS-0002", 3.0, 3500)):
                sip = self.satis_siparisi(musteri, "6063 Alüminyum Biyet",
                                          ton, fiyat)
                sev = self.sevkiyat_hazirla(sip["id"])
                self.sevkiyat_onayla(sev["id"], plaka="34 ALB 01")
                self.sevkiyat_onayla(sev["id"],
                                     client_id=f"SEED-{sev['id']}")

            # --- satış teklifi (bekleyen)
            self.teklif_hazirla("CUS-0003", "6063 Alüminyum Biyet", 2.0, 3600)

            # --- §7.3 muhasebe: tahsilat + dönem kapanışı
            self.odeme_kaydet("TAHSILAT", "CUS-0001", 50000)
            self.donem_kapat(time.strftime("%Y-%m"), onay=True)

            # --- §5/18 bakım
            self.bakim_kaydet("MCH-30", "bıçak değişimi", "Periyodik bakım",
                              kesim=1680)

            # --- ek personel
            self._ekle("users", {"ad": "Zeynep Arslan", "rol": "Kalite",
                                 "vardiya": "16:00-00:00", "aktif": True,
                                 "bordroKapsam": False})

            self._bildir("Demo verisi hazır",
                         "Örnek satın alma, üretim, satış ve sevkiyat "
                         "zinciri yüklendi.", "basari")
        except Exception as exc:  # pragma: no cover - demo verisi
            print("Örnek zincir kurulamadı:", exc)
        finally:
            self._seed_modu = False

    # ------------------------------------------------------------ §6.1 satın alma

    def talep_olustur(self, malzeme: str, miktar: float, gerekce: str,
                      istenen_tarih: Optional[str] = None,
                      client_id: Optional[str] = None) -> dict:
        """Talep aç (§5 ekran 6, §6.1 adım 1)."""
        self._zorunlu("materials", malzeme, "Malzeme")
        if miktar <= 0:
            raise ErpHatası("miktar pozitif olmalı")
        kayit = self._ekle("purchaseRequests", {
            "malzeme": malzeme, "miktar": float(miktar), "gerekce": gerekce,
            "istenenTarih": istenen_tarih, "durum": "ACIK",
        }, client_id)
        if not kayit.get("_tekrar"):
            self._olay("talep", f"{miktar} birim {malzeme} talebi açıldı", kayit["id"])
        return kayit

    def teklif_ver(self, talep_id: str, tedarikci: str, birim_fiyat: float,
                   teslim_gun: int = 7, gecerlilik_gun: int = 15) -> dict:
        """Tedarikçiden teklif al (§6.1 adım 2)."""
        self._zorunlu("purchaseRequests", talep_id, "Talep")
        self._zorunlu("suppliers", tedarikci, "Tedarikçi")
        if birim_fiyat <= 0:
            raise ErpHatası("birim fiyat pozitif olmalı")
        kayit = self._ekle("purchaseQuotes", {
            "talepId": talep_id, "tedarikci": tedarikci,
            "birimFiyat": float(birim_fiyat), "teslimGun": int(teslim_gun),
            "gecerlilikGun": int(gecerlilik_gun), "durum": "BEKLIYOR",
        })
        self._olay("teklif", f"{tedarikci} teklif verdi: {birim_fiyat}", kayit["id"])
        return kayit

    def teklif_sec(self, teklif_id: str) -> dict:
        """Teklifi seç → satın alma emri taslağı (§6.1 adım 2-3)."""
        teklif = self._zorunlu("purchaseQuotes", teklif_id, "Teklif")
        talep = self._zorunlu("purchaseRequests", teklif["talepId"], "Talep")
        teklif["durum"] = "SECILDI"
        teklif["updatedAt"] = time.time()
        talep["durum"] = "TEKLIF_SECILDI"
        emir = self._ekle("purchaseOrders", {
            "tedarikci": teklif["tedarikci"], "talepId": talep["id"],
            "teklifId": teklif_id, "malzeme": talep["malzeme"],
            "miktar": talep["miktar"],
            "birimFiyat": teklif["birimFiyat"],
            "toplam": round(talep["miktar"] * teklif["birimFiyat"], 2),
            "teslimTarihi": teklif["teslimGun"],
            "durum": "TASLAK", "karsilanan": 0.0,
        })
        self._olay("satin_alma", f"Satın alma emri taslağı: {emir['id']}", emir["id"])
        return emir

    def satin_alma_onayla(self, emir_id: str) -> dict:
        """Satın alma emrini onayla (§6.1 adım 3)."""
        emir = self._zorunlu("purchaseOrders", emir_id, "Satın alma emri")
        if emir["durum"] not in ("TASLAK", "ONAYLANDI"):
            raise ErpHatası(f"emir {emir['durum']} durumunda, onaylanamaz")
        emir["durum"] = "ONAYLANDI"
        emir["onayTarihi"] = time.time()
        emir["updatedAt"] = time.time()
        self._olay("satin_alma", f"Emir onaylandı: {emir_id}", emir_id)
        return emir

    def mal_kabul(self, emir_id: str, brut: float, fire: float,
                  depo: str = "DEP-0001", client_id: Optional[str] = None) -> dict:
        """Mal kabul: brüt/fire/net, stok girişi, fiyat geçmişi (§6.1 adım 4-5)."""
        emir = self._zorunlu("purchaseOrders", emir_id, "Satın alma emri")
        if emir["durum"] not in ("ONAYLANDI", "KISMI"):
            raise ErpHatası(
                f"emir {emir['durum']} durumunda; önce onaylanmalı")
        if brut <= 0:
            raise ErpHatası("brüt miktar pozitif olmalı")
        if fire < 0 or fire >= brut:
            raise ErpHatası("fire 0 ile brüt arasında olmalı")
        net = round(brut - fire, 3)
        mevcut_client = client_id
        if mevcut_client:
            for r in self.data["receipts"]:
                if r.get("clientId") == mevcut_client:
                    return dict(r, _tekrar=True)

        kalan = emir["miktar"] - emir["karsilanan"]
        kabul = min(net, kalan)

        makbuz = self._ekle("receipts", {
            "emirId": emir_id, "malzeme": emir["malzeme"], "brut": float(brut),
            "fire": float(fire), "net": net, "kabulEdilen": round(kabul, 3),
            "depo": depo, "birimFiyat": emir["birimFiyat"],
            "fireOraniYuzde": round(fire / brut * 100.0, 2),
        }, client_id)

        self._hareket(emir["malzeme"], "GIRIS", kabul, "KG", depo, makbuz["id"])

        # Fiyat geçmişi (§5 ekran 4)
        self._ekle("priceHistory", {
            "malzeme": emir["malzeme"], "tedarikci": emir["tedarikci"],
            "birimFiyat": emir["birimFiyat"], "kaynakBelge": makbuz["id"],
        })

        emir["karsilanan"] = round(emir["karsilanan"] + kabul, 3)
        emir["durum"] = "TAMAMLANDI" if emir["karsilanan"] >= emir["miktar"] - 0.001 else "KISMI"
        emir["updatedAt"] = time.time()

        self._olay("mal_kabul",
                   f"{kabul} KG kabul (brüt {brut}, fire {fire})", makbuz["id"])
        self._bildir("Mal kabul", f"{emir['malzeme']}: {kabul} KG stoğa girdi.")
        return makbuz

    def alis_faturasi(self, emir_id: str, client_id: Optional[str] = None) -> dict:
        """Alış faturası: 150+191 borç, 320 alacak (§6.1 adım 6)."""
        emir = self._zorunlu("purchaseOrders", emir_id, "Satın alma emri")
        makbuzlar = [r for r in self.data["receipts"] if r["emirId"] == emir_id]
        if not makbuzlar:
            raise ErpHatası("bu emre ait mal kabul yok")
        net_tutar = round(sum(r["kabulEdilen"] * r["birimFiyat"] for r in makbuzlar), 2)
        fis = M.purchase_entry(net_tutar, aciklama=f"Alış faturası {emir_id}")
        fis_kayit = self._ekle("journalEntries", {
            "aciklama": fis["aciklama"], "satirlar": fis["satirlar"],
            "toplamBorc": fis["toplam_borc"], "toplamAlacak": fis["toplam_alacak"],
            "balanced": fis["balanced"], "sourceId": emir_id, "tip": "ALIS",
        }, client_id)
        fatura = self._ekle("invoices", {
            "tip": "ALIS", "emirId": emir_id, "net": fis["tutar"]["net"],
            "kdv": fis["tutar"]["kdv"], "genelToplam": fis["tutar"]["genel_toplam"],
            "fisId": fis_kayit["id"], "durum": "KESILDI",
        })
        # Satıcı cari
        satici = self._bul("suppliers", emir["tedarikci"])
        if satici:
            satici["bakiye"] = round(satici.get("bakiye", 0.0) + fis["tutar"]["genel_toplam"], 2)
        self._olay("alis_faturasi", f"{fatura['genelToplam']} TL", fatura["id"])
        return {"fatura": fatura, "fis": fis_kayit}

    # ------------------------------------------------------------ §6.2 üretim

    def lot_ac(self, recete_id: str, firin_makine: str,
               hedef_ton: Optional[float] = None,
               client_id: Optional[str] = None) -> dict:
        """Döküm kodu (lot) aç (§6.2 adım 2)."""
        recete = self._zorunlu("recipes", recete_id, "Reçete")
        self._zorunlu("machines", firin_makine, "Makine")
        ton = float(hedef_ton or recete["hedefTonaj"])
        lot = self._ekle("lots", {
            "kod": None, "receteId": recete_id, "makineKod": firin_makine,
            "urun": recete["urun"], "hedefTon": ton,
            "asama": ASAMALAR[0], "asamaIndex": 0,
            "durum": "ACIK", "maliyetId": None,
            "baslangic": time.time(),
        }, client_id)
        if not lot.get("kod"):
            lot["kod"] = f"LOT-{time.strftime('%y%m%d')}-{lot['id'].split('-')[-1]}"
            lot["updatedAt"] = time.time()
        if not lot.get("_tekrar"):
            self._olay("lot", f"Döküm kodu açıldı: {lot['kod']}", lot["id"])
        return lot

    def asama_ilerlet(self, lot_id: str, asama: Optional[str] = None,
                      client_id: Optional[str] = None) -> dict:
        """Üretim aşamasını ilerlet (sürükle-bırak panosu, §5 ekran 11)."""
        lot = self._zorunlu("lots", lot_id, "Lot")
        if lot["durum"] != "ACIK":
            raise ErpHatası(f"lot {lot['durum']} durumunda, ilerletilemez")
        if asama:
            if asama not in ASAMALAR:
                raise ErpHatası(f"bilinmeyen aşama: {asama}. Geçerli: {ASAMALAR}")
            yeni = ASAMALAR.index(asama)
        else:
            yeni = lot["asamaIndex"] + 1
        if yeni >= len(ASAMALAR):
            raise ErpHatası("son aşamaya ulaşıldı; lot tamamlanmalı")
        if yeni != lot["asamaIndex"] + 1:
            raise ErpHatası(
                f"aşama atlanamaz ({lot['asama']} → {ASAMALAR[yeni]})")
        lot["asamaIndex"] = yeni
        lot["asama"] = ASAMALAR[yeni]
        lot["updatedAt"] = time.time()
        self._olay("asama", f"{lot['kod']} → {lot['asama']}", lot_id)
        return lot

    def lot_tamamla(self, lot_id: str, net_ton: float,
                    fire_ton: float = 0.0,
                    client_id: Optional[str] = None) -> dict:
        """Lotu kapat: mamul stok, yan ürün, maliyet kaydı (§6.2 adım 8)."""
        lot = self._zorunlu("lots", lot_id, "Lot")
        if lot["durum"] != "ACIK":
            raise ErpHatası(f"lot {lot['durum']} durumunda")
        if net_ton <= 0:
            raise ErpHatası("net ton pozitif olmalı")
        if net_ton > lot["hedefTon"] * 1.05:
            raise ErpHatası(
                f"net ton hedefi aşıyor ({net_ton} > {lot['hedefTon']})")

        lot["durum"] = "TAMAMLANDI"
        lot["asama"] = ASAMALAR[-1]
        lot["asamaIndex"] = len(ASAMALAR) - 1
        lot["netTon"] = float(net_ton)
        lot["fireTon"] = float(fire_ton)
        lot["bitis"] = time.time()
        lot["updatedAt"] = time.time()

        # Mamul stok girişi
        self._hareket(f"MAMUL:{lot['urun']}", "GIRIS", net_ton, "TON",
                      "DEP-0002", lot["id"], lot=lot["kod"])

        # Yan ürün (§5 ekran 9)
        if fire_ton > 0:
            self._ekle("byProductFates", {
                "lotId": lot_id, "miktarTon": float(fire_ton),
                "kader": "TEKRAR_FIRIN", "not": "Hurda tekrar ergitmeye",
            })
            self._ekle("crusher", {
                "lotId": lot_id, "girisTon": float(fire_ton),
                "cikisTon": round(float(fire_ton) * 0.97, 3),
                "kayipTon": round(float(fire_ton) * 0.03, 3),
                "kader": "TEKRAR_FIRIN",
            })

        self._olay("uretim", f"{lot['kod']} tamamlandı: {net_ton} ton", lot_id)
        return lot

    def lot_maliyet(self, lot_id: str, enerji: float = 0.0, sarf: float = 0.0,
                    iscilik: float = 0.0) -> dict:
        """Döküm kodu maliyeti (§7.4). Hammadde reçeteden hesaplanır."""
        lot = self._zorunlu("lots", lot_id, "Lot")
        recete = self._zorunlu("recipes", lot["receteId"], "Reçete")
        hammadde = 0.0
        for o in recete.get("malzemeOranlari", []):
            mal = self._bul("materials", o["malzeme"])
            if mal:
                hammadde += lot["hedefTon"] * 1000.0 * o["oran"] * mal["birimFiyat"]
        fire_maliyet = lot.get("fireTon", 0.0) * lot["hedefTon"] * 100.0
        net_ton = lot.get("netTon") or lot["hedefTon"]
        maliyet = M.lot_cost(hammadde=hammadde, enerji=enerji, sarf=sarf,
                             iscilik=iscilik, fire=fire_maliyet, net_ton=net_ton)
        kayit = self._ekle("costRecords", {
            "lotId": lot_id, **maliyet,
        })
        lot["maliyetId"] = kayit["id"]
        lot["updatedAt"] = time.time()
        self._olay("maliyet", f"{lot['kod']} ton maliyeti: {maliyet['ton_maliyet']}", kayit["id"])
        return kayit

    def homojenizasyon_plani(self, lot_id: str, recete_id: str,
                             hedef_sicaklik: float, hedef_sure_dk: float) -> dict:
        """Homojenizasyon partisi planla (§5 ekran 13)."""
        self._zorunlu("lots", lot_id, "Lot")
        self._zorunlu("homogenizationRecipes", recete_id, "Homojenizasyon reçetesi")
        return self._ekle("homogenizationBatches", {
            "lotId": lot_id, "receteId": recete_id,
            "hedefSicaklik": float(hedef_sicaklik),
            "hedefSureDk": float(hedef_sure_dk),
            "gerceklesenSureDk": None, "gerceklesenSicaklik": None,
            "durum": "PLANLANDI",
        })

    def homojenizasyon_tamamla(self, parti_id: str, gercek_sure_dk: float,
                               gercek_sicaklik: float) -> dict:
        """Partiyi tamamla; süre sapması raporlanır (§6.2 adım 6)."""
        parti = self._zorunlu("homogenizationBatches", parti_id, "Parti")
        if parti["durum"] == "TAMAMLANDI":
            raise ErpHatası("parti zaten tamamlanmış")
        parti["gerceklesenSureDk"] = float(gercek_sure_dk)
        parti["gerceklesenSicaklik"] = float(gercek_sicaklik)
        parti["durum"] = "TAMAMLANDI"
        parti["updatedAt"] = time.time()
        parti["sure_kontrol"] = M.duration_check(parti["hedefSureDk"], gercek_sure_dk)
        self._ekle("coolingBatches", {
            "lotId": parti["lotId"], "baslangic": time.time(),
            "durum": "BASLADI",
        })
        self._olay("homojenizasyon",
                   f"Parti tamam: sapma {parti['sure_kontrol']['fark_dk']} dk", parti_id)
        return parti

    # ------------------------------------------------------------ §6.4 sayım/fire

    def sayim_yap(self, malzeme: str, sayilan: float, depo: str = "DEP-0001",
                  client_id: Optional[str] = None) -> dict:
        """Fiziki sayım; fark varsa düzeltme hareketi + fiş (§6.4)."""
        self._zorunlu("materials", malzeme, "Malzeme")
        sistem = self._stok_miktar(malzeme)
        fark = round(float(sayilan) - sistem, 3)
        kayit = self._ekle("stockCounts", {
            "malzeme": malzeme, "depo": depo, "sistemMiktar": sistem,
            "sayilanMiktar": float(sayilan), "fark": fark,
            "durum": "FARK_VAR" if abs(fark) > 0.001 else "UYGUN",
        }, client_id)
        if kayit.get("_tekrar"):
            return kayit
        if abs(fark) > 0.001:
            self._hareket(malzeme, "DUZELTME", fark, "KG", depo, kayit["id"])
            mal = self._bul("materials", malzeme)
            tutar = round(abs(fark) * (mal["birimFiyat"] if mal else 0.0), 2)
            fis = M.build_entry(
                f"Sayım düzeltmesi {malzeme}",
                [{"hesap": "150", "borc": tutar if fark < 0 else 0},
                 {"hesap": "740", "alacak": tutar if fark < 0 else 0}] if fark < 0
                else [{"hesap": "150", "borc": tutar},
                      {"hesap": "740", "alacak": tutar}],
                source_id=kayit["id"])
            self._ekle("journalEntries", {
                "aciklama": fis["aciklama"], "satirlar": fis["satirlar"],
                "toplamBorc": fis["toplam_borc"],
                "toplamAlacak": fis["toplam_alacak"],
                "balanced": fis["balanced"], "sourceId": kayit["id"],
                "tip": "SAYIM",
            })
            self._olay("sayim", f"{malzeme} fark: {fark}", kayit["id"])
        return kayit

    def kirici_kaydet(self, lot_id: str, miktar_ton: float, kader: str,
                      client_id: Optional[str] = None) -> dict:
        """Kırıcı/fire kaydı; kader: TEKRAR_FIRIN / DONGUSEL / SATIS / ATIK."""
        self._zorunlu("lots", lot_id, "Lot")
        if kader not in ("TEKRAR_FIRIN", "DONGUSEL", "SATIS", "ATIK"):
            raise ErpHatası("kader şunlardan biri olmalı: TEKRAR_FIRIN, "
                            "DONGUSEL, SATIS, ATIK")
        kayit = self._ekle("crusher", {
            "lotId": lot_id, "girisTon": float(miktar_ton),
            "cikisTon": float(miktar_ton), "kayipTon": 0.0, "kader": kader,
        }, client_id)
        self._ekle("byProductFates", {"lotId": lot_id,
                                       "miktarTon": float(miktar_ton),
                                       "kader": kader})
        return kayit

    # ------------------------------------------------------------ §6.3 satış/sevkiyat

    def musteri_ekle(self, ad: str, kredi_limiti: float,
                     client_id: Optional[str] = None) -> dict:
        kayit = self._ekle("customers", {
            "ad": ad, "krediLimiti": float(kredi_limiti), "bakiye": 0.0,
            "riskDurumu": "normal",
        }, client_id)
        return kayit

    def satis_siparisi(self, musteri: str, urun: str, miktar_ton: float,
                       birim_fiyat: float, teslim_tarihi: Optional[str] = None,
                       client_id: Optional[str] = None) -> dict:
        """Satış siparişi; kredi kontrolü + stok rezervasyonu (§5 ekran 20)."""
        mus = self._zorunlu("customers", musteri, "Müşteri")
        if miktar_ton <= 0:
            raise ErpHatası("miktar pozitif olmalı")
        tutar = round(miktar_ton * birim_fiyat, 2)
        kredi = M.credit_check(mus["krediLimiti"], mus["bakiye"], tutar)
        if not kredi["onay"]:
            raise ErpHatası(
                f"kredi limiti aşılıyor: limit {mus['krediLimiti']:.0f}, "
                f"mevcut {mus['bakiye']:.0f}, yeni {tutar:.0f} → "
                f"aşılan {kredi['asilan']:.0f} TL")

        stok = self._stok_miktar(f"MAMUL:{urun}")
        if stok < miktar_ton:
            raise ErpHatası(
                f"yetersiz mamul stok: {urun} için {stok} ton var, "
                f"{miktar_ton} ton isteniyor")

        siparis = self._ekle("salesOrders", {
            "musteri": musteri, "urun": urun, "miktarTon": float(miktar_ton),
            "birimFiyat": float(birim_fiyat), "tutar": tutar,
            "teslimTarihi": teslim_tarihi, "durum": "ACIK",
            "krediKontrol": kredi,
        }, client_id)
        if siparis.get("_tekrar"):
            return siparis

        # Rezervasyon
        self._ekle("reservations", {
            "siparisId": siparis["id"], "malzeme": f"MAMUL:{urun}",
            "miktarTon": float(miktar_ton), "durum": "AKTIF",
        })
        self._olay("satis_siparisi", f"{tutar} TL sipariş", siparis["id"])
        return siparis

    def teklif_hazirla(self, musteri: str, urun: str, miktar_ton: float,
                       birim_fiyat: float) -> dict:
        """Müşteriye teklif (§5 ekran 20 akışı)."""
        self._zorunlu("customers", musteri, "Müşteri")
        tutar = round(miktar_ton * birim_fiyat, 2)
        return self._ekle("quotations", {
            "musteri": musteri, "urun": urun, "miktarTon": float(miktar_ton),
            "birimFiyat": float(birim_fiyat), "tutar": tutar,
            "kdv": M.amounts(tutar)["kdv"],
            "genelToplam": M.amounts(tutar)["genel_toplam"],
            "durum": "GONDERILDI",
        })

    def sevkiyat_hazirla(self, siparis_id: str,
                         client_id: Optional[str] = None) -> dict:
        """Sevkiyat kaydı aç — 1. onay bekliyor (§6.3)."""
        siparis = self._zorunlu("salesOrders", siparis_id, "Satış siparişi")
        if siparis["durum"] not in ("ACIK", "HAZIRLANIYOR"):
            raise ErpHatası(f"sipariş {siparis['durum']} durumunda")
        kayit = self._ekle("shipments", {
            "siparisId": siparis_id, "musteri": siparis["musteri"],
            "urun": siparis["urun"], "miktarTon": siparis["miktarTon"],
            "tutar": siparis["tutar"], "onay1": False, "onay2": False,
            "onay1Zaman": None, "onay2Zaman": None,
            "plaka": None, "irsaliyeNo": None, "durum": "HAZIRLANIYOR",
        }, client_id)
        if not kayit.get("_tekrar"):
            siparis["durum"] = "HAZIRLANIYOR"
            siparis["updatedAt"] = time.time()
            self._olay("sevkiyat", "Sevkiyat hazırlanıyor (1. onay bekliyor)", kayit["id"])
        return kayit

    def sevkiyat_onayla(self, sevkiyat_id: str, plaka: Optional[str] = None,
                        irsaliye_no: Optional[str] = None,
                        client_id: Optional[str] = None) -> dict:
        """İki kademeli onay (§6.3).

        1. onay → hazırlık tamam. 2. onay → fiili çıkış; **tek işlemde**
        stok çıkışı, satış faturası, fiş, cari hareket, maliyet yansıması,
        bildirim, outbox ve olay üretilir.

        Aynı `clientId` ikinci kez gelirse ikinci kez yazılmaz.
        """
        sev = self._zorunlu("shipments", sevkiyat_id, "Sevkiyat")

        # Idempotency: aynı clientId ile onay tekrar denenirse yeni kayıt yok.
        if client_id:
            for f in self.data["invoices"]:
                if f.get("clientId") == client_id:
                    return {"sevkiyat": sev, "tekrar": True,
                            "fatura": f, "mesaj": "Bu onay zaten işlenmiş (idempotent)"}

        if not sev["onay1"]:
            sev["onay1"] = True
            sev["onay1Zaman"] = time.time()
            sev["plaka"] = plaka or "34 ABC 123"
            sev["irsaliyeNo"] = irsaliye_no or f"IRS-{int(time.time())}"
            sev["durum"] = "ONAY1_TAMAM"
            sev["updatedAt"] = time.time()
            self._olay("sevkiyat", "1. onay verildi (hazırlık tamam)", sevkiyat_id)
            self._bildir("Sevkiyat hazır",
                         f"{sev['musteri']} için {sev['miktarTon']} ton hazır.")
            return {"sevkiyat": sev, "asama": 1,
                    "mesaj": "1. onay alındı; fiili çıkış için 2. onay gerekli"}

        if sev["onay2"]:
            raise ErpHatası("bu sevkiyat zaten ikinci onaydan geçmiş")

        sev["onay2"] = True
        sev["onay2Zaman"] = time.time()
        sev["durum"] = "SEVK_EDILDI"
        sev["updatedAt"] = time.time()

        siparis = self._bul("salesOrders", sev["siparisId"])
        if siparis:
            siparis["durum"] = "SEVK_EDILDI"
            siparis["updatedAt"] = time.time()

        # 1) Stok çıkışı
        self._hareket(f"MAMUL:{sev['urun']}", "CIKIS", sev["miktarTon"], "TON",
                      "DEP-0002", sevkiyat_id)

        # 2) Rezervasyonu kapat
        for r in self.data["reservations"]:
            if r.get("siparisId") == sev["siparisId"] and r["durum"] == "AKTIF":
                r["durum"] = "KULLANILDI"
                r["updatedAt"] = time.time()

        # 3) Satış faturası + 4) fiş
        net = sev["tutar"]
        fis = M.sales_entry(net, aciklama=f"Satış faturası {sevkiyat_id}")
        fis_kayit = self._ekle("journalEntries", {
            "aciklama": fis["aciklama"], "satirlar": fis["satirlar"],
            "toplamBorc": fis["toplam_borc"], "toplamAlacak": fis["toplam_alacak"],
            "balanced": fis["balanced"], "sourceId": sevkiyat_id, "tip": "SATIS",
        })
        fatura = self._ekle("invoices", {
            "tip": "SATIS", "sevkiyatId": sevkiyat_id,
            "siparisId": sev["siparisId"], "musteri": sev["musteri"],
            "net": fis["tutar"]["net"], "kdv": fis["tutar"]["kdv"],
            "genelToplam": fis["tutar"]["genel_toplam"],
            "fisId": fis_kayit["id"], "durum": "KESILDI",
        }, client_id)

        # 5) Müşteri cari
        mus = self._bul("customers", sev["musteri"])
        if mus:
            mus["bakiye"] = round(mus.get("bakiye", 0.0) + fis["tutar"]["genel_toplam"], 2)
            mus["riskDurumu"] = ("yüksek" if mus["bakiye"] > mus["krediLimiti"] * 0.8
                                 else "normal")
            mus["updatedAt"] = time.time()

        # 6) Maliyet yansıması
        maliyet_yansima = None
        maliyetler = [c for c in self.data["costRecords"]]
        if maliyetler:
            ort = sum(c["ton_maliyet"] for c in maliyetler) / len(maliyetler)
            maliyet_yansima = round(ort * sev["miktarTon"], 2)
            karlilik = M.sales_margin(fis["tutar"]["net"], maliyet_yansima)
        else:
            karlilik = None

        # 7) Bildirim + 8) outbox + 9) olay
        self._bildir("Sevkiyat muhasebeleştirildi",
                     f"{sevkiyat_id}: {fatura['genelToplam']} TL fatura kesildi.",
                     "basari")
        self._outbox("e-posta", "satis@ornek.com",
                     "Günlük satış raporu",
                     f"{sev['musteri']} - {sev['miktarTon']} ton - "
                     f"{fatura['genelToplam']} TL")
        self._olay("sevkiyat", f"2. onay: sevk edildi ({sevkiyat_id})", sevkiyat_id)

        # Bütçe gerçekleşen
        for b in self.data["budgets"]:
            b["gercek"] = round(b.get("gercek", 0.0) + fis["tutar"]["net"], 2)

        return {
            "sevkiyat": sev,
            "asama": 2,
            "uretilen": {
                "stok_cikis": True,
                "fatura": fatura["id"],
                "fis": fis_kayit["id"],
                "cari_bakiye": mus["bakiye"] if mus else None,
                "maliyet_yansimasi": maliyet_yansima,
                "karlilik": karlilik,
                "bildirim": True,
                "outbox": True,
                "olay": True,
            },
            "kayit_sayisi": 8,
            "mesaj": "Sevkiyat muhasebeleştirildi (tek işlem, 8 kayıt)",
        }

    # ------------------------------------------------------------ muhasebe

    def mizan(self) -> dict:
        """Trial balance (§7.2/7.3)."""
        return M.trial_balance(self.data["journalEntries"])

    def donem_kapat(self, donem: str, onay: bool = False) -> dict:
        """Dönem kapanışı: mizan kontrolü + bütçe sapması (§7.3)."""
        if not onay:
            raise ErpHatası("dönem kapanışı onay gerektirir (onay=true)")
        tb = self.mizan()
        if not tb["denk"]:
            raise ErpHatası(
                f"mizan denk değil (borç {tb['toplam_borc']} ≠ "
                f"alacak {tb['toplam_alacak']}); kapanış yapılamaz")
        butce = next((b for b in self.data["budgets"] if b["donem"] == donem), None)
        sapma = None
        if butce:
            sapma = round(butce["gercek"] - butce["plan"], 2)
        kayit = self._ekle("periodClosures", {
            "donem": donem, "mizanDenk": tb["denk"],
            "toplamBorc": tb["toplam_borc"], "toplamAlacak": tb["toplam_alacak"],
            "butceSapma": sapma, "onaylandi": True,
        })
        self._olay("donem_kapanis", f"{donem} kapatıldı", kayit["id"])
        return kayit

    def odeme_kaydet(self, tip: str, taraf: str, tutar: float,
                     client_id: Optional[str] = None) -> dict:
        """Tahsilat/ödeme (§5 ekran 22). tip: TAHSILAT / ODEME."""
        if tip == "TAHSILAT":
            mus = self._bul("customers", taraf)
            if not mus:
                raise ErpHatası(f"müşteri bulunamadı: {taraf}")
            if tutar > mus["bakiye"] + 0.01:
                raise ErpHatası(
                    f"tahsilat bakiye üstünde: bakiye {mus['bakiye']:.2f}, "
                    f"tahsilat {tutar:.2f}")
            mus["bakiye"] = round(mus["bakiye"] - tutar, 2)
            fis = M.build_entry("Tahsilat", [
                {"hesap": "100", "borc": tutar},
                {"hesap": "120", "alacak": tutar},
            ], source_id=None)
        elif tip == "ODEME":
            sup = self._bul("suppliers", taraf)
            if not sup:
                raise ErpHatası(f"tedarikçi bulunamadı: {taraf}")
            sup["bakiye"] = round(sup.get("bakiye", 0.0) - tutar, 2)
            fis = M.build_entry("Ödeme", [
                {"hesap": "320", "borc": tutar},
                {"hesap": "100", "alacak": tutar},
            ], source_id=None)
        else:
            raise ErpHatası("tip TAHSILAT veya ODEME olmalı")

        kayit = self._ekle("payments", {
            "tip": tip, "taraf": taraf, "tutar": float(tutar),
        }, client_id)
        if kayit.get("_tekrar"):
            return kayit
        self._ekle("journalEntries", {
            "aciklama": fis["aciklama"], "satirlar": fis["satirlar"],
            "toplamBorc": fis["toplam_borc"], "toplamAlacak": fis["toplam_alacak"],
            "balanced": fis["balanced"], "sourceId": kayit["id"], "tip": tip,
        })
        self._olay("odeme", f"{tip} {tutar} TL - {taraf}", kayit["id"])
        return kayit

    # ------------------------------------------------------------ bakım

    def bakim_kaydet(self, makine_kod: str, tip: str, notu: str,
                     saat: float = 0.0, kesim: int = 0) -> dict:
        """Bakım kaydı + sayaç sıfırlama (§5 ekran 18)."""
        makine = self._zorunlu("machines", makine_kod, "Makine")
        kayit = self._ekle("maintenanceEvents", {
            "makineKod": makine_kod, "tip": tip, "not": notu,
            "harcananSaat": saat, "harcananKesim": kesim,
        })
        for r in self.data["oilRules"]:
            if r["makineKod"] == makine_kod:
                r["kullanilanSaat"] = 0.0
        for r in self.data["bladeRules"]:
            if r["makineKod"] == makine_kod:
                r["kullanilanKesim"] = 0
        self._olay("bakim", f"{makine['ad']}: {tip}", kayit["id"])
        return kayit

    def bakim_durumu(self) -> list[dict]:
        """Yağ/bıçak ömür durumu (§7.2 maintenanceStatus)."""
        sonuc = []
        for r in self.data["oilRules"]:
            d = M.maintenance_status(r["kullanilanSaat"], r["limitSaat"])
            sonuc.append({"makineKod": r["makineKod"], "kaynak": "yağ", **d})
        for r in self.data["bladeRules"]:
            d = M.maintenance_status(r["kullanilanKesim"], r["limitKesim"])
            sonuc.append({"makineKod": r["makineKod"], "kaynak": "bıçak", **d})
        return sonuc

    # ------------------------------------------------------------ PLC (ekran 19)

    def plc_sinyal_guncelle(self, firin_states: dict) -> dict:
        """Fırın simülasyonunun sinyallerini ERP modeline işler.

        Doküman §8: dört sinyal (`door`, `casting`, `alarm`, `running`) +
        telemetri. `door` simülasyonda yoktur → `unknown` (§15.1/6).
        Kalite etiketi `SIMULATED` — gerçek ölçüm gibi raporlanmaz (§8.2).
        """
        guncellenen = 0
        for ad, s in (firin_states or {}).items():
            durum = s.get("status", "KAPALI")
            running = durum in ("ISINIYOR", "BEKLETIYOR", "SOGUYOR")
            alarm = durum == "ALARM"
            mevcut = next((x for x in self.data["signalStates"]
                           if x["firin"] == ad), None)
            kayit = {
                "firin": ad,
                "door": None,               # simülasyonda yok
                "casting": False,
                "alarm": alarm,
                "running": running,
                "sicaklik": s.get("temperature"),
                "hedef": s.get("target_temperature"),
                "durum": durum,
                "kalite": "SIMULATED",
                "ts": time.time(),
            }
            if mevcut:
                mevcut.update(kayit)
                mevcut["updatedAt"] = time.time()
            else:
                kayit["id"] = self._id("SIG")
                kayit["createdAt"] = time.time()
                kayit["updatedAt"] = kayit["createdAt"]
                kayit["plantId"] = "PLANT-1"
                self.data["signalStates"].append(kayit)
            # Telemetri
            self.data["telemetry"].append({
                "id": self._id("TLM"), "firin": ad,
                "sicaklik": s.get("temperature"),
                "gaz_tuketimi": s.get("gas_consumption"),
                "enerji_toplam": s.get("energy_total"),
                "kalite": "SIMULATED", "ts": time.time(),
                "plantId": "PLANT-1",
            })
            guncellenen += 1
        # Telemetri sonsuz büyümesin
        if len(self.data["telemetry"]) > 2000:
            self.data["telemetry"] = self.data["telemetry"][-2000:]
        if guncellenen:
            self._kaydet()
        return {"guncellenen": guncellenen}

    # ------------------------------------------------------------ raporlar

    def kpi(self) -> dict:
        """Panel KPI'ları (§7.2 kpiSnapshot + §13)."""
        ciro = sum(f["net"] for f in self.data["invoices"] if f["tip"] == "SATIS")
        alacak = sum(m["bakiye"] for m in self.data["customers"])
        borc = sum(s.get("bakiye", 0.0) for s in self.data["suppliers"])
        acik = sum(1 for s in self.data["salesOrders"]
                   if s["durum"] in ("ACIK", "HAZIRLANIYOR"))
        sevk = [s for s in self.data["shipments"] if s["durum"] == "SEVK_EDILDI"]
        uretim_ton = sum(l.get("netTon", 0.0) for l in self.data["lots"]
                         if l["durum"] == "TAMAMLANDI")
        fire_ton = sum(l.get("fireTon", 0.0) for l in self.data["lots"]
                       if l["durum"] == "TAMAMLANDI")
        butce = self.data["budgets"][0] if self.data["budgets"] else {}
        temel = M.kpi_snapshot(
            ciro=ciro, alacak=alacak, borc=borc, acik_siparis=acik,
            uretim_ton=uretim_ton, fire_ton=fire_ton,
            butce_plan=butce.get("plan", 0.0),
            butce_gercek=butce.get("gercek", 0.0),
        )
        # §13 ek göstergeler
        temel.update({
            "tedarikci_sayisi": len(self.data["suppliers"]),
            "musteri_sayisi": len(self.data["customers"]),
            "sevkiyat_sayisi": len(sevk),
            "acik_bildirim": sum(1 for n in self.data["notifications"]
                                 if not n.get("okundu")),
            "outbox_kuyruk": sum(1 for o in self.data["outbox"]
                                 if o["durum"] == "kuyrukta"),
            "stok_degeri": round(sum(
                self._stok_miktar(m["id"]) * m["birimFiyat"]
                for m in self.data["materials"]), 2),
            "acik_lot": sum(1 for l in self.data["lots"] if l["durum"] == "ACIK"),
        })
        return temel

    def stok_durumu(self) -> list[dict]:
        """Stok durumu (§5 ekran 7): mevcut, rezerve, kritik eşik, değer."""
        sonuc = []
        for m in self.data["materials"]:
            mevcut = self._stok_miktar(m["id"])
            rezerve = sum(r["miktarTon"] for r in self.data["reservations"]
                          if r["malzeme"] == m["id"] and r["durum"] == "AKTIF")
            sonuc.append({
                "malzeme": m["id"], "ad": m["ad"], "birim": m["birim"],
                "mevcut": mevcut, "rezerve": rezerve,
                "kullanilabilir": round(mevcut - rezerve, 3),
                "kritikEsik": m["kritikEsik"],
                "kritik": mevcut < m["kritikEsik"],
                "stokDegeri": round(mevcut * m["birimFiyat"], 2),
            })
        # Mamul stoğu
        mamuller = set()
        for l in self.data["lots"]:
            mamuller.add(l["urun"])
        for urun in sorted(mamuller):
            mevcut = self._stok_miktar(f"MAMUL:{urun}")
            sonuc.append({
                "malzeme": f"MAMUL:{urun}", "ad": urun, "birim": "TON",
                "mevcut": mevcut, "rezerve": 0.0,
                "kullanilabilir": mevcut, "kritikEsik": 0.0,
                "kritik": False, "stokDegeri": 0.0,
            })
        return sonuc

    def ekran_durumu(self) -> list[dict]:
        """35 ekranın veri doluluk durumu — 'her fonksiyon test edildi mi?'."""
        eslesme = {
            "Panel": self.kpi(),
            "Malzeme Tanımları": self.data["materials"],
            "Satın Alma Emirleri": self.data["purchaseOrders"],
            "Fiyat Takibi": self.data["priceHistory"],
            "Tedarikçiler": self.data["suppliers"],
            "Talep & Teklif Akışı": self.data["purchaseRequests"],
            "Stok Durumu": self.data["materials"],
            "Mal Kabul": self.data["receipts"],
            "Kırıcı & Fire": self.data["crusher"],
            "Stok Hareketleri": self.data["movements"],
            "Üretim Akışı": self.data["lots"],
            "Reçeteler": self.data["recipes"],
            "Homojenizasyon Partisi": self.data["homogenizationBatches"],
            "Olay & Arşiv": self.data["events"],
            "Makine Parkı": self.data["machines"],
            "Döküm Yolları": self.data["castingPaths"],
            "Kesim Hesap Motoru": [M.self_check()],
            "Yağ & Bakım": self.data["maintenanceEvents"],
            "PLC Durum": self.data["signalStates"] or self.data["plcConnections"],
            "Satış Siparişleri": self.data["salesOrders"],
            "Müşteriler & Cari": self.data["customers"],
            "Muhasebe & Fişler": self.data["journalEntries"],
            "Maliyet & Kârlılık": self.data["costRecords"],
            "Depo, Rezervasyon & Sayım": self.data["stockCounts"],
            "Personel & Vardiya": self.data["users"],
            "Sevkiyat & Onaylar": self.data["shipments"],
            "Arşiv": self.data["events"],
            "Raporlar & İstatistik": [self.kpi()],
            "Entegrasyon Matrisi": self.data["integrationRules"],
            "Simülasyon Bağlantısı": self.data["plcConnections"],
            "Saha Kurulum Sihirbazı": self.data["setupDrafts"],
            "Modül Kaydı": self.data["moduleRegistry"],
            "Merkezi Yönetim": self.data["plants"],
            "Bildirimler & Kuyruk": self.data["notifications"],
            "Ayarlar": self.data["settings"],
        }
        sonuc = []
        for no, ad, grup in EKRANLAR:
            veri = eslesme.get(ad, [])
            adet = len(veri) if isinstance(veri, list) else 1
            sonuc.append({
                "no": int(no), "ekran": ad, "grup": grup, "kayit": adet,
                "dolu": adet > 0,
            })
        return sonuc

    def durum(self) -> dict:
        """Tek çağrıda tüm ERP görünümü (ERP panelini beslemek için)."""
        return {
            "kpi": self.kpi(),
            "varlik_sayisi": len(VARLIKLAR),
            "varliklar": {k: len(v) for k, v in self.data.items()},
            "ekranlar": self.ekran_durumu(),
            "mizan": self.mizan(),
            "bakim": self.bakim_durumu(),
            "stok": self.stok_durumu(),
        }
