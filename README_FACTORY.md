# Fabrika Yerel ERP (.exe)

Bu klasör, fabrika içi bir bilgisayarda çalışacak, **sadece yerel ağda** erişilebilir ERP sisteminin starter kodlarını içerir.

## Ne yapar?

- Yerel PC’de SQLite veritabanında (`factory_erp.db`) PLC sensor verilerini saklar.
- PLC’ye (Modbus TCP / OPC UA / Siemens S7) bağlanır ve sensör verilerini her 3 saniyede bir okur.
- Fabrikadaki diğer bilgisayarlar tarayıcıyla `http://<yerel-pc-ip>:8000` adresinden ERP’yi görüntüler.
- İnternete gerek yok; tamamen fabricada lokal çalışır.

## Klasör yapısı

```
factory_server/      # Python kaynak kodu (FastAPI, SQLite, PLC istemcisi)
frontend/            # Tek dosyalık tarayıcı arayüzü
requirements_factory.txt
build_factory_exe.py # .exe üretmek için PyInstaller betiği
README_FACTORY.md
```

## Kurulum (Windows fabrika bilgisayarı)

1. Python 3.11+ kur (yüklerken "Add Python to PATH" işaretli olsun).
2. Bu klasördeki dosyaları fabrika bilgisayarına kopyala.
3. Komut İstemi (CMD) veya PowerShell'de:

```cmd
cd factory_server_kopyasi
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements_factory.txt
pip install pyinstaller
```

## .exe üretmek

```cmd
.venv\Scripts\activate
python build_factory_exe.py
```

`dist/FactoryERP.exe` dosyası oluşur. Bu tek dosyayı fabrika bilgisayarında çalıştırabilirsin.  
(.exe, Windows’dır. Linux fabrika bilgisayarıysa `python factory_server/main.py` ile doğrudan çalıştırabilirsin.)

## PLC ayarları

`factory_server/plc_client.py` dosyasındaki `PLCManager.tags` sözlüğünde, **PLC’nize göre doğru adresleri ve ölçeklendirmeleri girmen gerekir**:

```python
self.tags = {
    "sicaklik": {"address": 40001, "type": "holding", "scale": 0.1, "unit": "°C"},
    "durum":    {"address": 0,     "type": "coil",    "scale": 1,     "unit": ""},
    "enerji":   {"address": 40002, "type": "holding", "scale": 1.0,   "unit": "kWh"},
}
```

PLC marka/modeline göre bu adresler değişir. Program, ağdaki yaygın PLC portlarını tarayabilir (502 Modbus, 4840 OPC UA, 102 Siemens), ama hangi adreste hangi sensör olduğunu PLC dokümanından öğrenip buraya girmen lazım.

## Yerel ağ erişimi

Fabrika bilgisayarının LAN IP’sini öğren (Windows CMD'de `ipconfig`).  
Örnek: `192.168.1.45` ise diğer bilgisayarlardan:

```
http://192.168.1.45:8000
```

Windows Güvenlik Duvarı'nda 8000 portunu girişe izin ver.

## Kısıtlamalar

- "Otomatik sensör tanıma" sadece **PLC cihazını ağda bulmayı** yapar. Sensörlerin hangi register/adreste olduğunu siz PLC'ye göre tanımlayın.
- Tek bir PLC bağlantısı desteklenir (starter seviyesi). Çoklu PLC için `PLCManager`'ı genişletebilirsiniz.
- Güvenlik: Bu sistem yalnızca fabrika içi ağ içindir. İnternete açılmamalıdır.

## Veritabanı yedekleme

`factory_erp.db` dosyasını düzenli olarak kopyalayarak yedekleyebilirsiniz. İsterseniz SQLite'ı PostgreSQL'e geçirebilirsiniz (`sqlalchemy` zaten kullanıldığı için değişiklik küçük olacaktır).
