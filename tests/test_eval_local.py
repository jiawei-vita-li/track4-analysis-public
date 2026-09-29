from __future__ import annotations

import json
from pathlib import Path

import scripts.eval_local as eval_local


def test_schema_check_accepts_published_example(tmp_path: Path) -> None:
    source = Path("templates/answer.example.json")
    answer = tmp_path / "answer.json"
    answer.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    assert eval_local._schema_check(answer) == {"passed": True}


def test_schema_check_reports_malformed_json(tmp_path: Path) -> None:
    answer = tmp_path / "answer.json"
    answer.write_text("{", encoding="utf-8")

    result = eval_local._schema_check(answer)

    assert result["passed"] is False
    assert result["error"].startswith("JSONDecodeError:")


def test_run_preserves_failure_output(monkeypatch, tmp_path: Path) -> None:
    class Completed:
        returncode = 7
        stdout = "out"
        stderr = "err"

    monkeypatch.setattr(eval_local.subprocess, "run", lambda *args, **kwargs: Completed())

    result = eval_local._run(["tool", "arg"], cwd=tmp_path)

    assert result["returncode"] == 7
    assert result["stdout"] == "out"
    assert result["stderr"] == "err"
    assert json.dumps(result)


def test_find_tool_prefers_current_python_environment(monkeypatch, tmp_path: Path) -> None:
    python = tmp_path / "python"
    tool = tmp_path / "qfbench2"
    python.write_text("", encoding="utf-8")
    tool.write_text("", encoding="utf-8")
    monkeypatch.setattr(eval_local.sys, "executable", str(python))
    monkeypatch.setattr(eval_local.shutil, "which", lambda name: None)

    assert eval_local._find_tool("qfbench2") == str(tool)
