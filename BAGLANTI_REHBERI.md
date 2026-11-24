# Bağlantı Rehberi — "Bağlantı koptu / sayfa sürekli yenileniyor" neden oluyordu ve ERP'ye nasıl bağlanılır

Bu dosya iki soruyu yanıtlar:

1. **"ERP panosuna bağlanıyor… sonra bağlantı koptu" ne demekti, neden oluyordu?** (ve ne düzeltildi)
2. **Gerçek ERP sistemime / PLC'ye nasıl bağlarım?** (adım adım)

---

## 1. O "bağlantı" ERP değil, tarayıcı ile kendi backend'in arasındaki bağlantı

En önemli nokta: Panoda gördüğün nokta ve "Bağlanıyor… / Bağlantı koptu" yazısı
**hiçbir zaman gerçek ERP sistemine veya fabrikadaki PLC'ye bağlanmaya çalışmıyor.**

O gösterge sadece şunu söylüyor:

```
Tarayıcı  ──WebSocket──►  Senin bilgisayarında çalışan Python backend (localhost:8000)
```

Yani senin durumunda **bağlanılacak bir ERP zaten yoktu** — sistem kendi kendine yeten
bir simülasyon. Gösterge kendi yerel sunucusuna bağlanmaya çalışıyordu ve
"Bağlantı koptu" demesi, kendi backend'inin o an WebSocket'i yayınlayamadığı
anlamına geliyordu. Gerçek ERP/PLC bağlantısı ayrı bir konudur (Bölüm 3).

### Neden sürekli sayfa yeniliyordu ve sipariş oluşturamıyordun?

Eski kodda şu vardı:

```js
ws.onclose = () => {
  ... 'Bağlantı koptu, yeniden deneniyor…'
  setTimeout(() => location.reload(), 3000);   // ← SORUN
};
```

WebSocket her kapandığında sayfa **3 saniye sonra komple yenileniyordu**.
Yenileme olunca:

* Ürün adı alanına yazdığın metin siliniyordu,
* Fırın seçimin sıfırlanıyordu,
* "Sipariş Oluştur" isteği yarıda kalabiliyordu.

Yani sipariş oluşturamaman, formun her 3 saniyede bir yok edilmesindendi.

**Neden WebSocket sürekli kopuyordu?**

* İkinci varyantta (`run_mac.sh` / `run_windows.bat` ile açılan
  `erp_simulation/`) backend'de `/api/ws` endpoint'i **hiç yoktu**.
  Arayüz bağlanmaya çalışıyor, 404 alıyor, `onclose` tetikleniyor,
  3 saniye sonra sayfa yenileniyor, döngü sonsuza kadar sürüyordu.
  → Artık o varyantta gerçek `/api/ws` endpoint'i var.
* Proxy / önizleme / uyku modu gibi nedenlerle bağlantı kopabiliyordu.
  → Artık kopunca **sayfa yenilenmiyor**; artan aralıklarla (1s, 2s, 4s…
  en fazla 15s) sessizce yeniden bağlanıyor. Bu sırada pano boş kalmasın diye
  3 saniyede bir REST (`/api/furnaces`, `/api/orders`) ile veri çekiliyor.

### Ne değişti (özet)

| Konu | Önce | Sonra |
|------|------|-------|
| WebSocket kopunca | `location.reload()` → sayfa 3 sn'de bir yenileniyor | Sayfa **hiç** yenilenmiyor, sessiz yeniden bağlanma |
| Canlı akış yokken | Pano donuyor | 3 sn'de bir REST'ten veri (pano çalışmaya devam eder) |
| `erp_simulation` varyantı | `/api/ws` yok → sonsuz kopma döngüsü | Gerçek WebSocket endpoint'i eklendi |
| İkinci varyantın tablosu | Her veri gelişinde tablo + fırın seçimi sıfırdan kuruluyordu | Satırlar bir kez kurulur, sadece hücreler güncellenir |
| Tamamlanan emirler | `COMPLETED` olmuyordu (fırın sonsuza kadar meşgul) | Düzeltildi, özetle birlikte veritabanına yazılıyor |
| Sipariş butonu | Çift tıklamada mükerrer kayıt | Buton istek sırasında kilitlenir, hata mesajı görünür |
| Veritabanı hatası | Simülasyon döngüsü tamamen duruyordu | Hata loglanır, canlı akış devam eder |
| Gösterge metni | "Bağlanıyor…" (ERP'ye bağlanıyormuş gibi) | "Yerel sunucuya bağlanıyor…" + **Yeniden bağlan** butonu |

---

## 2. Simülasyonu çalıştırma — adım adım

### 2.1 Gereken tek şey

* Python 3.9+ (varsa `python3 --version` ile kontrol et)
* Terminal (macOS/Linux) veya Komut İstemi / PowerShell (Windows)
* Tarayıcı

Başka hiçbir kurulum gerekmiyor. İnternet gerekmez (paketler ilk seferde iner).

### 2.2 En kolay yol: çift tıkla

Terminal açmak istemiyorsan:

| İşletim sistemi | Çift tıklanacak dosya |
|-----------------|------------------------|
| Windows | `Baslat.bat` (veya `.exe` varsa `ERP_Simulasyon.exe`) |
| macOS | `Baslat.command` |
| Linux | `Baslat.sh` |

İlk seferde paketler kurulur (1-3 dk), sonra **tarayıcı kendiliğinden açılır**.
Ayrıntı: `README_CIFT_TIKLA.txt`

`.exe` dosyasını almak için GitHub → Actions → "Uygulama Derle" → Run workflow
→ bitince Artifacts → `ERP_Simulasyon-Windows`.

### 2.3 Terminalden başlat (tek komut)

Terminali **proje klasöründe** aç ve şunu çalıştır:

```bash
./start.sh 10
```

`10` = 10 kat hızlı. Hız vermezsen 1x (gerçek zamanlı) çalışır.

Windows'ta:

```cmd
start.sh 10
```

`start.sh` çalışmazsa (izin hatası) doğrudan:

```bash
bash start.sh 10
```

veya Python ile:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
SIM_SPEED=10 .venv/bin/python -m erp_backend.main
```

### 2.4 Tarayıcıyı aç

Terminalde şu satırı görünce hazırsın:

```
Uvicorn running on http://0.0.0.0:8000
```

Tarayıcıda aç: **http://localhost:8000**

> `localhost` çalışmazsa **http://127.0.0.1:8000** dene.

### 2.5 Ekranda ne görmelisin

| Gösterge | Anlamı | Ne yapmalı |
|----------|--------|-----------|
| Nokta **yeşil** + "Canlı veri akışı aktif" | Her şey yolunda | Devam et |
| Nokta **turuncu** + "bağlanıyor…" | Yeni bağlanıyor | 1-2 sn bekle |
| Nokta **gri** + "Canlı akış yok, N sn içinde…" | Yerel backend'e ulaşılamıyor | Terminalde sunucu çalışıyor mu bak; **Yeniden bağlan** butonuna bas |
| Fırın kartlarında 3 fırın + sıcaklıklar | Veri geliyor | Devam et |
| Kartlar boş / `--` | REST de başarısız | Sunucu kapalı; terminalde hatayı oku |

> **Önemli:** Nokta gri olsa bile **sipariş oluşturabilirsin.** Form artık
> canlı akıştan bağımsız çalışıyor ve sayfa asla kendini yenilemiyor.

### 2.6 Sipariş oluşturma ve çevrimi başlatma

1. **Ürün** alanına bir ad yaz — ör. `Alüminyum Profili`
2. **Hedef sıcaklık** — ör. `750` (illaki gerçekçi olmak zorunda değil, `50` de olur)
3. **Fırın** seç — ör. `Aluminyum Eritme Fırını`
4. **Süre (dk)** — ör. `30` (ya da hızlı test için `0.1`)
5. **Sipariş Oluştur** → tabloya `CREATED` olarak düşer, üstte `WO-... oluşturuldu` yazar
6. Tablodaki **Başlat** → fırın çalışmaya başlar, durum `RUNNING`
7. Fırın kartında sıcaklık yükselir: `KAPALI` → `ISINIYOR` → `BEKLETIYOR`
8. Süre dolunca emir `COMPLETED` olur ve SQLite'a özetiyle yazılır

> ⚠️ **Süre, hedef sıcaklığa ULAŞTIKTAN SONRA başlar.** Yani `750 °C` + `2 dk`
> demek, önce ~10 dakika ısınma (1x hızda), sonra 2 dakika bekletme demektir.
> "Bir türlü tamamlanmıyor" hissinin sebebi budur — hata değil.

### 2.7 En hızlı "çalışıyor mu?" testi (60 saniye)

```bash
./start.sh 10
```

Tarayıcıda:

| Alan | Değer |
|------|-------|
| Ürün | `Hizli Test` |
| Hedef sıcaklık | `60` |
| Fırın | `Homojenizasyon Fırını` |
| Süre | `0.2` |

**Sipariş Oluştur** → **Başlat** → yaklaşık **10-15 saniye** içinde satır
`COMPLETED` olur. Bunu gördüysen sistem uçtan uca çalışıyor demektir.

### 2.8 Alarm testi

| Alan | Değer |
|------|-------|
| Hedef sıcaklık | `900` (güvenlik sınırı 850 °C) |
| Fırın | `Aluminyum Eritme Fırını` |
| Süre | `1` |

`./start.sh 10` ile **~3 dakika** sonra fırın `ALARM` durumuna düşer, brülör kapanır,
"Alarmlar" panelinde kırmızı kayıt çıkar. (1x hızda bu 30 dakika sürer — bu yüzden
hız çarpanı var.)

### 2.9 Hızı arayüzden değiştirme

Arayüzün **sağ üstünde** `1x / 2x / 5x / 10x / 25x / 50x` düğmeleri var.
Bunlara basınca simülasyon **anında** hızlanır/yavaşlar — uygulamayı yeniden
başlatman gerekmez, komut yazman da gerekmez. Düğmelerin yanındaki küçük yazı
bağlantı durumunu gösterir (`· canlı`, `· bağlanıyor`, `· çevrimdışı`).

### 2.10 Durdurma

Terminalde **Ctrl+C**. Veritabanı dosyası (`erp_sim.db`) olduğu gibi kalır;
tekrar başlattığında geçmiş okumalar durur, emir listesi sıfırlanır (emirler
bellekte tutulur, sadece tamamlananlar DB'ye yazılır).

### 2.11 Sık karşılaşılan başlatma hataları

| Hata | Sebep | Çözüm |
|------|-------|-------|
| `Permission denied` | `start.sh` çalıştırılabilir değil | `bash start.sh 10` veya `chmod +x start.sh` |
| `address already in use` | 8000 portu dolu (eski sunucu açık) | `lsof -i :8000` (mac/linux) → süreci kapat; Windows: `netstat -ano \| findstr :8000` |
| `ModuleNotFoundError: fastapi` | `.venv` kurulmamış | `./start.sh` (kendisi kurar) veya `pip install -r requirements.txt` |
| `command not found: python3` | Python kurulu değil | python.org'dan Python 3.11+ kur |
| Açılışta `No encrypting policy available` | OPC UA sertifikası yok (simülasyon için normal) | Yoksay |
| Sayfa açılıyor ama "ERR_CONNECTION_REFUSED" | Sunucu henüz açılmamış / çökmüş | Terminal çıktısını oku |

### 2.12 İki farklı başlatıcı var — hangisini kullanmalısın?

| Komut | Backend | Arayüz | Not |
|-------|---------|--------|-----|
| `./start.sh [hız]` | `erp_backend/main.py` | `frontend/index.html` | **Önerilen.** Grafikli fırın kartları, WebSocket, alarm paneli |
| `./erp_simulation/run_mac.sh [hız]` | `erp_simulation/main.py` | `erp_simulation/frontend/index.html` | Eski/tablo tabanlı arayüz. O da artık WebSocket + hız çarpanı destekliyor |

İkisi de **8000** portunu ve `erp_sim.db` yerine kendi DB'sini kullanır —
**aynı anda çalıştırma**, biri "address already in use" verir.

---

## 3. Gerçek ERP sistemine / PLC'ye nasıl bağlanılır

### 3.1 Önce şunu netleştir: hangi yönde bağlantı?

Üç farklı "ERP'ye bağlanma" senaryosu var, çözümleri tamamen farklı:

```
A)  Bu simülasyon  ──►  Gerçek PLC/SCADA       (veri kaynağını değiştir)
B)  Bu simülasyon  ──►  Senin ERP yazılımın    (simülasyonu ERP'ye veri kaynağı yap)
C)  Senin ERP      ──►  Bu simülasyonun API'si (ERP'den veri çek)
```

### 3.2 A) Gerçek PLC'ye bağlanmak (OPC UA)

Simülasyonda PLC'yi taklit eden katman `simulator/opcua_server.py`.
Gerçek PLC'ye geçmek için sunucuyu kapatıp **istemciye** dönüşürsün.

**Adım 1 — PLC'nin OPC UA endpoint'ini öğren**

PLC/SCADA mühendisinden veya PLC dokümanından şu bilgileri al:

* Endpoint: `opc.tcp://<plc-ip>:4840` (bazı markalarda 4840 dışı port)
* Namespace URI'si (ör. `urn:siemens:s7` vb.)
* Değişkenlerin **NodeId**'leri (ör. `ns=2;s=Firin1.Sicaklik`)

**Adım 2 — ERP backend'i istemci moduna al**

`erp_backend/main.py` içinde sunucuyu başlatan satırı kaldır:

```python
# asyncio.create_task(run_opcua_server(plant, host="0.0.0.0", port=4840))
```

Yerine okuma yapan bir döngü ekle (taslak):

```python
from asyncua import Client

async def plc_reader():
    while True:
        try:
            async with Client("opc.tcp://192.168.1.10:4840") as client:
                node = client.get_node("ns=2;s=Firin1.Sicaklik")
                while True:
                    deger = await node.read_value()
                    # plant.furnaces["Aluminyum Eritme Fırını"].state.temperature = deger
                    await asyncio.sleep(1.0)
        except Exception as exc:
            print("PLC bağlantı hatası, 5 sn sonra tekrar:", exc)
            await asyncio.sleep(5.0)
```

> Simülasyondaki `plant` nesnesini tamamen kaldırmak istersen, `get_states()`
> yerine doğrudan PLC'den okuduğun sözlüğü `manager.broadcast(...)` içine ver.
> Arayüz `{ name: {temperature, status, ...} }` biçimini bekliyor.

**Adım 3 — Güvenlik kuralları (önemli)**

Rehberin de söylediği gibi: **ilk aşama salt-okunur olsun.** Fırın başlat/durdur,
hedef sıcaklık değiştirme ve acil durdurma yetkileri PLC/SCADA'da kalsın.
Bu simülasyon şu an PLC'ye **yazma** yapmıyor — bu doğru ve güvenli yaklaşım.

**Modbus TCP kullanacaksan:** `factory_server/plc_client.py` içinde hazır bir
`ModbusTCPClient` var. Ama `PLCManager.tags` içindeki adresler **örnektir**
(`40001`, `0`, `40002`) — gerçek PLC'ne göre değiştirmen şart.

### 3.3 B) Simülasyonu kendi ERP'ne veri kaynağı yapmak

Bu simülasyon zaten OPC UA yayınlıyor. ERP'n OPC UA okuyabiliyorsa:

```
ERP  ──OPC UA client──►  opc.tcp://<bu-bilgisayarın-ip>:4840/freeopcua/server/
```

* Namespace: `urn:erp-sim:plant`
* Üst nesne: `Objects → Fabrika → <Fırın Adı> → <değişken>`
* Değişkenler: `anlik_sicaklik`, `hedef_sicaklik`, `maks_sicaklik`, `durum`,
  `brulor_acik`, `gaz_tuketimi`, `enerji_toplam`, `evrim_suresi`, `alarm`

Test için (bu repoda `asyncua` kurulu):

```python
import asyncio
from asyncua import Client

async def main():
    async with Client("opc.tcp://localhost:4840/freeopcua/server/") as c:
        fabrika = await c.nodes.root.get_child(["0:Objects", "2:Fabrika"])
        firin = await fabrika.get_child("2:Aluminyum Eritme Fırını")
        sicaklik = await (await firin.get_child("2:anlik_sicaklik")).get_value()
        durum = await (await firin.get_child("2:durum")).get_value()
        print(f"Sıcaklık: {sicaklik} °C | Durum: {durum}")

asyncio.run(main())
```

⚠️ `2:Fabrika` içindeki `2`, namespace index'idir. Sunucu yeniden başlarsa
index değişebilir; üretimde URI ile aramak daha güvenlidir.

**Ağ erişimi:** OPC UA sunucusu `0.0.0.0:4840` dinliyor, yani aynı ağdaki
başka bir bilgisayardan `opc.tcp://<bu-makinenin-ip>:4840/...` ile erişilebilir.
Güvenlik duvarında 4840 portunu açman gerekir.

### 3.4 C) Kendi ERP'nden bu sistemin API'sini tüketmek

Hazır REST uçları (hepsi `http://localhost:8000`):

| Metot | Yol | Açıklama |
|-------|-----|----------|
| GET | `/api/furnaces` | Tüm fırınların anlık durumu |
| GET | `/api/furnaces/{ad}` | Tek fırın |
| GET | `/api/orders` | Üretim emirleri |
| POST | `/api/orders` | Emir oluştur |
| POST | `/api/orders/{id}/start` | Emri fırına ata ve başlat |
| GET | `/api/readings/{ad}?limit=200` | Geçmiş sıcaklık kayıtları |
| WS | `/api/ws` | Saniyelik canlı yayın (`type: "tick"`) |

Emir oluşturma örneği:

```bash
curl -X POST http://localhost:8000/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"Alüminyum Profili","furnace":"Aluminyum Eritme Fırını","target_temp":750,"duration_min":30}'
```

→ `{"id":"WO-20261124-0001","state":"CREATED"}`

```bash
curl -X POST http://localhost:8000/api/orders/WO-20261124-0001/start \
  -H "Content-Type: application/json" \
  -d '{"furnace":"Aluminyum Eritme Fırını"}'
```

> **Dikkat:** Şu anda API'de kimlik doğrulama **yok**. Bu yüzden README'de
> yazdığı gibi sadece yerel makinede / güvenli iç ağda çalıştır. İnternete
> açma. Dışarı açacaksan en azından bir ters vekil (nginx) + token doğrulama
> eklemelisin.

### 3.5 Üretime geçmeden önce kontrol listesi

- [ ] Veritabanını SQLite'tan PostgreSQL'e taşı (`DATABASE_URL`)
      — saniyede 3 kayıt yazıyor, uzun vadede SQLite şişer
- [ ] `plant` nesnesini gerçek PLC okuyucusuyla değiştir
- [ ] `simulator/furnace.py` içindeki `heat_rate`, `cool_rate`, `max_temp`
      değerlerini gerçek fırın reçetesine göre ayarla
- [ ] API'ye kimlik doğrulama + HTTPS ekle
- [ ] Salt-okunur başla; yazma komutlarını PLC/SCADA'da bırak
- [ ] `erp_sim.db` / `factory_sim.db` için otomatik yedek kur
- [ ] Alarm eşiklerini ve acil durdurma davranışını saha ekibiyle doğrula

---

## 4. Sorun giderme

| Belirti | Anlamı | Çözüm |
|---------|--------|-------|
| "Adres zaten kullanımda" / `address already in use` | 8000 portu dolu, muhtemelen eski sunucu açık | `lsof -i :8000` ile bul, süreci kapat |
| Nokta gri, "Canlı akış yok, N sn sonra…" | Yerel backend kapalı | `./start.sh` çalıştır, sonra **Yeniden bağlan** |
| Nokta turuncu, kalıcı "Bağlanıyor…" | Proxy/WebSocket engeli | Pano REST ile çalışmaya devam eder; 8000'e doğrudan bağlanmayı dene |
| Sipariş tabloda yok | İstek 400/500 dönmüş | Ekranda çıkan hata mesajını oku (artık sessizce yutulmuyor) |
| "Emir başlatılamadı: …fırın meşgul" | O fırında çalışan bir emir var | Emri `COMPLETED` olana kadar bekle, başka fırın seç |
| Sıcaklık hiç yükselmiyor | Emir `CREATED`, henüz başlatılmamış | Tablodaki **Başlat**'a bas |
| `attempt to write a readonly database` | DB dosyası çalışırken silinmiş/taşınmış | Sunucuyu durdur, `erp_sim.db`'yi sil, yeniden başlat |

---
