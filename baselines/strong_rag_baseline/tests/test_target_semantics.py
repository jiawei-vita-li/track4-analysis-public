"""Compiler and metamorphic tests for deterministic target semantics."""

from __future__ import annotations

import copy
import json

from baselines.strong_rag_baseline.indexer import Chunk, IndexedCorpus
from baselines.strong_rag_baseline.retriever import BM25Index
from baselines.strong_rag_baseline.target_semantics import (
    compile_target_semantics,
    consistency_diagnostics,
)
from baselines.strong_rag_baseline.task_context import build_task_context
from baselines.strong_rag_baseline.task_predictor import (
    TASK_SYSTEM_PROMPT,
    build_task_prompt,
)


def _task(target_type: str = "regression") -> dict:
    target = {"name": "future_value", "type": target_type}
    if target_type == "classification":
        target["labels"] = ["high", "low"]
    return {
        "task_id": "semantic-synthetic",
        "prompt": "Predict the next outcome.",
        "cutoff_date": "2026-01-01",
        "interval_level": 0.9,
        "target": target,
        "entities": [
            {"entity_id": "A", "irrelevant_number": 7.0},
            {"entity_id": "B", "irrelevant_number": 9.0},
        ],
    }


def test_explicit_unit_and_missing_unit() -> None:
    task = _task()
    task["target"]["unit"] = "basis points"
    field = compile_target_semantics(task).explicit_unit
    assert (field.value, field.source, field.status) == (
        "basis points",
        "target.unit",
        "resolved",
    )
    del task["target"]["unit"]
    field = compile_target_semantics(task).explicit_unit
    assert field.value is None and field.source is None and field.status == "unknown"


def test_explicit_horizon_and_missing_horizon() -> None:
    task = _task()
    task["target"]["forecast_horizon"] = "next 30 calendar days"
    field = compile_target_semantics(task).forecast_horizon
    assert field.value == "next 30 calendar days"
    assert field.source == "target.forecast_horizon"
    del task["target"]["forecast_horizon"]
    assert compile_target_semantics(task).forecast_horizon.status == "unknown"


def test_classification_labels_are_order_independent() -> None:
    task = _task("classification")
    first = compile_target_semantics(task)
    task["target"]["labels"].reverse()
    second = compile_target_semantics(task)
    assert first.legal_labels == second.legal_labels
    assert first.legal_labels.value == ["high", "low"]


def test_label_assertions_preserve_text_and_provenance() -> None:
    task = _task("classification")
    task["target"]["label_assertions"] = {
        "high": "the future value will be above its current value",
        "low": "the future value will not be above its current value",
    }
    semantics = compile_target_semantics(task)
    assert [item.label for item in semantics.label_assertions] == ["high", "low"]
    assert semantics.label_assertions[0].source == "target.label_assertions.high"
    assert not any(item.executable for item in semantics.label_assertions)
    assert semantics.numeric_thresholds.status == "unknown"


def test_only_exact_point_expression_is_executable() -> None:
    task = _task("classification")
    task["target"]["label_assertions"] = {
        "high": {
            "text": "high iff point exceeds 0.5",
            "expression": "point_forecast > 0.5",
        },
        "low": "probably lower",
    }
    high, low = compile_target_semantics(task).label_assertions
    assert high.executable and high.operator == ">" and high.threshold == 0.5
    assert not low.executable and low.expression is None


def test_regression_quantity_comes_from_target_name() -> None:
    task = _task("regression")
    semantics = compile_target_semantics(task)
    assert semantics.target_name.value == "future_value"
    assert semantics.target_name.source == "target.name"


def test_ranking_direction_requires_explicit_trusted_wording() -> None:
    task = _task("ranking")
    task["prompt"] = "Rank 1 = largest increase in the target quantity."
    direction = compile_target_semantics(task).ranking_direction
    assert direction.value == "higher point_forecast ranks first"
    assert direction.source.startswith("task.prompt:")


def test_unrelated_numeric_features_do_not_become_target_semantics() -> None:
    task = _task("regression")
    semantics = compile_target_semantics(task)
    assert semantics.point_meaning.status == "unknown"
    assert semantics.numeric_thresholds.status == "unknown"


def test_unknown_and_ambiguous_metadata_are_not_guessed() -> None:
    task = _task()
    task["prompt"] = "Predict a rate or a ratio for some later outcome."
    semantics = compile_target_semantics(task)
    assert semantics.explicit_unit.status == "unknown"
    assert semantics.forecast_horizon.status == "unknown"
    assert semantics.point_meaning.status == "unknown"


def test_conflicting_structured_units_are_unresolved() -> None:
    task = _task()
    task["target"]["unit"] = "percent"
    for entity in task["entities"]:
        entity["unit"] = "basis points"
    semantics = compile_target_semantics(task)
    assert semantics.explicit_unit.status == "conflict"
    assert semantics.explicit_unit.value is None
    assert "explicit_unit" in semantics.conflicts


def test_entity_roster_permutation_does_not_change_semantics() -> None:
    task = _task()
    task["target"]["unit"] = "percent"
    first = compile_target_semantics(task)
    task["entities"].reverse()
    assert compile_target_semantics(task) == first


def test_conflicting_entity_units_are_roster_order_independent() -> None:
    task = _task()
    task["entities"][0]["unit"] = "percent"
    task["entities"][1]["unit"] = "basis points"
    first = compile_target_semantics(task)
    task["entities"].reverse()
    second = compile_target_semantics(task)
    assert first == second
    assert first.explicit_unit.status == "conflict"


def test_irrelevant_feature_value_and_name_do_not_change_semantics() -> None:
    task = _task()
    first = compile_target_semantics(task)
    task["entities"][0]["irrelevant_number"] = 1000000
    task["entities"][0]["renamed_irrelevant"] = task["entities"][0].pop(
        "irrelevant_number"
    )
    assert compile_target_semantics(task) == first


def test_evidence_text_and_unrelated_numeric_column_do_not_change_semantics() -> None:
    task = _task()
    first = compile_target_semantics(task)
    task["evidence_text"] = "post-cutoff-looking text that the compiler must ignore"
    for entity in task["entities"]:
        entity["another_numeric_predictor"] = 42
    assert compile_target_semantics(task) == first


def test_explicit_unit_replacement_and_deletion_follow_trusted_input() -> None:
    task = _task()
    task["target"]["unit"] = "percent"
    assert compile_target_semantics(task).explicit_unit.value == "percent"
    task["target"]["unit"] = "basis points"
    assert compile_target_semantics(task).explicit_unit.value == "basis points"
    del task["target"]["unit"]
    assert compile_target_semantics(task).explicit_unit.status == "unknown"


def test_prompt_keeps_raw_target_and_adds_compiled_semantics() -> None:
    task = _task("ranking")
    task["target"]["unit"] = "percent"
    text = "Target evidence is pre-cutoff."
    chunk = Chunk("DOC", "2025-12-01", 0, len(text), text)
    corpus = IndexedCorpus(
        [chunk],
        {"DOC": text},
        {"DOC": "2025-12-01"},
        doc_entity_ids={"DOC": ("A", "B")},
        labels_present=True,
    ).with_task_table(task)
    context = build_task_context(
        task,
        BM25Index([chunk], task["cutoff_date"]),
        corpus,
        evidence_per_entity=1,
    )
    prompt = build_task_prompt(context, context.cards, include_evidence=True)
    payload, _ = json.JSONDecoder().raw_decode(
        prompt.split("TASK_CONTEXT_JSON:\n", 1)[1]
    )
    assert payload["raw_target"] == task["target"]
    assert payload["compiled_target_semantics"]["explicit_unit"]["value"] == "percent"
    assert "predictor, not automatically a candidate output" in TASK_SYSTEM_PROMPT
    assert "one shared scale" in TASK_SYSTEM_PROMPT


def test_consistency_diagnostics_are_nonfatal_and_explain_violations() -> None:
    task = _task("classification")
    task["target"]["label_assertions"] = {
        "high": {"text": "high", "expression": "point_forecast > 0.5"},
        "low": {"text": "low", "expression": "point_forecast <= 0.5"},
    }
    diagnostics = consistency_diagnostics(
        compile_target_semantics(task),
        [{"entity_id": "A", "label": "low", "point_forecast": 0.8}],
    )
    assert diagnostics["violation_count"] == 1
    assert diagnostics["violations"][0]["kind"] == "point_label_inconsistent"


def test_compiler_is_pure_under_deepcopy() -> None:
    task = _task()
    before = copy.deepcopy(task)
    compile_target_semantics(task)
    assert task == before


def test_every_resolved_or_conflicting_value_has_provenance() -> None:
    task = _task("classification")
    task["target"]["unit"] = "percent"
    task["target"]["label_assertions"] = {
        "high": {"text": "high", "expression": "point_forecast > 0.5"},
        "low": "not executable",
    }
    semantics = compile_target_semantics(task)
    fields = (
        semantics.target_type,
        semantics.target_name,
        semantics.target_description,
        semantics.explicit_unit,
        semantics.forecast_horizon,
        semantics.legal_labels,
        semantics.numeric_thresholds,
        semantics.ranking_direction,
        semantics.point_meaning,
        semantics.point_range,
        semantics.interval_level,
    )
    for field in fields:
        if field.status == "resolved":
            assert field.value is not None and field.source
        elif field.status == "unknown":
            assert field.value is None and field.source is None
        else:
            assert field.value is None and field.source is None
            assert all(candidate.get("source") for candidate in field.candidates)
    assert all(assertion.source for assertion in semantics.label_assertions)
