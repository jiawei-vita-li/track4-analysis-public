## Executive summary (read this first)

This phase anchors development to official repository commit
`7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491` and shared toolkit v2.4.4. The minimal baseline runs
end to end, emits a schema-valid answer, and passes the non-rankable official smoke harness on the
worked exemplar. The strong RAG mock also passes the same wiring checks, but it is explicitly not
a prediction-quality baseline. Repository tests produced 324 passes and one local environment
failure; the same official production judge was subsequently run on the remote 90 GiB development
host. Both minimal and strong-mock answers pass the production faithfulness gate with the pinned
two-model ensemble. No scorer, judge, validator, corpus, or baseline implementation was changed.

# Phase 1 — Understanding, Baseline Run, and Development Framework

## Environment and exact source

- Official repository: `https://github.com/Agenthon-2026/track4-analysis-public.git`
- Checked commit: `7b2bce1d80d96f5d5667d7f67bfaa945fa5d1491`
- Shared toolkit: `qfbench2-common==2.4.4`, tag v2.4.4
- Track scorer package: `qfbench2-track-analysis==3.1.0`
- Native development Python: 3.13.3
- POSIX validation Python: 3.13.15 in an isolated Ubuntu 24.04 WSL1 distribution
- NLI dependencies installed: Transformers 5.17.0 and PyTorch 2.14.0+cpu

The Windows global Git configuration had `core.autocrlf=true`, which changed frozen input bytes
while leaving ordinary Git diffs empty. The repository-local setting is now
`core.autocrlf=false`, and tracked files were rematerialized from the exact Git blobs. The exemplar
manifest hashes then matched. This is an environment fix, not a content change.

## Commands and observed results

### Minimal baseline

```powershell
.\.venv\Scripts\python.exe baselines\baseline_agent.py analyze `
  --task units\t4-EXAMPLE-eps-beat\task.json `
  --corpus units\t4-EXAMPLE-eps-beat\corpus `
  --out artifacts\phase1\minimal\answer.json
```

Result: exit 0; one AAPL row was written. The answer predicted `inline`, point forecast `1.5`,
interval `[-26498.5, 26501.5]`, and cited characters 0–240 of the pre-cutoff 8-K.

Schema validation against the toolkit's `analysis.schema.json` returned `schema ok`. The Linux
official smoke harness returned:

```text
[t4-EXAMPLE-eps-beat] factory=build_smoke_verifier admissible=True score=None labels=[]
```

`score=None` and `build_smoke_verifier` are expected: public units contain no resolved outcome,
and the smoke lexical judge is deliberately non-rankable and does not enforce the production
faithfulness threshold.

### Strong RAG wiring mock

```bash
/opt/agenthon-venv/bin/python -m baselines.strong_rag_baseline.cli analyze \
  --task units/t4-EXAMPLE-eps-beat/task.json \
  --corpus units/t4-EXAMPLE-eps-beat/corpus \
  --out artifacts/phase1/strong-mock/answer.json --mock
```

Result: exit 0; one entity and one exact-span grounded claim. The official smoke harness again
returned `admissible=True`, `score=None`. The mock predicted `beat` with point `0.0`; the baseline
README correctly warns that these numbers are not forecasts.

### Manifest/public-safety check

```bash
/opt/agenthon-venv/bin/qfbench2 manifest assert-public-safe \
  units/t4-EXAMPLE-eps-beat
```

Result: `OK public-safe units/t4-EXAMPLE-eps-beat`.

### Repository tests

```bash
/opt/agenthon-venv/bin/python -m pytest \
  scoring faithfulness baselines/tests baselines/strong_rag_baseline/tests tests -q
```

Result: `324 passed, 1 failed`. The single failure was
`test_call_kwargs_bind_against_the_real_pipeline_signature`, during `import torch`, with
`ImportError: libtorch_cpu.so: failed to map segment from shared object`. At that moment Windows
reported about 0.25 GB free virtual memory. This is an environment-capacity failure before the
test assertion and does not demonstrate a repository defect.

### Production faithfulness judge

The official command was attempted first on native Windows and failed for two platform reasons:

1. the CLI opened UTF-8 JSON using the GBK system default; `PYTHONUTF8=1` corrected that invocation;
2. the official corpus loader uses POSIX `O_DIRECTORY` and `dir_fd`, which Windows does not expose.

The local Linux attempt reached model loading but failed with
`MemoryError: Cannot allocate memory (os error 12)` because Windows exposed only 1,154 MB free
virtual memory to WSL. The exact answers were then evaluated, without modifying the judge, on a
90 GiB remote Linux development host. Both official weights were cached on the data disk and their
SHA-256 digests matched their Hugging Face blob identifiers.

The official CLI has no device flag and constructs its local ensemble with `device=-1`, so these
production-compatible measurements used CPU inference even though the host has an RTX 3080 Ti:

| Answer | Entity support | Overall faithfulness | Gate | Warm-cache runtime | Peak RSS | Peak VRAM |
|---|---:|---:|---|---:|---:|---:|
| minimal | 0.5366 | 1.0000 | PASS | 12.440 s | 2879 MiB | 0 MiB |
| strong-mock | 0.6082 | 1.0000 | PASS | 12.314 s | 2878 MiB | 0 MiB |

These are one-entity exemplar results, not evidence that either baseline will remain faithful on
larger hidden rosters. They do establish a real production-NLI baseline rather than substituting
the lexical smoke proxy.

## Accurate Track 4 contract

### Input

Each unit supplies `task.json` plus a frozen corpus. The task contains a cross-sectional entity
table, a target schema (`classification`, `regression`, or `ranking`), prompt, cutoff and interval
level. The manifest declares the trusted corpus documents. Official execution invokes:

```text
analyze --task /input/task.json --corpus /input/corpus --out /output/answer.json
```

Open internet is unavailable. The only permitted egress is the audited House model endpoint; the
budget is 25 admitted requests per unit and at most 4,000 output tokens per request.

### Output

`answer.json` names the task and contains exactly one prediction for every trusted roster entity.
Every row needs the target-appropriate prediction, a finite interval with the card's exact level,
and at least one citation/claim. Regression and ranking require `point_forecast`; classification
requires an allowed `label`. Ranking is scored from metric values in `point_forecast`, not from the
optional `rank`; if `rank` is supplied, it must be a complete `1..n` permutation.

### Scoring

- Classification: exact-label accuracy in `[0, 1]`.
- Regression: `clamp(1 - MAE / baseline_MAE, 0, 1)`, where `baseline_MAE` comes from predicting
  the cross-entity mean of the realized values for that unit.
- Ranking: Spearman correlation on `point_forecast`, rescaled as `(rho + 1) / 2`; ties use average
  ranks, a constant vector scores 0.5, and fewer than two rows also scores 0.5.
- Numeric-outcome composite:
  `0.7 * predictive_quality - 0.3 * abs(interval_coverage - interval_level)`.
- Pure-label outcomes drop the calibration leg and score `0.7 * predictive_quality`.

There is no interval-width or sharpness reward. Coverage is measured over every roster entity and
should approach the declared level, normally 0.90.

### Gates

- Schema gate: validates the published JSON schema. The later alignment/domain checks also enforce
  exact roster equality, finite target-appropriate values, label vocabulary, interval level/order,
  non-empty citations, and optional-rank consistency.
- Cutoff/resource gate: binds the answer to the task id; runtime/network/time/resource controls are
  applied by the harness. Citation embargo is enforced in domain semantics by resolving every
  citation through the trusted manifest and refusing unresolved, undated, malformed, or
  post-cutoff evidence.
- Faithfulness gate: for each roster entity, the scorer creates one canonical hypothesis from the
  submitted label/value/rank/interval and trusted task/entity names. An entity is supported when at
  least one of its spans has ensemble score above 0.5. At least 80% of roster entities must be
  supported. Participant claim prose is not the hypothesis and does not affect the denominator.

Any participant failure takes the committed worst unit score, normally `-0.27`, and remains in the
aggregate denominator. Missing/malformed output, schema failure, task/target mismatch, incomplete
or duplicated roster, invalid label/rank/number/interval, empty claims, bad or stale citations, and
faithfulness below threshold all fail the unit rather than merely losing partial credit. A
container crash, nonzero exit, or timeout also prevents a valid output from reaching scoring.

## Current baseline architecture and weaknesses

```text
minimal:
task -> glob corpus JSON -> whole-document lexical overlap -> EPS regex/rules
     -> fixed/uninformative interval -> first 240-character citation -> answer

strong scaffold:
task -> glob corpus JSON -> one chunk per supplied span/flat document -> BM25 Top-K
     -> one House request per entity -> JSON parse -> verbatim quote locator
     -> deterministic field fallbacks -> answer self-check
```

The highest-risk weaknesses are:

1. **Faithfulness objective mismatch.** Strong RAG asks the model for attractive factual claim
   prose but never reranks spans against the canonical prediction hypothesis, which also includes
   the interval. Exact offsets prove provenance, not entailment.
2. **Corpus/retrieval generalization.** Both agents glob files instead of binding to manifest
   entries. Strong RAG ignores `corpus_ref`, uses an earnings-biased query suffix for every family,
   and treats a flat-text document as one large chunk. It has no per-document diversity control.
3. **Prediction generalization.** Minimal logic is EPS-specific and otherwise returns a vocabulary
   fallback/zero. Strong RAG relies entirely on one row-at-a-time LLM call; it has no cross-entity
   ranking synthesis and no evidence-aware numerical fallback.
4. **Runtime/contract robustness.** One House request per entity can exceed the 25-request budget.
   Retries can consume more slots; an endpoint or JSON exception aborts the whole run; empty
   grounded evidence can produce schema-invalid claims; rank values are not globally repaired.
5. **Calibration.** Minimal intervals scale from the largest arbitrary entity number (market cap
   created a ±26,500 EPS band). Strong intervals are uncalibrated LLM output with a generic
   ±50%/1 fallback. Neither learns target-scale residual quantiles.

## Hidden-set guidance

The published eleven units are format examples, not a family roster. Hidden tasks are larger and
mostly use families absent from the public set. Generalization therefore depends on parsing target
semantics and units, retaining unknown feature columns, manifest-bound cutoff-safe retrieval,
target-type-specific typed output, complete rosters, global ranking consistency, request batching,
and graceful fallback. Dispatching on public `family` strings, EPS keys, or known outcomes is both
fragile and contrary to the rules. Counterfactual corpora make real-world priors especially risky.

## Recommended roadmap, ordered by benefit and risk

1. **Contract/preflight layer — highest benefit, low modeling risk.** Typed task parser,
   manifest-bound corpus loader, exact roster builder, finite-number/rank/interval validation,
   atomic output, deadline/request budgets, and deterministic complete fallback.
2. **Offset-safe generic chunking and retrieval — high benefit, low-to-medium risk.** Chunk flat
   text without altering canonical offsets; target-aware queries, entity scoping, and diversity.
3. **Faithfulness-aware prediction/evidence loop — highest gate benefit, medium risk.** Construct
   the official canonical hypothesis locally and select or repair predictions based on support for
   that hypothesis, not claim prose.
4. **Batched generic House reasoning — predictive benefit, medium risk.** Typed JSON, all target
   types, cross-entity ranking, evidence-only prompts, strict parsing, and graceful fallback within
   25 requests/600 seconds.
5. **Eligible interval calibration — useful but data-dependent.** Add target-scale heuristic bands
   first; consider disclosed quantile artifacts only after cutoff-safe training data and held-out
   evidence demonstrate better coverage.

## First implementation recommendation

Implement the contract/preflight layer first. It directly protects the user's top priority and is
independent of House-model quality: exact roster coverage, manifest-only pre-cutoff documents,
finite predictions, valid intervals, exact spans, optional-rank repair, request/deadline accounting,
and an atomic complete fallback. This creates a stable shell in which retrieval and prediction
experiments can fail locally without turning an entire hidden unit into `-0.27`.

The detailed module design is in `docs/COMPETITION-AGENT-V1.md`.
