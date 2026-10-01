"""Corpus indexer: one retrievable chunk per corpus span, with global offsets.

Corpus documents carry their text as a ``spans`` array (or a flat ``text``
field). The scorer's offset convention concatenates span texts with a single
space, so a span that starts at position ``p`` in that concatenation can be
cited directly as ``(doc_id, p, p + len(span_text))``. Indexing at span
granularity therefore gives every chunk an exact, citation-ready offset pair
for free — no separate span search needed for chunk-level citations.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

_MANIFEST_NAME = "manifest.json"
_MAX_CHUNK_CHARS = 600
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    doc_date: str | None
    span_start: int  # global char offset into the document's joined text
    span_end: int
    text: str


@dataclass(frozen=True)
class IndexedCorpus:
    chunks: list[Chunk]
    doc_texts: dict[str, str]  # doc_id -> full joined text (for span finding)
    doc_dates: dict[str, str | None]
    doc_entity_ids: dict[str, tuple[str, ...] | None] = field(default_factory=dict)
    shared_doc_ids: frozenset[str] = frozenset()
    labels_present: bool = False
    task_row_ranges: dict[str, tuple[int, int]] = field(default_factory=dict)

    def admits(self, entity_id: str, doc_id: str) -> bool:
        """Match the scorer's manifest ``entity_ids`` / ``shared`` relation."""
        if doc_id == "task":
            return entity_id in self.task_row_ranges
        # Current scorer semantics fail closed when the manifest carries no labels.
        # The task-table fallback remains available, but an unlabelled corpus document
        # is never silently treated as shared.
        if not self.labels_present:
            return False
        return doc_id in self.shared_doc_ids or entity_id in (
            self.doc_entity_ids.get(doc_id) or ()
        )

    def admits_citation(
        self, entity_id: str, doc_id: str, span_start: object, span_end: object
    ) -> bool:
        """Apply entity admission and the scorer's own-row rule for ``doc_id=task``."""
        if not self.admits(entity_id, doc_id):
            return False
        if doc_id != "task":
            return True
        if (
            isinstance(span_start, bool)
            or not isinstance(span_start, int)
            or isinstance(span_end, bool)
            or not isinstance(span_end, int)
        ):
            return True
        row_start, row_end = self.task_row_ranges[entity_id]
        return row_start <= span_start < span_end <= row_end

    def with_task_table(self, task: Mapping) -> "IndexedCorpus":
        """Add the official synthetic ``task`` document without changing BM25 input."""
        if "task" in self.doc_texts:
            raise ValueError("corpus uses reserved doc_id 'task'")
        rows = task.get("entities")
        if not isinstance(rows, list) or not rows:
            raise ValueError("task has no entities[] table")
        lines: list[str] = []
        ranges: dict[str, tuple[int, int]] = {}
        offset = 0
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(
                row.get("entity_id"), str
            ):
                raise ValueError("task entities[] has a row without an entity_id")
            entity_id = row["entity_id"]
            if entity_id in ranges:
                raise ValueError("task entities[] names an entity twice")
            line = json.dumps(row, ensure_ascii=False, separators=(", ", ": "))
            ranges[entity_id] = (offset, offset + len(line))
            lines.append(line)
            offset += len(line) + 1
        text = "\n".join(lines)
        cutoff = task.get("cutoff_date")
        if not isinstance(cutoff, str) or _ISO_DATE.fullmatch(cutoff) is None:
            raise ValueError("task has no canonical cutoff_date")
        task_chunks = [
            Chunk("task", cutoff, start, end, text[start:end])
            for start, end in ranges.values()
        ]
        return IndexedCorpus(
            chunks=[*self.chunks, *task_chunks],
            doc_texts={**self.doc_texts, "task": text},
            doc_dates={**self.doc_dates, "task": cutoff},
            doc_entity_ids={**self.doc_entity_ids, "task": tuple(ranges)},
            shared_doc_ids=self.shared_doc_ids,
            labels_present=self.labels_present,
            task_row_ranges=ranges,
        )


def _iter_span_texts(doc: dict) -> list[str]:
    if isinstance(doc.get("text"), str):
        return [doc["text"]]
    spans = doc.get("spans")
    if isinstance(spans, list):
        return [sp.get("text", "") for sp in spans if isinstance(sp, dict)]
    return []


def _split_text(text: str, base_offset: int) -> list[tuple[int, int, str]]:
    """Split long text at sentence/word boundaries without changing any byte offsets."""
    if len(text) <= _MAX_CHUNK_CHARS:
        return [(base_offset, base_offset + len(text), text)] if text else []
    boundaries = [match.start() for match in _SENTENCE_BREAK.finditer(text)]
    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(text):
        limit = min(start + _MAX_CHUNK_CHARS, len(text))
        choices = [boundary for boundary in boundaries if start < boundary <= limit]
        if choices:
            end = choices[-1]
        elif limit < len(text):
            word_break = text.rfind(" ", start + 1, limit + 1)
            end = word_break if word_break > start else limit
        else:
            end = len(text)
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            chunks.append((base_offset + start, base_offset + end, text[start:end]))
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    return chunks


def _manifest_labels(entry: dict, path: str) -> tuple[tuple[str, ...] | None, bool]:
    """Validate labels exactly as the current official corpus contract does."""
    raw_ids = entry.get("entity_ids")
    raw_shared = entry.get("shared")
    if raw_shared is not None and raw_shared is not True:
        raise ValueError(f"manifest entry {path!r}: shared must be true when present")
    shared = raw_shared is True
    entity_ids: tuple[str, ...] | None = None
    if raw_ids is not None:
        if not isinstance(raw_ids, list) or not all(
            isinstance(value, str) and value for value in raw_ids
        ):
            raise ValueError(
                f"manifest entry {path!r}: entity_ids must be non-empty strings"
            )
        if len(set(raw_ids)) != len(raw_ids):
            raise ValueError(f"manifest entry {path!r}: entity_ids repeats an id")
        entity_ids = tuple(raw_ids)
    if shared and entity_ids:
        raise ValueError(
            f"manifest entry {path!r} cannot be both shared and entity-labelled"
        )
    return entity_ids, shared


def _declared_paths(
    corpus_dir: Path,
) -> list[tuple[Path, str, tuple[str, ...] | None, bool]]:
    candidates = [corpus_dir.parent / _MANIFEST_NAME, corpus_dir / _MANIFEST_NAME]
    manifest_path = next((path for path in candidates if path.is_file()), None)
    if manifest_path is None:
        raise ValueError("corpus has no trusted manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("corpus manifest has no files[] array")
    declared: list[tuple[Path, str, tuple[str, ...] | None, bool]] = []
    for entry in files:
        if not isinstance(entry, dict) or entry.get("role") != "corpus":
            continue
        relative = entry.get("path")
        digest = entry.get("sha256")
        if relative == f"corpus/{_MANIFEST_NAME}":
            continue
        if (
            not isinstance(relative, str)
            or not relative.startswith("corpus/")
            or "/" in relative[len("corpus/") :]
            or not relative.endswith(".json")
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError(f"invalid corpus manifest entry: {entry!r}")
        entity_ids, shared = _manifest_labels(entry, relative)
        declared.append(
            (corpus_dir / relative[len("corpus/") :], digest, entity_ids, shared)
        )
    if not declared:
        raise ValueError("corpus manifest declares no corpus documents")
    return sorted(declared, key=lambda item: item[0].name)


def build_index(corpus_dir: str | Path) -> IndexedCorpus:
    """Index only digest-verified documents declared by the trusted manifest."""
    corpus_dir = Path(corpus_dir)
    chunks: list[Chunk] = []
    doc_texts: dict[str, str] = {}
    doc_dates: dict[str, str | None] = {}
    doc_entity_ids: dict[str, tuple[str, ...] | None] = {}
    shared_doc_ids: set[str] = set()
    labels_present = False
    for path, expected_digest, entity_ids, shared in _declared_paths(corpus_dir):
        if path.is_symlink():
            raise ValueError(f"declared corpus path is a symlink: {path.name}")
        raw = path.read_bytes()
        observed_digest = hashlib.sha256(raw).hexdigest()
        if observed_digest != expected_digest:
            raise ValueError(f"manifest digest mismatch for {path.name}")
        doc = json.loads(raw.decode("utf-8"))
        doc_id = path.stem
        if doc.get("doc_id", doc_id) != doc_id:
            raise ValueError(
                f"document doc_id does not match declared path: {path.name}"
            )
        doc_date = doc.get("doc_date")
        if not isinstance(doc_date, str) or _ISO_DATE.fullmatch(doc_date) is None:
            raise ValueError(f"document has no canonical doc_date: {path.name}")
        try:
            date.fromisoformat(doc_date)
        except ValueError as exc:
            raise ValueError(f"document has invalid doc_date: {path.name}") from exc
        offset = 0
        parts: list[str] = []
        for text in _iter_span_texts(doc):
            for span_start, span_end, chunk_text in _split_text(text, offset):
                chunks.append(
                    Chunk(
                        doc_id=doc_id,
                        doc_date=doc_date,
                        span_start=span_start,
                        span_end=span_end,
                        text=chunk_text,
                    )
                )
            parts.append(text)
            offset += len(text) + 1  # +1 for the joining space
        doc_texts[doc_id] = " ".join(parts)
        doc_dates[doc_id] = doc_date
        doc_entity_ids[doc_id] = entity_ids
        if shared:
            shared_doc_ids.add(doc_id)
        labels_present = labels_present or shared or entity_ids is not None
    return IndexedCorpus(
        chunks=chunks,
        doc_texts=doc_texts,
        doc_dates=doc_dates,
        doc_entity_ids=doc_entity_ids,
        shared_doc_ids=frozenset(shared_doc_ids),
        labels_present=labels_present,
    )
