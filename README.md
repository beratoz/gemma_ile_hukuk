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
| **LLM** | LM Studio, Gemma 4 E4B | Yerel dil modeli (OpenAI-uyumlu API) |

> **Not:** Gateway katmanı başlangıçta Spring Boot (Java) ile yazılmış, daha sonra ASP.NET Core'a migrate edilmiştir. Java versiyonu `src/` klasöründe referans olarak durmaktadır.

---

## 🔧 4-Aşamalı RAG Pipeline

**Aşama 1 — Tercüman:** Halk ağzındaki soruyu hukuki kavramlara çevirir. Özel ontoloji ile zenginleştirir (`"küfür"` → `"hakaret"`, `"ofisime daldı"` → `"işyeri dokunulmazlığı"`).

**Aşama 2 — Multi-Query Retrieval:** Her kavram için ayrı ChromaDB sorgusu yapar. Sonuçları Reciprocal Rank Fusion (RRF) ile birleştirir. Mülga maddeleri otomatik dışlar.

**Aşama 2.5 — Eksik Suç Kontrolü:** Mini LLM çağrısı ile gözden kaçan suç tiplerini tespit eder, gerekirse ek retrieval yapar.

**Aşama 3 — Mütalaa:** 5-adımlı per-suç metodoloji: Fiil → Hukuki Nitelendirme → Maddi Unsur → Hukuka Aykırılık Kontrolü → Ceza ve Sonuç. İçtima değerlendirmesi ve pratik sonuç ekler.

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
| **Frontend** | React 19, Vite, Tailwind CSS, Axios |
| **LLM** | LM Studio, Gemma 4 E4B Instruct (Q4_K_M, ~5 GB) |

---

## 📋 Gereksinimler

| Bileşen | Sürüm |
|---|---|
| **Python** | 3.11+ |
| **.NET SDK** | 8.0+ |
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
conda create -n rag python=3.11 -y
conda activate rag
pip install -r requirements.txt
```

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
[LM Studio](https://lmstudio.ai)'dan **Gemma 4 E4B Instruct** modelini yükleyin. Context: 8500 token. Port: 1234.

### 7. Servisleri Başlat (4 terminal)

| Terminal | Komut | Port |
|---|---|---|
| LM Studio | GUI'den başlat | 1234 |
| FastAPI | `uvicorn main:app --port 8000` | 8000 |
| .NET Gateway | `cd dotnet-gateway && dotnet run` | 8080 |
| React | `cd frontend && npm run dev` | 5173 |

Tarayıcıda aç: **http://localhost:5173**

---

## 📊 Test Sonuçları

| Vaka | Puan |
|---|---|
| WhatsApp grup hakaret | 4/10 |
| Eski sevgili şantaj | 4/10 |
| Trafik tartışması (Multi-Query + Ontoloji sonrası) | 6/10 |
| Ofis saldırı (5 suç tespiti) | 6/10 |

Doğruluk oranı **%60-80** aralığında. Çoklu suç tespiti, içtima değerlendirmesi, temel nitelendirmeler doğru çalışıyor. Nitelikli hallerin tespiti ve içtima derinliği geliştirilmeye devam ediyor.

---

## 🎯 Roadmap

- [ ] Hybrid Search (BM25 + Dense embedding)
- [ ] Cross-encoder Re-ranker
- [ ] Streamed response (UX)
- [ ] Konuşma geçmişi (multi-turn)
- [ ] Ek kanunlar (TMK, İİK)

---

## ⚠️ Sınırlamalar

- 🚫 **Hukuki danışmanlık yerine geçmez.** Eğitim ve araştırma amaçlıdır.
- 🚫 Üretilen mütalaalar bir avukat tarafından mutlaka doğrulanmalıdır.
- 🚫 Halüsinasyon riski mevcuttur.
- 🚫 Tek cevap 4-7 dakika sürer (LLM ağırlıklı, streaming yok).

---

## 📁 Proje Yapısı

```
├── main.py                         # FastAPI RAG Engine (4-aşamalı pipeline)
├── tck_indeksleme.py               # ChromaDB indeksleme scripti
├── tck_rag_chatbot.py              # Eski CLI sürüm (referans)
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
├── src/main/                       # [Legacy] Spring Boot Gateway (referans)
├── pom.xml                         # [Legacy] Maven build
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
