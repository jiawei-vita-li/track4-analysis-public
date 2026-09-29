"""OpenAI-compatible chat client for ``$MODEL_ENDPOINT`` (stdlib only).

The eval sandbox's only egress is the organizer-hosted House route. The harness
injects ``MODEL_ENDPOINT`` as the route **origin** (``scheme://host:port``) and the
OpenAI-compatible API is served under ``/v1``, so the request goes to
``$MODEL_ENDPOINT/v1/chat/completions`` with ``Authorization: Bearer $MODEL_TOKEN``
(see the hub's ``docs/HOUSE-MODEL.md``, "Calling the House route"). Locally, any
server speaking that protocol works (ollama, llama.cpp, vLLM) whether its URL is
given with or without the ``/v1`` suffix, and tests inject :class:`MockModelClient`
— same interface, canned replies, no network.

Determinism: temperature 0 and a fixed ``seed`` are sent on every request.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .config import Config


def chat_completions_url(model_endpoint: str) -> str:
    """The chat-completions URL for an endpoint given with or without ``/v1``.

    The harness injects the route origin (no path); local servers are often
    configured as ``http://host:port/v1``. Both resolve to ``.../v1/chat/completions``.
    """
    base = model_endpoint.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base + "/chat/completions"


class ModelClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the assistant message text for one chat exchange."""
        ...


class RequestBudgetExceeded(RuntimeError):
    pass


class UnitDeadlineExceeded(RuntimeError):
    pass


@dataclass
class HTTPModelClient:
    config: Config
    request_count: int = field(init=False, default=0)
    _deadline: float = field(init=False)

    def __post_init__(self) -> None:
        self._deadline = time.monotonic() + self.config.unit_timeout_s

    def _remaining(self) -> float:
        return self._deadline - time.monotonic()

    def complete(self, system: str, user: str) -> str:
        if not self.config.model_endpoint:
            raise RuntimeError(
                "MODEL_ENDPOINT is not set. In the eval sandbox it is injected "
                "by the harness; locally, point it at an OpenAI-compatible "
                "server or use --mock."
            )
        payload = {
            "model": self.config.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
            "seed": self.config.seed,
            "max_tokens": self.config.max_output_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.config.model_token:
            headers["Authorization"] = f"Bearer {self.config.model_token}"
        request = urllib.request.Request(
            chat_completions_url(self.config.model_endpoint),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            remaining = self._remaining()
            if remaining <= 0:
                raise UnitDeadlineExceeded("unit model-call deadline exhausted")
            if self.request_count >= self.config.max_requests:
                raise RequestBudgetExceeded(
                    f"official request budget exhausted ({self.config.max_requests})"
                )
            self.request_count += 1
            try:
                with urllib.request.urlopen(
                    request, timeout=min(self.config.timeout_s, max(0.1, remaining))
                ) as response:
                    body = json.loads(response.read().decode("utf-8"))
                return body["choices"][0]["message"]["content"]
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                sleep_for = min(2**attempt, 8, max(0.0, self._remaining()))
                if sleep_for:
                    time.sleep(sleep_for)
        raise RuntimeError(
            f"model call failed after {self.config.max_retries} attempts"
        ) from last_error


@dataclass
class MockModelClient:
    """Test double: returns canned text, or delegates to a callable."""

    reply: str | Callable[[str, str], str]
    request_count: int = field(init=False, default=0)

    def complete(self, system: str, user: str) -> str:
        self.request_count += 1
        if callable(self.reply):
            return self.reply(system, user)
        return self.reply
