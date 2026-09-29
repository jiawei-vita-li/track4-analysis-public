"""Runtime configuration for the strong RAG baseline (env-driven, no files).

Everything is resolved from environment variables so the same agent runs
unchanged in the eval sandbox (where the organizer injects ``$MODEL_ENDPOINT``)
and locally (where you can point it at a mock or an ollama/llama.cpp server
speaking the same OpenAI-compatible protocol).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    model_endpoint: str  # House route origin as injected (http://host:port); a local http://host/v1 also works
    model_id: str
    model_token: str | None
    seed: int  # forwarded to the model AND used for any local tie-breaking
    top_k: int  # retrieved chunks per entity
    timeout_s: float  # per model call
    max_retries: int
    max_requests: int  # official admitted-request ceiling per unit
    max_output_tokens: int
    unit_timeout_s: float  # stop early enough to serialize a fallback answer
    temperature: float  # fixed at 0 for determinism; env override for experiments
    evidence_per_entity: int = 4
    batch_max_entities: int = 20
    batch_max_input_chars: int = 48_000
    batch_max_output_chars: int = 12_000
    max_primary_requests: int = 5

    @staticmethod
    def from_env() -> "Config":
        return Config(
            model_endpoint=os.environ.get("MODEL_ENDPOINT", "").rstrip("/"),
            # MODEL_NAME is what the harness injects (SUBMISSION_CLI.md container
            # contract); MODEL_ID is a local-dev fallback only.
            model_id=os.environ.get("MODEL_NAME") or os.environ.get("MODEL_ID", ""),
            model_token=os.environ.get("MODEL_TOKEN") or None,
            seed=int(os.environ.get("T4_SEED", "20260731")),
            top_k=int(os.environ.get("T4_TOP_K", "10")),
            timeout_s=float(os.environ.get("T4_MODEL_TIMEOUT_S", "60")),
            max_retries=int(os.environ.get("T4_MODEL_RETRIES", "3")),
            max_requests=min(25, max(0, int(os.environ.get("T4_MAX_REQUESTS", "25")))),
            max_output_tokens=min(
                4000, max(1, int(os.environ.get("T4_MAX_OUTPUT_TOKENS", "4000")))
            ),
            unit_timeout_s=min(
                540.0, max(1.0, float(os.environ.get("T4_UNIT_TIMEOUT_S", "540")))
            ),
            temperature=float(os.environ.get("T4_TEMPERATURE", "0")),
            evidence_per_entity=min(
                8, max(1, int(os.environ.get("T4_EVIDENCE_PER_ENTITY", "4")))
            ),
            batch_max_entities=min(
                50, max(1, int(os.environ.get("T4_BATCH_MAX_ENTITIES", "20")))
            ),
            batch_max_input_chars=min(
                100_000, max(8_000, int(os.environ.get("T4_BATCH_MAX_INPUT_CHARS", "48000")))
            ),
            batch_max_output_chars=min(
                14_000, max(2_000, int(os.environ.get("T4_BATCH_MAX_OUTPUT_CHARS", "12000")))
            ),
            max_primary_requests=min(
                5, max(1, int(os.environ.get("T4_MAX_PRIMARY_REQUESTS", "5")))
            ),
        )
