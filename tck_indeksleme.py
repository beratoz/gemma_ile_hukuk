# =============================================================
# MULTI-CORPUS INDEKSLEME — Phase 2.0+
# Kaynaklar (universal şema):
#   - TCK (tck_rag.json)
#   - TCK Gerekçeleri (tck_gerekceleri_rag.json)
#   - CMK — Ceza Muhakemesi Kanunu (cmk_rag.json)
#   - CGTIK — Ceza ve Güvenlik Tedbirlerinin İnfazı Hakkında Tüzük (cgtik_rag.json)
#   - TCK Genel Hükümler Doktrini (genelhukumler_rag.json) — chunking uygulanır
#
# Tek ChromaDB koleksiyonuna yazılır, metadata.kaynak_kodu ile ayırt edilir.
# .env'den DATASETS_PATHS (virgülle ayrılmış) okunur.
# =============================================================

import json
import os

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# --- 1. AYARLAR ---
load_dotenv()

DATASETS_PATHS_RAW = os.getenv("DATASETS_PATHS", "")
DATASETS_PATHS = [p.strip() for p in DATASETS_PATHS_RAW.split(",") if p.strip()]
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")
BATCH_SIZE = 32

# Chunking — yalnızca uzun doktrin metinleri için.
# E5 modeli ~512 token max → ~2000 karakter pratik sınır.
# 1800 karakter (~450 token) parça + 200 karakter overlap → bağlam koruma
CHUNK_THRESHOLD_CHARS = 2200   # Bu eşiğin üstündekiler parçalanır
CHUNK_SIZE_CHARS = 1800
CHUNK_OVERLAP_CHARS = 200

_required = {
    "DATASETS_PATHS": DATASETS_PATHS,
    "CHROMA_DB_PATH": CHROMA_DB_PATH,
    "COLLECTION_NAME": COLLECTION_NAME,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    raise RuntimeError(f"Eksik .env değişkenleri: {', '.join(_missing)}")


# --- 2. CHUNKING YARDIMCISI ---
def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """Karakter bazlı sliding-window chunking. Cümle sınırına yakınlaştırmaya çalışır."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        # Cümle sınırına yakınlaştır (son noktaya yakın kes)
        if end < n:
            last_period = text.rfind(".", start, end)
            last_newline = text.rfind("\n", start, end)
            cut = max(last_period, last_newline)
            if cut > start + max_chars // 2:  # Yarıdan azına gitme
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= n:
            break
        start = end - overlap
    return [c for c in chunks if c]


# --- 3. KAYNAKLARI OKU ---
print("=" * 70)
print(f"INDEKSLEME — {len(DATASETS_PATHS)} kaynak yüklenecek")
print("=" * 70)

all_items: list[dict] = []
for path in DATASETS_PATHS:
    if not os.path.isfile(path):
        print(f"  UYARI: {path} bulunamadı, atlandı.")
        continue
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    print(f"  {os.path.basename(path)}: {len(items)} kayıt")
    all_items.extend(items)

print(f"\nToplam {len(all_items)} ham kayıt yüklendi.\n")

# --- 4. EMBEDDING MODELİNİ YÜKLE ---
print(f"Embedding modeli yükleniyor: {EMBEDDING_MODEL_NAME}")
model = SentenceTransformer(EMBEDDING_MODEL_NAME)
print("Model hazır.\n")

# --- 5. CHROMADB'YE BAĞLAN, TEMİZ KOLEKSİYON ---
client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
try:
    client.delete_collection(name=COLLECTION_NAME)
    print(f"Eski '{COLLECTION_NAME}' koleksiyonu silindi.")
except Exception:
    print(f"Yeni koleksiyon oluşturuluyor (eskisi yoktu).")

collection = client.create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
)
print(f"'{COLLECTION_NAME}' koleksiyonu hazır.\n")

# --- 6. METİNLERİ HAZIRLA + CHUNKING ---
ids: list[str] = []
documents_for_storage: list[str] = []
texts_to_encode: list[str] = []
metadatas: list[dict] = []

chunked_count = 0
skipped_empty = 0
mulga_count = 0

for item in all_items:
    base_id = item.get("id") or f"{item.get('kaynak_kodu','UNK')}-m{item.get('birim_no','?')}"
    embedding_text = item.get("embedding_text") or item.get("metin") or ""
    if not embedding_text.strip():
        skipped_empty += 1
        continue

    is_mulga = bool(item.get("mulga", False))
    if is_mulga:
        mulga_count += 1

    # Ortak metadata
    # Şema fallback'leri:
    #   - tck_rag.json eski şema (madde_no, kanun) kullanır
    #   - Yeni 4 dosya universal şema (birim_no, kaynak_kodu) kullanır
    #   - id prefix'inden kaynak çıkarımı (tck-m125 → "TCK", cmk-m91 → "CMK")
    item_id = str(item.get("id") or "")
    id_prefix = item_id.split("-")[0].upper() if "-" in item_id else ""

    kaynak_kodu = (
        item.get("kaynak_kodu")
        or (id_prefix if id_prefix in ("TCK", "CMK", "CGTIK", "TCK_GEREKCE", "TCK_DOKTRIN") else None)
        or ("TCK" if item.get("kanun_no") == "5237" else None)
        or "TCK"  # son çare default
    )
    base_meta = {
        "kaynak_kodu": str(kaynak_kodu),
        "kaynak_tipi": str(item.get("kaynak_tipi") or "kanun"),
        "kaynak_adi": str(item.get("kaynak_adi") or item.get("kanun") or ""),
        "kaynak_no": str(item.get("kaynak_no") or item.get("kanun_no") or ""),
        # birim_no fallback: yeni şema → birim_no; eski şema → madde_no
        "birim_no": str(item.get("birim_no") or item.get("madde_no") or ""),
        "baslik": str(item.get("baslik") or "")[:200],
        "konu": str(item.get("konu") or ""),
        "kitap": str(item.get("kitap") or ""),
        "kisim": str(item.get("kisim") or ""),
        "bolum": str(item.get("bolum") or ""),
        "hiyerarsi": str(item.get("hiyerarsi") or "")[:300],
        "mulga": is_mulga,
        "karakter_sayisi": int(item.get("karakter_sayisi") or len(embedding_text)),
    }

    # Chunking gerekli mi? (yalnızca uzun metinler)
    parts = chunk_text(embedding_text, CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS) \
        if len(embedding_text) > CHUNK_THRESHOLD_CHARS \
        else [embedding_text]

    if len(parts) > 1:
        chunked_count += 1

    for chunk_idx, chunk in enumerate(parts):
        chunk_id = base_id if len(parts) == 1 else f"{base_id}-c{chunk_idx + 1}"
        ids.append(chunk_id)
        documents_for_storage.append(chunk)
        texts_to_encode.append("passage: " + chunk)
        # Chunk-level metadata
        chunk_meta = dict(base_meta)
        chunk_meta["chunk_no"] = chunk_idx + 1
        chunk_meta["chunk_toplam"] = len(parts)
        metadatas.append(chunk_meta)

print(f"Boş atlanan kayıt: {skipped_empty}")
print(f"Mülga kayıt (metadata'da işaretli): {mulga_count}")
print(f"Chunking uygulanan kayıt: {chunked_count}")
print(f"Indekslenecek toplam doküman: {len(ids)}\n")

# --- 7. TOPLU EMBEDDİNG (BATCH) ---
print(f"{len(texts_to_encode)} doküman vektörleştiriliyor...")
embeddings = model.encode(
    texts_to_encode,
    batch_size=BATCH_SIZE,
    show_progress_bar=True,
    convert_to_numpy=True,
    normalize_embeddings=True,
).tolist()
print("Vektörleştirme tamamlandı.\n")

# --- 8. CHROMADB'YE EKLE (parça parça, hafıza için) ---
print("Veriler ChromaDB'ye yazılıyor...")
ADD_BATCH = 1000
for start in range(0, len(ids), ADD_BATCH):
    end = min(start + ADD_BATCH, len(ids))
    collection.add(
        ids=ids[start:end],
        embeddings=embeddings[start:end],
        documents=documents_for_storage[start:end],
        metadatas=metadatas[start:end],
    )
print(f"{collection.count()} doküman başarıyla kaydedildi.\n")

# --- 9. DOĞRULAMA TESTLERİ ---
print("=" * 70)
print("DOĞRULAMA TESTLERİ (mülga maddeler hariç)")
print("=" * 70)
test_sorulari = [
    ("Hırsızlık suçunun cezası nedir?", "TCK", 141),
    ("Birine hakaret ettim, cezası ne olur?", "TCK", 125),
    ("Şantaj nedir?", "TCK", 107),
    ("Tutuklama nedenleri nelerdir?", "CMK", 100),
    ("Yakalama nasıl yapılır?", "CMK", 90),
    ("Koşullu salıverme şartları?", "CGTIK", None),  # ne bulduğunu görelim
]
for soru, beklenen_kaynak, beklenen_no in test_sorulari:
    vek = model.encode("query: " + soru, normalize_embeddings=True).tolist()
    sonuc = collection.query(
        query_embeddings=[vek],
        n_results=5,
        where={"mulga": False},
    )
    bulunanlar = [
        (m.get("kaynak_kodu"), m.get("birim_no"), m.get("baslik", "")[:40])
        for m in sonuc["metadatas"][0]
    ]
    if beklenen_no is None:
        isaret = "?"
    else:
        beklenen_str = str(beklenen_no)
        match = any(k == beklenen_kaynak and b == beklenen_str for k, b, _ in bulunanlar)
        isaret = "✓" if match else "✗"
    print(f"\n{isaret} Soru: {soru}")
    print(f"   Beklenen: {beklenen_kaynak} {beklenen_no}")
    for k, b, ba in bulunanlar:
        print(f"   {k} m.{b} — {ba}")

print("\n✓ Multi-corpus indeksleme tamamlandı. FastAPI'yi başlatabilirsin.")
