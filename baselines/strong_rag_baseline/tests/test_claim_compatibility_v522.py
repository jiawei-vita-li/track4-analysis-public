"""Regression tests for scorer-5.2.2-compatible extractive claims."""

from __future__ import annotations

from pathlib import Path

import pytest

from baselines.strong_rag_baseline.cli import _mock_reply, run
from baselines.strong_rag_baseline.client import MockModelClient
from baselines.strong_rag_baseline.indexer import Chunk, build_index
from baselines.strong_rag_baseline.task_context import EntityCard, EvidenceItem
from baselines.strong_rag_baseline.task_predictor import (
    _FALLBACK_CLAIM_CHARS,
    _claim_from_card,
)

REPO = Path(__file__).resolve().parents[3]
UNITS = REPO / "units"
GENERIC_FILLER = "This pre-cutoff passage was used as evidence for the prediction."


def _card(text: str, *, start: int = 17, entity_id: str = "SYN-A") -> EntityCard:
    chunk = Chunk(
        doc_id="DOC-1",
        doc_date="2026-01-01",
        span_start=start,
        span_end=start + len(text),
        text=text,
    )
    return EntityCard(
        entity_id=entity_id,
        features={},
        queries=(entity_id,),
        evidence=(EvidenceItem(evidence_id="E1_1", chunk=chunk, score=1.0),),
    )


def test_generic_evidence_filler_is_never_constructed() -> None:
    [claim], _ = _claim_from_card(
        _card("Revenue rose while operating costs declined."),
        {"evidence_ids": ["E1_1"]},
    )
    assert claim["claim"] != GENERIC_FILLER
    assert claim["claim"] == "Revenue rose while operating costs declined."


@pytest.mark.parametrize(
    "quote",
    [
        "Guidance was reduced for the next quarter.",
        "Revenue was 5.2 billion and gross margin was 46 percent.",
        "See https://example.test/releases/2026/10?item=42 for the filing.",
    ],
    ids=["factual", "numeric", "url-numbers"],
)
def test_exact_quote_becomes_the_claim_with_exact_offsets(quote: str) -> None:
    prefix = "Unrelated introduction. "
    card = _card(prefix + quote + " Trailing text.", start=101)
    [claim], used = _claim_from_card(
        card,
        {"evidence": [{"evidence_id": "E1_1", "quote": quote}]},
    )
    assert claim["claim"] == quote
    assert claim["span_start"] == 101 + len(prefix)
    assert claim["span_end"] - claim["span_start"] == len(quote)
    assert used == ["E1_1"]
    assert "citations" not in claim


def test_missing_or_unmatched_quote_falls_back_to_a_short_verbatim_extract() -> None:
    text = ("Demand weakened and management reduced guidance. " * 20).strip()
    card = _card(text)
    for row in (
        {"evidence_ids": ["E1_1"]},
        {"evidence": [{"evidence_id": "E1_1", "quote": "not in the passage"}]},
    ):
        [claim], _ = _claim_from_card(card, row)
        assert claim["claim"] == text[: len(claim["claim"])]
        assert 0 < len(claim["claim"]) <= _FALLBACK_CLAIM_CHARS
        assert claim["span_end"] - claim["span_start"] == len(claim["claim"])
        assert claim["span_end"] - claim["span_start"] <= 8_000


@pytest.mark.parametrize(
    "unit_name,expected_entities",
    [("t4-EXAMPLE-eps-beat", 1), ("t4-cotpos-202411-us10", 10)],
)
def test_one_and_multi_entity_outputs_use_only_flat_verbatim_claims(
    tmp_path: Path, unit_name: str, expected_entities: int
) -> None:
    unit = UNITS / unit_name
    answer = run(
        unit / "task.json",
        unit / "corpus",
        tmp_path / f"{unit_name}.json",
        MockModelClient(_mock_reply),
        top_k=10,
    )
    assert len(answer["entity_predictions"]) == expected_entities
    corpus_text = build_index(unit / "corpus").doc_texts
    for row in answer["entity_predictions"]:
        assert row["claims"]
        for claim in row["claims"]:
            assert set(claim) == {"doc_id", "span_start", "span_end", "claim"}
            cited = corpus_text[claim["doc_id"]][
                claim["span_start"] : claim["span_end"]
            ]
            assert claim["claim"] == cited
            assert len(cited) <= _FALLBACK_CLAIM_CHARS
