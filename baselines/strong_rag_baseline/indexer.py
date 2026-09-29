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
from dataclasses import dataclass
from pathlib import Path

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


def _declared_paths(corpus_dir: Path) -> list[tuple[Path, str]]:
    candidates = [corpus_dir.parent / _MANIFEST_NAME, corpus_dir / _MANIFEST_NAME]
    manifest_path = next((path for path in candidates if path.is_file()), None)
    if manifest_path is None:
        raise ValueError("corpus has no trusted manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("corpus manifest has no files[] array")
    declared: list[tuple[Path, str]] = []
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
        declared.append((corpus_dir / relative[len("corpus/") :], digest))
    if not declared:
        raise ValueError("corpus manifest declares no corpus documents")
    return sorted(declared, key=lambda item: item[0].name)


def build_index(corpus_dir: str | Path) -> IndexedCorpus:
    """Index only digest-verified documents declared by the trusted manifest."""
    corpus_dir = Path(corpus_dir)
    chunks: list[Chunk] = []
    doc_texts: dict[str, str] = {}
    doc_dates: dict[str, str | None] = {}
    for path, expected_digest in _declared_paths(corpus_dir):
        if path.is_symlink():
            raise ValueError(f"declared corpus path is a symlink: {path.name}")
        raw = path.read_bytes()
        observed_digest = hashlib.sha256(raw).hexdigest()
        if observed_digest != expected_digest:
            raise ValueError(f"manifest digest mismatch for {path.name}")
        doc = json.loads(raw.decode("utf-8"))
        doc_id = path.stem
        if doc.get("doc_id", doc_id) != doc_id:
            raise ValueError(f"document doc_id does not match declared path: {path.name}")
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
    return IndexedCorpus(chunks=chunks, doc_texts=doc_texts, doc_dates=doc_dates)
