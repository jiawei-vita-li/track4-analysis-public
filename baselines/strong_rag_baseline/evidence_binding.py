"""Entity-aware evidence admission between retrieval and evidence-card creation."""

from __future__ import annotations

from .indexer import Chunk, IndexedCorpus
from .retriever import BM25Index, ScoredChunk


def retrieve_admissible(
    index: BM25Index,
    queries: list[str],
    corpus: IndexedCorpus,
    entity_id: str,
    top_k: int,
) -> list[ScoredChunk]:
    """Keep RRF order while excluding documents that do not admit ``entity_id``.

    The first pass uses the retriever's existing per-query depth of at least ten,
    so an already-valid top-k is byte-for-byte unchanged.  Only when filtering
    creates vacancies do we inspect deeper results; existing admitted candidates
    keep their order and deeper candidates are appended.
    """
    if top_k <= 0:
        return []
    primary_depth = max(top_k, 10)
    primary = index.search_multi(
        queries,
        primary_depth,
        per_query_k=primary_depth,
        fusion="rrf",
    )
    admitted = [hit for hit in primary if corpus.admits(entity_id, hit.chunk.doc_id)][
        :top_k
    ]
    if len(admitted) >= top_k or primary_depth >= len(index.chunks):
        return admitted

    seen = {
        (hit.chunk.doc_id, hit.chunk.span_start, hit.chunk.span_end) for hit in admitted
    }
    deeper = index.search_multi(
        queries,
        len(index.chunks),
        per_query_k=len(index.chunks),
        fusion="rrf",
    )
    for hit in deeper:
        key = (hit.chunk.doc_id, hit.chunk.span_start, hit.chunk.span_end)
        if key in seen or not corpus.admits(entity_id, hit.chunk.doc_id):
            continue
        admitted.append(hit)
        seen.add(key)
        if len(admitted) == top_k:
            break
    return admitted


def task_row_fallback(corpus: IndexedCorpus, entity_id: str) -> Chunk | None:
    """Return the entity's own official task-table row, never another entity's row."""
    row_range = corpus.task_row_ranges.get(entity_id)
    text = corpus.doc_texts.get("task")
    date = corpus.doc_dates.get("task")
    if row_range is None or text is None:
        return None
    start, end = row_range
    if not (0 <= start < end <= len(text)):
        return None
    return Chunk("task", date, start, end, text[start:end])
