"""Deterministic cross-entity summaries from the trusted structured table.

The representation describes relative feature position, never target direction.
Explicit unit conflicts disable comparisons instead of being guessed through.
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .target_semantics import TargetSemantics

COMPARATIVE_CONTEXT_VERSION = "1"
_UNIT_FIELD = re.compile(r"(?:^|_)(?:unit|units|currency|scale)$", re.IGNORECASE)
_MISSING = object()


@dataclass(frozen=True)
class NumericFeatureSummary:
    feature_name: str
    source: str
    valid_count: int
    missing_count: int
    median: float
    minimum: float
    maximum: float

    def prompt_value(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "source": self.source,
            "valid_count": self.valid_count,
            "missing_count": self.missing_count,
            "median": self.median,
            "min": self.minimum,
            "max": self.maximum,
        }

    def compact_prompt_value(self) -> dict[str, Any]:
        """Prompt fields that add comparison information beyond the entity table."""
        return {
            "feature_name": self.feature_name,
            "valid_count": self.valid_count,
            "missing_count": self.missing_count,
            "median": self.median,
            "min": self.minimum,
            "max": self.maximum,
        }


@dataclass(frozen=True)
class RelativeNumericFeature:
    feature_name: str
    source: str
    raw_value: float
    ordinal_rank: float
    percentile: float
    relation_to_median: str

    def prompt_value(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "source": self.source,
            "raw_value": self.raw_value,
            "ordinal_rank": self.ordinal_rank,
            "percentile": self.percentile,
            "relation_to_median": self.relation_to_median,
        }


@dataclass(frozen=True)
class EntityRelativeFeatures:
    entity_id: str
    features: tuple[RelativeNumericFeature, ...]

    def prompt_value(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "relative_numeric_features": {
                feature.feature_name: {
                    "ordinal_rank": feature.ordinal_rank,
                    "percentile": feature.percentile,
                    "relation_to_median": feature.relation_to_median,
                }
                for feature in self.features
            },
        }


@dataclass(frozen=True)
class SkippedNumericFeature:
    feature_name: str
    source: str
    reason: str

    def prompt_value(self) -> dict[str, str]:
        return {
            "feature_name": self.feature_name,
            "source": self.source,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ComparativeContext:
    version: str
    numeric_features_considered: tuple[str, ...]
    numeric_features: tuple[NumericFeatureSummary, ...]
    skipped_numeric_features: tuple[SkippedNumericFeature, ...]
    per_entity_relative_features: tuple[EntityRelativeFeatures, ...]

    @property
    def comparison_count(self) -> int:
        return sum(len(entity.features) for entity in self.per_entity_relative_features)

    def prompt_value(
        self, *, entity_ids: Iterable[str] | None = None
    ) -> dict[str, Any]:
        """Return compact global summaries plus batch-local relative records.

        Statistics and ranks were compiled against the complete trusted roster.
        ``entity_ids`` only filters which already-computed relative rows are repeated
        in the current prediction request.
        """
        included = None if entity_ids is None else set(entity_ids)
        return {
            "version": self.version,
            "numeric_features": [
                feature.compact_prompt_value() for feature in self.numeric_features
            ],
            "per_entity_relative_features": [
                entity.prompt_value()
                for entity in self.per_entity_relative_features
                if entity.features
                and (included is None or entity.entity_id in included)
            ],
            "interpretation": (
                "Ranks are ascending within the same feature (1 = lowest). "
                "They do not imply better, worse, or target direction."
            ),
        }

    def trace_value(self) -> dict[str, Any]:
        return {
            "comparative_context_version": self.version,
            "numeric_features_considered": list(self.numeric_features_considered),
            "numeric_features_compared": [
                feature.feature_name for feature in self.numeric_features
            ],
            "numeric_feature_summaries": [
                feature.prompt_value() for feature in self.numeric_features
            ],
            "numeric_features_skipped": [
                feature.feature_name for feature in self.skipped_numeric_features
            ],
            "skipped_feature_details": [
                feature.prompt_value() for feature in self.skipped_numeric_features
            ],
            "skip_reasons": {
                feature.feature_name: feature.reason
                for feature in self.skipped_numeric_features
            },
            "per_entity_relative_features": {
                entity.entity_id: [
                    feature.prompt_value() for feature in entity.features
                ]
                for entity in self.per_entity_relative_features
            },
            "comparison_count": self.comparison_count,
        }


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _numeric_candidate(values: Sequence[object]) -> bool:
    present = [value for value in values if value is not _MISSING]
    return bool(present) and (
        any(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in present
        )
        or all(value is None for value in present)
    )


def _unit_conflicts(
    entities: Sequence[Mapping[str, Any]], semantics: TargetSemantics
) -> tuple[str, ...]:
    conflicts: set[str] = set()
    if semantics.explicit_unit.status == "conflict":
        conflicts.add("compiled_target_semantics.explicit_unit")
    unit_fields = sorted(
        {
            str(key)
            for entity in entities
            for key in entity
            if _UNIT_FIELD.search(str(key))
        }
    )
    for field_name in unit_fields:
        values = {
            " ".join(str(entity[field_name]).strip().lower().split())
            for entity in entities
            if field_name in entity and entity[field_name] not in (None, "")
        }
        if len(values) > 1:
            conflicts.add(f"entities[].{field_name}")
    return tuple(sorted(conflicts))


def _average_rank(value: float, values: Sequence[float]) -> float:
    less = sum(candidate < value for candidate in values)
    equal = sum(candidate == value for candidate in values)
    return 1.0 + less + (equal - 1) / 2.0


def compile_comparative_context(
    entity_table: Sequence[Mapping[str, Any]], semantics: TargetSemantics
) -> ComparativeContext:
    """Compile same-field comparisons without assigning predictive meaning."""
    entities = [dict(entity) for entity in entity_table]
    feature_names = sorted(
        {
            str(key)
            for entity in entities
            for key in entity
            if key != "entity_id" and not _UNIT_FIELD.search(str(key))
        }
    )
    candidates = tuple(
        feature_name
        for feature_name in feature_names
        if _numeric_candidate(
            [entity.get(feature_name, _MISSING) for entity in entities]
        )
    )
    unit_conflicts = _unit_conflicts(entities, semantics)
    summaries: list[NumericFeatureSummary] = []
    skipped: list[SkippedNumericFeature] = []
    relatives: dict[str, list[RelativeNumericFeature]] = {
        str(entity.get("entity_id", "")): []
        for entity in sorted(entities, key=lambda row: str(row.get("entity_id", "")))
    }

    for feature_name in candidates:
        source = f"entities[].{feature_name}"
        observations = [
            (str(entity.get("entity_id", "")), _finite(entity.get(feature_name)))
            for entity in entities
        ]
        finite = [
            (entity_id, value) for entity_id, value in observations if value is not None
        ]
        if not finite:
            skipped.append(
                SkippedNumericFeature(feature_name, source, "no_finite_values")
            )
            continue
        if len(finite) < 2:
            skipped.append(
                SkippedNumericFeature(
                    feature_name, source, "insufficient_finite_values"
                )
            )
            continue
        if unit_conflicts:
            skipped.append(
                SkippedNumericFeature(
                    feature_name,
                    source,
                    "conflicting_unit_metadata:" + ",".join(unit_conflicts),
                )
            )
            continue

        values = [value for _, value in finite]
        median = float(statistics.median(values))
        summaries.append(
            NumericFeatureSummary(
                feature_name=feature_name,
                source=source,
                valid_count=len(values),
                missing_count=len(entities) - len(values),
                median=median,
                minimum=min(values),
                maximum=max(values),
            )
        )
        for entity_id, value in finite:
            rank = _average_rank(value, values)
            relation = (
                "below" if value < median else "above" if value > median else "near"
            )
            relatives.setdefault(entity_id, []).append(
                RelativeNumericFeature(
                    feature_name=feature_name,
                    source=source,
                    raw_value=value,
                    ordinal_rank=rank,
                    percentile=round((rank - 1.0) / (len(values) - 1.0), 6),
                    relation_to_median=relation,
                )
            )

    per_entity = tuple(
        EntityRelativeFeatures(
            entity_id=entity_id,
            features=tuple(sorted(features, key=lambda feature: feature.feature_name)),
        )
        for entity_id, features in sorted(relatives.items())
    )
    return ComparativeContext(
        version=COMPARATIVE_CONTEXT_VERSION,
        numeric_features_considered=candidates,
        numeric_features=tuple(summaries),
        skipped_numeric_features=tuple(skipped),
        per_entity_relative_features=per_entity,
    )
