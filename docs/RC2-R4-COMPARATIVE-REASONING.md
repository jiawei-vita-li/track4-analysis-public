## Executive summary (read this first)

R4 adds a deterministic cross-entity comparison layer derived only from the trusted structured entity table. It compares finite values only within the same named feature, refuses comparison when trusted unit metadata conflicts, and never assigns predictive direction to a relative position. A controlled mock ablation across all 11 current public units preserved byte-identical answers, one normal House request per unit, and the frozen R3 reliability envelope. Actual user-prompt characters increased by 7.885%, while the largest prompt remained below the configured planning threshold but close enough to require monitoring on hidden tasks. Public outcomes are unavailable, so this is a mechanism and reliability result, not a predictive-quality claim.

## 1. Research question

Can explicit, deterministic cross-entity comparative context improve task-level prediction reasoning while preserving the R3/R2.6 reliability envelope? R4 isolates that question by changing only the comparative representation and prediction-stage prompt. It does not add another House call or alter retrieval, evidence, claims, fallbacks, intervals, model parameters, request budgets, schema, Docker, or packaging.

## 2. Frozen R3 base

R4 starts from commit `3f762ed1a53252417a2d53de11cf07cc5b003df4` on `research/predictive-v2`. The `agenthon-t4-rc1` tag remains untouched at `0c288e4b775c84ac354c3765cb00974314efc48e`.

## 3. Scorer snapshot

The pre-coding rule-drift gate matched the required source of truth:

| Artifact | Exact value |
| --- | --- |
| Official upstream commit | `ede7381d8c1ba9d8c84068f9d142f5e093a33892` |
| `SCORER_VERSION` | `5.2.2` |
| `qfbench2_track_analysis/scoring.py` blob | `a35c7747f5afe50c4105ec7718b6cd7c78e7c985` |
| Toolkit used locally | `qfbench2-common 2.5.1` |

No rule drift was detected.

## 4. Exact method

For every structured entity field, the compiler first determines whether the field is a numeric candidate. Boolean values are excluded. `NaN`, positive or negative infinity, non-numeric values, explicit nulls, and absent values never receive ranks. A field is compared only when it has at least two finite observations and no explicit unit conflict.

For every admitted feature, R4 records the finite count, missing count, median, minimum, and maximum. Each finite entity value receives an ascending average rank, a normalized rank `(rank - 1) / (n - 1)`, and an exact relation to the median: `below`, `near` when equal, or `above`. Ties receive the same average rank. These values describe position only: the compiler never interprets higher as better, more likely, causal, or directionally related to the target.

No categorical frequencies are included in R4. This is deliberate: they are not required to test the numeric comparative mechanism and would add high-cardinality prompt cost and a second research variable.

## 5. `ComparativeContext` schema

The typed structure contains:

- a version string;
- the canonical list of numeric features considered;
- per-feature `NumericFeatureSummary` records with provenance and roster statistics;
- `SkippedNumericFeature` records with deterministic reason and provenance;
- canonical per-entity `RelativeNumericFeature` records;
- a deterministic total comparison count.

The prompt form stores feature provenance once in the feature summary and uses a compact feature-keyed map for entity-relative values. The trace form is intentionally more verbose: it retains the source path on every relative feature plus the summary statistics, skipped-feature details, and skip reasons needed to reconstruct why an entity received a comparison.

## 6. Comparability rules

A feature is comparable only when all of the following hold:

1. It is the same structured field name across entities; different feature names are never placed on one scale.
2. At least two roster entities have finite numeric values.
3. Trusted unit metadata contains no explicit conflict.
4. R3 `TargetSemantics.explicit_unit` is not conflicting.

Missing values are allowed, but missing entities receive no relative record. An all-missing field is recorded as `no_finite_values`; a one-value field is `insufficient_finite_values`. The compiler uses no task ID, outcomes, naive answers, scorer references, Development score, evidence, or model output.

## 7. Unit-conflict handling

Unit-like metadata is recognized only from structured field names ending in `unit`, `units`, `currency`, or `scale`. Multiple distinct non-empty values for any such field create an explicit conflict. If R3 already reports an explicit-unit conflict, that conflict is also honored. Under either condition, numeric comparisons are skipped with the exact conflicting source paths in the trace.

This conservative rule correctly skips `latest_precutoff_estimate` in `t4-macrorev-20240930-us6`, whose roster mixes index levels, thousands, annualized units, and currency scales. R4 does not attempt conversion. The invariant is **NO COMPARISON > UNSAFE COMPARISON**.

## 8. Prompt integration

R4 keeps the complete R3 payload and inserts `comparative_context` after the complete entity table conceptually. The raw target and compiled target semantics remain present and authoritative. The added instruction tells House to compare before predicting, treat relative position as comparison evidence rather than a forecast, avoid inferring target direction from feature direction, and keep ranking scores on one common target scale. It does not request chain-of-thought or emitted reasoning.

The primary design still makes one normal task-level House request when no repair is needed. A planning-call-then-prediction-call design is explicitly deferred to a possible R5 experiment.

## 9. Mechanism switch

The CLI now accepts `--comparative-context on|off`, defaulting to `on` for R4. `off` omits the comparative payload, restores the exact R3 system prompt, and removes comparative characters from batch planning. No retrieval, model-call, parse, formatting, or fallback path is forked.

## 10. Files changed

| File | Purpose |
| --- | --- |
| `baselines/strong_rag_baseline/comparative_context.py` | Typed compiler, unit-safety rules, ranks, summaries, provenance, and trace representation. |
| `baselines/strong_rag_baseline/task_context.py` | Compile optional comparative context and account for it in batch planning. |
| `baselines/strong_rag_baseline/task_predictor.py` | Add the optional prompt section, compare-then-predict instruction, prompt-size measurement, and trace fields. |
| `baselines/strong_rag_baseline/cli.py` | Add the isolated `on/off` mechanism switch. |
| `baselines/strong_rag_baseline/tests/test_comparative_context.py` | Construction, safety, switch, trace, and metamorphic tests. |
| `docs/RC2-R4-COMPARATIVE-REASONING.md` | This experiment record. |

No frozen R3 subsystem was modified.

## 11. Metamorphic and construction tests

Fourteen focused R4 tests cover construction, provenance, deterministic ordering, ascending rank and percentile, ties, missing values, non-finite values, explicit unit conflict, one-entity tasks, all-missing fields, prompt integration, trace observability, and the mechanism switch.

The required metamorphic controls pass:

1. Roster permutation produces the same canonical representation.
2. Adding an irrelevant numeric feature leaves every existing comparison unchanged.
3. Renaming an irrelevant categorical feature leaves target semantics and comparisons unchanged.
4. A positive affine transform preserves ranks, percentiles, and median relations.
5. Equal values receive deterministic average ranks.
6. Missing values receive no fake rank.
7. Heterogeneous units skip comparison.
8. A one-entity task produces a graceful minimal context.
9. An all-missing feature is skipped.
10. Non-finite values are excluded deterministically.
11. Label-order permutation does not alter comparative context.
12. Evidence perturbation does not alter comparative context.

## 12. R3 versus R4 controlled mock ablation

This is a **MOCK / BEHAVIORAL EVALUATION** over all 11 current public units. Both arms use the same R4 code and official task/corpus snapshot; only the mechanism switch changes. Diversity is the sum of within-unit distinct values, matching the R3 reporting convention.

| Metric | R3: OFF | R4: ON | Change |
| --- | ---: | ---: | ---: |
| Units | 11 | 11 | 0 |
| House requests | 11 | 11 | 0 |
| Parse failures | 0 | 0 | 0 |
| Repairs | 0 | 0 | 0 |
| Fallback entities | 1 | 1 | 0 |
| Label diversity | 5 | 5 | 0 |
| Point diversity | 20 | 20 | 0 |
| Ranking-score diversity | 10 | 10 | 0 |
| Semantic consistency violations | 0 | 0 | 0 |
| Claims | 78 | 78 | 0 |
| Numeric features considered | 0 | 18 | +18 |
| Numeric features compared | 0 | 14 | +14 |
| Numeric features skipped | 0 | 4 | +4 |
| Entity-feature comparisons | 0 | 98 | +98 |

All 11 R4 answers are byte-identical to both the switch-OFF answers and the frozen R3 mock answers previously admitted by official scorer 5.2.2 smoke. Therefore schema, roster, cutoff, offsets, claim counts, false-claim counts, and every deterministic scorer penalty are unchanged in this control. The current host's WSL service later failed before a redundant rerun could enter the smoke verifier; byte identity is used as the exact artifact-level control rather than describing that host failure as a fresh pass.

## 13. Prompt-size and request-count cost

`prompt_chars` is the exact Python character count of each primary user prompt. `estimated_input_chars` is the pre-existing batch-planner estimate, which omits some fixed output-contract prose; both are reported to avoid comparing different measurements.

| Measure | R3: OFF | R4: ON | Delta |
| --- | ---: | ---: | ---: |
| Actual primary user-prompt chars | 260,682 | 281,236 | +20,554 (+7.885%) |
| Batch-planner estimated chars | 247,232 | 266,422 | +19,190 (+7.762%) |
| Requests | 11 | 11 | 0 |

The largest R4 prompt is `t4-macrorev-20240930-us6` at 44,635 characters, 92.990% of the configured 48,000-character planning threshold. Its R3 prompt was already 44,158 characters, so R4 adds only 477 there because the unsafe comparison is skipped and empty per-entity prompt records are omitted. Nevertheless, hidden tasks with larger rosters or more numeric fields may force extra batches; this is the principal operational risk.

## 14. Scorer penalties and reliability

The switch comparison produced byte-identical `answer.json` artifacts for every unit. The frozen R3 versions of those exact bytes passed current official scorer 5.2.2 smoke on Linux with `admissible=True` for all 11 units and zero known deterministic claim penalties. R4 therefore introduced no content-free, wrong-entity, unanchored, contradicted, over-cap, malformed, schema, roster, cutoff, or offset regression in the mock control.

The full strong-baseline suite passes 99/99 under Python 3.13 with toolkit 2.5.1. The documentation/firewall selection passes 15/15, focused R4 tests pass 14/14, and Ruff lint plus changed-file formatting checks pass. Native Windows cannot execute the official secure no-follow corpus walk and is not counted as a Linux smoke pass.

## 15. Known limitations

- Same-name comparison is structural, not semantic; absent explicit conflict, malformed organizer metadata could still make a field unsafe.
- A global conflict in explicit unit metadata conservatively suppresses every numeric comparison, even when an individual predictor might have been comparable.
- Exact equality defines `near`; R4 does not invent a scale-dependent tolerance.
- Rank and percentile discard distance information except for the separately supplied raw value and summary statistics.
- No evidence here shows House actually uses the context beneficially.
- Prompt cost grows with comparable feature count times roster size and may change batching on larger hidden tasks.
- No categorical comparative context, feature selection model, causal interpretation, or target-direction mapping is attempted.

## 16. Development evaluation protocol

The R4 code must be frozen and its algorithm commit recorded before any new organizer Development result is viewed. A future authorized evaluation should use the immutable R4 commit and compare it with the frozen R3 candidate without prompt edits, task-specific patches, outcome inspection, or repeated tuning against leaderboard scores. One Development result may evaluate the frozen hypothesis; it must not become training data or an iterative optimization target. No CodaBench upload or Development attempt is performed in this phase.

## 17. Freeze record

R4 algorithm commit: `15a09731c607d10c42202aae3e0b28f72de9e2a6`.

The exact commit will replace this marker in a documentation-only freeze-record commit after all gates pass. No runtime code may change between the algorithm commit and that record.

**NO PREDICTIVE QUALITY CLAIM**
