# ⚖️ TCK Hukuk Asistanı — Yerel RAG Chatbot

Türk Ceza Kanunu (TCK) maddeleri üzerinde çalışan, **tamamen yerel** ve **internet bağlantısız** çalışan bir Retrieval-Augmented Generation (RAG) chatbot. LangChain veya benzeri framework kullanmadan, saf Python ile yazılmıştır.

> Kullanıcının verdiği hukuki sorularda, ChromaDB üzerinden ilgili kanun maddelerini bulur ve LM Studio üzerinden çalışan Gemma 4B gibi yerel bir LLM ile uydurma yapmadan, kaynak göstererek cevap üretir.

---

## 🎯 Özellikler

- 🔒 **%100 Yerel Çalışma** — Hiçbir veri internete çıkmaz, gizlilik garantili
- 📚 **343 TCK Maddesi** üzerinde semantik arama
- 🧠 **multilingual-e5-base** çok dilli embedding modeli (Türkçe için optimize)
- 🎯 **Anti-Halüsinasyon Sistem Promptu** — Model sadece sunulan maddelere göre cevap verir
- 🔍 **Top-K Retrieval** — Her soru için en alakalı 3-10 madde getirilir
- 💾 **Kalıcı Vektör Veritabanı** — ChromaDB ile bir kez indeksleme, sonsuz kullanım
- 🚀 **LangChain Bağımlılığı Yok** — Tüm akış saf Python ile, anlaşılır kod

---

## 🏗️ Mimari

```
┌─────────────────┐
│ Kullanıcı Soru  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│ E5 Embedding (query: ...)   │   ← Soru vektöre çevriliyor
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ ChromaDB Top-K Search       │   ← En benzer 3-10 madde
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Mega-Prompt Oluşturma       │   ← Kanun maddeleri + soru + kurallar
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ LM Studio (Gemma 4B)        │   ← Yerel LLM cevap üretir
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ "TCK Madde X'e göre ..."    │   ← Kaynaklı, kısa, vurucu cevap
└─────────────────────────────┘
```

---

## 📋 Gereksinimler

### Yazılım
- **Python 3.11** (3.10–3.12 arası uyumlu)
- **LM Studio** (https://lmstudio.ai) — Yerel LLM sunucusu
- **Conda / Miniconda** (önerilir)

### Donanım (önerilen minimum)
- 8 GB RAM (Gemma 4B için)
- 4 GB boş disk alanı (model + embeddings için)
- GPU şart değil ama varsa daha hızlı

### Python Kütüphaneleri
- `chromadb`
- `sentence-transformers`
- `openai`

---

## 🚀 Kurulum

### 1. Repoyu klonla
```bash
git clone https://github.com/<kullanici-adi>/tck-rag-chatbot.git
cd tck-rag-chatbot
```

### 2. Conda ortamı oluştur
```bash
conda create -n rag python=3.11 -y
conda activate rag
```

### 3. Bağımlılıkları kur
```bash
pip install chromadb sentence-transformers openai
```

### 4. LM Studio kurulumu
1. https://lmstudio.ai adresinden LM Studio'yu indir ve kur
2. İçeriden **Gemma 4B Instruct** (veya tercih ettiğin başka bir model) indir
3. **Developer** sekmesinden:
   - Modeli yükle (Load)
   - Server'ı başlat (**Status: Running** yeşil olmalı)
   - Default port: `1234`

---

## 📖 Kullanım

### Adım 1 — Vektör Veritabanını Oluştur (TEK SEFER)

`tck_indeksleme.py` dosyasındaki yolları kendi makinene göre düzenle, sonra çalıştır:

```bash
python tck_indeksleme.py
```

Bu script:
- `tck_maddeler_temiz.json` dosyasını okur (343 madde)
- Her maddeyi vektöre çevirir (`passage: ` öneki ile)
- ChromaDB'ye kaydeder
- Doğrulama testi yapar

> ⏱️ İlk seferde ~3-5 dakika sürer (embedding modeli indirilir + vektörleştirme yapılır)

### Adım 2 — Chatbot'u Çalıştır

```bash
python tck_rag_chatbot.py
```

Örnek bir oturum:
```
Soru: Hırsızlık yapan birinin cezası nedir?
>> Referans alınan maddeler: TCK Madde 141, 142, 143

Cevap: TCK Madde 141'e göre, başkasına ait taşınır bir malı, zilyedinin
rızası olmadan kendisine veya başkasına yarar sağlamak amacıyla
bulunduğu yerden alan kimseye 1 yıldan 3 yıla kadar hapis cezası verilir.
```

Çıkmak için: `q`, `çıkış`, `exit`

---

## 🗂️ Proje Yapısı

```
tck-rag-chatbot/
├── tck_indeksleme.py           # Vektör DB'yi oluşturan script (1 kez çalıştırılır)
├── tck_rag_chatbot.py          # Ana chatbot döngüsü
├── tck_maddeler_temiz.json     # Kaynak veri: 343 TCK maddesi
├── tck_chromadb/               # Otomatik oluşur — Persistent vektör DB
│   ├── chroma.sqlite3
│   └── <uuid>/
│       ├── data_level0.bin
│       ├── header.bin
│       ├── length.bin
│       └── link_lists.bin
└── README.md
```

---



## 🧠 Önemli Teknik Detaylar

### E5 Modeli için Prefix Kullanımı
`intfloat/multilingual-e5-base` modeli **asimetrik retrieval** için tasarlanmıştır:
- **İndeksleme sırasında**: `"passage: " + metin`
- **Sorgu sırasında**: `"query: " + soru`

Bu prefix'ler atlanırsa retrieval doğruluğu ciddi düşer. Her iki script de bunları otomatik ekler.

### Sıcaklık (Temperature)
Hukuki cevaplar için `temperature=0.2` kullanılır. Yaratıcılık değil, **deterministik kesinlik** istenir.

### Sistem Promptu Felsefesi
Sistem promptu modelin:
- Sadece verilen maddeleri kullanmasını
- Ceza miktarlarını yuvarlamadan aynen aktarmasını
- Yetersiz bilgi durumunda dürüstçe "yeterli değil" demesini
- Süslü, gereksiz cümleler yazmamasını sağlar

---


## 📌 Notlar ve Sınırlamalar

- Bu proje **eğitim ve araştırma amaçlıdır**, gerçek hukuki danışmanlık yerine geçmez.
- Üretilen cevaplar bir avukat tarafından mutlaka doğrulanmalıdır.
- TCK maddeleri zaman içinde değişebilir; veri seti güncel tutulmalıdır.
- Chatbot tek seferlik soru-cevap çalışır, **sohbet geçmişi tutmaz** (geliştirilebilir).

---

## 🔮 Gelecek Geliştirmeler

- [ ] Konuşma geçmişi (conversational memory)
- [ ] Hibrit arama (BM25 + dense retrieval)
- [ ] Re-ranker entegrasyonu (cross-encoder ile top-K yeniden sıralama)
- [ ] Streamlit / Gradio web arayüzü
- [ ] Diğer kanunlar (TMK, İİK) için modüler yapı



---

## 🙏 Teşekkürler

- [intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base) — Embedding modeli
- [ChromaDB](https://www.trychroma.com/) — Vektör veritabanı
- [LM Studio](https://lmstudio.ai/) — Yerel LLM altyapısı
- [Google Gemma](https://ai.google.dev/gemma) — Dil modeli
