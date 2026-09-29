from __future__ import annotations

import json
from pathlib import Path

from baselines.strong_rag_baseline.indexer import build_index
from scripts.retrieval_ablation import run_ablation

UNIT = Path(__file__).resolve().parents[1] / "units" / "t4-EXAMPLE-eps-beat"


def test_ablation_reports_all_variants_and_invariants() -> None:
    task = json.loads((UNIT / "task.json").read_text(encoding="utf-8"))
    result = run_ablation(task, build_index(UNIT / "corpus"), top_k=4)

    [entity] = result["entities"]
    assert set(entity["variants"]) == {
        "official_strong",
        "task_single",
        "task_multi_rrf",
        "task_multi_max_normalized",
    }
    for variant in entity["variants"].values():
        assert variant["cutoff_violations"] == 0
        assert variant["invalid_spans"] == 0
        assert variant["span_diversity"] == len(variant["retrieved"])
    assert result["prediction_accuracy_measured"] is False
