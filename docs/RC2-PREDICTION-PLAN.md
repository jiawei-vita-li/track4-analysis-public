## Executive summary (read this first)

RC2 targets prediction quality while preserving RC1 as an immutable fallback. The current agent
has a sound submission envelope, but its predictive layer is essentially one generic House prompt
plus unsafe per-row fallbacks; there is no outcome-based evidence that it improves accuracy,
regression error, ranking correlation, or interval score. Current official scoring is scorer
5.2.1: prediction and raw interval quality are measured relative to the unit's declared naive
rule, and interval quality above 0.5 is capped by predictive quality. RC2 will begin with a
target-semantics and comparative-reasoning improvement that needs no external training data.
Until a cutoff-compatible labelled evaluation set exists, every result in this plan carries the
verdict **NO PREDICTIVE QUALITY CLAIM**.

# Scope and source of truth

The audited code is RC1 commit `0c288e4b775c84ac354c3765cb00974314efc48e`. Runtime behavior is
defined by `baselines/strong_rag_baseline/`, especially `task_context.py`, `task_predictor.py`,
`queries.py`, `retriever.py`, `agent.py`, `safety.py`, and `cli.py`. The public units under
`units/` contain no outcomes and are used only for inference-only behavioral checks.

Rules were rechecked against current upstream `origin/main` at commit
`fe313cee2865fbfbe47b65a8fcf7b830a40ea141` on 2026-09-30, plus toolkit
`qfbench2-common 2.5.1` and the current Hub documents `docs/DEVELOPMENT-RUNTIME.md` and
`docs/HOUSE-MODEL.md`. The current scorer identifies itself as 5.2.1; the immutable details and
the 5.2.0 to 5.2.1 diff are pinned in `docs/RULES-SNAPSHOT-2026-09-30-v521.md`. Relative to RC1,
current public classification tasks add trusted `target.label_assertions`; the generic RC1 prompt
already passes the complete target object through, but it does not turn those assertions into an
explicit decision procedure.

The current scorer implications are:

- classification is roster-wide label accuracy, then piecewise anchored so the declared naive
  rule scores 0.5;
- regression is `naive_MAE / (naive_MAE + submission_MAE)`, with any missing/non-finite graded
  value reducing the unit prediction leg to zero;
- ranking is rescaled Spearman correlation, then anchored to the stronger of the declared naive
  rule and the information-free constant rule;
- a scored interval leg first computes
  `raw_iq = naive_IS / (naive_IS + submission_IS)`, then scores
  `iq = min(raw_iq, max(0.5, predictive_quality))`; coverage is diagnostic rather than the scored
  term, and interval tricks cannot substitute for weak point predictions;
- scorer 5.2.1 retains the per-claim false-claim penalty introduced in 5.2.0 instead of the
  retired 80% faithfulness admission threshold. Structural schema, roster, citation-resolution,
  and cutoff failures remain fatal.

# Current prediction pipeline

```text
task.json
  -> manifest-verified corpus and cutoff-filtered BM25 index
  -> per-entity lexical queries and top-4 RRF evidence cards
  -> TaskContext: raw target object + full structured entity table
  -> batches: full table repeated, evidence only for entities being predicted
  -> one House JSON response per batch; at most one repair request per unit
  -> label / point forecast / ranking score + model-selected evidence IDs and quotes
  -> local quote-to-offset grounding
  -> deterministic sanitizer for missing/invalid rows, values, intervals, and claims
  -> preflight and atomic answer.json
```

# Required ten-question audit

## 1. How classification is generated

The House model sees the task prompt, the full `target` object, the complete entity table, and
evidence cards for the current batch. It returns one exact allowed label per entity and may return
a numeric `point_forecast`. `_row_failures` rejects an out-of-vocabulary label and permits one
unit-wide repair. If the row remains absent or invalid, `sanitize_results` chooses `labels[0]`.
There is no local check that a probability-like point is in range, that it agrees with the label,
or that the interval and label threshold are mutually consistent. In the wiring mock, every
classification entity receives the first declared label; this is a mock limitation, but it
demonstrates the exact majority/default-collapse shape that the production fallback has.

## 2. Where a regression point forecast comes from

On the primary path it is the House model's raw finite `point_forecast`; there is no deterministic
numeric model, unit conversion, or local anchor. On fallback, `_fallback_point` chooses a numeric
feature whose field-name tokens overlap the target name; if none overlaps, it returns the median
of every numeric field in the entity row. This can mix dates, identifiers, percentages, yields,
prices, and levels and therefore can produce a finite but dimensionally meaningless answer.

## 3. How a ranking score is generated

The House model returns a finite `score` for every entity; local code stores it as
`point_forecast` and deliberately emits no optional `rank`. All entities normally fit one batch,
so the model can compare the full table. There is no local normalization, pairwise comparison,
rank-to-score conversion, or cross-batch scale correction. The wiring mock copies the first
numeric feature and adds a roster-position epsilon, proving non-ties but not predictive ranking.

## 4. How structured features enter the prompt

Every non-metadata entity field is copied verbatim into `complete_entity_table`. The current
batch repeats the same entity fields inside `prediction_batch[].features`. Field names and values
are not typed, normalized, unit-checked, winsorized, differenced, or converted into cross-sectional
statistics. This preserves information but delegates all schema interpretation to one prompt.

## 5. How evidence enters the prompt

`build_queries` creates up to five lexical queries from entity identity, task prompt, target name
and type, feature names, short text values, and up to six numeric features. Span-level BM25 results
are fused by reciprocal rank and the top four chunks per entity become evidence cards containing
an ID, document ID, date, and exact text. The model selects one or two IDs and verbatim quotes;
offsets stay in trusted metadata. If it selects nothing, `_claim_from_card` silently chooses the
first card, and if its quote is absent or invalid the whole known-good chunk is cited. Those paths
preserve citation validity but do not establish that the model used or was supported by the text.

## 6. Which public units clearly depend on fallback

No honest claim can be made about live House fallback frequency because no admitted House run is
available. In an explicit no-endpoint failure injection, all 78 entities across all 11 public
units used deterministic fallback; every unit attempted the one repair before sanitation. In the
well-formed mock run, reported sanitizer fallback was zero, but structured-only R1 still attached
the top evidence card to every entity even though the mock never saw evidence. The latter is an
implicit citation fallback that the current trace does not count.

## 7. Which units have no point-forecast diversity

Under the wiring mock, 10 of 11 public units have point diversity 1: every classification and
regression unit emits zero for every row, and the one-entity exemplar is necessarily constant.
Only `t4-cotpos-202411-us10` has ten distinct mock scores, created by first-feature copying plus an
epsilon. These are wiring diagnostics, not observations of House behavior and not evidence of
forecast quality.

## 8. Which tasks do not use cross-sectional information

The House path can see the complete table for all task types, but no deterministic component
actually computes cross-sectional information. Retrieval, fallback points, fallback labels,
interval repair, and citation repair operate independently per entity. Ranking therefore depends
entirely on the House model for global comparison; regression has no cross-sectional anchor; and
classification has no task-level class prior or explicit compare-then-decide stage. Repeating the
full table in a prompt is access to cross-sectional data, not evidence that it was used.

## 9. How intervals are generated

The House model proposes `lo` and `hi`; local code accepts any finite ordered pair and replaces
the level with the trusted task level. Missing or invalid bounds become a symmetric interval about
the point with half-width `max(abs(point) * 0.5, 1.0)`. There is no target-scale model,
heteroskedasticity estimate, empirical residual distribution, or legal calibration dataset. The
fallback was designed to avoid schema failure, not to beat the current official naive interval on
mean interval score. Under scorer 5.2.1, even a raw interval improvement is capped at
`max(0.5, predictive_quality)`, so interval optimization is downstream of point-prediction quality.

## 10. Modules with no predictive-quality evidence

There is no labelled, cutoff-compliant evidence for the task-level prompt, query construction,
BM25 top-k, evidence-card count, target-unit instruction, House temperature/seed choice,
classification label selection, regression values, ranking scores, interval widths, repair prompt,
or deterministic fallback. Existing tests and ablations establish contract behavior only. The
worked exemplar's earlier NLI result was evidence about citation plumbing, not prediction quality.

For claim text, scorer 5.2.1 treats equivalent fractions, spelled-out amounts, and glued unit
forms as the same number; excludes additional date/index/rule shapes; applies exact scale-aware
and direction-aware own-value exemptions; and recognizes a scored interval's `±` half-width and
its level beside interval wording. Claim generation must either quote the cited span verbatim or
check every written number under these current rules. Styling a claim does not improve support.

# Classification, regression, and ranking failure audit

## Classification

- Legal labels are passed through, and current `label_assertions` are available when supplied by
  the task, but the prompt does not require a label-by-label evidence table or a threshold check.
- The fallback is always the first allowed label, so a primary failure produces complete default
  collapse regardless of features or evidence.
- A classification row can carry a label, numeric point, and interval that imply different
  outcomes. Only vocabulary and finiteness/schema checks are local.
- The mock produced one label across every multi-entity classification unit: `credit_event` for
  8/8, `up` for 6/6 and 12/12, and `positive_reaction` for 3/3. This is **not** an accuracy result.

## Regression

- Primary values are entirely model-authored. The warning not to copy an unrelated feature is an
  instruction, not an executable unit check.
- The no-endpoint fallback exposed dimensional errors: for example it can select the median of
  unrelated numerics when no target-name token matches a field.
- No regression unit has a task-level anchor, residual formulation, or comparison against the
  official naive rule exposed to the participant. RC2 cannot inspect the private naive answer, so
  it must build only legitimate pre-cutoff anchors from the supplied task.
- Mock point diversity was 1 for every regression unit. Again, this measures the stub, not House
  prediction quality.

## Ranking

- One full-roster call is the strongest part of the current predictor, but score meaning and scale
  are unconstrained beyond “larger means higher”.
- Multiple batches would have independent score scales even though each sees the same table.
- No pairwise consistency, permutation-equivariance, or batch-scale test is part of inference.
- The mock's ten distinct scores are mostly the first numeric feature plus roster epsilon; a
  non-tied vector is necessary but far from sufficient for Spearman skill.

# Measured outcome-free behavior

The existing R0–R3 mock ablation was rerun across all 11 public units at RC1. R0 made 78 requests;
each task-level variant made 11 total requests, one per unit. Every variant passed schema, exact
roster, citation-span, cutoff, and ranking-consistency checks, with zero reported sanitizer
fallbacks on well-formed mock replies. P3 prompt estimates ranged from 3,587 to 40,422 characters.
No mock parse failure occurred. A separate no-endpoint injection caused 78/78 entity fallbacks and
two failure records per unit (primary plus repair). All measurements are inference-only
engineering evidence.

**NO PREDICTIVE QUALITY CLAIM.** Public outcomes were neither obtained nor reconstructed.

# Legal evaluation and training policy

## Inference-only evaluation

May use official public tasks and frozen corpora without outcomes. Measure schema, roster, cutoff,
citation validity, request count, fallback count, parse failures, output and label diversity,
ranking score diversity, evidence selection, prompt size, latency, permutation equivariance, and
controlled sensitivity to synthetic feature perturbations. These tests can reject broken behavior
but cannot establish accuracy uplift.

## Offline training

Do not train in this phase. A later learned artifact is permitted only after a provenance register
shows that every feature and label was publicly available before every official task cutoff on
which the artifact will be used. Observation date is not enough; first public availability and
label release date control eligibility. The artifact must also comply with `docs/ARTIFACT-POLICY.md`.

## Model selection

Do not select prompts, thresholds, features, or algorithms using a public task's later-resolved
outcome. A legal future strategy is rolling-origin evaluation on separate historical tasks: for a
deployment cutoff `T`, every training and selection label must have a documented availability
date no later than `T`. Splits and metrics must be fixed before reading held-out labels.

## Interval calibration

Treat calibration as fitting, not as harmless post-processing. Residuals or quantiles used to set
widths must have label-availability dates no later than the relevant task cutoff. Until such a
dataset is documented, compare only interval validity, width diversity, monotonicity, and behavior
under synthetic perturbations; do not claim calibrated 90% coverage or interval-score uplift.

## Required external-data register

Before any external data is collected, create `ARTIFACT_PROVENANCE.md` with one row per source and
these fields: source, immutable version/checksum, license, release date, first availability date,
label availability date, intended use (`fitting`, `selection`, or `calibration`), compatible task
cutoffs, and exclusion rationale where compatibility cannot be proved. “Unknown” means unusable,
not provisionally allowed.

# RC2 ablation design

| Variant | Definition | Purpose |
|---|---|---|
| R0 | Frozen RC1 task-level predictor | Immutable behavioral control |
| R1 | Structured-only task-level prompt | Isolate task/table reasoning from retrieval |
| R2 | Structured table plus current evidence cards | Measure evidence-induced behavior and cost |
| R3 | R2 plus compiled target semantics, units, label assertions, and explicit prediction/label consistency constraints | Test target interpretation without training |
| R4 | R3 plus an explicit full-roster compare-then-predict stage and common task-level numeric/ranking scale | Test comparative reasoning and batch stability |

Every run records request count, fallback count, point diversity, label diversity, ranking-score
diversity, parse failures, selected evidence count, prompt size, latency, schema, cutoff, and
citation validity. Add prompt/output hashes so two runs can be compared without storing secrets.
For ranking, add roster-permutation equivariance and split-batch scale checks. For classification,
record label/point/interval consistency. For regression, record target-unit checks and distance
from legitimate task-provided anchors where such anchors exist.

Without legally available outcomes, the ablation verdict is exactly:

**NO PREDICTIVE QUALITY CLAIM.** A variant may advance only as a safer or more behaviorally coherent
research candidate, not as a more accurate model.

# Top predictive bottlenecks

1. **Target semantics are passed through but not compiled.** The model must infer units,
   thresholds, label meanings, forecast horizon, and point/label consistency from raw prose.
2. **Fallbacks are dimensionally unsafe and class-collapsed.** A transient model failure can turn
   every classification into `labels[0]` or mix unrelated numeric fields into a regression target.
3. **Cross-sectional access is not cross-sectional reasoning.** No feature deltas, robust anchors,
   comparative ranks, or common scale are computed outside the model.
4. **Evidence retrieval optimizes lexical relevance, not predictive utility.** Top chunks may name
   the entity and target yet provide no forward-looking signal; silent first-card citation hides
   this distinction.
5. **Intervals have no scale or calibration model.** Generic symmetric fallback widths were built
   for schema survival and are not optimized against scorer 5.2.1's capped interval-score ratio;
   interval work cannot compensate for a predictive leg at or below naive parity.

# First recommended algorithm improvement

Implement a deterministic **target-semantics compiler and comparative reasoning block** before
changing retrieval or adding learned artifacts. It should convert trusted target metadata,
`label_assertions`, task wording, entity units, and the complete table into a compact reasoning
contract: what quantity is predicted, its units and horizon, legal decision thresholds, which
features are dimensionally compatible anchors, and which cross-entity comparisons must be made.
The House model should first state structured per-entity drivers on this shared scale and then emit
the final predictions in the same response; local checks should reject label/point/unit
inconsistency rather than silently accepting it.

This is the best first move because it directly addresses all three target types, consumes no
external data, adds no model artifact, preserves the one-call path, and is testable with synthetic
and public outcome-free cases. Validate it by R0–R4 behavioral ablation, schema/cutoff/citation
checks, unit and label consistency tests, roster-permutation tests, feature-perturbation tests,
ranking scale tests, and fallback injection. Only a later vintage-safe labelled backtest may support
an accuracy, MAE, Spearman, or interval-score claim.

Training-policy risk is **none for the proposed first implementation** as long as it uses only the
trusted task, supplied structured fields, and frozen corpus at inference. Risk becomes material
if any historical labels, fitted thresholds, residual widths, or external lookup tables are added;
those require the provenance and cutoff audit above before use.
