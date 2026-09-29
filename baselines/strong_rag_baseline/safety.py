"""Submission-contract repair and fail-closed preflight checks.

The prediction model is allowed to be wrong.  It is not allowed to turn one
malformed row, timeout, or empty evidence list into a whole-unit engineering
failure.  This module is deliberately target-family agnostic.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from .agent import EntityResult
from .indexer import Chunk, IndexedCorpus

_TOKEN = re.compile(r"[a-z0-9]+")


class ContractError(ValueError):
    """The frozen inputs make a valid answer impossible or the repair failed."""


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _fallback_point(task: Mapping, entity: Mapping) -> float:
    target_name = str((task.get("target") or {}).get("name", ""))
    target_tokens = set(_TOKEN.findall(target_name.lower()))
    candidates: list[tuple[int, str, float]] = []
    for key, raw in entity.items():
        value = _finite(raw)
        if value is None:
            continue
        key_tokens = set(_TOKEN.findall(str(key).lower()))
        overlap = len(target_tokens & key_tokens)
        candidates.append((-overlap, str(key), value))
    if not candidates:
        return 0.0
    candidates.sort()
    if candidates[0][0] < 0:
        return candidates[0][2]
    values = sorted(item[2] for item in candidates)
    return values[len(values) // 2]


def _eligible_chunks(task: Mapping, corpus: IndexedCorpus) -> list[Chunk]:
    cutoff = task.get("cutoff_date")
    return sorted(
        (
            chunk
            for chunk in corpus.chunks
            if isinstance(corpus.doc_dates.get(chunk.doc_id), str)
            and isinstance(cutoff, str)
            and corpus.doc_dates[chunk.doc_id] <= cutoff
            and 0 <= chunk.span_start < chunk.span_end
            and chunk.span_end <= len(corpus.doc_texts.get(chunk.doc_id, ""))
        ),
        key=lambda chunk: (chunk.doc_id, chunk.span_start, chunk.span_end),
    )


def _safe_claims(
    task: Mapping, prediction: Mapping, corpus: IndexedCorpus, fallback: Chunk
) -> list[dict]:
    cutoff = task["cutoff_date"]
    kept: list[dict] = []
    for claim in prediction.get("claims") or []:
        if not isinstance(claim, Mapping):
            continue
        doc_id = claim.get("doc_id")
        start, end = claim.get("span_start"), claim.get("span_end")
        claim_text = claim.get("claim")
        text = corpus.doc_texts.get(doc_id) if isinstance(doc_id, str) else None
        doc_date = corpus.doc_dates.get(doc_id) if isinstance(doc_id, str) else None
        if (
            text is None
            or not isinstance(doc_date, str)
            or doc_date > cutoff
            or isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or not (0 <= start < end <= len(text))
            or not isinstance(claim_text, str)
            or not claim_text.strip()
        ):
            continue
        kept.append(
            {
                "doc_id": doc_id,
                "span_start": start,
                "span_end": end,
                "claim": claim_text.strip(),
            }
        )
    if kept:
        return kept
    return [
        {
            "doc_id": fallback.doc_id,
            "span_start": fallback.span_start,
            "span_end": fallback.span_end,
            "claim": "Deterministic fallback: this is the top available pre-cutoff passage.",
        }
    ]


def sanitize_results(
    task: Mapping, results: list[EntityResult], corpus: IndexedCorpus
) -> list[EntityResult]:
    """Return exactly one safe result for every trusted roster entity."""
    eligible = _eligible_chunks(task, corpus)
    if not eligible:
        raise ContractError("no dated pre-cutoff corpus chunk can support a valid fallback")
    fallback_chunk = eligible[0]
    first_by_id: dict[str, EntityResult] = {}
    for result in results:
        entity_id = result.prediction.get("entity_id")
        if isinstance(entity_id, str) and entity_id not in first_by_id:
            first_by_id[entity_id] = result

    target = task.get("target") or {}
    target_type = target.get("type")
    labels = target.get("labels") or []
    level = _finite(task.get("interval_level"))
    if target_type not in {"classification", "regression", "ranking"}:
        raise ContractError(f"unsupported target type: {target_type!r}")
    if level is None:
        raise ContractError("task interval_level is not finite")

    sanitized: list[EntityResult] = []
    for entity in task.get("entities") or []:
        entity_id = entity.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id:
            raise ContractError("trusted roster contains an invalid entity_id")
        original = first_by_id.get(entity_id)
        raw = original.prediction if original is not None else {}
        point = _finite(raw.get("point_forecast"))
        if point is None:
            point = _fallback_point(task, entity)

        interval = raw.get("interval") if isinstance(raw.get("interval"), Mapping) else {}
        lo, hi = _finite(interval.get("lo")), _finite(interval.get("hi"))
        if lo is None or hi is None or lo > hi:
            half = max(abs(point), 1.0)
            lo, hi = point - half, point + half

        prediction: dict = {
            "entity_id": entity_id,
            "point_forecast": point,
            "interval": {"level": level, "lo": lo, "hi": hi},
            "claims": _safe_claims(task, raw, corpus, fallback_chunk),
        }
        if target_type == "classification":
            label = raw.get("label")
            if label not in labels:
                if not labels:
                    raise ContractError("classification task has no label vocabulary")
                label = labels[0]
            prediction["label"] = label
        sanitized.append(
            EntityResult(
                prediction=prediction,
                dropped_claims=(original.dropped_claims if original else 0),
                model_raw=(original.model_raw if original else "fallback: missing entity result"),
            )
        )
    return sanitized


def preflight(task: Mapping, answer: Mapping, corpus: IndexedCorpus) -> None:
    """Raise :class:`ContractError` unless the fatal local invariants hold."""
    if answer.get("task_id") != task.get("task_id"):
        raise ContractError("task_id mismatch")
    rows = answer.get("entity_predictions")
    if not isinstance(rows, list):
        raise ContractError("entity_predictions must be an array")
    trusted = [entity.get("entity_id") for entity in task.get("entities") or []]
    observed = [row.get("entity_id") for row in rows if isinstance(row, Mapping)]
    if observed != trusted or len(set(observed)) != len(observed):
        raise ContractError("entity roster is missing, duplicated, unknown, or out of order")

    target = task.get("target") or {}
    target_type = target.get("type")
    labels = target.get("labels") or []
    level = _finite(task.get("interval_level"))
    ranks: list[int] = []
    some_rank = False
    for row in rows:
        if target_type == "classification" and row.get("label") not in labels:
            raise ContractError(f"{row.get('entity_id')}: invalid classification label")
        if target_type in {"regression", "ranking"} and _finite(row.get("point_forecast")) is None:
            raise ContractError(f"{row.get('entity_id')}: point_forecast is not finite")
        interval = row.get("interval")
        if not isinstance(interval, Mapping):
            raise ContractError(f"{row.get('entity_id')}: missing interval")
        lo, hi = _finite(interval.get("lo")), _finite(interval.get("hi"))
        if _finite(interval.get("level")) != level or lo is None or hi is None or lo > hi:
            raise ContractError(f"{row.get('entity_id')}: invalid interval")
        claims = row.get("claims")
        if not isinstance(claims, list) or not claims:
            raise ContractError(f"{row.get('entity_id')}: missing claims")
        # Reuse the same strict filter: if any item would be dropped, the answer is invalid.
        if _safe_claims(task, row, corpus, _eligible_chunks(task, corpus)[0]) != claims:
            raise ContractError(f"{row.get('entity_id')}: invalid citation")
        if "rank" in row:
            some_rank = True
            rank = row["rank"]
            if isinstance(rank, bool) or not isinstance(rank, int):
                raise ContractError(f"{row.get('entity_id')}: invalid rank")
            ranks.append(rank)
    if some_rank and (len(ranks) != len(rows) or sorted(ranks) != list(range(1, len(rows) + 1))):
        raise ContractError("optional ranks must be a complete permutation")
