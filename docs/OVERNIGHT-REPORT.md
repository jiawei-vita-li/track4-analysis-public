## Executive summary (read this first)

Overnight work produced a submission-safe, task-aware v1 baseline without changing any official
scorer, validator, faithfulness judge, frozen corpus, or canonical-hypothesis code. The official
worked exemplar now passes schema validation, manifest/cutoff checks, the smoke harness, and the
production two-model faithfulness gate. The final strong-mock support score is `0.6082`, identical
to the pre-prompt baseline, with overall faithfulness `1.0000` (`PASS`).

The main durable improvements are: deterministic complete-roster fallbacks for all three target
types; manifest-bound and cutoff-safe corpus indexing; exact-offset chunking; task-derived
multi-query BM25/RRF retrieval; request/deadline/output-token guards; atomic answer writes; strict
preflight validation; and a separate per-entity debug trace. A dev-time NLI reranker raised the
single public exemplar's score from `0.6082` to `0.6480`, but inspection showed it selected a
topically related span that did not actually entail the forecast. It was therefore rejected from
the submission runtime as an NLI false-positive exploit, and Phase 4 recovery was not attempted.

There is no evidence yet for improved hidden-task predictive accuracy or interval calibration:
the public repository exposes only one unresolved classification exemplar. The next highest-value
work is a task-level prediction layer, especially global reasoning for ranking, evaluated on
outcome-bearing held-out units when they become available.

# Overnight development report

## Reproducibility anchor

- Official repository commit: `7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`.
- Development branch: `nightly/t4-agent`.
- Remote checkout: `/root/autodl-tmp/t4-agent`.
- Remote Python: 3.13.15 at `/root/autodl-tmp/t4-py313/bin/python`.
- Toolkit: `qfbench2-common` from official tag `v2.4.4`.
- GPU host: RTX 3080 Ti; PyTorch 2.11.0+cu128 reports CUDA available.
- Cgroup memory limit: 90 GiB. Data disk: `/root/autodl-tmp`.
- NLI cache: `/root/autodl-tmp/hf_cache`; both model blobs matched their expected SHA-256.
- Production judge behavior: the published CLI fixes `device=-1`, so official checks ran on CPU;
  GPU was used only for the explicitly dev-time citation experiment.

Checkpoint commits before this report:

1. `e3d79e2 checkpoint 1: record production faithfulness baseline`
2. `971682c checkpoint 2: add submission safety and eval orchestration`
3. `4b97da4 checkpoint 3: add task-aware retrieval and exact chunking`
4. `2cb4fa2 checkpoint 4: enforce runtime budgets and record NLI ablation`

## Final architecture

```text
task.json
  -> target/schema parser + trusted entity roster
  -> per-entity task-derived queries
       + structured feature names/values
       + prompt and target semantics
  -> manifest-bound corpus index
       -> SHA-256 verification
       -> strict ISO document dates
       -> pre-retrieval cutoff filtering
       -> exact-offset <=600-character chunks
  -> multi-query BM25 -> RRF -> deduplicated top-k spans
  -> House-compatible prediction call
       -> global request/deadline/output-token budget
       -> robust JSON-object extraction
  -> exact-quote claim alignment and filtering
  -> target-aware sanitizer + deterministic complete fallback
  -> preflight contract validation
  -> atomic answer.json write
       + optional separate trace.json
  -> official schema / manifest / smoke / faithfulness checks
```

The submission answer remains free of debug metadata. Trace output records queries, retrieved
document IDs and exact spans, retrieval/model/total latency, raw model response, exception,
fallback use, request count, and final sanitized prediction.

## Checkpoint decisions and evidence

### 1. Production faithfulness baseline

**Bottleneck.** The local Windows/WSL environment could not allocate enough virtual memory for
the published two-DeBERTa ensemble.

**Hypothesis.** An isolated Linux environment with the official models and sufficient RAM would
allow an unmodified production-faithfulness measurement.

**Result.** Both original answers passed:

| Answer | Entity support | Overall | Gate | Warm runtime | Peak RSS | Peak VRAM |
|---|---:|---:|---|---:|---:|---:|
| minimal | 0.5366 | 1.0000 | PASS | 12.440 s | 2879 MiB | 0 MiB |
| strong mock | 0.6082 | 1.0000 | PASS | 12.314 s | 2878 MiB | 0 MiB |

No model, threshold, hypothesis template, or judge behavior was changed. The result proves the
worked-exemplar wiring only; it does not establish hidden-roster faithfulness.

### 2. Submission safety and evaluation orchestration

**Bottleneck.** The original strong baseline could omit an entity after an exception and trusted
model output too directly, exposing the entire unit to schema, roster, numeric, rank, interval,
and citation failures.

**Hypothesis.** A deterministic target-aware sanitizer plus official-check orchestration would
turn per-entity model failures into complete valid answers without masking checker failures.

**Accepted changes.** `scripts/eval_local.py` delegates to the official schema, public-safety
manifest command, smoke harness, and faithfulness judge and emits a JSON summary. The safety layer
enforces the exact trusted roster, legal labels, finite numbers, correct interval level/order,
valid pre-cutoff exact spans, and no unsafe partial rank. Classification, regression, and ranking
have deterministic complete fallbacks. Per-entity failures no longer use `continue` as the final
output policy.

**Impact.** Schema robustness improved directly. Predictive quality and calibration were not
claimed; fallbacks are designed for survival, not optimal score.

### 3. Task-aware retrieval and exact chunking

**Bottleneck.** The official strong query was generic and financially biased, while whole spans
could be too broad for precise support.

**Hypothesis.** Queries derived from task prompt, target semantics, entity identity, and feature
schema, combined by deterministic RRF, would generalize better to unseen families.

**Accepted changes.** Three to five task-derived queries are searched independently with BM25,
deduplicated by `(doc_id, span_start, span_end)`, and fused with RRF. Corpus files are an allow-list
from the manifest and must match SHA-256. Long text is split at sentence/word boundaries while
preserving original character offsets. Documents are filtered by parsed date before retrieval.

**Controlled public ablation.** The only public exemplar was compared with legacy query,
task-aware single query, multi-query RRF, and max-normalized fusion. Every variant had zero cutoff
or span violations. RRF retained a task-relevant guidance span that max-normalized fusion dropped
for a generic services paragraph, so RRF was retained. This is retrieval-behavior evidence, not
accuracy evidence. Public regression/ranking outcomes do not exist; their contracts are covered
with synthetic tests only.

### 4. Runtime guards and dev-time NLI experiment

**Bottleneck.** Network retries and malformed responses could exhaust the official unit budget;
lexical relevance alone does not guarantee support for the canonical prediction hypothesis.

**Accepted runtime changes.** House requests now share a unit-level request counter and deadline;
each attempted URL consumes budget, timeouts are bounded by remaining time, and output tokens are
capped. Defaults are clamped to 25 requests, 4,000 output tokens, and 540 seconds. Model JSON is
decoded by scanning for a valid object rather than a greedy regular expression. Output writes are
atomic.

**Rejected research change.** With the prediction fixed, a dev-only GPU reranker using the
official canonical hypothesis and ensemble increased support from `0.6082` to `0.6480`. Manual
inspection found that it preferred a passage about services margin and iPhone demand, which does
not entail a future EPS beat. Because the numeric gain was a judge false positive rather than
semantic grounding, the reranker is not called by the runtime. Phase 4 verifier-driven recovery
was skipped because its prerequisite—reliable Phase 3 improvement—was not met.

### 5. Strict input handling, generic prompt, and observability

**Bottleneck.** Lexical date comparison, permissive manifest digests, financial-only wording, and
missing diagnostics create avoidable hidden-task risk.

**Hypothesis.** Strict calendar parsing and manifest checks would fail closed on malformed input;
a domain-neutral prompt and separate trace would improve generality and diagnosability without
changing answer schema.

**Accepted changes.** Manifest digests must be 64 lowercase hex characters; declared document
paths cannot be symlinks; document dates must be canonical valid ISO dates; cutoff comparison uses
`date` objects. The prompt now says evidence-grounded forecaster, emphasizes support for canonical
prediction fields, and asks ranking entities only for the metric point forecast because global
ranks cannot be validly assigned in independent calls. Optional `--trace` output is atomic and
separate from `answer.json`.

**Observed result.** Strong-baseline tests passed `37/37`. The final worked-exemplar run retained
the exact `0.6082` support score and passed every official gate, so no measured faithfulness
regression was introduced.

## Exact final commands and results

Strong mock and trace:

```bash
/root/autodl-tmp/t4-py313/bin/python \
  -m baselines.strong_rag_baseline.cli analyze \
  --task units/t4-EXAMPLE-eps-beat/task.json \
  --corpus units/t4-EXAMPLE-eps-beat/corpus \
  --out /root/autodl-tmp/final-smoke/answer.json \
  --trace /root/autodl-tmp/final-smoke/trace.json \
  --mock
```

Result: exit 0; one trusted entity, one grounded claim, no fallback.

Official preflight orchestration:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/root/autodl-tmp/t4-py313/bin/python scripts/eval_local.py \
  --unit units/t4-EXAMPLE-eps-beat \
  --answer /root/autodl-tmp/final-smoke/answer.json \
  --cache-dir /root/autodl-tmp/hf_cache \
  --summary /root/autodl-tmp/final-smoke/eval-summary.json
```

Result:

- schema: pass
- exact roster/cutoff/citation checks: pass
- `qfbench2 manifest assert-public-safe`: pass
- official smoke: admissible
- production faithfulness: entity `0.6082`, overall `1.0000`, gate `PASS`
- faithfulness runtime: 12.552 seconds

The offline variables prevent unreachable Hugging Face metadata probes after the official models
are already cached; they do not change inference or scoring semantics.

Tests:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/root/autodl-tmp/t4-py313/bin/python -m pytest -q \
  --deselect=faithfulness/tests/test_local_check_reads_corpus.py::test_cli_runs_as_a_script_from_the_repo_root \
  --deselect=faithfulness/tests/test_local_check_reads_corpus.py::test_transformers_without_torch_degrades_instead_of_crashing
```

Result: `358 passed, 2 deselected in 36.16s`.

The unfiltered suite was also run and reported `358 passed, 2 failed in 45.38s`. Both failures are
environment-assumption tests in the official judge suite: one assumes absent/offline production
weights still reach a `GATE:` line, and the other simulates importable Transformers without torch
while this GPU environment intentionally has real torch installed. The unmodified official judge
passes with its real cached models. These tests and the judge were not edited to force green.

## Changed files and purpose

- `scripts/eval_local.py`: official-check orchestration and machine-readable summary.
- `baselines/strong_rag_baseline/safety.py`: sanitizer, complete fallbacks, preflight invariants.
- `baselines/strong_rag_baseline/queries.py`: task-derived query construction.
- `baselines/strong_rag_baseline/retriever.py`: multi-query fusion and parsed-date cutoff filter.
- `baselines/strong_rag_baseline/indexer.py`: manifest/digest/date checks and exact chunking.
- `baselines/strong_rag_baseline/client.py`: request/deadline/token budgets.
- `baselines/strong_rag_baseline/agent.py`: robust parsing and per-entity trace data.
- `baselines/strong_rag_baseline/cli.py`: graceful per-entity degradation, atomic outputs, trace CLI.
- `baselines/strong_rag_baseline/prompts.py`: domain-neutral, canonical-support-aware instructions.
- `baselines/strong_rag_baseline/formatter.py`: sanitizer and preflight integration.
- `scripts/retrieval_ablation.py`: retrieval behavior comparison.
- `scripts/rerank_citations.py`: dev-only controlled NLI experiment; not runtime-integrated.
- baseline tests: synthetic classification/regression/ranking and failure-mode coverage.
- `artifacts/phase*` and `artifacts/final`: immutable experiment inputs/outputs/summaries.

## Current bottlenecks, ordered by expected value

1. **Prediction is still primarily one House-compatible call per entity.** Hidden ranking tasks
   need task-level cross-entity reasoning, and all target types need a stronger generic structured
   feature/text fusion policy.
2. **Faithfulness is proven on only one entity.** Retrieval should prioritize explicit forecast,
   guidance, and comparative language, but any learned or NLI reranking must be tested for real
   semantic entailment rather than judge-score gaming.
3. **No outcome-bearing development set exists here.** Predictive changes cannot be selected
   honestly without held-out outcomes across classification, regression, and ranking.
4. **Intervals are schema-safe but not empirically calibrated.** Current fallback widths are
   conservative heuristics; there is no basis to claim 90% coverage.
5. **House API behavior remains an external dependency.** Budget and fallback paths are covered,
   but latency and output quality need an integration run against the admitted competition endpoint.

## Recommended next step

Implement one minimal task-level prediction pass that consumes the full structured entity table
plus compact per-entity evidence summaries and returns point forecasts for every entity in one
schema-constrained response. Derive ranking globally and deterministically from those points, then
send every row through the existing safety/preflight layer. Keep the current per-entity path as a
fallback. Do this only alongside an evaluation fixture or held-out units that can measure roster,
faithfulness, ranking coherence, request count, latency, and—when outcomes are available—predictive
score. This targets the largest architectural gap without weakening the now-stable submission
contract.

## Generalization and regression risks

- More task terms in lexical queries can retrieve prompt-like but non-predictive text; trace review
  and evidence-type features are still needed.
- Strict malformed-date rejection is intentionally fail-closed. It assumes official hidden corpora
  obey the documented canonical date contract.
- Independent entity calls cannot assign globally coherent ranks; omitting optional rank is safer,
  but point forecasts may still be weakly comparable until task-level reasoning is added.
- Deterministic fallbacks prevent unit death but may lower predictive score and have unvalidated
  interval coverage.
- The public NLI result is too small to estimate hidden faithfulness. The rejected reranker shows
  that optimizing the judge score alone can actively reduce true semantic grounding.
