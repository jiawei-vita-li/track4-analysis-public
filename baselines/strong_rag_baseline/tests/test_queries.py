from __future__ import annotations

from baselines.strong_rag_baseline.indexer import Chunk
from baselines.strong_rag_baseline.queries import build_queries
from baselines.strong_rag_baseline.retriever import BM25Index


def test_queries_derive_from_unknown_task_semantics_without_earnings_bias() -> None:
    task = {
        "target": {"name": "reservoir_level", "type": "regression"},
        "prompt": "Forecast next-month reservoir storage from hydrology reports.",
    }
    entity = {
        "entity_id": "DAM-7",
        "name": "North Basin",
        "region": "alpine",
        "snowpack_index": 1.2,
    }

    queries = build_queries(task, entity)

    assert 3 <= len(queries) <= 5
    assert any("reservoir_level" in query for query in queries)
    assert any("hydrology" in query for query in queries)
    assert all("earnings" not in query for query in queries)


def test_multi_query_rrf_is_deterministic_and_deduplicated() -> None:
    chunks = [
        Chunk("A", "2026-01-01", 0, 20, "reservoir storage snowpack"),
        Chunk("B", "2026-01-01", 0, 18, "hydrology river flow"),
        Chunk("C", "2026-01-01", 0, 16, "unrelated boilerplate"),
    ]
    index = BM25Index(chunks, "2026-02-01")
    queries = ["reservoir snowpack", "hydrology reservoir"]

    first = index.search_multi(queries, 3, fusion="rrf")
    second = index.search_multi(queries, 3, fusion="rrf")

    keys = [(hit.chunk.doc_id, hit.chunk.span_start, hit.chunk.span_end) for hit in first]
    assert keys == [(hit.chunk.doc_id, hit.chunk.span_start, hit.chunk.span_end) for hit in second]
    assert len(keys) == len(set(keys))
    assert keys[0][0] == "A"
