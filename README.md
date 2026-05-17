# ⚖️ TCK Hukuk Asistanı — Multi-Corpus RAG Sistemi

> **Tamamen yerel** çalışan, **Türk Ceza Hukuku** alanında uzmanlaşmış bir RAG (Retrieval-Augmented Generation) tabanlı hukuki danışma asistanı. Halk ağzıyla yazılmış olayları analiz eder, ilgili kanun maddelerini otomatik bulur, profesyonel hukukçu metodolojisiyle **mütalaa** üretir.

Türkçe doğal dil ile yazılmış sorular alır, **5 farklı hukuki kaynaktan** (TCK, TCK Gerekçeleri, CMK, CGTIK, Genel Hükümler Doktrini) ilgili maddeleri vektör arama ile bulur, yerel bir LLM (Gemma 4) üzerinden **5-adımlı hukuki metodoloji** ile cevap üretir. Tüm pipeline tamamen yereldir; veri internete çıkmaz, gizlilik garanti altındadır.

---

## 📺 Örnek Kullanım

**Kullanıcı sorusu (halk dili):**
> *"Eski iş ortağım rızam dışında şirket ofisime geldi. Girişteki sekreterimi sertçe iterek zorla odama daldı. Masamın üzerinde duran bilgisayar monitörünü yere fırlatıp kırdı. Sonra da bana 'Seni bu sektörde ticari olarak bitireceğim, batıracağım seni hırsız herif!' diye bağırarak üzerime yürüdü. TCK'ya göre bu şahıs hangi suçları işlemiştir?"*

**Sistemin cevabı (özet):**
- 5 ayrı suç tespit eder: İşyeri Dokunulmazlığı İhlali (TCK 116), Kasten Yaralama (TCK 86), Mala Zarar Verme (TCK 151), Tehdit (TCK 106), Hakaret (TCK 125)
- Her suç için: **Fiil → Hukuki Nitelendirme → Maddi Unsur → Hukuka Aykırılık Kontrolü → Ceza ve Sonuç**
- İçtima değerlendirmesi (gerçek/fikri içtima)
- Pratik sonuç: hapis cezası ihtimali, HAGB durumu, şikayet süresi

---

## 🎯 Temel Özellikler

| Özellik | Açıklama |
|---|---|
| 🔒 **%100 Yerel** | Hiçbir veri internete çıkmaz, tüm işlem yerel sunucularda |
| 📚 **Multi-Corpus** | 5 farklı kaynak (1695+ doküman) tek koleksiyonda |
| 🧠 **Halk Dili Anlama** | 107 hukuki kavram, 499 halk dili eşlemesi ("küfür" → "hakaret") |
| 🔍 **4 Aşamalı Pipeline** | Tercüman → Multi-Query Retrieval → Eksik Suç Kontrolü → Yapılandırılmış Mütalaa |
| 📐 **Hukuk Metodolojisi** | Türk hukuk pratiğine uygun 5-adımlı per-suç analiz şablonu |
| 🎨 **Modern UI** | React + Tailwind + ChatGPT-tarzı sohbet arayüzü, multi-kaynak rozetler |
| ⚡ **Düşük Halüsinasyon** | Resmi başlıklar + hukuka aykırılık kontrolü + sıkı prompt mühendisliği |
| 🔧 **Mikroservis Mimarisi** | Frontend → Gateway → RAG Engine → LLM (4 ayrı süreç) |

---

## 🏗️ Sistem Mimarisi

```
┌──────────────────────────────────────────────────────────────────┐
│                      KULLANICI TARAYICISI                        │
│                    http://localhost:5173                         │
└──────────────────────────────┬───────────────────────────────────┘
                               │ POST /api/chat
                               │ {"soru": "..."}
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  REACT FRONTEND (Vite + Tailwind)                                │
│  • Chat UI (ChatGPT-tarzı sohbet)                                │
│  • Multi-corpus rozetler (TCK 125, CMK 91, CGTIK 172)            │
│  • "Kullanılan kaynaklar" + "Diğer aday kaynaklar" expandable    │
│  • Axios (660 sn timeout)                                        │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTP
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  SPRING BOOT GATEWAY (port 8080)                                 │
│  • REST proxy (Java 17 + WebFlux WebClient)                      │
│  • CORS (React origin'leri için)                                 │
│  • Request validation, error mapping                             │
│  • Timeout: 600 sn (LLM ağır işlerde)                            │
└──────────────────────────────┬───────────────────────────────────┘
                               │ POST /api/v1/analyze
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  FASTAPI RAG ENGINE (port 8000) — 4 AŞAMALI PIPELINE             │
│                                                                  │
│  ┌─ AŞAMA 1: TERCÜMAN ──────────────────────────────────────┐    │
│  │ Halk ağzı → Hukuki kavramlar                             │    │
│  │ • LLM (Gemma 4) ile kavram çıkarma                       │    │
│  │ • Halk dili ontolojisi ile zenginleştirme                │    │
│  │   "küfür" → "hakaret", "ofisime daldı" → "konut dok."    │    │
│  └────────────────────────┬─────────────────────────────────┘    │
│                           │ ["hakaret", "tehdit", "mala zarar"]   │
│                           ▼                                       │
│  ┌─ AŞAMA 2: MULTI-QUERY RETRIEVAL ─────────────────────────┐    │
│  │ Her kavram için ayrı ChromaDB sorgusu                    │    │
│  │ • Embedding: multilingual-e5-base                        │    │
│  │ • Reciprocal Rank Fusion (RRF) ile birleştirme           │    │
│  │ • Mülga maddeleri otomatik dışla (where=mulga:False)     │    │
│  └────────────────────────┬─────────────────────────────────┘    │
│                           │ Top-8 madde (5 kaynaktan karışık)    │
│                           ▼                                       │
│  ┌─ AŞAMA 2.5: EKSİK SUÇ KONTROLÜ (İteratif Refinement) ───┐    │
│  │ Mini LLM çağrısı                                         │    │
│  │ • "Bu olayda gözden kaçan suç tipi var mı?"              │    │
│  │ • Eksik tespit edilirse → ek retrieval                   │    │
│  │ • Hata durumunda sessizce devam (pipeline bozulmaz)      │    │
│  └────────────────────────┬─────────────────────────────────┘    │
│                           │ Genişletilmiş madde listesi          │
│                           ▼                                       │
│  ┌─ AŞAMA 3: MÜTALAA ──────────────────────────────────────┐    │
│  │ 7 kurallı sistem prompt + 5-adımlı per-suç metodoloji   │    │
│  │   1. Fiil tespiti                                        │    │
│  │   2. Hukuki Nitelendirme                                 │    │
│  │   3. Maddi Unsur Kontrolü                                │    │
│  │   4. Hukuka Aykırılık Kontrolü (KRİTİK)                  │    │
│  │   5. Ceza ve Sonuç                                       │    │
│  │ + İçtima Değerlendirmesi (gerçek/fikri/zincirleme)       │    │
│  │ + Pratik Sonuç (hapis cezası, HAGB, şikayet)             │    │
│  │ • Temperature: 0.1 (hukuki tutarlılık)                   │    │
│  │ • max_tokens: 4000                                       │    │
│  └────────────────────────┬─────────────────────────────────┘    │
└────────────────────────────┼─────────────────────────────────────┘
                             │ JSON: {mutalaa, kavramlar, maddeler}
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  CHROMADB VECTOR STORE                                           │
│  • 1695+ doküman tek koleksiyonda                                │
│  • HNSW index, cosine similarity                                 │
│  • Metadata: kaynak_kodu, baslik, kitap, kisim, bolum, mulga, …  │
│  • Persistent storage (tck_chromadb/)                            │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  LM STUDIO (yerel LLM sunucusu, port 1234)                       │
│  • Model: Gemma 4 E4B Instruct (Q4_K_M, ~5 GB)                   │
│  • Context: 8500 token                                           │
│  • OpenAI-uyumlu API                                             │
│  • 4-7 dk/cevap (RTX 3050 4GB VRAM, kısmi CPU offload)           │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📚 Veri Kaynakları

Tüm kaynaklar **tek bir ChromaDB koleksiyonunda** indekslenir, `kaynak_kodu` metadata alanı ile ayrılır. Bu sayede tek bir vektör aramasıyla farklı kaynaklardan ilgili maddeler bulunabilir.

| Kaynak | Doc | Açıklama | Path |
|---|---|---|---|
| **TCK** | 364 | Türk Ceza Kanunu (5237 sayılı), 343 madde | `ceza_kanunu_duzeltilmis_2/tck_rag.json` |
| **TCK_GEREKCE** | 487 | TCK madde gerekçeleri | `eklenebilir_hukuk/tck_gerekceleri_rag.json` |
| **CMK** | 407 | Ceza Muhakemesi Kanunu (5271 sayılı) | `eklenebilir_hukuk/cmk_rag.json` |
| **CGTIK** | 231 | Ceza ve Güvenlik Tedbirlerinin İnfazı Hakkında Tüzük | `eklenebilir_hukuk/cgtik_rag.json` |
| **TCK_DOKTRIN** | 206 | Genel Hükümler Doktrini (Yargıtay kararları, chunklanmış) | `eklenebilir_hukuk/genelhukumler_rag.json` |
| **TOPLAM** | **1695** | | |

### Veri Şeması (Universal)

Her doküman için **18 alan**:
```json
{
  "id": "tck-m125",
  "kaynak_kodu": "TCK",
  "kaynak_tipi": "kanun",
  "kaynak_adi": "Türk Ceza Kanunu",
  "kaynak_no": "5237",
  "birim_no": 125,
  "baslik": "Hakaret",
  "kitap": "İkinci Kitap - Özel Hükümler",
  "kisim": "İkinci Kısım - Kişilere Karşı Suçlar",
  "bolum": "Sekizinci Bölüm - Şerefe Karşı Suçlar",
  "hiyerarsi": "TCK > İkinci Kitap > İkinci Kısım > Sekizinci Bölüm",
  "konu": "Şerefe Karşı Suçlar",
  "mulga": false,
  "metin": "(1) Bir kimseye onur, şeref ve saygınlığını...",
  "fikralar": [{"no": 1, "metin": "...", "mulga": false}],
  "referans_maddeler": [],
  "degisiklikler": ["Değişik: 29/6/2005 – 5377/15 md."],
  "embedding_text": "TCK Madde 125\nBaşlık: Hakaret\nKonu: Şerefe Karşı Suçlar\n\n(1) Bir kimseye..."
}
```

### Hukuk Ontolojisi

`hukuk_sozlugu/ceza_hukuku_ontolojisi.json` — **107 hukuki kavram**, her biri için:
- `resmi_terim` (örn: `"hakaret"`)
- `ingilizce_karsilik` (örn: `"defamation"`)
- `halk_dili_karsiliklari` — toplam **499 eşleme**: `["küfür", "sövme", "aşağılama", "ağır laf etme", "şerefine laf etme", "iftira"]`
- `iliskili_kavramlar`

Bu ontoloji **Stage 1 Tercüman**'ı güçlendirir: halk dili kelimeleri otomatik olarak resmi hukuki kavramlara eşlenir, LLM'in kaçırabileceği eşleştirmeler deterministik olarak yakalanır.

---

## 🔧 Teknoloji Stack

### Backend — RAG Engine (Python)
- **FastAPI** 0.136 — REST API, async endpoint, lifespan ile model yükleme
- **sentence-transformers** + [`intfloat/multilingual-e5-base`](https://huggingface.co/intfloat/multilingual-e5-base) — Embedding modeli (Türkçe için optimize)
- **ChromaDB** 1.5 — Persistent vektör veritabanı, HNSW index, cosine similarity
- **OpenAI Python SDK** — LM Studio'ya OpenAI-uyumlu istek
- **python-dotenv** — Konfigürasyon yönetimi
- **Pydantic** — Request/Response şemaları

### Gateway (Java)
- **Spring Boot** 3.3.5
- **Java 17**
- **WebClient** (Reactor Netty) — Non-blocking HTTP istemcisi
- **Jakarta Validation** — Request validation
- **Maven** — Build sistemi

### Frontend (JavaScript)
- **React** 19 + **Vite** 8
- **Tailwind CSS** v3
- **Axios** — HTTP istemcisi
- **PostCSS** + **Autoprefixer**
- ChatGPT-tarzı UI, multi-corpus regex highlight, "diğer aday kaynaklar" expandable bölüm

### Yerel LLM
- **LM Studio** (https://lmstudio.ai) — Yerel LLM sunucusu
- **Gemma 4 E4B Instruct** (Q4_K_M quantize, ~5 GB)
- **Context Length: 8500 token**
- OpenAI-uyumlu `/v1/chat/completions` endpoint

---

## 📋 Gereksinimler

### Yazılım
| Bileşen | Sürüm |
|---|---|
| **Python** | 3.11 (Conda env önerilir) |
| **Java** | 17+ |
| **Maven** | 3.9+ |
| **Node.js** | 20+ |
| **npm** | 10+ |
| **LM Studio** | En güncel |

### Donanım (Önerilen)
- **8 GB RAM** minimum (16 GB önerilir)
- **NVIDIA GPU** 4 GB+ VRAM (yoksa tamamen CPU'da çok yavaş çalışır — 15+ dk/cevap)
- **10 GB boş disk** (LLM modeli + ChromaDB + node_modules)

---

## 🚀 Kurulum

### 1. Repoyu Klonla
```bash
git clone https://github.com/beratoz/gemma_ile_hukuk.git
cd gemma_ile_hukuk
```

### 2. Python Ortamı
```bash
conda create -n rag python=3.11 -y
conda activate rag
pip install -r requirements.txt
```

### 3. Frontend Bağımlılıkları
```bash
cd frontend
npm install
cd ..
```

### 4. LM Studio Kurulumu
1. [LM Studio](https://lmstudio.ai)'yu indir ve kur
2. **Gemma 4 E4B Instruct** modelini indir (Q4_K_M yeterli)
3. Developer sekmesi → modeli yükle
4. **Context Length: 8500** ayarla (Settings → Load Configuration)
5. Server'ı başlat (port 1234)

### 5. Konfigürasyon (`.env`)
`.env.example`'i kopyala ve düzenle:
```bash
cp .env.example .env
```

`.env` içeriği:
```bash
# ChromaDB
CHROMA_DB_PATH=C:/Users/berat/Desktop/Gemma_Hukuk/tck_chromadb
COLLECTION_NAME=tck_koleksiyonu_e5

# Data sources (multi-corpus, virgülle ayrılmış)
DATASETS_PATHS=C:/Users/berat/.../tck_rag.json,C:/Users/berat/.../tck_gerekceleri_rag.json,C:/Users/berat/.../cmk_rag.json,C:/Users/berat/.../cgtik_rag.json,C:/Users/berat/.../genelhukumler_rag.json
ONTOLOGY_PATH=C:/Users/berat/.../hukuk_sozlugu/ceza_hukuku_ontolojisi.json

# Embedding
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-base
N_RESULTS=8

# LM Studio
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LM_STUDIO_API_KEY=lm-studio
LM_MODEL_NAME=google/gemma-4-e4b

# API
API_HOST=0.0.0.0
API_PORT=8000
```

### 6. ChromaDB İndeksleme (Tek Seferlik)
```bash
python tck_indeksleme.py
```

Bu script:
- 5 JSON kaynağını yükler
- Doktrin metinlerini chunklar (1800 char + 200 overlap)
- multilingual-e5-base ile embedding üretir
- ChromaDB'ye yazar (1695 doc)
- 6 doğrulama testi yapar

⏱️ Süre: ~5 dakika (ilk seferde embedding modeli indirilir)

---

## ▶️ Çalıştırma

**4 farklı terminal** açın:

### Terminal 1 — LM Studio
GUI'den başlat, Developer sekmesi → Server: Running (port 1234)

### Terminal 2 — FastAPI RAG Engine
```bash
conda activate rag
uvicorn main:app --port 8000
```

Başlangıçta görmek istediğiniz log:
```
Embedding modeli yükleniyor...
ChromaDB bağlantısı kuruluyor...
'tck_koleksiyonu_e5' koleksiyonuna bağlanıldı.
Hukuk ontolojisi yüklendi: 107 kavram, 499 halk dili eşlemesi.
LM Studio istemcisi hazırlanıyor.
Tüm bileşenler hazır. API çalışmaya hazır.
```

### Terminal 3 — Spring Boot Gateway
```bash
mvn spring-boot:run
```

Beklenen log: `Started GatewayApplication in X seconds`, Tomcat port 8080.

### Terminal 4 — React Frontend
```bash
cd frontend
npm run dev
```

Tarayıcıda aç: **http://localhost:5173**

---

## 📁 Proje Yapısı

```
.
├── main.py                            # FastAPI ana uygulama (4-aşamalı RAG pipeline)
├── tck_indeksleme.py                  # ChromaDB multi-source indeksleme
├── tck_rag_chatbot.py                 # Eski CLI sürüm (referans için)
├── generate_titles.py                 # Tek seferlik: LLM ile TCK başlık üretici
├── requirements.txt                   # Python bağımlılıkları
├── .env.example                       # Konfigürasyon şablonu
├── pom.xml                            # Maven (Spring Boot gateway)
│
├── src/main/                          # Java kaynak kodu
│   ├── java/com/berat/legaltech/gateway/
│   │   ├── GatewayApplication.java    # Main class
│   │   ├── config/
│   │   │   ├── WebClientConfig.java   # FastAPI istemcisi (Netty timeout)
│   │   │   └── CorsConfig.java        # CORS (5173, 3000)
│   │   ├── controller/
│   │   │   └── ChatController.java    # POST /api/chat endpoint
│   │   ├── service/
│   │   │   └── AnalyzeService.java    # FastAPI'ye forward, error mapping
│   │   ├── dto/
│   │   │   ├── ChatRequest.java       # Validation: soru min 3 max 4000 char
│   │   │   ├── AnalyzeResponse.java   # @JsonProperty ile snake_case mapping
│   │   │   └── ErrorResponse.java
│   │   └── exception/
│   │       ├── PythonServiceException.java
│   │       └── GlobalExceptionHandler.java
│   └── resources/application.yml      # port 8080, FastAPI URL, timeout 600 sn
│
├── frontend/                          # React + Vite + Tailwind
│   ├── package.json
│   ├── vite.config.js, tailwind.config.js, postcss.config.js
│   ├── index.html
│   └── src/
│       ├── App.jsx, main.jsx, index.css
│       └── components/
│           ├── Chat.jsx               # Ana sohbet bileşeni
│           │                          # • State: messages, input, isLoading
│           │                          # • Multi-corpus regex (TCK/CMK/CGTIK)
│           │                          # • Axios 660 sn timeout
│           │                          # • "Kullanılan kaynaklar" rozetleri
│           │                          # • "Diğer aday kaynaklar" expandable
│           └── MessageContent.jsx     # Mütalaa metnindeki referans highlight
│
├── ceza_kanunu_duzeltilmis/           # Eski (Phase 1) veri seti — referans
│   ├── tck_maddeler.json
│   ├── tck_maddeler_temiz.json
│   ├── tck_basliklar.json             # LLM-üretimi başlıklar
│   └── tck_basliklar_override.json    # Manuel düzeltme
│
├── ceza_kanunu_duzeltilmis_2/         # Phase 2.0 resmi veri seti
│   ├── tck_meta.json                  # Kanun metadata (5237 vb.)
│   ├── tck_basliklar_resmi.json       # 343 RESMİ marjinal başlık
│   ├── tck_hiyerarsi.json             # Kitap > Kısım > Bölüm ağacı
│   ├── tck_rag.json                   # 343 madde, 18 alan (RAG-hazır)
│   └── tck_rag_chunks.json            # 381 chunk (alternatif granular)
│
├── eklenebilir_hukuk/                 # Multi-corpus ek kaynaklar
│   ├── tck_gerekceleri_rag.json       # 343 madde gerekçe
│   ├── cmk_rag.json                   # 335 CMK madde
│   ├── cgtik_rag.json                 # 197 CGTIK madde
│   ├── genelhukumler_rag.json         # 41 doktrin parçası (chunklanır)
│   ├── *.pdf                          # Kaynak PDF'leri
│   └── hukuk_gerekceleri.txt
│
├── hukuk_sozlugu/                     # Hukuki ontoloji
│   ├── ceza_hukuku_ontolojisi.json    # 107 kavram, 499 halk dili eşleme
│   └── hukuk-terminoloji-110615.pdf
│
├── tck_chromadb/                      # ChromaDB persistent storage
│   ├── chroma.sqlite3
│   └── <uuid>/                        # HNSW index segmentleri
│       ├── data_level0.bin
│       ├── header.bin
│       ├── length.bin
│       └── link_lists.bin
│
└── target/                            # Maven build çıktısı
```

---

## 🧠 Önemli Teknik Detaylar

### E5 Modeli için Prefix Kullanımı
`intfloat/multilingual-e5-base` modeli **asimetrik retrieval** için tasarlanmıştır:
- **İndeksleme sırasında**: `"passage: " + metin`
- **Sorgu sırasında**: `"query: " + soru`

Bu prefix'ler atlanırsa retrieval doğruluğu ciddi düşer. Her iki script de bunları otomatik ekler.

### Multi-Query Retrieval ve RRF
Stage 1'in çıkardığı **her kavram için ayrı ChromaDB sorgusu** yapılır. Sonuçlar **Reciprocal Rank Fusion** ile birleştirilir:

```
RRF skoru = Σ 1/(60 + rank_i)
```

Bu yöntem, tek bir birleşik sorgu yapmaktan **daha kapsamlı sonuçlar** verir — özellikle çok suçlu olaylarda her suç için kendi en alakalı maddesi bulunur.

### Stage 2.5 — İteratif Refinement
RAG'da klasik bir problem: bir suç kavramı kullanıcının sorusunda **açıkça geçmiyorsa** Stage 1 onu kaçırabilir. Bu eksiklik tüm pipeline'ı etkiler.

Çözüm: Stage 2'den sonra **mini LLM çağrısı**:
```
"Mevcut maddeler şunlar: TCK 125 (Hakaret), TCK 106 (Tehdit).
Bu olayda gözden kaçan başka suç tipi var mı?"
```

LLM eksik tespit ederse, ek retrieval yapılır ve top-K listesine dahil edilir. Pipeline'ı bozmamak için hata durumunda sessizce devam eder.

### Token Bütçesi (Stage 3)
LM Studio context 8500 token ile çalışır:
- SISTEM_PROMPTU: ~1822 token
- 8 madde retrieve (avg ~280 token/madde): ~2240 token
- Soru + format: ~200 token
- **Input toplam: ~4262 token**
- max_tokens (output): 4000
- **TOTAL: ~8262 token** (8500 limit içinde, ~238 buffer)

### Halk Dili Genişletmesi (Stage 1)
Ontolojiden **ters indeks** oluşturulur: `halk_dili_kelime → resmi_terim`.

Stage 1 LLM'in çıkardığı kavramlara, soruyu tarayarak bulunan halk dili eşlemeleri eklenir:

| Kullanıcı sorusunda | Eklenen kavram |
|---|---|
| "küfür", "sövme" | hakaret |
| "tokat", "yumruk", "itme" | kasten yaralama |
| "rızam dışında girdi" | konut/işyeri dokunulmazlığı |
| "para istedi yoksa..." | şantaj |
| "cinayet", "vurdu" | kasten adam öldürme |

Bu deterministik eşleme, LLM'in kaçırdığı durumları yakalar.

### Mütalaa Metodolojisi (Türk Hukuk Pratiğine Uygun)
Her tespit edilen suç için **5 adımlı analiz**:

1. **Fiil** — Olayda gerçekleşen eylemin tek cümle özeti
2. **Hukuki Nitelendirme** — TCK madde numarası + suç adı
3. **Maddi Unsur Kontrolü** — Fiil, netice, illiyet bağı
4. **Hukuka Aykırılık Kontrolü** ⚠️ **KRİTİK** — Meşru müdafaa, rıza, hakkın kullanılması varsa **beraat** verilir
5. **Ceza ve Sonuç** — Madde, ceza aralığı, şikayet durumu, HAGB ihtimali

Sonra **İçtima Değerlendirmesi** (gerçek/fikri/zincirleme suç) ve **Pratik Sonuç** (hapis cezası, atılacak adımlar).

### Mülga Madde Filtreleme
ChromaDB sorgularında `where={"mulga": False}` filtresi uygulanır — yürürlükten kalkmış maddeler asla LLM'e gönderilmez.

---

## 📊 Geliştirme Süreci (Faz Özeti)

| Faz | Açıklama |
|---|---|
| **Phase 0** | CLI tabanlı 3-aşamalı RAG (yalnız TCK, tek koleksiyon) |
| **Phase 1** | FastAPI'ye taşıma + Spring Boot Gateway + React UI (3 katmanlı mimari) |
| **Phase 1.5** | Title enrichment, Frontend referans filtresi, Prompt sıkılaştırma |
| **Phase 2.0** | Multi-corpus ChromaDB (5 kaynak), resmi başlıklar, hukuk ontolojisi |
| **Phase 2.0+** | 4-aşamalı pipeline: Multi-Query + Stage 2.5 İteratif Refinement + 5-adımlı metodoloji |

### Yapılan İyileştirmeler

- ✅ **S1 — Title Enrichment**: Madde başlıkları embedding text'ine eklendi (`"TCK Madde 125 - Hakaret\n..."`). Kullanıcının "hakaret" kelimesi madde içeriğinde geçmese bile başlıkla eşleşir.
- ✅ **A1 — Referans Filtresi**: Frontend mütalaadaki maddeleri regex ile parse eder, sadece kullanılanları gösterir.
- ✅ **K3 — Multi-Query Retrieval**: Her kavram için ayrı sorgu + RRF birleştirme.
- ✅ **Alt B — İteratif Refinement**: Stage 2.5 eksik suç kontrolü.
- ✅ **Halk Dili Ontolojisi**: 499 eşleme ile Stage 1 zenginleştirildi.

---

## 🎯 Roadmap (Sıradaki)

### Phase 2.1 — Retrieval Mimarisi
- [ ] **K1 — Hybrid Search**: BM25 (`rank-bm25`) + dense embedding, Reciprocal Rank Fusion
- [ ] **K2 — Cross-encoder Re-ranker**: `BAAI/bge-reranker-v2-m3` (~600 MB) ile top-30 → top-8 elemesi
- [ ] **K4 — Otomatik Prosedürel Madde Eşleme**: TCK 125 → TCK 73 (şikayet süresi) gibi otomatik bağlantılar

### Gelecek Planlar
- [ ] Daha güçlü LLM denemesi (Qwen 3 14B veya API tabanlı — Gemma 4 E4B kapasite sınırı için)
- [ ] Konuşma geçmişi (multi-turn dialogue)
- [ ] Streamed response (UX iyileştirmesi)
- [ ] Diğer kanunlar (TMK — Türk Medeni Kanunu, İİK — İcra İflas Kanunu)

---

## 🧪 Test Sonuçları

Sistemin profesyonel bir avukat tarafından değerlendirilmesi:

| Test | Vaka | Puan |
|---|---|---|
| 1 | WhatsApp grup hakaret (Phase 1 öncesi) | 4/10 |
| 2 | Eski sevgili şantaj (Phase 1 sonrası) | 4/10 |
| 3 | Trafik tartışma (Phase 2.0+ sonrası) | 6/10 |
| 4 | Ofis saldırı (max_tokens=4000) | 6/10 |

**İyileşme noktaları:**
- ✅ Çoklu suç tespiti doğru (gerçek içtima)
- ✅ TCK 125 (Hakaret), TCK 107 (Şantaj), TCK 151 (Mala Zarar) doğru bulunur

**Kalan eksiklikler:**
- ❌ Bazı nitelikli haller kaçırılıyor (örn: TCK 116/4 cebirle ihlal)
- ❌ Bazı vakalarda "Pratik Sonuç" yeterli detayda değil
- ❌ İçtima derinliği yetersiz

**Hedef:** Phase 2.1 ile 8-9/10 puana çıkış.

---

## ⚠️ Sınırlamalar ve Uyarılar

- 🚫 **Hukuki danışmanlık yerine geçmez.** Bu sistem eğitim ve araştırma amaçlıdır.
- 🚫 **Üretilen mütalaalar bir avukat tarafından mutlaka doğrulanmalıdır.**
- 🚫 **Halüsinasyon riski.** Çok katı prompt kuralları olsa bile model bazen yanlış nitelendirme yapabilir.
- 🚫 **Yargıtay içtihatları yok.** Doktrin sınırlı (sadece Genel Hükümler), spesifik içtihatlar veritabanında değil.
- 🚫 **Yavaş.** Tek cevap 4-7 dakika (LLM ağırlıklı). Senkron, streaming yok.
- 🚫 **TCK güncel olmalı.** Kanun değişikliklerinde veri seti yeniden indekslemelidir.

---

## 🤝 Katkıda Bulunma

Bu proje aktif geliştirme aşamasındadır. Katkı için:
1. Issue açın (öneri/bug)
2. Fork edin
3. Feature branch (`feature/...`) oluşturun
4. Commit'lerinizi açıklayıcı yazın
5. Pull Request açın

**Test datalarınızı eklemek için:** Universal şemayı takip eden yeni bir JSON dosyası `eklenebilir_hukuk/`'a koyun ve `.env`'deki `DATASETS_PATHS`'a ekleyin.

---

## 🔗 İlgili Repolar

- **Aktif geliştirme:** [beratoz/gemma_ile_hukuk](https://github.com/beratoz/gemma_ile_hukuk) (bu repo)
- **Snapshot/Arşiv:** [beratoz/hukuk_basarili_guncel_hali_](https://github.com/beratoz/hukuk_basarili_guncel_hali_) — Phase 2.0+ tam yedek

---

## 🙏 Teşekkürler

- [Google Gemma](https://ai.google.dev/gemma) — Dil modeli
- [LM Studio](https://lmstudio.ai/) — Yerel LLM altyapısı
- [intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base) — Embedding modeli
- [ChromaDB](https://www.trychroma.com/) — Vektör veritabanı
- [FastAPI](https://fastapi.tiangolo.com/) — Python REST framework
- [Spring Boot](https://spring.io/projects/spring-boot) — Java gateway framework
- [Vite](https://vitejs.dev/) + [React](https://react.dev/) — Frontend
- [Tailwind CSS](https://tailwindcss.com/) — UI styling

---

## 📜 Lisans

Bu proje eğitim amaçlıdır. TCK metinleri kamu malıdır (resmi gazete).
