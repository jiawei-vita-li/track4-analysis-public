"""Task-level prediction, batching, repair, and trace tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from baselines.strong_rag_baseline.cli import _mock_reply, run
from baselines.strong_rag_baseline.client import MockModelClient
from baselines.strong_rag_baseline.indexer import build_index
from baselines.strong_rag_baseline.retriever import BM25Index
from baselines.strong_rag_baseline.task_context import build_task_context, plan_batches

REPO = Path(__file__).resolve().parents[3]
UNITS = REPO / "units"


@pytest.mark.parametrize(
    "unit_name,target_type",
    [
        ("t4-eps-yoy-2023Q2-mixed", "classification"),
        ("t4-auction-btc-202411-us7", "regression"),
        ("t4-cotpos-202411-us10", "ranking"),
    ],
)
def test_task_level_mock_is_complete_and_one_request(
    tmp_path: Path, unit_name: str, target_type: str
) -> None:
    unit = UNITS / unit_name
    task = json.loads((unit / "task.json").read_text(encoding="utf-8"))
    client = MockModelClient(_mock_reply)
    trace_path = tmp_path / f"{unit_name}.trace.json"

    answer = run(
        unit / "task.json",
        unit / "corpus",
        tmp_path / f"{unit_name}.json",
        client,
        top_k=10,
        trace_path=trace_path,
    )

    trusted = [entity["entity_id"] for entity in task["entities"]]
    rows = answer["entity_predictions"]
    assert [row["entity_id"] for row in rows] == trusted
    assert answer["target_type"] == target_type
    assert client.request_count == 1
    assert all(row["claims"] for row in rows)
    assert all(
        all(claim["span_end"] - claim["span_start"] <= 200 for claim in row["claims"])
        for row in rows
    )
    assert all("rank" not in row for row in rows)
    if target_type == "ranking":
        assert len({row["point_forecast"] for row in rows}) > 1

    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    task_trace = trace["task_prediction"]
    assert task_trace["batch_count"] == 1
    assert task_trace["request_count"] == 1
    assert task_trace["entities_per_batch"] == [len(trusted)]
    assert not task_trace["parse_failures"]
    assert all("features_used" in entity for entity in trace["entities"])
    assert all("evidence_used" in entity for entity in trace["entities"])


def test_one_constrained_repair_recovers_a_partial_reply(tmp_path: Path) -> None:
    unit = UNITS / "t4-EXAMPLE-eps-beat"

    def partial_then_valid(system: str, user: str) -> str:
        if client.request_count == 1:
            return '{"predictions": []}'
        return _mock_reply(system, user)

    client = MockModelClient(partial_then_valid)
    trace_path = tmp_path / "trace.json"
    answer = run(
        unit / "task.json",
        unit / "corpus",
        tmp_path / "answer.json",
        client,
        top_k=5,
        trace_path=trace_path,
    )

    assert client.request_count == 2
    assert answer["entity_predictions"][0]["label"] == "beat"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["task_prediction"]["repair_used"] is True
    assert trace["task_prediction"]["parse_failures"]


def test_primary_request_cap_defers_overflow_to_safe_fallback(tmp_path: Path) -> None:
    unit = UNITS / "t4-auction-btc-202411-us7"
    task = json.loads((unit / "task.json").read_text(encoding="utf-8"))
    corpus = build_index(unit / "corpus")
    index = BM25Index(corpus.chunks, task["cutoff_date"])
    context = build_task_context(task, index, corpus, evidence_per_entity=1)
    plan = plan_batches(
        context,
        include_evidence=True,
        max_entities=1,
        max_input_chars=100_000,
        max_output_chars=12_000,
        max_primary_requests=5,
    )

    assert len(plan.batches) == 5
    assert len(plan.deferred_entity_ids) == 2

    client = MockModelClient(_mock_reply)
    answer = run(
        unit / "task.json",
        unit / "corpus",
        tmp_path / "answer.json",
        client,
        top_k=5,
        batch_max_entities=1,
        max_primary_requests=5,
    )
    assert client.request_count == 5
    assert len(answer["entity_predictions"]) == len(task["entities"])
    assert all(row["claims"] for row in answer["entity_predictions"])


def test_structured_only_mode_still_finishes_through_safety(tmp_path: Path) -> None:
    unit = UNITS / "t4-cotpos-202411-us10"
    client = MockModelClient(_mock_reply)
    answer = run(
        unit / "task.json",
        unit / "corpus",
        tmp_path / "answer.json",
        client,
        top_k=5,
        include_evidence=False,
    )

    assert client.request_count == 1
    assert len(answer["entity_predictions"]) == 10
    assert all(row["claims"] for row in answer["entity_predictions"])


def test_trace_does_not_call_removed_null_label_a_fallback(tmp_path: Path) -> None:
    unit = UNITS / "t4-auction-btc-202411-us7"
    trace_path = tmp_path / "trace.json"
    run(
        unit / "task.json",
        unit / "corpus",
        tmp_path / "answer.json",
        MockModelClient(_mock_reply),
        top_k=5,
        trace_path=trace_path,
        prediction_mode="entity",
    )
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert not any(entity["fallback_used"] for entity in trace["entities"])


def test_task_context_prefers_published_top_level_target_type() -> None:
    unit = UNITS / "t4-EXAMPLE-eps-beat"
    task = json.loads((unit / "task.json").read_text(encoding="utf-8"))
    task["target_type"] = "regression"
    corpus = build_index(unit / "corpus")
    context = build_task_context(
        task,
        BM25Index(corpus.chunks, task["cutoff_date"]),
        corpus,
        evidence_per_entity=1,
    )
    assert context.target["type"] == "regression"
