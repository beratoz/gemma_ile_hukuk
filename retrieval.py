"""Aşama 2: Hibrit arama (dense E5 + BM25), Reciprocal Rank Fusion ile birleştirme."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import chromadb
    from sentence_transformers import SentenceTransformer

# Başlık eşleşmesinde yalnızca kanun maddeleri (gerekçe/doktrin değil) aday olur.
TITLE_SOURCES = ("TCK", "CMK")


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

    def title_hits(self, concept: str, sources=TITLE_SOURCES, limit: int = 2) -> list[dict]:
        """Kavram bir kanun maddesinin başlığında bütün olarak geçiyorsa o maddeyi döndür.

        Örn. "meşru savunma" → TCK 25 "Meşru Savunma ve Zorunluluk Hâli".
        Tam eşleşen (en kısa) başlık önce gelir; gerekçe/doktrin başlıkları dahil edilmez.
        """
        words = _search_tokens(concept)
        if not words:
            return []
        size = len(words)
        found = {}
        for hit, title in zip(self.hits, self.titles):
            if hit["meta"].get("kaynak_kodu", "TCK") not in sources or hit["display_key"] in found:
                continue
            if any(title[i:i + size] == words for i in range(len(title) - size + 1)):
                found[hit["display_key"]] = (len(title), hit)
        ordered = sorted(found.values(), key=lambda item: (item[0], item[1]["display_key"]))
        return [hit for _, hit in ordered[:limit]]


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
            if query != search_text:
                # Kavram adı madde başlığıyla örtüşüyorsa (ör. "meşru savunma" → TCK 25) ek oy ver.
                add_ranking(lexical_index.title_hits(query))

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
