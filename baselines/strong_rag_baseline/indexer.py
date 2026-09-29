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
from dataclasses import dataclass
from pathlib import Path

_MANIFEST_NAME = "manifest.json"


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
            or len(digest) != 64
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
        raw = path.read_bytes()
        observed_digest = hashlib.sha256(raw).hexdigest()
        if observed_digest != expected_digest:
            raise ValueError(f"manifest digest mismatch for {path.name}")
        doc = json.loads(raw.decode("utf-8"))
        doc_id = path.stem
        if doc.get("doc_id", doc_id) != doc_id:
            raise ValueError(f"document doc_id does not match declared path: {path.name}")
        doc_date = doc.get("doc_date")
        offset = 0
        parts: list[str] = []
        for text in _iter_span_texts(doc):
            if text:
                chunks.append(
                    Chunk(
                        doc_id=doc_id,
                        doc_date=doc_date,
                        span_start=offset,
                        span_end=offset + len(text),
                        text=text,
                    )
                )
            parts.append(text)
            offset += len(text) + 1  # +1 for the joining space
        doc_texts[doc_id] = " ".join(parts)
        doc_dates[doc_id] = doc_date
    return IndexedCorpus(chunks=chunks, doc_texts=doc_texts, doc_dates=doc_dates)
