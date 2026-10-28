# =============================================================
# TCK RAG CHATBOT - FastAPI REST API
# 3 Aşamalı Mimari:
#   Aşama 1: Hukuki Tercüman (LLM ile kavram çıkarma)
#   Aşama 2: Vektör Retrieval (kavramlarla ChromaDB araması)
#   Aşama 3: Nihai Mütalaa (LLM ile hukuki analiz)
# =============================================================

import asyncio
import json
import math
import os
import re
from collections import Counter, defaultdict
from contextlib import aclosing, asynccontextmanager

import chromadb
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
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

# --- 2. PROMPTLAR ---
# CLI sürümünden harfiyen kopyalandı (commit ba3545e: retrieval doğruluğunu artıran promptlar).

TERCUMAN_PROMPTU = """Sen bir hukuki kavram çıkarıcısın. Halk ağzıyla anlatılan olayı analiz et ve TCK'daki ilgili somut suç/kurum adlarını çıkar.

KURALLAR:
- En fazla 5 kavram yaz.
- Sadece olayda AÇIKÇA GEÇEN fiile DOĞRUDAN ilişkin kavramları yaz. Yan kavramlar, ihtimal kavramları, "olabilir" denilen kavramlar EKLEME.
- Genel/soyut kavramlar (örn: "ceza hukuku", "ceza sorumluluğu", "bilişim", "hukuki süreç") YAZMA; somut suç/kurum adları kullan.
- Türkçe ve TCK terminolojisi kullan. Açıklama veya Markdown yazma.

ÇIKTI: Sadece JSON yaz: {"kavramlar": ["kavram1"], "ek_soru": null}
Yalnızca somut olayın hangi fiil olduğu anlaşılamıyorsa veya açık bir belirsizlik
temel nitelendirmeyi değiştiriyorsa ek_soru alanında TEK kısa soru sor (en çok 240 karakter).
Genel bilgi ve doğrudan madde sorularında, anlaşılır olaylarda soru SORMA.
Her olaya yaş, tarih, sabıka, delil gibi rutin sorular sorma; eksik ayrıntıları varsayma.
Örnek: "Bana bir şey yaptı, suç mu?" → {"kavramlar": [], "ek_soru": "Size tam olarak ne yaptı veya ne söyledi?"}
Örnek: "Cüzdanımı çaldı" → {"kavramlar": ["hırsızlık", "taşınır mal", "zilyet"], "ek_soru": null}
Örnek: "Ofise zorla girip eşyamı kırdı ve küfür etti" → {"kavramlar": ["işyeri dokunulmazlığı", "mala zarar verme", "hakaret"], "ek_soru": null}
"""

SISTEM_PROMPTU = """Sen uzman bir ceza avukatısın. Görevin, sana sunulan kanun/gerekçe/doktrin kaynaklarını kullanarak, olayda BÜTÜN suç boyutlarını tespit edip pratik ve eyleme dönüştürülebilir bir hukuki mütalaa üretmektir.

KURALLAR:

1. SIFIR UYDURMA — Ama Doğru Sınırla:
   ASLA UYDURMA:
   - Spesifik fıkra/bend numaraları (örn. "TCK 86/2-c" alt-bend) sana verilmediyse yazma
   - Sana verilmemiş madde içeriği veya kesin hüküm metni
   - Kanun değişiklik tarihleri, yargı kararı numaraları, içtihat detayları
   - Sana verilen ceza miktarını YUVARLAMA, AYNEN aktar

   KULLANABİLİRSİN (uydurma sayılmaz, hukukçunun temel bilgisi):
   - Suçun adı ve hukuki niteliği: "hakaret", "şantaj", "işyeri dokunulmazlığını ihlal" vb.
   - Türk hukukundaki MADDE NUMARALARI: TCK 125 = Hakaret, TCK 116 = Konut/İşyeri Dokunulmazlığı, TCK 86 = Kasten Yaralama, TCK 106 = Tehdit, TCK 107 = Şantaj, TCK 151 = Mala Zarar Verme vb. — bu kategorik bilgidir
   - Bir suçun TEMEL CEZA ARALIĞI (örn. "tehdit suçu genel olarak 6 aydan 2 yıla kadar hapis ile cezalandırılır") — kanunun temel terimleri kategorik bilgidir
   - Şikayete tabi suç / resen takip ayrımı (genel bilgi)
   - HAGB, adli para cezasına çevirme, gerçek/fikri içtima, sabıka etkisi gibi pratik kavramlar

2. HUKUKİ NİTELENDİRME (Kritik):
   Günlük dildeki fiilleri hukuki kavramlara çevir:
   - "küfür/sövme/hakaret etti" → hakaret
   - "tokat/yumruk/itme/darp" → kasten yaralama
   - "para istedi yoksa rezil ederim" → şantaj
   - "rızam dışında girdi/daldı" → konut veya işyeri dokunulmazlığını ihlal
   - "seni bitireceğim/öldürürüm" → tehdit
   - "kırdı/parçaladı/yaktı" → mala zarar verme
   - "zorla aldı" → yağma (cebir varsa) veya hırsızlık
   Her fiili ayrı ayrı tanı, atla.

3. ATIF VE KESİNLİK (Multi-Corpus):
   Sana sunulan kaynak başlıkları "KAYNAK N: KAYNAK_KODU Madde X — Başlık" formatındadır. Atıflarını şöyle yap:
   - TCK için: "TCK Madde [X]'e göre"
   - CMK için: "CMK Madde [X]'e göre"
   - CGTIK için: "CGTIK Madde [X]'e göre"
   - TCK Gerekçesi için: "TCK Madde [X] gerekçesinde belirtildiği üzere"
   - Doktrin için: "Doktrine göre" veya "TCK Madde [X] doktrininde belirtildiği üzere"
   Sana verilen ceza süre/miktar/oranlarını AYNEN aktar — yuvarlama, yorumlama.

4. ÜÇ DURUM — DÜRÜST AMA YARDIMCI YAKLAŞIM:

   (A) Verilen kaynaklardan EN AZ BİRİ olayın CEZA HÜKMÜNÜ doğrudan içeriyorsa:
       O kaynak(lar)ı kullanarak mütalaa yaz, ceza miktarını AYNEN aktar. Net hukuki sonuç ver.

   (B) Verilen kaynaklar olayın suçunu KAVRAMSAL OLARAK kapsıyor ama CEZA FIKRASINI tam içermiyorsa:
       1) Suçu adlandır ve TCK madde numarasını söyle (örn. "Bu olay TCK Madde 116 kapsamında İşyeri Dokunulmazlığını İhlal suçunu oluşturur").
       2) Suçun TEMEL CEZA ARALIĞINI kategorik bilgi olarak ver (örn. "bu suçun temel ceza aralığı 6 aydan 2 yıla kadar hapistir; cebir/tehdit unsurları varsa nitelikli hali uygulanır").
       3) Şu uyarıyı ekle: "Spesifik alt/üst sınır ve nitelikli haller için ilgili maddenin tam metnine başvurulmalıdır."
       SAKIN "verilen kaynaklarda spesifik madde bulunmamaktadır, danışmanlık alın" şeklinde TOPU TACA ATMA.

   (C) Verilen kaynaklar olayla TAMAMEN ALAKASIZSA:
       Yine de suçun hukuki niteliğini ADLANDIR (kategorik bilgini kullan), TCK madde numarasını söyle, genel ceza aralığını belirt. "Yeterli değil" deme; tanı koy.

   YASAKLAR (kesinlikle):
   - "Bilemem", "kaynaklarımda yok" gibi atlatma ifadeleri KULLANMA.
   - Bir maddeyi yanlışlıkla ZORLA UYGULAMA (örn. şantaj olayını "özel hayatın gizliliği" diye etiketleme).
   - Sözlü tehdidi "hürriyetten yoksun kılma" gibi yanlış kategorize etme.

5. PRATİK SORU — PRATİK CEVAP:
   Kullanıcı pratik soru sorduğunda yuvarlama; net cevap ver.
   - "Hapis cezası alır mı?" → "Evet/Hayır, [aralık] hapis veya adli para cezası alır. İlk suç ise HAGB veya paraya çevirme ihtimali var. Sicile işleme: ..." şeklinde NET değerlendirme.
   - "Kaç yıl ceza alır?" → Ceza aralığını söyle (X aydan Y yıla kadar). Birden çok suç varsa toplam değerlendirmesi yap.
   - "Şikayetçi olursam ne olur?" → Suç şikayete tabi mi yoksa resen takip mi, süre (genelde 6 ay), olası sonuçlar.
   - "Tutuklanır mı?" → Tutuklama şartlarının özeti (CMK 100 — kuvvetli suç şüphesi + kaçma/delil karartma şüphesi + suçun cezasının ağırlığı), ihtimal değerlendirmesi.
   "Profesyonel danışmanlık alın" cümlesini sadece SONUÇ kısmında kısa bir uyarı olarak ekle, asıl cevabın yerine değil.

6. ÇOKLU SUÇ (İÇTİMA) ve METODOLOJİ — Türk Hukuk Pratiğine Uygun Analiz:

   ADIM 1 (Olay Haritalama): Olayda kaç fail (suç işleyen) ve kaç fiil (eylem) var? Her birini ayrı ayrı listele. "A'nın B'yi yaralaması", "C'nin mala zarar vermesi" gibi her fail+fiil çiftini izole et.

   ADIM 2 (Her Suç İçin 5-Adımlı Analiz): Tespit ettiğin HER suç için aşağıdaki 5 alt-adımı sırayla uygula:

   ### Suç [N]: [Suç Adı]
   **1. Fiil:** Olayda gerçekleşen eylemi tek cümle ile özetle (örn: "Fail, mağdurun bilgisayarını yere fırlatıp kırmıştır").
   **2. Hukuki Nitelendirme:** Bu fiil hangi suçu oluşturur? TCK madde numarasını ve suç adını yaz (örn: "TCK Madde 151 — Mala Zarar Verme").
   **3. Maddi Unsur Kontrolü:** Fiil var mı, netice (somut zarar) var mı, fiil-netice arası nedensellik bağı var mı? Kısa tespit.
   **4. Hukuka Aykırılık Kontrolü (KRİTİK):** Olayda meşru müdafaa, ilgilinin rızası, hakkın kullanılması, kanunun hükmünü yerine getirme gibi bir hukuka uygunluk sebebi VAR MI? Eğer varsa fiil suç oluşturmaz, BERAAT verilir. Eğer YOKSA "Hukuka aykırılık devam etmektedir, suç oluşmuştur" yaz. **Bu adımı asla atlama** — kullanıcı söylemese bile her olayda kontrol et.
   **5. Ceza ve Sonuç:** İlgili madde, ceza aralığı (verilen kaynakta varsa AYNEN, yoksa kategorik bilgini kullan), şikayete tabi mi/resen takip mi, HAGB/paraya çevirme ihtimali.

   ADIM 3 (Genel Değerlendirme): Tüm suçlar incelendikten sonra:
   **### İçtima Değerlendirmesi**
   - Suçlar AYRI FİİLLERLE işlenmişse → gerçek içtima → cezalar TOPLANIR
   - TEK FİİL birden fazla suç oluşturuyorsa → fikri içtima (TCK 44) → EN AĞIR ceza uygulanır
   - Aynı suç tekrar tekrar işlenmişse → zincirleme suç (TCK 43) → ceza artırılır

   **### Pratik Sonuç (Kullanıcının Sorusuna Net Cevap)**
   - "Hapis cezası alır mı?" sorusuna kategorik cevap: muhtemel toplam ceza, HAGB ihtimali, paraya çevirme şansı
   - Atılacak hukuki adımlar: şikayet süresi, gerekli deliller, başvuru yeri
   - 1-3 cümlelik özet

   YAYGIN YANLIŞLAR (KAÇIN):
   - Bir olayda 3-4 suç varken sadece 1-2 görmek (TÜM fiilleri tarayın)
   - Sözlü tehdidi "hürriyetten yoksun kılma" sanmak
   - "İtme" gibi basit fiziksel temasları sadece "hürriyet" çerçevesinde değerlendirmek (kasten yaralama olabilir)
   - Hukuka aykırılık adımını atlamak (özellikle savunma vakalarında VAHIM)
   - Şablonu "BOŞ DOLDURMAK": olayda bilgi yoksa "kusurluluk açısından bir engel görünmemektedir" gibi varsayım yapma; bilgi yoksa "olayda bu konuda bilgi verilmemiştir" de

7. KATI FORMAT:
   - Net, yapılandırılmış, profesyonel hukuki mütalaa
   - Yapay zeka süsleri (Merhaba, başka soru?, umarım yardımcı olur) KESİNLİKLE YASAK
   - Markdown başlıklar/listeler kullanabilirsin (### Suç 1, ### Suç 2, ### İçtima, ### Sonuç şeklinde)
   - Sonuç bölümünde KISA pratik özet ver: hangi suçlardan ne kadar ceza, şikayet/HAGB durumu, atılacak adımlar"""


# --- 3. PYDANTIC ŞEMALARI ---
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


# --- 4. RAG YARDIMCI FONKSİYONLARI (CLI sürümünden taşındı) ---
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
        # \b ile kelime sınırı kontrolü — kısmî eşleşmeleri ele
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


def _format_retrieved_hit(
    doc: str, meta: dict, doc_id: str, index: int
) -> tuple[str, str]:
    """Tek bir retrieval sonucunu (display_key, formatted_block) çiftine çevir."""
    kaynak_kodu = (meta.get("kaynak_kodu") or "TCK").strip() or "TCK"
    birim_no = str(
        meta.get("birim_no")
        or meta.get("madde_no")  # eski şema geriye uyumluluk
        or meta.get("madde")
        or doc_id
    )
    baslik = (meta.get("baslik") or "").strip()
    chunk_no = meta.get("chunk_no")
    chunk_toplam = meta.get("chunk_toplam")

    display_key = f"{kaynak_kodu} {birim_no}"
    baslik_kismi = f" — {baslik}" if baslik else ""
    chunk_kismi = (
        f" (parça {chunk_no}/{chunk_toplam})"
        if chunk_no and chunk_toplam and chunk_toplam > 1
        else ""
    )
    block = (
        f"--- KAYNAK {index}: {kaynak_kodu} Madde {birim_no}{baslik_kismi}{chunk_kismi} ---\n"
        f"{doc}\n\n"
    )
    return display_key, block


def _search_tokens(text: str) -> list[str]:
    # Türkçe I/İ ve şapkalı harfleri iki arama kanalında tutarlı işle.
    normalized = text.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()
    normalized = normalized.translate(str.maketrans("ıâîû", "iaiu"))
    stop_words = {"ve", "veya", "ile", "bir", "bu", "su", "o", "da", "de", "mi", "mu", "icin", "gore", "nedir"}
    return [word for word in re.findall(r"\w+", normalized) if word not in stop_words]


def _article_key(meta: dict, doc_id: str) -> str:
    source = meta.get("kaynak_kodu") or "TCK"
    number = meta.get("birim_no") or meta.get("madde_no") or meta.get("madde") or doc_id
    return f"{source} {number}"


def _explicit_article_refs(text: str) -> set[str]:
    matches = re.findall(
        r"\b(TCK_GEREKCE|TCK_DOKTRIN|TCK|CMK|CGTIK)\s*(?:madde(?:si)?\s*)?(\d+(?:/\d+)?)\b",
        text, re.IGNORECASE,
    )
    return {f"{source.upper()} {number.split('/')[0]}" for source, number in matches}


class BM25Index:
    """Mevcut ChromaDB metinlerinden CPU/RAM üzerinde kurulur; yeni model indirmez."""

    def __init__(self, records: dict):
        self.hits = []
        self.lengths = []
        self.titles = []
        self.postings = defaultdict(dict)
        for doc_id, doc, meta in zip(records["ids"], records["documents"], records["metadatas"]):
            meta = meta or {}
            if meta.get("mulga") or not doc:
                continue
            key = _article_key(meta, doc_id)
            title_words = _search_tokens(meta.get("baslik", ""))
            words = _search_tokens(f"{key} {doc}") + title_words * 3
            position = len(self.hits)
            self.hits.append({"doc_id": doc_id, "doc": doc, "meta": meta, "display_key": key})
            self.lengths.append(len(words))
            self.titles.append(title_words)
            for word, frequency in Counter(words).items():
                self.postings[word][position] = frequency
        self.average_length = sum(self.lengths) / max(1, len(self.lengths)) or 1

    def search(self, text: str, limit: int) -> list[dict]:
        if limit <= 0:
            return []
        scores = defaultdict(float)
        count = len(self.hits)
        query_words = _search_tokens(text)
        for word in set(query_words):
            matches = self.postings.get(word, {})
            idf = math.log(1 + (count - len(matches) + 0.5) / (len(matches) + 0.5))
            for index, frequency in matches.items():
                length_norm = 0.25 + 0.75 * self.lengths[index] / self.average_length
                scores[index] += idf * frequency * 2.5 / (frequency + 1.5 * length_norm)
        # Tam suç/kurum adı, uzun metindeki tesadüfi tekrarların gerisinde kalmasın.
        for index in scores:
            if query_words == self.titles[index]:
                scores[index] *= 1.75
        ordered = sorted(scores, key=lambda index: (-scores[index], self.hits[index]["doc_id"]))
        hits, seen = [], set()
        for index in ordered:
            hit = self.hits[index]
            if hit["display_key"] in seen:
                continue
            seen.add(hit["display_key"])
            hits.append(hit)
            if len(hits) >= limit:
                break
        return hits


def _retrieve_articles(
    search_text: str,
    embedding_model: SentenceTransformer,
    collection: "chromadb.Collection",
    n_results: int,
    concepts: list[str] | None = None,
    lexical_index: BM25Index | None = None,
) -> tuple[list[str], str, list[dict]]:
    """Dense multi-query + BM25, RRF ile birleşir. LLM'e gönderilen kaynak sayısı artmaz."""
    queries = list(dict.fromkeys([search_text] + [c for c in (concepts or []) if c.strip()]))
    per_query_k = max(3, min(n_results, 6))
    aggregated: dict[str, dict] = {}

    def add_ranking(hits: list[dict]):
        seen = set()
        for rank, hit in enumerate(hits, start=1):
            key = hit["display_key"]
            # Aynı listenin farklı parçaları aynı maddeye fazladan oy vermesin.
            if key in seen:
                continue
            seen.add(key)
            contribution = 1 / (60 + rank)
            if key not in aggregated:
                aggregated[key] = {**hit, "score": 0, "chunk_scores": defaultdict(float)}
            entry = aggregated[key]
            entry["score"] += contribution
            entry["chunk_scores"][hit["doc_id"]] += contribution
            if entry["chunk_scores"][hit["doc_id"]] > entry["chunk_scores"][entry["doc_id"]]:
                entry.update(hit)

    for query in queries:
        vector = embedding_model.encode("query: " + query, normalize_embeddings=True).tolist()
        result = collection.query(query_embeddings=[vector], n_results=per_query_k, where={"mulga": False})
        hits = []
        for doc, meta, doc_id in zip(result["documents"][0], result["metadatas"][0], result["ids"][0]):
            meta = meta or {}
            if doc and not meta.get("mulga"):
                hits.append({"doc": doc, "meta": meta, "doc_id": doc_id, "display_key": _article_key(meta, doc_id)})
        add_ranking(hits)
        if lexical_index:
            add_ranking(lexical_index.search(query, per_query_k))

    # Açıkça istenen madde, anlamsal benzerliğin gölgesinde kalmasın.
    explicit_keys = _explicit_article_refs(search_text)
    if lexical_index:
        exact_hits = [hit for hit in lexical_index.hits if hit["display_key"] in explicit_keys]
        add_ranking(exact_hits)
    ranked = sorted(aggregated.values(), key=lambda hit: (hit["display_key"] not in explicit_keys, -hit["score"], hit["display_key"]))[:n_results]
    refs, blocks, metadatas = [], [], []
    for index, hit in enumerate(ranked, start=1):
        key, block = _format_retrieved_hit(hit["doc"], hit["meta"], hit["doc_id"], index)
        refs.append(key)
        blocks.append(block)
        metadatas.append(hit["meta"])
    return refs, "".join(blocks), metadatas


# --- Aşama 2.5: EKSİK SUÇ KONTROL ---
# Stage 2 retrieval sonrası, mini LLM çağrısı ile "bu olayda ele alınmamış suç var mı?"
# sorulur. Eğer model eksik kavram önerirse, bu kavramlar için ek retrieval yapılır.
# Amaç: Alternatif B (İteratif Refinement) — eksik suç tespit problemini çözer.

MISSING_CHECK_PROMPT = """Sen bir hukuk asistanısın. Sana bir kullanıcı sorusu ve mevcut retrieval sonuçları (TCK/CMK/CGTIK maddelerinin başlıkları) verilecek.

GÖREVİN: Kullanıcının olayında **mevcut maddelerle KAPSANMAYAN** başka suç tipleri var mı tespit et.

KURALLAR:
- Sadece olayda AÇIKÇA geçen ama listede karşılığı OLMAYAN suçları öner.
- Mevcut maddelerin başlıklarına bak; eğer suç türü zaten temsil ediliyorsa TEKRAR ÖNERME.
- Önerini SADECE virgülle ayrılmış kavram listesi olarak yaz (1-5 kavram, max).
- Eğer eksiklik yoksa veya emin değilsen sadece "YOK" yaz.
- Açıklama, cümle, yorum YAPMA. Sadece "kavram1, kavram2" veya "YOK".
- Türk Ceza Kanunu terminolojisi kullan.

ÖRNEKLER:
Soru: "Ofise zorla girdi, eşya kırdı, hakaret etti"
Mevcut başlıklar: "Mala Zarar Verme, Hakaret"
Cevap: işyeri dokunulmazlığı, tehdit

Soru: "Birinin cüzdanını çaldı"
Mevcut başlıklar: "Hırsızlık, Nitelikli Hırsızlık"
Cevap: YOK
"""


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


# --- 5. LIFESPAN: modelleri sunucu açılırken bir kez yükle ---
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
    """JSON ve SSE uçları aynı pipeline'ı kullanır; sohbet geçmişi sunucuda saklanmaz."""
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
            yield {"type": "sources", **metadata}
            stage = "Mütalaa üretimi"
            yield {"type": "progress", "message": "Yanıt hazırlanıyor…"}
            parts = []
            stream = await state.llm_client.chat.completions.create(
                model=LM_MODEL_NAME,
                messages=[{"role": "system", "content": SISTEM_PROMPTU},
                          {"role": "user", "content": f"{articles}SORU:\n{question}"}],
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


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, http_request: Request) -> AnalyzeResponse:
    async with aclosing(_analysis_events(request, http_request.app.state)) as events:
        async for event in events:
            if event["type"] == "result":
                return AnalyzeResponse.model_validate(event)
            if event["type"] == "error":
                raise HTTPException(status_code=503, detail=event["message"])
    raise HTTPException(status_code=503, detail="Analiz tamamlanamadı.")


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
