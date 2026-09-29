#!/usr/bin/env python3
"""Orchestrate the published Track 4 development checks.

This script deliberately delegates validation and faithfulness to the official
toolkit and repository entry points.  It does not implement a substitute judge.
"""

from __future__ import annotations

import argparse
import importlib.resources as resources
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

import jsonschema


_FAITHFULNESS_RE = re.compile(
    r"Faithfulness \(fraction of supported predictions\):\s*([0-9.]+)"
)
_GATE_RE = re.compile(r"^GATE:\s*(PASS|FAIL)\s*$", re.MULTILINE)


def _run(command: Sequence[str], *, cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "runtime_sec": round(time.perf_counter() - started, 3),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _schema_check(answer_path: Path) -> dict[str, Any]:
    try:
        schema_path = (
            resources.files("qfbench2_common") / "schemas" / "analysis.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(answer)
    except Exception as exc:  # the summary must survive a failed check
        return {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"passed": True}


def _find_tool(name: str) -> str | None:
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [executable_dir / name, executable_dir / f"{name}.exe"]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def evaluate(
    *,
    repo: Path,
    unit: Path,
    answer: Path,
    cache_dir: Path,
    run_tests: bool,
) -> dict[str, Any]:
    repo = repo.resolve()
    unit = unit.resolve()
    answer = answer.resolve()
    cache_dir = cache_dir.resolve()
    summary: dict[str, Any] = {
        "unit": str(unit),
        "answer": str(answer),
        "schema": _schema_check(answer),
    }

    qfbench2 = _find_tool("qfbench2")
    smoke = _find_tool("qfbench2-smoke")
    if not qfbench2 or not smoke:
        missing = [name for name, value in (("qfbench2", qfbench2), ("qfbench2-smoke", smoke)) if not value]
        summary["tooling"] = {"passed": False, "error": f"missing executables: {', '.join(missing)}"}
        return summary
    summary["tooling"] = {"passed": True}

    manifest = _run([qfbench2, "manifest", "assert-public-safe", str(unit)], cwd=repo)
    manifest["passed"] = manifest["returncode"] == 0
    summary["manifest"] = manifest

    with tempfile.TemporaryDirectory(prefix="t4-eval-") as temporary:
        output_dir = Path(temporary)
        shutil.copyfile(answer, output_dir / "answer.json")
        smoke_result = _run(
            [smoke, str(unit), str(output_dir), "--track", "analysis"], cwd=repo
        )
    smoke_result["passed"] = (
        smoke_result["returncode"] == 0 and "admissible=True" in smoke_result["stdout"]
    )
    summary["smoke"] = smoke_result
    # The smoke verifier delegates these checks to the official schema/alignment/corpus gates.
    summary["roster_cutoff_citations"] = {"passed": smoke_result["passed"]}

    judge = _run(
        [
            sys.executable,
            str(repo / "faithfulness" / "judge.py"),
            "--answer",
            str(answer),
            "--unit",
            str(unit),
            "--cache-dir",
            str(cache_dir),
        ],
        cwd=repo,
    )
    combined = judge["stdout"] + "\n" + judge["stderr"]
    score_match = _FAITHFULNESS_RE.search(combined)
    gate_match = _GATE_RE.search(combined)
    judge["score"] = float(score_match.group(1)) if score_match else None
    judge["gate"] = gate_match.group(1) if gate_match else None
    judge["passed"] = judge["returncode"] == 0 and judge["gate"] == "PASS"
    summary["faithfulness"] = judge

    if run_tests:
        tests = _run([sys.executable, "-m", "pytest", "-q"], cwd=repo)
        tests["passed"] = tests["returncode"] == 0
        summary["tests"] = tests

    required = ["schema", "tooling", "manifest", "smoke", "roster_cutoff_citations", "faithfulness"]
    if run_tests:
        required.append("tests")
    summary["passed"] = all(summary[name].get("passed") is True for name in required)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", type=Path, required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--tests", action="store_true", help="also run the repository test suite")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    summary = evaluate(
        repo=repo,
        unit=args.unit,
        answer=args.answer,
        cache_dir=args.cache_dir,
        run_tests=args.tests,
    )
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
