# =============================================================
# TCK RAG CHATBOT - FastAPI REST API
# Pipeline:
#   Aşama 1:   Hukuki Tercüman (LLM + ontoloji ile kavram çıkarma)
#   Aşama 2:   Hibrit arama (retrieval.py: E5 + BM25, RRF)
#   Aşama 2.5: Eksik suç kontrolü (LLM)
#   Aşama 3:   Nihai Mütalaa (LLM, SSE ile akış)
# Promptlar prompts.py içindedir.
# =============================================================

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager

import chromadb
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

from prompts import MISSING_CHECK_PROMPT, SISTEM_PROMPTU, TERCUMAN_PROMPTU
from penalties import build_penalty_index, penalty_table, range_warning, unsupported_ranges
from retrieval import BM25Index, _explicit_article_refs, _retrieve_articles

# --- 1. KONFİGÜRASYON (.env'den okunur) ---
load_dotenv()

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")
N_RESULTS = int(os.getenv("N_RESULTS", "5"))
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL")
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY")
LM_MODEL_NAME = os.getenv("LM_MODEL_NAME")
ONTOLOGY_PATH = os.getenv("ONTOLOGY_PATH")  # Phase 2.0 — hukuk sözlüğü (opsiyonel)

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

# --- 2. PYDANTIC ŞEMALARI ---
class AnalyzeRequest(BaseModel):
    soru: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Kullanıcının halk ağzıyla yazdığı hukuki olay/soru.",
        examples=["Hırsızlık yapan birinin cezası nedir?"],
    )
    ek_bilgi: str = Field(default="", max_length=1200)
    ek_soru: str = Field(default="", max_length=240)
    ek_soru_yanitlandi: bool = False

    def analysis_question(self) -> str:
        if not self.ek_soru_yanitlandi:
            return self.soru
        bilgi = self.ek_bilgi.strip() or "Ek bilgi verilmedi; eksik hususları varsaymadan koşullu değerlendir."
        return f"OLAY: {self.soru}\nNETLEŞTİRME SORUSU: {self.ek_soru}\nEK BİLGİ: {bilgi}"


class AnalyzeResponse(BaseModel):
    soru: str = Field(..., description="Orijinal kullanıcı sorusu (echo).")
    cikarilan_kavramlar: list[str] = Field(
        ..., description="Aşama 1: LLM tarafından çıkarılan hukuki kavramların listesi."
    )
    bulunan_madde_numaralari: list[str] = Field(
        ..., description="Aşama 2: ChromaDB'den retrieve edilen TCK madde numaraları."
    )
    mutalaa: str = Field(..., description="Aşama 3: LLM'in nihai hukuki mütalaası.")
    ek_soru: str | None = None


class HealthResponse(BaseModel):
    status: str
    collection_doc_count: int | None
    lm_studio_reachable: bool


# --- 3. RAG YARDIMCI FONKSİYONLARI (CLI sürümünden taşındı) ---
async def _llm_chat(
    llm_client: AsyncOpenAI,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 3000,
    temperature: float = 0.3,
    reasoning_effort: str | None = None,
) -> str:
    """LM Studio'ya istek atar, cevap metnini döndürür. Boş cevap durumlarında güvenli."""
    cevap = await llm_client.chat.completions.create(
        model=LM_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        # LM Studio/Gemma destekler; eski OpenAI SDK'larında da extra_body kullanılabilir.
        extra_body={"reasoning_effort": reasoning_effort} if reasoning_effort else {},
    )
    if cevap.choices and cevap.choices[0].message.content:
        return cevap.choices[0].message.content.strip()
    return ""


def _build_halk_dili_index(ontology: dict) -> dict[str, str]:
    """Hukuk ontolojisinden halk_dili_kelime -> resmi_terim ters indeksi oluştur.

    Örnek: {"küfür": "hakaret", "sövme": "hakaret", "cinayet": "kasten adam öldürme", ...}
    """
    index: dict[str, str] = {}
    for key, val in ontology.items():
        if not isinstance(val, dict):
            continue
        resmi = (val.get("resmi_terim") or key or "").strip()
        if not resmi:
            continue
        halk_kelimeler = val.get("halk_dili_karsiliklari") or []
        for k in halk_kelimeler:
            if isinstance(k, str) and k.strip():
                index[k.strip().lower()] = resmi
    return index


def _expand_with_halk_dili(question: str, halk_index: dict[str, str]) -> list[str]:
    """Soruyu tarayıp halk dili kelimelerini bulur, karşılık gelen resmi terimleri döndürür.

    Whole-word match (word boundary) kullanır. Çoklu eşleşmeler tek listeye birleşir.
    """
    if not halk_index:
        return []
    q_lower = question.lower()
    found: list[str] = []
    seen_resmi: set[str] = set()
    for halk_word, resmi in halk_index.items():
        # \b ile kelime sınırı kontrolü — kısmî eşleşmeleri ele.
        # Sonu "*" olan karşılıklar kök eşleşmesidir: "çaldı*" → çaldı, çaldılar.
        if halk_word.endswith("*"):
            pattern = r"\b" + re.escape(halk_word[:-1])
        else:
            pattern = r"\b" + re.escape(halk_word) + r"\b"
        if re.search(pattern, q_lower):
            if resmi not in seen_resmi:
                seen_resmi.add(resmi)
                found.append(resmi)
    return found


async def _extract_concepts(
    question: str,
    llm_client: AsyncOpenAI,
    halk_index: dict[str, str] | None = None,
    allow_clarification: bool = True,
) -> tuple[list[str], str | None]:
    """Aşama 1: Halk ağzındaki olayı saf hukuki kavramlara dönüştür.

    İki kaynak birleştirilir:
      (a) LLM tabanlı kavram çıkarma (TERCUMAN_PROMPTU).
      (b) Ontoloji tabanlı halk dili → resmi terim eşleştirmesi (deterministik).
    LLM'in kaçırdığı yaygın kelimeler (örn. "küfür" → "hakaret") (b) ile yakalanır.
    """
    # Küçük modelin madde numarasından yanlış suç adı tahmin etmesini önle.
    # Kaynaklar zaten orijinal sorudaki açık referans üzerinden bulunur.
    if _explicit_article_refs(question) and len(question) < 160 and re.search(
        r"\b(neyi düzenler|nedir|ne diyor|açıkla|metni|metnini)\b", question.lower()
    ):
        return [], None
    prompt = TERCUMAN_PROMPTU
    if not allow_clarification:
        prompt += "\nBu olay için ek soru hakkı kullanıldı. Yeni soru SORMA; ek_soru null olsun. Mevcut bilgilerle kavramları çıkar."
    raw = await _llm_chat(
        llm_client=llm_client,
        system_prompt=prompt,
        user_message=question,
        max_tokens=512,
        temperature=0.3,
        reasoning_effort="none",
    )
    llm_kavramlar, ek_soru = _parse_concepts(raw, allow_clarification)

    halk_kavramlar = _expand_with_halk_dili(question, halk_index or {})

    # Birleştir, sıra koru (LLM önce, halk dili sonra), case-insensitive dedup
    seen: set[str] = set()
    merged: list[str] = []
    for k in llm_kavramlar + halk_kavramlar:
        k_low = k.lower()
        if k_low not in seen:
            seen.add(k_low)
            merged.append(k)
    return merged[:8], ek_soru


def _parse_concepts(raw: str, allow_clarification: bool) -> tuple[list[str], str | None]:
    """JSON biçimini doğrula; eski virgüllü cevaplara da tolerans göster."""
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        concepts = data.get("kavramlar", [])
        if not isinstance(concepts, list):
            concepts = []
        concepts = [c.strip()[:100] for c in concepts if isinstance(c, str) and c.strip()]
        question = data.get("ek_soru")
        if not allow_clarification or not isinstance(question, str) or not question.strip():
            question = None
        else:
            # Küçük model birden çok soru döndürürse yalnızca ilkini kullan.
            question = question.strip().split("?")[0].strip()
            question = (question[:239] + "?") if question else None
        return concepts[:5], question
    except (ValueError, TypeError, AttributeError):
        # Bozuk JSON'u hukuki arama kavramına dönüştürme.
        if any(char in raw for char in '{}[]'):
            return [], None
        return [c.strip()[:100] for c in raw.split(",") if c.strip()][:5], None



# --- Aşama 2.5: EKSİK SUÇ KONTROL ---
# Stage 2 retrieval sonrası, mini LLM çağrısı ile "bu olayda ele alınmamış suç var mı?"
# sorulur. Eğer model eksik kavram önerirse, bu kavramlar için ek retrieval yapılır.
# Amaç: Alternatif B (İteratif Refinement) — eksik suç tespit problemini çözer.


async def _check_missing_concepts(
    question: str,
    current_articles: list[str],
    current_metadatas: list[dict],
    llm_client: AsyncOpenAI,
) -> list[str]:
    """Aşama 2.5: Mevcut retrieval'ın eksik bıraktığı suç kavramlarını tespit et.

    Returns:
        Eksik kavram listesi (boşsa veya "YOK" denildiyse [] döner).
    """
    # Mevcut maddelerin başlıklarını listele (mini LLM'e gönderilecek)
    basliklar_listesi: list[str] = []
    for ref, meta in zip(current_articles, current_metadatas):
        baslik = (meta.get("baslik") or "").strip()
        if baslik:
            basliklar_listesi.append(f"- {ref}: {baslik}")
    basliklar_metni = "\n".join(basliklar_listesi) if basliklar_listesi else "(boş)"

    user_msg = (
        f"SORU:\n{question}\n\n"
        f"MEVCUT MADDELERİN BAŞLIKLARI:\n{basliklar_metni}\n\n"
        f"Eksik suç kavramları (sadece virgülle ayrılmış kelimeler veya YOK):"
    )

    raw = await _llm_chat(
        llm_client=llm_client,
        system_prompt=MISSING_CHECK_PROMPT,
        user_message=user_msg,
        max_tokens=300,
        temperature=0.3,
        reasoning_effort="none",
    )

    if not raw:
        return []
    raw = raw.strip()
    if not raw or raw.upper().startswith("YOK"):
        return []
    # Virgülle ayrılmış kavramları temizle
    eksikler = [c.strip() for c in raw.split(",") if c.strip() and c.strip().upper() != "YOK"]
    return eksikler[:5]  # max 5 ek kavram


# --- 4. LIFESPAN: modelleri sunucu açılırken bir kez yükle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Embedding modeli CPU üzerinde yükleniyor...")
    app.state.embedding_model = SentenceTransformer(
        EMBEDDING_MODEL_NAME, device="cpu", local_files_only=True,
    )
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    app.state.collection = chroma_client.get_collection(name=COLLECTION_NAME)
    records = app.state.collection.get(where={"mulga": False}, include=["documents", "metadatas"])
    app.state.lexical_index = BM25Index(records)
    print(f"Hibrit arama hazır: {len(app.state.lexical_index.hits)} aktif parça.")
    app.state.penalty_index = build_penalty_index(records)
    print(f"Ceza tablosu hazır: {len(app.state.penalty_index)} madde.")

    if ONTOLOGY_PATH and os.path.isfile(ONTOLOGY_PATH):
        with open(ONTOLOGY_PATH, "r", encoding="utf-8") as file:
            app.state.halk_dili_index = _build_halk_dili_index(json.load(file))
    else:
        app.state.halk_dili_index = {}
        print("UYARI: Hukuk ontolojisi yüklenmedi.")

    # 4 GB VRAM için analizleri sırayla işle; ikinci model yükleme.
    app.state.analysis_lock = asyncio.Semaphore(1)
    app.state.llm_client = AsyncOpenAI(
        base_url=LM_STUDIO_BASE_URL, api_key=LM_STUDIO_API_KEY,
        timeout=600, max_retries=0,
    )
    try:
        yield
    finally:
        await app.state.llm_client.close()


app = FastAPI(
    title="TCK Hukuk Asistanı API",
    description="Yerel hibrit arama ve akan yanıt ile hukuki analiz.",
    version="1.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)


async def _analysis_events(request: AnalyzeRequest, state):
    """SSE ucunun analiz pipeline'ı; sohbet geçmişi sunucuda saklanmaz."""
    yield {"type": "progress", "message": "Analiz sırası bekleniyor…"}
    async with state.analysis_lock:
        stage = "Kavram çıkarma"
        try:
            question = request.analysis_question()
            yield {"type": "progress", "message": "Olay ve hukuki kavramlar inceleniyor…"}
            concepts, clarification = await _extract_concepts(
                question, state.llm_client, state.halk_dili_index,
                allow_clarification=not request.ek_soru_yanitlandi,
            )
            if clarification:
                response = AnalyzeResponse(
                    soru=request.soru, cikarilan_kavramlar=concepts,
                    bulunan_madde_numaralari=[], mutalaa=clarification, ek_soru=clarification,
                )
                yield {"type": "result", **response.model_dump()}
                return

            if (request.ek_soru_yanitlandi and not concepts and not request.ek_bilgi.strip()
                    and not _explicit_article_refs(request.soru)):
                # Atlanan tek ek sorudan sonra belirsiz olaya suç/ceza yakıştırma.
                response = AnalyzeResponse(
                    soru=request.soru, cikarilan_kavramlar=[], bulunan_madde_numaralari=[],
                    mutalaa=("Anlatımda somut eylem belirtilmediği için bir suç tipi veya ceza aralığı "
                             "belirlenemez. Eksik bilgileri varsaymadan değerlendirme yapabilmek için "
                             "kişinin ne yaptığı veya ne söylediği bilgisi gerekir."),
                )
                yield {"type": "result", **response.model_dump()}
                return

            stage = "Hibrit arama"
            yield {"type": "progress", "message": "Kanun kaynakları anlam ve kelime eşleşmesiyle aranıyor…"}
            refs, articles, metadatas = await asyncio.to_thread(
                _retrieve_articles, question, state.embedding_model, state.collection,
                N_RESULTS, concepts, state.lexical_index,
            )
            stage = "Eksik suç kontrolü"
            yield {"type": "progress", "message": "Kaynakların kapsamı kontrol ediliyor…"}
            try:
                missing = await _check_missing_concepts(question, refs, metadatas, state.llm_client)
            except Exception as error:
                # Olayın kendisini veya model yanıtını loglama.
                print(f"Eksik suç kontrolü atlandı: {type(error).__name__}")
                missing = []
            if missing:
                concepts = list(dict.fromkeys(concepts + missing))[:8]
                refs, articles, metadatas = await asyncio.to_thread(
                    _retrieve_articles, question, state.embedding_model, state.collection,
                    N_RESULTS, concepts, state.lexical_index,
                )

            metadata = {"cikarilan_kavramlar": concepts, "bulunan_madde_numaralari": refs}
            table = penalty_table(refs, getattr(state, "penalty_index", {}))
            yield {"type": "sources", **metadata}
            stage = "Mütalaa üretimi"
            yield {"type": "progress", "message": "Yanıt hazırlanıyor…"}
            parts = []
            stream = await state.llm_client.chat.completions.create(
                model=LM_MODEL_NAME,
                messages=[{"role": "system", "content": SISTEM_PROMPTU},
                          {"role": "user", "content": f"{articles}{table}SORU:\n{question}"}],
                temperature=0.1, max_tokens=4000, stream=True,
            )
            truncated = False
            async with stream:
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    truncated = truncated or choice.finish_reason == "length"
                    content = choice.delta.content
                    if content:
                        parts.append(content)
                        yield {"type": "token", "content": content}
            if not parts:
                raise ValueError("Empty model response")
            if truncated:
                yield {"type": "error", "message": "Yanıt modelin çıktı sınırına ulaştığı için tamamlanamadı. Görünen metin kısmi yanıttır."}
                return
            # Kaynakta karşılığı olmayan ceza aralıklarını kullanıcıya açıkça işaretle.
            warning = range_warning(unsupported_ranges("".join(parts), articles + table))
            if warning:
                parts.append(warning)
                yield {"type": "token", "content": warning}
            response = AnalyzeResponse(soru=request.soru, mutalaa="".join(parts).strip(), **metadata)
            yield {"type": "result", **response.model_dump()}
        except Exception as error:
            print(f"{stage} başarısız: {type(error).__name__}")
            yield {"type": "error", "message": f"{stage} tamamlanamadı. LM Studio bağlantısını, modelin yüklü olduğunu ve bağlam sınırını kontrol edin."}


async def _sse_events(request: AnalyzeRequest, state):
    # Uzun GPU üretimlerinde bağlantı canlı kalsın; istemci ayrılınca model akışını kapat.
    iterator = _analysis_events(request, state)
    pending = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait({pending}, timeout=10)
            if not done:
                yield ": keep-alive\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
    finally:
        if pending is not None:
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
        await iterator.aclose()


@app.post("/api/v1/analyze/stream")
async def analyze_stream(request: AnalyzeRequest, http_request: Request):
    return StreamingResponse(
        _sse_events(request, http_request.app.state), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
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
        await state.llm_client.models.list()
        lm_ok = True
    except Exception:
        lm_ok = False

    overall = "ok" if (doc_count is not None and lm_ok) else "degraded"

    return HealthResponse(
        status=overall,
        collection_doc_count=doc_count,
        lm_studio_reachable=lm_ok,
    )
