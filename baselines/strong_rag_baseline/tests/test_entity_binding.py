"""Focused controls for scorer-5.2.2 entity-aware evidence binding."""

from __future__ import annotations

import pytest

from baselines.strong_rag_baseline.agent import EntityResult
from baselines.strong_rag_baseline.evidence_binding import retrieve_admissible
from baselines.strong_rag_baseline.indexer import Chunk, IndexedCorpus
from baselines.strong_rag_baseline.retriever import BM25Index
from baselines.strong_rag_baseline.safety import (
    ContractError,
    preflight,
    sanitize_results,
)
from baselines.strong_rag_baseline.task_context import build_task_context
from baselines.strong_rag_baseline.task_predictor import _claim_from_card


def _chunk(
    doc_id: str, text: str = "entity signal improved", date: str = "2024-01-01"
) -> Chunk:
    return Chunk(doc_id, date, 0, len(text), text)


def _corpus(
    chunks: list[Chunk],
    labels: dict[str, tuple[str, ...] | None],
    *,
    shared: frozenset[str] = frozenset(),
) -> IndexedCorpus:
    return IndexedCorpus(
        chunks=chunks,
        doc_texts={chunk.doc_id: chunk.text for chunk in chunks},
        doc_dates={chunk.doc_id: chunk.doc_date for chunk in chunks},
        doc_entity_ids=labels,
        shared_doc_ids=shared,
        labels_present=True,
    )


def _task(target_type: str = "classification") -> dict:
    target = {"name": "outcome", "type": target_type}
    if target_type == "classification":
        target["labels"] = ["yes", "no"]
    return {
        "task_id": f"binding-{target_type}",
        "schema_version": "3",
        "prompt": "Predict the outcome.",
        "cutoff_date": "2024-02-01",
        "interval_level": 0.9,
        "target": target,
        "entities": [{"entity_id": "A", "feature": 1.0}],
    }


def test_entity_specific_document_is_admitted_and_wrong_entity_is_filtered() -> None:
    wrong, right = _chunk("A_WRONG"), _chunk("Z_RIGHT")
    corpus = _corpus([wrong, right], {"A_WRONG": ("B",), "Z_RIGHT": ("A",)})
    hits = retrieve_admissible(
        BM25Index(corpus.chunks, "2024-02-01"), ["entity signal"], corpus, "A", 2
    )
    assert [hit.chunk.doc_id for hit in hits] == ["Z_RIGHT"]


def test_explicitly_shared_document_is_admitted() -> None:
    shared = _chunk("MARKET")
    corpus = _corpus([shared], {"MARKET": None}, shared=frozenset({"MARKET"}))
    hits = retrieve_admissible(
        BM25Index(corpus.chunks, "2024-02-01"), ["signal"], corpus, "A", 1
    )
    assert [hit.chunk.doc_id for hit in hits] == ["MARKET"]


def test_empty_entity_ids_admits_no_entity() -> None:
    peer = _chunk("PEER")
    corpus = _corpus([peer], {"PEER": ()})
    assert not retrieve_admissible(
        BM25Index(corpus.chunks, "2024-02-01"), ["signal"], corpus, "A", 1
    )


def test_multi_entity_manifest_document_admits_each_listed_entity() -> None:
    joint = _chunk("JOINT")
    corpus = _corpus([joint], {"JOINT": ("A", "B")})
    index = BM25Index(corpus.chunks, "2024-02-01")
    assert retrieve_admissible(index, ["signal"], corpus, "A", 1)
    assert retrieve_admissible(index, ["signal"], corpus, "B", 1)
    assert not retrieve_admissible(index, ["signal"], corpus, "C", 1)


def test_no_admissible_corpus_evidence_uses_only_own_task_row() -> None:
    peer = _chunk("PEER")
    task = _task()
    corpus = _corpus([peer], {"PEER": ("B",)}).with_task_table(task)
    context = build_task_context(
        task,
        BM25Index([peer], task["cutoff_date"]),
        corpus,
        evidence_per_entity=4,
    )
    [item] = context.cards[0].evidence
    assert item.chunk.doc_id == "task"
    assert corpus.admits_citation(
        "A", "task", item.chunk.span_start, item.chunk.span_end
    )


@pytest.mark.parametrize("target_type", ["classification", "regression", "ranking"])
def test_all_target_families_keep_entity_admission(target_type: str) -> None:
    valid = _chunk("VALID", f"outcome {target_type} feature evidence")
    task = _task(target_type)
    corpus = _corpus([valid], {"VALID": ("A",)}).with_task_table(task)
    context = build_task_context(
        task,
        BM25Index([valid], task["cutoff_date"]),
        corpus,
        evidence_per_entity=1,
    )
    assert context.target["type"] == target_type
    assert context.cards[0].evidence[0].chunk.doc_id == "VALID"


def test_exact_quote_and_offsets_survive_entity_filtering() -> None:
    wrong = _chunk("WRONG", "wrong outcome classification feature")
    right = _chunk(
        "RIGHT", "Outcome classification: the exact entity signal improved materially."
    )
    task = _task()
    corpus = _corpus([wrong, right], {"WRONG": ("B",), "RIGHT": ("A",)})
    context = build_task_context(
        task,
        BM25Index(corpus.chunks, task["cutoff_date"]),
        corpus,
        evidence_per_entity=1,
    )
    card = context.cards[0]
    quote = "entity signal improved"
    claims, _ = _claim_from_card(
        card,
        {"evidence": [{"evidence_id": card.evidence[0].evidence_id, "quote": quote}]},
    )
    [claim] = claims
    assert claim["doc_id"] == "RIGHT"
    assert right.text[claim["span_start"] : claim["span_end"]] == quote


def test_cutoff_and_entity_filters_both_apply() -> None:
    late = _chunk("LATE", date="2024-03-01")
    wrong = _chunk("WRONG")
    valid = _chunk("VALID")
    corpus = _corpus(
        [late, wrong, valid],
        {"LATE": ("A",), "WRONG": ("B",), "VALID": ("A",)},
    )
    hits = retrieve_admissible(
        BM25Index(corpus.chunks, "2024-02-01"), ["entity signal"], corpus, "A", 3
    )
    assert [hit.chunk.doc_id for hit in hits] == ["VALID"]


def test_final_preflight_rejects_wrong_entity_and_sanitizer_records_event() -> None:
    wrong, right = _chunk("WRONG"), _chunk("RIGHT", "right evidence")
    task = _task("regression")
    corpus = _corpus([wrong, right], {"WRONG": ("B",), "RIGHT": ("A",)})
    result = EntityResult(
        prediction={
            "entity_id": "A",
            "point_forecast": 1.0,
            "interval": {"level": 0.9, "lo": 0.0, "hi": 2.0},
            "claims": [
                {
                    "doc_id": "WRONG",
                    "span_start": 0,
                    "span_end": len(wrong.text),
                    "claim": wrong.text,
                }
            ],
        },
        dropped_claims=0,
        model_raw="{}",
        trace={},
    )
    repaired = sanitize_results(task, [result], corpus)
    assert repaired[0].prediction["claims"][0]["doc_id"] == "RIGHT"
    assert result.trace["entity_binding_violations"][0]["doc_id"] == "WRONG"

    invalid_answer = {
        "task_id": task["task_id"],
        "entity_predictions": [result.prediction],
    }
    with pytest.raises(ContractError, match="invalid citation"):
        preflight(task, invalid_answer, corpus)
