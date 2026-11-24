# Alüminyum Fabrika Simülasyonu — ERP Test Ortamı

Mac mini M2 (ve Windows) üzerinde çalışan, gerçek bir fabrika otomasyon sistemine çok benzeyen sanal bir üretim ortamıdır.

## Mimari

```
Sanal Fırın (Python termal model)
        ↓
OPC UA Sunucusu (sanal PLC)
        ↓
ERP Adaptörü (FastAPI + SQLite)
        ↓
Tarayıcı Arayüzü (Canlı panot)
```

ERP, sıcaklığı üretmez. Sıcaklıkları sanal fabrika üretir, ERP OPC UA üzerinden okur.

## Fırınlar

1. **Alüminyum Ergitme Fırını** — 750 °C hedef, 850 °C alarm sınırı
2. **Homojenizasyon Fırını** — 560 °C hedef, 620 °C alarm sınırı
3. **Biyet Isıtma Fırını** — 480 °C hedef, 540 °C alarm sınırı

Her fırın: sıcaklık, hedef, durum (KAPALI/ISINIYOR/BEKLETIYOR/ALARM), brülör, gaz tüketimi, çevrim süresi, alarm.

## Kurulum ve çalıştırma

### Mac mini M2

```bash
cd erp_simulation
chmod +x run_mac.sh
./run_mac.sh
```

### Windows

```cmd
cd erp_simulation
run_windows.bat
```

Sonra tarayıcıda aç: **http://localhost:8000**

## Test senaryosu

1. "Üretim Emri Oluştur" bölümünden bir sipariş aç (ör. Alüminyum Profili, Ergitme Fırını, 750 °C, 2 dk).
2. Aşağıdan fırını seçip **Başlat** tıkla.
3. Fırın kartında sıcaklığın 25 °C'dan 750 °C'ye yükseldiğini, brülörün açık olduğunu, durumun `ISINIYOR` → `BEKLETIYOR` değişimini görebilirsin.
4. 2 dakikalık bekletme bittiğinde emir `TAMAMLANDI` olur ve SQLite veritabanına kaydedilir.
5. Hedef olarak 900 °C girersen fırın **ALARM** durumuna düşer, brülör kapanır.

## OPC UA (gerçek PLC ile benzer)

Sunucu: `opc.tcp://localhost:4840/freeopcua/server/`

Örnek Python istemcisi:

```python
from asyncua import Client
import asyncio

async def main():
    async with Client("opc.tcp://localhost:4840/freeopcua/server/") as client:
        fabrika = await client.nodes.root.get_child(["0:Objects", "2:Fabrika"])
        firin = await fabrika.get_child("2:Alüminyum Ergitme Fırını")
        sicaklik = await (await firin.get_child("2:anlik_sicaklik")).get_value()
        durum = await (await firin.get_child("2:durum")).get_value()
        print(f"Sıcaklık: {sicaklik} °C | Durum: {durum}")

asyncio.run(main())
```

## Gerçek fabrika geçişi

- `erp_simulation/furnace.py` ve `plant.py`'deki `heat_rate`, `cool_rate`, `max_temp` değerlerini gerçek fırın reçetesine göre ayarla.
- `opcua_server.py`'yi kendi PLC'nin OPC UA endpoint'ine yönlendir (veya Modbus/S7 istemcisi ekle).
- ERP tarafındaki `erp_adapter.py`'deki OPC UA okuma kısmını gerçek PLC'le değiştir.

## Veritabanı

Tüm okumalar ve emirler `factory_sim.db` (SQLite) dosyasında yerel olarak saklanır. İstersen PostgreSQL'e geçirebilirsin.

---

**Yazar:** ERP Simülasyon Ortamı — Mac mini M2 / Windows uyumlu
