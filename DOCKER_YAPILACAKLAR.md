# Docker'a geçiş planı

Tarih: 28 Ekim 2026

Durum: İleride uygulanmak üzere kaydedildi. Henüz Docker yapılandırması hazırlanmadı.

29 Ekim 2026 durumu: `hukuk` Conda ortamı ve CPU kütüphaneleri hazır. E5 yerel Hugging Face önbelleğine kuruldu; Gemma LM Studio'da kalıyor. Gerçek uygulama akışı doğrulandı. Docker'a geçerken E5 önbelleği de bağlanmalı/kalıcı tutulmalı; modelin yeniden indirilmesine gerek bırakılmamalı.

## Hedef

Kullanıcı Gemma modelini LM Studio üzerinden kendi bilgisayarına indirip çalıştıracak. Projenin diğer bileşenleri Docker Compose ile başlatılacak. Gemma modeli Docker imajına eklenmeyecek.

Planlanan mimari:

```text
Tarayıcı → React arayüzü → ASP.NET Core Gateway → Python FastAPI
                                                   ├─ ChromaDB
                                                   ├─ multilingual-e5-base
                                                   └─ Bilgisayardaki LM Studio / Gemma
```

ASP.NET Core gateway korunmuştur; kullanılmayan eski Java/Spring Boot kodu kaldırılmıştır.

## Yapılacaklar

- [ ] Python FastAPI servisi için Dockerfile hazırla.
- [ ] Arama/embedding modelini CPU'da çalıştıracak bağımlılıkları seç; gereksiz CUDA paketlerini indirme. Gemma'nın GPU kullanımı LM Studio tarafından yönetilecek.
- [ ] ASP.NET Core gateway için çok aşamalı Dockerfile hazırla; son imajda yalnızca çalışma zamanı ve derlenmiş uygulama bulunsun.
- [ ] React arayüzünü derleyip statik dosyaları sunacak Dockerfile hazırla.
- [ ] Üç servisi başlatacak `compose.yaml` dosyasını oluştur.
- [ ] Gateway–FastAPI adreslerini Compose servis adlarıyla yapılandır; tarayıcının erişeceği API adresini ayrıca düzenle.
- [ ] FastAPI'nin bilgisayardaki LM Studio API'sine erişimini yapılandır. Windows/Docker Desktop için `host.docker.internal:1234/v1` adresini kullan; LM Studio'nun Docker'dan erişilebilir biçimde dinlediğini doğrula.
- [ ] Ortama özel Windows dosya yollarını konteyner yollarına çevir; `.env.example` dosyasını güncelle.
- [ ] Hukuk veri dosyalarını ve ChromaDB dizinini kalıcı bağlamalar/volume'larla yapılandır. Kullanıcıya veritabanı mı dağıtılacağını, yoksa ilk kurulumda indeksleme mi yapılacağını netleştir.
- [ ] `multilingual-e5-base` model önbelleğini kalıcı volume'da tut; her konteyner oluşturulduğunda yeniden indirilmesini önle.
- [ ] ChromaDB ile diğer Python paketlerinin sürümlerini sabitle; mevcut veritabanının seçilen sürümle açıldığını doğrula.
- [ ] `.dockerignore` dosyaları ekle; `.env`, `.git`, yerel derleme çıktıları, `node_modules` ve gereksiz önbellekleri imajlara dahil etme. Gerekli veri dosyalarını seçilen dağıtım yöntemine göre ayrıca ele al.
- [ ] Servis sağlık kontrollerini ve başlatma sırasını düzenle; LM Studio kapalıysa anlaşılır hata gösterildiğini doğrula.
- [ ] README'ye Docker Desktop/WSL, LM Studio, model indirme, veri hazırlama, başlatma ve durdurma adımlarını yaz.
- [ ] İlk kurulum, soru-cevap ve yeniden başlatma akışlarını dene; volume'ların veri ve model önbelleğini koruduğunu doğrula.
- [ ] Gerçek imaj boyutlarını, ilk kurulumdaki indirme miktarını ve disk kullanımını ölçerek aşağıdaki tahminleri güncelle.

## Disk ve internet tahminleri

28 Ekim 2026 güncellemesi: LM Studio'da fiilen mevcut model **Gemma 4 E2B Q4_K_M**, yerel model dosyası yaklaşık **4,41 GB**. Aşağıdaki önceki boyut tablosu E4B varsayımıyla hazırlanmıştı; Docker uygulanırken seçilen gerçek model esas alınarak güncellenecek. Mevcut modelin yeniden indirilmesi gerekmez.

Aşağıdaki değerler henüz Docker imajı oluşturulmadan yapılmış yaklaşık planlama rakamlarıdır. Windows/Docker Desktop ve CPU üzerinde embedding varsayılmıştır. Paket sürümleri, mevcut kurulumlar, önbellekler ve derleme yöntemi sonucu değiştirebilir.

| Bileşen | İlk indirme / internet | Disk alanı |
|---|---:|---:|
| Gemma 4 E4B, Q4_K_M | 5,34 GB | 5,34 GB |
| Docker uygulaması, Python bağımlılıkları ve embedding modeli | 2–4 GB | 4–7 GB |
| Docker Desktop, gerekli WSL bileşenleri ve LM Studio | 1–3 GB | 3–6 GB |
| LM Studio ayrıca görsel model dosyasını indirirse | Yaklaşık 1 GB | Yaklaşık 1 GB |

- Sıfırdan kurulum için yaklaşık **9–14 GB internet** ve **14–20 GB disk alanı** planlandı.
- Kurulum ve geçici dosyalar için başlangıçta **en az 25 GB boş alan** ayırmak uygun olur. Yerel imaj derlemeleri ve biriken önbellekler daha fazla alan gerektirebilir.
- Gemma, LM Studio ve Docker zaten kuruluysa kalan uygulama için yaklaşık **2–4 GB indirme** ve **4–7 GB ek disk alanı** bekleniyor.
- Projede kullanılan `intfloat/multilingual-e5-base` modelinin ağırlıkları yaklaşık **1,11 GB**; bu miktar yukarıdaki Docker uygulaması satırına dahildir.
- Mevcut `tck_chromadb` klasörü inceleme sırasında yaklaşık **32,4 MiB** idi; kaynaklar arttıkça büyüyecek.
- Gerekli modeller ve bağımlılıklar indirildikten sonra yerel soru-cevap için internet gerekmez. Güncellemeler, yeni modeller ve yeniden indirmeler ayrıca internet tüketir.
- Disk rakamları RAM/VRAM ihtiyacını ifade etmez.

Boyut kaynakları (28 Ekim 2026 tarihinde kontrol edildi):

- [LM Studio Gemma 4 E4B GGUF dosyaları](https://huggingface.co/lmstudio-community/gemma-4-E4B-it-GGUF/tree/main): Q4_K_M 5,34 GB; isteğe bağlı görsel dosyası yaklaşık 992 MB.
- [multilingual-e5-base model ağırlıkları](https://huggingface.co/intfloat/multilingual-e5-base/blob/main/model.safetensors): 1,11 GB.

## Tamamlanma ölçütü

Kullanıcı LM Studio'da Gemma'yı başlatıp gerekli veri ve ayarları hazırladıktan sonra `docker compose up -d` komutuyla uygulamayı açabilmeli. Konteynerler yeniden oluşturulduğunda veri ve model önbelleği korunmalı; yerel soru-cevap akışı çalışmalı.
