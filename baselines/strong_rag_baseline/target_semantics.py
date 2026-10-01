"""Deterministic compilation of trusted task-side target semantics.

The compiler deliberately prefers an explicit unknown over a plausible guess.
It reads only task.json material and never consults evidence or model output.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

SemanticStatus = Literal["resolved", "unknown", "conflict"]


@dataclass(frozen=True)
class SemanticField:
    value: Any
    source: str | None
    status: SemanticStatus
    candidates: tuple[dict[str, Any], ...] = ()

    def prompt_value(self) -> dict[str, Any]:
        value = {"value": self.value, "source": self.source, "status": self.status}
        if self.candidates:
            value["candidates"] = [dict(candidate) for candidate in self.candidates]
        return value


@dataclass(frozen=True)
class LabelAssertion:
    label: str
    text: str
    source: str
    executable: bool
    expression: str | None = None
    operator: str | None = None
    threshold: float | None = None


@dataclass(frozen=True)
class TargetSemantics:
    target_type: SemanticField
    target_name: SemanticField
    target_description: SemanticField
    explicit_unit: SemanticField
    forecast_horizon: SemanticField
    legal_labels: SemanticField
    label_assertions: tuple[LabelAssertion, ...]
    numeric_thresholds: SemanticField
    ranking_direction: SemanticField
    point_meaning: SemanticField
    point_range: SemanticField
    interval_level: SemanticField
    conflicts: tuple[str, ...]

    def prompt_value(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type.prompt_value(),
            "target_name": self.target_name.prompt_value(),
            "target_description": self.target_description.prompt_value(),
            "explicit_unit": self.explicit_unit.prompt_value(),
            "forecast_horizon": self.forecast_horizon.prompt_value(),
            "legal_labels": self.legal_labels.prompt_value(),
            "label_assertions": [
                asdict(assertion) for assertion in self.label_assertions
            ],
            "numeric_thresholds": self.numeric_thresholds.prompt_value(),
            "ranking_direction": self.ranking_direction.prompt_value(),
            "point_meaning": self.point_meaning.prompt_value(),
            "point_range": self.point_range.prompt_value(),
            "interval_level": self.interval_level.prompt_value(),
            "conflicts": list(self.conflicts),
        }


_POINT_EXPRESSION = re.compile(
    r"^point_forecast\s*(<=|>=|<|>|==)\s*(-?(?:\d+(?:\.\d*)?|\.\d+))$",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?\s*%")


def _unknown() -> SemanticField:
    return SemanticField(None, None, "unknown")


def _resolved(value: Any, source: str) -> SemanticField:
    return SemanticField(value, source, "resolved")


def _normalized(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.strip().lower().split())
    return repr(value)


def _choose(candidates: list[tuple[Any, str]]) -> SemanticField:
    candidates = [(value, source) for value, source in candidates if value is not None]
    if not candidates:
        return _unknown()
    distinct: dict[str, tuple[Any, str]] = {}
    for value, source in candidates:
        distinct.setdefault(_normalized(value), (value, source))
    if len(distinct) == 1:
        value, source = next(iter(distinct.values()))
        return _resolved(value, source)
    return SemanticField(
        None,
        None,
        "conflict",
        tuple({"value": value, "source": source} for value, source in candidates),
    )


def _uniform_entity_candidates(
    entities: list[Mapping[str, Any]], keys: tuple[str, ...]
) -> list[tuple[Any, str]]:
    candidates: list[tuple[Any, str]] = []
    for key in keys:
        values = {
            _normalized(entity[key]): entity[key]
            for entity in entities
            if key in entity
        }
        candidates.extend(
            (value, f"entities[].{key}")
            for _, value in sorted(values.items(), key=lambda item: item[0])
        )
    return candidates


def _prompt_unit(prompt: str) -> tuple[str, str] | None:
    patterns = (
        (r"\bin basis points\b", "basis points"),
        (r"\bexpressed as (?:a )?percent\b", "percent"),
        (r"\bin percent\b", "percent"),
        (r"\babnormal return \(%\)", "percent"),
        (r"\bprobability[^.]{0,80}\(0 to 1\)", "probability [0,1]"),
    )
    for pattern, value in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return value, f"task.prompt:{match.group(0)}"
    return None


def _prompt_horizon(prompt: str, cutoff: object) -> tuple[Any, str] | None:
    range_match = re.search(
        r"\bfrom (?:the )?(\d{4}-\d{2}-\d{2})(?:[^.;]{0,90}?)to (?:the )?(\d{4}-\d{2}-\d{2})",
        prompt,
        re.IGNORECASE,
    )
    if range_match:
        return (
            {"start": range_match.group(1), "end": range_match.group(2)},
            f"task.prompt:{range_match.group(0)}",
        )
    duration_match = re.search(
        r"\b(\d+) months after the cutoff(?:[^.;]{0,50}?through (\d{4}-\d{2}-\d{2}))?",
        prompt,
        re.IGNORECASE,
    )
    if duration_match:
        value = {
            "duration": f"{duration_match.group(1)} months",
            "start": cutoff if isinstance(cutoff, str) else "cutoff_date",
            "end": duration_match.group(2),
        }
        return value, f"task.prompt:{duration_match.group(0)}"
    patterns = (
        r"\bquarter ended [A-Za-z]+ \d{1,2}, \d{4}",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)[- ]\d{4} quarter",
        r"\bQ[1-4] FY\d{4}",
        r"\bfor (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4}",
    )
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return match.group(0), f"task.prompt:{match.group(0)}"
    return None


def _prompt_point_meaning(prompt: str) -> tuple[str, str] | None:
    patterns = (
        r"point_forecast\s*=\s*([^.;]+)",
        r"point_forecast of ([^.;]+)",
        r"point forecast of ([^.;]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            value = match.group(1).strip()[:240]
            value = re.split(r"\s+and\s+(?:a\s+)?90%\s+interval", value, maxsplit=1)[0]
            return value, f"task.prompt:{match.group(0)[:120]}"
    return None


def _prompt_ranking_direction(prompt: str) -> tuple[str, str] | None:
    match = re.search(r"rank 1\s*=\s*([^.;]+)", prompt, re.IGNORECASE)
    if not match:
        return None
    phrase = match.group(1).strip()
    lower = phrase.lower()
    if "largest" in lower or "highest" in lower:
        return "higher point_forecast ranks first", f"task.prompt:{match.group(0)}"
    if "smallest" in lower or "lowest" in lower:
        return "lower point_forecast ranks first", f"task.prompt:{match.group(0)}"
    return None


def _compile_assertions(target: Mapping[str, Any]) -> tuple[LabelAssertion, ...]:
    raw = target.get("label_assertions")
    if not isinstance(raw, Mapping):
        return ()
    assertions: list[LabelAssertion] = []
    for label in sorted(raw):
        value = raw[label]
        source = f"target.label_assertions.{label}"
        text = value.get("text") if isinstance(value, Mapping) else value
        expression = value.get("expression") if isinstance(value, Mapping) else value
        if not isinstance(text, str):
            continue
        match = (
            _POINT_EXPRESSION.fullmatch(expression.strip())
            if isinstance(expression, str)
            else None
        )
        assertions.append(
            LabelAssertion(
                label=str(label),
                text=text,
                source=source,
                executable=match is not None,
                expression=expression.strip() if match else None,
                operator=match.group(1) if match else None,
                threshold=float(match.group(2)) if match else None,
            )
        )
    return tuple(assertions)


def _numeric_thresholds(
    target: Mapping[str, Any],
    entities: list[Mapping[str, Any]],
    assertions: tuple[LabelAssertion, ...],
) -> SemanticField:
    values: list[dict[str, Any]] = []
    raw = target.get("numeric_thresholds", target.get("thresholds"))
    if raw is not None:
        values.append(
            {"name": "target", "value": raw, "source": "target.numeric_thresholds"}
        )
    threshold_keys = sorted(
        {
            key
            for entity in entities
            for key in entity
            if "threshold" in str(key).lower()
        }
    )
    for key in threshold_keys:
        candidates = _uniform_entity_candidates(entities, (key,))
        field = _choose(candidates)
        if field.status == "resolved":
            values.append({"name": key, "value": field.value, "source": field.source})
        elif field.status == "conflict":
            return SemanticField(None, None, "conflict", field.candidates)
    for assertion in assertions:
        numbers = (
            (str(assertion.threshold),)
            if assertion.executable and assertion.threshold is not None
            else tuple(
                match.group(0).strip() for match in _PERCENT.finditer(assertion.text)
            )
        )
        if numbers:
            values.append(
                {
                    "name": f"label_assertion.{assertion.label}",
                    "value": list(numbers),
                    "source": assertion.source,
                }
            )
    return (
        _resolved(values, "trusted target threshold fields") if values else _unknown()
    )


def compile_target_semantics(task: Mapping[str, Any]) -> TargetSemantics:
    """Compile target meaning from trusted task-side fields, never from evidence."""
    target = task.get("target") if isinstance(task.get("target"), Mapping) else {}
    entities = [
        entity for entity in task.get("entities", []) if isinstance(entity, Mapping)
    ]
    prompt = task.get("prompt") if isinstance(task.get("prompt"), str) else ""
    conflicts: list[str] = []

    target_type = _choose(
        [
            (task.get("target_type"), "task.target_type"),
            (target.get("type"), "target.type"),
        ]
    )
    target_name = (
        _resolved(target["name"], "target.name")
        if isinstance(target.get("name"), str) and target["name"].strip()
        else _unknown()
    )
    target_description = (
        _resolved(target["description"], "target.description")
        if isinstance(target.get("description"), str) and target["description"].strip()
        else _unknown()
    )

    unit_candidates = [
        (target.get(key), f"target.{key}")
        for key in ("unit", "units")
        if target.get(key) is not None
    ]
    unit_candidates.extend(_uniform_entity_candidates(entities, ("unit", "units")))
    explicit_unit = _choose(unit_candidates)
    if explicit_unit.status == "unknown":
        parsed = _prompt_unit(prompt)
        explicit_unit = _resolved(*parsed) if parsed else explicit_unit

    horizon_candidates = [
        (target.get(key), f"target.{key}")
        for key in ("forecast_horizon", "horizon")
        if target.get(key) is not None
    ]
    horizon_candidates.extend(
        _uniform_entity_candidates(entities, ("forecast_horizon",))
    )
    forecast_horizon = _choose(horizon_candidates)
    if forecast_horizon.status == "unknown":
        parsed = _prompt_horizon(prompt, task.get("cutoff_date"))
        forecast_horizon = _resolved(*parsed) if parsed else forecast_horizon

    labels = target.get("labels")
    legal_labels = (
        _resolved(sorted(set(labels)), "target.labels")
        if isinstance(labels, list)
        and labels
        and all(isinstance(label, str) and label for label in labels)
        else _unknown()
    )
    assertions = _compile_assertions(target)
    thresholds = _numeric_thresholds(target, entities, assertions)

    direction_candidates = [
        (target.get(key), f"target.{key}")
        for key in ("ranking_direction", "direction")
        if target.get(key) is not None
    ]
    ranking_direction = _choose(direction_candidates)
    if ranking_direction.status == "unknown" and target_type.value == "ranking":
        parsed = _prompt_ranking_direction(prompt)
        ranking_direction = _resolved(*parsed) if parsed else ranking_direction

    point_candidates = (
        [(target.get("point_meaning"), "target.point_meaning")]
        if target.get("point_meaning") is not None
        else []
    )
    point_meaning = _choose(point_candidates)
    if point_meaning.status == "unknown":
        parsed = _prompt_point_meaning(prompt)
        point_meaning = _resolved(*parsed) if parsed else point_meaning

    range_candidates: list[tuple[Any, str]] = []
    if target.get("range") is not None:
        range_candidates.append((target.get("range"), "target.range"))
    elif target.get("min") is not None or target.get("max") is not None:
        range_candidates.append(
            ({"min": target.get("min"), "max": target.get("max")}, "target.min/max")
        )
    point_range = _choose(range_candidates)
    if point_range.status == "unknown" and re.search(
        r"probability[^.]{0,80}\(0 to 1\)", prompt, re.IGNORECASE
    ):
        point_range = _resolved({"min": 0.0, "max": 1.0}, "task.prompt:(0 to 1)")

    interval = task.get("interval_level")
    interval_level = (
        _resolved(float(interval), "task.interval_level")
        if isinstance(interval, (int, float))
        and not isinstance(interval, bool)
        and math.isfinite(float(interval))
        else _unknown()
    )

    for name, field in (
        ("target_type", target_type),
        ("explicit_unit", explicit_unit),
        ("forecast_horizon", forecast_horizon),
        ("numeric_thresholds", thresholds),
        ("ranking_direction", ranking_direction),
        ("point_meaning", point_meaning),
        ("point_range", point_range),
    ):
        if field.status == "conflict":
            conflicts.append(name)

    return TargetSemantics(
        target_type=target_type,
        target_name=target_name,
        target_description=target_description,
        explicit_unit=explicit_unit,
        forecast_horizon=forecast_horizon,
        legal_labels=legal_labels,
        label_assertions=assertions,
        numeric_thresholds=thresholds,
        ranking_direction=ranking_direction,
        point_meaning=point_meaning,
        point_range=point_range,
        interval_level=interval_level,
        conflicts=tuple(conflicts),
    )


def _compare(value: float, operator: str, threshold: float) -> bool:
    return {
        "<": value < threshold,
        "<=": value <= threshold,
        ">": value > threshold,
        ">=": value >= threshold,
        "==": value == threshold,
    }[operator]


def consistency_diagnostics(
    semantics: TargetSemantics, predictions: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Non-fatal, deterministic checks justified by compiled trusted semantics."""
    target_type = semantics.target_type.value
    legal = set(semantics.legal_labels.value or [])
    violations: list[dict[str, Any]] = []
    points: list[float] = []
    executable = [
        assertion for assertion in semantics.label_assertions if assertion.executable
    ]
    for row in predictions:
        entity_id = row.get("entity_id")
        raw_point = row.get("point_forecast", row.get("score"))
        point = (
            float(raw_point)
            if isinstance(raw_point, (int, float))
            and not isinstance(raw_point, bool)
            and math.isfinite(float(raw_point))
            else None
        )
        if point is None:
            violations.append({"entity_id": entity_id, "kind": "non_finite_point"})
        else:
            points.append(point)
        if target_type == "classification":
            label = row.get("label")
            if legal and label not in legal:
                violations.append({"entity_id": entity_id, "kind": "illegal_label"})
            if point is not None and executable:
                matching = {
                    assertion.label
                    for assertion in executable
                    if assertion.operator is not None
                    and assertion.threshold is not None
                    and _compare(point, assertion.operator, assertion.threshold)
                }
                if len(matching) == 1 and label not in matching:
                    violations.append(
                        {
                            "entity_id": entity_id,
                            "kind": "point_label_inconsistent",
                            "expected": sorted(matching),
                            "observed": label,
                        }
                    )
        if point is not None and semantics.point_range.status == "resolved":
            bounds = semantics.point_range.value
            if isinstance(bounds, Mapping):
                lo, hi = bounds.get("min"), bounds.get("max")
                if isinstance(lo, (int, float)) and point < float(lo):
                    violations.append(
                        {"entity_id": entity_id, "kind": "below_trusted_range"}
                    )
                if isinstance(hi, (int, float)) and point > float(hi):
                    violations.append(
                        {"entity_id": entity_id, "kind": "above_trusted_range"}
                    )
    ties = len(points) - len(set(points)) if target_type == "ranking" else 0
    return {
        "target_type": target_type,
        "resolved_fields": sum(
            field.status == "resolved"
            for field in (
                semantics.target_type,
                semantics.target_name,
                semantics.target_description,
                semantics.explicit_unit,
                semantics.forecast_horizon,
                semantics.legal_labels,
                semantics.numeric_thresholds,
                semantics.ranking_direction,
                semantics.point_meaning,
                semantics.point_range,
                semantics.interval_level,
            )
        ),
        "unknown_fields": sum(
            field.status == "unknown"
            for field in (
                semantics.target_type,
                semantics.target_name,
                semantics.target_description,
                semantics.explicit_unit,
                semantics.forecast_horizon,
                semantics.legal_labels,
                semantics.numeric_thresholds,
                semantics.ranking_direction,
                semantics.point_meaning,
                semantics.point_range,
                semantics.interval_level,
            )
        ),
        "conflicts": list(semantics.conflicts),
        "unit_status": semantics.explicit_unit.status,
        "ranking_tie_count": ties,
        "violations": violations,
        "violation_count": len(violations),
    }
