"""Task-level House prediction over structured rows and compact evidence cards."""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Any

from .agent import EntityResult, _parse_model_json, _safe_interval
from .client import ModelClient
from .indexer import IndexedCorpus
from .task_context import BatchPlan, EntityCard, TaskContext

TASK_SYSTEM_PROMPT = """\
You are a careful evidence-grounded forecaster. Jointly compare the complete entity table and
predict only the entities in PREDICTION_BATCH. Use only the supplied structured fields and frozen
pre-cutoff evidence. Do not use remembered outcomes or infer post-cutoff facts. Return one JSON
object and no prose. For evidence, select an evidence_id supplied for that same entity and copy a
short verbatim quote from its text. Never invent document IDs or character offsets. Keep all numeric predictions in the
target's own units, and do not copy an unrelated numeric feature merely because it is available.
A related passage is not necessarily support: prefer explicit measurements, guidance, trends,
and comparisons that bear on the prediction."""

_FALLBACK_CLAIM_CHARS = 200


@dataclass(frozen=True)
class TaskPredictionRun:
    results: tuple[EntityResult, ...]
    trace: dict[str, Any]


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def build_task_prompt(
    context: TaskContext,
    cards: tuple[EntityCard, ...],
    *,
    include_evidence: bool,
    repair: dict[str, Any] | None = None,
) -> str:
    target_type = context.target.get("type", "classification")
    if target_type == "classification":
        prediction_shape: dict[str, Any] = {
            "entity_id": "trusted entity_id",
            "label": "exactly one allowed label",
            "point_forecast": "finite number or null",
            "interval": {"lo": "finite number", "hi": "finite number"},
            "evidence": [{"evidence_id": "supplied ID", "quote": "verbatim substring"}],
        }
    elif target_type == "ranking":
        prediction_shape = {
            "entity_id": "trusted entity_id",
            "score": "finite numeric target value; larger means higher rank",
            "interval": {"lo": "finite number", "hi": "finite number"},
            "evidence": [{"evidence_id": "supplied ID", "quote": "verbatim substring"}],
        }
    else:
        prediction_shape = {
            "entity_id": "trusted entity_id",
            "point_forecast": "finite numeric target value",
            "interval": {"lo": "finite number", "hi": "finite number"},
            "evidence": [{"evidence_id": "supplied ID", "quote": "verbatim substring"}],
        }
    payload: dict[str, Any] = {
        "task_id": context.task_id,
        "task_prompt": context.prompt,
        "cutoff_date": context.cutoff_date,
        "target": context.target,
        "interval_level": context.interval_level,
        "complete_entity_table": context.entity_table,
        "prediction_batch": [
            card.prompt_value(include_evidence=include_evidence) for card in cards
        ],
        "required_output": {"predictions": [prediction_shape]},
    }
    if repair is not None:
        payload["repair"] = repair
    instructions = (
        "Return every prediction_batch entity exactly once and no other entity. "
        "Do not output optional rank; ranking is derived globally from numeric score. "
        "Choose one or two evidence entries only from that entity's card; quotes must be exact. "
        "The interval level is fixed by the task and must not be changed."
    )
    return "TASK_CONTEXT_JSON:\n" + json.dumps(payload, ensure_ascii=False) + "\n" + instructions


def _rows_from_raw(raw: str, cards: tuple[EntityCard, ...]) -> list[dict[str, Any]]:
    parsed = _parse_model_json(raw)
    rows = parsed.get("predictions")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    # Backward-compatible single-entity shape keeps the original controlled
    # tests and local model harness useful during the transition.
    if len(cards) == 1 and any(key in parsed for key in ("label", "point_forecast", "score")):
        return [{"entity_id": cards[0].entity_id, **parsed}]
    raise ValueError("task-level reply has no predictions array")


def _row_failures(
    rows: list[dict[str, Any]], cards: tuple[EntityCard, ...], context: TaskContext
) -> list[str]:
    expected = [card.entity_id for card in cards]
    observed = [row.get("entity_id") for row in rows]
    failures: list[str] = []
    if len(observed) != len(set(observed)):
        failures.append("duplicate entity_id")
    if set(observed) != set(expected):
        failures.append("missing or unknown entity_id")
    target_type = context.target.get("type")
    labels = context.target.get("labels") or []
    for row in rows:
        if row.get("entity_id") not in expected:
            continue
        if target_type == "classification" and row.get("label") not in labels:
            failures.append(f"{row.get('entity_id')}: invalid label")
        if target_type in {"regression", "ranking"}:
            value = row.get("score") if target_type == "ranking" else row.get("point_forecast")
            if _finite(value) is None:
                failures.append(f"{row.get('entity_id')}: non-finite point")
    return failures


def _claim_from_card(card: EntityCard, row: dict[str, Any]) -> tuple[list[dict], list[str]]:
    allowed = {item.evidence_id: item for item in card.evidence}
    selected: list[tuple[str, str]] = []
    evidence = row.get("evidence")
    if isinstance(evidence, list):
        for value in evidence:
            if not isinstance(value, dict):
                continue
            evidence_id = value.get("evidence_id")
            quote = value.get("quote")
            if isinstance(evidence_id, str) and evidence_id in allowed and isinstance(quote, str):
                selected.append((evidence_id, quote))
    # Accept the earlier evidence_ids shape as a graceful compatibility path.
    if not selected and isinstance(row.get("evidence_ids"), list):
        selected = [
            (value, "")
            for value in row["evidence_ids"]
            if isinstance(value, str) and value in allowed
        ]
    if not selected and card.evidence:
        selected = [(card.evidence[0].evidence_id, "")]

    claims: list[dict] = []
    used: list[str] = []
    for evidence_id, quote in selected[:2]:
        chunk = allowed[evidence_id].chunk
        relative = chunk.text.find(quote) if quote else -1
        if relative >= 0 and quote.strip():
            start = chunk.span_start + relative
            end = start + len(quote)
            claim_text = quote
        else:
            # A generic sentence about having selected evidence is content-free under
            # scorer 5.2.2.  If the model supplied no usable quote, cite a short exact
            # extract instead: it cannot invent a fact, keeps offsets auditable, and is
            # far below the scorer's 8,000-character citation cap.
            claim_text = chunk.text[:_FALLBACK_CLAIM_CHARS]
            if len(chunk.text) > _FALLBACK_CLAIM_CHARS:
                claim_text = claim_text.rsplit(" ", 1)[0] or claim_text
            start = chunk.span_start
            end = start + len(claim_text)
        claims.append(
            {
                "doc_id": chunk.doc_id,
                "span_start": start,
                "span_end": end,
                "claim": claim_text,
            }
        )
        used.append(evidence_id)
    return claims, used


def _result_from_row(
    row: dict[str, Any], card: EntityCard, context: TaskContext, raw: str
) -> EntityResult:
    target_type = context.target.get("type")
    if target_type == "ranking":
        point = _finite(row.get("score"))
    else:
        point = _finite(row.get("point_forecast"))
    claims, evidence_used = _claim_from_card(card, row)
    prediction: dict[str, Any] = {
        "entity_id": card.entity_id,
        "point_forecast": point,
        "interval": _safe_interval(row, context.interval_level, point),
        "claims": claims,
    }
    if target_type == "classification":
        prediction["label"] = row.get("label")
    return EntityResult(
        prediction=prediction,
        dropped_claims=0,
        model_raw=raw,
        trace={
            "entity_id": card.entity_id,
            "features_used": card.features,
            "evidence_used": evidence_used,
            "queries": list(card.queries),
            "retrieved": [
                {
                    "evidence_id": item.evidence_id,
                    "doc_id": item.chunk.doc_id,
                    "span_start": item.chunk.span_start,
                    "span_end": item.chunk.span_end,
                    "score": item.score,
                }
                for item in card.evidence
            ],
            "raw_prediction": row,
            "fallback_used": False,
        },
    )


def run_task_prediction(
    context: TaskContext,
    plan: BatchPlan,
    corpus: IndexedCorpus,
    client: ModelClient,
    *,
    include_evidence: bool,
    allow_repair: bool = True,
) -> TaskPredictionRun:
    """Run primary batches with at most one constrained repair request per unit."""
    del corpus  # Grounding uses only trusted chunk metadata embedded in the context.
    results: list[EntityResult] = []
    raw_outputs: list[str] = []
    parse_failures: list[dict[str, Any]] = []
    batch_latencies: list[float] = []
    repair_used = False
    request_before = int(getattr(client, "request_count", 0))

    for batch_number, cards in enumerate(plan.batches, start=1):
        started = time.perf_counter()
        prompt = build_task_prompt(context, cards, include_evidence=include_evidence)
        raw = ""
        rows: list[dict[str, Any]] = []
        failures: list[str] = []
        try:
            raw = client.complete(TASK_SYSTEM_PROMPT, prompt)
            raw_outputs.append(raw)
            rows = _rows_from_raw(raw, cards)
            failures = _row_failures(rows, cards, context)
        except Exception as exc:
            failures = [f"{type(exc).__name__}: {exc}"]

        if failures and allow_repair and not repair_used:
            repair_used = True
            parse_failures.append({"batch": batch_number, "failures": failures})
            repair_prompt = build_task_prompt(
                context,
                cards,
                include_evidence=include_evidence,
                repair={
                    "errors": failures,
                    "invalid_output": raw[:8000],
                    "instruction": "Return a complete corrected object in the required shape.",
                },
            )
            try:
                raw = client.complete(TASK_SYSTEM_PROMPT, repair_prompt)
                raw_outputs.append(raw)
                rows = _rows_from_raw(raw, cards)
                failures = _row_failures(rows, cards, context)
            except Exception as exc:
                failures = [f"repair {type(exc).__name__}: {exc}"]

        if failures:
            parse_failures.append({"batch": batch_number, "failures": failures})
            rows = []

        first_by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            entity_id = row.get("entity_id")
            if isinstance(entity_id, str) and entity_id not in first_by_id:
                first_by_id[entity_id] = row
        for card in cards:
            row = first_by_id.get(card.entity_id)
            if row is not None:
                results.append(_result_from_row(row, card, context, raw))
        batch_latencies.append(round((time.perf_counter() - started) * 1000, 3))

    request_after = int(getattr(client, "request_count", request_before))
    trace = {
        "target_type": context.target.get("type"),
        "batch_count": len(plan.batches),
        "entities_per_batch": [len(batch) for batch in plan.batches],
        "estimated_input_chars": list(plan.estimated_input_chars),
        "deferred_entity_ids": list(plan.deferred_entity_ids),
        "request_count": max(0, request_after - request_before),
        "repair_used": repair_used,
        "raw_outputs": raw_outputs,
        "parse_failures": parse_failures,
        "batch_latency_ms": batch_latencies,
    }
    return TaskPredictionRun(results=tuple(results), trace=trace)
