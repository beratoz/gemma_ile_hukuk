# =============================================================
# TCK İNDEKSLEME SCRIPTİ - JSON'dan ChromaDB'ye
# Türk Ceza Kanunu maddelerini multilingual-e5-base ile vektörleştirir
# Bu dosyayı SADECE BİR KEZ çalıştırırsın, sonrası chatbot'tur
# =============================================================

import json
import chromadb
from sentence_transformers import SentenceTransformer

# --- 1. AYARLAR ---
JSON_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/ceza_kanunu_duzeltilmis/tck_maddeler_temiz.json"  # Kaynak JSON
CHROMA_DB_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/tck_chromadb"        # Hedef DB klasörü
COLLECTION_NAME = "tck_koleksiyonu_e5"                                     # Koleksiyon adı
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"                     # E5 çok dilli model
BATCH_SIZE = 32                                                            # Toplu encode boyutu

# --- 2. JSON DOSYASINI OKU ---
print("JSON dosyası okunuyor...")
with open(JSON_PATH, "r", encoding="utf-8") as f:
    maddeler = json.load(f)
print(f"Toplam {len(maddeler)} madde yüklendi.\n")

# --- 3. EMBEDDING MODELİNİ YÜKLE ---
print("Embedding modeli yükleniyor (intfloat/multilingual-e5-base)...")
model = SentenceTransformer(EMBEDDING_MODEL_NAME)
print("Model hazır.\n")

# --- 4. CHROMADB'YE BAĞLAN ---
client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

# Eski koleksiyon varsa sil (temiz başlangıç için)
# Bu sayede script'i tekrar çalıştırırsan duplicate olmaz
try:
    client.delete_collection(name=COLLECTION_NAME)
    print(f"Eski '{COLLECTION_NAME}' koleksiyonu silindi.")
except Exception:
    print(f"Yeni koleksiyon oluşturuluyor (eskisi yoktu).")

# Yeni koleksiyon oluştur
# cosine benzerliği hukuki metinler için en uygun seçenektir
collection = client.create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)
print(f"'{COLLECTION_NAME}' koleksiyonu hazır.\n")

# --- 5. METİNLERİ HAZIRLA ---
# E5 modeli, indekslenecek dokümanların başında "passage: " öneki bekler
# (Sorgu vektörü için "query: " kullanırız — chatbot'ta öyle yapıyoruz)
# Bu prefix uyumu, retrieval doğruluğunu ciddi artırır
ids = []
documents_for_storage = []   # ChromaDB'ye saklanacak orijinal metin (prefix'siz)
texts_to_encode = []         # Modele verilecek metin (prefix'li)
metadatas = []

for madde in maddeler:
    madde_no = madde["madde_no"]
    icerik = madde["icerik"]

    ids.append(f"madde_{madde_no}")                       # Benzersiz ID
    documents_for_storage.append(icerik)                  # Saklanacak: orijinal metin
    texts_to_encode.append("passage: " + icerik)          # Encode edilecek: prefix'li
    metadatas.append({
        "madde_no": madde_no,
        "kelime_say": madde["kelime_say"]
    })

# --- 6. TOPLU EMBEDDİNG (BATCH) ---
# Tek tek encode etmek yerine batch ile hız kazanırız (~10x daha hızlı)
print(f"{len(texts_to_encode)} madde vektörleştiriliyor...")
embeddings = model.encode(
    texts_to_encode,
    batch_size=BATCH_SIZE,
    show_progress_bar=True,
    convert_to_numpy=True,
    normalize_embeddings=True   # E5 için normalize edilmiş vektör tavsiye edilir
).tolist()
print("Vektörleştirme tamamlandı.\n")

# --- 7. CHROMADB'YE EKLE ---
# ChromaDB'nin add() fonksiyonu büyük listeleri sorunsuz alır
print("Veriler ChromaDB'ye yazılıyor...")
collection.add(
    ids=ids,
    embeddings=embeddings,
    documents=documents_for_storage,   # Orijinal metin saklanır (prefix'siz)
    metadatas=metadatas
)
print(f"{collection.count()} madde başarıyla kaydedildi.\n")

# --- 8. DOĞRULAMA TESTİ ---
# Rastgele bir soru ile retrieval'ın doğru çalıştığını kontrol edelim
print("=" * 55)
print("DOĞRULAMA TESTİ")
print("=" * 55)
test_sorusu = "Hırsızlık suçunun cezası nedir?"
test_vektoru = model.encode(
    "query: " + test_sorusu,
    normalize_embeddings=True
).tolist()

sonuc = collection.query(query_embeddings=[test_vektoru], n_results=1)
print(f"\nTest sorusu: {test_sorusu}")
print(f"Bulunan madde no: {sonuc['metadatas'][0][0]['madde_no']}")
print(f"Madde önizleme: {sonuc['documents'][0][0][:200]}...")
print("\n✓ İndeksleme tamamlandı. Artık chatbot'u çalıştırabilirsin.")
