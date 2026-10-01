## Executive summary (read this first)

R3 adds a deterministic `TargetSemantics` compiler that exposes what the trusted task says about the target and marks everything else unknown or conflicting. It keeps the raw target beside the compiled interpretation and adds only non-fatal consistency diagnostics; retrieval, evidence binding, claims, fallbacks, intervals, batching, request limits, and submission code are unchanged. In a mock behavioral comparison across all 11 current public units, R2.6 and R3 produced byte-identical answers and retained zero known deterministic scorer penalties. R3 increased estimated prompt characters by 6.745% while request, parse, repair, and fallback counts were unchanged. Public outcomes are unavailable, so this experiment supports retaining the safer interpretation layer but makes **NO PREDICTIVE QUALITY CLAIM**.

## 1. Scorer snapshot

The pre-coding and pre-commit rule-drift gates both matched the required snapshot:

| Artifact | Exact value |
| --- | --- |
| Official upstream commit | `ede7381d8c1ba9d8c84068f9d142f5e093a33892` |
| `SCORER_VERSION` | `5.2.2` |
| `qfbench2_track_analysis/scoring.py` blob | `a35c7747f5afe50c4105ec7718b6cd7c78e7c985` |
| R3 base commit | `1964b484abd8de91ef6fad0e7fbe767f92ae32cf` |
| Branch | `research/predictive-v2` |

No rule drift was detected. The official scorer and unit tree were read from a detached checkout at the exact upstream commit; R3 did not alter them.

## 2. Exact files changed

| File | Reason |
| --- | --- |
| `baselines/strong_rag_baseline/target_semantics.py` | New typed deterministic compiler and non-fatal diagnostics. |
| `baselines/strong_rag_baseline/task_context.py` | Compile semantics once per task and include their size in the existing batch planner. |
| `baselines/strong_rag_baseline/task_predictor.py` | Keep `raw_target`, add compiled semantics to the prompt, and emit diagnostics in the trace. |
| `baselines/strong_rag_baseline/cli.py` | Keep the deterministic mock compatible with the renamed `raw_target` prompt key. |
| `baselines/strong_rag_baseline/tests/test_target_semantics.py` | Compiler, provenance, diagnostic, prompt-integration, and metamorphic controls. |
| `docs/RC2-R3-TARGET-SEMANTICS.md` | This experiment record. |

The diff contains no changes to retrieval, query construction, evidence selection or filtering, claim construction, preflight, fallback, batching rules, request budget, model parameters, interval construction, Docker, or packaging.

## 3. `TargetSemantics` schema

`TargetSemantics` contains `SemanticField` values for `target_type`, `target_name`, `target_description`, `explicit_unit`, `forecast_horizon`, `legal_labels`, `numeric_thresholds`, `ranking_direction`, `point_meaning`, `point_range`, and `interval_level`. It also contains typed `LabelAssertion` records and a list of conflicting field names.

Each `SemanticField` has:

```json
{
  "value": null,
  "source": null,
  "status": "unknown",
  "candidates": []
}
```

`status` is exactly `resolved`, `unknown`, or `conflict`. `candidates` is emitted only for conflicts. Each label assertion records its label, exact trusted text, source path, whether it is safely executable, and—only when executable—the parsed operator and threshold.

## 4. Provenance design

The compiler reads only the supplied task mapping: the target object, task prompt, target type, interval level, cutoff date, entities, and trusted structured field names and values. Structured target fields take priority, followed by exact target assertions, then narrowly recognized task-prompt forms. Resolved fields carry their source path or the exact matched prompt fragment. Conflict candidates retain their individual values and sources; label assertions retain their exact `target.label_assertions.<label>` source.

The compiler has no corpus or retriever parameter and does not receive model output. It contains no task-ID branch or public-unit identifier. A provenance invariant test checks that every resolved value and every conflict candidate has a source and that unknown fields have neither a value nor source.

## 5. Unknown and conflict handling

The invariant is `UNKNOWN > GUESS`. Missing or ambiguous metadata remains `{value: null, source: null, status: "unknown"}`. Distinct trusted candidates produce `status: "conflict"`; the compiler does not select one. Candidate ordering is normalized so roster permutation cannot change even a heterogeneous-unit conflict representation.

Parsing is intentionally narrow. It recognizes only explicit unit phrases, explicit date or quarter horizons, explicit point-forecast definitions, an explicit `rank 1 = largest/highest/smallest/lowest` rule, and a stated probability range. Arbitrary numbers in prose are not thresholds: threshold extraction is limited to named structured threshold fields, percent values in trusted label assertions, or an exact safe expression of the form `point_forecast <operator> number`.

## 6. Classification behavior

Legal labels come only from `target.labels` and are sorted to remove list-order semantics. Assertion text is preserved verbatim. An assertion becomes executable only when its expression exactly matches the safe point-forecast comparison grammar; ordinary natural-language label definitions remain non-executable. Diagnostics check legal labels and point/label consistency only when the trusted mapping is executable and identifies one matching label. No label is treated as a default, negative class, or semantic opposite based on spelling or position.

## 7. Regression behavior

The compiled quantity comes from the trusted target name and, when explicitly available, point meaning, unit, horizon, and range. The prompt now explicitly separates target semantics from predictor features and says that a numeric feature is not automatically a candidate output. R3 adds no learned regression rule, normalization, winsorization, target conversion, or fallback change. Diagnostics check finite points and an explicit trusted range only.

## 8. Ranking behavior

Ranking direction is resolved only from an explicit structured direction or the narrow trusted `rank 1 = ...` prompt form. The prompt tells House that every score must represent the same compiled target quantity on one shared scale. The output remains a continuous `point_forecast`; R3 does not generate optional rank fields. Diagnostics report non-finite scores and ties without creating a new fatal gate.

## 9. Public-unit compiled semantics

This table was generated from R3 traces for all 11 current public units. `R/U/C` counts the 11 semantic fields as resolved/unknown/conflicting; assertions are listed separately and are not included in that count.

| Unit | Type and target | Unit | Horizon | Labels / direction | Assertions | R/U/C |
| --- | --- | --- | --- | --- | ---: | ---: |
| `t4-auction-btc-202411-us7` | regression; `bid_to_cover_ratio` | `bid_to_cover_ratio` | unknown | — | 0 | 5/6/0 |
| `t4-cotpos-202411-us10` | ranking; `net_positioning_change_pct_oi_rank` | `pct_of_open_interest` | 2024-10-22 to 2024-11-26 | higher score ranks first | 0 | 7/4/0 |
| `t4-cpicomp-202410-us11` | regression; `cpi_component_mom_first_print` | `mom_pct_change_sa` | October 2024 | — | 0 | 5/6/0 |
| `t4-credit-event-2023` | classification; `credit_event_12m` | probability `[0,1]` | 12 months, 2023-03-31 to 2024-03-31 | `credit_event`, `no_event` | 2 | 8/3/0 |
| `t4-eps-growth-2024Q3-banks` | regression; `eps_yoy_growth_pct` | percent | quarter ended 2024-09-30 | — | 0 | 5/6/0 |
| `t4-eps-yoy-2023Q2-mixed` | classification; `eps_yoy_direction` | unknown | June 2023 quarter | `down`, `up` | 2 | 6/5/0 |
| `t4-EXAMPLE-eps-beat` | classification; `eps_outcome` | unknown | Q2 FY2024 | `beat`, `inline`, `miss` | 3 | 6/5/0 |
| `t4-fomc-curve-20220728` | regression; `yield_change_bps_intermeeting` | `bps_change` | 2022-07-28 to 2022-09-20 | — | 0 | 6/5/0 |
| `t4-fomc-curve-20240918` | regression; `yield_change_bps_intermeeting` | `bps_change` | 2024-09-19 to 2024-11-06 | — | 0 | 6/5/0 |
| `t4-macrorev-20240930-us6` | classification; `next_estimate_revision_direction` | conflict across entity units | unknown | `down`, `up` | 2 | 5/5/1 |
| `t4-postearn-20240201-megacap` | classification; `earnings_reaction` | percent | 2024-02-01 to 2024-02-02 | `flat`, `negative_reaction`, `positive_reaction` | 3 | 7/4/0 |

The single conflict is intentional: the macro-revision roster supplies heterogeneous entity units, so R3 refuses to invent a common target unit. Public natural-language label assertions are preserved but not promoted to executable expressions. The EPS and post-earnings units expose trusted structured or percentage thresholds; dates are not misclassified as thresholds.

## 10. Compiler and metamorphic tests

The focused suite has 19 passing tests. It covers explicit and missing units and horizons, classification labels and assertions, safe executable and non-executable assertions, regression quantity, ranking direction, unrelated numeric features, unknown metadata, ambiguous wording, conflicting semantics, purity, provenance, prompt integration, and non-fatal diagnostics.

All eight requested metamorphic properties are exercised:

1. Entity roster permutation leaves semantics unchanged, including heterogeneous conflicts.
2. Irrelevant feature-value perturbation leaves semantics unchanged.
3. Evidence-text perturbation leaves semantics unchanged.
4. Explicit unit replacement follows the new trusted value.
5. Explicit unit deletion makes the unit unknown.
6. Label-order permutation leaves semantics unchanged.
7. Adding an unrelated numeric column leaves semantics unchanged.
8. Renaming an irrelevant feature leaves semantics unchanged.

Linux verification used Python 3.13.15 and official `qfbench2-common` 2.5.1. The R3 baseline plus documentation/firewall selection passed 100/100 tests. The exact official upstream suite passed 1,138 tests before its three cross-repository document checks reported the deliberately absent hub checkout; after a sparse official hub checkout was supplied through the documented environment variable, that entire test file passed 10/10. The current official `qfbench2-smoke --profile smoke` then admitted all 11 R3 public-unit outputs (`admissible=True`, no labels) under real POSIX path semantics.

Running the secure corpus suite natively on Windows is not a valid substitute: it fails closed because `O_NOFOLLOW` and `O_DIRECTORY` are unavailable. A combined suite against the research branch's frozen, older scorer copy also retains one pre-existing synthetic regression fixture that omits the naive baseline now required by toolkit 2.5.1; the exact upstream version supplies that fixture and passes. Neither platform behavior nor the frozen scorer/tests were changed for R3.

## 11. R2.6 versus R3 ablation

This is a **MOCK / BEHAVIORAL EVALUATION**. R2.6 ran from a detached worktree at the base commit, and R3 ran from the working tree. Both consumed the same 11 task and corpus directories from the exact official upstream snapshot. Manifest document hashes were verified before constructing official trusted-corpus objects. Current official schema, roster alignment, embargo reporting, citation admission, and numeric-claim evaluation were applied with scorer 5.2.2 and `qfbench2-common` 2.5.1 under Python 3.13.3.

The shared `qfbench2-smoke` manifest wrapper was also attempted directly on Windows, where it correctly fails closed because that platform lacks the `O_NOFOLLOW`/`O_DIRECTORY` guarantees required for its secure directory walk. This was treated as a host-platform limitation, not as a pass; the wrapper subsequently passed all 11 units under WSL/Linux. The component-level comparison did not bypass integrity: it first recomputed and matched every corpus document hash from each official manifest, then built the official trusted document/index objects and ran the current schema and scorer checks.

| Metric | R2.6 | R3 | Change |
| --- | ---: | ---: | ---: |
| Units | 11 | 11 | 0 |
| Model requests | 11 | 11 | 0 |
| Estimated prompt characters | 231,609 | 247,232 | +15,623 (+6.745%) |
| Parse failures | 0 | 0 | 0 |
| Repairs | 0 | 0 | 0 |
| Fallback entities | 1 | 1 | 0 |
| Label diversity | 5 | 5 | 0 |
| Point diversity | 20 | 20 | 0 |
| Ranking score diversity | 10 | 10 | 0 |
| Output consistency violations | 0 | 0 | 0 |
| Claims | 78 | 78 | 0 |
| False claims | 0 | 0 | 0 |
| Content-free claims | 0 | 0 | 0 |
| Wrong-entity claims | 0 | 0 | 0 |
| Unanchored claims | 0 | 0 | 0 |
| Contradicted claims | 0 | 0 | 0 |
| Over-cap claims | 0 | 0 | 0 |
| Malformed claims | 0 | 0 | 0 |
| Out-of-range citations | 0 | 0 | 0 |
| Schema / roster / cutoff / offset passes | 11/11 each | 11/11 each | 0 |
| Mock total task-call latency | 4.336 ms | 5.585 ms | +1.249 ms |
| Mock median task-call latency | 0.352 ms | 0.440 ms | +0.088 ms |

The mock latency is dominated by local process noise and is descriptive only. The one fallback is the same `USB` entity in `t4-eps-growth-2024Q3-banks` in both arms. All 11 `answer.json` files are byte-equivalent between R2.6 and R3.

## 12. Request-count and prompt-size result

Request count stayed at one task-level request per public unit: 11 total in each arm. No unit changed batch count. Prompt size increased on every unit because `raw_target` is retained while the provenance-bearing compiled representation is added; the aggregate increase was 15,623 characters, or 6.745%. This is the principal measured cost of R3.

## 13. Parse, repair, and fallback result

Both arms had zero parse failures and zero repairs. Both had one fallback entity, with the same identity. The deterministic mock outputs were byte-identical, so R3 neither masked nor created an output-path difference in this control.

## 14. Consistency, penalties, and compiler hallucinations

R3 resolved 66 semantic fields, left 54 explicitly unknown, and surfaced one conflict across the public set. Its diagnostics reported zero output consistency violations. This does not prove predictions are correct; it says only that no safely executable trusted constraint was violated by the mock output.

Known deterministic scorer penalties remained zero: no content-free, wrong-entity, unanchored, contradicted, over-cap, malformed, schema, roster, cutoff, or offset failures were observed. Production NLI faithfulness and outcome-dependent predictive and interval scores were not evaluated.

Compiler hallucination count was **0 detected** under the defined structural audit: every resolved field had task-side provenance, every conflict candidate had provenance, unknowns had no value or source, evidence perturbation had no effect, and there were no task-ID branches. This is not a claim that every conservative parser rule will be semantically complete on hidden tasks.

## 15. Regressions and remaining risks

The only measured regression is prompt size (+6.745%); mock timing also increased by 1.249 ms in total, too little and noisy to interpret. No reliability regression was detected. The compiler is intentionally incomplete: unfamiliar wording remains unknown, heterogeneous entity metadata can prevent a task-level unit from resolving, natural-language assertions remain non-executable, and prompt-fragment parsing may miss valid variants. A larger compiled object may matter near hidden-task context limits even though the existing planner accounts for it. Current tests establish deterministic behavior and provenance, not House-model comprehension or outcome accuracy.

## 16. Retention decision and next experiment

R3 should be retained: it makes uncertainty and provenance explicit, preserves the R2.6 reliability baseline, leaves answers unchanged under the deterministic control, and has a bounded prompt-size cost. There is no evidence here that it improves accuracy, MAE, Spearman correlation, interval score, or leaderboard score.

R4 is justified only as a separately approved research question about comparative task-level reasoning, because the remaining bottleneck is prediction quality rather than submission reliability. R3 does not itself supply evidence that any particular R4 method will improve predictions, and no R4 work was started.

**NO PREDICTIVE QUALITY CLAIM**
