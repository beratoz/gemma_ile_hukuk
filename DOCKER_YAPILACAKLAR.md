# Docker kurulumu

Güncelleme: 30 Ekim 2026

Gemma kullanıcı tarafından LM Studio'da indirilip çalıştırılır. Docker imajlarına Gemma veya özel yerel dosyalar eklenmez.

## Hazırlananlar

- [x] Tek Dockerfile içinde Python API, .NET gateway ve React/Nginx hedefleri.
- [x] Compose ile servis adresleri, API hazır olma kontrolü ve localhost'a açık arayüz.
- [x] Nginx üzerinden aynı adreste API erişimi ve tamponlanmadan SSE aktarımı.
- [x] İzin verilen dosyaları listeleyen `.dockerignore`; özel veri, `.env`, cache ve derleme çıktıları hariç.
- [x] Ayrı Docker volume'larında E5 önbelleği ve ChromaDB.
- [x] Açıkça çağrılan `setup` servisi: yalnızca E5 indirme ve yerelde kullanılan beş JSON kaynağını indeksleme.
- [x] Normal çalışma sırasında çevrimdışı embedding; tek API worker ve CPU PyTorch.
- [x] README içinde ilk kurulum, LM Studio bağlantısı, açma/kapatma ve volume silme açıklamaları.

## Docker kurulu bir bilgisayarda yapılacaklar

- [x] Linux üzerinde Python, .NET ve frontend imajlarını derle.
- [x] `docker compose run --build --rm setup` ile beş kaynaktan 1695 kayıtlık tam indeksi hazırla.
- [x] `docker compose up --build -d` ile üç servisi başlat.
- [x] Gerçek LM Studio bağlantısı ve Nginx/.NET/Python üzerinden SSE yanıtını doğrula.
- [x] `down` / `up` sonrası E5 ve 1695 kaydın korunduğunu doğrula.
- [x] İmaj boyutlarını `docker image ls`, toplam kullanımı `docker system df -v` ile ölç.

Docker Desktop kullanıcı dizininde bulundu ve üç imaj Linux üzerinde derlendi. Windows kilit dosyasında eksik Linux bağımlılıkları tamamlandı. Önceki 4–7 GB disk ve 2–4 GB indirme rakamları ölçülmüş sonuç değildir. Gemma (~4,4 GB) bu kurulumun dışındadır. E5'in gerekli dosyaları yaklaşık 1,13 GB'tır ve imajdan ayrı saklanır. Docker Desktop/WSL, derleme önbelleği ve çalışma ortamları ayrıca yer kaplar.

Yerel doğrulamalar: Compose YAML yapısı ve dışa açık portlar kontrol edildi; hazırlık işlemi indirme/Chroma sınırları taklit edilerek ilk kurulum, önbellekten kullanım, yeniden indekslememe ve yarım indeksi koruma senaryolarında denendi. `/api/chat` adresiyle frontend üretim derlemesi geçti. Bu kontroller konteynerlerde uçtan uca test yerine geçmez; yeni model indirilmedi.

Gerçek Docker doğrulaması: 1695 kayıt ve beş kaynak dağılımı yerelle eşleşti; JSON SHA256 değerleri aynı. `/health` sonucu `ok`. Gerçek Gemma yanıtı 180 SSE parçasıyla tamamlandı (tek denemede ilk metin 34,7 s, toplam 41,2 s). Çevrimdışı hazırlık tekrarında indeks korundu. E5 mevcut önbellekten Docker volume'una kopyalandı. Uygulama imajları ve E5/indeks toplamı yaklaşık 4,2 GB; ayrıntılı ölçüm README içinde.

Konteynerler `down` / `up` ile yeniden oluşturulduktan sonra sağlık `ok`, kayıt sayısı yine 1695. Gerçek SSE akışı ilk metinde iptal edildi; takip eden ek soru isteği 3,2 saniyede tamamlandı, analiz kilidi açık kalmadı. Tarayıcı sohbet kaydı önceki yerel sürümde doğrulanmıştı; Docker geçişinde frontend kayıt kodu değiştirilmedi.

Kullanım komutları ve ayrıntılar [README.md](README.md) içindedir. Mevcut özel yerel ChromaDB ve hukuk veri dosyaları bu kurulum tarafından değiştirilmez.
