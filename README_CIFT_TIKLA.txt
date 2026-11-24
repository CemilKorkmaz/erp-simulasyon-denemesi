# ERP Simülasyonu — çift tıklayarak çalıştırma

Bu klasördeki dosyalar, **terminal açmadan** simülasyonu başlatmak içindir.

---

## Windows — `Baslat.bat` (çift tıkla)

1. Bilgisayarında **Python 3.9 veya üstü** kurulu olmalı.
   * Kontrol: Komut İstemi'ne `python --version` yaz.
   * Kurulu değilse: <https://www.python.org/downloads/> → kurulumda
     **"Add Python to PATH"** kutusunu mutlaka işaretle.
2. Bu klasördeki **`Baslat.bat`** dosyasına **çift tıkla**.
3. İlk çalıştırmada gerekli paketler otomatik iner (1-3 dakika).
   Sonraki açılışlar 5-10 saniye sürer.
4. Tarayıcı kendiliğinden `http://localhost:8000` adresinde açılır.
5. **Kapatmak için** açılan siyah penceredeki talimatı izle (ya pencereyi
   kapat ya `Ctrl+C` bas). Sunucu pencereyle birlikte kapanır.

> İlk açılışta Windows "Windows korumalı bilgisayarınızı korudu" derse
> **"Ek bilgi" → "Yine de çalıştır"** seç. (İmzalı olmayan bir betik olduğu için.)

---

## Windows — `ERP_Simulasyon.exe` (Python bile gerekmez)

Bu, `Baslat.bat`'ın "her şey içinde" hâlidir. Python kurulu olmayan
bilgisayarlarda da çalışır.

* Derlemek için: `.github/workflows/build-app.yml` iş akışını GitHub →
  **Actions → "Uygulama Derle" → Run workflow** ile çalıştır, bitince
  **ERP_Simulasyon-Windows** zip'ini indir, içindeki `.exe`'ye çift tıkla.
* Ya da kendi bilgisayarında:
  ```bat
  pip install -r requirements.txt pyinstaller
  pyinstaller --noconfirm --clean erp_launcher.spec
  ```
  → `dist\ERP_Simulasyon.exe`

`.exe` **tek dosyadır**. İstediğin yere kopyalayabilirsin. Veritabanı
(`erp_sim.db`) her zaman `.exe`'nin **yanında** oluşur; `.exe`'yi taşırsan
veritabanını da yanında taşı.

---

## macOS — `Baslat.command` (çift tıkla)

1. İlk seferde Terminal'de şu komutu çalıştır (bir kere yeter):
   ```bash
   chmod +x Baslat.command
   ```
2. Sonra **`Baslat.command`** dosyasına **çift tıkla**.
3. macOS "geliştirici doğrulanamadı" derse: dosyaya **sağ tık → Aç → Aç**.

---

## Linux — `Baslat.sh` (çift tıkla)

1. İlk seferde:
   ```bash
   chmod +x Baslat.sh
   ```
2. Dosya yöneticisinden **çift tıkla** veya `./Baslat.sh`.

---

## İlk açılışta ne oluyor?

| Adım | Süre | Ne yapman gerekiyor |
|------|------|---------------------|
| Python sanal ortamı (`.venv`) kurulur | 10-30 sn | Bekle |
| Paketler iner (sadece ilk seferde) | 1-3 dk | Bekle |
| Sunucu başlar, tarayıcı açılır | 5-10 sn | Bekle |
| Arayüzde 3 fırın görünür | anında | Kullanmaya başla |

Sonraki açılışlarda sadece son iki satır olur → **5-10 saniye**.

---

## Kapatma

* **`Baslat.bat` / `Baslat.sh` / `.command`**: açılan terminal penceresini kapat
  (veya `Ctrl+C`).
* **`.exe`**: pencere görünmez; **Görev Yöneticisi → ERP_Simulasyon →
  Görevi sonlandır**. (Ya da bilgisayarı kapat.)

Port 8000'i meşgul bırakırsan bir sonraki açılışta "zaten çalışıyor" uyarısı
alırsın; eski kopyayı kapatman yeterli.

---

## Beğenmedin mi? Terminale dön

Her şey eskisi gibi de çalışır:

```bash
./start.sh 10          # 10x hızlı
./start.sh             # gerçek zamanlı
```

Hızı ayrıca **arayüzün sağ üstündeki düğmelerden** (1x / 2x / 5x / 10x /
25x / 50x) canlı olarak değiştirebilirsin — uygulamayı yeniden başlatmak
gerekmez.
