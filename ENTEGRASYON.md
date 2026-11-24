# ERP'yi Simülasyona Bağlama — Entegrasyon Rehberi

Bu doküman, **kendi ERP sisteminden** (port 8080'de çalışan ERP Studio) bu
simülasyona nasıl bağlanacağını adım adım anlatır. Simülasyon artık
**ERP'nin bütün zincirini test edebileceğin** bir ortam.

---

## 1. Önce şunu bil: iki ayrı bağlantı var

```
   ┌─────────────────┐         ┌──────────────────────┐
   │   ERP Studio    │◄───────►│  Fırın Simülasyonu   │
   │   :8080         │  REST   │  :8000               │
   └─────────────────┘         └──────────────────────┘
            ▲                             │
            │                             │ OPC UA :4840
            │                             ▼
   ┌─────────────────┐              (gerçek PLC yerine)
   │  Edge Ajanı     │
   │  :8787          │
   └─────────────────┘
```

| Bağlantı | Yön | Ne için | Bu sistemde |
|----------|-----|---------|-------------|
| **ERP → Simülasyon (REST)** | ERP okur + yazar | Fırın durumu okuma, emir verme | ✅ Hazır (`:8000/api/*`) |
| **Edge → Simülasyon (REST)** | Edge okur | Dört sinyal + telemetri toplama | ✅ Hazır |
| **Simülasyon → OPC UA server** | Simülasyon yayınlar | Gerçek PLC taklidi | ✅ Hazır (`:4840`) |
| **ERP → Simülasyon (OPC UA client)** | ERP okur | PLC gibi okuma | ✅ Hazır (`:4840`) |

> **Önemli:** Dokümanındaki kural gereği gerçek fabrikada ERP **PLC'ye yazmaz**.
> Simülasyonda ise test edebilmen için **yazma yönünü** açtık — ama
> **varsayılan kapalıdır** ve `ERP_PLC_WRITE=1` ile açılır. Yani ERP'ndeki
> "yazma" kodunu test edebilirsin ama üretimde aynı kod kapalı çalışır.

---

## 2. Simülasyonu başlatma

```bash
# Test modu: PLC yazma açık + 25x hız
ERP_PLC_WRITE=1 SIM_SPEED=25 ./start.sh 25
```

veya çift tıkla: `Baslat.bat` / `Baslat.command` (yazma kapalı, salt okuma)

| Ortam değişkeni | Varsayılan | Ne yapar |
|-----------------|-----------|----------|
| `ERP_PLC_WRITE` | `0` (kapalı) | `1` → `/api/plc/*` yazma uçları çalışır |
| `SIM_SPEED` | `1` | Simülasyon hız çarpanı (1, 10, 25, 50) |

Arayüzün sağ üstündeki **hız düğmeleri** ile de hız değiştirilebilir (yeniden
başlatmadan).

**Doğrula:** tarayıcıda <http://localhost:8000> aç → Üstte yeşil nokta,
altta **🧪 Test Konsolu** görünmeli.

---

## 3. Hazır uçlar (ERP'nin bağlanacağı adresler)

Temel adres: `http://localhost:8000`

### 3.1 Sağlık ve meta — **ERP önce bunu çağırmalı**

```http
GET /api/meta
```

```json
{
  "health": true,
  "quality": "GOOD",
  "offline": false,
  "stale": false,
  "sensor_fault": false,
  "note": "",
  "sim_speed": 25.0,
  "plc_write": true,
  "furnaces": ["Aluminyum Eritme Fırını", "Homojenizasyon Fırını", "Biyet Isıtma Fırını"],
  "version": "2.0-test"
}
```

ERP'nin uygulaması gereken kural:

| Alan | Değer | ERP ne yapmalı |
|------|-------|----------------|
| `health` | `false` | Bağlantı yok say; son bilinen veriyi `stale` işaretle |
| `quality` | `GOOD` | Normal işle |
| `quality` | `STALE` | Veriyi göster ama **"bayat"** etiketle, karar verme |
| `quality` | `BAD` | Veriyi **kullanma**, uyarı göster |
| `plc_write` | `false` | Yazma denemesi yapma; sadece oku |

### 3.2 Fırın durumu (okuma)

```http
GET /api/furnaces
GET /api/furnaces/{ad}
```

```json
{
  "Aluminyum Eritme Fırını": {
    "name": "Aluminyum Eritme Fırını",
    "temperature": 723.4,
    "target_temperature": 700.0,
    "max_temperature": 850.0,
    "status": "ISINIYOR",
    "status_kodu": "HEATING",
    "burner_on": true,
    "gas_consumption": 120.0,
    "energy_total": 18.32,
    "cycle_time": 612.0,
    "alarm": null,
    "order_id": "PLC-1795522-1",
    "quality": "GOOD",
    "simulated": true
  }
}
```

**Kalite kuralı:** `simulated: true` olan veri **gerçek ölçüm değildir**.
Dokümanın §4.1'deki kurala uy: bunu `SIMULATED` etiketiyle sakla.

`status` değerleri: `KAPALI`, `ISINIYOR`, `BEKLETIYOR`, `SOGUYOR`, `ALARM`

### 3.3 Dört kontrol sinyali (doküman §8.1)

```http
GET /api/plc/signals
```

```json
{
  "Aluminyum Eritme Fırını": {
    "running": true,
    "casting": false,
    "alarm": false,
    "door": null
  }
}
```

`door: null` → simülasyonda kapı sensörü **yoktur**; `unknown` olarak işle
(doküman §15.1/6'daki gerçek kısıt).

### 3.4 SCADA benzeri tam görüntü

```http
GET /api/plc/snapshot
```

Sinyaller + telemetri + son 10 komut tek çağrıda. ERP'nde **"PLC Durum"**
ekranını beslemek için ideal.

### 3.5 Yazma uçları (yalnızca `ERP_PLC_WRITE=1` ile)

#### Hedef sıcaklık yaz

```http
POST /api/plc/set-target
Content-Type: application/json

{"furnace": "Aluminyum Eritme Fırını", "target": 700, "source": "ERP"}
```

✅ Başarılı:
```json
{"seq": 3, "action": "set_target", "ok": true,
 "message": "Hedef 700 °C yazıldı (önce 750 °C)"}
```

❌ Güvenlik reddi (**HTTP 400**):
```json
{"detail": "REDDEDİLDİ: 900 °C güvenlik sınırını (850 °C) aşıyor. PLC interlok devrede."}
```

> **Bunu test et!** ERP'nin hata yakalama kodunun bu 400'ü doğru göstermesi
> gerekir. Gerçek PLC de aynı şekilde reddeder.

#### Fırını başlat / durdur

```http
POST /api/plc/start
{"furnace": "Homojenizasyon Fırını", "product": "Biyet A", "duration_min": 5, "target": 560}

POST /api/plc/stop
{"furnace": "Homojenizasyon Fırını"}
```

Reddedilen durumlar (hepsi **HTTP 400**):
* Fırın meşgul → `"REDDEDİLDİ: fırın meşgul (aktif emir PLC-...)"`
* Hedef güvenlik sınırı üstü
* Fırın adı yanlış

#### Alarm onaylama (acknowledge)

```http
POST /api/plc/reset-alarm
{"furnace": "Biyet Isıtma Fırını"}
```

**Alarm mandallıdır (latched):** sıcaklık düşse bile kendiliğinden silinmez.
ERP'nin **"Alarm Onayla"** düğmesi buraya bağlanmalı.

Sıcaklık hâlâ güvenli seviyenin üstündeyse reddeder:
`"REDDEDİLDİ: sıcaklık hâlâ yüksek (520 °C)..."`

#### Sinyal yazma (test)

```http
POST /api/plc/signals
{"furnace": "Aluminyum Eritme Fırını", "signals": {"door": true, "running": true}}
```

Bilinmeyen sinyal adı → `400`.

### 3.6 Üretim emirleri

```http
GET  /api/orders
POST /api/orders
POST /api/orders/{id}/start
```

Yaşam döngüsü: `CREATED` → `RUNNING` → `COMPLETED`

```bash
curl -X POST http://localhost:8000/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"product":"Alüminyum Profili","furnace":"Aluminyum Eritme Fırını",
       "target_temp":700,"duration_min":2}'
# → {"id":"WO-20261124-0001","state":"CREATED"}
```

> **Süre kuralı:** `duration_min` **hedef sıcaklığa ulaştıktan sonra** işler.
> Belgede tamamlanan emir `finished_at`, `energy_total_m3`, `cycle_time_s`
> ile birlikte `production_orders` tablosuna yazılır.

### 3.7 Geçmiş okumalar

```http
GET /api/readings/{furnace}?limit=200
```

### 3.8 Canlı akış (WebSocket)

```
ws://localhost:8000/api/ws
```

Saniyede 4 kez `{"type":"tick","furnaces":{...},"orders":[...]}` yayınlar.

> ⚠️ **Dokümanın §11'e göre ERP Studio WebSocket kullanmıyor** (2,5 sn'de bir
> REST ile tazeliyor). Sende de öyleyse **WebSocket'i hiç bağlama** — sadece
> REST kullan. Bu sistemde WebSocket varken de REST uçları aynı veriyi verir.

---


---

## 3b. ERP İŞ FONKSİYONLARI — 59 varlık, 35 ekran, 18 hesap motoru

Yukarıdaki fırın uçları makine verisini verir. **Bu bölüm ise ERP'nin ticari
zincirinin tamamıdır** — personel, satış, maliyet, kâr, stok, satın alma,
muhasebe, bakım. Dokümanındaki her fonksiyonu burada sınayabilirsin.

Temel adres: `http://localhost:8000/api/erp`

### 3b.1 Ne var?

| Ölçü | Sayı | Doğrulama |
|------|------|-----------|
| Varlık (koleksiyon) | **59** | `GET /api/erp/meta` |
| Ekran | **35** | `GET /api/erp/ekranlar` |
| Modül | **15** | `GET /api/erp/meta` |
| Hesap motoru | **18** | `GET /api/erp/meta` |
| Hesap planı | **12** (100–740) | `GET /api/erp/accounts` |

Veri tek dosyada: `erp_sim_data.json`. Silersen demo verisi yeniden kurulur.
Sıfırlamak için: `POST /api/erp/sistem/sifirla`

### 3b.2 Tek çağrıda her şey

```http
GET /api/erp/durum
```

```json
{
  "kpi": {"ciro": 16000, "alacak": 384200, "borc": 27600,
          "uretim_ton": 14, "fire_orani_yuzde": 2.86,
          "stok_degeri": 147200, "sevkiyat_sayisi": 1, ...},
  "varlik_sayisi": 59,
  "varliklar": {"plants": 1, "machines": 8, "lots": 3, ...},
  "ekranlar": [{"no": 1, "ekran": "Panel", "dolu": true}, ...],
  "mizan": {"denk": true, "satirlar": [...]},
  "bakim": [{"makineKod": "MCH-30", "yuzde": 82.4, "seviye": "yaklasiyor"}],
  "stok": [{"malzeme": "MAT-0001", "mevcut": 30000, "kritik": false}]
}
```

### 3b.3 Her varlığı okuma

59 koleksiyonun her biri `GET /api/erp/{koleksiyon}` ile okunur:

```bash
curl http://localhost:8000/api/erp/materials
curl http://localhost:8000/api/erp/customers
curl http://localhost:8000/api/erp/journalEntries
curl http://localhost:8000/api/erp/lots
curl http://localhost:8000/api/erp/lots/LOT-0001      # tek kayıt
```

Geçerli koleksiyon adları `GET /api/erp/meta` → `varliklar` alanında listelenir.

### 3b.4 Satın Alma zinciri (§6.1)

Talep → teklif → teklif seçimi → emir → onay → mal kabul → fatura.

```bash
# 1) Talep aç
curl -X POST http://localhost:8000/api/erp/satin-alma/talep \
  -H 'Content-Type: application/json' \
  -d '{"malzeme":"MAT-0001","miktar":5000,"gerekce":"Üretim ihtiyacı"}'
# → {"id":"TLP-0001","durum":"ACIK",...}

# 2) İki tedarikçiden teklif al
curl -X POST .../satin-alma/teklif \
  -d '{"talep_id":"TLP-0001","tedarikci":"SUP-0001","birim_fiyat":2.40}'
curl -X POST .../satin-alma/teklif \
  -d '{"talep_id":"TLP-0001","tedarikci":"SUP-0002","birim_fiyat":2.25}'

# 3) Ucuz olanı seç → emir taslağı doğar
curl -X POST .../satin-alma/teklif-sec -d '{"teklif_id":"TKF-0002"}'
# → {"id":"SAE-0001","durum":"TASLAK","toplam":11250}

# 4) Onayla (onaysız mal kabul REDDEDİLİR)
curl -X POST .../satin-alma/onayla -d '{"emir_id":"SAE-0001"}'

# 5) Mal kabul: brüt/fire/net ayrı
curl -X POST .../satin-alma/mal-kabul \
  -d '{"emir_id":"SAE-0001","brut":5200,"fire":200}'
# → {"brut":5200,"fire":200,"net":5000,"fireOraniYuzde":3.85}

# 6) Alış faturası → 150+191 borç, 320 alacak
curl -X POST .../satin-alma/fatura -d '{"emir_id":"SAE-0001"}'
# → {"fatura":{"net":11500,"kdv":2300,"genelToplam":13800},"fis":{"balanced":true}}
```

**Test etmen gereken hatalar:**

| Durum | Beklenen |
|-------|----------|
| Olmayan malzeme | `400` "Malzeme bulunamadı" |
| Negatif miktar | `400` "miktar pozitif olmalı" |
| Onaysız emre mal kabul | `400` "emir TASLAK durumunda; önce onaylanmalı" |
| Fire > brüt | `400` "fire 0 ile brüt arasında olmalı" |

### 3b.5 Üretim zinciri (§6.2)

Reçete → lot (döküm kodu) → 8 aşama → mamul stok + yan ürün + maliyet.

```bash
# Lot aç
curl -X POST .../uretim/lot \
  -d '{"recete_id":"RCP-0001","firin_makine":"MCH-01"}'
# → {"id":"LOT-0001","kod":"LOT-261124-0001","asama":"Ergitme"}

# Aşama ilerlet (7 kez: Ergitme→Döküm→...→Sevkiyat)
for i in $(seq 7); do
  curl -X POST .../uretim/asama -d '{"lot_id":"LOT-0001"}'
done

# Tamamla → mamul stoğa girer
curl -X POST .../uretim/tamamla \
  -d '{"lot_id":"LOT-0001","net_ton":14,"fire_ton":0.4}'

# Maliyet (5 kalem: hammadde, enerji, sarf, işçilik, fire)
curl -X POST .../uretim/maliyet \
  -d '{"lot_id":"LOT-0001","enerji":3500,"sarf":800,"iscilik":2200}'
# → {"toplam":53526,"ton_maliyet":3823.29,"kg_maliyet":3.8233}
```

**Aşama atlanamaz:** `Ergitme`den `Testere`ye atlarsan `400` alırsın.
**Hedef tonaj aşımı:** 14 tonluk lota 20 ton → `400`.

Homojenizasyon (§5/13):

```bash
curl -X POST .../uretim/homojenizasyon \
  -d '{"lot_id":"LOT-0001","recete_id":"HRC-0001","hedef_sicaklik":560,"hedef_sure_dk":8}'
curl -X POST .../uretim/homojenizasyon-tamamla \
  -d '{"parti_id":"HOM-0001","gercek_sure_dk":9.5,"gercek_sicaklik":558}'
# → "sure_kontrol": {"fark_dk": 1.5, "asildi": true, "sapma_yuzde": 18.75}
```

### 3b.6 Satış + Sevkiyat (§6.3)

**Kredi kontrolü** sipariş anında yapılır:

```bash
curl -X POST .../satis/siparis \
  -d '{"musteri":"CUS-0003","urun":"6063 Alüminyum Biyet","miktar_ton":8,"birim_fiyat":3500}'
# CUS-0003: limit 150.000, bakiye 142.000 → 28.000 TL yeni → REDDEDİLİR
# → 400 "kredi limiti aşılıyor: limit 150000, mevcut 142000, yeni 28000 → aşılan 20000 TL"
```

**İki kademeli sevkiyat — tek işlem 8 kayıt:**

```bash
curl -X POST .../sevkiyat/hazirla -d '{"siparis_id":"SSP-0001"}'
# → {"id":"SVK-0001","durum":"HAZIRLANIYOR"}

# 1. onay — sadece hazırlık
curl -X POST .../sevkiyat/onayla -d '{"sevkiyat_id":"SVK-0001"}'
# → {"asama":1,"mesaj":"1. onay alındı; fiili çıkış için 2. onay gerekli"}

# 2. onay — fiili çıkış, 8 kayıt
curl -X POST .../sevkiyat/onayla \
  -d '{"sevkiyat_id":"SVK-0001","plaka":"34 TEST 01","client_id":"SEVK-001"}'
```

```json
{
  "asama": 2,
  "kayit_sayisi": 8,
  "uretilen": {
    "stok_cikis": true,
    "fatura": "FTR-0001",
    "fis": "FIS-0001",
    "cari_bakiye": 129800.0,
    "kost_yansimasi": 19116.45,
    "karlilik": {"gelir": 16000, "maliyet": 19116.45,
                 "brut_kar": -3116.45, "marj_yuzde": -19.48},
    "bildirim": true,
    "outbox": true,
    "olay": true
  }
}
```

**Idempotency — en kritik test:** Aynı `client_id` ile tekrar gönder:

```bash
curl -X POST .../sevkiyat/onayla \
  -d '{"sevkiyat_id":"SVK-0001","client_id":"SEVK-001"}'
# → {"tekrar": true, "mesaj": "Bu onay zaten işlenmiş (idempotent)"}
```

Yeni fatura oluşmaz, stok ikinci kez düşmez. Bunu ERP'nde **mutlaka** test et:
ağ tekrar denemesi yaptığında çift fatura kesilmemeli.

### 3b.7 Muhasebe (§7.3)

```bash
curl http://localhost:8000/api/erp/finans/mizan
```

```json
{
  "denk": true,
  "toplam_borc": 46800.0,
  "toplam_alacak": 46800.0,
  "satirlar": [
    {"hesap": "120", "hesap_adi": "Alıcılar", "borc": 19200, "alacak": 0, "taraf": "BORC"},
    {"hesap": "600", "hesap_adi": "Yurt İçi Satışlar", "borc": 0, "alacak": 16000, "taraf": "ALACAK"},
    {"hesap": "391", "hesap_adi": "Hesaplanan KDV", "borc": 0, "alacak": 3200, "taraf": "ALACAK"}
  ]
}
```

**Dönem kapanışı mizan kontrolü yapar:**

```bash
curl -X POST .../finans/donem-kapat -d '{"donem":"2026-11","onay":false}'
# → 400 "dönem kapanışı onay gerektirir (onay=true)"

curl -X POST .../finans/donem-kapat -d '{"donem":"2026-11","onay":true}'
# → {"id":"DKN-0001","mizanDenk":true,"butceSapma":...}
```

**Tahsilat/ödeme** bakiye kontrolü yapar:

```bash
curl -X POST .../finans/odeme \
  -d '{"tip":"TAHSILAT","taraf":"CUS-0002","tutar":1000}'
# bakiye 97.000 → 96.000

curl -X POST .../finans/odeme \
  -d '{"tip":"TAHSILAT","taraf":"CUS-0002","tutar":999999}'
# → 400 "tahsilat bakiye üstünde: bakiye 96000.00, tahsilat 999999.00"
```

### 3b.8 Stok, sayım, kırıcı (§6.4)

```bash
curl http://localhost:8000/api/erp/stok/durum
# her malzeme: mevcut, rezerve, kritik eşik, stok değeri

# Sayım — fark varsa düzeltme hareketi + fiş üretir
curl -X POST .../stok/sayim -d '{"malzeme":"MAT-0003","sayilan":388}'
# → {"sistemMiktar":400,"sayilanMiktar":388,"fark":-12,"durum":"FARK_VAR"}

# Kırıcı — 4 kader: TEKRAR_FIRIN / DONGUSEL / SATIS / ATIK
curl -X POST .../stok/kirici \
  -d '{"lot_id":"LOT-0001","miktar_ton":0.5,"kader":"TEKRAR_FIRIN"}'
```

### 3b.9 Personel, bakım, KPI

```bash
# Personel & vardiya (bordro kapsam dışı)
curl http://localhost:8000/api/erp/personel/vardiya
curl -X POST .../personel -d '{"ad":"Ali Veli","rol":"Operatör","vardiya":"16:00-00:00"}'

# Bakım — yağ/bıçak ömrü, eşik, sayaç sıfırlama
curl http://localhost:8000/api/erp/bakim/durum
# → [{"makineKod":"MCH-30","kaynak":"yağ","yuzde":82.4,
#     "seviye":"yaklasiyor","bakim_gerekli":false}]
curl -X POST .../bakim/kaydet \
  -d '{"makine_kod":"MCH-30","tip":"bıçak değişimi","notu":"Periyodik"}'
# → sayaç 0'a döner

# KPI — §13'teki tüm göstergeler
curl http://localhost:8000/api/erp/kpi
```

### 3b.10 Hesap motorları (§7.1–7.4)

Dokümanındaki 18 saf fonksiyon. **Dokümanda yazan sayıları birebir üretir:**

```bash
curl http://localhost:8000/api/erp/hesap/self-check
```

```json
{
  "dokum_6300_kg": 423.29,   "dokuman_bekliyor": 423.29,
  "mamul_6000_kg": 403.13,   "dokuman_bekliyor": 403.13,
  "kafa_300_kg": 20.16,      "dokuman_bekliyor": 20.16,
  "talas_3_kg": 0.202,       "dokuman_bekliyor": 0.202,
  "uyumlu": true
}
```

Diğer motorlar:

```bash
# Kesim raporu (kafa, talaş, fire, net biyet, geometri kontrolü)
curl -X POST .../hesap/kesim \
  -d '{"kafa_adedi":2,"kesim_sayisi":2,"tonaj_kg":420}'
# → "geometry_check": {"fark_yuzde": 9.8, "uygun": false}

# Kredi kontrolü
curl -X POST .../hesap/kredi -d '{"limit":50000,"kullanilan":30000,"yeni_tutar":25000}'
# → {"onay":false,"asilan":5000}

# Döküm kodu maliyeti
curl -X POST .../hesap/maliyet \
  -d '{"hammadde":12000,"enerji":3500,"sarf":800,"iscilik":2200,"fire":1500,"net_ton":14}'
# → {"toplam":20000,"ton_maliyet":1428.57,"kalem_paylari":{...}}

# Bir belgeden doğacak kayıtlar (§6.3 tablosu)
curl -X POST .../hesap/posting-effects -d '{"belge_tipi":"sevkiyat","tutar":10000}'
# → {"kayit_sayisi":8,"uretilen_kayitlar":[...],"fis_dengeli":true}
```

### 3b.11 Fırın simülasyonu ↔ ERP bağlantısı

Fırın sinyalleri **otomatik olarak** ERP modeline akar (doküman §8/§11):

```bash
curl http://localhost:8000/api/erp/signalStates
```

```json
[{"firin": "Aluminyum Eritme Fırını", "door": null, "casting": false,
  "alarm": false, "running": true, "sicaklik": 723.4, "hedef": 750,
  "kalite": "SIMULATED", "ts": 1795522775}]
```

- **5 saniyede bir** güncellenir (her tikte yazmak dosyayı şişirirdi)
- `door: null` → simülasyonda kapı sensörü yok (doküman §15.1/6: `unknown`)
- `kalite: "SIMULATED"` → gerçek ölçüm gibi raporlanmaz (doküman §8.2)
- Telemetri ayrı koleksiyonda: `GET /api/erp/telemetry`

### 3b.12 Arayüzdeki ERP paneli

Arayüzün altında **🏢 ERP İş Zinciri** var. 8 sekme:

| Sekme | Ne yapar |
|-------|----------|
| **Satın Alma** | Talep aç (otomatik teklif+seçim), emri onayla, mal kabul + fatura |
| **Üretim** | Lot aç, 8 aşamayı tek tek ilerlet, tamamla, maliyet |
| **Satış** | Kredi kontrollü sipariş, kâr hesabı |
| **Sevkiyat** | Hazırla → 1. onay → 2. onay (8 kayıt) |
| **Muhasebe** | Canlı mizan, denklik kontrolü |
| **Stok** | Mevcut/rezerve/kritik/değer |
| **Hesap Motoru** | Doküman §7.1 doğrulaması yan yana |
| **35 Ekran** | Hangi ekran dolu, kaç kayıt |

Üstte 8 KPI kartı canlı güncellenir (ciro, alacak, borç, üretim, fire,
stok değeri, açık sipariş, sevkiyat).

### 3b.13 Otomatik test — 150 test

```bash
# 1. terminal
ERP_PLC_WRITE=1 SIM_SPEED=25 python3 -m erp_backend.main

# 2. terminal
python3 tools/erp_test.py
```

```
================================================================
  SONUÇ: 150/150 test geçti
  ✓ ERP'nin her fonksiyonu test edildi.
================================================================
```

16 grup: meta, hesap motorları, tanımlar, satın alma, üretim,
homojenizasyon, stok/sayım, satış, sevkiyat, muhasebe, bakım, personel,
KPI, olay/kuyruk, idempotency, 35 ekran doluluk.

Fırın testleri ayrı: `python3 tools/system_test.py` (53 test).

### 3b.14 Senin ERP'nde neyi test etmelisin

| # | Senaryo | Uç | ERP'nde kontrol |
|---|---------|-----|-----------------|
| 1 | Talep → emir zinciri | `/satin-alma/*` | Onay izi kaydediliyor mu |
| 2 | Onaysız mal kabul | `400` | Hata gösteriliyor mu (yutulmuyor mu) |
| 3 | Fire > brüt | `400` | Doğrulama çalışıyor mu |
| 4 | Aşama atlama | `400` | Pano sıra kontrolü |
| 5 | Hedef tonaj aşımı | `400` | Tonaj uyarısı |
| 6 | **Kredi limiti aşımı** | `400` | Sipariş reddi kullanıcıya gösteriliyor mu |
| 7 | **Yetersiz stok** | `400` | Rezervasyon engeli |
| 8 | **Idempotency** | `tekrar:true` | Çift fatura kesilmiyor mu |
| 9 | Mizan denkliği | `denk:true` | Fiş dengesi raporlanıyor mu |
| 10 | Onaysız dönem kapanışı | `400` | Onay akışı |
| 11 | Bakiye üstü tahsilat | `400` | Cari kontrol |
| 12 | Sayım farkı | `fark` | Düzeltme + fiş üretiliyor mu |
| 13 | Bakım sayacı sıfırlama | `yuzde:0` | Sayaç güncelleniyor mu |
| 14 | Personel vardiya | `vardiyalar` | Gruplama doğru mu |
| 15 | **35 ekran dolu** | `/ekranlar` | Her ekran veri gösteriyor mu |
| 16 | **Kalite etiketi** | `SIMULATED` | Simülasyon verisi ayrı işaretli mi |

**En kritik 4 tanesi:** 2, 6, 8, 16. Bunlar sessizce yutulursa gerçek
fabrikada mali kayba yol açar.

---

## 4. ERP'ne ekleyeceğin istemci kodu (örnek)

Bu bir "simülasyon adaptörü" — kendi kod tabanına kopyalayabilirsin.

```python
"""ERP tarafı: simülasyona bağlanan adaptör."""
import requests  # pip install requests

BASE = "http://localhost:8000"


class SimAdapter:
    def __init__(self, base=BASE):
        self.base = base
        self.yazma_acik = False

    # -------- okuma --------

    def meta(self) -> dict:
        r = requests.get(f"{self.base}/api/meta", timeout=5)
        r.raise_for_status()
        d = r.json()
        self.yazma_acik = d["plc_write"]
        return d

    def firinlar(self) -> dict:
        """Kaliteye göre filtrelenmiş fırın durumu."""
        meta = self.meta()
        if meta["quality"] == "BAD":
            raise RuntimeError("Sensör verisi güvenilmez (BAD) — kullanma")
        r = requests.get(f"{self.base}/api/furnaces", timeout=5)
        if r.status_code == 503:
            raise ConnectionError("Simülasyon bağlantısı yok (503)")
        return r.json()

    def sinyaller(self) -> dict:
        return requests.get(f"{self.base}/api/plc/signals", timeout=5).json()

    # -------- yazma (dikkat: üretimde kapalı olmalı) --------

    def hedef_yaz(self, furnace: str, target: float):
        r = requests.post(f"{self.base}/api/plc/set-target",
                          json={"furnace": furnace, "target": target,
                                "source": "ERP"}, timeout=5)
        if r.status_code == 400:
            # Güvenlik reddi — ERP'nde kullanıcıya GÖSTER, yutma!
            raise ValueError(r.json()["detail"])
        r.raise_for_status()
        return r.json()

    def baslat(self, furnace: str, urun: str, sure_dk: float, hedef: float | None = None):
        r = requests.post(f"{self.base}/api/plc/start",
                          json={"furnace": furnace, "product": urun,
                                "duration_min": sure_dk, "target": hedef,
                                "source": "ERP"}, timeout=5)
        if r.status_code == 400:
            raise ValueError(r.json()["detail"])
        r.raise_for_status()
        return r.json()

    def alarm_onayla(self, furnace: str):
        r = requests.post(f"{self.base}/api/plc/reset-alarm",
                          json={"furnace": furnace, "source": "ERP"}, timeout=5)
        if r.status_code == 400:
            raise ValueError(r.json()["detail"])
        return r.json()

    def komutlar(self, limit=50) -> list:
        """Denetim izi: ERP ne yazdı, PLC ne cevap verdi."""
        return requests.get(f"{self.base}/api/plc/commands",
                            params={"limit": limit}, timeout=5).json()
```

Kullanım:

```python
sim = SimAdapter()
print(sim.meta())                       # sağlık + kalite
sim.hedef_yaz("Homojenizasyon Fırını", 560)
sim.baslat("Homojenizasyon Fırını", "Biyet A", 5)
try:
    sim.hedef_yaz("Aluminyum Eritme Fırını", 900)   # reddedilmeli
except ValueError as e:
    print("Beklenen ret:", e)
```

---

## 5. Test senaryoları — ERP'nde neyi denemelisin

Aşağıdaki tablo, **senin ERP'nde hangi kodu** test edeceğini söyler.

| # | Senaryo | Nasıl tetiklenir | ERP'nde ne test edilir |
|---|---------|------------------|------------------------|
| 1 | Normal okuma | `GET /api/furnaces` | Fırın kartı doğru mu dolduruluyor |
| 2 | Hedef yazma | Panel → "Yaz" / `POST /api/plc/set-target` | Yazma isteği + başarı gösterimi |
| 3 | **Güvenlik reddi** | Hedef 900 yaz (max 850) | 400 hatası **kullanıcıya gösteriliyor mu** (yutulmuyor mu) |
| 4 | **Meşgul fırın** | Aynı fırına 2. `start` | Çakışma hatası yakalanıyor mu |
| 5 | **Ağ kesintisi** | Panel → "Ağ Kesintisi" | 503 gelince sayfa çöküyor mu, `stale` etiketi koyuyor mu |
| 6 | **Bayat veri** | Panel → "Bayat Veri" | `quality: STALE` görülüyor mu; karar vermiyor mu |
| 7 | **Sensör hatası** | Panel → "Sensör Hatası" | `quality: BAD` görülüyor mu; veri **kullanılmıyor** mu |
| 8 | **Alarm** | Panel → "Aşırı Sıcaklık" | Alarm ekranı, brülör kapanması, mandal |
| 9 | **Alarm onayı** | Soğuduktan sonra "Alarm Onayla" | Ack akışı; erken onay reddi denenmeli |
| 10 | **Güç kesintisi** | Panel → "Güç Kesintisi" | Tüm fırınlar KAPALI; ERP bunu görüyor mu |
| 11 | **Kalite etiketi** | Her yanıtta `quality`/`simulated` | Simülasyon verisi `SIMULATED` olarak saklanıyor mu |
| 12 | **Denetim izi** | `GET /api/plc/commands` | ERP'nin yaptığı her yazma kayıtlı mı |
| 13 | **Emir yaşam döngüsü** | `POST /api/orders` → `start` | CREATED→RUNNING→COMPLETED doğru işleniyor mu |
| 14 | **Idempotency** | Aynı emri 2 kez başlat | İkinci istek reddediliyor mu (doküman §4.1) |
| 15 | **OPC UA okuma** | `opc.tcp://localhost:4840` | Gerçek PLC istemcin aynı veriyi okuyor mu |

### 5.1 "Neyi bozacağımı bilmiyorum" diyorsan — otomatik test

Simülasyona **bağımsız bir test aracı** ekledik. ERP'ni bağlamadan önce
sistemin kendisi sağlam mı diye bakar:

```bash
# 1. terminal
ERP_PLC_WRITE=1 SIM_SPEED=25 python3 -m erp_backend.main

# 2. terminal
python3 tools/system_test.py
```

Çıktı:

```
==============================================================
  ERP ENTEGRASYON TESTİ
==============================================================
[A] Sağlık ve meta
  ✓ GET /api/meta 200 döndü
  ...
[K] Emir yaşam döngüsü (CREATED → RUNNING → COMPLETED)
  ✓ Emir COMPLETED oldu
==============================================================
  SONUÇ: 46/46 test geçti
  ✓ Her şey çalışıyor. ERP'ni bağlayabilirsin.
==============================================================
```

**46 test** 11 grupta: sağlık, üç fırın, yazma, güvenlik reddi, çakışma,
alarm döngüsü, kesinti, kalite etiketleri, güç kesintisi, emir yaşam döngüsü,
denetim izi.

---

## 6. Arayüzdeki Test Konsolu

Arayüzün altında **🧪 Test Konsolu** var. Kod yazmadan her senaryoyu
tetikleyebilirsin:

| Düğme | Ne yapar | Beklenen davranış |
|-------|----------|-------------------|
| **Yaz** | Hedef sıcaklık gönderir | 850 üstü → kırmızı "REDDEDİLDİ" |
| **Başlat** | Fırını çalıştırır | Isınma başlar, brülör AÇIK |
| **Durdur** | Fırını kapatır | KAPALI'ya döner (alarm silinmez) |
| **Alarm Onayla** | Mandalı açar | Sıcaklık yüksekse reddeder |
| **Ağ Kesintisi** | `/api/furnaces` → 503 | "Bağlantı: KOPUK", kalite BAD |
| **Bayat Veri** | Veri donar | Kalite STALE |
| **Sensör Hatası** | Ölçüm güvenilmez | Kalite BAD, `sensor_ok=false` |
| **Aşırı Sıcaklık** | Fırını sınır üstüne çeker | ALARM, brülör kapanır |
| **Güç Kesintisi** | Tüm fırınlar KAPALI | Emirler iptal, sıcaklık düşer |
| **Temizle** | Tüm arızaları kapatır | Kalite GOOD |

"Düğmeler açık/kapalı" durumunu gösterir (basınca ikinci kez basmak kapatır).
Altta **son PLC komutları** tablosu var — ERP'nin denetim izi olarak da
kullanabilirsin.

---

## 7. Eşleme: fırın adları → makine kimlikleri

Dokümanın §11.1'deki eşlemeyi ERP'nde tanımlamalısın:

| Simülasyon fırını | Önerilen makine | Tip |
|-------------------|-----------------|-----|
| `Aluminyum Eritme Fırını` | `MCH-01` | Ergitme ocağı |
| `Homojenizasyon Fırını` | `MCH-10` | Homojenizasyon fırını |
| `Biyet Isıtma Fırını` | `MCH-02` | Yaşlandırma/ısıtma |

Eşleşmeyen fırın için veri üretme; arayüzde uyarı olarak göster.

---

## 8. Üretim kuralı: yazmayı kapat

Test bitince aynı sistemi **salt okunur** çalıştır — doküman §8:

```bash
./start.sh 10     # ERP_PLC_WRITE verilmez -> /api/plc/* yazma uçları 400 döner
```

```bash
curl -X POST http://localhost:8000/api/plc/set-target \
  -H 'Content-Type: application/json' -d '{"furnace":"X","target":700}'
# {"detail":"PLC yazma kapalı (ERP_PLC_WRITE=1 ile açılır)"}
```

ERP'nin kodu **aynı** kalır; sadece yazma denemesi reddedilir. Bu, gerçek
fabrikadaki "ERP PLC'ye yazmaz" kuralının simülasyondaki karşılığıdır.

---

## 9. OPC UA ile bağlanma (PLC gibi)

Simülasyon `opc.tcp://localhost:4840/freeopcua/server/` yayınlar.

```
Objects → Fabrika → <Fırın Adı> → <değişken>
```

Değişkenler: `anlik_sicaklik`, `hedef_sicaklik`, `maks_sicaklik`, `durum`,
`brulor_acik`, `gaz_tuketimi`, `enerji_toplam`, `evrim_suresi`, `alarm`

```python
import asyncio
from asyncua import Client

async def main():
    async with Client("opc.tcp://localhost:4840/freeopcua/server/") as c:
        fabrika = await c.nodes.root.get_child(["0:Objects", "2:Fabrika"])
        firin = await fabrika.get_child("2:Homojenizasyon Fırını")
        t = await (await firin.get_child("2:anlik_sicaklik")).get_value()
        print("Sıcaklık:", t)

asyncio.run(main())
```

> `2:` namespace index'idir; güvenli olsun dersen URI (`urn:erp-sim:plant`) ile ara.

---

## 10. Sık karşılaşılan durumlar

| Belirti | Sebep | Çözüm |
|---------|-------|-------|
| Yazma uçları `400: PLC yazma kapalı` | `ERP_PLC_WRITE` verilmemiş | `ERP_PLC_WRITE=1` ile başlat |
| `/api/furnaces` → `503` | Test Konsolu'nda "Ağ Kesintisi" açık | "Temizle" veya "Kesintiyi Bitir" |
| Kalite `BAD` | Sensör hatası veya kesinti açık | "Temizle" |
| Fırın ısınmıyor | Emir yok veya durdurulmuş | `POST /api/plc/start` |
| Emir hiç `COMPLETED` olmuyor | `duration_min` çok kısa + hız düşük | `SIM_SPEED` artır veya süreyi uzat |
| Alarm kendiliğinden silinmiyor | **Doğru davranış** (mandallı) | `reset-alarm` ile onayla |
| Sıcaklık 850'yi geçmiyor | Güvenlik özelliği | Hata değil; alarm testi için "Aşırı Sıcaklık" kullan |

---

## 11. Özet: senin yapacağın 5 adım

1. **Başlat:** `ERP_PLC_WRITE=1 SIM_SPEED=25 ./start.sh 25`
2. **Doğrula:** `python3 tools/system_test.py` → 46/46 geçmeli
3. **ERP'nde adaptör yaz:** §4'teki `SimAdapter`'ı kendi kod tabanına kopyala
4. **Bağla:** ERP Studio'da Simülasyon Bağlantısı ekranının veri kaynağını
   `http://localhost:8000` yap; eşlemeyi §7'ye göre tanımla
5. **Test et:** §5 tablosundaki 15 senaryoyu tek tek dene; her senaryoda
   ERP'nin **hata gösterip göstermediğine** bak (en kritik nokta bu)

Test bitince **yazmayı kapat** (`./start.sh 10`) ve gerçek PLC'ye geçerken
`SimAdapter`'ı OPC UA istemcisiyle değiştir. Sözleşme aynı kaldığı için
ERP'nin üst katmanlarında değişiklik gerekmez.
