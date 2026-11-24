# erp-simulasyon-denemesi

Fabrikaya gitmeden, bilgisayar üzerinde sanal bir alüminyum fırına fabrikası kurup,
geliştirdiğin ERP sistemiyle gerçek zamanlı entegrasyonunu test edebileceğin
tek komutluk bir simülasyon ortamı.

Bu proje paylaştığın rehberdeki mimariyi aynen uygular:

```
Sanal Fırın (Python)  →  OPC UA / endüstriyel katman  →  ERP Backend (FastAPI + SQLite)
                                                       ↳ Canlı WebSocket arayüzü
```

## Ne içerir?

| Katman | İçerik | Teknoloji |
|--------|--------|-----------|
| Fırın simülasyonu | 3 sanal fırın (alüminyum eritme, homojenizasyon, biyet ısıtma), termal model, alarm, tüketim | Python |
| Endüstriyel haberleşme | Fırın değişkenlerinin OPC UA üzerinden yayımlanması | `asyncua` (OPC UA Server) |
| ERP backend | Veri alma, veritabanı kaydı, üretim emri yönetimi, Canlı WebSocket yayını | FastAPI + SQLite |
| Arayüz | Canlı fırın panoları, sıcaklık geçişi, alarmlar, üretim emri oluşturma/başlatma | HTML + JS (tek dosya, harici bağımlılık yok) |

Simüle edilen fırınlar (rehberdeki ekipmanlarla birebir):

1. **Alüminyum Eritme Fırını** — anlık/hedef sıcaklık, çalışma durumu, brülör, gaz tüketimi, eritme süresi, alarm
2. **Homojenizasyon Fırını** — iç/bölgesel sıcaklık modeli, ısıtma-bekletme çevrimi, reçete/parametre
3. **Biyet Isıtma Fırını** — biyet sıcaklığı, ısıtma süresi, ürün adedi, üretim durumu

## ERP'nin tamamını test et

Sadece fırın değil — **dokümanındaki her ERP fonksiyonu** bu simülasyonda
sınanabilir. Ayrıntı: **[ENTEGRASYON.md §3b](ENTEGRASYON.md)**

| Katman | Sayı | Örnek uç |
|--------|------|----------|
| Varlık (koleksiyon) | **59** | `/api/erp/materials`, `/api/erp/lots` |
| Ekran | **35** | `/api/erp/ekranlar` |
| Modül | **15** | `/api/erp/meta` |
| Hesap motoru | **18** | `/api/erp/hesap/self-check` |

### İş zincirleri

| Zincir | Adımlar |
|--------|---------|
| **Satın Alma** | talep → teklif → teklif seç → emir → onay → mal kabul → fatura |
| **Üretim** | reçete → lot → 8 aşama → mamul stok + yan ürün + maliyet |
| **Satış** | kredi kontrolü → sipariş → rezervasyon |
| **Sevkiyat** | hazırla → 1. onay → 2. onay (**8 kayıt tek işlemde**) |
| **Muhasebe** | fiş → mizan → dönem kapanışı → tahsilat/ödeme |
| **Stok** | sayım farkı → düzeltme + fiş, kırıcı (4 kader) |

### Arayüzde ERP paneli

Arayüzün altında **🏢 ERP İş Zinciri** — 8 sekme, 8 canlı KPI kartı.
Kod yazmadan tüm zinciri tıklayarak deneyebilirsin.

### Test

```bash
python3 tools/erp_test.py     # 150 test / 16 grup — ERP fonksiyonları
python3 tools/system_test.py  #  53 test / 14 grup — fırın + PLC
```

---

## Test modu: ERP'nin bütün zincirini dene

Bu simülasyon artık **salt izleme** değil — ERP'ndeki her davranışı
sınayabileceğin bir test ortamı. Ayrıntılı rehber: **[ENTEGRASYON.md](ENTEGRASYON.md)**

### Hızlı başlangıç

```bash
# Test modu: PLC yazma açık, 25x hız
ERP_PLC_WRITE=1 SIM_SPEED=25 ./start.sh 25
```

Arayüzün altındaki **🧪 Test Konsolu** ile kod yazmadan:

| Düğme | Tetiklediği senaryo |
|-------|---------------------|
| Yaz / Başlat / Durdur / Alarm Onayla | ERP → PLC yazma komutları |
| Ağ Kesintisi | 503 servis yok (bağlantı koptu) |
| Bayat Veri | `quality: STALE` |
| Sensör Hatası | `quality: BAD`, `sensor_ok: false` |
| Aşırı Sıcaklık | Mandallı ALARM + brülör kapanır |
| Güç Kesintisi | Tüm fırınlar KAPALI |
| Temizle | Tüm arızaları sıfırlar |

### Test yazma uçları

| Uç | Ne yapar |
|----|----------|
| `POST /api/plc/set-target` | Hedef sıcaklık yaz (güvenlik sınırı dışı → 400) |
| `POST /api/plc/start` | Emir vererek fırını başlat (meşgulse → 400) |
| `POST /api/plc/stop` | Fırını durdur (alarm silinmez) |
| `POST /api/plc/reset-alarm` | Mandallı alarmı onayla (sıcakken → 400) |
| `POST /api/plc/signals` | Sinyal yaz (test) |
| `GET /api/plc/commands` | Denetim izi: kim ne yazdı, PLC ne cevap verdi |
| `GET /api/meta` | Sağlık + veri kalitesi + yetenekler |

Yazma uçları **varsayılan kapalıdır**; `ERP_PLC_WRITE=1` ile açılır. Kapalıyken
400 döner ve ERP'ndeki "PLC'ye yazma" kodunun hata yakalama yolunu test edebilirsin.

### Sistem kendi kendini sınasın

```bash
python3 tools/system_test.py     # 46 test, 11 grup, ~35 saniye
```

### Fırınlar artık aynı şekilde çalışıyor

Eskiden varsayılan 750 °C hedef, max 620 °C'lik Homojenizasyon Fırınında alarm
tetikleyip fırını kapatıyordu; ayrıca doğrusal ısınma eğrisi hedefe hiç
ulaşmıyordu. İkisi de düzeltildi:

| Fırın | Max | Hedefe ulaşma |
|-------|-----|---------------|
| Alüminyum Eritme | 850 °C | ~12 sim-dakikası |
| Homojenizasyon | 620 °C | ~12 sim-dakikası |
| Biyet Isıtma | 540 °C | ~12 sim-dakikası |

Arayüz artık fırın seçilince hedefi otomatik olarak o fırının güvenli
değerine çekiyor ve `fill_minutes` ile kalibre edilmiş üstel ısınma modeli
kullanıyor — 1x, 10x, 25x, 50x hızda sonuç aynı.

---

## Gereksinim: Python 3.10 veya üzeri

Bu proje `Optional[...]` yerine yeni tip sözdizimini kullanmıyor, ama
FastAPI/pydantic 3.10+ istiyor. macOS'un sistem Python'u genelde **3.9**'dur
ve şu hatayı verir:

```
TypeError: Unable to evaluate type annotation 'dict | None'
```

**Çözüm (macOS):**

```bash
# 1. Python 3.12 kur
brew install python@3.12
#   veya https://www.python.org/downloads/ adresinden indir

# 2. Eski sanal ortamı sil (3.9 ile kurulmuştu)
cd ~/Documents/GitHub/erp-simulasyon-denemesi
rm -rf .venv

# 3. Baslat.command'a tekrar çift tıkla — yeni sürümle kurulur
```

Sürüm kontrolünü **`Baslat.command` kendisi yapıyor**: 3.10+ bulamazsa
anlaşılır bir mesaj verir, traceback göstermez. `.venv` eski Python ile
kurulmuşsa otomatik silip yeniden kurar.

Sürümü kontrol etmek için: `python3 -V`

---

## Kurulum ve çalıştırma

### En kolay yol: çift tıkla (terminal yok)

| İşletim sistemi | Çift tıklanacak dosya | Not |
|-----------------|------------------------|-----|
| **Windows** | `Baslat.bat` | **Python 3.10+** kurulu olmalı |
| **Windows** | `ERP_Simulasyon.exe` | Python bile gerekmez (Actions ile derlenir) |
| **macOS** | `Baslat.command` | İlk sefer `chmod +x Baslat.command` |
| **Linux** | `Baslat.sh` | İlk sefer `chmod +x Baslat.sh` |

Çift tıkladığında: ilk seferde paketler kurulur (1-3 dk), sonra sunucu başlar
ve **tarayıcı kendiliğinden** `http://localhost:8000` adresinde açılır.
Terminale hiçbir şey yazman gerekmez. Kapatmak için pencereyi kapat.

Ayrıntılı anlatım: [`README_CIFT_TIKLA.txt`](README_CIFT_TIKLA.txt)

### `.exe` dosyasını nereden alırım?

GitHub → **Actions** → **"Uygulama Derle"** → **Run workflow** →
bitince çalışmanın altındaki **Artifacts** bölümünden
`ERP_Simulasyon-Windows` zip'ini indir, içindeki `.exe`'ye çift tıkla.

Kendi bilgisayarında derlemek istersen:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean erp_launcher.spec
# çıktı: dist/ERP_Simulasyon(.exe)
```

### Terminal sevenler için

```bash
./start.sh 10      # 10 kat hızlı — demo/test için ÖNERİLEN
```

veya gerçek zamanlı (gerçekçi ama yavaş):

```bash
./start.sh         # 1x = gerçek zamanlı
```

Sonra tarayıcıda **http://localhost:8000** adresini aç.

> **Hız çarpanı neden önemli?** 1x hızda bir fırının 750 °C'ye çıkması ~10 dakika,
> `900 °C` alarm testi ~**30 dakika** sürer. `./start.sh 10` ile aynı senaryolar
> ~10 kat kısa sürede tamamlanır. Fizik modeli (ısıtma eğrisi, reçete, alarm
> eşiği) değişmez — sadece zaman hızlı akar.

| Hız | 750 °C'ye çıkış | Alarm testi (900 °C) | Ne zaman kullan |
|-----|-----------------|----------------------|-----------------|
| `1x` (varsayılan) | ~10 dk | ~30 dk | Gerçek fabrikaya benzer davranış |
| `10x` | ~1 dk | ~3 dk | Demo, test, "hemen göreyim" |
| `25x` | ~25 sn | ~1 dk | Sadece hızlı deneme |

`start.sh` şunları yapar:

1. Gerekli Python paketlerini bir sanal ortama (`.venv`) yükler (`fastapi`, `uvicorn`, `asyncua`, `sqlalchemy`).
2. Sanal fabrika simülasyonunu başlatır (fırın durumları sürekli güncellenir).
3. OPC UA sunucusunu açar: `opc.tcp://localhost:4840/freeopcua/server/`
4. ERP arayüzünü açar: **http://localhost:8000**

> `start.sh` olmadan doğrudan: `SIM_SPEED=10 .venv/bin/python -m erp_backend.main`

### Arayüzde neler yapabilirsin?

- **Fırın kartları:** Anlık sıcaklık, hedef sıcaklık, durum (KAPALI/ISINIYOR/BEKLETIYOR/ALARM), brülör açık/kapalı, gaz tüketimi, kümülatif enerji, çevrim süresi, küçük geçiş grafiği.
- **Üretim emirleri:** Yeni sipariş oluştur (ürün, fırın, hedef sıcaklık, süre), fırına ata ve "Başlat" ile çevrimi başlat. Sıcaklık hedefe ulaştığında bekletmeye, süre dolduğunda emir TAMAMLANDI olarak geçer.
- **Alarmlar:** Aşırı sıcaklık (850 °C üstü) anında alarm döner ve brülör kapanır.
- **Canlılık:** Sağ üstteki nokta **yeşil**ken canlı veri akışı aktif demektir. Nokta **gri/turuncu** ise sayfa yenilenmez; panoya 3 saniyede bir REST üzerinden veri gelmeye devam eder ve bağlantı arka planda yeniden denenir. **Yeniden bağlan** butonuyla elle de deneyebilirsin.
- **Hız kontrolü (sağ üst):** `1x / 2x / 5x / 10x / 25x / 50x` düğmeleriyle simülasyon hızını **canlı** değiştir. Yeniden başlatmak gerekmez; düğme anında etki eder (fizik modeli aynı kalır, sadece zaman hızlı akar).

> **"Bağlantı koptu" ne demek? ERP'ye mi bağlanıyor?**
> Hayır. O gösterge **tarayıcı ↔ yerel backend (localhost:8000)** bağlantısını gösterir,
> gerçek ERP/PLC bağlantısını değil. Nedenleri, ne düzeltildiği ve **gerçek ERP/PLC'ye
> nasıl bağlanılacağı** için: [`BAGLANTI_REHBERI.md`](BAGLANTI_REHBERI.md)

## Uçtan uca test senaryosu

1. Tarayıcıda http://localhost:8000 aç.
2. "Üretim Emirleri" bölümünden bir sipariş oluştur (ör. `Alüminyum Profili`, `Alüminyum Eritme Fırını`, `750 °C`, `2 dk`).
3. Aşağıdan fırını seçip **Başlat** tıkla.
4. Fırın kartında sıcaklığın yükseldiğini, brülörün açık olduğunu, durumun `ISINIYOR` → `BEKLETIYOR` değişimini görebilirsin.
5. 2 dakikalık bekletme bittiğinde emir `TAMAMLANDI` olur ve kayıt veritabanına yazılır.
6. Sıcaklık sınırı (850 °C) aşılmayı denemek istersen, hedef olarak 900 °C girerek deneyebilirsin — fırın ALARM durumuna düşer, brülör kapanır.

## OPC UA (gerçek PLC/SCADA taklit katmanı)

Sunucu: `opc.tcp://localhost:4840/freeopcua/server/`
Namespace: `urn:erp-sim:plant`
Üst nesne: `Fabrika` → her fırın bir nesne, altında değişkenler:

| Değişken (BrowseName) | Anlamı | Tür |
|-----------------------|--------|-----|
| `anlik_sicaklik` | Anlık fırın sıcaklığı (°C) | Double |
| `hedef_sicaklik` | Hedef/ayarlı sıcaklık (°C) | Double |
| `maks_sicaklik` | Güvenlik sınırı (°C) | Double |
| `durum` | `KAPALI` / `ISINIYOR` / `BEKLETIYOR` / `SOGUYOR` / `ALARM` | String |
| `brulor_acik` | Brülör/ısıtıcı açık mı | Boolean |
| `gaz_tuketimi` | Anlık gaz tüketimi (m³/saat) | Double |
| `enerji_toplam` | Kümülatif tüketim (m³) | Double |
| `evrim_suresi` | Mevcut çevrim süresi (saniye) | Double |
| `alarm` | Alarm metanı (boşsa alarm yok) | String |

Örnek Python istemcisi:

```python
from asyncua import Client

async def main():
    client = Client("opc.tcp://localhost:4840/freeopcua/server/")
    await client.connect()
    fabrika = await client.nodes.root.get_child(["0:Objects", "2:Fabrika"])
    firin = await fabrika.get_child("2:Aluminyum Eritme Fırını")
    sicaklik = await (await firin.get_child("2:anlik_sicaklik")).get_value()
    durum = await (await firin.get_child("2:durum")).get_value()
    print(f"Sıcaklık: {sicaklik} °C | Durum: {durum}")
    await client.disconnect()

import asyncio; asyncio.run(main())
```

ERP backend aynı verileri her saniye `erp_sim.db` (SQLite) dosyasına yazar ve `/api/ws` WebSocket üzerinden arayüze yayar.

## Klasör yapısı

```
simulator/          # Sanal fabrika ve fırın termal modeli
  furnace.py        # Tek fırın modeli (ısıtma/bekletme/soğuma/alarm)
  plant.py          # Tüm fırınlar + üretim emri döngüsü
  opcua_server.py   # OPC UA sunucusu (PLC/SCADA taklit)
erp_backend/        # ERP sunucusu
  main.py           # FastAPI: REST API, WebSocket, simülasyon döngüsü
  database.py       # SQLite veritabanı (okunur veri kaydı)
frontend/
  index.html        # Tek dosyalık canlı ERP arayüzü
start.sh            # Tek komutluk başlatıcı
Dockerfile / docker-compose.yml  # İsteğe bağlı konteyner çalıştırmak için
```

## Gerçek fabrika geçişi için öneriler (rehberden)

1. **İlk aşama salt-okunur olsun.** ERP sadece PLC/SCADA'dan veri okusun. Kontrol komutu (fırın başlat/durdur, hedef sıcaklık değiştir), acil durdurma ve güvenlik kilitleri yetkili PLC/SCADA sistemlerinde kalsın.
2. **Veritabanı:** Simülasyonda SQLite kullanıldı. Gerçek fabrika geçişinde `erp_backend/database.py` ve `DATABASE_URL` ile PostgreSQL'e geçebilirsin (rehberde önerildiği gibi).
3. **Gerçek PLC:** OPC UA sunucusunu kendi `simulator/opcua_server.py` yerine gerçek PLC'cin OPC UA arayüzüyle değiştir; ERP tarafındaki URL'yi PLC'nin endpoint'ine çek. MQTT alternatifi için `paho-mqtt` zaten `requirements.txt`'de düşünülebilir (şu an OPC UA önceliklidir).
4. **Proses modeli:** Fırın sıcaklık davranışı şu an basit bir ilk-merkezli modeldendi. Gerçek fırının termal özellikleri (yalıtım, brülör kapasitesi, metal kütlesi) öğrendikten sonra `simulator/furnace.py`'deki `heat_rate`, `cool_rate`, `hold_band` değerlerini gerçek reçeteye göre ayarla.

## Notlar

- Bu bir **test/simülasyon ortamıdır**, üretimde doğrudan kullanılamaz.
- Tüm veriler bilgisayarında yerel `erp_sim.db` dosyasında tutulur; ağa açılmamalıdır.
- Canlı önizleme (port 8000) sadece bu oturum için geçerdir.

---

Hazırlayan: ERP + Sanal Fabrika Simülasyonu projesine ait test ortamı.
İyi çalışmalar, Cemil!
