## Executive summary (read this first)

The competition candidate was built and exercised with the real Docker daemon on a GitHub-hosted
Linux runner. The final workflow run passed image inspection, content checks, all three public
target shapes, an offline run, an unreachable-model fallback, schema validation, and the official
non-rankable smoke verifier. No runtime or Dockerfile defect was found, so this validation branch
changes only the workflow and this report. The candidate is ready for a Development submission;
this result does not claim predictive quality or replace the production faithfulness judge.

## A. Source of truth

The validation used the submission contract in `README.md` and `SUBMISSION_CLI.md`, the candidate
at `baselines/strong_rag_baseline/Dockerfile`, and the executable validators installed from the
shared toolkit version pinned by the repository documentation. The run checked commit
`183a1442c5a50a5116c492534a3853d2dd00be53` on the personal-fork branch
`ci/docker-validation`; the competition-agent checkpoint remains `0c288e4` on
`nightly/t4-agent`.

The workflow is `.github/workflows/docker-validation.yml`. Its uploaded artifact is the
authoritative record for commands, raw image inspection, Docker history, container logs, answers,
traces, and validator output. No resolved outcomes were used or produced.

## B. GitHub Actions run

The final `workflow_dispatch` run is
[36557482355](https://github.com/jiawei-vita-li/track4-analysis-public/actions/runs/36557482355).
It completed successfully in 49 seconds on `ubuntu-latest`. Artifact
`docker-validation-36557482355` has artifact ID `11028229605` and contains the files described by
the workflow's upload step. An earlier successful run, `36557181118`, exposed a weakness in the
test setup rather than the image: a zero-retry setting made no connection attempt. The final run
uses one bounded attempt for both the primary call and the single repair.

## C. Docker build

The runner executed:

```bash
docker build --platform linux/amd64 \
  --file baselines/strong_rag_baseline/Dockerfile \
  --tag t4-task-agent:validation .
```

The final build took 5 seconds with Docker Server 28.0.4. It produced local image ID
`sha256:6d089681b13a0c200ece17a0a43c555445a071ef43208f2a40179d7d53dcf656`.
This is a local image ID, not a registry digest and not a submitted image reference.

## D. Image inspection and content

`docker image inspect` reported Linux on amd64, an uncompressed size of 118,317,522 bytes
(approximately 112.84 MiB), the Python module entrypoint, the expected help command, and the
required interface label. The exact configuration is in the run artifact's
`docker-inspect.json` and `image-summary.txt` rather than duplicated here.

`docker history` shows one 79 kB application-code layer over the pinned Python base. An exported
filesystem-name scan found no SSH material, environment files, credentials, Hugging Face cache,
DeBERTa evaluator weights, validation artifacts, or experiment cache. The scan result and complete
file list are in `image-content-check.txt` and `image-files.txt`. The artifact itself also passed a
credential-pattern scan after download.

## E. Classification run

The classification check used public practice unit `t4-credit-event-2023`. The container exited
0 in 3 seconds, wrote `answer.json`, covered all eight roster entities, and emitted one grounded
claim per entity. Schema validation passed. The official smoke verifier reported
`factory=build_smoke_verifier`, `admissible=True`, and no failure labels.

## F. Regression run

The regression check used public practice unit `t4-auction-btc-202411-us7`. The container exited
0 in under one recorded second, wrote `answer.json`, covered all seven roster entities, and emitted
one grounded claim per entity. Schema validation and the official smoke verifier passed with no
failure labels.

## G. Ranking run

The ranking check used public practice unit `t4-cotpos-202411-us10`. The container exited 0 in
under one recorded second, wrote `answer.json`, covered all ten roster entities, and emitted one
grounded claim per entity. Schema validation and the official smoke verifier passed with no
failure labels.

## H. Restricted-network run

The ranking unit was run again with Docker's `--network=none`. It exited 0 in 1 second and produced
an answer byte-for-byte identical to the ordinary no-model-endpoint ranking run. Its schema and
official smoke checks passed. This proves that the submission image has no hidden public-network
or download dependency; it is not a test of the organiser-injected House route.

## I. Official validator results

Each Docker-produced answer was validated against the shared package's
`analysis.schema.json`. Each corresponding unit was then checked with `qfbench2-smoke` using the
repository's `qfbench2_track_analysis` implementation and the explicitly non-rankable smoke
factory. All five outputs were admissible with empty failure-label lists. The smoke path covers
roster alignment, manifest resolution, cutoff and citation-span admissibility in addition to the
separate schema check. `qfbench2 manifest assert-public-safe` also passed for each selected public
unit.

These public practice units have no resolved outcomes. The run therefore establishes runtime and
admissibility only; it does not measure prediction quality, interval coverage, or rankable
production faithfulness.

## J. Fallback behavior

The final failure simulation used `--network=none` plus a loopback endpoint that refuses
connections. The client made one bounded primary attempt and one bounded repair attempt, recorded
two total requests in its trace, and returned in 5 seconds. It then emitted a complete,
schema-valid eight-entity classification answer with grounded pre-cutoff citations. The result was
byte-for-byte identical to the deterministic no-endpoint fallback and passed the official smoke
verifier.

The exact bounded settings and invocation live in `.github/workflows/docker-validation.yml`; the
raw evidence is in `endpoint-unavailable/run-info.txt`, `logs.txt`, `trace.json`, and
`validation.txt` in the run artifact.

## K. Packaging bugs and fixes

No image packaging bug was found. The candidate entrypoint accepted the harness-supplied
`analyze` verb, every required Python module was present, Linux paths and bind mounts worked, and
no runtime dependency was missing. Accordingly, no runtime, prediction, safety, or Dockerfile code
was changed.

One validation-only correction was made after the first successful run: the unreachable-endpoint
test now permits one attempt instead of zero. This changes only the workflow and makes the failure
simulation exercise a real refused connection.

## L. Remaining risks

The GitHub runner does not reproduce the organiser's audited restricted network, House endpoint,
GPU allocation, or full per-unit resource envelope. The run intentionally used the non-rankable
smoke verifier; it did not package the development-only NLI models and did not execute the
production judge inside the submission image. A future runner-image migration is already announced
by GitHub, although the Docker contract is insulated by the pinned Linux/amd64 base digest. The
image has not yet been pushed to an anonymous registry or packaged into a Development upload, and
this workflow did not perform either action.

## M. Exact reproduction commands

Build and inspect from the repository root:

```bash
docker build --platform linux/amd64 \
  --file baselines/strong_rag_baseline/Dockerfile \
  --tag t4-task-agent:validation .
docker image inspect t4-task-agent:validation
docker history --no-trunc t4-task-agent:validation
```

Run a public unit with the official mount and command shape:

```bash
mkdir -p /tmp/t4-docker-output
docker run --rm --network=none \
  -v "$PWD/units/t4-cotpos-202411-us10:/input:ro" \
  -v "/tmp/t4-docker-output:/output" \
  t4-task-agent:validation \
  analyze --task /input/task.json --corpus /input/corpus \
  --out /output/answer.json --trace /output/trace.json
PYTHONPATH="$PWD" qfbench2-smoke \
  units/t4-cotpos-202411-us10 /tmp/t4-docker-output \
  --track analysis --profile smoke
```

To reproduce every check and upload the same artifact layout, dispatch
`.github/workflows/docker-validation.yml` from the personal fork. The workflow contains the exact
classification, regression, ranking, offline, endpoint-failure, schema, manifest, and smoke
commands used for the final run.

## Readiness

**READY FOR DEVELOPMENT SUBMISSION**
