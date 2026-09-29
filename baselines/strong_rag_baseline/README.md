# Strong RAG baseline — BM25 retrieval + house model over `$MODEL_ENDPOINT`

## Executive summary (read this first)

The track's reference retrieval-augmented agent (Baseline 3 in `../README.md`) retrieves compact
span-level evidence cards for every entity with BM25 (embargo enforced before retrieval), sends
the complete structured table plus batched evidence cards to the house model at
`$MODEL_ENDPOINT`, and turns the model's card IDs and verbatim quotes into claims with **exact
`(doc_id, span_start, span_end)` citations** — model-supplied offsets are never trusted; quotes
are located as verbatim substrings of the corpus, and anything ungroundable is dropped rather
than cited loosely. Classification and regression share this task-level path; ranking compares
the full table and emits globally comparable numeric scores, never per-row optional ranks. One
agent handles all units without family dispatch; it is deterministic given the model pin and seed.

**Status: scaffold.** Fully runnable end-to-end with `--mock` or any local OpenAI-compatible
server; quality acceptance (beats `baseline_agent/`, ≥0.80 faithfulness under the pinned judge)
waits on the staging `$MODEL_ENDPOINT`.

`--mock` is a **wiring check, not a prediction**. It answers from the prompt it is handed:
it quotes a verbatim slice of the top retrieved excerpt, so the quote grounds to a real span
through the same path a real model's quote takes, and every row comes back with at least one
grounded claim. What it does not do is forecast — `point_forecast` is `0.0` except on ranking
units, where a constant vector would be the degenerate answer of public #47. Use it to prove
retrieval → prompt → parse → ground → assemble works end to end; do not read its numbers.

## Run

```bash
# standard interface contract
python -m baselines.strong_rag_baseline.cli \
  --task   units/t4-EXAMPLE-eps-beat/task.json \
  --corpus units/t4-EXAMPLE-eps-beat/corpus \
  --out    /tmp/answer.json

# wiring smoke run without any model server
python -m baselines.strong_rag_baseline.cli --task ... --corpus ... --out ... --mock

# retained controlled ablation; not the submission default
python -m baselines.strong_rag_baseline.cli --task ... --corpus ... --out ... \
  --mock --prediction-mode entity
```

Environment:

| Var | Meaning | Default |
|---|---|---|
| `MODEL_ENDPOINT` | House route origin (harness-injected at scoring time); requests go to `$MODEL_ENDPOINT/v1/chat/completions`. A local URL already ending in `/v1` also works | — (required unless `--mock`) |
| `MODEL_NAME` | model id sent in the request — this is what the harness injects (see `SUBMISSION_CLI.md`, container environment contract) | empty |
| `MODEL_ID` | local-dev fallback for `MODEL_NAME`; read only when `MODEL_NAME` is unset | empty |
| `MODEL_TOKEN` | per-unit bearer credential (harness-injected at scoring time); sent as `Authorization: Bearer` on every request. Optional locally | none |
| `T4_SEED` | seed forwarded to the model | `20260731` |
| `T4_TOP_K` | retrieved chunks per entity | `10` |
| `T4_MODEL_TIMEOUT_S` / `T4_MODEL_RETRIES` | per-call timeout / retry count | `60` / `3` |

Task batching uses bounded defaults for evidence cards, input/output size, and primary requests.
They are deliberately below the published House ceilings; see `config.py` for the executable
values and `docs/PHASE3-TASK-LEVEL-PREDICTION.md` for the measured request budget.

Local model example: `ollama serve` + `MODEL_ENDPOINT=http://localhost:11434/v1 MODEL_ID=qwen2.5:7b`.

## Design

| Module | Role |
|---|---|
| `indexer.py` | One chunk per corpus span; global offsets follow the scorer's join-with-space convention, so every chunk is citation-ready as-is |
| `retriever.py` | Pure-Python Okapi BM25; docs with missing or post-cutoff `doc_date` dropped before scoring; ties break by `(doc_id, span_start)` |
| `client.py` | stdlib HTTP client for `$MODEL_ENDPOINT/v1/chat/completions` with the `MODEL_TOKEN` bearer (temp 0, seed, retries) + `MockModelClient` for tests |
| `prompts.py` | Per-target-type prompt; demands one JSON object with verbatim quotes |
| `span_finder.py` | Locates quotes as exact substrings (length-preserving curly-quote normalization); never trusts model offsets |
| `agent.py` | Orchestration; ungroundable quotes fall back to the source chunk's known-good offsets or are dropped; off-vocabulary labels and missing intervals get deterministic fallbacks |
| `task_context.py` | Complete structured entity table, cutoff-safe evidence cards, and deterministic dynamic batching |
| `task_predictor.py` | Joint classification/regression/ranking prediction, one constrained repair, and local quote-to-offset grounding |
| `formatter.py` | Final answer assembly + hard self-check (spans resolve, intervals complete, `notes` is an object) |

## Competition Docker candidate

The candidate is standard-library only and contains no local neural weights or development NLI
models. Build it from the repository root:

```bash
docker buildx build --platform linux/amd64 \
  -f baselines/strong_rag_baseline/Dockerfile \
  -t t4-task-agent:dev --load .
```

The base is pinned by linux/amd64 manifest digest. The normal harness invocation supplies the
House environment and the leading `analyze` verb. With no endpoint, the same image produces a
complete deterministic fallback rather than shrinking the roster.

**BM25 only, no dense retrieval** (deviation from the Baseline-3 sketch in `../README.md`): the
eval sandbox's restricted network cannot fetch embedding weights at run time, so a lexical index
keeps the agent reproducible everywhere. The binding constraint is build-time vendoring: nothing
can be downloaded at run time, and bundling embedding weights for a dense index is an additional
neural checkpoint under the [artifact policy](../../docs/ARTIFACT-POLICY.md), which needs
organizer approval. The chunking already
targets the corpus's natural citable units (rendered-table NOTES lines, per-span passages),
which recovers much of what dense retrieval would add on these corpora.

## Acceptance (tracked, not yet runnable)

- [ ] Schema PASS + embargo PASS on the public practice unit(s)
- [ ] ≥0.80 citation faithfulness under the pinned judge
- [ ] Predictive quality strictly above `baseline_agent/`
- [ ] Runs as-is on `sample-tasks/track4-analysis/` and passes `evaluation/check_submission.py`

All four wait on the staging `$MODEL_ENDPOINT` and the sample-tasks export.
