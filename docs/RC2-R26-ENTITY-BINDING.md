## Executive summary (read this first)

R2.6 removes four deterministic `wrong_entity` claim failures without changing any prediction,
interval, query, model setting, batching rule, or House-request budget. The defect was between
retrieval and evidence-card creation: R2.5 retained cutoff-safe BM25/RRF hits without checking the
current manifest's `entity_ids` or `shared` label. R2.6 applies the scorer 5.2.2 admission relation
before evidence enters a card and repeats it during final preflight. On all 11 current public units,
the controlled mock run keeps 78 claims and 11 requests while reducing false claims from four to
zero. This is a reliability result only: **NO PREDICTIVE QUALITY CLAIM**.

# Frozen rule input

The edit gate used official upstream commit
`ede7381d8c1ba9d8c84068f9d142f5e093a33892`. Its
`qfbench2_track_analysis/scoring.py` blob is
`a35c7747f5afe50c4105ec7718b6cd7c78e7c985`, and `SCORER_VERSION` is `5.2.2`.
The executable admission source is `qfbench2_track_analysis/corpus.py` at that commit:
an ordinary document admits an entity only when it is explicitly listed in `entity_ids` or the
document has `shared: true`; `entity_ids: []` admits nobody. The synthetic `doc_id: "task"`
admits only the cited entity's own serialized task-table row.

# Root cause of the four R2.5 failures

`Q1` through `Q5` below are the unchanged queries emitted by `queries.build_queries`, in order.
Only ranks within the R2.5 per-query depth of ten contributed to RRF. Each bad passage became
evidence-card position 1 because no entity-admission check existed after fusion.

| Unit / predicted entity | R2.5 evidence and manifest label | Retrieval query(s), BM25 rank and score | RRF | Why it entered the card |
|---|---|---|---|---|
| `t4-cotpos-202411-us10` / `UST_10Y` | `E8_1`; `COT_UST_2Y_20241025`; `entity_ids=["UST_2Y"]`; not shared | Q1 `u.s. treasury 10-year note futures ust_10y net_positioning_change_pct_oi_rank ranking` #1 / 12.3433; Q2 task-prompt query #1 / 29.1609; Q3 feature-name query #1 / 13.2440; Q4 `... chicago board trade rates pct_of_open_interest` #1 / 21.7090; Q5 numeric-feature query #1 / 13.2440 | card #1; 0.0819672 | The 2-year and 10-year COT documents share almost all Treasury/CFTC terms. The lexical ranker preferred the 2-year chunk on every query, and R2.5 never read the manifest label. |
| `t4-credit-event-2023` / `WE` | `E7_1`; `EDGAR_0000886158_10Q_20230126`; `entity_ids=["BBBY"]`; not shared | Q1 `wework inc. we credit_event_12m classification` #1 / 14.1068; Q3 `wework inc. we credit_event_12m classification industry cik` #1 / 14.1068. Q2 and Q4 were outside the top-ten fusion depth. | card #1; 0.0327869 | The ticker `WE` is also a common word. Generic credit-event and filing language matched BBBY while the correct CIK-specific query did not place this chunk in the fusion depth. |
| `t4-eps-growth-2024Q3-banks` / `C` | `E2_1`; `EDGAR_0000019617_10Q_20240802`; `entity_ids=["JPM"]`; not shared | Q1 `citigroup inc. financials eps_yoy_growth_pct regression` #3 / 12.4769; Q2 task-prompt query #3 / 30.3919; Q3 feature-name query #6 / 19.9859; Q5 `... prior year eps 1.63` #1 / 19.9859. CIK Q4 was outside depth. | card #1; 0.0632910 | Common bank/EPS language plus the prior-year value accumulated across four query lists; repeated RRF contributions outweighed entity identity. |
| `t4-eps-growth-2024Q3-banks` / `USB` | `E7_1`; `EDGAR_0000019617_10Q_20240802`; `entity_ids=["JPM"]`; not shared | Q1 `u.s. bancorp usb financials eps_yoy_growth_pct regression` #3 / 12.4769; Q3 feature-name query #3 / 19.9859; Q5 `... prior year eps 0.91` #1 / 19.9859. Q2 was #22 and CIK Q4 outside depth. | card #1; 0.0481395 | Generic bank/EPS terms and the numeric feature matched a JPM passage on three contributing query lists. No post-retrieval binding check rejected it. |

The path was therefore deterministic:

```text
cutoff-safe chunks -> unchanged BM25 queries -> unchanged RRF -> top-k evidence card
                                                        ^ no entity admission in R2.5
```

# R2.6 implementation

`indexer.py` now retains validated `entity_ids` and `shared` metadata from the same trusted
manifest entries whose digests it already verifies. `evidence_binding.py` filters the existing
RRF candidate order before card construction. It first inspects the unchanged top-ten fusion
pool; if rejected documents create vacancies, it appends deeper admissible hits without
renumbering or rescoring already-admitted candidates. BM25 scoring, query generation, and RRF's
formula are unchanged.

If no corpus hit admits the entity, the only fallback is the scorer-defined synthetic task-table
document, restricted to that entity's own row. It never uses another entity's document, an empty
`entity_ids` document, or an inferred “shared-looking” document. The final sanitizer and preflight
both call the same admission relation. A rejected model-produced claim is replaced by an
entity-admissible exact extract and the event is written to the optional trace as
`entity_binding_violations`; a claim that still violates the invariant makes preflight fail.

The four corrected first documents are respectively
`COT_UST_10Y_20241025`, `EDGAR_0001813756_10K_20230329`,
`EDGAR_0000831001_10Q_20240802`, and `EDGAR_0000036104_8K_20240912`.

# Controlled public-unit comparison

Both sides used commit `16b9637` versus the R2.6 working tree, the same current official units,
the same deterministic mock, and qfbench2-common 2.5.1 with the official scorer 5.2.2 claim
evaluator. Corpus bytes were checked against manifest SHA-256 values before evaluation.

| Measure, all 11 public units | R2.5 | R2.6 |
|---|---:|---:|
| Claims | 78 | 78 |
| False claims | 4 | 0 |
| `wrong_entity` | 4 | 0 |
| `content_free` | 0 | 0 |
| `unanchored` | 0 | 0 |
| `contradicted` | 0 | 0 |
| `over_cap` | 0 | 0 |
| `malformed` | 0 | 0 |
| `out_of_range` | 0 | 0 |
| Schema / roster / cutoff / citation-offset unit passes | 11 / 11 / 11 / 11 | 11 / 11 / 11 / 11 |
| House requests | 11 | 11 |

After removing only each row's `claims` field, all prediction rows compare equal as parsed JSON:
labels, point forecasts, intervals, entity order, and optional ranks are unchanged. The task
prompt implementation, target reasoning, batching, query builder, seed/temperature behavior, and
Docker/submission files have no diff. Evidence payloads change only where current manifest
admission requires it.

# Tests and limits

- `python -m pytest baselines/strong_rag_baseline/tests -q` under Python 3.13 and UTF-8 mode:
  66 passed.
- Focused R2.6 controls: 11 passed, covering entity-specific, wrong-entity, shared, empty-label,
  multi-entity, no-corpus-evidence, classification, regression, ranking, exact-quote, combined
  cutoff/entity filtering, and final-preflight behavior.
- Current official claim-test subset on Windows: 132 passed; 43 integration cases stopped only at
  the official Linux-only `os.O_DIRECTORY` secure-open boundary. No scorer code was changed or
  bypassed. The public-unit comparison instead instantiated the unmodified official trusted-doc
  and claim-evaluation types after verifying every manifest digest; Linux CI supplies the final
  platform check.

No hidden outcome, practice outcome, external label, or task-specific answer was used. Therefore
this comparison supports only removal of known deterministic submission penalties:
**NO PREDICTIVE QUALITY CLAIM**.
