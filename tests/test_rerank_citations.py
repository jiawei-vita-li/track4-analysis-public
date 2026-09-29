from __future__ import annotations

import json
from pathlib import Path

from baselines.strong_rag_baseline.indexer import build_index
from scripts.rerank_citations import rerank_answer

UNIT = Path(__file__).resolve().parents[1] / "units" / "t4-EXAMPLE-eps-beat"


class GuidanceJudge:
    def entail(self, premise: str, hypothesis: str) -> float:
        assert "eps outcome" in hypothesis
        return 0.9 if "provided the following guidance" in premise else 0.1


def test_reranker_keeps_prediction_fixed_and_selects_best_span() -> None:
    task = json.loads((UNIT / "task.json").read_text(encoding="utf-8"))
    answer = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "phase1"
            / "strong-mock"
            / "answer.json"
        ).read_text(encoding="utf-8")
    )
    original_prediction = {
        key: value for key, value in answer["entity_predictions"][0].items() if key != "claims"
    }

    reranked, trace = rerank_answer(
        task, answer, build_index(UNIT / "corpus"), GuidanceJudge(), candidate_k=10
    )

    row = reranked["entity_predictions"][0]
    assert {key: value for key, value in row.items() if key != "claims"} == original_prediction
    [claim] = row["claims"]
    selected_text = build_index(UNIT / "corpus").doc_texts[claim["doc_id"]][
        claim["span_start"] : claim["span_end"]
    ]
    assert "provided the following guidance" in selected_text
    assert trace["entities"][0]["canonical_hypothesis"].startswith("The eps outcome")
