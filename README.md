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

## Kurulum ve çalıştırma

Terminali repodaki klasörde aç ve çalıştır:

```bash
./start.sh
```

`start.sh` şunları yapar:

1. Gerekli Python paketlerini bir sanal ortama (`.venv`) yükler (`fastapi`, `uvicorn`, `asyncua`, `sqlalchemy`).
2. Sanal fabrika simülasyonunu başlatır (her saniye fırın durumlarını günceller).
3. OPC UA sunucusunu açar: `opc.tcp://localhost:4840/freeopcua/server/`
4. ERP arayüzünü açar: **http://localhost:8000**

### Arayüzde neler yapabilirsin?

- **Fırın kartları:** Anlık sıcaklık, hedef sıcaklık, durum (KAPALI/ISINIYOR/BEKLETIYOR/ALARM), brülör açık/kapalı, gaz tüketimi, kümülatif enerji, çevrim süresi, küçük geçiş grafiği.
- **Üretim emirleri:** Yeni sipariş oluştur (ürün, fırın, hedef sıcaklık, süre), fırına ata ve "Başlat" ile çevrimi başlat. Sıcaklık hedefe ulaştığında bekletmeye, süre dolduğunda emir TAMAMLANDI olarak geçer.
- **Alarmlar:** Aşırı sıcaklık (850 °C üstü) anında alarm döner ve brülör kapanır.
- **Canlılık:** Sağ üstteki nokta yeşilken WebSocket üzerinden veri akışı aktif demektir.

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
- Tüm veriler bilgisayarındaーカル yerel `erp_sim.db` dosyasında tutulur; ağa açılmamalıdır.
- Canlı önizleme (port 8000) sadece bu oturum için geçerdir.

---

Hazırlayan: ERP + Sanal Fabrika Simülasyonu projesine ait test ortamı.
İyi çalışmalar, Cemil!
