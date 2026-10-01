from __future__ import annotations

import math
import importlib.resources as resources
import json

import jsonschema
import pytest

from baselines.strong_rag_baseline.agent import EntityResult
from baselines.strong_rag_baseline.indexer import Chunk, IndexedCorpus
from baselines.strong_rag_baseline.formatter import build_answer
from baselines.strong_rag_baseline.safety import (
    ContractError,
    preflight,
    sanitize_results,
    task_target_type,
)


def corpus() -> IndexedCorpus:
    text = "Entity guidance supports a possible future outcome."
    chunk = Chunk("DOC", "2026-01-01", 0, len(text), text)
    return IndexedCorpus(
        [chunk],
        {"DOC": text},
        {"DOC": "2026-01-01"},
        doc_entity_ids={"DOC": ("A", "B")},
        labels_present=True,
    )


def task(target_type: str) -> dict:
    target = {"name": "future_metric", "type": target_type}
    if target_type == "classification":
        target["labels"] = ["yes", "no"]
    return {
        "task_id": f"synthetic-{target_type}",
        "schema_version": "3",
        "target": target,
        "cutoff_date": "2026-02-01",
        "interval_level": 0.9,
        "entities": [
            {"entity_id": "A", "future_metric_estimate": 2.5},
            {"entity_id": "B", "feature": 4.0},
        ],
    }


@pytest.mark.parametrize("target_type", ["classification", "regression", "ranking"])
def test_missing_results_become_complete_safe_roster(target_type: str) -> None:
    current_task = task(target_type)

    repaired = sanitize_results(current_task, [], corpus())
    answer = {
        "task_id": current_task["task_id"],
        "entity_predictions": [item.prediction for item in repaired],
    }

    preflight(current_task, answer, corpus())
    assert [row["entity_id"] for row in answer["entity_predictions"]] == ["A", "B"]
    assert all(row["claims"] for row in answer["entity_predictions"])
    assert all(
        math.isfinite(row["point_forecast"]) for row in answer["entity_predictions"]
    )
    assert all("rank" not in row for row in answer["entity_predictions"])
    if target_type == "classification":
        assert all(row["label"] == "yes" for row in answer["entity_predictions"])
    else:
        assert all("label" not in row for row in answer["entity_predictions"])

    official = build_answer(current_task, repaired, corpus())
    schema_path = (
        resources.files("qfbench2_common") / "schemas" / "analysis.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(official)


def test_bad_numbers_claims_and_duplicate_results_are_repaired() -> None:
    current_task = task("regression")
    bad = EntityResult(
        prediction={
            "entity_id": "A",
            "label": None,
            "point_forecast": float("nan"),
            "interval": {"level": 0.5, "lo": float("inf"), "hi": -1},
            "claims": [
                {"doc_id": "UNKNOWN", "span_start": 0, "span_end": 1, "claim": "x"}
            ],
        },
        dropped_claims=0,
        model_raw="bad",
    )

    repaired = sanitize_results(current_task, [bad, bad], corpus())

    assert len(repaired) == 2
    assert repaired[0].prediction["point_forecast"] == 2.5
    assert repaired[0].prediction["claims"][0]["doc_id"] == "DOC"
    assert repaired[0].prediction["interval"]["level"] == 0.9


def test_preflight_rejects_partial_optional_rank() -> None:
    current_task = task("ranking")
    repaired = sanitize_results(current_task, [], corpus())
    repaired[0].prediction["rank"] = 1
    answer = {
        "task_id": current_task["task_id"],
        "entity_predictions": [item.prediction for item in repaired],
    }

    with pytest.raises(ContractError, match="complete permutation"):
        preflight(current_task, answer, corpus())


def test_no_pre_cutoff_evidence_fails_closed() -> None:
    current_task = task("classification")
    late = corpus()
    late.doc_dates["DOC"] = "2026-03-01"

    with pytest.raises(ContractError, match="no dated pre-cutoff"):
        sanitize_results(current_task, [], late)


def test_top_level_target_type_is_supported_and_preferred() -> None:
    current_task = task("classification")
    current_task["target_type"] = "ranking"
    assert task_target_type(current_task) == "ranking"

    answer = build_answer(current_task, [], corpus())
    assert answer["target_type"] == "ranking"
    assert all("label" not in row for row in answer["entity_predictions"])
