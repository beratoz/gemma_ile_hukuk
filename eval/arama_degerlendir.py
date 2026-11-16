"""Arama (retrieval) ölçümü: eval/vakalar.json'daki beklenen maddeler bulunuyor mu?

Kullanım (proje kökünden, FastAPI kapalıyken veya açıkken):
    python eval/arama_degerlendir.py          # LLM'siz: soru + ontoloji (halk dili) kavramları
    python eval/arama_degerlendir.py --llm    # Aşama 1'i LM Studio ile çalıştırır (gerçek pipeline'a daha yakın)

"beklenen": her grup için en az bir maddenin ilk N_RESULTS içinde olması gerekir (zorunlu).
"ek": olması iyi olan maddeler; skora ayrı raporlanır.
Hukuki doğruluğu değil, modele doğru kaynağın gidip gitmediğini ölçer.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

import main  # noqa: E402  (.env doğrulaması ve yardımcı fonksiyonlar)
from penalties import build_penalty_index, penalty_table  # noqa: E402
from retrieval import BM25Index, _retrieve_articles  # noqa: E402


def covered(groups, refs):
    return [any(key in refs for key in group) for group in groups]


async def run(use_llm: bool):
    cases = json.loads((ROOT / "eval" / "vakalar.json").read_text(encoding="utf-8"))
    model = SentenceTransformer(main.EMBEDDING_MODEL_NAME, device="cpu", local_files_only=True)
    collection = chromadb.PersistentClient(path=main.CHROMA_DB_PATH).get_collection(main.COLLECTION_NAME)
    records = collection.get(where={"mulga": False}, include=["documents", "metadatas"])
    lexical, penalties = BM25Index(records), build_penalty_index(records)
    halk = {}
    if main.ONTOLOGY_PATH and os.path.isfile(main.ONTOLOGY_PATH):
        halk = main._build_halk_dili_index(json.loads(Path(main.ONTOLOGY_PATH).read_text(encoding="utf-8")))
    llm = AsyncOpenAI(base_url=main.LM_STUDIO_BASE_URL, api_key=main.LM_STUDIO_API_KEY, timeout=120) if use_llm else None

    required_hits = required_total = extra_hits = extra_total = 0
    for case in cases:
        if llm:
            concepts, _ = await main._extract_concepts(case["soru"], llm, halk, allow_clarification=False)
        else:
            concepts = main._expand_with_halk_dili(case["soru"], halk)
        refs, _, _ = _retrieve_articles(case["soru"], model, collection, main.N_RESULTS, concepts, lexical)
        required = covered(case["beklenen"], refs)
        extra = covered(case.get("ek", []), refs)
        required_hits += sum(required)
        required_total += len(required)
        extra_hits += sum(extra)
        extra_total += len(extra)
        table = bool(penalty_table(refs, penalties))
        missing = [" / ".join(group) for group, ok in zip(case["beklenen"], required) if not ok]
        mark = "✓" if all(required) else "✗"
        print(f"{mark} {case['id']:<26} tablo={'var' if table else 'yok':<3} eksik={missing or '-'}")
        print(f"    kavramlar={concepts}")
        print(f"    bulunan={refs}")
    if llm:
        await llm.close()
    print("\n" + "=" * 70)
    print(f"Zorunlu kapsama: {required_hits}/{required_total} = {required_hits / max(1, required_total):.0%}")
    if extra_total:
        print(f"Ek (olması iyi) kapsama: {extra_hits}/{extra_total} = {extra_hits / max(1, extra_total):.0%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Kavram çıkarmayı LM Studio ile yap")
    asyncio.run(run(parser.parse_args().llm))
