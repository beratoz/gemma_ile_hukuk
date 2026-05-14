# =============================================================
# TCK RAG CHATBOT - FastAPI REST API
# 3 Aşamalı Mimari:
#   Aşama 1: Hukuki Tercüman (LLM ile kavram çıkarma)
#   Aşama 2: Vektör Retrieval (kavramlarla ChromaDB araması)
#   Aşama 3: Nihai Mütalaa (LLM ile hukuki analiz)
# =============================================================

import asyncio
import os
from contextlib import asynccontextmanager

import chromadb
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

# --- 1. KONFİGÜRASYON (.env'den okunur) ---
load_dotenv()

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")
N_RESULTS = int(os.getenv("N_RESULTS", "5"))
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL")
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY")
LM_MODEL_NAME = os.getenv("LM_MODEL_NAME")

_required = {
    "CHROMA_DB_PATH": CHROMA_DB_PATH,
    "COLLECTION_NAME": COLLECTION_NAME,
    "EMBEDDING_MODEL_NAME": EMBEDDING_MODEL_NAME,
    "LM_STUDIO_BASE_URL": LM_STUDIO_BASE_URL,
    "LM_STUDIO_API_KEY": LM_STUDIO_API_KEY,
    "LM_MODEL_NAME": LM_MODEL_NAME,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    raise RuntimeError(f"Eksik .env değişkenleri: {', '.join(_missing)}")

# --- 2. PROMPTLAR ---
# CLI sürümünden harfiyen kopyalandı (commit ba3545e: retrieval doğruluğunu artıran promptlar).

TERCUMAN_PROMPTU = """Sen bir hukuki kavram çıkarıcısın. Sana verilen halk ağzıyla anlatılmış olayı analiz et ve TCK'da karşılık gelen en fazla 5 hukuki anahtar kelimeyi/kavramı aralarına virgül koyarak yaz.

KURALLAR:
- Cümle kurma, açıklama yapma, yorum yapma.
- Sadece virgülle ayrılmış kelime/kavramları yaz.
- Örnek format: meşru savunma, sınırın aşılması, kasten öldürme, korku ve telaş, taksir
- Türkçe ve TCK terminolojisi kullan."""

SISTEM_PROMPTU = """Sen uzman bir ceza avukatısın. Görevin, sana sunulan TCK maddeleri arasından olayla en ilgili olanı/olanları seçip hukuki bir sonuç üretmektir.

KURALLAR:
1. SIFIR UYDURMA: Asla kendi hafızandan kanun, madde veya bilgi ekleme. SADECE sana verilen KANUN MADDELERİ'ni kullan. İlgisiz olanları ele.
2. HUKUKİ NİTELENDİRME (Kritik): Günlük dilde anlatılan fiilleri (örneğin: küfür, tokat, dikkatsizlik), maddelerdeki soyut hukuki kavramlarla (örneğin: haksız fiil, kasten yaralama, taksir) mantıksal olarak eşleştir. Seçtiğin maddeyi bu olayla bağdaştırarak açıkla.
3. ATIF VE KESİNLİK: Cevabına daima "TCK Madde [X]'e göre" diyerek başla. Ceza sürelerini ve miktarlarını (yıl/ay/gün) AYNEN aktar, asla yuvarlama.
4. GÜVENLİK: Verilen maddeler olayla kurduğun mantık çerçevesinde uyuşmuyorsa SADECE "Verilen maddeler bu soruyu cevaplamak için yeterli değildir." yaz. Başka hiçbir açıklama yapma.
5. KATI FORMAT: Kelime sınırı yoktur ancak laf kalabalığı yapma. Cevabını net, yapılandırılmış ve özet bir hukuki mütalaa şeklinde sun. "Merhaba", "Yardımcı olabileceğim başka bir şey var mı?" gibi yapay zeka süsleri KESİNLİKLE YASAK. Sadece hukuki analizi, nedensellik bağını ve nihai sonucu yaz."""


# --- 3. PYDANTIC ŞEMALARI ---
class AnalyzeRequest(BaseModel):
    soru: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Kullanıcının halk ağzıyla yazdığı hukuki olay/soru.",
        examples=["Hırsızlık yapan birinin cezası nedir?"],
    )


class AnalyzeResponse(BaseModel):
    soru: str = Field(..., description="Orijinal kullanıcı sorusu (echo).")
    cikarilan_kavramlar: list[str] = Field(
        ..., description="Aşama 1: LLM tarafından çıkarılan hukuki kavramların listesi."
    )
    bulunan_madde_numaralari: list[str] = Field(
        ..., description="Aşama 2: ChromaDB'den retrieve edilen TCK madde numaraları."
    )
    mutalaa: str = Field(..., description="Aşama 3: LLM'in nihai hukuki mütalaası.")


class HealthResponse(BaseModel):
    status: str
    collection_doc_count: int | None
    lm_studio_reachable: bool


# --- 4. RAG YARDIMCI FONKSİYONLARI (CLI sürümünden taşındı) ---
def _llm_chat(
    llm_client: OpenAI,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> str:
    """LM Studio'ya istek atar, cevap metnini döndürür. Boş cevap durumlarında güvenli."""
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


def _extract_concepts(question: str, llm_client: OpenAI) -> list[str]:
    """Aşama 1: Halk ağzındaki olayı saf hukuki kavramlara dönüştür."""
    raw = _llm_chat(
        llm_client=llm_client,
        system_prompt=TERCUMAN_PROMPTU,
        user_message=question,
        max_tokens=2000,
        temperature=0.1,
    )
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


def _retrieve_articles(
    search_text: str,
    embedding_model: SentenceTransformer,
    collection: "chromadb.Collection",
    n_results: int,
) -> tuple[list[str], str]:
    """Aşama 2: Kavramları E5 ile vektöre çevir, ChromaDB'den en alakalı maddeleri al.

    Returns:
        (madde_no_listesi, llm'e gönderilecek formatted maddeler_metni)
    """
    # E5 modeli sorgular için MUTLAKA "query: " öneki ister
    sorgu_metni = "query: " + search_text
    sorgu_vektoru = embedding_model.encode(sorgu_metni).tolist()

    sonuclar = collection.query(
        query_embeddings=[sorgu_vektoru],
        n_results=n_results,
    )

    documents = sonuclar["documents"][0]
    metadatas = sonuclar["metadatas"][0]
    ids = sonuclar["ids"][0]

    madde_no_listesi: list[str] = []
    maddeler_metni = ""
    for i, (doc, meta, doc_id) in enumerate(zip(documents, metadatas, ids), start=1):
        madde_no = meta.get("madde_no") or meta.get("madde") or doc_id
        madde_no_listesi.append(str(madde_no))
        maddeler_metni += f"--- KANUN MADDESİ {i} (TCK Madde {madde_no}) ---\n{doc}\n\n"

    return madde_no_listesi, maddeler_metni


def _generate_opinion(question: str, articles_text: str, llm_client: OpenAI) -> str:
    """Aşama 3: Orijinal soru + bulunan maddeler ile hukuki mütalaa üret."""
    kullanici_mesaji = f"{articles_text}SORU:\n{question}"
    cevap = _llm_chat(
        llm_client=llm_client,
        system_prompt=SISTEM_PROMPTU,
        user_message=kullanici_mesaji,
        max_tokens=3000,
        temperature=0.2,
    )
    if not cevap:
        return "(Model boş cevap döndü — context çok uzun olabilir veya thinking budget yetersiz)"
    return cevap


# --- 5. LIFESPAN: modelleri sunucu açılırken bir kez yükle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Embedding modeli yükleniyor... (ilk seferde indirilebilir)")
    app.state.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    print("Embedding modeli hazır.")

    print(f"ChromaDB bağlantısı kuruluyor: {CHROMA_DB_PATH}")
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    app.state.collection = chroma_client.get_collection(name=COLLECTION_NAME)
    print(f"'{COLLECTION_NAME}' koleksiyonuna bağlanıldı.")

    print(f"LM Studio istemcisi hazırlanıyor: {LM_STUDIO_BASE_URL}")
    app.state.llm_client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key=LM_STUDIO_API_KEY)
    print("Tüm bileşenler hazır. API çalışmaya hazır.\n")

    yield

    print("API kapatılıyor...")


# --- 6. FASTAPI UYGULAMASI ---
app = FastAPI(
    title="TCK Hukuk Asistanı API",
    description="3 aşamalı RAG (Tercüman → Vektör Arama → Mütalaa) ile TCK üzerinde çalışan hukuki analiz API'si.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 7. ENDPOINT'LER ---
@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, http_request: Request) -> AnalyzeResponse:
    """Hukuki olayı 3 aşamalı RAG pipeline'ından geçirip mütalaa üretir."""
    state = http_request.app.state

    try:
        # Aşama 1: Hukuki Tercüman
        kavramlar = await asyncio.to_thread(_extract_concepts, request.soru, state.llm_client)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Aşama 1 (Tercüman) hatası — LM Studio erişilemiyor olabilir: {e}",
        )

    # Tercüman boş döndüyse fallback: orijinal soru ile retrieval yap
    arama_metni = ", ".join(kavramlar) if kavramlar else request.soru

    try:
        # Aşama 2: Vektör Arama
        madde_nolari, maddeler_metni = await asyncio.to_thread(
            _retrieve_articles,
            arama_metni,
            state.embedding_model,
            state.collection,
            N_RESULTS,
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Aşama 2 (Vektör Arama) hatası — ChromaDB erişilemiyor olabilir: {e}",
        )

    try:
        # Aşama 3: Nihai Mütalaa
        mutalaa = await asyncio.to_thread(
            _generate_opinion, request.soru, maddeler_metni, state.llm_client
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Aşama 3 (Mütalaa) hatası — LM Studio erişilemiyor olabilir: {e}",
        )

    return AnalyzeResponse(
        soru=request.soru,
        cikarilan_kavramlar=kavramlar,
        bulunan_madde_numaralari=madde_nolari,
        mutalaa=mutalaa,
    )


@app.get("/health", response_model=HealthResponse)
async def health(http_request: Request) -> HealthResponse:
    """ChromaDB ve LM Studio canlılığını test eder."""
    state = http_request.app.state

    # ChromaDB
    try:
        doc_count = await asyncio.to_thread(state.collection.count)
    except Exception:
        doc_count = None

    # LM Studio
    try:
        await asyncio.to_thread(state.llm_client.models.list)
        lm_ok = True
    except Exception:
        lm_ok = False

    overall = "ok" if (doc_count is not None and lm_ok) else "degraded"

    return HealthResponse(
        status=overall,
        collection_doc_count=doc_count,
        lm_studio_reachable=lm_ok,
    )
