## Executive summary (read this first)

R4.1 fixes the release-blocking prompt-budget defect without changing the R4 comparative statistics or prediction hypothesis. Planning and execution now share one exact renderer, full-roster statistics remain global, and derived relative rows are included only for the entities in the current prediction batch. Both required synthetic stress cases stay below 48,000 full-request characters with no deferred entity or planning fallback, while all 11 public mock answers remain byte-identical to frozen R4-v1. A new immutable Linux/AMD64 image passed platform-like validation and current scorer smoke. The descriptors are valid, but ZIP packing is blocked because the approved local WSL 0600 key environment currently cannot start; the Team Key was never accessed and no Development attempt was consumed.

## 1. Scientific interpretation

R4-v1 at `15a09731c607d10c42202aae3e0b28f72de9e2a6` remains the historical frozen algorithm. Its comparative method is valid, but its prompt representation is release-unsafe for larger rosters because every batch repeats every entity's derived relative rows and the planner measures a different partial serialization from the one sent to the House model.

R4.1 at `80961b68768154ba05cbd6ba00f38e3e04a7b495` is a resource-safety correction discovered before outcome evaluation. It preserves the same numeric admission, finite-value, unit-conflict, median/min/max, average-rank, percentile, relation-to-median, no-direction, TargetSemantics, retrieval, evidence, claim, interval, fallback, model-parameter, and answer-schema behavior. It makes no predictive-method or predictive-quality claim.

## 2. Exact implementation

`baselines/strong_rag_baseline/prompting.py` is now the single renderer for both planning and execution. The budget covers the exact system string plus exact user string passed to `ModelClient.complete`. The planner greedily renders every candidate batch and accepts it only when entity, exact-input, and output limits all pass. A single-entity overflow is recorded as `single_entity_prompt_overflow` and deferred to the existing deterministic fallback rather than sent.

Immediately before both primary and repair calls, the runtime renders the same request again and rejects it if the exact full-request size exceeds the frozen 48,000-character limit. Guard diagnostics enter trace as `prompt_guard_failures`; a rejected request is never sent.

The full trusted roster still determines every summary and rank. Prompt representation now contains global full-roster feature summaries and only the current batch's already-computed relative rows. Raw numeric values remain in `COMPLETE_ENTITY_TABLE`; raw values, skipped-feature provenance, and full per-entity comparative detail remain in trace. No comparative record is recomputed from a batch subset.

Changed runtime files:

- `baselines/strong_rag_baseline/prompting.py`;
- `baselines/strong_rag_baseline/comparative_context.py`;
- `baselines/strong_rag_baseline/task_context.py`;
- `baselines/strong_rag_baseline/task_predictor.py`.

Regression coverage is in `baselines/strong_rag_baseline/tests/test_prompt_budget_safety.py`.

## 3. Required synthetic stress gates

Both cases use deterministic generated structured rows, a generic ranking target, the production 20-entity batch cap, the unchanged 48,000-character full-request cap, the unchanged 12,000 output-character cap, and the unchanged five-primary-request cap. They use no outcomes, task IDs, scorer references, Development results, or previous model outputs.

| Variant | Synthetic shape | Batch sizes | Maximum exact full request | Deferred | Planning fallback | Unique coverage |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| R3-equivalent OFF | 40 × 8 | 20, 20 | 13,671 | 0 | 0 | 40/40 |
| R4-v1 | 40 × 8 | 20, 19, 1 | 52,945 | 0 | 0 | 40/40 |
| R4.1 | 40 × 8 | 20, 20 | **27,525** | 0 | 0 | 40/40 |
| R3-equivalent OFF | 30 × 12 | 20, 10 | 15,802 | 0 | 0 | 30/30 |
| R4-v1 | 30 × 12 | 1, 1, 1, 1, 1 | 54,052 | 25 | 25 | 30/30 |
| R4.1 | 30 × 12 | 20, 10 | **35,980** | 0 | 0 | 30/30 |

For every R4.1 batch, `planned_actual_prompt_chars` exactly equals the renderer's system-plus-user character count. The pre-send guard is zero-trigger in passing tests and rejects a deliberately oversized synthetic plan without calling the client.

## 4. Public 11-unit resource comparison

The R3 and R4-v1 totals below add their recorded exact user prompts to the unchanged exact system-prompt length for each of the 11 requests. R4.1 records the combined value directly from the shared renderer.

| Variant | Total full-request chars | Maximum full request | Batches | Requests | Deferred | Fallback entities |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R3 | 271,858 | 45,174 | 11 | 11 | 0 | 1 |
| R4-v1 | 297,692 | 46,131 | 11 | 11 | 0 | 1 |
| R4.1 | 294,215 | 45,888 | 11 | 11 | 0 | 1 |

R4.1 produced zero parse failures, repairs, runtime-guard failures, single-entity overflows, and deferred entities. It produced 78 claims. Every R4.1 `answer.json` is byte-identical to both prior R4-v1 and R3 controlled mock output, so this hardening changes prompt representation and batching safety, not mock predictions.

## 5. Tests and scorer validation

- Local Python 3.13 / toolkit 2.5.1 strong-baseline suite: 106 passed.
- Local focused R4.1/R4/R3 tests, including the single-overflow regression: 48 passed.
- Documentation/firewall selection: 18 passed.
- Ruff lint and changed-file formatting: passed.
- Linux complete baseline suite in release CI: 171 passed.
- All 11 image-executed public `--mock` units: current scorer 5.2.2 smoke `admissible=True` and byte-identical to R4-v1.
- Representative platform sandbox and unavailable-House fallback: schema, roster, cutoff, citations, deterministic claims, and image-content audit passed.

Native Windows additionally ran the combined baseline set with 166 passes and four known platform-only failures: three locale decoding/POSIX path assumptions and one `/output` existence assertion. The exact same set passed 171/171 on Linux; no runtime code was changed for Windows-only behavior.

## 6. R4.1 image

| Field | Value |
| --- | --- |
| Source commit | `80961b68768154ba05cbd6ba00f38e3e04a7b495` |
| Tag | `ghcr.io/jiawei-vita-li/agenthon-track4-agent:r4-1-80961b6` |
| Immutable image | `ghcr.io/jiawei-vita-li/agenthon-track4-agent@sha256:60ab12d37026d41fcf7c1837f53486729a933af1799ebf62b429220adbc4831a` |
| Size | 118,366,528 bytes |
| Platform | Linux/AMD64 |
| Interface label | `2.0` |
| Dockerfile blob | `07b496db1a8c04ae15c9a3ebc08d780778d455b2` |
| Anonymous digest pull | PASS |
| Secret/path scan | PASS |
| CI run | [36961862566](https://github.com/jiawei-vita-li/track4-analysis-public/actions/runs/36961862566) |

The earlier R4-v1 digest `sha256:461dc8ac7c62b1cada5a20a3d658a582f5d29b699e3162872f9b1798a76d3b2b` was not reused. The valid R3 digest remains `sha256:9a758b364eddf00a7634228a1d5d8f8ff74150c7b12a1eacf0652f995a25a11d` and was not rebuilt.

## 7. Descriptor status

Toolkit 2.5.1 `SubmissionDescriptor.from_mapping` and `seal_descriptor_digest` both pass for:

| Candidate | Descriptor | Descriptor digest |
| --- | --- | --- |
| R3 | `release/r3/submission.json` | `sha256:ab4e3d739b16a9a90d3cfbc0765432b8d658c8205f4b0f780b92b1704a85b7f5` |
| R4.1 | `release/r4_1/submission.json` | `sha256:ddc8b6c1349ec2db9267aef3ac322ddf2eb82060c157305dcf9b7afd775b6954` |

The descriptors differ only in image digest and the descriptor digest derived from it. Track, phase, category, competition ID, interface, public access, license, team ID, and the current official House disclosure are identical.

## 8. Packaging blocker

The approved secure packaging procedure requires a temporary mode-0600 Team Key copy on a native WSL filesystem. The default Ubuntu registration currently points to a missing `ext4.vhdx`, and the dedicated `AgenthonT4v1` environment also fails to start with `Wsl/Service/CreateInstance/0xd0000034`. `wsl --shutdown` and a reversible temporary default-distribution switch did not restore it.

No destructive WSL action, unregister, import, monkey patch, permission-check bypass, remote Key copy, or GitHub Actions secret was attempted. The external Windows Team Key was never read, opened, copied, printed, or passed to a process in this phase. Therefore `release/r3/submission.zip` and `release/r4_1/submission.zip` do not yet exist, their hashes and team claims cannot be audited, and no CodaBench upload occurred.

After the user restores WSL—normally by rebooting Windows—the safe continuation is to use the previously approved native-filesystem `mktemp`, mode-0600 `install`, toolkit 2.5.1 `--team-key-file`, trap cleanup, package inspection, digest verification, and secret scan. No algorithm or image rebuild is needed.

**BLOCKED — approved WSL-native 0600 Team Key packaging environment cannot start (`0xd0000034`), so the two required ZIPs cannot yet be produced or validated**
