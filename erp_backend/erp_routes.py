"""ERP test uçları — doküman §5'teki 35 ekranın tamamı REST'e açılır.

Bu router `/api/erp/*` altında yayınlanır. Amaç: senin ERP'ndeki her
fonksiyonu **bu simülasyona bağlayıp** sınayabilmen. Fırın uçlarından
(`/api/furnaces`, `/api/plc/*`) tamamen bağımsızdır; aynı süreçte çalışır
ama ayrı bir veri modeli kullanır (`erp_sim_data.json`).

Uç grupları:

    GET  /api/erp/meta              varlık/ekran/modül listesi
    GET  /api/erp/durum             tek çağrıda tüm ERP görünümü
    GET  /api/erp/kpi               panel göstergeleri
    GET  /api/erp/ekranlar          35 ekran doluluk durumu
    GET  /api/erp/{koleksiyon}      herhangi bir varlık listesi (59 tanesi)
    GET  /api/erp/{koleksiyon}/{id} tek kayıt

    POST /api/erp/satin-alma/talep
    POST /api/erp/satin-alma/teklif
    POST /api/erp/satin-alma/teklif-sec
    POST /api/erp/satin-alma/onayla
    POST /api/erp/satin-alma/mal-kabul
    POST /api/erp/satin-alma/fatura
    POST /api/erp/uretim/lot
    POST /api/erp/uretim/asama
    POST /api/erp/uretim/tamamla
    POST /api/erp/uretim/maliyet
    POST /api/erp/uretim/homojenizasyon
    POST /api/erp/uretim/homojenizasyon-tamamla
    POST /api/erp/stok/sayim
    POST /api/erp/stok/kirici
    POST /api/erp/satis/siparis
    POST /api/erp/satis/teklif
    POST /api/erp/sevkiyat/hazirla
    POST /api/erp/sevkiyat/onayla           (iki kademeli; clientId idempotent)
    POST /api/erp/finans/odeme
    POST /api/erp/finans/donem-kapat
    GET  /api/erp/finans/mizan
    POST /api/erp/bakim/kaydet
    GET  /api/erp/bakim/durum
    POST /api/erp/personel
    GET  /api/erp/personel/vardiya
    POST /api/erp/hesap/kesim              kesim raporu (doküman §7.1)
    POST /api/erp/hesap/kredi              kredi kontrolü
    POST /api/erp/hesap/maliyet            lot maliyeti hesabı
    POST /api/erp/hesap/kpi                KPI hesabı
    GET  /api/erp/hesap/self-check         doküman §7.1 doğrulaması
    POST /api/erp/hesap/posting-effects    bir belgeden doğacak kayıtlar
    POST /api/erp/sistem/sifirla           demo verisini sıfırla
    GET  /api/erp/sistem/varliklar         59 varlık + kayıt sayıları
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from simulator import erp_math as M
from simulator.erp_model import (EKRANLAR, MODULLER, VARLIKLAR, ErpHatası,
                                 ErpModel)

router = APIRouter(prefix="/api/erp", tags=["ERP test"])

ERP = ErpModel()


def _guvenli(fn, *args, **kwargs):
    """İş kuralı hatasını 400'e çevirir."""
    try:
        return fn(*args, **kwargs)
    except ErpHatası as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------------------------------------------------------------- modeller

class TalepIn(BaseModel):
    malzeme: str
    miktar: float
    gerekce: str = "İhtiyaç"
    istenen_tarih: Optional[str] = None
    client_id: Optional[str] = None


class TeklifIn(BaseModel):
    talep_id: str
    tedarikci: str
    birim_fiyat: float
    teslim_gun: int = 7
    gecerlilik_gun: int = 15


class TeklifSecIn(BaseModel):
    teklif_id: str


class OnayIn(BaseModel):
    emir_id: str


class MalKabulIn(BaseModel):
    emir_id: str
    brut: float
    fire: float = 0.0
    depo: str = "DEP-0001"
    client_id: Optional[str] = None


class FaturaIn(BaseModel):
    emir_id: str
    client_id: Optional[str] = None


class LotIn(BaseModel):
    recete_id: str
    firin_makine: str
    hedef_ton: Optional[float] = None
    client_id: Optional[str] = None


class AsamaIn(BaseModel):
    lot_id: str
    asama: Optional[str] = None
    client_id: Optional[str] = None


class LotTamamlaIn(BaseModel):
    lot_id: str
    net_ton: float
    fire_ton: float = 0.0
    client_id: Optional[str] = None


class MaliyetIn(BaseModel):
    lot_id: str
    enerji: float = 0.0
    sarf: float = 0.0
    iscilik: float = 0.0


class HomojenIn(BaseModel):
    lot_id: str
    recete_id: str
    hedef_sicaklik: float = 560.0
    hedef_sure_dk: float = 8.0


class HomojenTamamIn(BaseModel):
    parti_id: str
    gercek_sure_dk: float
    gercek_sicaklik: float


class SayimIn(BaseModel):
    malzeme: str
    sayilan: float
    depo: str = "DEP-0001"
    client_id: Optional[str] = None


class KiriciIn(BaseModel):
    lot_id: str
    miktar_ton: float
    kader: str = "TEKRAR_FIRIN"
    client_id: Optional[str] = None


class SiparisIn(BaseModel):
    musteri: str
    urun: str
    miktar_ton: float
    birim_fiyat: float
    teslim_tarihi: Optional[str] = None
    client_id: Optional[str] = None


class TeklifSatisIn(BaseModel):
    musteri: str
    urun: str
    miktar_ton: float
    birim_fiyat: float


class SevkiyatIn(BaseModel):
    siparis_id: str
    client_id: Optional[str] = None


class SevkiyatOnayIn(BaseModel):
    sevkiyat_id: str
    plaka: Optional[str] = None
    irsaliye_no: Optional[str] = None
    client_id: Optional[str] = None


class OdemeIn(BaseModel):
    tip: str
    taraf: str
    tutar: float
    client_id: Optional[str] = None


class DonemIn(BaseModel):
    donem: str
    onay: bool = False


class BakimIn(BaseModel):
    makine_kod: str
    tip: str = "periyodik"
    notu: str = ""
    saat: float = 0.0
    kesim: int = 0


class PersonelIn(BaseModel):
    ad: str
    rol: str
    vardiya: str = "08:00-16:00"


class KesimHesapIn(BaseModel):
    cap_mm: float = M.VARSAYILAN_CAP_MM
    dokum_boyu_mm: float = M.VARSAYILAN_DOKUM_BOYU_MM
    mamul_boyu_mm: float = M.VARSAYILAN_MAMUL_BOYU_MM
    kafa_mm: float = M.VARSAYILAN_KAFA_MM
    bicak_mm: float = M.VARSAYILAN_BICAK_MM
    yogunluk: float = M.VARSAYILAN_YOGUNLUK
    kafa_adedi: int = 2
    kesim_sayisi: int = 2
    tonaj_kg: Optional[float] = None


class KrediIn(BaseModel):
    limit: float
    kullanilan: float
    yeni_tutar: float


class MaliyetHesapIn(BaseModel):
    hammadde: float
    enerji: float = 0.0
    sarf: float = 0.0
    iscilik: float = 0.0
    fire: float = 0.0
    net_ton: float = 1.0


class KpiIn(BaseModel):
    ciro: float = 0.0
    alacak: float = 0.0
    borc: float = 0.0
    acik_siparis: int = 0
    zamaninda_teslim_orani: float = 0.0
    uretim_ton: float = 0.0
    fire_ton: float = 0.0
    butce_plan: float = 0.0
    butce_gercek: float = 0.0


class PostingIn(BaseModel):
    belge_tipi: str
    tutar: float
    kdv_orani: float = M.VARSAYILAN_KDV
    net_ton: float = 0.0
    ton_maliyet: float = 0.0


# ---------------------------------------------------------------- meta

@router.get("/meta")
async def meta():
    """ERP test ortamının yetenekleri: 59 varlık, 35 ekran, 15 modül."""
    return {
        "surum": "erp-test-1.0",
        "varlik_sayisi": len(VARLIKLAR),
        "varliklar": VARLIKLAR,
        "ekran_sayisi": len(EKRANLAR),
        "ekranlar": [{"no": int(n), "ad": a, "grup": g} for n, a, g in EKRANLAR],
        "modul_sayisi": len(MODULLER),
        "moduller": MODULLER,
        "hesap_motorlari": [
            "cylinder_mass_kg", "cutting_report", "geometry_check",
            "mass_balance_chain", "maintenance_status", "duration_check",
            "amounts", "sum_lines", "is_balanced", "build_entry",
            "sales_entry", "purchase_entry", "trial_balance", "lot_cost",
            "sales_margin", "credit_check", "kpi_snapshot", "posting_effects",
        ],
        "durum": ERP.durum(),
    }


@router.get("/durum")
async def durum():
    """Tek çağrıda tüm ERP görünümü (panel + ekranlar + mizan + stok)."""
    return ERP.durum()


@router.get("/kpi")
async def kpi():
    return ERP.kpi()


@router.get("/ekranlar")
async def ekranlar():
    return {"ekranlar": ERP.ekran_durumu(),
            "dolu": sum(1 for e in ERP.ekran_durumu() if e["dolu"]),
            "toplam": len(EKRANLAR)}


@router.get("/sistem/varliklar")
async def varliklar():
    return {k: len(v) for k, v in ERP.data.items()}


@router.post("/sistem/sifirla")
async def sifirla():
    ERP.sifirla()
    return {"mesaj": "Demo verisi sıfırlandı", "varlik_sayisi": len(VARLIKLAR)}


# ---------------------------------------------------------------- koleksiyonlar

# ---------------------------------------------------------------- §6.1 satın alma

@router.post("/satin-alma/talep")
async def satin_alma_talep(g: TalepIn):
    return _guvenli(ERP.talep_olustur, g.malzeme, g.miktar, g.gerekce,
                    g.istenen_tarih, g.client_id)


@router.post("/satin-alma/teklif")
async def satin_alma_teklif(g: TeklifIn):
    return _guvenli(ERP.teklif_ver, g.talep_id, g.tedarikci,
                    g.birim_fiyat, g.teslim_gun, g.gecerlilik_gun)


@router.post("/satin-alma/teklif-sec")
async def satin_alma_teklif_sec(g: TeklifSecIn):
    return _guvenli(ERP.teklif_sec, g.teklif_id)


@router.post("/satin-alma/onayla")
async def satin_alma_onayla(g: OnayIn):
    return _guvenli(ERP.satin_alma_onayla, g.emir_id)


@router.post("/satin-alma/mal-kabul")
async def satin_alma_mal_kabul(g: MalKabulIn):
    return _guvenli(ERP.mal_kabul, g.emir_id, g.brut, g.fire, g.depo, g.client_id)


@router.post("/satin-alma/fatura")
async def satin_alma_fatura(g: FaturaIn):
    return _guvenli(ERP.alis_faturasi, g.emir_id, g.client_id)


# ---------------------------------------------------------------- §6.2 üretim

@router.post("/uretim/lot")
async def uretim_lot(g: LotIn):
    return _guvenli(ERP.lot_ac, g.recete_id, g.firin_makine, g.hedef_ton,
                    g.client_id)


@router.post("/uretim/asama")
async def uretim_asama(g: AsamaIn):
    return _guvenli(ERP.asama_ilerlet, g.lot_id, g.asama, g.client_id)


@router.post("/uretim/tamamla")
async def uretim_tamamla(g: LotTamamlaIn):
    return _guvenli(ERP.lot_tamamla, g.lot_id, g.net_ton, g.fire_ton,
                    g.client_id)


@router.post("/uretim/maliyet")
async def uretim_maliyet(g: MaliyetIn):
    return _guvenli(ERP.lot_maliyet, g.lot_id, g.enerji, g.sarf, g.iscilik)


@router.post("/uretim/homojenizasyon")
async def uretim_homojen(g: HomojenIn):
    return _guvenli(ERP.homojenizasyon_plani, g.lot_id, g.recete_id,
                    g.hedef_sicaklik, g.hedef_sure_dk)


@router.post("/uretim/homojenizasyon-tamamla")
async def uretim_homojen_tamam(g: HomojenTamamIn):
    return _guvenli(ERP.homojenizasyon_tamamla, g.parti_id,
                    g.gercek_sure_dk, g.gercek_sicaklik)


# ---------------------------------------------------------------- §6.4 stok

@router.post("/stok/sayim")
async def stok_sayim(g: SayimIn):
    return _guvenli(ERP.sayim_yap, g.malzeme, g.sayilan, g.depo, g.client_id)


@router.post("/stok/kirici")
async def stok_kirici(g: KiriciIn):
    return _guvenli(ERP.kirici_kaydet, g.lot_id, g.miktar_ton, g.kader,
                    g.client_id)


@router.get("/stok/durum")
async def stok_durum():
    return ERP.stok_durumu()


# ---------------------------------------------------------------- §6.3 satış

@router.post("/satis/siparis")
async def satis_siparis(g: SiparisIn):
    return _guvenli(ERP.satis_siparisi, g.musteri, g.urun, g.miktar_ton,
                    g.birim_fiyat, g.teslim_tarihi, g.client_id)


@router.post("/satis/teklif")
async def satis_teklif(g: TeklifSatisIn):
    return _guvenli(ERP.teklif_hazirla, g.musteri, g.urun, g.miktar_ton,
                    g.birim_fiyat)


@router.post("/sevkiyat/hazirla")
async def sevkiyat_hazirla(g: SevkiyatIn):
    return _guvenli(ERP.sevkiyat_hazirla, g.siparis_id, g.client_id)


@router.post("/sevkiyat/onayla")
async def sevkiyat_onayla(g: SevkiyatOnayIn):
    """İki kademeli onay. 2. onayda 8 kayıt tek işlemde üretilir."""
    return _guvenli(ERP.sevkiyat_onayla, g.sevkiyat_id, g.plaka,
                    g.irsaliye_no, g.client_id)


# ---------------------------------------------------------------- finans

@router.post("/finans/odeme")
async def finans_odeme(g: OdemeIn):
    return _guvenli(ERP.odeme_kaydet, g.tip, g.taraf, g.tutar, g.client_id)


@router.get("/finans/mizan")
async def finans_mizan():
    return ERP.mizan()


@router.post("/finans/donem-kapat")
async def finans_donem(g: DonemIn):
    return _guvenli(ERP.donem_kapat, g.donem, g.onay)


# ---------------------------------------------------------------- bakım

@router.post("/bakim/kaydet")
async def bakim_kaydet(g: BakimIn):
    return _guvenli(ERP.bakim_kaydet, g.makine_kod, g.tip, g.notu, g.saat,
                    g.kesim)


@router.get("/bakim/durum")
async def bakim_durum():
    return ERP.bakim_durumu()


# ---------------------------------------------------------------- personel

@router.post("/personel")
async def personel_ekle(g: PersonelIn):
    kayit = ERP._ekle("users", {
        "ad": g.ad, "rol": g.rol, "vardiya": g.vardiya, "aktif": True,
        "bordroKapsam": False,
    })
    ERP._olay("personel", f"{g.ad} eklendi ({g.rol})", kayit["id"])
    return kayit


@router.get("/personel/vardiya")
async def personel_vardiya():
    """Vardiya planı: personeli vardiyaya göre gruplar (bordro kapsam dışı)."""
    gruplar: dict[str, list] = {}
    for u in ERP.data["users"]:
        gruplar.setdefault(u.get("vardiya", "-"), []).append({
            "id": u["id"], "ad": u["ad"], "rol": u["rol"],
            "aktif": u.get("aktif", True),
        })
    return {
        "vardiyalar": gruplar,
        "toplam_personel": len(ERP.data["users"]),
        "bordro_kapsam": False,
        "not": "Bordro kapsam dışıdır (doküman §5 ekran 25).",
    }


# ---------------------------------------------------------------- hesap motorları

@router.get("/hesap/self-check")
async def hesap_self_check():
    """Doküman §7.1'deki sayıları yeniden üretir."""
    return M.self_check()


@router.post("/hesap/kesim")
async def hesap_kesim(g: KesimHesapIn):
    return _guvenli(M.cutting_report, g.cap_mm, g.dokum_boyu_mm,
                    g.mamul_boyu_mm, g.kafa_mm, g.bicak_mm, g.yogunluk,
                    g.kafa_adedi, g.kesim_sayisi,
                    M.VARSAYILAN_TOLERANS, g.tonaj_kg)


@router.post("/hesap/kredi")
async def hesap_kredi(g: KrediIn):
    return _guvenli(M.credit_check, g.limit, g.kullanilan, g.yeni_tutar)


@router.post("/hesap/maliyet")
async def hesap_maliyet(g: MaliyetHesapIn):
    return _guvenli(M.lot_cost, g.hammadde, g.enerji, g.sarf, g.iscilik,
                    g.fire, g.net_ton)


@router.post("/hesap/kpi")
async def hesap_kpi(g: KpiIn):
    return M.kpi_snapshot(**g.model_dump())


@router.post("/hesap/posting-effects")
async def hesap_posting(g: PostingIn):
    return _guvenli(M.posting_effects, g.belge_tipi, g.tutar, g.kdv_orani,
                    g.net_ton, g.ton_maliyet)


# ---------------------------------------------------------------- joker yollar

@router.get("/{koleksiyon}")
async def koleksiyon_listesi(koleksiyon: str, limit: int = 500):
    """Herhangi bir varlığın listesi. 59 varlığın tamamı erişilebilir."""
    if koleksiyon not in ERP.data:
        raise HTTPException(
            404, f"bilinmeyen varlık: {koleksiyon}. "
                 f"Geçerli varlıklar: /api/erp/meta → varliklar")
    kayitlar = ERP.data[koleksiyon][-limit:]
    return {"koleksiyon": koleksiyon, "toplam": len(ERP.data[koleksiyon]),
            "kayitlar": kayitlar}


@router.get("/{koleksiyon}/{kid}")
async def koleksiyon_kayit(koleksiyon: str, kid: str):
    if koleksiyon not in ERP.data:
        raise HTTPException(404, f"bilinmeyen varlık: {koleksiyon}")
    for k in ERP.data[koleksiyon]:
        if k.get("id") == kid:
            return k
    raise HTTPException(404, f"{koleksiyon} içinde bulunamadı: {kid}")
