#!/usr/bin/env python3
"""Compare published, task-aware single, and task-aware multi-query retrieval."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines.strong_rag_baseline.indexer import IndexedCorpus, build_index
from baselines.strong_rag_baseline.queries import build_queries, legacy_query
from baselines.strong_rag_baseline.retriever import BM25Index, ScoredChunk


def _metrics(hits: list[ScoredChunk], corpus: IndexedCorpus, cutoff: str) -> dict:
    rendered = []
    cutoff_violations = 0
    invalid_spans = 0
    for hit in hits:
        chunk = hit.chunk
        doc_text = corpus.doc_texts.get(chunk.doc_id, "")
        resolved = doc_text[chunk.span_start : chunk.span_end] == chunk.text
        eligible = (
            isinstance(chunk.doc_date, str)
            and chunk.doc_date <= cutoff
            and resolved
        )
        cutoff_violations += int(not isinstance(chunk.doc_date, str) or chunk.doc_date > cutoff)
        invalid_spans += int(not resolved)
        rendered.append(
            {
                "doc_id": chunk.doc_id,
                "doc_date": chunk.doc_date,
                "span_start": chunk.span_start,
                "span_end": chunk.span_end,
                "score": hit.score,
                "citation_resolves": resolved,
                "cutoff_eligible": eligible,
                "text": chunk.text,
            }
        )
    return {
        "retrieved": rendered,
        "document_diversity": len({hit.chunk.doc_id for hit in hits}),
        "span_diversity": len(
            {(hit.chunk.doc_id, hit.chunk.span_start, hit.chunk.span_end) for hit in hits}
        ),
        "cutoff_violations": cutoff_violations,
        "invalid_spans": invalid_spans,
    }


def run_ablation(task: dict, corpus: IndexedCorpus, *, top_k: int) -> dict:
    index = BM25Index(corpus.chunks, task["cutoff_date"])
    rows = []
    for entity in task.get("entities") or []:
        task_queries = build_queries(task, entity)
        variants = {
            "official_strong": ([legacy_query(entity)], "single"),
            "task_single": (task_queries[:1], "single"),
            "task_multi_rrf": (task_queries, "rrf"),
            "task_multi_max_normalized": (task_queries, "max_normalized"),
        }
        comparisons = {}
        for name, (queries, fusion) in variants.items():
            started = time.perf_counter()
            if fusion == "single":
                hits = index.search(queries[0], top_k) if queries else []
            else:
                hits = index.search_multi(queries, top_k, fusion=fusion)
            metrics = _metrics(hits, corpus, task["cutoff_date"])
            metrics["queries"] = queries
            metrics["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            comparisons[name] = metrics
        rows.append({"entity_id": entity.get("entity_id"), "variants": comparisons})
    return {
        "task_id": task.get("task_id"),
        "target_type": (task.get("target") or {}).get("type"),
        "top_k": top_k,
        "entities": rows,
        "prediction_accuracy_measured": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    task = json.loads((args.unit / "task.json").read_text(encoding="utf-8"))
    corpus = build_index(args.unit / "corpus")
    result = run_ablation(task, corpus, top_k=args.top_k)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
