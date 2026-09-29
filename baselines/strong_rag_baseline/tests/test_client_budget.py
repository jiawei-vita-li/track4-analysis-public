from __future__ import annotations

import urllib.error

import pytest

from baselines.strong_rag_baseline.client import (
    HTTPModelClient,
    RequestBudgetExceeded,
    UnitDeadlineExceeded,
)
from baselines.strong_rag_baseline.config import Config


def config(**overrides) -> Config:
    values = {
        "model_endpoint": "http://house.invalid",
        "model_id": "house",
        "model_token": None,
        "seed": 1,
        "top_k": 5,
        "timeout_s": 1.0,
        "max_retries": 1,
        "max_requests": 2,
        "max_output_tokens": 4000,
        "unit_timeout_s": 30.0,
        "temperature": 0.0,
    }
    values.update(overrides)
    return Config(**values)


def test_every_failed_http_attempt_consumes_shared_budget(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise urllib.error.URLError("synthetic")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    client = HTTPModelClient(config())

    with pytest.raises(RuntimeError, match="failed after"):
        client.complete("system", "first")
    with pytest.raises(RuntimeError, match="failed after"):
        client.complete("system", "second")
    with pytest.raises(RequestBudgetExceeded, match="budget exhausted"):
        client.complete("system", "third")
    assert client.request_count == 2


def test_request_payload_caps_output_tokens(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def succeed(request, timeout):
        captured["body"] = request.data.decode("utf-8")
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", succeed)
    client = HTTPModelClient(config(max_output_tokens=1234))

    assert client.complete("system", "user") == "ok"
    assert '"max_tokens": 1234' in captured["body"]


def test_expired_unit_deadline_makes_no_request(monkeypatch) -> None:
    monkeypatch.setattr("time.monotonic", lambda: 10.0)
    client = HTTPModelClient(config(unit_timeout_s=0.0))

    with pytest.raises(UnitDeadlineExceeded, match="deadline exhausted"):
        client.complete("system", "user")
    assert client.request_count == 0
