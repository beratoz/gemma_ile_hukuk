# ⚖️ TCK Hukuk Asistanı — Multi-Corpus RAG Sistemi

> **Tamamen yerel** çalışan, **Türk Ceza Hukuku** alanında uzmanlaşmış bir RAG (Retrieval-Augmented Generation) tabanlı hukuki danışma asistanı.

Halk ağzıyla yazılmış olayları analiz eder, **5 farklı hukuki kaynaktan** (TCK, TCK Gerekçeleri, CMK, CGTİK, Genel Hükümler Doktrini) ilgili kanun maddelerini otomatik bulur ve profesyonel hukukçu metodolojisiyle **mütalaa** üretir. Tüm pipeline tamamen yereldir — veri internete çıkmaz.

---

## 🎯 Temel Özellikler

| Özellik | Açıklama |
|---|---|
| 🔒 **%100 Yerel** | Hiçbir veri internete çıkmaz |
| 📚 **Multi-Corpus** | 5 farklı kaynak, 1695+ doküman |
| 🧠 **Halk Dili Anlama** | 118 hukuki kavram, 578 halk dili eşlemesi (kök eşleşmesiyle: "çaldı*" → çaldılar) |
| ⚖️ **Ceza Tablosu ve Kontrol** | Fıkra bazında ceza/şikâyet tablosu; yanıttaki kaynaksız ceza aralıkları otomatik işaretlenir |
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
React Frontend (5173) → FastAPI RAG Engine (8000) → LM Studio / Gemma 4B (1234)
                                ↕
                          ChromaDB (1695 doc)
```

| Katman | Teknoloji | Görev |
|---|---|---|
| **Frontend** | React 19, Vite, Tailwind CSS | ChatGPT-tarzı sohbet arayüzü |
| **RAG Engine** | Python, FastAPI, ChromaDB | 4-aşamalı hukuki analiz pipeline |
| **LLM** | LM Studio, Gemma 4 E2B | Yerel dil modeli (OpenAI-uyumlu API) |

> Ayrı bir API gateway yoktur: doğrulama (Pydantic), CORS ve SSE doğrudan FastAPI'dedir. Docker'da Nginx arayüzü sunar ve `/api/` isteklerini FastAPI'ye iletir. Önceki Java ve .NET gateway'leri yalnızca proxy görevi gördüğü için kaldırılmıştır.

---

## 🔧 4-Aşamalı RAG Pipeline

**Aşama 1 — Tercüman:** Halk ağzındaki soruyu hukuki kavramlara çevirir. Özel ontoloji ile zenginleştirir (`"küfür"` → `"hakaret"`, `"ofisime daldı"` → `"işyeri dokunulmazlığı"`). Aynı model çağrısında, yalnızca kritik belirsizlik varsa tek kısa ek soru önerebilir. Yanıt veya atlama sonrasında tekrar soru sorulmaz.

Kısa, açık madde sorularında modelden suç adı tahmin etmesi istenmez; orijinal madde referansı aramaya aktarılır. Kavram çıkarma ve eksik suç kontrolünde `reasoning_effort=none` kullanılır; nihai mütalaanın düşünme ayarı korunur.

**Aşama 2 — Hibrit Multi-Query Retrieval:** Orijinal soru ve kavramlar için ChromaDB vektör araması ile BM25 kelime aramasını RRF üzerinden birleştirir. Mülga maddeler iki kanalda da dışlanır. Açık madde referansları önceliklendirilir; aynı maddenin parçaları aynı sıralamada fazladan oy almaz. BM25 mevcut veritabanından açılışta oluşturulur; ek paket/model veya yeniden indeksleme gerektirmez. Veri değiştirildiğinde API yeniden başlatılmalıdır.

BM25 başlık alanına ek ağırlık verir ve sonuç sınırını parçalara değil farklı maddelere uygular; uzun gerekçe metinleri diğer maddelerin bütün sıralarını tüketmez.

**Aşama 2.5 — Eksik Suç Kontrolü:** Mini LLM çağrısı ile gözden kaçan suç tiplerini tespit eder, gerekirse ek retrieval yapar.

**Aşama 3 — Mütalaa:** 5-adımlı per-suç metodoloji: Fiil → Hukuki Nitelendirme → Maddi Unsur → Hukuka Aykırılık Kontrolü → Ceza ve Sonuç. İçtima değerlendirmesi ve pratik sonuç ekler. Yanıt SSE ile FastAPI → tarayıcı boyunca parça parça aktarılır. Durdurma veya sohbet silme, istemci bağlantısını ve model akışını kapatır; yarıda kalan yanıt etiketlenir.

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

> Docker kurulumu yerel sistemle aynı beş JSON kaynağını ve ontolojiyi kullanır. Toplam 1259 ham kayıt, uzun metinler parçalandığında 1695 RAG belgesine dönüşür. PDF'ler, ham kaynaklar ve mevcut yerel ChromaDB repoya/imaja alınmaz; indeks JSON'lardan ayrı Docker volume'unda oluşturulur.

---

## 🔧 Teknoloji Stack

| Katman | Teknolojiler |
|---|---|
| **RAG Engine** | Python 3.11, FastAPI, ChromaDB, sentence-transformers (multilingual-e5-base), OpenAI SDK |
| **Frontend** | React 19, Vite, Tailwind CSS, Fetch / SSE |
| **LLM** | LM Studio, Gemma 4 E2B (Q4_K_M, yerel dosya yaklaşık 4,41 GB) |

---

## 📋 Gereksinimler

| Bileşen | Sürüm |
|---|---|
| **Python** | 3.11+ |
| **Node.js** | 20+ |
| **LM Studio** | En güncel |
| **GPU (önerilen)** | NVIDIA 4 GB+ VRAM |

---

## 🚀 Kurulum ve Çalıştırma

### Docker ile (Gemma kullanıcı bilgisayarında)

Docker Desktop'ı **Linux containers** modunda açın. Bu kurulum Windows/Linux x64 içindir; Python embedding servisi CPU kullanır. Python veya Node'u bilgisayara ayrıca kurmanız gerekmez.

1. LM Studio'yu kurun, Gemma modelini kendiniz indirin/yükleyin ve **Developer → Local Server** üzerinden sunucuyu 1234 portunda açın. Docker'dan erişim için LM Studio'da **Serve on Local Network** seçeneğini açmanız gerekebilir. Güvenlik duvarında erişimi yerel bilgisayar/Docker ile sınırlayın.
2. Bu repoyu indirin ve kök klasörde aşağıdaki ilk hazırlık komutunu çalıştırın:

```bash
docker compose run --build --rm setup
docker compose up --build -d
```

Tarayıcıda **http://localhost:8088** adresini açın. Gemma'nın LM Studio API model kimliği farklıysa `.env` dosyasında `DOCKER_LM_MODEL_NAME` değerini düzenleyin (örnekler `.env.example` içinde). Docker varsayılanlarıyla `.env` oluşturmak zorunlu değildir; mevcut yerel `.env` dosyanızı değiştirmeyin. İsteğe bağlı `DOCKER_WEB_PORT` arayüz portunu değiştirir.

İlk `setup` komutu yalnızca **E5 arama modelini (~1,13 GB)** indirir ve beş JSON kaynağının tamamını indeksler. Gemma indirilmez, hiçbir model imaja gömülmez. E5 ve oluşturulan ChromaDB ayrı Docker volume'larında kalır; tekrar hazırlıkta tamamlanmış indeks korunur ve tam E5 önbelleği varsa internet gerekmez. Normal API çalışması model indirmez. Yerel `data/chromadb` klasörüne dokunulmaz; Docker aynı kaynaklardan kendi **1695 kayıtlık koleksiyonunu** oluşturur. JSON içerikleri değişirse hazırlık eski indeksin üzerine yazmaz; kaynak değişikliğinde yeni bir indeks volume'u hazırlanmalıdır.

Sonraki açılışlarda `docker compose up -d`, kapatmak için `docker compose down` yeterlidir. `down` kayıtlı E5 ve indeks volume'larını korur. **`docker compose down -v` bu iki volume'u siler** ve ilk hazırlığın yeniden yapılmasını gerektirir. Sohbet kaydı tarayıcıda kalır; arayüzden ayrıca silinir.

`docker compose logs --tail 50 api web` hata ayıklama içindir. API model/koleksiyon bulunamadığı için açılmazsa önce `setup` komutunu tamamlayın. LM Studio erişilemiyorsa sunucuyu, model kimliğini ve ağ iznini kontrol edin. Konteyner içinden bilgisayara erişim adresi `host.docker.internal` olarak ayarlanmıştır; Linux'ta bunun için Compose `host-gateway` eşlemesi kullanır.

Docker imajları Linux üzerinde başarıyla derlendi. Kod/veri klasörünün boyutu Python çalışma ortamını, E5 önbelleğini ve Docker derleme önbelleğini kapsamaz. Docker Windows'ta kullanıcı dizininde kuruluysa terminali yeniden açmanız veya Docker'ın `resources/bin` dizinini PATH'e eklemeniz gerekebilir.

16 Kasım 2026 tarihli temiz kurulum ölçümü (`docker system df -v`, .NET gateway kaldırıldıktan sonra):

| Bileşen | Docker'ın bildirdiği disk kullanımı |
|---|---:|
| Python / RAG imajı (CPU kütüphaneleri + beş JSON kaynak) | 2,57 GB |
| Arayüz / Nginx imajı | 93 MB |
| E5 model volume'u | 1,13 GB |
| ChromaDB indeks volume'u | 25 MB |

Çalışma bileşenleri yaklaşık **3,8 GB** tutar (30 Ekim'de .NET imajıyla birlikte yaklaşık 4,2 GB idi). Gemma ve Docker Desktop/WSL bu toplamın dışındadır. Derleme sırasında ayrıca Docker build cache oluşur (bu kurulumda yaklaşık 3,1 GB); `docker builder prune` ile silinebilir. İmajlarla paylaşılan katmanlar içerdiği için bu rakam doğrudan toplamın üzerine eklenmez. Bunlar disk ölçümleridir, internet aktarım miktarı değildir.

> Docker imajları Git reposuna konmaz (GitHub dosya sınırı 100 MB). Repodaki `Dockerfile`, `compose.yaml`, `docker/nginx.conf`, `backend/docker_setup.py` ve `.dockerignore` aynı imajları herhangi bir bilgisayarda yeniden üretmek için yeterlidir.

Docker davranışı için başvurular: [Compose başlangıç sırası](https://docs.docker.com/compose/how-tos/startup-order/), [Docker build context ve ignore kuralları](https://docs.docker.com/build/concepts/context/).

Docker ile doğrulananlar (30 Ekim 2026): beş JSON kaynağının SHA256 değerleri yerel dosyalarla eşleşti; indeks TCK 364, TCK_GEREKCE 487, CMK 407, CGTIK 231 ve TCK_DOKTRIN 206 parça içerdi. `/health` sonucu `ok`, LM Studio erişimi başarılı. Nginx → .NET → FastAPI → E5/ChromaDB → Gemma zincirinde gerçek yanıt 180 SSE parçasıyla tamamlandı; örnek denemede ilk metin 34,7 saniye, tamamlanma 41,2 saniyeydi. Bu tek örnek genel hız veya hukuki doğruluk puanı değildir. Çevrimdışı `setup` tekrarında indeksleme yapılmadı; Python bağımlılık kontrolü temiz çıktı. İmajda PDF veya `.env` bulunmadığı doğrulandı.

Konteynerler silinip yeniden oluşturulduğunda E5 ve 1695 kayıt korundu. SSE istemcisi ilk metinden sonra bağlantıyı kapattığında üretim iptal edildi; sonraki ek soru isteği 3,2 saniyede tamamlandı.

Docker ile doğrulananlar (16 Kasım 2026, temiz kurulum, gateway'siz): Docker tamamen boşken `setup` E5'i indirdi ve beş kaynaktan **1695 kayıtlık** indeksi oluşturdu; indeksleme doğrulama sorularının hepsi ✓. `docker compose up --build -d` ile `api` (healthy) ve `web` başladı. API açılışta 1692 aktif BM25 parçası ve 300 maddelik ceza tablosu yükledi. `/health` sonucu `ok`, LM Studio'ya `host.docker.internal` üzerinden erişildi. Nginx → FastAPI zincirinde boş soru 422 döndü. Arayüz `http://localhost:8088`'de açıldı ve paket `/api/v1/analyze` adresiyle derlendi. Gerçek Gemma 4 E2B ile "ofise zorla girme, bilgisayar kırma, hakaret" sorusu **82 saniyede** tamamlandı: TCK 116, 151 ve 125 bulundu, ceza aralıkları tablodan doğru aktarıldı, 116/4 nitelikli hali de belirtildi. Zayıf yön: işyeri için 116/2 yerine 116/1 aralığı uygulandı.

### Docker olmadan mevcut kurulum

### 1. Repoyu Klonla
```bash
git clone https://github.com/beratoz/gemma_ile_hukuk.git
cd gemma_ile_hukuk
```

### 2. Python Ortamı
```bash
conda create -n hukuk python=3.11 -y
conda activate hukuk
pip install -r backend/requirements.txt
```

Python paketleri yalnızca `hukuk` ortamına kurulmalıdır. Embedding modeli CPU üzerinde ve `local_files_only=True` ile açılır: **model dosyası otomatik indirilmez**. `intfloat/multilingual-e5-base` dosyalarının daha önce yerel Hugging Face önbelleğine konmuş olması veya `EMBEDDING_MODEL_NAME` ayarının mevcut yerel model klasörünü göstermesi gerekir. Bu dosyalar yoksa API açılışı durur; paket kurmak model ağırlıklarını sağlamaz.

Bu bilgisayardaki `hukuk` ortamında `HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1` ve `ANONYMIZED_TELEMETRY=False` kalıcı ortam değişkenleri olarak ayarlanmıştır. Ortam `conda activate hukuk` ile etkinleştirildiğinde uygulanırlar. `backend/requirements.txt`, CPU PyTorch ve kontrol edilen ana paket sürümlerini sabitler.

E5 modeli 29 Ekim 2026 tarihinde kullanıcı izniyle yerel önbelleğe kuruldu. `EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-base` ayarıyla çevrimdışı açılır; normal kullanımda tekrar indirme gerekmez.

### 3. Konfigürasyon
```bash
cp .env.example .env
# .env dosyasındaki path'leri kendi sisteminize göre düzenleyin
```

### 4. ChromaDB İndeksleme (Tek seferlik)
```bash
python backend/tck_indeksleme.py
```

### 5. Frontend Bağımlılıkları
```bash
cd frontend && npm install && cd ..
```

### 6. LM Studio
Bu bilgisayarda mevcut **Gemma 4 E2B, Q4_K_M** modeli kullanılır (`google/gemma-4-e2b`). Başka model indirmek gerekmez. Yerel API sunucusu açık ve port 1234 olmalıdır. Bağlam ve çıktı toplamı yüklenmiş bağlam sınırına sığmalıdır.

Önerilen yükleme: **9216 token bağlam, tek paralel slot** (ceza tablosu için bağlam 8500'den artırıldı; 16 Kasım 2026'da bu ayarla test edildi). 28 Ekim 2026 tarihinde mevcut model için tek eşzamanlı üretim ve 8500 token bağlam isteğiyle yükleme yapılmıştı. LM Studio bunu 8704 token olarak uyguladı; görünen GPU kullanımı yaklaşık 2,6 GB idi. Aynı oturum ayarını mevcut yerel dosyayla yeniden uygulamak için:

```powershell
lms unload google/gemma-4-e2b
lms load google/gemma-4-e2b --context-length 9216 --parallel 1 --yes
lms server start --port 1234
```

Bu komutlar yeni model indirmez. GPU offload otomatik seçimde bırakılmıştır; toplam fiziksel belleğin yeterliliği ve hız farklı cihazlarda ayrıca kontrol edilmelidir.

### 7. Servisleri Başlat (3 terminal)

FastAPI terminalinde önce `conda activate hukuk` çalıştırın.

| Terminal | Komut | Port |
|---|---|---|
| LM Studio | GUI'den başlat | 1234 |
| FastAPI | `uvicorn main:app --app-dir backend --port 8000` | 8000 |
| React | `cd frontend && npm run dev` | 5173 |

Tarayıcıda aç: **http://localhost:5173**

---

## 🗂️ Klasör Düzeni — 20 Kasım 2026

Kök dizindeki dağınıklık giderildi; kod ve davranış değişmedi.

| Önce | Sonra |
|---|---|
| Kökte 8 Python dosyası + `requirements.txt` | `backend/` |
| `ceza_kanunu_duzeltilmis_2/tck_rag.json`, `eklenebilir_hukuk/*_rag.json` | `data/rag/` |
| `hukuk_sozlugu/ceza_hukuku_ontolojisi.json` | `data/ontoloji/` |
| `tck_chromadb/` | `data/chromadb/` (yerel, gitignore) |
| PDF'ler, ara JSON'lar, `hukuk_gerekceleri.txt` (üç farklı klasörde) | `data/ham/` altında özgün klasör adlarıyla (yerel, gitignore) |
| `nginx.conf` | `docker/nginx.conf` |

Güncellenen komutlar (proje kökünden):

```bash
uvicorn main:app --app-dir backend --port 8000
python -m unittest backend.test_main
python backend/tck_indeksleme.py
python eval/arama_degerlendir.py
```

Mevcut kurulumlarda `.env` içindeki yollar `data/chromadb`, `data/rag/...` ve `data/ontoloji/...` olarak değiştirilmelidir (`.env.example` güncel). Doğrulama: 23 test hem kökten hem `backend/` içinden geçti; ölçüm sonucu değişmedi (LLM'siz %90); API iki başlatma şekliyle de açıldı (1695 kayıt); frontend lint ve build hatasız; Docker `COPY` yolları küçük bir kontrol imajıyla doğrulandı (`.env` ve PDF imaja girmiyor).

---

## 📈 Hukuki Kalite İyileştirmeleri — 16 Kasım 2026

Model değiştirilmeden (Gemma 4 E2B) modele giden kaynakların doğruluğu ve ceza bilgisinin kaynağa bağlılığı artırıldı.

### ➕ Eklenenler

| Ne | Ne işe yarar |
|---|---|
| `eval/vakalar.json` + `eval/arama_degerlendir.py` | 18 vakalık ölçüm seti. Her vakada bulunması zorunlu ve "olması iyi" maddeler var. `python eval/arama_degerlendir.py` LLM'siz, `--llm` ile Aşama 1 LM Studio'da çalışır. Hukuki doğruluğu değil, modele doğru kaynağın gidip gitmediğini ölçer. |
| `penalties.py` — ceza tablosu | Bulunan TCK maddelerinin fıkralarından ceza ve şikâyet cümleleri çıkarılır ve mütalaa çağrısına kısa bir "CEZA VE ŞİKÂYET TABLOSU" olarak eklenir (en çok ~1800 karakter, madde başına 5 satır). Model temel fıkranın yanında hafif/nitelikli halleri (ör. 86/2, 116/4) ayrı satırlar olarak görür. |
| `penalties.py` — aralık doğrulaması | Yanıttaki "X'den Y'ye kadar" aralıkları sayıya çevrilir ("bir yıl altı ay" = "18 ay") ve kaynak metinlerle karşılaştırılır. Kaynakta karşılığı olmayan aralık varsa yanıtın sonuna "⚠️ Otomatik kontrol" notu eklenir. |
| Ontoloji: 11 temel suç | Hırsızlık, kasten yaralama, tehdit, konut dokunulmazlığı (işyeri dahil), mala zarar verme, yağma, şantaj, dolandırıcılık, konuşmaların kayda alınması, özel hayatın gizliliği, meşru savunma. Önceki 107 kavramda bu temel suçlar yoktu. |
| Kök eşleşmesi | Sonu `*` olan halk dili karşılıkları kelime başından eşleşir: `çaldı*` → "çaldılar"; "çalıştım" eşleşmez. |
| Başlık eşleşmesi (`retrieval.py`) | Kavram bir TCK/CMK maddesinin başlığında bütün olarak geçiyorsa o maddeye aramada ek oy verilir (ör. "meşru savunma" → TCK 25). |
| 6 yeni test | Ceza tablosu, aralık ayrıştırma, kaynaksız aralık uyarısı, başlık ve kök eşleşmesi. Toplam 23 test. |

### 🔁 Değişenler

- **Mütalaa promptu (`prompts.py`):** "Temel ceza aralığını kategorik bilgi olarak ver" izni kaldırıldı. Aralık tablodan veya kaynaktan AYNEN alınır, kaynakta yoksa yazılmaz. Model olaya uyan fıkrayı seçip gerekçelendirir. Yaygın yanlışlara iki madde eklendi: kavgada haksız tahrik (TCK 29) ve karşılıklı hakaret (TCK 129) ihtimali, hafif/nitelikli fıkrayı atlamak.
- **LM Studio önerisi:** 9216 token bağlam ve tek paralel slot. Ceza tablosu yaklaşık 500 token ekler.

### 📊 Ölçüm sonuçları (18 vaka, 21 zorunlu madde, N_RESULTS=8)

| Mod | Önce | Sonra |
|---|---:|---:|
| Kavramlar LM Studio ile (`--llm`, gerçek pipeline'a yakın) | 16/21 = %76 | **21/21 = %100** |
| LLM'siz (soru + ontoloji) | 9/21 = %43 | **19/21 = %90** |
| "Olması iyi" maddeler (`--llm`) | 1/5 = %20 | 3/5 = %60 |

Aşama 1'de sıcaklık 0,3 olduğu için `--llm` sonuçları çalıştırmadan çalıştırmaya biraz değişebilir.

### 🧪 Gerçek Gemma 4 E2B ile kontrol (9216 bağlam, tek slot)

- **Kavga, küfür ve tokat (81 sn):** TCK 125/1, 125/4 ve 86/1 doğru aktarıldı. **86/2 hafif yaralama ve şikâyet şartı ayrıca değerlendirildi**; önceki sürümde bu yoktu. Otomatik kontrol, yanıtın bir yerinde 86/2 için yanlış yazılan "altı aydan bir yıla kadar" aralığını doğru şekilde işaretledi. Zayıf yönler: haksız tahrik ele alınmadı (TCK 29 bu çalıştırmada kaynaklara girmedi). Hakaretin şikâyete bağlılığı TCK 131'de düzenlendiği ve kaynaklarda olmadığı için bu kısım belirsiz/hatalı anlatıldı.
- **Gece kapıyı kırıp eve girme ve tehdit (107 sn):** Avukat değerlendirmesinde önceden kaçırılan **TCK 116/4 (gece vakti, cebir/tehdit) nitelikli hali doğru tespit edildi**. TCK 151 mala zarar verme ve TCK 106 tehdit de bulundu. Zayıf yön: "Bu suçların tamamı şikâyete bağlıdır" genellemesi hatalı; 116/4 ve tehdidin temel hali şikâyete bağlı değildir.

Sonuç: Kaynak bulma ve fıkra seçimi belirgin şekilde iyileşti. Küçük modelin usul bilgisi (şikâyet, HAGB) ve genellemeleri hâlâ avukat kontrolü gerektirir.

---

## 🧹 Sadeleştirme — 16 Kasım 2026

Amaç, hukuki çıktıyı (promptlar, arama, model ayarları) değiştirmeden projedeki katman ve dosya sayısını azaltmaktı. Promptlar yeni dosyaya karakteri karakterine aynı taşındı; bu otomatik karşılaştırmayla doğrulandı.

### ➖ Çıkarılanlar

| Ne | Neden |
|---|---|
| `dotnet-gateway/` (ASP.NET Core, 14 dosya) | Yalnızca isteği FastAPI'ye iletiyordu. Doğrulama (Pydantic), CORS ve SSE zaten FastAPI'de. Zincir artık **React → FastAPI → LM Studio**. |
| Docker `gateway` servisi ve .NET derleme aşamaları | Compose servisleri `setup`, `api`, `web`'e indi. Nginx `/api/` isteklerini doğrudan `api:8000`'e iletir. |
| `POST /api/v1/analyze` (JSON, akışsız uç) | Arayüz yalnızca SSE ucunu kullanıyordu. Bu uç ve ona ait test kaldırıldı. |
| `DOCKER_YAPILACAKLAR.md` | Tüm maddeleri tamamlanmıştı; içerik bu README'de zaten var. |
| Yerel kalıntılar: `target/`, `src/` (eski Spring Boot), `__pycache__/`, `frontend/dist/` | Derleme çıktıları ve boş klasörler; gerektiğinde yeniden oluşur. Repoda zaten yoktu. |

### ➕ Eklenenler / Bölünenler

| Ne | İçerik |
|---|---|
| `prompts.py` | `TERCUMAN_PROMPTU`, `SISTEM_PROMPTU`, `MISSING_CHECK_PROMPT` (birebir taşındı) |
| `retrieval.py` | `BM25Index`, `_retrieve_articles` ve yardımcıları: E5 + BM25 hibrit arama, RRF |
| `main.py` | 781 satırdan 468 satıra indi: yalnızca pipeline, SSE ucu, `/health` |
| `frontend/src/components/` | `Chat.jsx` 474 satırdan 262 satıra indi; `MessageBubble`, `EmptyState`, `TypingIndicator` ayrı bileşenler |
| `frontend/src/lib/` | `sse.js` (SSE okuyucu), `history.js` (yerel sohbet kaydı), `legalRefs.js` (kaynak referansı ayrıştırma) |
| `.gitignore` | Genel `*.pdf` kuralı: ham kaynaklar (PDF, ara JSON, txt) yerelde kalır; repoda yalnızca 5 RAG JSON ve ontoloji bulunur |

### 🔁 Davranış değişiklikleri

- Arayüzün varsayılan API adresi `http://localhost:8080/api/chat` yerine `http://localhost:8000/api/v1/analyze` oldu (Docker'da `/api/v1/analyze`).
- Yerel çalıştırma için LM Studio dışında 2 terminal yeterli: FastAPI ve React.
- 8000 portu başka bir uygulama tarafından kullanılıyorsa API'yi `uvicorn main:app --app-dir backend --port 8001` ile başlatın ve frontend'i `VITE_API_URL=http://localhost:8001/api/v1/analyze` ile çalıştırın.

### ✅ Doğrulama

- 17 regresyon testi geçti; hem tam bağımlılıklarla (`hukuk` ortamı) hem bağımlılıksız AST modunda çalıştırıldı.
- Frontend lint ve üretim derlemesi hatasız.
- API gerçek ChromaDB ile açıldı: `/health` → `ok`, 1695 kayıt, LM Studio erişilebilir. Boş soru 422 dönüyor, `localhost:5173` için CORS izinli.
- Gerçek Gemma 4 E2B ile iki soru uçtan uca tamamlandı: çok fiilli olay (küfür + tokat) 104 sn, doğrudan madde sorusu (`TCK 116 neyi düzenler?`) 73 sn. Teknik akışı doğrular; hukuki doğruluk ayrıca değerlendirilmelidir. İlk yanıtta TCK 86/1 aralığı kaynakla uyumluydu (güncel metin: bir yıl altı aydan üç yıla); ancak tokat için 86/2 (hafif yaralama) ve kavgada haksız tahrik (TCK 29) / karşılıklı hakaret (TCK 129) değerlendirilmedi. Bu eksikler aşağıdaki iyileştirmelerin konusu oldu.
- Docker imajları bu değişiklikten sonra yeniden derlenmedi.

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
- [x] Arama kalitesini örnek vakalarla ölçme (`eval/`, 18 vaka)
- [x] Fıkra bazında ceza tablosu ve ceza aralığı doğrulaması
- [ ] Ölçüm setini genişletme ve yanıt kalitesini (LLM çıktısı) otomatik puanlama
- [ ] Her suç için ayrı mütalaa çağrısı ve cross-encoder re-ranker (gerekirse)
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

Son 100 mesaj aynı tarayıcı profilinin `localStorage` alanında saklanır; backend sohbet veritabanı oluşturmaz. **Sohbeti sil** hem ekrandaki hem kalıcı kaydı kaldırır ve devam eden isteği iptal eder. **Sohbeti bu tarayıcıda kaydet** kapatılırsa önceki kalıcı kayıt silinir; mevcut mesajlar sayfa kapanana kadar ekranda kalır. Kayıt şifreli değildir; tarayıcı profilini kullanan kişi erişebilir. API soru metnini ve cevap gövdesini loglamaz.

Ek soru önerildiğinde kısa bilgi yazılabilir veya **Mevcut bilgilerle yanıtla** seçilebilir. Normal sorular birbirinden bağımsızdır; yalnızca bu tek netleştirme yanıtı asıl olayla birlikte modele gönderilir.

Arayüz API adresi isteğe bağlı `VITE_API_URL` ile değiştirilebilir (varsayılan `http://localhost:8000/api/v1/analyze`). Tek analiz ucu SSE akışıdır: `POST /api/v1/analyze/stream`. Sağlık kontrolü: `GET /health`. İstek alanları: `soru`, isteğe bağlı `ek_bilgi` (en çok 1200 karakter), `ek_soru` ve `ek_soru_yanitlandi`.

---

## 📁 Proje Yapısı

```
├── backend/                        # Python API (FastAPI) ve araçları
│   ├── main.py                     # Pipeline, SSE ucu, /health
│   ├── prompts.py                  # LLM promptları (tercüman, mütalaa, eksik suç)
│   ├── retrieval.py                # Hibrit arama: E5 + BM25 + başlık eşleşmesi, RRF
│   ├── penalties.py                # Fıkra bazında ceza tablosu ve ceza aralığı doğrulaması
│   ├── tck_indeksleme.py           # ChromaDB indeksleme scripti
│   ├── docker_setup.py             # Docker setup: E5 önbelleği + indeksleme
│   ├── test_main.py                # Model/GPU gerektirmeyen regresyon testleri (23)
│   └── requirements.txt            # Python bağımlılıkları
│
├── frontend/                       # React + Vite + Tailwind UI
│   └── src/
│       ├── components/             # Chat, MessageBubble, MessageContent, EmptyState, TypingIndicator
│       └── lib/                    # SSE okuyucu, yerel sohbet kaydı, kaynak referansı ayrıştırma
│
├── data/
│   ├── rag/                        # 5 RAG JSON: TCK, gerekçeler, CMK, CGTİK, genel hükümler
│   ├── ontoloji/                   # Hukuk ontolojisi (118 kavram, 578 eşleme)
│   ├── ham/                        # Ham kaynaklar: PDF, ara JSON, txt (yalnızca yerelde, gitignore)
│   └── chromadb/                   # Yerel vektör indeksi (yalnızca yerelde, gitignore)
│
├── eval/                           # Ölçüm seti (vakalar.json) ve arama değerlendirme scripti
├── docker/nginx.conf               # Arayüz sunumu ve FastAPI'ye SSE proxy
├── Dockerfile                      # Python API ve frontend/Nginx derleme hedefleri
├── compose.yaml                    # İlk hazırlık, API ve web servisleri
└── .env.example                    # Konfigürasyon şablonu
```

---

## 📜 Lisans

Bu proje eğitim amaçlıdır. TCK metinleri kamu malıdır (Resmi Gazete).
