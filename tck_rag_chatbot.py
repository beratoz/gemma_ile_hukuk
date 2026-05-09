# =============================================================
# TCK RAG CHATBOT - Saf Python (LangChain'siz)
# Yerel ChromaDB + LM Studio + multilingual-e5-base embedding
# Top-5 retrieval ile çoklu madde değerlendirmesi
# =============================================================

import chromadb
from sentence_transformers import SentenceTransformer
from openai import OpenAI

# --- 1. AYARLAR (kullanıcı değiştirebilir) ---
CHROMA_DB_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/tck_chromadb"   # Vektör DB yerel yolu
COLLECTION_NAME = "tck_koleksiyonu_e5"                                   # Koleksiyon adı
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"                # Çok dilli embedding modeli
N_RESULTS = 3                                                         # Kaç madde çekilsin

# LM Studio (OpenAI uyumlu) yerel sunucu bilgileri
# Not: openai kütüphanesi base_url'ye /chat/completions eklediği için "/v1" gerekir
LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
LM_STUDIO_API_KEY = "lm-studio"

# --- 2. EMBEDDING MODELİ YÜKLEME ---
# Soruyu vektöre çevirmek için modeli RAM'e alıyoruz
print("Embedding modeli yükleniyor... (ilk seferde indirilebilir)")
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
print("Embedding modeli hazır.\n")

# --- 3. CHROMADB BAĞLANTISI ---
# Diskte kalıcı (PersistentClient) olarak tutulan veritabanına bağlan
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
# Daha önce kanun maddeleri ile doldurulmuş koleksiyonu çek
collection = chroma_client.get_collection(name=COLLECTION_NAME)
print(f"'{COLLECTION_NAME}' koleksiyonuna bağlanıldı.\n")

# --- 4. LM STUDIO (LLM) İSTEMCİSİ ---
# OpenAI kütüphanesini yerel LM Studio sunucusuna yönlendiriyoruz
llm_client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key=LM_STUDIO_API_KEY)

# --- 5. SİSTEM PROMPTU (KURALLAR) ---
# Modelin halüsinasyon yapmasını engelleyen, kısa ve vurucu cevap için katı kurallar
# Artık 5 madde içinden seçim yapılacağı için prompt çoklu maddeye uyarlandı
SISTEM_PROMPTU = """Sen uzman bir ceza avukatısın. Görevin, sana sunulan 5 TCK maddesi arasından olayla en ilgili olanı/olanları seçip hukuki bir sonuç üretmektir.

KURALLAR:
1. SIFIR UYDURMA: Asla kendi hafızandan kanun, madde veya bilgi ekleme. SADECE sana verilen KANUN MADDELERİ'ni kullan. İlgisiz olanları ele.
2. HUKUKİ NİTELENDİRME (Kritik): Günlük dilde anlatılan fiilleri (örneğin: küfür, tokat, dikkatsizlik), maddelerdeki soyut hukuki kavramlarla (örneğin: haksız fiil, kasten yaralama, taksir) mantıksal olarak eşleştir. Seçtiğin maddeyi bu olayla bağdaştırarak açıkla.
3. ATIF VE KESİNLİK: Cevabına daima "TCK Madde [X]'e göre" diyerek başla. Ceza sürelerini ve miktarlarını (yıl/ay/gün) AYNEN aktar, asla yuvarlama.
4. GÜVENLİK: Verilen maddeler olayla kurduğun mantık çerçevesinde uyuşmuyorsa SADECE "Verilen maddeler bu soruyu cevaplamak için yeterli değildir." yaz. Başka hiçbir açıklama yapma.
5. KATI FORMAT: Kelime sınırı yoktur ancak laf kalabalığı yapma. Cevabını net, yapılandırılmış ve özzet bir hukuki mütalaa şeklinde sun. "Merhaba", "Yardımcı olabileceğim başka bir şey var mı?" gibi yapay zeka süsleri KESİNLİKLE YASAK. Sadece hukuki analizi, nedensellik bağını ve nihai sonucu yaz."""
# --- 6. SOHBET DÖNGÜSÜ ---
print("=" * 55)
print(" TCK Hukuk Asistanı - Çıkmak için 'q' veya 'çıkış' ")
print("=" * 55)

while True:
    # Kullanıcıdan soruyu al ve baş/son boşlukları temizle
    kullanici_sorusu = input("\nSoru: ").strip()

    # Çıkış komutları kontrolü
    if kullanici_sorusu.lower() in ("q", "çıkış", "cikis", "exit", "quit"):
        print("Görüşmek üzere!")
        break

    # Boş giriş geldiyse döngüyü atla
    if not kullanici_sorusu:
        continue

    # --- RETRIEVAL: Soruyu vektöre çevir ---
    # E5 modeli sorgular için MUTLAKA "query: " öneki ister
    sorgu_metni = "query: " + kullanici_sorusu
    sorgu_vektoru = embedding_model.encode(sorgu_metni).tolist()

    # En benzer N_RESULTS adet maddeyi ChromaDB'den çek
    sonuclar = collection.query(
        query_embeddings=[sorgu_vektoru],
        n_results=N_RESULTS
    )

    # --- Bulunan maddeleri tek tek işle ---
    documents = sonuclar["documents"][0]
    metadatas = sonuclar["metadatas"][0]
    ids = sonuclar["ids"][0]

    # Maddeleri prompt için birleştir + ekrana referansları yazdır
    maddeler_metni = ""
    referans_listesi = []
    for i, (doc, meta, doc_id) in enumerate(zip(documents, metadatas, ids), start=1):
        # Madde numarası önce metadata'dan, yoksa doküman ID'sinden alınır
        madde_no = meta.get("madde_no") or meta.get("madde") or doc_id
        referans_listesi.append(str(madde_no))
        maddeler_metni += f"--- KANUN MADDESİ {i} (TCK Madde {madde_no}) ---\n{doc}\n\n"

    print(f">> Referans alınan maddeler: TCK Madde {', '.join(referans_listesi)}")

    # --- GENERATION: Mega-Prompt'u dinamik kur ---
    # 5 madde + soru tek mesaj olarak modele gönderilir
    kullanici_mesaji = (
        f"{maddeler_metni}"
        f"SORU:\n{kullanici_sorusu}"
    )

    # LM Studio'ya OpenAI uyumlu chat completion isteği gönder
    cevap = llm_client.chat.completions.create(
        model="google/gemma-4-e4b",  # LM Studio yüklü modeli otomatik kullanır
        messages=[
            {"role": "system", "content": SISTEM_PROMPTU},
            {"role": "user", "content": kullanici_mesaji},
        ],
        temperature=0.2,  # Hukuk için düşük sıcaklık = daha tutarlı/deterministik cevap
    )

    # Modelin ürettiği cevabı ekrana yazdır
 # Debug: LM Studio'dan ne geldi?
# Modelin ürettiği cevabı ekrana yazdır
 # Debug: LM Studio'dan ne geldi?
# Debug: LM Studio'dan ne geldi?
    #print("DEBUG ham yanıt:", cevap)

    # Güvenli erişim
    if cevap.choices and cevap.choices[0].message.content:
        asistan_cevabi = cevap.choices[0].message.content.strip()
    else:
        asistan_cevabi = "(Model boş cevap döndü — context çok uzun olabilir)"

    print(f"\nCevap: {asistan_cevabi}")
    print("-" * 55)