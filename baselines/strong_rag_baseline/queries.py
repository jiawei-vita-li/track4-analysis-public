"""Target-family-agnostic lexical query construction."""

from __future__ import annotations

import re
from collections.abc import Mapping

_TOKEN = re.compile(r"[a-z0-9][a-z0-9._%-]*")
_STOP = {
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "given", "in",
    "is", "of", "on", "or", "predict", "the", "their", "to", "will", "with",
}
_META_FIELDS = {"entity_id", "name", "corpus_ref"}


def _terms(value: object, *, limit: int) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN.findall(str(value).lower()):
        if len(token) < 2 or token in _STOP or token in seen:
            continue
        seen.add(token)
        found.append(token)
        if len(found) >= limit:
            break
    return found


def _join(parts: list[object], *, limit: int = 36) -> str:
    return " ".join(_terms(" ".join(str(part) for part in parts if part), limit=limit))


def build_queries(task: Mapping, entity: Mapping, *, max_queries: int = 5) -> list[str]:
    """Build 3–5 deterministic queries from task semantics and entity fields.

    ``family`` is intentionally not consulted: hidden families need the same
    behavior as public ones.
    """
    target = task.get("target") if isinstance(task.get("target"), Mapping) else {}
    identity = [entity.get(key) for key in ("name", "entity_id", "sector", "description", "series_id")]
    target_terms = [target.get("name"), target.get("type")]
    prompt = task.get("prompt", "")
    feature_names = [key.replace("_", " ") for key in entity if key not in _META_FIELDS]
    textual_values = [
        value
        for key, value in entity.items()
        if key not in _META_FIELDS and isinstance(value, str) and len(value) <= 160
    ]
    numeric_features = [
        f"{key.replace('_', ' ')} {value:g}"
        for key, value in entity.items()
        if key not in _META_FIELDS and isinstance(value, (int, float)) and not isinstance(value, bool)
    ][:6]

    candidates = [
        _join(identity + target_terms),
        _join(identity[:2] + [prompt], limit=42),
        _join(identity[:2] + target_terms + feature_names, limit=42),
        _join(identity[:2] + textual_values, limit=36),
        _join(identity[:2] + target_terms + numeric_features, limit=36),
    ]
    queries: list[str] = []
    for query in candidates:
        if query and query not in queries:
            queries.append(query)
        if len(queries) >= max_queries:
            break
    return queries


def legacy_query(entity: Mapping) -> str:
    """The published strong-baseline query, retained for controlled A/B tests."""
    parts = [str(entity.get(key, "")) for key in ("name", "entity_id", "sector", "series_id", "description")]
    return " ".join(part for part in parts if part) + " results revenue earnings guidance outlook growth"
