# ⚖️ TCK Hukuk Asistanı — Multi-Corpus RAG Sistemi

> **Tamamen yerel** çalışan, **Türk Ceza Hukuku** alanında uzmanlaşmış bir RAG (Retrieval-Augmented Generation) tabanlı hukuki danışma asistanı.

Halk ağzıyla yazılmış olayları analiz eder, **5 farklı hukuki kaynaktan** (TCK, TCK Gerekçeleri, CMK, CGTİK, Genel Hükümler Doktrini) ilgili kanun maddelerini otomatik bulur ve profesyonel hukukçu metodolojisiyle **mütalaa** üretir. Tüm pipeline tamamen yereldir — veri internete çıkmaz.

---

## 🎯 Temel Özellikler

| Özellik | Açıklama |
|---|---|
| 🔒 **%100 Yerel** | Hiçbir veri internete çıkmaz |
| 📚 **Multi-Corpus** | 5 farklı kaynak, 1695+ doküman |
| 🧠 **Halk Dili Anlama** | 107 hukuki kavram, 499 halk dili eşlemesi |
| 🔍 **4 Aşamalı Pipeline** | Tercüman → Multi-Query Retrieval → Eksik Suç Kontrolü → Mütalaa |
| 📐 **Hukuk Metodolojisi** | 5-adımlı per-suç analiz şablonu |
| ⚡ **Halüsinasyon Koruması** | Resmi başlıklar + hukuka aykırılık kontrolü + sıkı prompt mühendisliği |
| 🔎 **Hibrit Arama** | CPU üzerinde BM25 + çoklu vektör araması, RRF ile birleştirme |
| ⏳ **İlerleme ve Akan Yanıt** | Gerçek analiz aşamaları, geçen süre ve üretilen metnin anlık gösterimi |
| 💾 **Silinebilir Yerel Kayıt** | Son 100 mesaj tarayıcıda saklanır; tek düğmeyle silinir, kayıt kapatılabilir |
| ❓ **Sınırlı Ek Soru** | Kritik belirsizlikte olay başına en fazla bir soru; atlayarak devam edilebilir |

---

## 🏗️ Sistem Mimarisi

```
React Frontend (5173) → ASP.NET Core Gateway (8080) → FastAPI RAG Engine (8000) → LM Studio / Gemma 4B (1234)
                                                              ↕
                                                        ChromaDB (1695 doc)
```

| Katman | Teknoloji | Görev |
|---|---|---|
| **Frontend** | React 19, Vite, Tailwind CSS | ChatGPT-tarzı sohbet arayüzü |
| **API Gateway** | ASP.NET Core (.NET), C# | CORS, validation, hata yönetimi, proxy |
| **RAG Engine** | Python, FastAPI, ChromaDB | 4-aşamalı hukuki analiz pipeline |
| **LLM** | LM Studio, Gemma 4 E2B | Yerel dil modeli (OpenAI-uyumlu API) |

> Gateway ASP.NET Core ile çalışır. Kullanılmayan Java gateway, eski CLI ve tek seferlik modelle başlık üretme aracı kaldırılmıştır. Veri setleri, ontoloji ve indeksleme aracı korunmuştur.

---

## 🔧 4-Aşamalı RAG Pipeline

**Aşama 1 — Tercüman:** Halk ağzındaki soruyu hukuki kavramlara çevirir. Özel ontoloji ile zenginleştirir (`"küfür"` → `"hakaret"`, `"ofisime daldı"` → `"işyeri dokunulmazlığı"`). Aynı model çağrısında, yalnızca kritik belirsizlik varsa tek kısa ek soru önerebilir. Yanıt veya atlama sonrasında tekrar soru sorulmaz.

Kısa, açık madde sorularında modelden suç adı tahmin etmesi istenmez; orijinal madde referansı aramaya aktarılır. Kavram çıkarma ve eksik suç kontrolünde `reasoning_effort=none` kullanılır; nihai mütalaanın düşünme ayarı korunur.

**Aşama 2 — Hibrit Multi-Query Retrieval:** Orijinal soru ve kavramlar için ChromaDB vektör araması ile BM25 kelime aramasını RRF üzerinden birleştirir. Mülga maddeler iki kanalda da dışlanır. Açık madde referansları önceliklendirilir; aynı maddenin parçaları aynı sıralamada fazladan oy almaz. BM25 mevcut veritabanından açılışta oluşturulur; ek paket/model veya yeniden indeksleme gerektirmez. Veri değiştirildiğinde API yeniden başlatılmalıdır.

BM25 başlık alanına ek ağırlık verir ve sonuç sınırını parçalara değil farklı maddelere uygular; uzun gerekçe metinleri diğer maddelerin bütün sıralarını tüketmez.

**Aşama 2.5 — Eksik Suç Kontrolü:** Mini LLM çağrısı ile gözden kaçan suç tiplerini tespit eder, gerekirse ek retrieval yapar.

**Aşama 3 — Mütalaa:** 5-adımlı per-suç metodoloji: Fiil → Hukuki Nitelendirme → Maddi Unsur → Hukuka Aykırılık Kontrolü → Ceza ve Sonuç. İçtima değerlendirmesi ve pratik sonuç ekler. Yanıt SSE ile FastAPI → .NET → tarayıcı boyunca parça parça aktarılır. Durdurma veya sohbet silme, istemci bağlantısını ve model akışını kapatır; yarıda kalan yanıt etiketlenir.

---

## 📚 Veri Kaynakları

| Kaynak | Doküman | Açıklama |
|---|---|---|
| **TCK** | 364 | Türk Ceza Kanunu (5237 sayılı) |
| **TCK_GEREKCE** | 487 | TCK madde gerekçeleri |
| **CMK** | 407 | Ceza Muhakemesi Kanunu (5271 sayılı) |
| **CGTİK** | 231 | Ceza ve Güvenlik Tedbirlerinin İnfazı Hakkında Tüzük |
| **TCK_DOKTRİN** | 206 | Genel Hükümler Doktrini |
| **TOPLAM** | **1695** | Tek ChromaDB koleksiyonunda |

> Repoda yalnızca örnek veri seti (`tck_rag.json`) ve ontoloji (`ceza_hukuku_ontolojisi.json`) bulunur. Tam veri setleri `.gitignore` ile hariç tutulmuştur.

---

## 🔧 Teknoloji Stack

| Katman | Teknolojiler |
|---|---|
| **RAG Engine** | Python 3.11, FastAPI, ChromaDB, sentence-transformers (multilingual-e5-base), OpenAI SDK |
| **API Gateway** | C# / ASP.NET Core (.NET), HttpClient, FluentValidation |
| **Frontend** | React 19, Vite, Tailwind CSS, Fetch / SSE |
| **LLM** | LM Studio, Gemma 4 E2B (Q4_K_M, yerel dosya yaklaşık 4,41 GB) |

---

## 📋 Gereksinimler

| Bileşen | Sürüm |
|---|---|
| **Python** | 3.11+ |
| **.NET SDK** | 10.0+ (`net10.0`) |
| **Node.js** | 20+ |
| **LM Studio** | En güncel |
| **GPU (önerilen)** | NVIDIA 4 GB+ VRAM |

---

## 🚀 Kurulum ve Çalıştırma

### 1. Repoyu Klonla
```bash
git clone https://github.com/beratoz/gemma_ile_hukuk.git
cd gemma_ile_hukuk
```

### 2. Python Ortamı
```bash
conda create -n hukuk python=3.11 -y
conda activate hukuk
pip install -r requirements.txt
```

Python paketleri yalnızca `hukuk` ortamına kurulmalıdır. Embedding modeli CPU üzerinde ve `local_files_only=True` ile açılır: **model dosyası otomatik indirilmez**. `intfloat/multilingual-e5-base` dosyalarının daha önce yerel Hugging Face önbelleğine konmuş olması veya `EMBEDDING_MODEL_NAME` ayarının mevcut yerel model klasörünü göstermesi gerekir. Bu dosyalar yoksa API açılışı durur; paket kurmak model ağırlıklarını sağlamaz.

Bu bilgisayardaki `hukuk` ortamında `HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1` ve `ANONYMIZED_TELEMETRY=False` kalıcı ortam değişkenleri olarak ayarlanmıştır. Ortam `conda activate hukuk` ile etkinleştirildiğinde uygulanırlar. `requirements.txt`, CPU PyTorch ve kontrol edilen ana paket sürümlerini sabitler.

E5 modeli 29 Ekim 2026 tarihinde kullanıcı izniyle yerel önbelleğe kuruldu. `EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-base` ayarıyla çevrimdışı açılır; normal kullanımda tekrar indirme gerekmez.

### 3. Konfigürasyon
```bash
cp .env.example .env
# .env dosyasındaki path'leri kendi sisteminize göre düzenleyin
```

### 4. ChromaDB İndeksleme (Tek seferlik)
```bash
python tck_indeksleme.py
```

### 5. Frontend Bağımlılıkları
```bash
cd frontend && npm install && cd ..
```

### 6. LM Studio
Bu bilgisayarda mevcut **Gemma 4 E2B, Q4_K_M** modeli kullanılır (`google/gemma-4-e2b`). Başka model indirmek gerekmez. Yerel API sunucusu açık ve port 1234 olmalıdır. Bağlam ve çıktı toplamı yüklenmiş bağlam sınırına sığmalıdır.

28 Ekim 2026 tarihinde mevcut model için tek eşzamanlı üretim ve 8500 token bağlam isteğiyle yükleme yapıldı. LM Studio bunu 8704 token olarak uyguladı; görünen GPU kullanımı yaklaşık 2,6 GB idi. Aynı oturum ayarını mevcut yerel dosyayla yeniden uygulamak için:

```powershell
lms unload google/gemma-4-e2b
lms load google/gemma-4-e2b --context-length 8500 --parallel 1 --yes
lms server start --port 1234
```

Bu komutlar yeni model indirmez. GPU offload otomatik seçimde bırakılmıştır; toplam fiziksel belleğin yeterliliği ve hız farklı cihazlarda ayrıca kontrol edilmelidir.

### 7. Servisleri Başlat (4 terminal)

FastAPI terminalinde önce `conda activate hukuk` çalıştırın.

| Terminal | Komut | Port |
|---|---|---|
| LM Studio | GUI'den başlat | 1234 |
| FastAPI | `uvicorn main:app --port 8000` | 8000 |
| .NET Gateway | `cd dotnet-gateway && dotnet run` | 8080 |
| React | `cd frontend && npm run dev` | 5173 |

Tarayıcıda aç: **http://localhost:5173**

---

## 📊 Test Sonuçları

### 29 Ekim 2026 — gerçek E5 / ChromaDB / .NET / arayüz akışı

- Kullanıcının izniyle `intfloat/multilingual-e5-base` kuruldu. Gerekli model dosyaları toplam **1.134.355.035 bayt (yaklaşık 1,13 GB)**; model revision'ı `d128750597153bb5987e10b1c3493a34e5a4502a`. Safetensors ağırlığının SHA256 değeri doğrulandı. Yinelenen PyTorch ve ONNX ağırlıkları indirilmedi.
- İlk indirme yeniden başlatılırken yaklaşık 199 MB tekrar aktarım oldu; eski 765 MB'lık kısım HTTP Range ile tamamlandı. Gereksiz yarım kopya temizlendi. Model önbelleğinde ikinci fiziksel ağırlık kopyası oluşturulmadı.
- API `HF_HUB_OFFLINE=1` ile açıldı. E5 CPU üzerinde, Gemma LM Studio'da çalıştı. `/health` sonucu `ok`, kayıt sayısı **1695**, BM25 aktif parça sayısı **1692**. GPU kullanımı yaklaşık **2,6 GB** kaldı.
- Veritabanı test öncesi yedeklendi. Test sonrasında kayıt ve metadata karşılaştırması yapıldı; veri kaybı veya yeniden indeksleme olmadı, migration sayısı **18** kaldı.
- Tarayıcı → ASP.NET Core → FastAPI → gerçek E5 / ChromaDB → gerçek Gemma → SSE → tarayıcı zinciri çalıştırıldı. Basit örnek olayın yanıtı tamamlandı; çok fiilli örnekte kaynak araması ve kontrollü iptal denendi.
- Gerçek arayüzde ilerleme aşamaları, akan metin, durdurma, kısmi yanıt işareti, yenileme sonrası kayıt, tek düğmeyle silme, kayıt kapatma ve aktif işlem sırasında silinen mesajların geri gelmemesi doğrulandı.
- Belirsiz olayda tek ek soru ve atlama seçeneği denendi. Soru atlandığında somut fiil hâlâ belirlenemiyorsa suç/ceza tahmini yapılmadan kısa açıklama döndürülür; ikinci soru sorulmaz.
- **18 kod/API regresyon testi geçti.** .NET derlemesi hatasız tamamlandı. Bu kontroller teknik akışı doğrular; küçük yerel modelin hukuki değerlendirmeleri ayrıca uzman ve örnek vaka kontrolü gerektirir.
- Bu oturumda arayüz `http://localhost:15173`, gateway `http://localhost:8080`, FastAPI `http://127.0.0.1:8000` adreslerinde çalıştırıldı. Normal frontend başlangıcı için yukarıdaki varsayılan 5173 portu kullanılabilir.

### 29 Ekim 2026 — izole Python ortamı

- `hukuk` adlı Conda ortamı Python 3.11.17 ile yerel Conda önbelleğinden oluşturuldu; diğer ortamların paketleri değiştirilmedi.
- CPU PyTorch dahil 105 Python kütüphanesi/paket dosyası indirildi; wheel dosyalarının toplamı **281.481.941 bayt (281,5 MB)**. Çözümleme önbelleği yaklaşık 18 MB idi; metadata ile toplam indirme yaklaşık 300 MB düzeyindedir. Model dosyası indirilmedi.
- Paketlerin SHA256 değerleri doğrulanıp kurulum tamamen yerel wheel dosyalarından yapıldı. `pip check` bağımlılık sorunu bulmadı. PyTorch sürümü `2.15.0+cpu`; CUDA derlemesi yok.
- Gerçek FastAPI/Pydantic/Starlette kütüphaneleriyle JSON ve SSE uçları dahil ilk aşamada **17 test geçti**: `conda activate hukuk` ardından `python -m unittest -v test_main`. Ek soru atlama kontrolüyle sayı 18'e çıktı. Testlerde LM Studio ve veri arama sınırları sahte nesnelerle temsil edilir; model indirilmez.
- Paketlerin import kontrolü geçti. Bu ilk aşamada E5 dosyaları yoktu; sonraki kullanıcı izniyle model kurulup yukarıdaki gerçek uçtan uca kontrol tamamlandı.

### 28 Ekim 2026 — çevrimdışı kontrol

- İnternetten paket, model veya başka dosya indirilmedi.
- Mevcut Gemma 4 E2B ile açık olayda kavram çıkarma, belirsiz olayda tek ek soru ve atlama sonrası ikinci sorunun kod tarafından engellenmesi kontrol edildi.
- Kavram çıkarma için düşünme açık benzer denemeler yaklaşık 11–12 saniye, `reasoning_effort=none` ile kısa denemeler yaklaşık 0,9–1,3 saniye sürdü. Bunlar küçük örneklerdir; genel hız/kalite ölçümü sayılmaz.
- Mevcut Chroma SQLite verisi salt okunur açılarak BM25, 1692 aktif parça üzerinde kontrol edildi. Başlık ağırlığı sonrası `hakaret` ve `hırsızlık` sorgularında ilgili temel madde ilk sıraya geldi. Bu kontrol dense arama kanalını çalıştırmaz.
- Gerçek modelle **önceden seçilmiş üç kaynak metni** üzerinden mütalaa akışı kontrol edildi: ilk içerik yaklaşık 24,7 saniye, tamamlanma yaklaşık 71,6 saniye; bitiş nedeni `stop`. Bu süre tüm RAG pipeline'ının süresi değildir.
- Yanıtta olayda verilmeyen bir ayrıntının varsayıldığı görüldü. Akışın tamamlanması hukuki doğruluğun doğrulandığı anlamına gelmez; gerçek vakalarla uzman değerlendirmesi hâlâ gerekir.
- FastAPI, Pydantic ve Starlette ile JSON/SSE API testleri dahil **18 regresyon testi geçti** (`conda activate hukuk` ardından `python -m unittest -v test_main`). LM Studio ve arama sınırları testlerde sahte nesnelerle temsil edilir.
- Gerçek E5 → ChromaDB → Gemma akışı .NET gateway ve tarayıcı arayüzüyle denendi: yanıt akışı, kaynaklar, iptal, sohbet kaydı, silme ve kaydı kapatma doğrulandı. ChromaDB'deki **1695 kayıt** ve indeks verisi test öncesi/sonrası karşılaştırılarak korundu.

Aşağıdaki puanlar önceki sürümün tarihsel sonuçlarıdır; yeni model/aramaya ait kalite puanı değildir.

| Vaka | Puan |
|---|---|
| WhatsApp grup hakaret | 4/10 |
| Eski sevgili şantaj | 4/10 |
| Trafik tartışması (Multi-Query + Ontoloji sonrası) | 6/10 |
| Ofis saldırı (5 suç tespiti) | 6/10 |

Doğruluk oranı **%60-80** aralığında. Çoklu suç tespiti, içtima değerlendirmesi, temel nitelendirmeler doğru çalışıyor. Nitelikli hallerin tespiti ve içtima derinliği geliştirilmeye devam ediyor.

---

## 🎯 Roadmap

- [x] Hybrid Search (BM25 + Dense embedding)
- [x] Gerçek ilerleme aşamaları ve streamed response
- [x] Silinebilir, kapatılabilir yerel sohbet kaydı
- [x] Olay başına en fazla bir ek soru ve atlama seçeneği
- [ ] Donanım üzerinde yeni arama kalitesini örnek vakalarla değerlendirme
- [ ] Sınırlı konuşma bağlamı (mevcut kayıt özelliği modele geçmişi göndermez)
- [ ] Ek kanunlar (TMK, İİK)

---

## ⚠️ Sınırlamalar

- 🚫 **Hukuki danışmanlık yerine geçmez.** Eğitim ve araştırma amaçlıdır.
- 🚫 Üretilen mütalaalar bir avukat tarafından mutlaka doğrulanmalıdır.
- 🚫 Halüsinasyon riski mevcuttur.
- 🚫 Önceki ölçümlerde tek cevap 4-7 dakika sürüyordu. Akan yanıt beklemeyi görünür kılar; toplam süreyi tek başına azaltmaz. Yeni sürümün gerçek Gemma hız ve kalite ölçümü ayrıca yapılmalıdır.
- Embedding modeli CPU üzerinde çalışır; 4 GB VRAM üzerinde Gemma'ya alan bırakılır. Analizler API süreci içinde sırayla işlenir; tek worker ile çalıştırın. Ek reranker veya büyük model eklenmemiştir.

### Sohbet kaydı ve silme

Son 100 mesaj aynı tarayıcı profilinin `localStorage` alanında saklanır; backend sohbet veritabanı oluşturmaz. **Sohbeti sil** hem ekrandaki hem kalıcı kaydı kaldırır ve devam eden isteği iptal eder. **Sohbeti bu tarayıcıda kaydet** kapatılırsa önceki kalıcı kayıt silinir; mevcut mesajlar sayfa kapanana kadar ekranda kalır. Kayıt şifreli değildir; tarayıcı profilini kullanan kişi erişebilir. Gateway soru metnini ve cevap gövdesini loglamaz.

Ek soru önerildiğinde kısa bilgi yazılabilir veya **Mevcut bilgilerle yanıtla** seçilebilir. Normal sorular birbirinden bağımsızdır; yalnızca bu tek netleştirme yanıtı asıl olayla birlikte modele gönderilir.

Arayüz API adresi isteğe bağlı `VITE_API_URL` ile değiştirilebilir (varsayılan `http://localhost:8080/api/chat`). JSON uçları korunmuştur: `POST /api/chat` ve `POST /api/v1/analyze`. SSE uçları bunların `/stream` uzantılarıdır. İstek alanları: `soru`, isteğe bağlı `ek_bilgi` (en çok 1200 karakter), `ek_soru` ve `ek_soru_yanitlandi`.

---

## 📁 Proje Yapısı

```
├── main.py                         # FastAPI RAG Engine (4-aşamalı pipeline)
├── tck_indeksleme.py               # ChromaDB indeksleme scripti
├── test_main.py                    # Model/GPU gerektirmeyen çekirdek regresyon testleri
├── requirements.txt                # Python bağımlılıkları
├── .env.example                    # Konfigürasyon şablonu
│
├── dotnet-gateway/                 # ASP.NET Core API Gateway
│   ├── Program.cs                  # Uygulama başlangıcı ve servis kayıtları
│   ├── Controllers/                # ChatController (POST /api/chat)
│   ├── Services/                   # AnalyzeService (FastAPI proxy)
│   ├── Dto/                        # Request/Response modelleri
│   ├── Exceptions/                 # PythonServiceException
│   ├── Middleware/                  # GlobalExceptionHandler
│   └── Validators/                 # FluentValidation kuralları
│
├── frontend/                       # React + Vite + Tailwind UI
│   └── src/components/
│       ├── Chat.jsx                # Ana sohbet bileşeni
│       └── MessageContent.jsx      # Referans highlight
│
├── ceza_kanunu_duzeltilmis_2/      # TCK veri seti (örnek: tck_rag.json)
└── hukuk_sozlugu/                  # Hukuk ontolojisi (107 kavram, 499 eşleme)
```

---

## 📜 Lisans

Bu proje eğitim amaçlıdır. TCK metinleri kamu malıdır (Resmi Gazete).
