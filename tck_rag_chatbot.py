# =============================================================
# TCK RAG CHATBOT - 3 AŞAMALI MİMARİ
# Aşama 1: Hukuki Tercüman (LLM ile kavram çıkarma)
# Aşama 2: Vektör Retrieval (kavramlarla ChromaDB araması)
# Aşama 3: Nihai Mütalaa (LLM ile hukuki analiz)
# =============================================================

import chromadb
from sentence_transformers import SentenceTransformer
from openai import OpenAI

# --- 1. AYARLAR (kullanıcı değiştirebilir) ---
CHROMA_DB_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/tck_chromadb"   # Vektör DB yerel yolu
COLLECTION_NAME = "tck_koleksiyonu_e5"                                # Koleksiyon adı
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"                # Çok dilli embedding modeli
N_RESULTS = 5                                                         # Kaç madde çekilsin
LM_MODEL_NAME = "google/gemma-4-e4b"                                  # LM Studio'da yüklü model adı

# LM Studio (OpenAI uyumlu) yerel sunucu bilgileri
LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
LM_STUDIO_API_KEY = "lm-studio"

# --- 2. EMBEDDING MODELİ YÜKLEME ---
print("Embedding modeli yükleniyor... (ilk seferde indirilebilir)")
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
print("Embedding modeli hazır.\n")

# --- 3. CHROMADB BAĞLANTISI ---
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = chroma_client.get_collection(name=COLLECTION_NAME)
print(f"'{COLLECTION_NAME}' koleksiyonuna bağlanıldı.\n")

# --- 4. LM STUDIO (LLM) İSTEMCİSİ ---
llm_client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key=LM_STUDIO_API_KEY)

# --- 5A. TERCÜMAN PROMPTU (Aşama 1 - Gizli) ---
# Bu prompt kullanıcıya GÖRÜNMEZ. LLM'i kavram çıkarıcıya dönüştürür.
# Halk ağzındaki olayı saf hukuki kavramlara çevirir, retrieval'ı kurtarır.
TERCUMAN_PROMPTU = """Sen bir hukuki kavram çıkarıcısın. Sana verilen halk ağzıyla anlatılmış olayı analiz et ve TCK'da karşılık gelen en fazla 5 hukuki anahtar kelimeyi/kavramı aralarına virgül koyarak yaz.

KURALLAR:
- Cümle kurma, açıklama yapma, yorum yapma.
- Sadece virgülle ayrılmış kelime/kavramları yaz.
- Örnek format: meşru savunma, sınırın aşılması, kasten öldürme, korku ve telaş, taksir
- Türkçe ve TCK terminolojisi kullan."""

# --- 5B. MÜTALAA PROMPTU (Aşama 3 - Asıl Sistem Promptu) ---
SISTEM_PROMPTU = """Sen uzman bir ceza avukatısın. Görevin, sana sunulan TCK maddeleri arasından olayla en ilgili olanı/olanları seçip hukuki bir sonuç üretmektir.

KURALLAR:
1. SIFIR UYDURMA: Asla kendi hafızandan kanun, madde veya bilgi ekleme. SADECE sana verilen KANUN MADDELERİ'ni kullan. İlgisiz olanları ele.
2. HUKUKİ NİTELENDİRME (Kritik): Günlük dilde anlatılan fiilleri (örneğin: küfür, tokat, dikkatsizlik), maddelerdeki soyut hukuki kavramlarla (örneğin: haksız fiil, kasten yaralama, taksir) mantıksal olarak eşleştir. Seçtiğin maddeyi bu olayla bağdaştırarak açıkla.
3. ATIF VE KESİNLİK: Cevabına daima "TCK Madde [X]'e göre" diyerek başla. Ceza sürelerini ve miktarlarını (yıl/ay/gün) AYNEN aktar, asla yuvarlama.
4. GÜVENLİK: Verilen maddeler olayla kurduğun mantık çerçevesinde uyuşmuyorsa SADECE "Verilen maddeler bu soruyu cevaplamak için yeterli değildir." yaz. Başka hiçbir açıklama yapma.
5. KATI FORMAT: Kelime sınırı yoktur ancak laf kalabalığı yapma. Cevabını net, yapılandırılmış ve özet bir hukuki mütalaa şeklinde sun. "Merhaba", "Yardımcı olabileceğim başka bir şey var mı?" gibi yapay zeka süsleri KESİNLİKLE YASAK. Sadece hukuki analizi, nedensellik bağını ve nihai sonucu yaz."""

# --- 6. YARDIMCI FONKSİYONLAR ---
def llm_cevap_al(system_prompt: str, user_message: str, max_tokens: int = 2000, temperature: float = 0.2) -> str:
    """LM Studio'ya istek atar ve cevap metnini döndürür. Boş cevap durumlarında güvenli."""
    cevap = llm_client.chat.completions.create(
        model=LM_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if cevap.choices and cevap.choices[0].message.content:
        return cevap.choices[0].message.content.strip()
    return ""

# --- 7. SOHBET DÖNGÜSÜ ---
print("=" * 55)
print(" TCK Hukuk Asistanı - Çıkmak için 'q' veya 'çıkış' ")
print("=" * 55)

while True:
    kullanici_sorusu = input("\nSoru: ").strip()

    if kullanici_sorusu.lower() in ("q", "çıkış", "cikis", "exit", "quit"):
        print("Görüşmek üzere!")
        break

    if not kullanici_sorusu:
        continue

    # ============================================================
    # AŞAMA 1: HUKUKİ TERCÜMAN (Gizli LLM çağrısı)
    # Halk ağzındaki olayı saf hukuki kavramlara dönüştür
    # ============================================================
    print(">> [Aşama 1] Hukuki kavramlar çıkarılıyor...")
    hukuki_kavramlar = llm_cevap_al(
        system_prompt=TERCUMAN_PROMPTU,
        user_message=kullanici_sorusu,
        max_tokens=2000,   # thinking modeli için pay bırakıyoruz
        temperature=0.1    # kavram çıkarımı için düşük yaratıcılık
    )

    # Tercüman boş döndüyse fallback: kullanıcının orijinal sorusunu kullan
    if not hukuki_kavramlar:
        print("   (Tercüman boş döndü, orijinal soru ile devam ediliyor)")
        arama_metni = kullanici_sorusu
    else:
        print(f"   Çıkarılan kavramlar: {hukuki_kavramlar}")
        arama_metni = hukuki_kavramlar

    # ============================================================
    # AŞAMA 2: VEKTÖR RETRIEVAL (ChromaDB araması)
    # Saf hukuki kavramları vektöre çevirip en alakalı maddeleri bul
    # ============================================================
    # E5 modeli sorgular için MUTLAKA "query: " öneki ister
    sorgu_metni = "query: " + arama_metni
    sorgu_vektoru = embedding_model.encode(sorgu_metni).tolist()

    sonuclar = collection.query(
        query_embeddings=[sorgu_vektoru],
        n_results=N_RESULTS
    )

    documents = sonuclar["documents"][0]
    metadatas = sonuclar["metadatas"][0]
    ids = sonuclar["ids"][0]

    # Maddeleri prompt için birleştir + ekrana referansları yazdır
    maddeler_metni = ""
    referans_listesi = []
    for i, (doc, meta, doc_id) in enumerate(zip(documents, metadatas, ids), start=1):
        madde_no = meta.get("madde_no") or meta.get("madde") or doc_id
        referans_listesi.append(str(madde_no))
        maddeler_metni += f"--- KANUN MADDESİ {i} (TCK Madde {madde_no}) ---\n{doc}\n\n"

    print(f">> [Aşama 2] Bulunan maddeler: TCK Madde {', '.join(referans_listesi)}")

    # ============================================================
    # AŞAMA 3: NİHAİ MÜTALAA (Asıl LLM çağrısı)
    # Orijinal soru + bulunan kanun maddeleri ile hukuki analiz yaptır
    # ============================================================
    print(">> [Aşama 3] Hukuki mütalaa hazırlanıyor...")
    kullanici_mesaji = (
        f"{maddeler_metni}"
        f"SORU:\n{kullanici_sorusu}"   # Orijinal soruyu gönderiyoruz, kavramları değil
    )

    asistan_cevabi = llm_cevap_al(
        system_prompt=SISTEM_PROMPTU,
        user_message=kullanici_mesaji,
        max_tokens=3000,
        temperature=0.2
    )

    if not asistan_cevabi:
        asistan_cevabi = "(Model boş cevap döndü — context çok uzun olabilir veya thinking budget yetersiz)"

    print(f"\nCevap: {asistan_cevabi}")
    print("-" * 55)
