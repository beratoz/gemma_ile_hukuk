# =============================================================
# TCK İNDEKSLEME SCRIPTİ - JSON'dan ChromaDB'ye
# Türk Ceza Kanunu maddelerini multilingual-e5-base ile vektörleştirir
# Bu dosyayı SADECE BİR KEZ çalıştırırsın, sonrası chatbot'tur
# =============================================================

import json
import chromadb
from sentence_transformers import SentenceTransformer

# --- 1. AYARLAR ---
JSON_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/ceza_kanunu_duzeltilmis/tck_maddeler_temiz.json"      # Kaynak JSON
BASLIKLAR_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/ceza_kanunu_duzeltilmis/tck_basliklar.json"      # LLM-üretilen marjinal başlıklar
OVERRIDE_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/ceza_kanunu_duzeltilmis/tck_basliklar_override.json"  # Manuel düzeltme (öncelikli)
CHROMA_DB_PATH = "C:/Users/berat/Desktop/Gemma_Hukuk/tck_chromadb"        # Hedef DB klasörü
COLLECTION_NAME = "tck_koleksiyonu_e5"                                     # Koleksiyon adı
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-base"                     # E5 çok dilli model
BATCH_SIZE = 32                                                            # Toplu encode boyutu

# --- 2. JSON DOSYALARINI OKU ---
print("JSON dosyası okunuyor...")
with open(JSON_PATH, "r", encoding="utf-8") as f:
    maddeler = json.load(f)
print(f"Toplam {len(maddeler)} madde yüklendi.")

# Marjinal başlıklar (RAG retrieval kalitesini artırır — S1 iyileştirmesi).
# Sıralama: önce LLM-üretilen başlıklar, ÜZERİNE manuel override.
basliklar: dict[str, str] = {}

# Önce LLM-üretilen başlıkları yükle (fallback)
try:
    with open(BASLIKLAR_PATH, "r", encoding="utf-8") as f:
        basliklar = json.load(f)
    bos_sayi = sum(1 for v in basliklar.values() if not v)
    print(f"LLM-üretilen başlıklar yüklendi: {len(basliklar) - bos_sayi}/{len(basliklar)} dolu.")
except FileNotFoundError:
    print(f"UYARI: {BASLIKLAR_PATH} bulunamadı, LLM-üretilen başlıklar atlandı.")

# Sonra manuel override'ı uygula (öncelikli, doğrulanmış başlıklar)
try:
    with open(OVERRIDE_PATH, "r", encoding="utf-8") as f:
        raw_overrides = json.load(f)
    # Yorum amaçlı `_` ile başlayan anahtarları atla
    overrides = {k: v for k, v in raw_overrides.items() if not k.startswith("_") and v}
    onceki = sum(1 for k in overrides if basliklar.get(k))
    basliklar.update(overrides)
    print(f"Manuel override uygulandı: {len(overrides)} başlık ({onceki} mevcut başlık üzerine yazıldı).\n")
except FileNotFoundError:
    print(f"UYARI: {OVERRIDE_PATH} bulunamadı, sadece LLM-üretilenler kullanılıyor.\n")

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
    baslik = basliklar.get(str(madde_no), "").strip()

    # Zenginleştirilmiş metin: TCK Madde X - <başlık>\n<içerik>
    # Başlık yoksa sadece içerik ile devam (boş başlık embedding'i bozmasın diye)
    if baslik:
        zenginlestirilmis = f"TCK Madde {madde_no} - {baslik}\n{icerik}"
    else:
        zenginlestirilmis = icerik

    ids.append(f"madde_{madde_no}")                                # Benzersiz ID
    documents_for_storage.append(zenginlestirilmis)                # Saklanacak: zenginleştirilmiş metin
    texts_to_encode.append("passage: " + zenginlestirilmis)        # Encode edilecek: prefix'li + başlıklı
    metadatas.append({
        "madde_no": madde_no,
        "baslik": baslik or "",
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
# Birkaç farklı soru ile retrieval'ın doğru çalıştığını kontrol edelim
print("=" * 55)
print("DOĞRULAMA TESTLERİ")
print("=" * 55)
test_sorulari = [
    ("Hırsızlık suçunun cezası nedir?", 141),
    ("Birine hakaret ettim, cezası ne olur?", 125),
    ("Kasten birini yaraladım, ne ceza alırım?", 86),
    ("Birini öldürmek istedim ama başaramadım", 81),
]
for soru, beklenen_no in test_sorulari:
    vek = model.encode("query: " + soru, normalize_embeddings=True).tolist()
    sonuc = collection.query(query_embeddings=[vek], n_results=3)
    bulunanlar = [m["madde_no"] for m in sonuc["metadatas"][0]]
    isaret = "✓" if beklenen_no in bulunanlar else "✗"
    print(f"\n{isaret} Soru: {soru}")
    print(f"  Beklenen: TCK {beklenen_no} | Bulunan top-3: {bulunanlar}")

print("\n✓ İndeksleme tamamlandı. Artık chatbot'u çalıştırabilirsin.")
