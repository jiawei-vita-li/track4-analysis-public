"""Exact-render batching and fail-closed prompt-budget regression tests."""

from __future__ import annotations

import json

import pytest

from baselines.strong_rag_baseline.cli import _mock_reply
from baselines.strong_rag_baseline.client import MockModelClient
from baselines.strong_rag_baseline.comparative_context import (
    compile_comparative_context,
)
from baselines.strong_rag_baseline.indexer import IndexedCorpus
from baselines.strong_rag_baseline.prompting import render_task_request
from baselines.strong_rag_baseline.target_semantics import compile_target_semantics
from baselines.strong_rag_baseline.task_context import (
    BatchPlan,
    EntityCard,
    TaskContext,
    plan_batches,
)
from baselines.strong_rag_baseline.task_predictor import run_task_prediction

LIMIT = 48_000


def _context(
    entity_count: int, feature_count: int, *, comparative: bool = True
) -> TaskContext:
    entities: list[dict] = []
    cards: list[EntityCard] = []
    for entity_number in range(entity_count):
        features = {
            f"feature_{feature_number:02d}": float(
                (entity_number + 1) * (feature_number + 1)
            )
            for feature_number in range(feature_count)
        }
        entity_id = f"E{entity_number:03d}"
        entities.append({"entity_id": entity_id, **features})
        cards.append(EntityCard(entity_id, features, (), ()))
    task = {
        "task_id": "synthetic-resource-only",
        "prompt": "Rank entities on one common target scale.",
        "cutoff_date": "2026-01-01",
        "interval_level": 0.9,
        "target": {
            "type": "ranking",
            "description": "Synthetic target for batching mechanics only.",
        },
        "entities": entities,
    }
    semantics = compile_target_semantics(task)
    return TaskContext(
        task_id=task["task_id"],
        prompt=task["prompt"],
        target=task["target"],
        cutoff_date=task["cutoff_date"],
        interval_level=task["interval_level"],
        semantics=semantics,
        comparative_context=(
            compile_comparative_context(entities, semantics) if comparative else None
        ),
        cards=tuple(cards),
    )


def _plan(context: TaskContext) -> BatchPlan:
    return plan_batches(
        context,
        include_evidence=True,
        max_entities=20,
        max_input_chars=LIMIT,
        max_output_chars=12_000,
        max_primary_requests=5,
    )


def _payload(context: TaskContext, cards: tuple[EntityCard, ...]) -> dict:
    rendered = render_task_request(context, cards, include_evidence=True)
    payload, _ = json.JSONDecoder().raw_decode(
        rendered.user_prompt.split("TASK_CONTEXT_JSON:\n", 1)[1]
    )
    return payload


def test_planner_counts_the_exact_full_rendered_request_and_fixed_overhead() -> None:
    context = _context(21, 8)
    plan = _plan(context)
    actual = tuple(
        render_task_request(context, batch, include_evidence=True).total_chars
        for batch in plan.batches
    )
    assert plan.planned_actual_prompt_chars == actual
    for batch, planned in zip(plan.batches, actual, strict=True):
        rendered = render_task_request(context, batch, include_evidence=True)
        assert planned == len(rendered.system_prompt) + len(rendered.user_prompt)
        assert planned > len(rendered.user_prompt)


@pytest.mark.parametrize("entity_count,feature_count", [(40, 8), (30, 12)])
def test_stress_batches_never_exceed_limit_or_defer(
    entity_count: int, feature_count: int
) -> None:
    context = _context(entity_count, feature_count)
    plan = _plan(context)
    actual = [
        render_task_request(context, batch, include_evidence=True).total_chars
        for batch in plan.batches
    ]
    covered = [card.entity_id for batch in plan.batches for card in batch]
    assert actual == list(plan.planned_actual_prompt_chars)
    assert max(actual) <= LIMIT
    assert not plan.deferred_entity_ids
    assert not plan.single_entity_prompt_overflow
    assert len(covered) == entity_count
    assert len(set(covered)) == entity_count


def test_prompt_keeps_full_roster_summaries_but_only_batch_relative_rows() -> None:
    context = _context(30, 12)
    plan = _plan(context)
    first_batch = plan.batches[0]
    comparative = _payload(context, first_batch)["comparative_context"]
    assert all(item["valid_count"] == 30 for item in comparative["numeric_features"])
    assert {
        item["entity_id"] for item in comparative["per_entity_relative_features"]
    } == {card.entity_id for card in first_batch}
    last_id = first_batch[-1].entity_id
    last = next(
        item
        for item in comparative["per_entity_relative_features"]
        if item["entity_id"] == last_id
    )
    assert last["relative_numeric_features"]["feature_00"]["ordinal_rank"] == 20.0
    assert last["relative_numeric_features"]["feature_00"]["percentile"] == round(
        19 / 29, 6
    )
    assert "raw_value" not in last["relative_numeric_features"]["feature_00"]
    assert "skipped_numeric_features" not in comparative


def test_comparative_off_keeps_relative_payload_absent() -> None:
    context = _context(30, 12, comparative=False)
    plan = _plan(context)
    assert "comparative_context" not in _payload(context, plan.batches[0])
    assert max(plan.planned_actual_prompt_chars) <= LIMIT


def test_single_entity_overflow_is_recorded_and_deferred_without_a_request() -> None:
    context = _context(2, 2)
    plan = plan_batches(
        context,
        include_evidence=True,
        max_entities=20,
        max_input_chars=1,
        max_output_chars=12_000,
        max_primary_requests=5,
    )
    assert not plan.batches
    assert plan.single_entity_prompt_overflow == ("E000", "E001")
    assert plan.deferred_entity_ids == ("E000", "E001")


def test_runtime_guard_rejects_deliberately_oversized_planned_batch() -> None:
    context = _context(2, 2)
    rendered = render_task_request(context, context.cards, include_evidence=True)
    plan = BatchPlan(
        batches=(context.cards,),
        deferred_entity_ids=(),
        planned_actual_prompt_chars=(rendered.total_chars,),
        single_entity_prompt_overflow=(),
        max_input_chars=rendered.total_chars - 1,
    )
    client = MockModelClient(_mock_reply)
    corpus = IndexedCorpus([], {}, {}, doc_entity_ids={}, labels_present=False)
    result = run_task_prediction(
        context,
        plan,
        corpus,
        client,
        include_evidence=True,
    )
    assert client.request_count == 0
    assert not result.results
    [failure] = result.trace["prompt_guard_failures"]
    assert failure["phase"] == "primary"
    assert failure["actual_chars"] == rendered.total_chars
    assert result.trace["parse_failures"]
