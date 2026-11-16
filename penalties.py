"""Ceza tablosu ve ceza aralığı doğrulaması (yalnızca standart kütüphane).

1) Kanun metinlerinden fıkra bazında ceza/şikâyet cümlelerini çıkarır; mütalaa
   çağrısına kısa bir "CEZA VE ŞİKÂYET TABLOSU" olarak eklenir. Böylece model
   aralığı ezberden yazmak yerine kaynaktan alır ve nitelikli/hafif halleri
   (ör. TCK 86/2, 86/3) ayrı ayrı görür.
2) Üretilen yanıttaki "X'den Y'ye kadar" aralıklarını sayısallaştırıp kaynak
   metinlerdeki aralıklarla karşılaştırır; kaynakta olmayanları işaretler.
"""

from __future__ import annotations

import re

PENALTY_SOURCES = ("TCK",)
MAX_SENTENCE_CHARS = 170
MAX_LINES_PER_ARTICLE = 5
MAX_TABLE_CHARS = 1800

_KEYWORDS = re.compile(
    r"hapis|adl[îi] para|artırılır|indirilir|şik[âa]yet|cezalandırılır|hükmolunur|ceza verilmez",
    re.IGNORECASE,
)
_AMENDMENT = re.compile(r"\((?:Ek|Değişik|Mülga|İptal)[^)]*\)", re.IGNORECASE)
_FOOTNOTE = re.compile(r"(?<=[a-zçğıöşü,.;)])\d{1,3}(?=\s|$)")
_FIKRA = re.compile(r"(?:^|\n|\s)\((\d{1,2})\)\s")


def _clean(text: str) -> str:
    text = _AMENDMENT.sub("", text)
    text = re.sub(r"\(\.\.\.\)\s*\d{0,3}", "", text)
    text = _FOOTNOTE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _body(document: str) -> str:
    """Embedding başlığını ("... Madde X / Başlık / Konu") at, kanun metnini döndür."""
    parts = document.split("\n\n", 1)
    if len(parts) == 2 and parts[0].count("\n") <= 3 and "Madde" in parts[0]:
        return parts[1]
    return document


def _fikralar(text: str) -> list[tuple[str, str]]:
    matches = list(_FIKRA.finditer(text))
    if not matches:
        return [("", text)]
    result = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result.append((match.group(1), text[match.end():end]))
    return result


def _penalty_sentences(fikra_text: str) -> list[str]:
    sentences = re.split(r"(?<=[.;])\s+(?=[A-ZÇĞİÖŞÜ(])", _clean(fikra_text))
    picked = []
    for sentence in sentences:
        if not _KEYWORDS.search(sentence):
            continue
        if len(sentence) > MAX_SENTENCE_CHARS:
            sentence = "…" + sentence[-MAX_SENTENCE_CHARS:].split(" ", 1)[-1]
        picked.append(sentence)
    return picked


def build_penalty_index(records: dict) -> dict[str, list[str]]:
    """ChromaDB kayıtlarından {"TCK 86": ["86/1: ...", "86/2: ..."]} indeksi kurar.

    Parçalanmış (chunk) maddeler sırayla birleştirilir; örtüşmeden doğan
    tekrar cümleler elenir.
    """
    grouped: dict[str, list[tuple[int, str]]] = {}
    for doc, meta in zip(records.get("documents", []), records.get("metadatas", [])):
        meta = meta or {}
        source = meta.get("kaynak_kodu") or "TCK"
        number = str(meta.get("birim_no") or meta.get("madde_no") or "")
        if source not in PENALTY_SOURCES or not number or meta.get("mulga") or not doc:
            continue
        grouped.setdefault(f"{source} {number}", []).append((int(meta.get("chunk_no") or 1), doc))

    index: dict[str, list[str]] = {}
    for key, chunks in grouped.items():
        number = key.split(" ", 1)[1]
        text = " ".join(_body(doc) if i == 0 else doc for i, (_, doc) in enumerate(sorted(chunks)))
        lines, seen = [], set()
        for fikra_no, fikra_text in _fikralar(text):
            for sentence in _penalty_sentences(fikra_text):
                if sentence in seen:
                    continue
                seen.add(sentence)
                label = f"{number}/{fikra_no}" if fikra_no else number
                lines.append(f"{label}: {sentence}")
        if lines:
            index[key] = lines
    return index


def penalty_table(refs: list[str], index: dict[str, list[str]]) -> str:
    """Bulunan maddeler için kısa ceza tablosu; yoksa boş metin."""
    lines, used = [], 0
    for ref in dict.fromkeys(refs):
        for line in index.get(ref, [])[:MAX_LINES_PER_ARTICLE]:
            entry = f"- {ref.split(' ', 1)[0]} {line}"
            if used + len(entry) > MAX_TABLE_CHARS:
                continue
            lines.append(entry)
            used += len(entry)
    if not lines:
        return ""
    return "--- CEZA VE ŞİKÂYET TABLOSU (kanun metninden, fıkra bazında) ---\n" + "\n".join(lines) + "\n\n"


# --- Ceza aralığı doğrulaması ---
_NUMBERS = {
    "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8,
    "dokuz": 9, "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50,
}
_NUM = r"(?:\d+|" + "|".join(sorted(_NUMBERS, key=len, reverse=True)) + r")"
_AMOUNT = rf"(?:{_NUM}\s+)+(?:yıl|ay|gün)(?:\s+(?:{_NUM}\s+)+(?:yıl|ay|gün))?"
_RANGE = re.compile(
    rf"(?<![\wçğıöşü])({_AMOUNT})(?:dan|den|tan|ten)\s+({_AMOUNT})(?:a|e|ya|ye)\s+kadar",
    re.IGNORECASE,
)
_UNIT_DAYS = {"yıl": 360, "ay": 30, "gün": 1}


def _to_days(amount: str) -> int:
    total, current = 0, 0
    for token in re.findall(rf"{_NUM}|yıl|ay|gün", amount.lower()):
        if token in _UNIT_DAYS:
            total += (current or 1) * _UNIT_DAYS[token]
            current = 0
        else:
            current += int(token) if token.isdigit() else _NUMBERS[token]
    return total


def find_ranges(text: str) -> list[tuple[str, tuple[int, int]]]:
    """Metindeki ceza aralıkları: [("üç aydan iki yıla kadar", (90, 720)), ...]"""
    normalized = text.replace(" ", " ")
    return [
        (match.group(0), (_to_days(match.group(1)), _to_days(match.group(2))))
        for match in _RANGE.finditer(normalized)
    ]


def unsupported_ranges(answer: str, sources: str) -> list[str]:
    """Yanıtta geçen ama kaynak metinlerde karşılığı olmayan aralıklar."""
    allowed = {value for _, value in find_ranges(sources)}
    missing = []
    for phrase, value in find_ranges(answer):
        if value not in allowed and phrase not in missing:
            missing.append(phrase)
    return missing


def range_warning(missing: list[str]) -> str:
    if not missing:
        return ""
    listed = "; ".join(f"“{phrase}”" for phrase in missing[:5])
    return (
        "\n\n> ⚠️ Otomatik kontrol: Şu ceza aralıkları verilen kaynak metinlerde bulunamadı: "
        f"{listed}. Bu aralıkları ilgili kanun maddesinin güncel metninden doğrulayın."
    )
