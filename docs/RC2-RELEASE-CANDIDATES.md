## Executive summary (read this first)

The exact frozen R3 and R4 source commits were built and pushed as separate Linux/AMD64 images, and both passed anonymous-pull, image-content, non-root, read-only-root, no-network fallback, schema, roster, cutoff, citation, and current scorer smoke checks. The images use the same Dockerfile and differ in runtime source only by the reviewed R4 comparative-context change. The required pre-packaging synthetic stress test found that frozen R4 can exceed its configured 48,000-character planning threshold because the planner undercounts fixed prompt-contract text and cannot split shared comparative context. Packaging stopped at that gate: no descriptors or ZIPs were created, the external Team Key was never accessed, and nothing was uploaded to CodaBench. R3 and R4 remain frozen while this resource-safety bug is reviewed.

## 1. Current rule snapshot

The release gate was re-run before building and matched the requested source of truth.

| Contract | Exact value |
| --- | --- |
| Official Track 4 commit | `ede7381d8c1ba9d8c84068f9d142f5e093a33892` |
| `SCORER_VERSION` | `5.2.2` |
| `qfbench2_track_analysis/scoring.py` blob | `a35c7747f5afe50c4105ec7718b6cd7c78e7c985` |
| Toolkit | `qfbench2-common 2.5.1` under Python 3.13 |
| Submission interface | `2.0` |
| Development descriptor fixture | `qfbench2_common/contracts/fixtures/c5/analysis_dev.json` from toolkit tag `v2.5.1` |

The current House disclosure was re-read from toolkit tag `v2.5.1` at `docs/HOUSE-MODEL.md`. It was not copied into a descriptor because the stress gate failed before descriptor construction.

## 2. Frozen sources and build provenance

| Candidate | Role | Exact source commit | Convenience tag |
| --- | --- | --- | --- |
| R3 | Control | `3f762ed1a53252417a2d53de11cf07cc5b003df4` | `ghcr.io/jiawei-vita-li/agenthon-track4-agent:r3-3f762ed1` |
| R4 | Treatment | `15a09731c607d10c42202aae3e0b28f72de9e2a6` | `ghcr.io/jiawei-vita-li/agenthon-track4-agent:r4-15a09731` |

Both builds used Dockerfile blob `07b496db1a8c04ae15c9a3ebc08d780778d455b2`. The Dockerfile, base-image pin, entrypoint, dependencies, model parameters, retrieval, evidence, fallback, interval, and claim code are identical between the candidates. `git diff 3f762ed1..15a09731` contains only the comparative representation, prompt integration, switch wiring, and its tests. R3 has no comparative-context module or CLI option; R4 defaults the reviewed switch to ON. Both retain TargetSemantics.

The validation-only GitHub Actions workflow lives in fork commit `a97191f6f7b36a9ff4153bf108542d43b57f9971`; it checks out each frozen source SHA into a separate build directory. It does not form part of either runtime source commit. Real-Docker build and validation run: [`36960036425`](https://github.com/jiawei-vita-li/track4-analysis-public/actions/runs/36960036425).

## 3. Immutable images

| Candidate | Immutable image | Size | Build interval (UTC) |
| --- | --- | ---: | --- |
| R3 | `ghcr.io/jiawei-vita-li/agenthon-track4-agent@sha256:9a758b364eddf00a7634228a1d5d8f8ff74150c7b12a1eacf0652f995a25a11d` | 118,349,069 bytes | 2026-10-02 03:25:31–03:25:40 |
| R4 | `ghcr.io/jiawei-vita-li/agenthon-track4-agent@sha256:461dc8ac7c62b1cada5a20a3d658a582f5d29b699e3162872f9b1798a76d3b2b` | 118,362,228 bytes | 2026-10-02 03:24:57–03:25:11 |

Each digest was pulled with an empty temporary Docker configuration after registry logout. Both pulls passed anonymously. Image inspection reported Linux, AMD64, `qfbench2.interface_version=2.0`, and the exact expected source-revision label.

## 4. Image contract and platform-like validation

Both immutable digests passed the following checks on GitHub's Ubuntu Docker daemon:

- entrypoint plus `analyze --task /input/task.json --corpus /input/corpus/ --out /output/answer.json`;
- UID/GID `65534:65534`, read-only root, dropped capabilities, `no-new-privileges`, 64 MiB no-exec `/tmp`, 256 PIDs, bounded `nofile`/`nproc`, and a separately mounted writable output directory;
- `--network=none` normal public-unit mock path on `t4-cotpos-202411-us10`;
- explicitly unavailable House endpoint fallback on `t4-credit-event-2023`;
- exit code zero and non-empty `answer.json` and `trace.json`;
- current answer schema, exact ordered roster with no duplicates, claims present, public manifest safety, and scorer 5.2.2 smoke with `admissible=True`;
- cutoff, citation-span, entity admission, and deterministic claim checks exercised by the current smoke verifier;
- no hidden-write error patterns in container logs;
- no forbidden credential, Team Key, Git metadata, cache, submission archive, or secret-like build-history paths in either image.

The hosted runner used 2 CPUs and a 6 GiB memory limit rather than pretending to provide the platform's larger physical resource grant. All sandbox security properties were retained. The candidate source contains no runtime package/model download and its only network client targets the injected House `MODEL_ENDPOINT`; successful `--network=none` fallback runs provide the execution check.

## 5. Prompt-limit stress result

The synthetic test used only generated pre-cutoff structured rows, a generic ranking target, and deterministic numeric values. It used the frozen R4 planner's production settings: 20 entities per batch, 48,000 estimated input characters, 12,000 output characters, and at most five primary requests. No task ID, outcome, scorer reference, Development result, or model output entered the test.

For eight numeric features, the first split occurs at entity 21 because the per-batch entity cap changes request count from one to two. R3-equivalent OFF and R4 ON both cover those 21 entities exactly once and remain below the threshold. At 30 entities and eight features, R4 produces two batches of 20 and 10 entities, observes a maximum actual prompt of 41,498 characters, and covers all 30 entities once.

The larger cases expose the blocker:

| Mode | Synthetic shape | Batch sizes | Largest estimate | Largest actual prompt | Deferred fallback | Unique coverage |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| R3-equivalent OFF | 40 entities × 8 features | 20, 20 | 11,793 | 13,671 | 0 | 40/40 |
| R4 ON | 40 entities × 8 features | 20, 19, 1 | 47,946 | **52,945** | 0 | 40/40 |
| R3-equivalent OFF | 30 entities × 12 features | 20, 10 | 13,704 | 15,802 | 0 | 30/30 |
| R4 ON | 30 entities × 12 features | 1, 1, 1, 1, 1 | 49,017 | **54,052** | 25 | 30/30 |

R4 does add a third request in the 40×8 case, but every emitted prompt still exceeds 48,000 characters because the estimator omits fixed prompt-contract text. In the 30×12 case, the repeated shared entity table plus comparative context already exceeds the limit before a useful batch can be packed; the planner admits one oversized entity per request and then defers the remaining 25 entities after the five-request cap. Entity completeness remains protected by fallback, but the required invariant—batch instead of exceeding the planning threshold—is not satisfied.

This is a resource-safety and hidden-task generalization defect, not predictive-quality evidence. The frozen R4 algorithm was not modified after discovery.

## 6. Descriptor and package status

The release procedure requires the stress gate to pass before packaging. Consequently:

| Item | R3 | R4 |
| --- | --- | --- |
| `release/*/submission.json` | Not generated | Not generated |
| Toolkit parser/seal validation | Not run | Not run |
| Descriptor diff | Not applicable | Not applicable |
| `release/*/submission.zip` | Not generated | Not generated |
| ZIP SHA-256 | Not available | Not available |
| Package content/claim audit | Not run | Not run |

The external rotated Team Key was never opened, copied, passed to a command, or placed in WSL during this phase. No key material, registry credential, GitHub token, local path, or secret was added to either image or repository. The historical RC1 descriptor, image digest, ZIP, SHA-256, and tag were not changed.

## 7. Planned paired Development evaluation

After an explicitly reviewed resource-safety resolution produces newly frozen candidate provenance and both packages pass current toolkit validation, the planned upload order remains:

1. frozen R3 control;
2. frozen R4 treatment as close in time as practical.

Neither candidate may change between those two submissions, and the R3 score must not be used to tune R4 before R4 is submitted. For each eventual upload, record candidate, source SHA, image digest, ZIP SHA-256, UTC submission time, CodaBench submission ID, scorer version, returned analysis/leaderboard output, and only the diagnostics actually provided by the organizer. No upload was made in this phase, so zero attempts were consumed.

## 8. Remaining blocker and required decision

The frozen R4 candidate violates the requested prompt-limit stress invariant on larger generic structured rosters. Packaging an image known to exceed its own planning threshold would turn a local, zero-cost finding into an avoidable Development failure risk. Because the instruction also freezes the exact R4 algorithm SHA, this report does not silently patch batching or substitute a later runtime commit.

The next decision is whether to authorize a narrowly scoped release-hardening experiment that fixes prompt accounting/shared-context overflow, then re-freezes and rebuilds both paired candidates as needed. Until then, descriptors, team claims, ZIPs, and Development uploads remain intentionally absent.

**BLOCKED — frozen R4 exceeds the 48,000-character planning threshold under the required synthetic larger-roster stress test**
