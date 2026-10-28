"""Çekirdek regresyonları: python -m unittest -v test_main

Kütüphaneler varsa gerçek modülü ve ASGI uçlarını, yoksa saf çekirdeği AST ile
yükler. Sunucuyu/modeli başlatmaz, paket veya model indirmez. ChromaDB/LM Studio
sınırları sahte nesnelerle temsil edilir; hukuki doğruluğu ölçmez.
"""

import ast
import asyncio
import json
import importlib.util
import math
import os
import re
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class Response:
    def __init__(self, **data):
        self.data = data

    def model_dump(self):
        return self.data


def load_core():
    modules = ("fastapi", "chromadb", "openai", "sentence_transformers", "dotenv")
    if all(importlib.util.find_spec(name) is not None for name in modules):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["ANONYMIZED_TELEMETRY"] = "False"
        import main
        return vars(main)
    tree = ast.parse(Path(__file__).with_name("main.py").read_text(encoding="utf-8"))
    names = {
        "_search_tokens", "_article_key", "_explicit_article_refs", "BM25Index", "_retrieve_articles",
        "_format_retrieved_hit", "_parse_concepts", "_analysis_events", "_sse_events",
        "_extract_concepts", "_expand_with_halk_dili", "_llm_chat", "_check_missing_concepts",
    }
    prompts = {"TERCUMAN_PROMPTU", "SISTEM_PROMPTU", "MISSING_CHECK_PROMPT"}
    nodes = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in prompts for target in node.targets):
            nodes.append(node)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id in prompts:
            nodes.append(node)
    namespace = {
        "asyncio": asyncio, "json": json, "math": math, "re": re,
        "Counter": Counter, "defaultdict": defaultdict,
        "AnalyzeResponse": Response, "N_RESULTS": 3, "LM_MODEL_NAME": "local-test",
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), "main.py", "exec"), namespace)
    return namespace


core = load_core()


def records():
    return {
        "ids": ["tck-125-c1", "tck-125-c2", "tck-141", "old"],
        "documents": ["Hakaret ve şeref", "Hakaret ikinci parça", "Hırsızlık taşınır mal", "Hırsızlık eski hüküm"],
        "metadatas": [
            {"kaynak_kodu": "TCK", "birim_no": "125", "baslik": "Hakaret", "mulga": False},
            {"kaynak_kodu": "TCK", "birim_no": "125", "baslik": "Hakaret", "mulga": False},
            {"kaynak_kodu": "TCK", "birim_no": "141", "baslik": "Hırsızlık", "mulga": False},
            {"kaynak_kodu": "TCK", "birim_no": "999", "mulga": True},
        ],
    }


class Collection:
    def query(self, **kwargs):
        assert kwargs["where"] == {"mulga": False}
        data = records()
        # Anlamsal kanal ilgili hırsızlık maddesini kaçırıyor.
        return {key: [data[key][:2]] for key in ("ids", "documents", "metadatas")}


class Embedding:
    def encode(self, text, **kwargs):
        assert text.startswith("query: ")
        return SimpleNamespace(tolist=lambda: [0.1, 0.2])


class SearchTests(unittest.TestCase):
    def test_turkish_normalization(self):
        self.assertEqual(core["_search_tokens"]("İŞYERİ HIRSIZLIK"), ["işyeri", "hirsizlik"])

    def test_lexical_recovers_missing_dense_result_and_filters_repealed(self):
        index = core["BM25Index"](records())
        hits = index.search("hırsızlık", 8)
        self.assertEqual([hit["doc_id"] for hit in hits], ["tck-141"])
        self.assertEqual(index.search("bilinmeyenkelime", 8), [])
        self.assertEqual(len(index.hits), 3)

    def test_hybrid_chunk_dedup_and_source_budget(self):
        refs, text, metas = core["_retrieve_articles"](
            "hırsızlık", Embedding(), Collection(), 2, [], core["BM25Index"](records()),
        )
        self.assertEqual(set(refs), {"TCK 125", "TCK 141"})
        self.assertEqual(len(metas), 2)
        self.assertIn("Hırsızlık", text)

    def test_explicit_article_is_prioritized(self):
        refs, _, _ = core["_retrieve_articles"](
            "TCK Madde 141", Embedding(), Collection(), 2, ["hakaret"], core["BM25Index"](records()),
        )
        self.assertEqual(refs[0], "TCK 141")
        self.assertEqual(len(refs), len(set(refs)))
        self.assertEqual(core["_explicit_article_refs"]("TCK 141/1"), {"TCK 141"})

    def test_empty_corpus_and_dense_fallback(self):
        empty = core["BM25Index"]({"ids": [], "documents": [], "metadatas": []})
        self.assertEqual(empty.search("hakaret", 3), [])
        refs, _, _ = core["_retrieve_articles"]("hakaret", Embedding(), Collection(), 3)
        self.assertEqual(refs, ["TCK 125"])

    def test_lexical_ranking_returns_unique_articles(self):
        hits = core["BM25Index"](records()).search("hakaret", 6)
        self.assertEqual([hit["display_key"] for hit in hits], ["TCK 125"])
        self.assertEqual(core["BM25Index"](records()).search("hakaret", 0), [])

    def test_clarification_format_limit_and_one_question(self):
        parse = core["_parse_concepts"]
        raw = json.dumps({"kavramlar": ["hakaret"], "ek_soru": "Ne söyledi? Nerede söyledi?"})
        self.assertEqual(parse(raw, True), (["hakaret"], "Ne söyledi?"))
        self.assertEqual(parse(raw, False), (["hakaret"], None))
        raw = json.dumps({"kavramlar": [], "ek_soru": "x" * 500})
        self.assertEqual(len(parse(raw, True)[1]), 240)
        self.assertEqual(parse('{"kavramlar": [', True), ([], None))
        self.assertEqual(parse("hakaret, tehdit", True), (["hakaret", "tehdit"], None))


def completion(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class Stream:
    def __init__(self, truncated=False, slow=False):
        self.closed = False
        self.truncated = truncated
        self.slow = slow
        self.waiting = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def __aiter__(self):
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Türkçe yanıt"), finish_reason=None)])
        if self.slow:
            self.waiting.set()
            await asyncio.Event().wait()
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="length" if self.truncated else "stop")])


def state_for(stream=None, clarification=None):
    raw = json.dumps({"kavramlar": ["hakaret"], "ek_soru": clarification})
    create = AsyncMock(side_effect=[completion(raw), completion("YOK"), stream or Stream()])
    state = SimpleNamespace(
        analysis_lock=asyncio.Semaphore(1), halk_dili_index={},
        embedding_model=Embedding(), collection=Collection(),
        lexical_index=core["BM25Index"](records()),
        llm_client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )
    return state, create


def request(answered=False):
    return SimpleNamespace(soru="Bir olay anlatıyorum", ek_soru_yanitlandi=answered,
                           ek_bilgi="",
                           analysis_question=lambda: "Bir olay anlatıyorum")


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_article_question_does_not_guess_offense(self):
        state, create = state_for()
        concepts, clarification = await core["_extract_concepts"](
            "TCK Madde 125 neyi düzenler?", state.llm_client,
        )
        self.assertEqual(concepts, [])
        self.assertIsNone(clarification)
        create.assert_not_awaited()

    async def test_stream_progress_tokens_and_final_result(self):
        stream = Stream()
        state, create = state_for(stream)
        events = [event async for event in core["_analysis_events"](request(), state)]
        types = [event["type"] for event in events]
        self.assertLess(types.index("progress"), types.index("token"))
        self.assertEqual(events[-1]["mutalaa"], "Türkçe yanıt")
        self.assertEqual(events[-1]["type"], "result")
        self.assertTrue(stream.closed)
        self.assertFalse(state.analysis_lock.locked())
        self.assertTrue(create.call_args.kwargs["stream"])
        self.assertEqual(create.call_args.kwargs["max_tokens"], 4000)

    async def test_clarification_uses_existing_call_and_stops_analysis(self):
        state, create = state_for(clarification="Size ne yaptı?")
        events = [event async for event in core["_analysis_events"](request(), state)]
        self.assertEqual(create.await_count, 1)
        self.assertEqual(events[-1]["ek_soru"], "Size ne yaptı?")
        self.assertNotIn("token", [event["type"] for event in events])

    async def test_answering_or_skipping_prevents_second_clarification(self):
        state, create = state_for(clarification="Tekrar soru?")
        events = [event async for event in core["_analysis_events"](request(answered=True), state)]
        self.assertEqual(create.await_count, 3)
        self.assertEqual(events[-1]["type"], "result")
        self.assertFalse(events[-1].get("ek_soru"))

    async def test_skipped_vague_question_does_not_invent_analysis(self):
        state, create = state_for()
        create.side_effect = [completion('{"kavramlar": [], "ek_soru": null}')]
        events = [event async for event in core["_analysis_events"](request(answered=True), state)]
        self.assertEqual(create.await_count, 1)
        self.assertEqual(events[-1]["type"], "result")
        self.assertEqual(events[-1]["bulunan_madde_numaralari"], [])
        self.assertIn("somut eylem", events[-1]["mutalaa"])
        self.assertFalse(events[-1].get("ek_soru"))

    async def test_output_limit_produces_error_not_success(self):
        state, _ = state_for(Stream(truncated=True))
        events = [event async for event in core["_analysis_events"](request(), state)]
        self.assertEqual(events[-1]["type"], "error")
        self.assertNotIn("result", [event["type"] for event in events])

    async def test_disconnect_closes_model_and_releases_lock(self):
        stream = Stream(slow=True)
        state, _ = state_for(stream)
        events = core["_sse_events"](request(), state)
        while True:
            wire = await anext(events)
            if '"type": "token"' in wire:
                break
        pending = asyncio.create_task(anext(events))
        await asyncio.wait_for(stream.waiting.wait(), timeout=2)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        await events.aclose()
        self.assertTrue(stream.closed)
        self.assertFalse(state.analysis_lock.locked())

    async def test_service_error_is_sanitized(self):
        state, create = state_for()
        create.side_effect = RuntimeError("PRIVATE QUESTION CONTENT")
        events = [event async for event in core["_analysis_events"](request(), state)]
        self.assertEqual(events[-1]["type"], "error")
        self.assertNotIn("PRIVATE", json.dumps(events))
        self.assertFalse(state.analysis_lock.locked())


@unittest.skipUnless("app" in core, "ASGI testleri için proje kütüphaneleri gerekli")
class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_endpoint_schema_and_pipeline(self):
        import httpx
        state, _ = state_for()
        with patch.object(core["app"], "state", state):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=core["app"]), base_url="http://test") as client:
                response = await client.post("/api/v1/analyze", json={"soru": "Örnek olay anlatımı"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mutalaa"], "Türkçe yanıt")

    async def test_sse_endpoint_protocol(self):
        import httpx
        state, _ = state_for()
        with patch.object(core["app"], "state", state):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=core["app"]), base_url="http://test") as client:
                response = await client.post("/api/v1/analyze/stream", json={"soru": "Örnek olay anlatımı"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[0]["type"], "progress")
        self.assertEqual(events[-1]["type"], "result")
        self.assertEqual(events[-1]["mutalaa"], "Türkçe yanıt")

    async def test_validation_rejects_invalid_question_before_model_call(self):
        import httpx
        state, create = state_for()
        with patch.object(core["app"], "state", state):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=core["app"]), base_url="http://test") as client:
                response = await client.post("/api/v1/analyze/stream", json={"soru": ""})
        self.assertEqual(response.status_code, 422)
        create.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
