#!/usr/bin/env python3
"""DEV-TIME citation reranking against the official canonical hypothesis.

This is an experiment/evaluator, not submission-runtime code.  It intentionally
uses the official NLI ensemble to measure the best citation among lexical
candidates while keeping every prediction field fixed.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines.strong_rag_baseline.indexer import IndexedCorpus, build_index
from baselines.strong_rag_baseline.queries import build_queries
from baselines.strong_rag_baseline.retriever import BM25Index
from faithfulness.judge import build_ensemble_judge
from qfbench2_track_analysis.alignment import EntityRoster, align_predictions
from qfbench2_track_analysis.hypothesis import HypothesisSpec, canonical_hypothesis


class Judge(Protocol):
    def entail(self, premise: str, hypothesis: str) -> float: ...


def rerank_answer(
    task: dict,
    answer: dict,
    corpus: IndexedCorpus,
    judge: Judge,
    *,
    candidate_k: int,
) -> tuple[dict, dict]:
    """Keep predictions fixed and replace each claims list with its best NLI candidate."""
    target = task["target"]
    target_type = target["type"]
    interval_level = float(task["interval_level"])
    roster = EntityRoster.from_task(task)
    aligned = align_predictions(
        answer, roster, target_type=target_type, interval_level=interval_level
    )
    spec = HypothesisSpec.from_task(
        task, target_type=target_type, interval_level=interval_level
    )
    index = BM25Index(corpus.chunks, task["cutoff_date"])
    entities = {entity["entity_id"]: entity for entity in task["entities"]}
    output = copy.deepcopy(answer)
    output_rows = {row["entity_id"]: row for row in output["entity_predictions"]}
    traces = []

    for position, entity_id in enumerate(aligned.entity_ids):
        hypothesis = canonical_hypothesis(
            spec,
            entity_id=entity_id,
            label=aligned.pred_labels[position],
            point_forecast=aligned.pred_values[position],
            rank=aligned.ranks[position],
            lo=aligned.lo[position],
            hi=aligned.hi[position],
        )
        queries = build_queries(task, entities[entity_id])
        hits = index.search_multi(queries, candidate_k, fusion="rrf")
        scored = [
            {
                "doc_id": hit.chunk.doc_id,
                "span_start": hit.chunk.span_start,
                "span_end": hit.chunk.span_end,
                "retrieval_score": hit.score,
                "support_score": float(judge.entail(hit.chunk.text, hypothesis)),
                "text": hit.chunk.text,
            }
            for hit in hits
        ]
        scored.sort(
            key=lambda item: (
                -item["support_score"],
                -item["retrieval_score"],
                item["doc_id"],
                item["span_start"],
            )
        )
        if not scored:
            raise RuntimeError(f"{entity_id}: lexical retrieval returned no citation candidates")
        best = scored[0]
        output_rows[entity_id]["claims"] = [
            {
                "doc_id": best["doc_id"],
                "span_start": best["span_start"],
                "span_end": best["span_end"],
                "claim": "Dev-time canonical-hypothesis reranker selected this exact span.",
            }
        ]
        traces.append(
            {
                "entity_id": entity_id,
                "queries": queries,
                "canonical_hypothesis": hypothesis,
                "candidates": scored,
                "selected": {key: best[key] for key in ("doc_id", "span_start", "span_end", "support_score")},
            }
        )
    return output, {"task_id": task["task_id"], "entities": traces}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", type=Path, required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--device", type=int, default=-1)
    args = parser.parse_args()
    task = json.loads((args.unit / "task.json").read_text(encoding="utf-8"))
    answer = json.loads(args.answer.read_text(encoding="utf-8"))
    corpus = build_index(args.unit / "corpus")
    judge = build_ensemble_judge(cache_dir=str(args.cache_dir), device=args.device)
    reranked, trace = rerank_answer(
        task, answer, corpus, judge, candidate_k=args.candidate_k
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.trace.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reranked, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.trace.write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
