## Executive summary (read this first)

Phase 3 replaces the submission default of one House call per entity with a generic task-level
predictor that sees the complete structured roster and compact, cutoff-safe evidence cards. Across
all 11 public units, the deterministic ablation reduced primary mock calls from 78 to 11, with a
maximum of one call per unit, while every output passed schema, roster, citation-span, cutoff, and
ranking-consistency checks. The worked exemplar still passes the unmodified production
faithfulness ensemble at entity support `0.6082` and overall `1.0000`. The code candidate is ready
for a real container build, but it is **not yet ready for Development upload** because neither
available host has a working Docker daemon, so the required linux/amd64 image build and container
run have not actually been completed. No upload was attempted.

# Phase 3 — Task-level prediction

## A. Design

The prediction path is now:

```text
trusted task + complete entity roster
  -> manifest-verified, pre-cutoff BM25 index
  -> per-entity compact evidence cards
       evidence_id + doc_id + date + exact text span
       offsets remain trusted local metadata
  -> deterministic dynamic batching
       complete structured table repeated in every batch
       only current batch's evidence cards included
  -> task-level House JSON prediction
       classification: legal label
       regression: target-unit point forecast
       ranking: globally comparable numeric score
       one or two evidence IDs + verbatim quotes
  -> local quote-to-offset grounding
  -> existing sanitizer and preflight, unchanged in role
  -> atomic answer.json + optional separate trace.json
```

`TaskContext` is family-agnostic. It is derived only from target metadata, task prompt, trusted
entity fields, and retrieved frozen-corpus text. `family` is not used for dispatch and no public
answer or entity roster is hard-coded.

The complete entity table is always visible to the House model. For rosters that fit, all entities
are predicted in one call. When a batch is necessary, every call still sees the complete table so
it can preserve a common cross-sectional scale; only evidence cards are partitioned. The planner
records estimated input characters, batch count, entities per batch, deferred entities, requests,
latency, raw replies, repair errors, and final per-entity state.

Evidence selection does not ask the model for offsets. The model selects a supplied `evidence_id`
and copies a short exact quote from that card. Local code resolves the quote inside the trusted
chunk and derives `(doc_id, span_start, span_end)`. If a quote is invalid, the known-good card span
is used; if a whole prediction is invalid, the existing deterministic fallback supplies a complete
row.

## B. Code changes

- `task_context.py`: task representation, evidence cards, complete structured table, deterministic
  batching, five-primary-request cap, and explicit overflow deferral.
- `task_predictor.py`: shared task prompt, classification/regression/ranking output contracts,
  robust batch parsing, one constrained repair, exact quote grounding, and task-level trace.
- `cli.py`: task-level mode is now the default; `--prediction-mode entity` retains P0 for controlled
  comparison. It integrates the batch predictor before the frozen sanitizer/preflight path.
- `config.py`: bounded evidence and batching controls. The pre-existing official House ceilings
  remain clamped rather than trusted from environment input.
- `client.py`: mock calls now carry the same request accounting used in experiments.
- `formatter.py` and `safety.py`: a narrow contract bug fix supports both published target-type
  shapes, preferring a top-level `target_type`, and emits/checks the matching answer field.
- `Dockerfile`: standard-library-only linux/amd64 candidate, pinned to the current Python 3.13.15
  slim manifest, with the required interface label and `analyze` entrypoint.
- `scripts/task_level_ablation.py`: outcome-free P0–P3 engineering ablation across every public
  unit.
- Tests cover all three target types, one-call task prediction, request-cap overflow, one repair,
  structured-only mode, exact short quote spans, target-type precedence, trace semantics, and the
  Docker contract.

The manifest validator, cutoff-first index, atomic output, deterministic fallback, schema checks,
and official judge were not bypassed or replaced.

## C. Classification strategy

The prompt carries the legal label vocabulary, full structured table, target semantics, and each
batch entity's evidence cards. The House reply must include every batch entity exactly once and use
an exact trusted label. Invalid, missing, duplicate, and unknown rows make the batch eligible for
the single repair request; if repair fails, the sanitizer restores the complete roster with its
deterministic legal-label fallback.

Classification may include a numeric underlying forecast when the task defines one, but the legal
label is the primary typed output. The interval remains mandatory because the official answer
schema requires it for every target type.

## D. Regression strategy

The House model jointly sees cross-sectional rows and evidence. The prompt explicitly names the
target, requires its own units, and warns against copying an unrelated numeric feature merely
because it is available. A regression row is accepted as a primary result only when its
`point_forecast` is finite. The existing interval and numeric sanitizer remains the final guard.

No learned calibration system was added. Interval generation is still model-proposed with a
deterministic conservative fallback, so no coverage improvement is claimed.

## E. Ranking strategy

Ranking prioritizes a single full-roster call. The House model returns one finite numeric `score`
per entity; local code writes this as `point_forecast`. It never asks for or emits optional `rank`,
so the scored ordering follows the global numeric values and cannot contain a partial or invalid
rank permutation.

If batching becomes necessary, each batch receives the complete entity table and is told to use
the target's absolute units. This is the least-bad generic way to preserve scale without another
normalization call, but cross-batch comparability remains a real risk. The public ranking unit has
10 entities and fit into one call with 25,905 estimated input characters, ten distinct finite
scores, and no optional ranks.

## F. Request budget and recovery

The current official contract was re-read from `SUBMISSION_CLI.md`: 25 admitted requests per unit
and at most 4,000 output tokens per request. The client still charges every attempted retry before
forwarding and has a unit-level deadline below the 600-second card ceiling.

Phase 3 adds these primary limits:

- at most 20 entities per ordinary batch;
- approximately 48,000 input characters and 12,000 expected output characters per batch;
- at most five primary batches per unit;
- at most one constrained repair request for the entire unit;
- overflow entities are deferred to deterministic fallback instead of spending more requests.

Thus the normal successful path is at most five admitted requests and the public set used one per
unit. A transient HTTP failure can still consume configured client retries; this is visible in the
shared request counter. More than half the official slots remain unused in the normal path for
future controlled recovery work.

## G. Controlled ablations

The machine-readable results are in `artifacts/task-level/ablation-summary.json`. Public units do
not ship outcomes, so the experiment makes no accuracy, MAE, ranking-score, or interval-coverage
claim.

| Variant | Units | Total mock requests | Max/unit | Schema | Roster | Citations | Cutoff | Ranking consistency |
|---|---:|---:|---:|---|---|---|---|---|
| P0 entity-by-entity | 11 | 78 | 12 | all pass | all pass | all pass | all pass | pass |
| P1 task structured only | 11 | 11 | 1 | all pass | all pass | all pass | all pass | pass |
| P2 task structured + evidence | 11 | 11 | 1 | all pass | all pass | all pass | all pass | pass |
| P3 final task predictor + safety | 11 | 11 | 1 | all pass | all pass | all pass | all pass | pass |

P1's citations are contract-valid fallback citations because the model intentionally did not see
evidence; this is not a faithfulness claim. P2 and P3 use evidence cards and their final answers
match deterministically under well-formed mock output. P3 additionally names the mandatory final
sanitizer/preflight boundary. Malformed/partial recovery is controlled separately by unit tests.

Every P3 public output passed `qfbench2 manifest assert-public-safe` and the official non-rankable
`qfbench2-smoke`. The worked exemplar then ran through the production two-model judge without any
judge changes:

- entity support: `0.6082` (`PASS`);
- overall faithfulness: `1.0000`;
- gate: `PASS`;
- judge runtime: 12.455 seconds.

An intermediate evidence-ID-only implementation cited the full 442-character card and reduced
support to `0.5404`. Requiring a short verbatim quote, while retaining local offset derivation,
restored `0.6082`. This is evidence for citation specificity, not an NLI reranking objective.

## H. Remaining risks

1. There has been no live admitted House call. Real output compliance, latency, and forecasting
   quality remain unmeasured.
2. Character-count batching is a deterministic approximation, not the House tokenizer. Extremely
   wide entity tables can reach the five-batch cap and force safe fallbacks.
3. Ranking across multiple batches may drift despite sharing the full table and absolute-unit
   instruction. A future repair should be conditional on measured hidden-like failures, not added
   speculatively.
4. Evidence cards are lexical retrieval results. They may be relevant without supporting the
   eventual prediction; the exact-quote path improves specificity but does not prove entailment.
5. Deterministic fallback protects the unit contract but can reduce predictive score and has no
   empirically validated 90% coverage.
6. The public exemplar faithfulness measurement is one entity and cannot estimate hidden-set gate
   stability.
7. The Dockerfile is statically checked and its copied source closure was run in isolation, but a
   real image build remains blocked by the host container daemon.

## I. Exact build and test commands

Build from the repository root when a Docker daemon is available:

```bash
docker buildx build --platform linux/amd64 \
  -f baselines/strong_rag_baseline/Dockerfile \
  -t t4-task-agent:dev --load .

docker image inspect t4-task-agent:dev \
  --format '{{.Architecture}} {{.Os}} {{index .Config.Labels "qfbench2.interface_version"}} {{.Size}}'
```

Offline fallback container check:

```bash
mkdir -p .runs/t4-offline/output
docker run --rm --network=none \
  -v "$PWD/units/t4-cotpos-202411-us10:/input:ro" \
  -v "$PWD/.runs/t4-offline/output:/output" \
  t4-task-agent:dev analyze \
  --task /input/task.json --corpus /input/corpus --out /output/answer.json

qfbench2-smoke units/t4-cotpos-202411-us10 .runs/t4-offline/output --track analysis
```

Wiring mock, which exercises task batching and exact citations without a House endpoint:

```bash
docker run --rm --network=none \
  -v "$PWD/units/t4-cotpos-202411-us10:/input:ro" \
  -v "$PWD/.runs/t4-mock/output:/output" \
  t4-task-agent:dev analyze \
  --task /input/task.json --corpus /input/corpus --out /output/answer.json --mock
```

Repository checks used in this phase:

```bash
python -m pytest -q baselines/strong_rag_baseline/tests
python -m pytest -q \
  --deselect=faithfulness/tests/test_local_check_reads_corpus.py::test_cli_runs_as_a_script_from_the_repo_root \
  --deselect=faithfulness/tests/test_local_check_reads_corpus.py::test_transformers_without_torch_degrades_instead_of_crashing
python scripts/task_level_ablation.py --out /tmp/t4-phase3-ablation
```

Observed results were `48 passed` for the focused suite and `369 passed, 2 deselected` for the
applicable full suite. The unfiltered suite was also run: `369 passed, 2 failed`. Those are the same
two official environment-assumption tests previously documented: one expects an unavailable
`/model-cache` path to reach a verdict, and one simulates Transformers-without-torch while this
production-NLI environment intentionally has real torch installed. The official judge itself
passes with its real cached weights; neither test nor judge was edited.

The Docker base resolves to linux/amd64 manifest
`sha256:37134a49d21d2120e4c4d73bb76f8a4ab9aef31f096f7ec2ead48c2feead4332`.
Its four compressed layers total 43,032,850 bytes (41.04 MiB); agent source adds only standard-library
Python files, far below the published 15 GB recommendation. A copy-closure simulation containing
only the `.py` files selected by the Dockerfile ran the public ranking unit and passed official
smoke.

After a successful build, obtain and publish the immutable image digest, prepare the official
descriptor with category `api` and the organizer-supplied House model disclosure, then package:

```bash
docker push <registry>/<repository>:<tag>
docker buildx imagetools inspect <registry>/<repository>:<tag>
qfbench2 submission pack \
  --descriptor submission.json --team-number <team-number> --out submission.zip
```

Do not put the Team Key, `MODEL_TOKEN`, registry credentials, or local trace files in the image or
descriptor. The Team Key is entered only into the packer's hidden prompt.

## J. Development submission readiness

**NOT READY FOR DEVELOPMENT SUBMISSION.** The code and source closure pass their checks, but the
required real Docker build/run is unverified. The remote GPU host has no Docker/Podman/buildah, and
the local Docker Desktop daemon remains stuck in `starting` with its `docker-desktop` WSL
distribution stopped, even after one clean stop/shutdown/start attempt. No image digest exists yet.

To clear the blocker:

1. restore or provide a working linux/amd64 Docker/BuildKit daemon;
2. execute the exact build, label/architecture/size inspection, offline fallback run, and mock run
   above;
3. preferably make one staging House call to confirm response compatibility and measured latency;
4. rerun official smoke on the container output;
5. only then push by digest and create the descriptor/zip.

No Development leaderboard upload should be made before those checks, and none was made in this
phase.
