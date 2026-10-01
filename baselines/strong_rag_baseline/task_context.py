"""Generic task-level context and deterministic prediction batching.

The House model sees the complete structured entity table, but only compact
pre-cutoff evidence cards for the entities it must predict in a given batch.
Citation offsets never enter the prompt: they stay in trusted local metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .evidence_binding import retrieve_admissible, task_row_fallback
from .indexer import Chunk, IndexedCorpus
from .queries import build_queries
from .retriever import BM25Index

_META_FIELDS = {"corpus_ref"}


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    chunk: Chunk
    score: float

    def prompt_value(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "doc_id": self.chunk.doc_id,
            "date": self.chunk.doc_date,
            "text": self.chunk.text,
        }


@dataclass(frozen=True)
class EntityCard:
    entity_id: str
    features: dict[str, Any]
    queries: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]

    def prompt_value(self, *, include_evidence: bool) -> dict[str, Any]:
        value: dict[str, Any] = {
            "entity_id": self.entity_id,
            "features": self.features,
        }
        if include_evidence:
            value["evidence"] = [item.prompt_value() for item in self.evidence]
        return value


@dataclass(frozen=True)
class TaskContext:
    task_id: str
    prompt: str
    target: dict[str, Any]
    cutoff_date: str
    interval_level: float
    cards: tuple[EntityCard, ...]

    @property
    def entity_table(self) -> list[dict[str, Any]]:
        return [{"entity_id": card.entity_id, **card.features} for card in self.cards]


@dataclass(frozen=True)
class BatchPlan:
    batches: tuple[tuple[EntityCard, ...], ...]
    deferred_entity_ids: tuple[str, ...]
    estimated_input_chars: tuple[int, ...]


def _features(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in entity.items()
        if key not in _META_FIELDS and key != "entity_id"
    }


def build_task_context(
    task: dict,
    index: BM25Index,
    corpus: IndexedCorpus,
    *,
    evidence_per_entity: int,
) -> TaskContext:
    """Retrieve compact, cutoff-safe evidence cards for the trusted roster."""
    cards: list[EntityCard] = []
    for entity_number, entity in enumerate(task.get("entities") or [], start=1):
        entity_id = str(entity.get("entity_id", ""))
        queries = build_queries(task, entity)
        hits = retrieve_admissible(
            index, queries, corpus, entity_id, evidence_per_entity
        )
        evidence = tuple(
            EvidenceItem(
                evidence_id=f"E{entity_number}_{hit_number}",
                chunk=hit.chunk,
                score=hit.score,
            )
            for hit_number, hit in enumerate(hits, start=1)
        )
        if not evidence:
            fallback = task_row_fallback(corpus, entity_id)
            if fallback is not None:
                evidence = (
                    EvidenceItem(
                        evidence_id=f"E{entity_number}_TASK",
                        chunk=fallback,
                        score=0.0,
                    ),
                )
        cards.append(
            EntityCard(
                entity_id=entity_id,
                features=_features(entity),
                queries=tuple(queries),
                evidence=evidence,
            )
        )
    target = task.get("target") if isinstance(task.get("target"), dict) else {}
    if task.get("target_type") is not None:
        target = {**target, "type": task["target_type"]}
    return TaskContext(
        task_id=str(task.get("task_id", "")),
        prompt=str(task.get("prompt", "")),
        target=dict(target),
        cutoff_date=str(task.get("cutoff_date", "")),
        interval_level=float(task.get("interval_level", 0.9)),
        cards=tuple(cards),
    )


def _json_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def plan_batches(
    context: TaskContext,
    *,
    include_evidence: bool,
    max_entities: int,
    max_input_chars: int,
    max_output_chars: int,
    max_primary_requests: int,
) -> BatchPlan:
    """Greedily pack deterministic batches and defer overflow instead of overspending.

    The shared full entity table is counted in every batch.  An entity whose card
    cannot fit alone is still admitted (the model needs at least its structured
    row), while evidence is clipped by ``build_task_context`` rather than here.
    If the plan would require more primary calls than allowed, remaining entities
    are deferred to the existing deterministic safety fallback.
    """
    shared_chars = _json_chars(
        {
            "task_id": context.task_id,
            "prompt": context.prompt,
            "target": context.target,
            "cutoff_date": context.cutoff_date,
            "interval_level": context.interval_level,
            "complete_entity_table": context.entity_table,
        }
    )
    batches: list[tuple[EntityCard, ...]] = []
    estimates: list[int] = []
    deferred: list[str] = []
    current: list[EntityCard] = []
    current_chars = shared_chars

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        if len(batches) < max_primary_requests:
            batches.append(tuple(current))
            estimates.append(current_chars)
        else:
            deferred.extend(card.entity_id for card in current)
        current = []
        current_chars = shared_chars

    for card in context.cards:
        card_chars = _json_chars(card.prompt_value(include_evidence=include_evidence))
        output_chars = (len(current) + 1) * 500
        would_overflow = current and (
            len(current) >= max_entities
            or current_chars + card_chars > max_input_chars
            or output_chars > max_output_chars
        )
        if would_overflow:
            flush()
        current.append(card)
        current_chars += card_chars
    flush()

    return BatchPlan(
        batches=tuple(batches),
        deferred_entity_ids=tuple(deferred),
        estimated_input_chars=tuple(estimates),
    )
