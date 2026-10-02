"""Single-source rendering for task-level House requests.

The planner and runtime must count the exact same system and user strings.  This
module intentionally depends on context objects only by protocol so importing it
from the batching module cannot create an import cycle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .task_context import EntityCard, TaskContext


TASK_SYSTEM_PROMPT = """\
You are a careful evidence-grounded forecaster. Jointly compare the complete entity table and
predict only the entities in PREDICTION_BATCH. Use only the supplied structured fields and frozen
pre-cutoff evidence. Do not use remembered outcomes or infer post-cutoff facts. Return one JSON
object and no prose. For evidence, select an evidence_id supplied for that same entity and copy a
short verbatim quote from its text. Never invent document IDs or character offsets. Keep all numeric predictions in the
target's own units, and do not copy an unrelated numeric feature merely because it is available.
A structured numeric feature is a predictor, not automatically a candidate output. Treat unknown
compiled semantics as unknown rather than filling them from domain knowledge. For ranking, every
entity score must express the same compiled target quantity on one shared scale.
A related passage is not necessarily support: prefer explicit measurements, guidance, trends,
and comparisons that bear on the prediction."""

_COMPARATIVE_INSTRUCTIONS = """\
 Before assigning final predictions, compare the entities under the same compiled target semantics
and use COMPARATIVE_CONTEXT to establish a shared task-level frame. Relative feature position is
comparison evidence, not a forecast by itself. Never assume that a larger feature value implies a
larger target unless the trusted task semantics explicitly state that relationship. For ranking,
assign every entity score on one common target scale; never use independent local scales."""


@dataclass(frozen=True)
class RenderedTaskRequest:
    """The exact strings passed to ``ModelClient.complete``."""

    system_prompt: str
    user_prompt: str

    @property
    def total_chars(self) -> int:
        return len(self.system_prompt) + len(self.user_prompt)


def task_system_prompt(*, comparative_context_enabled: bool) -> str:
    return (
        TASK_SYSTEM_PROMPT + _COMPARATIVE_INSTRUCTIONS
        if comparative_context_enabled
        else TASK_SYSTEM_PROMPT
    )


def _prediction_shape(target_type: str) -> dict[str, Any]:
    evidence = [{"evidence_id": "supplied ID", "quote": "verbatim substring"}]
    if target_type == "classification":
        return {
            "entity_id": "trusted entity_id",
            "label": "exactly one allowed label",
            "point_forecast": "finite number or null",
            "interval": {"lo": "finite number", "hi": "finite number"},
            "evidence": evidence,
        }
    if target_type == "ranking":
        return {
            "entity_id": "trusted entity_id",
            "score": "finite numeric target value; larger means higher rank",
            "interval": {"lo": "finite number", "hi": "finite number"},
            "evidence": evidence,
        }
    return {
        "entity_id": "trusted entity_id",
        "point_forecast": "finite numeric target value",
        "interval": {"lo": "finite number", "hi": "finite number"},
        "evidence": evidence,
    }


def render_task_prompt(
    context: TaskContext,
    cards: tuple[EntityCard, ...],
    *,
    include_evidence: bool,
    repair: dict[str, Any] | None = None,
) -> str:
    """Render the exact user prompt, with comparative rows local to ``cards``."""
    payload: dict[str, Any] = {
        "task_id": context.task_id,
        "task_prompt": context.prompt,
        "cutoff_date": context.cutoff_date,
        "raw_target": context.target,
        "compiled_target_semantics": context.semantics.prompt_value(),
        "interval_level": context.interval_level,
        "complete_entity_table": context.entity_table,
        "prediction_batch": [
            card.prompt_value(include_evidence=include_evidence) for card in cards
        ],
        "required_output": {
            "predictions": [
                _prediction_shape(context.target.get("type", "classification"))
            ]
        },
    }
    if context.comparative_context is not None:
        payload["comparative_context"] = context.comparative_context.prompt_value(
            entity_ids=(card.entity_id for card in cards)
        )
    if repair is not None:
        payload["repair"] = repair
    instructions = (
        "Return every prediction_batch entity exactly once and no other entity. "
        "Do not output optional rank; ranking is derived globally from numeric score. "
        "Choose one or two evidence entries only from that entity's card; quotes must be exact. "
        "The interval level is fixed by the task and must not be changed."
    )
    return (
        "TASK_CONTEXT_JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n"
        + instructions
    )


def render_task_request(
    context: TaskContext,
    cards: tuple[EntityCard, ...],
    *,
    include_evidence: bool,
    repair: dict[str, Any] | None = None,
) -> RenderedTaskRequest:
    """Render the exact full request used for both planning and execution."""
    comparative_enabled = context.comparative_context is not None
    return RenderedTaskRequest(
        system_prompt=task_system_prompt(
            comparative_context_enabled=comparative_enabled
        ),
        user_prompt=render_task_prompt(
            context,
            cards,
            include_evidence=include_evidence,
            repair=repair,
        ),
    )
