## Executive summary (read this first)

Competition Agent v1 is a contract-first, target-type-generic design for Track 4. It treats the
task, manifest-declared frozen corpus, answer schema, and official gates as trusted inputs rather
than dispatching on published family names. The first objective is to always emit one valid row per
roster entity without allowing post-cutoff or unresolved evidence into reasoning. The second is to
make citation selection optimize entailment of the scorer's canonical prediction hypothesis, not
the participant-authored claim prose. Prediction quality and interval calibration are layered on
only after those invariants are enforced.

# Competition Agent v1 — Generic Track 4 Design

## Source-of-truth assumptions

- Parse `target.type`, target name, optional label vocabulary, interval level, cutoff date, prompt,
  and the complete ordered entity roster from `task.json`.
- Treat `family` as descriptive metadata, never as a closed dispatch enum.
- Resolve citable documents only through the unit manifest. A JSON file merely present under
  `corpus/` is not automatically trusted.
- Filter missing-date and `doc_date > cutoff_date` documents before indexing, retrieval, prompt
  construction, or prediction. A final output filter remains a backstop, not the primary control.
- Preserve the scorer's document-text convention exactly: flat `text` as-is, otherwise span texts
  joined with one ASCII space. Store offsets into that canonical string.
- Build and inspect the same canonical hypothesis as
  `qfbench2_track_analysis.hypothesis.canonical_hypothesis` before choosing citations.
- Never use a real-world resolved outcome, a post-cutoff document, or a public-unit answer as a
  prediction feature.

## Proposed pipeline

```text
task.json + trusted manifest + corpus/
        |
        v
TaskContract parser --------------------------------------------+
  target type/name/labels, interval level, cutoff, roster       |
        |                                                       |
        +--> manifest-bound CorpusStore                         |
               digest/identity checks                           |
               canonical document text + exact offsets          |
               pre-index cutoff filtering                       |
                       |                                        |
structured entity row | cutoff-safe chunks                     |
          \            /                                       |
           v          v                                        |
        QueryPlanner -> BM25 retrieval -> diversified candidates|
                                      |                         |
                                      v                         |
                          House-model prediction request         |
                       (batched within 25-request budget)         |
                                      |                         |
                                      v                         |
                  typed candidate prediction + uncertainty       |
                                      |                         |
                                      v                         |
                       canonical hypothesis builder <-------------+
                                      |
                                      v
                 evidence reranker / entailment-aware selector
                    exact quote -> exact corpus span only
                                      |
                                      v
                      deterministic repair and fallback
                                      |
                                      v
        complete predictions + 90% intervals + >=1 citation/entity
                                      |
                                      v
          local preflight: schema -> roster -> numeric -> cutoff -> spans
                                      |
                                      v
                                answer.json
```

## Module contracts

### 1. TaskContract parser

Return a typed immutable object containing task id, target type, target name, allowed labels,
interval level, cutoff/resolution dates, prompt, and ordered entities. Validate unknown target
types, duplicate/empty entity ids, malformed label vocabularies, and absent required fields before
any model call. Support both the repository's nested `target.type` and the published top-level
compatibility shape, while refusing disagreement if both are present.

Do not infer semantics from an EPS-specific key. Retain all unknown entity fields as structured
features and separately classify their JSON types (finite numeric, categorical string, boolean,
list/object, missing).

### 2. Manifest-bound CorpusStore

Load only manifest entries with `role = "corpus"`. Verify file identity where the runtime makes
the trusted manifest available, reject duplicate document ids, require a parseable document date,
and filter embargo-ineligible documents before text reaches the retriever. Record canonical text,
document date, source metadata, and an offset-preserving chunk map.

Chunk flat text by sentence/paragraph boundaries with overlap, but retain `(doc_id, start, end)`
into the unchanged canonical string. Never normalize whitespace before calculating offsets.
Normalization may be used in a parallel retrieval representation only if every result maps back to
the original substring.

### 3. QueryPlanner and retrieval

Build queries from the task prompt, target name/type, entity identity, descriptions, categorical
features, and names of informative numeric fields. Avoid a universal earnings-oriented suffix.
Use BM25 first because it is deterministic and requires no prohibited neural artifact. Add:

- entity/document scoping derived from `corpus_ref` when it is meaningful, with a safe global
  fallback for shared-document units;
- query variants for target language, entity aliases, and feature names;
- per-document caps and maximal-marginal-relevance-style lexical diversity;
- a small Top-K sized to the House context and request budget, retaining extra candidates for
  post-prediction citation reranking.

Retrieval relevance and prediction support are different objectives. A passage about the right
company but the wrong quantity is not useful evidence.

### 4. Generic prediction layer

Use a typed prompt containing the full target contract, the entity row, cutoff date, and numbered
evidence spans. Ask the House model for strict JSON with prediction, interval rationale inputs,
and verbatim evidence quotes. The response parser must reject booleans/non-finite numbers,
off-vocabulary labels, inverted intervals, and malformed JSON.

Batch entities where possible. The public roster can exceed the 25-request House limit, so one
request per row is not a valid generic strategy. Ranking should be reasoned over the cross-section
or normalized globally after entity scoring; optional ranks must be a full `1..n` permutation.

If the House endpoint is absent, times out, or returns unusable output, fall back per entity to a
deterministic target-type-generic predictor using finite structured features. The fallback is not
expected to be accurate, but it must still finish within the unit timeout and emit a complete,
finite, schema-valid answer.

### 5. Faithfulness-aware citation selection

Locate model quotes as exact substrings and reject any quote that cannot be mapped back to a
retrieved, embargo-eligible document. Then build the official canonical hypothesis from the
candidate label/value/rank and interval. Rerank candidate spans for support of that complete
hypothesis. Claim prose is an audit note only and cannot rescue a prediction.

When no candidate supports the prediction, the repair order is:

1. search additional pre-cutoff candidates for the same entity and target;
2. revise the prediction toward what the strongest evidence actually supports;
3. widen or revise the interval only if the evidence supports the revised canonical sentence;
4. emit the safest fully grounded fallback available, while preserving schema completeness.

Exact offsets and embargo eligibility are hard constraints. Local NLI is a development oracle, not
a model that may be bundled into the submission unless the artifact policy explicitly permits it.

### 6. Interval calibration

Separate point prediction from interval construction. v1 should use target-scale features and
declared units, not the largest arbitrary numeric value in the entity row. A later permitted
calibration artifact can estimate residual quantiles using cutoff-eligible training data and must
be disclosed under the artifact/training policies.

The scorer rewards coverage near the declared level and has no width penalty. Therefore broad
fallback intervals are safer than unjustifiably narrow ones, but blindly forcing 100% coverage
still pays a calibration penalty. Pure-label outcomes have no calibration leg even though the
schema still requires intervals.

### 7. Deterministic OutputBuilder and preflight

The builder owns roster order and creates exactly one row for every entity. Before atomic output,
validate:

- task id and target type consistency;
- exact entity-set equality and optional global rank permutation;
- required prediction field for each target type;
- finite JSON numbers only, with `lo <= hi` and exact interval level;
- non-empty claims for every entity;
- manifest-resolvable document ids, parseable pre-cutoff dates, and non-empty in-range spans;
- canonical hypothesis generation for every entity;
- output against the installed official `analysis.schema.json`.

Write to a temporary file and atomically replace `answer.json` only after preflight succeeds. Keep
a last-resort complete fallback answer in memory so a House/model exception never leaves no output.

## Request, timeout, and failure budgets

- Reserve at least one House request for repair or synthesis; never spend all 25 on first-pass
  per-row calls.
- Enforce a unit-level deadline below the card's 600-second ceiling and derive per-call timeouts
  from remaining time.
- Retry only failures likely to be transient, with a strict global request counter because each
  admitted retry consumes another slot.
- Catch exceptions at entity/batch boundaries, record compact local diagnostics, and continue with
  deterministic fallbacks.
- Disable vendor-side tools and use only the harness-provided House endpoint, name, and bearer.

## What v1 deliberately does not add yet

- No dense neural retriever or bundled checkpoint.
- No family-name dispatch table.
- No learned calibration head without eligible training data and measured benefit.
- No multi-agent orchestration that spends requests without a demonstrated gate or quality gain.
- No use of public practice outcomes or real-world future knowledge.

These remain experiments behind the contract-first pipeline, not prerequisites for a reliable
first competitive agent.
