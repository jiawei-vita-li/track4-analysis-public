## Executive summary (read this first)

This snapshot pins the current Track 4 source of truth to official commit `ede7381d` and scorer
5.2.2. The release makes content-free claims and overlong citation spans deterministically false,
removes the old claim-level `citations` list, excludes URL numbers from numeric consistency, and
changes the production judge's window selection for long passages. Frozen RC1's generic claim is
therefore false on every current public row and would multiply every public unit's composite by
zero. R2.5 fixes only claim construction by submitting exact corpus extracts; it does not change
predictions, retrieval, intervals, batching, or request counts. No outcome was read and this
snapshot makes **NO PREDICTIVE QUALITY CLAIM**.

# Frozen source identities

Executable scorer and toolkit contracts outrank official tests, which outrank current track docs,
README/CONCEPTS, and historical notes. The historical 5.2.1 snapshot remains unchanged.

| Item | Current official value |
|---|---|
| Track upstream | `Agenthon-2026/track4-analysis-public` |
| Track commit | `ede7381d8c1ba9d8c84068f9d142f5e093a33892` |
| `SCORER_VERSION` | `5.2.2` |
| `qfbench2_track_analysis/scoring.py` blob / SHA-256 | `a35c7747f5afe50c4105ec7718b6cd7c78e7c985` / `2fb01cceb9dfb4f77d0dc8e59fb4fc81157cb1d751fa67860b37e515cc799f47` |
| `qfbench2_track_analysis/numeric.py` blob / SHA-256 | `0088c4e096ca13c32a0d32573a7b2639e8970686` / `5ae5a2c942bd3917ca9e1c17097353b1b32420da51338388d21609673ba2caef` |
| Toolkit | `qfbench2-common` 2.5.1, official participant pin `v2.5.1` |
| Current Hub commit | `8c0b3f7bf031b595c2e45c2e488cdd33fbf0c7fd` |
| Answer schema | `common/qfbench2_common/schemas/analysis.schema.json`, blob `ce1b927b7ed596d7191a5de7f74baed048560733`, SHA-256 `c19283fcc72d4031f23575705673a3f396cd92fc047cf6b9542220ea899cdacd` |
| Submission schema | blob `9c71b5252d930d314c9898629ca9f5153f39b948`; interface `2.0` |
| Development fixture | C5 `schema_version = 1.0.0`, interface `2.0`, blob `56724ffb7b6dc91e5b266baba8c6445399091a3f` |

The toolkit package and the answer/submission schemas did not change from the preceding 5.2.1
snapshot. Track docs still require toolkit 2.5.1; `pyproject.toml` retains its broader executable
compatibility range `qfbench2-common>=2.5.0,<3`.

## Relevant executable tests

| Test surface | Git blob |
|---|---|
| `scoring/tests/test_claim_rules_filler_cap_window.py` | `3c4009d0ef0670e52748191fe825650a12099926` |
| `scoring/tests/test_claim_citations_removed.py` | `0fc454ca082dd042385cf551701c44ed98de7346` |
| `scoring/tests/test_number_forms.py` | `eb9c746a883a3e7e572079d7c6bdf1b44a0cf160` |
| `baselines/guardrails_example/tests/test_submitted_reasons.py` | `ab51fc912be6f1853539f4c20558d6308836ca37` |
| `tests/test_strong_rag_answers_pass_the_scorer_gates.py` | `d02503936e62c1ced5a3af7e2d81c6ff12924d20` |
| `baselines/strong_rag_baseline/tests/test_bad_reply_fallback.py` | `7199bae00954443c9508aeb7897ebed25faea48f` |

# Current public unit revisions

No file under `units/` changed between official commits `fe313cee` and `ede7381d`. These are the
current task/card/manifest blobs; they are recorded because the research branch intentionally does
not merge the organizer's unrelated baseline rewrite.

| Unit | `task.json` | `card.toml` | `manifest.json` |
|---|---|---|---|
| `t4-auction-btc-202411-us7` | `848a476d1831d6dc1d2d0c4168f94a5748d631d0` | `7f6c7d0cbfed7aea3bd234a25311e61fbadca68a` | `3a5f5abf358b5bd6e439df2185a8a34505ee7714` |
| `t4-cotpos-202411-us10` | `325b228e24c19c71ce044bf348312e81f1931fc9` | `cae7516dd814925be440370be92c4c246931fce0` | `dac8a12bc841462bcfd6a654af815048578c7e7f` |
| `t4-cpicomp-202410-us11` | `e7e06e61047e30695b92c7b4c7b6779a8236c4b9` | `6f174fbe09198fe05a77dbb485319ed0cc4c6a59` | `f3b2e4e6604993c367c3667aa06a7d7290f7cacb` |
| `t4-credit-event-2023` | `b2ecd4f75dc7a878f597e05396fda6903933509a` | `bfe4da776e128183dd269527202812b64ac7eddf` | `31a792ff783ebacfa22196ccdfe3fc99f81de44f` |
| `t4-eps-growth-2024Q3-banks` | `6a21de470578f056d2a841b7fb13c134f9b363b6` | `12504a6f68c5b3a5fed9f0059301a60bf5d891c8` | `fb7a854f57c98caeba2f562f83a9e3f4065bf1ae` |
| `t4-eps-yoy-2023Q2-mixed` | `d2400ac94467b0756a8a515fa5405ab122237b73` | `c6747e3a01af5bf58bf86e8dddac5fe1723fd7fc` | `bde758d5b0769677d1cd026423aca0fb0270460f` |
| `t4-EXAMPLE-eps-beat` | `2b3e0789f5fe40826a712993de3318cd9241203c` | `1cad52bbc0274e16a394f74f14e4c238993623ad` | `0f63a238a68cd9a1c66e0b8e02451b4d223a1e0c` |
| `t4-fomc-curve-20220728` | `5b095a05128f9b24e818d5329cad7ade40bdd781` | `2d0881fba015be6cff604cff664a9936e4090c3e` | `deace4b1ee6472f63b782a869dea472b5c74da8f` |
| `t4-fomc-curve-20240918` | `1c7ddc85e81d18d5bd98cb149845ac6fc3b5560b` | `a2d621b55f1e977702468790a97d9fa00d9f7772` | `4a3baf3f14b2e3fba0df4df13826e04af410663c` |
| `t4-macrorev-20240930-us6` | `89a2c0495da354da50e7918c5589cc9a39b2f1f6` | `c6dc06e96b29ccac74c8a1230fc70a700de40650` | `e9d57b6e7959aae517ca8bfbd2ca854ccfd09c2e` |
| `t4-postearn-20240201-megacap` | `e79d4bc85ec1ca557ac171d5dfe612ce93b42a99` | `2f13b2148717aaefe93101aa8278fad0ded70ad2` | `05062fa48ef59455b9de0e1428adaab0f9018fff` |

# Exact scorer 5.2.1 to 5.2.2 behavior

| Area | Executable 5.2.2 behavior | Relevance to this agent |
|---|---|---|
| Predictive and interval legs | Classification, regression, ranking, naive anchors, interval formula, interval prediction-quality cap, domain, and worst case are unchanged. | No prediction or calibration change. |
| Content-free claims | After entity names/IDs/tickers and the exact notice `model inference failed` are blanked, a no-figure claim made only of function/meta words is false when only function words remain or an evidence/retrieval/citation filler anchor remains. Status and false reason are `content_free`; the NLI judge is not called. | RC1's fixed prose is deterministically false. Claim generation must state passage content. |
| Citation cap | Any cited span longer than 8,000 characters yields `over_cap` and is false outright, including when claim text is a verbatim quote. | R2.5 caps fallback extracts at 200 characters. |
| Claim shape | A claim cites exactly its own flat `doc_id`, `span_start`, and `span_end`. If it also carries the removed claim-level `citations` key, alignment ignores the list and marks the claim `malformed`/false; the unit is still scored. | Agent outputs no nested list. |
| URL numbers | Numeric normalization blanks ordinary and disguised URLs at equal length before extracting figures. This includes scheme URLs, scheme-less `//host.tld`, `www.` hosts, look-alike slash/colon characters, and invisible fillers. Numbers outside URLs remain figures. | URL IDs cannot anchor a numeric claim and cannot by themselves make it unanchored. |
| Long-passage window | When a citation exceeds the judge's own premise window, candidate windows start at zero and later line/sentence boundaries roughly half a window apart. The window containing the most distinct non-stopword claim terms wins; ties keep the earliest. The judge applies its own cut again to that winning region. | Production/final contradiction behavior only; deterministic smoke checks do not invent an NLI verdict. Exact verbatim claims bypass the NLI contradiction call. |
| False reasons | Ordered set is now `wrong_entity`, `out_of_range`, `malformed`, `over_cap`, `unanchored`, `content_free`, `contradicted`. The penalty formula and soft floor are unchanged. | Smoke and production both charge the new deterministic reasons. |
| Submitted reasons | Caps are planned reason-by-reason in submission order; an over-cap/over-budget/duplicate reason can be skipped while later reasons remain eligible. URLs are folded and masked before judge-byte accounting; the deny list still checks participant text, including disguised forms. | No effect: RC1 and R2.5 emit no `submitted_reasons` field. |
| Contract surface | Answer schema, toolkit version, C5 fixture, and submission interface are unchanged. | No descriptor/package change in this round. |

The claim is deliberately separate from the forecast: scorer 5.2.2 judges whether the cited
passage contradicts the claim, not whether the passage entails the future prediction. R2.5 thus
quotes what the passage says and does not add prose saying that it supports prediction X.

# Frozen RC1 claim audit and R2.5 comparison

Frozen RC1 commit `0c288e4b775c84ac354c3765cb00974314efc48e` hard-codes this exact claim in
`_claim_from_card`: `This pre-cutoff passage was used as evidence for the prediction.` The current
official `content_free` function classifies it as content-free with `figure_status=no_figures`.
`evaluate_claims` emits status/reason `content_free`, does not call NLI, and the unchanged
soft-floor penalty with `penalty_k = 1` gives factor 0 when every claim is false.

Both frozen RC1 and R2.5 were run in mock mode from their own source trees against the exact 11
units at `ede7381d`. Each made one request per unit (11 total), produced all 78 roster rows, and
produced one claim per row. Current 5.2.2 `align_predictions` and `evaluate_claims` were then used
with the official current manifests and corpus text. Contradiction is exactly zero in this
comparison: RC1's claims stop at `content_free`, while every R2.5 claim is a verbatim cited span
and therefore bypasses NLI.

| Result | RC1 | R2.5 |
|---|---:|---:|
| Claims | 78 | 78 |
| False claims | 78 | 4 |
| `content_free` | 78 | 0 |
| `over_cap` | 0 | 0 |
| `unanchored` | 0 | 0 |
| `contradicted` | 0 | 0 |
| `wrong_entity` | 4 | 4 |
| `malformed` | 0 | 0 |
| `out_of_range` | 0 | 0 |
| Schema / ordered roster / offsets / cutoff | 11/11 pass | 11/11 pass |

The four `wrong_entity` reasons occur for `UST_10Y` citing the 2-year COT document, `WE` citing
BBBY's filing, and `C` plus `USB` citing JPM's filing. They are not a 5.2.2 change: document/entity
binding has made claims false since 5.2.0. They arise from the existing mock/model evidence choice
and remain because this focused patch was expressly forbidden from changing retrieval. The
5.2.2-specific false claims caused by our generic construction fell from 78 to zero.

R2.5 changes only `_claim_from_card`: a model-supplied exact nonblank quote becomes both the claim
and the cited slice; a missing or non-matching quote becomes a word-boundary-shortened prefix of
the already trusted retrieved chunk, at most 200 characters. Both paths are extractive, flat,
cutoff-safe by inheritance from retrieval, and preserve exact offsets. Non-claim answer fields are
byte-equivalent after normalizing away `claims`; request counts are identical.

# Validation evidence

- Focused local agent tests: 15 passed, covering exact factual and numeric quotes, URL-bearing
  text, missing/unmatched quote fallback, flat shape, exact offsets, the 8,000-character bound,
  and one- and ten-entity paths.
- Official 5.2.2 claim/number/reasoning tests on Windows: 294 passed. Six integration cases reached
  the known Linux-only secure corpus walker and failed on absent `os.O_DIRECTORY`; no validator or
  scorer code was altered to hide that platform limitation.
- Official Linux CI for `ede7381d`, run `36735895008`: success. Scorer/judge reports 1,155 passed
  and 1 skipped; firewall/baseline reports 283 passed and 17 skipped; lint, mypy, all 11 manifests,
  and public-safety pass.
- Current-unit behavioral audit: 11/11 schema, ordered roster, offsets, and cutoff checks pass for
  both RC1 and R2.5; all R2.5 claim spans are at most 200 characters.

# Known contract/document inconsistencies

- Public card prose still describes the retired 0.80 faithfulness admission threshold. The
  executable scorer applies the 5.2.0 per-claim soft-floor penalty; no claim reason refuses the
  unit structurally.
- `analysis.schema.json` requires the four flat citation/claim fields but does not set
  `additionalProperties: false` on a claim. Consequently a nested `citations` key can pass JSON
  Schema while scorer 5.2.2 marks that claim malformed and false. The executable scorer wins.
- The research branch's checked-in public manifests predate the current entity labels. All final
  counts in this snapshot use the files at official commit `ede7381d`, not those stale local
  copies. The source patch does not rewrite or copy organizer unit data.

# R3 decision

TargetSemantics remains the next prediction-quality experiment because 5.2.2 does not change any
predictive metric and R2.5 does not alter a prediction. The four current `wrong_entity` findings
are a separate evidence-binding robustness item that must be carried into the next preflight
work; they are not evidence for or against TargetSemantics and are not a reason to claim an
accuracy uplift. No image, descriptor, package, or submission was generated.
