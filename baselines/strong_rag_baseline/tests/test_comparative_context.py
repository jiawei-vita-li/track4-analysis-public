"""Construction, safety, metamorphic, and prompt-switch tests for R4."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

from baselines.strong_rag_baseline.cli import _mock_reply, run
from baselines.strong_rag_baseline.client import MockModelClient
from baselines.strong_rag_baseline.comparative_context import (
    compile_comparative_context,
)
from baselines.strong_rag_baseline.indexer import Chunk, IndexedCorpus
from baselines.strong_rag_baseline.retriever import BM25Index
from baselines.strong_rag_baseline.target_semantics import compile_target_semantics
from baselines.strong_rag_baseline.task_context import (
    build_task_context,
    plan_batches,
)
from baselines.strong_rag_baseline.task_predictor import (
    TASK_SYSTEM_PROMPT,
    build_task_prompt,
    task_system_prompt,
)


def _task() -> dict:
    return {
        "task_id": "comparative-synthetic",
        "prompt": "Predict the next outcome.",
        "cutoff_date": "2026-01-01",
        "interval_level": 0.9,
        "target": {"name": "future_value", "type": "regression"},
        "entities": [
            {"entity_id": "C", "signal": 30.0, "unit": "percent", "sector": "z"},
            {"entity_id": "A", "signal": 10.0, "unit": "percent", "sector": "x"},
            {"entity_id": "B", "signal": 20.0, "unit": "percent", "sector": "y"},
        ],
    }


def _compile(task: dict):
    return compile_comparative_context(task["entities"], compile_target_semantics(task))


def _relative(context, entity_id: str, feature_name: str):
    entity = next(
        item
        for item in context.per_entity_relative_features
        if item.entity_id == entity_id
    )
    return next(item for item in entity.features if item.feature_name == feature_name)


def _prompt_payload(prompt: str) -> dict:
    payload, _ = json.JSONDecoder().raw_decode(
        prompt.split("TASK_CONTEXT_JSON:\n", 1)[1]
    )
    return payload


def _task_context(task: dict, *, enabled: bool):
    text = "Pre-cutoff evidence for all entities."
    chunk = Chunk("DOC", "2025-12-01", 0, len(text), text)
    corpus = IndexedCorpus(
        [chunk],
        {"DOC": text},
        {"DOC": "2025-12-01"},
        doc_entity_ids={"DOC": ("A", "B", "C")},
        labels_present=True,
    ).with_task_table(task)
    return build_task_context(
        task,
        BM25Index([chunk], task["cutoff_date"]),
        corpus,
        evidence_per_entity=1,
        comparative_context_enabled=enabled,
    )


def test_constructs_stats_relative_positions_and_provenance() -> None:
    context = _compile(_task())
    [summary] = context.numeric_features
    assert summary.feature_name == "signal"
    assert summary.source == "entities[].signal"
    assert (summary.valid_count, summary.missing_count) == (3, 0)
    assert (summary.minimum, summary.median, summary.maximum) == (10.0, 20.0, 30.0)
    low = _relative(context, "A", "signal")
    middle = _relative(context, "B", "signal")
    high = _relative(context, "C", "signal")
    assert (low.ordinal_rank, low.percentile, low.relation_to_median) == (
        1.0,
        0.0,
        "below",
    )
    assert (middle.ordinal_rank, middle.percentile, middle.relation_to_median) == (
        2.0,
        0.5,
        "near",
    )
    assert (high.ordinal_rank, high.percentile, high.relation_to_median) == (
        3.0,
        1.0,
        "above",
    )
    assert context.comparison_count == 3


def test_entity_permutation_is_canonicalized() -> None:
    task = _task()
    first = _compile(task)
    task["entities"].reverse()
    assert _compile(task) == first
    assert [item.entity_id for item in first.per_entity_relative_features] == [
        "A",
        "B",
        "C",
    ]


def test_irrelevant_feature_addition_leaves_existing_comparison_unchanged() -> None:
    task = _task()
    first = _compile(task)
    for index, entity in enumerate(task["entities"]):
        entity["unrelated_numeric"] = 100 + index
    second = _compile(task)
    assert first.numeric_features[0] == next(
        item for item in second.numeric_features if item.feature_name == "signal"
    )
    for entity_id in ("A", "B", "C"):
        assert _relative(first, entity_id, "signal") == _relative(
            second, entity_id, "signal"
        )


def test_irrelevant_feature_rename_does_not_change_target_or_comparisons() -> None:
    task = _task()
    semantics = compile_target_semantics(task)
    first = _compile(task)
    for entity in task["entities"]:
        entity["renamed_sector"] = entity.pop("sector")
    assert compile_target_semantics(task) == semantics
    assert _compile(task) == first


def test_positive_affine_transform_preserves_rank_percentile_and_relation() -> None:
    task = _task()
    first = _compile(task)
    for entity in task["entities"]:
        entity["signal"] = 4.0 * entity["signal"] + 7.0
    second = _compile(task)
    for entity_id in ("A", "B", "C"):
        before = _relative(first, entity_id, "signal")
        after = _relative(second, entity_id, "signal")
        assert (
            before.ordinal_rank,
            before.percentile,
            before.relation_to_median,
        ) == (
            after.ordinal_rank,
            after.percentile,
            after.relation_to_median,
        )


def test_ties_use_average_rank_deterministically() -> None:
    task = _task()
    task["entities"][0]["signal"] = 10.0
    tied = _compile(task)
    assert _relative(tied, "A", "signal").ordinal_rank == 1.5
    assert _relative(tied, "C", "signal").ordinal_rank == 1.5
    assert _relative(tied, "B", "signal").ordinal_rank == 3.0


def test_missing_and_nonfinite_values_receive_no_rank() -> None:
    task = _task()
    task["entities"][0]["signal"] = None
    task["entities"][1]["signal"] = math.inf
    context = _compile(task)
    assert context.numeric_features == ()
    assert context.numeric_features_considered == ("signal",)
    assert context.skipped_numeric_features[0].reason == "insufficient_finite_values"
    assert all(not entity.features for entity in context.per_entity_relative_features)


def test_one_missing_value_is_excluded_without_fake_rank() -> None:
    task = _task()
    task["entities"][0]["signal"] = None
    context = _compile(task)
    [summary] = context.numeric_features
    assert (summary.valid_count, summary.missing_count) == (2, 1)
    assert not next(
        item for item in context.per_entity_relative_features if item.entity_id == "C"
    ).features
    assert _relative(context, "A", "signal").ordinal_rank == 1.0
    assert _relative(context, "B", "signal").ordinal_rank == 2.0


def test_heterogeneous_unit_metadata_skips_unsafe_comparison() -> None:
    task = _task()
    task["entities"][0]["unit"] = "basis points"
    context = _compile(task)
    assert context.numeric_features == ()
    [skipped] = context.skipped_numeric_features
    assert skipped.feature_name == "signal"
    assert skipped.reason.startswith("conflicting_unit_metadata:")
    assert "entities[].unit" in skipped.reason


def test_one_entity_and_all_missing_fields_are_skipped_gracefully() -> None:
    task = _task()
    task["entities"] = [{"entity_id": "A", "signal": 1.0, "all_missing": None}]
    context = _compile(task)
    assert context.numeric_features == ()
    assert context.comparison_count == 0
    assert context.numeric_features_considered == ("all_missing", "signal")
    assert {item.reason for item in context.skipped_numeric_features} == {
        "no_finite_values",
        "insufficient_finite_values",
    }


def test_label_order_and_evidence_perturbations_do_not_change_context() -> None:
    task = _task()
    task["target"] = {
        "name": "future_value",
        "type": "classification",
        "labels": ["up", "down"],
    }
    first = _compile(task)
    task["target"]["labels"].reverse()
    task["evidence_text"] = "The compiler must not inspect evidence."
    assert _compile(task) == first


def test_prompt_switch_off_is_r3_and_on_adds_only_comparative_payload() -> None:
    task = _task()
    off = _task_context(task, enabled=False)
    on = _task_context(task, enabled=True)
    off_prompt = build_task_prompt(off, off.cards, include_evidence=True)
    on_prompt = build_task_prompt(on, on.cards, include_evidence=True)
    off_payload = _prompt_payload(off_prompt)
    on_payload = _prompt_payload(on_prompt)
    comparative = on_payload.pop("comparative_context")
    assert on_payload == off_payload
    assert "comparative_context" not in off_payload
    assert comparative["numeric_features"][0]["feature_name"] == "signal"
    [first_entity] = [
        entity
        for entity in comparative["per_entity_relative_features"]
        if entity["entity_id"] == "A"
    ]
    assert first_entity["relative_numeric_features"]["signal"]["ordinal_rank"] == 1.0
    assert task_system_prompt(comparative_context_enabled=False) == TASK_SYSTEM_PROMPT
    assert "compare the entities" in task_system_prompt(
        comparative_context_enabled=True
    )

    off_plan = plan_batches(
        off,
        include_evidence=True,
        max_entities=20,
        max_input_chars=48_000,
        max_output_chars=12_000,
        max_primary_requests=5,
    )
    on_plan = plan_batches(
        on,
        include_evidence=True,
        max_entities=20,
        max_input_chars=48_000,
        max_output_chars=12_000,
        max_primary_requests=5,
    )
    assert on_plan.estimated_input_chars[0] > off_plan.estimated_input_chars[0]


def test_compiler_is_pure() -> None:
    task = _task()
    before = copy.deepcopy(task)
    _compile(task)
    assert task == before


def test_switch_controls_trace_and_preserves_mock_answer(tmp_path: Path) -> None:
    unit = Path(__file__).resolve().parents[3] / "units" / "t4-cotpos-202411-us10"
    off_trace = tmp_path / "off.trace.json"
    on_trace = tmp_path / "on.trace.json"
    off_client = MockModelClient(_mock_reply)
    on_client = MockModelClient(_mock_reply)
    off_answer = run(
        unit / "task.json",
        unit / "corpus",
        tmp_path / "off.answer.json",
        off_client,
        top_k=10,
        trace_path=off_trace,
        comparative_context=False,
    )
    on_answer = run(
        unit / "task.json",
        unit / "corpus",
        tmp_path / "on.answer.json",
        on_client,
        top_k=10,
        trace_path=on_trace,
        comparative_context=True,
    )
    assert on_answer == off_answer
    assert (off_client.request_count, on_client.request_count) == (1, 1)
    off = json.loads(off_trace.read_text(encoding="utf-8"))["task_prediction"]
    on = json.loads(on_trace.read_text(encoding="utf-8"))["task_prediction"]
    assert off["comparative_context_version"] == "off"
    assert off["comparison_count"] == 0
    assert on["comparative_context_version"] == "1"
    assert on["comparison_count"] > 0
    assert on["numeric_features_compared"]
    assert on["numeric_feature_summaries"][0]["source"].startswith("entities[]")
    assert on["prompt_chars"][0] > off["prompt_chars"][0]
