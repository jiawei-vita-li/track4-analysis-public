"""Controlled P0-P3 engineering ablation for the public Track 4 units.

Public units have no resolved outcomes, so this script measures contract,
request, latency, citation, and ranking-coherence properties only.  It does not
report accuracy, MAE, or a ranking metric.
"""
from __future__ import annotations

import argparse
import importlib.resources as resources
import json
import math
import sys
import time
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.strong_rag_baseline.cli import _mock_reply, run  # noqa: E402
from baselines.strong_rag_baseline.client import MockModelClient  # noqa: E402
from baselines.strong_rag_baseline.indexer import build_index  # noqa: E402


def _contract_metrics(unit: Path, answer: dict) -> dict:
    task = json.loads((unit / "task.json").read_text(encoding="utf-8"))
    corpus = build_index(unit / "corpus")
    schema_path = resources.files("qfbench2_common") / "schemas" / "analysis.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_ok = True
    try:
        jsonschema.Draft202012Validator(schema).validate(answer)
    except jsonschema.ValidationError:
        schema_ok = False

    trusted = [entity["entity_id"] for entity in task["entities"]]
    rows = answer.get("entity_predictions") or []
    citation_ok = True
    cutoff_ok = True
    for row in rows:
        for claim in row.get("claims") or []:
            text = corpus.doc_texts.get(claim.get("doc_id"))
            date = corpus.doc_dates.get(claim.get("doc_id"))
            start, end = claim.get("span_start"), claim.get("span_end")
            citation_ok = citation_ok and (
                isinstance(text, str)
                and isinstance(start, int)
                and isinstance(end, int)
                and 0 <= start < end <= len(text)
            )
            cutoff_ok = cutoff_ok and isinstance(date, str) and date <= task["cutoff_date"]

    points = [row.get("point_forecast") for row in rows]
    finite_points = all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        for value in points
    )
    target_type = task["target"]["type"]
    return {
        "schema": schema_ok,
        "roster_complete": [row.get("entity_id") for row in rows] == trusted,
        "citation_spans": citation_ok,
        "cutoff": cutoff_ok,
        "finite_points": finite_points,
        "point_diversity": len(set(points)),
        "ranking_consistent": (
            target_type != "ranking"
            or (finite_points and len(set(points)) == len(points) and all("rank" not in row for row in rows))
        ),
    }


def _run_variant(unit: Path, output_dir: Path, name: str, **kwargs) -> dict:
    client = MockModelClient(_mock_reply)
    answer_path = output_dir / unit.name / name / "answer.json"
    trace_path = output_dir / unit.name / name / "trace.json"
    started = time.perf_counter()
    answer = run(
        unit / "task.json",
        unit / "corpus",
        answer_path,
        client,
        top_k=10,
        trace_path=trace_path,
        **kwargs,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    fallback_count = sum(bool(entity.get("fallback_used")) for entity in trace["entities"])
    return {
        "variant": name,
        "request_count": client.request_count,
        "latency_ms": round(elapsed_ms, 3),
        "batch_count": trace.get("task_prediction", {}).get("batch_count"),
        "entities_per_batch": trace.get("task_prediction", {}).get("entities_per_batch"),
        "estimated_input_chars": trace.get("task_prediction", {}).get("estimated_input_chars"),
        "fallback_count": fallback_count,
        **_contract_metrics(unit, answer),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=Path, default=REPO / "units")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "limitations": (
            "Public units have no outcomes; no predictive-quality or calibration claim is made."
        ),
        "units": {},
    }
    for unit in sorted(path for path in args.units.iterdir() if (path / "task.json").is_file()):
        p0 = _run_variant(unit, args.out, "P0-entity", prediction_mode="entity")
        p1 = _run_variant(
            unit,
            args.out,
            "P1-task-structured",
            prediction_mode="task",
            include_evidence=False,
        )
        p2 = _run_variant(
            unit,
            args.out,
            "P2-task-evidence",
            prediction_mode="task",
            include_evidence=True,
        )
        # P3 repeats P2 through the mandatory sanitizer/preflight and atomic
        # writer.  Equality with P2 under a well-formed reply is a determinism
        # check; malformed-output recovery is covered separately in unit tests.
        p3 = _run_variant(
            unit,
            args.out,
            "P3-final-safety",
            prediction_mode="task",
            include_evidence=True,
        )
        p2_answer = json.loads(
            (args.out / unit.name / "P2-task-evidence" / "answer.json").read_text(encoding="utf-8")
        )
        p3_answer = json.loads(
            (args.out / unit.name / "P3-final-safety" / "answer.json").read_text(encoding="utf-8")
        )
        p3["matches_p2_answer"] = p3_answer == p2_answer
        report["units"][unit.name] = [p0, p1, p2, p3]

    summary = []
    for variant in ("P0-entity", "P1-task-structured", "P2-task-evidence", "P3-final-safety"):
        rows = [
            row
            for unit_rows in report["units"].values()
            for row in unit_rows
            if row["variant"] == variant
        ]
        summary.append(
            {
                "variant": variant,
                "units": len(rows),
                "requests": sum(row["request_count"] for row in rows),
                "max_requests_per_unit": max(row["request_count"] for row in rows),
                "all_schema": all(row["schema"] for row in rows),
                "all_rosters": all(row["roster_complete"] for row in rows),
                "all_citations": all(row["citation_spans"] for row in rows),
                "all_cutoff": all(row["cutoff"] for row in rows),
                "all_ranking_consistent": all(row["ranking_consistent"] for row in rows),
                "fallbacks": sum(row["fallback_count"] for row in rows),
                "latency_ms": round(sum(row["latency_ms"] for row in rows), 3),
            }
        )
    report["summary"] = summary
    report_path = args.out / "ablation-summary.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
