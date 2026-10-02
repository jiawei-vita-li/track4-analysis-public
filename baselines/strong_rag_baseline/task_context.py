"""Generic task-level context and deterministic prediction batching.

The House model sees the complete structured entity table, but only compact
pre-cutoff evidence cards for the entities it must predict in a given batch.
Citation offsets never enter the prompt: they stay in trusted local metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .comparative_context import ComparativeContext, compile_comparative_context
from .evidence_binding import retrieve_admissible, task_row_fallback
from .indexer import Chunk, IndexedCorpus
from .prompting import render_task_request
from .queries import build_queries
from .retriever import BM25Index
from .target_semantics import TargetSemantics, compile_target_semantics

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
    semantics: TargetSemantics
    comparative_context: ComparativeContext | None
    cards: tuple[EntityCard, ...]

    @property
    def entity_table(self) -> list[dict[str, Any]]:
        return [{"entity_id": card.entity_id, **card.features} for card in self.cards]


@dataclass(frozen=True)
class BatchPlan:
    batches: tuple[tuple[EntityCard, ...], ...]
    deferred_entity_ids: tuple[str, ...]
    planned_actual_prompt_chars: tuple[int, ...]
    single_entity_prompt_overflow: tuple[str, ...]
    max_input_chars: int

    @property
    def estimated_input_chars(self) -> tuple[int, ...]:
        """Backward-compatible alias for callers that predate exact rendering."""
        return self.planned_actual_prompt_chars


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
    comparative_context_enabled: bool = True,
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
    semantics = compile_target_semantics(task)
    entity_table = [{"entity_id": card.entity_id, **card.features} for card in cards]
    return TaskContext(
        task_id=str(task.get("task_id", "")),
        prompt=str(task.get("prompt", "")),
        target=dict(target),
        cutoff_date=str(task.get("cutoff_date", "")),
        interval_level=float(task.get("interval_level", 0.9)),
        semantics=semantics,
        comparative_context=(
            compile_comparative_context(entity_table, semantics)
            if comparative_context_enabled
            else None
        ),
        cards=tuple(cards),
    )


def plan_batches(
    context: TaskContext,
    *,
    include_evidence: bool,
    max_entities: int,
    max_input_chars: int,
    max_output_chars: int,
    max_primary_requests: int,
) -> BatchPlan:
    """Greedily pack using the exact full request sent to the House client.

    Every candidate batch is rendered through the shared prompt renderer.  A card
    that cannot fit by itself is never sent; it is recorded and deferred to the
    existing deterministic safety fallback.  If the request budget is exhausted,
    remaining entities are deferred through the same path.
    """
    batches: list[tuple[EntityCard, ...]] = []
    planned_chars: list[int] = []
    deferred: list[str] = []
    single_overflow: list[str] = []
    current: list[EntityCard] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        if len(batches) < max_primary_requests:
            batches.append(tuple(current))
            planned_chars.append(current_chars)
        else:
            deferred.extend(card.entity_id for card in current)
        current = []
        current_chars = 0

    def exact_chars(cards: tuple[EntityCard, ...]) -> int:
        return render_task_request(
            context,
            cards,
            include_evidence=include_evidence,
        ).total_chars

    for card in context.cards:
        candidate = tuple([*current, card])
        candidate_chars = exact_chars(candidate)
        candidate_fits = (
            len(candidate) <= max_entities
            and candidate_chars <= max_input_chars
            and len(candidate) * 500 <= max_output_chars
        )
        if candidate_fits:
            current = list(candidate)
            current_chars = candidate_chars
            continue

        if current:
            flush()

        single = (card,)
        single_chars = exact_chars(single)
        if single_chars > max_input_chars:
            single_overflow.append(card.entity_id)
            deferred.append(card.entity_id)
            continue
        if max_entities < 1 or 500 > max_output_chars:
            deferred.append(card.entity_id)
            continue
        current = [card]
        current_chars = single_chars
    flush()

    return BatchPlan(
        batches=tuple(batches),
        deferred_entity_ids=tuple(deferred),
        planned_actual_prompt_chars=tuple(planned_chars),
        single_entity_prompt_overflow=tuple(single_overflow),
        max_input_chars=max_input_chars,
    )
