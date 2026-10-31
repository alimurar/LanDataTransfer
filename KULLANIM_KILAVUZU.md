# ⚡ LAN Transfer - 2 Windows Cihaz Arasında Yerel Ağ Veri Transferi

Bu proje, aynı yerel ağa (Wi-Fi veya Ethernet/LAN kablosu) bağlı 2 Windows bilgisayar arasında **internet kotası harcamadan**, yerel ağınızın izin verdiği **en yüksek hızda (Gigabit / Wi-Fi 6 vb.)** dosya ve klasör aktarımı yapmanız için geliştirilmiştir.

Herhangi bir harici kütüphane (`pip install`) gerektirmez; **saf Python (Standard Library)** ile çalışır.

---

## 🎯 İki Farklı Kullanım Yolu Hazırlandı

İhtiyacınıza göre en uygun yöntemi seçebilirsiniz:

| Özellik | 🌐 Yöntem 1: Web Portalı (`baslat_web.bat`) | 💻 Yöntem 2: Masaüstü Programı (`baslat_gui.bat`) |
| :--- | :--- | :--- |
| **İkinci Bilgisayara Kurulum** | ❌ **Hiçbir şey gerekmez!** Sadece tarayıcı (Chrome/Edge) yeterlidir. | ✔️ İki bilgisayarda da program açılır. |
| **Arayüz** | Modern Web Arayüzü (Sürükle & Bırak) | Yerel Windows Masaüstü Penceresi (Tkinter) |
| **Mobil / Tablet Desteği** | ✔️ Evet (Telefon/Tabletle de dosya alıp verebilirsiniz) | ❌ Yalnızca PC |
| **Cihaz Bulma** | IP adresini tarayıcıya yazarak bağlanma | 🔍 Tek tıkla otomatik cihaz arama (UDP Beacon) |
| **Klasör Aktarımı** | ✔️ Evet (Tümünü ZIP indir veya klasör yükle) | ✔️ Evet (Klasör yapısını koruyarak doğrudan aktarır) |
| **Pano / Not Paylaşımı** | ✔️ Evet (Metin/Link aktarma panosu) | - |

---

## 🌐 YÖNTEM 1: Web Tabanlı Transfer (En Pratik Yol)

> 💡 **Avantajı:** İkinci bilgisayara Python veya program yüklemenize gerek kalmaz!

1. **1. Bilgisayarda:**
   - Klasördeki **`baslat_web.bat`** dosyasına çift tıklayın (veya terminalde `python lan_web.py` çalıştırın).
   - Ekranda yerel IP adresiniz yazacaktır (Örn: `http://192.168.1.113:8990`). Tarayıcınız bu bilgisayarda otomatik olarak açılacaktır.

2. **2. Bilgisayarda:**
   - Google Chrome veya Microsoft Edge tarayıcısını açın.
   - Adres çubuğuna 1. bilgisayarda görünen adresi yazın: `http://192.168.1.113:8990`

3. **Nasıl Kullanılır?**
   - **Dosya Gönderme:** Dosyaları veya klasörleri tarayıcıdaki kutucuğa sürükleyip bırakın. Yükleme hızı (MB/s) ve ilerleme çubuğu canlı olarak görüntülenir.
   - **Dosya İndirme:** Sayfadaki dosya listesinden istediğiniz dosyanın yanındaki **"İndir"** butonuna basabilir veya **"Tümünü ZIP Olarak İndir"** diyerek tek seferde arşiv alabilirsiniz.
   - **Pano / Not Paylaşımı:** İki bilgisayar arasında link veya metin aktarmak için sayfadaki metin kutusunu kullanabilirsiniz.

---

## 💻 YÖNTEM 2: Masaüstü Arayüzü (GUI - Yüksek Hızlı TCP Transferi)

> 💡 **Avantajı:** Çok büyük dosyaları (50 GB+ oyunlar, ISO dosyaları) doğrudan soket üzerinden sıfır kayıpla aktarır ve klasör yapısını aynen korur.

1. **Her iki bilgisayarda da:**
   - Klasördeki **`baslat_gui.bat`** dosyasına çift tıklayın.

2. **Dosyayı Alacak Olan Bilgisayarda:**
   - Program açıldığında otomatik olarak **"📥 Dosya Al (Alıcı Modu)"** sekmesinde dinlemeye başlar.
   - İsterseniz "Kayıt Klasörü"nü değiştirebilirsiniz (Varsayılan: `Lan Transfer/Gelen_Dosyalar`).

3. **Dosyayı Gönderecek Olan Bilgisayarda:**
   - **"📤 Dosya Gönder"** sekmesine geçin.
   - **"🔍 Alıcıları Otomatik Bul"** butonuna tıklayın (Ağdaki alıcıyı bulup IP'sini otomatik yazar). *(Eğer modeminiz broadcast yayınını engelliyorsa, alıcı bilgisayardaki IP adresini manuel olarak da yazabilirsiniz).*
   - **"➕ Dosya Ekle"** veya **"📁 Klasör Ekle"** butonlarıyla göndermek istediğiniz öğeleri seçin.
   - **"🚀 Gönderimi Başlat"** butonuna basın!

Transfer boyunca anlık aktarım hızı (MB/s), kalan süre ve ilerleme yüzdesi görüntülenir.

---

## ⌨️ YÖNTEM 3: Komut Satırı (CLI)

Terminal kullanmayı tercih edenler için `lan_cli.py` komutları:

- **Ağdaki alıcıları aramak için:**
  ```powershell
  python lan_cli.py scan
  ```

- **Alıcı modunu başlatmak için:**
  ```powershell
  python lan_cli.py receive "C:\Hedef\Klasor"
  ```

- **Dosya veya klasör göndermek için:**
  ```powershell
  python lan_cli.py send 192.168.1.113 "C:\Dosyalarim\dosya.zip"
  ```

---

## ⚠️ Sorun Giderme ve İpuçları (Windows Güvenlik Duvarı)

Eğer iki bilgisayar birbirine bağlanamıyorsa:

1. **Aynı Ağda Olduğunuzdan Emin Olun:**
   - Her iki bilgisayarın da aynı modeme (aynı Wi-Fi veya Ethernet ağına) bağlı olduğundan emin olun.
   - Misafir ağı (Guest Wi-Fi) kullanıyorsanız cihazlar arası iletişim kapalı olabilir; standart ev/iş ağına bağlanın.

2. **Windows Güvenlik Duvarı Uyarısı:**
   - Programı ilk kez çalıştırdığınızda Windows Defender Güvenlik Duvarı uyarı verirse, **"Özel Ağlar"** (Private Networks) kutucuğunu işaretleyip **Erişime İzin Ver** deyin.

3. **Ağ Profilini "Özel Ağ" Olarak Ayarlayın:**
   - Windows Ayarları > Ağ ve İnternet > Wi-Fi/Ethernet > Bağlantınızın özelliklerine girip ağ profilini **"Ortak Ağ" (Public)** yerine **"Özel Ağ" (Private)** yapın.
