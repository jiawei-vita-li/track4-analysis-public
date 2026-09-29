"""Static checks for the competition Docker candidate."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = ROOT / "baselines" / "strong_rag_baseline" / "Dockerfile"


def test_candidate_is_pinned_small_and_implements_the_interface() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    first_from = next(line for line in text.splitlines() if line.startswith("FROM "))
    assert re.fullmatch(r"FROM python:3\.13-slim@sha256:[0-9a-f]{64}", first_from)
    assert 'LABEL qfbench2.interface_version="2.0"' in text
    assert 'ENTRYPOINT ["python", "-m", "baselines.strong_rag_baseline.cli"]' in text
    assert 'CMD ["analyze", "--help"]' in text
    assert "pip install" not in text


def test_candidate_contains_no_model_weights_or_secret_injection() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8").lower()
    forbidden = ("transformers", "torch", "huggingface", "model_token=", "api_key", "secret")
    assert not [term for term in forbidden if term in text]
