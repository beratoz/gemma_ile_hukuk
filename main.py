# =============================================================
# TCK RAG CHATBOT - FastAPI REST API
# 3 Aşamalı Mimari:
#   Aşama 1: Hukuki Tercüman (LLM ile kavram çıkarma)
#   Aşama 2: Vektör Retrieval (kavramlarla ChromaDB araması)
#   Aşama 3: Nihai Mütalaa (LLM ile hukuki analiz)
# =============================================================

import asyncio
import json
import os
import re
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

TERCUMAN_PROMPTU = """Sen bir hukuki kavram çıkarıcısın. Sana verilen halk ağzıyla anlatılmış olayı analiz et ve TCK'da karşılık gelen anahtar kelimeleri/kavramları aralarına virgül koyarak yaz.

KURALLAR:
- En fazla 5 kavram yaz.
- Sadece olayda AÇIKÇA GEÇEN fiile DOĞRUDAN ilişkin kavramları yaz. Yan kavramlar, ihtimal kavramları, "olabilir" denilen kavramlar EKLEME.
- Genel/soyut kavramlar (örn: "ceza hukuku", "ceza sorumluluğu", "bilişim", "hukuki süreç") YAZMA; somut suç/kurum adları kullan.
- Cümle kurma, açıklama yapma, yorum yapma.
- Sadece virgülle ayrılmış kelime/kavramları yaz.
- Örnek 1: "WhatsApp grubunda ağır hakaret edildi" → "hakaret, aleniyet, ihtilat, şikayete bağlı suç"
- Örnek 2: "Komşum birine bıçakla saldırdı" → "kasten yaralama, silahla yaralama, kasten öldürmeye teşebbüs"
- Örnek 3: "Cüzdanım çalındı, hırsız yakalandı" → "hırsızlık, taşınır mal, zilyet"
- Türkçe ve TCK terminolojisi kullan."""

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
        max_length=4000,
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
    max_tokens: int = 3000,
    temperature: float = 0.3,
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


def _extract_concepts(
    question: str,
    llm_client: OpenAI,
    halk_index: dict[str, str] | None = None,
) -> list[str]:
    """Aşama 1: Halk ağzındaki olayı saf hukuki kavramlara dönüştür.

    İki kaynak birleştirilir:
      (a) LLM tabanlı kavram çıkarma (TERCUMAN_PROMPTU).
      (b) Ontoloji tabanlı halk dili → resmi terim eşleştirmesi (deterministik).
    LLM'in kaçırdığı yaygın kelimeler (örn. "küfür" → "hakaret") (b) ile yakalanır.
    """
    raw = _llm_chat(
        llm_client=llm_client,
        system_prompt=TERCUMAN_PROMPTU,
        user_message=question,
        max_tokens=3000,
        temperature=0.3,
    )
    llm_kavramlar = [c.strip() for c in raw.split(",") if c.strip()] if raw else []

    halk_kavramlar = _expand_with_halk_dili(question, halk_index or {})

    # Birleştir, sıra koru (LLM önce, halk dili sonra), case-insensitive dedup
    seen: set[str] = set()
    merged: list[str] = []
    for k in llm_kavramlar + halk_kavramlar:
        k_low = k.lower()
        if k_low not in seen:
            seen.add(k_low)
            merged.append(k)
    return merged


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


def _retrieve_articles(
    search_text: str,
    embedding_model: SentenceTransformer,
    collection: "chromadb.Collection",
    n_results: int,
    concepts: list[str] | None = None,
) -> tuple[list[str], str]:
    """Aşama 2: Multi-query retrieval (K3).

    İki strateji:
      (a) Eğer `concepts` listesi (Stage 1'in çıkardığı kavramlar) verilmişse:
          her kavram için ayrı bir ChromaDB sorgusu yapılır, sonuçlar Reciprocal
          Rank Fusion (RRF) ile birleştirilir. Birden çok suç içeren olaylarda
          her suç kavramı için spesifik retrieval yapılır → kapsam artar.
      (b) Yoksa: tek query (eski davranış) — `search_text` ile fallback.

    Returns:
        (madde_no_listesi, llm'e gönderilecek formatted maddeler_metni)
    """
    # Sorgu metinleri listesi — birden fazlaysa multi-query, değilse tek
    if concepts and len(concepts) >= 2:
        # Multi-query: her kavram ayrı + tüm kavramlar birleşik bir backup sorgu
        sorgu_metinleri = [c for c in concepts if c.strip()]
        # Tüm kavramların birleşimi (eski stil) de dahil — geniş semantic için
        birlesik = ", ".join(sorgu_metinleri)
        if birlesik not in sorgu_metinleri:
            sorgu_metinleri.append(birlesik)
    else:
        sorgu_metinleri = [search_text]

    # Her sorgu için top-K retrieval
    # Per-query K: n_results / num_queries kadar (min 3), ama RRF için biraz daha fazla
    per_query_k = max(3, min(n_results, 6))

    # RRF parametresi (Reciprocal Rank Fusion sabiti)
    RRF_K = 60

    # Tüm hits'leri toplama: doc_id -> {score, doc, meta, ids}
    aggregated: dict[str, dict] = {}

    for q_text in sorgu_metinleri:
        # E5 modeli sorgular için MUTLAKA "query: " öneki ister
        q_with_prefix = "query: " + q_text
        q_vec = embedding_model.encode(q_with_prefix, normalize_embeddings=True).tolist()
        sonuclar = collection.query(
            query_embeddings=[q_vec],
            n_results=per_query_k,
            where={"mulga": False},
        )
        docs = sonuclar["documents"][0]
        metas = sonuclar["metadatas"][0]
        ids_list = sonuclar["ids"][0]
        for rank, (doc, meta, doc_id) in enumerate(zip(docs, metas, ids_list), start=1):
            # display_key bazlı dedup (aynı madde farklı chunk'larda birden fazla gelebilir)
            kaynak_kodu = (meta.get("kaynak_kodu") or "TCK").strip() or "TCK"
            birim_no = str(
                meta.get("birim_no")
                or meta.get("madde_no")
                or meta.get("madde")
                or doc_id
            )
            display_key = f"{kaynak_kodu} {birim_no}"
            rrf_contribution = 1.0 / (RRF_K + rank)
            if display_key not in aggregated:
                aggregated[display_key] = {
                    "score": rrf_contribution,
                    "doc": doc,
                    "meta": meta,
                    "doc_id": doc_id,
                    "display_key": display_key,
                }
            else:
                # Aynı madde başka sorguda da çıktıysa skoru topla (RRF özelliği)
                aggregated[display_key]["score"] += rrf_contribution

    # Skora göre sırala, top-n_results al
    ranked = sorted(aggregated.values(), key=lambda x: x["score"], reverse=True)
    top_hits = ranked[:n_results]

    # Formatla
    madde_no_listesi: list[str] = []
    maddeler_metni = ""
    for i, hit in enumerate(top_hits, start=1):
        display_key, block = _format_retrieved_hit(
            hit["doc"], hit["meta"], hit["doc_id"], i
        )
        madde_no_listesi.append(display_key)
        maddeler_metni += block

    return madde_no_listesi, maddeler_metni


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


def _check_missing_concepts(
    question: str,
    current_articles: list[str],
    current_metadatas: list[dict],
    llm_client: OpenAI,
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

    raw = _llm_chat(
        llm_client=llm_client,
        system_prompt=MISSING_CHECK_PROMPT,
        user_message=user_msg,
        max_tokens=300,
        temperature=0.3,
    )

    if not raw:
        return []
    raw = raw.strip()
    if not raw or raw.upper().startswith("YOK"):
        return []
    # Virgülle ayrılmış kavramları temizle
    eksikler = [c.strip() for c in raw.split(",") if c.strip() and c.strip().upper() != "YOK"]
    return eksikler[:5]  # max 5 ek kavram


def _generate_opinion(question: str, articles_text: str, llm_client: OpenAI) -> str:
    """Aşama 3: Orijinal soru + bulunan maddeler ile hukuki mütalaa üret.

    temperature=0.1: hukuki context'te daha tutarlı/katı cevaplar için (yaratıcılık değil,
    determinizm tercih edilir).
    max_tokens=4000: 5-adımlı per-suç metodoloji + içtima + pratik sonuç için yeterli alan
    (önceki 3000 cevabı 'Huk' gibi kelime ortasında kesiyordu).
    """
    kullanici_mesaji = f"{articles_text}SORU:\n{question}"
    cevap = _llm_chat(
        llm_client=llm_client,
        system_prompt=SISTEM_PROMPTU,
        user_message=kullanici_mesaji,
        max_tokens=4000,
        temperature=0.1,
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

    # Phase 2.0 — Hukuk ontolojisi (opsiyonel, halk dili genişletmesi için)
    if ONTOLOGY_PATH and os.path.isfile(ONTOLOGY_PATH):
        with open(ONTOLOGY_PATH, "r", encoding="utf-8") as f:
            ontology = json.load(f)
        app.state.halk_dili_index = _build_halk_dili_index(ontology)
        print(
            f"Hukuk ontolojisi yüklendi: {len(ontology)} kavram, "
            f"{len(app.state.halk_dili_index)} halk dili eşlemesi."
        )
    else:
        app.state.halk_dili_index = {}
        print("UYARI: ONTOLOGY_PATH ayarlı değil, halk dili genişletmesi devre dışı.")

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
        # Aşama 1: Hukuki Tercüman + halk dili genişletme
        kavramlar = await asyncio.to_thread(
            _extract_concepts,
            request.soru,
            state.llm_client,
            state.halk_dili_index,
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Aşama 1 (Tercüman) hatası — LM Studio erişilemiyor olabilir: {e}",
        )

    # Tercüman boş döndüyse fallback: orijinal soru ile retrieval yap
    arama_metni = ", ".join(kavramlar) if kavramlar else request.soru

    try:
        # Aşama 2: Multi-Query Retrieval (K3) — her kavram için ayrı sorgu + RRF birleşim
        madde_nolari, maddeler_metni = await asyncio.to_thread(
            _retrieve_articles,
            arama_metni,
            state.embedding_model,
            state.collection,
            N_RESULTS,
            kavramlar,  # K3: Stage 1'in kavramlarını multi-query için gönder
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Aşama 2 (Vektör Arama) hatası — ChromaDB erişilemiyor olabilir: {e}",
        )

    # Aşama 2.5: Eksik Suç Kontrolü (Alternatif B — İteratif Refinement)
    # Mini LLM'e mevcut retrieval başlıklarını gösterip "eksik suç var mı?" sor
    eksik_kavramlar: list[str] = []
    try:
        # Mevcut maddelerin metadata'larını çek (kısa LLM bağlamı için)
        # Not: bu zaten yapılmış bir sorgu, tekrar fetch etmek yerine
        # mevcut display_key'leri ve başlıkları çıkarmak gerekiyor.
        # Bu yüzden kısa bir ek query ile başlıkları çekiyoruz.
        # (alternatif: _retrieve_articles döner değerini değiştirmek; minimal değişiklik için
        # buradan ek query yapıyoruz — performans etkisi düşük)
        current_metadatas: list[dict] = []
        for ref in madde_nolari:
            # ref formatı "TCK 125" gibi → kaynak_kodu + birim_no
            parts = ref.split(" ", 1)
            if len(parts) == 2:
                kk, bn = parts[0], parts[1]
                try:
                    r = state.collection.get(
                        where={"$and": [{"kaynak_kodu": kk}, {"birim_no": bn}]},
                        limit=1,
                    )
                    if r and r.get("metadatas"):
                        current_metadatas.append(r["metadatas"][0])
                    else:
                        current_metadatas.append({})
                except Exception:
                    current_metadatas.append({})
            else:
                current_metadatas.append({})

        eksik_kavramlar = await asyncio.to_thread(
            _check_missing_concepts,
            request.soru,
            madde_nolari,
            current_metadatas,
            state.llm_client,
        )

        # Eğer eksik kavramlar tespit edildiyse, onlar için EK retrieval yap, top-N'e ekle
        if eksik_kavramlar:
            print(f"[Stage 2.5] Eksik kavram tespit edildi: {eksik_kavramlar}")
            ek_kavramlar = kavramlar + eksik_kavramlar  # birleşik kavram listesi
            # Tekrar multi-query ile retrieve, ama bu sefer eksik kavramları da dahil ederek
            ek_madde_nolari, ek_maddeler_metni = await asyncio.to_thread(
                _retrieve_articles,
                ", ".join(ek_kavramlar),
                state.embedding_model,
                state.collection,
                N_RESULTS,
                ek_kavramlar,
            )
            # Yeni sonuçları kullan (eksik kavramlar artık dahil)
            madde_nolari, maddeler_metni = ek_madde_nolari, ek_maddeler_metni
            # Kavramlar listesine de ekle (frontend görsün)
            kavramlar = ek_kavramlar
    except Exception as e:
        # Stage 2.5 başarısız olursa pipeline'ı bozmamak için sessizce devam
        print(f"[Stage 2.5] UYARI: Eksik suç kontrolü başarısız: {e}")

    try:
        # Aşama 3: Nihai Mütalaa (yapılandırılmış metodoloji ile)
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
