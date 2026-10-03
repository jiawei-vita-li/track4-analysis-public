## Executive summary (read this first)

The frozen R3 control and R4.1 treatment now have locally persistent submission packages produced by the official `qfbench2-common 2.5.1` toolkit under Python 3.13. The official Track 4 main branch advanced from the earlier rule snapshot by one documentation and baseline-clarification commit, while `SCORER_VERSION` and the executable scoring blob remained unchanged. Both immutable images still satisfy the clarified nested target-type and output-tree contracts without rebuilding either image. Each ZIP passed descriptor, team-claim, structure, digest, and non-secret-content checks, and its local SHA-256 exactly matches the remote packaging copy. Nothing was uploaded to CodaBench.

## 1. Rebased rule snapshot

| Contract | Exact value |
| --- | --- |
| Previous official snapshot | `ede7381d8c1ba9d8c84068f9d142f5e093a33892` |
| Current official snapshot | `1c744e1d6725340643a533f436517d72b53ca0e1` |
| `SCORER_VERSION` | `5.2.2` |
| `qfbench2_track_analysis/scoring.py` blob | `a35c7747f5afe50c4105ec7718b6cd7c78e7c985` |
| Packaging toolkit | `qfbench2-common 2.5.1` |
| Packaging Python | `3.13.15` |
| Submission interface | `2.0` |

The upstream change touched `README.md`, `SUBMISSION_CLI.md`, the public minimal-baseline CLI, its task-shape test, and `docs/CONCEPTS.md`. It did not change `qfbench2_track_analysis/scoring.py`. This is a documentation and baseline-clarification advance, not scorer drift, so the frozen R3 and R4.1 sources, images, and descriptors were not rebuilt or edited.

## 2. Frozen candidates

| Candidate | Exact source commit | Immutable Linux/AMD64 image |
| --- | --- | --- |
| R3 control | `3f762ed1a53252417a2d53de11cf07cc5b003df4` | `ghcr.io/jiawei-vita-li/agenthon-track4-agent@sha256:9a758b364eddf00a7634228a1d5d8f8ff74150c7b12a1eacf0652f995a25a11d` |
| R4.1 treatment | `80961b68768154ba05cbd6ba00f38e3e04a7b495` | `ghcr.io/jiawei-vita-li/agenthon-track4-agent@sha256:60ab12d37026d41fcf7c1837f53486729a933af1799ebf62b429220adbc4831a` |

Registry inspection by immutable digest reported `linux/amd64` for both images. The earlier R4-v1 prompt-budget blocker is superseded by the separately reviewed and frozen R4.1 source; this release record does not modify either candidate.

## 3. Clarified-contract audit

Both immutable images were pulled anonymously by digest into an OCI layout on `agent-gpu`. Because that disposable AutoDL environment does not expose `CAP_SYS_ADMIN`, it cannot run a Docker daemon; the previously completed GitHub Actions real-Docker sandbox validation remains the full container-runtime evidence. For this clarification audit, the original image root filesystems were unpacked and executed with UID/GID 65534, read-only copied inputs, a dedicated writable output, `QFBENCH_NETWORK=none`, and no House credentials.

Each image ran one current public unit for every supported target type:

| Candidate | Classification | Regression | Ranking |
| --- | --- | --- | --- |
| R3 | PASS | PASS | PASS |
| R4.1 | PASS | PASS | PASS |

For all six executions, `answer.json.target_type` matched `task["target"]["type"]`, the ordered entity roster was complete, and the process exited zero. Every output contained exactly the authorized `answer.json` and `trace.json`; there were no extra directories, symbolic links, hard links, special files, sparse files, non-NFC names, drive-letter-style names, or write-error diagnostics. Total output sizes ranged from 6,602 to 33,354 bytes, safely below 64 MiB.

## 4. Descriptor validation

The existing sealed descriptors were copied without modification and their local and remote file hashes matched. Under `qfbench2-common 2.5.1`, both passed `SubmissionDescriptor.from_mapping`, and `seal_descriptor_digest` reproduced each descriptor exactly.

| Candidate | Descriptor digest | Validation |
| --- | --- | --- |
| R3 | `sha256:ab4e3d739b16a9a90d3cfbc0765432b8d658c8205f4b0f780b92b1704a85b7f5` | PASS |
| R4.1 | `sha256:ddc8b6c1349ec2db9267aef3ac322ddf2eb82060c157305dcf9b7afd775b6954` | PASS |

Both descriptors declare `track=analysis`, `phase=dev`, `category=api`, `interface_version=2.0`, the expected immutable image digest, and the toolkit-derived team identifier `team-a5feec08147ef9378eebcdbd1b1ad1c2`.

## 5. Submission packages

| Candidate | Local persistent package | ZIP SHA-256 | Package validation |
| --- | --- | --- | --- |
| R3 | `release/r3/submission.zip` | `abc8c366b57ff150aa69ce0bd440f4c037917d44c9caf4a73acdcaa07a37bc37` | PASS |
| R4.1 | `release/r4_1/submission.zip` | `7641e86abfdcbefd4515799322d99199916af68160e7214508ebac19215f0546` | PASS |

Each archive has exactly two root entries: `submission.json` and `team-claim.json`. The archived descriptor is logically identical to its pre-packaging sealed descriptor. Each claim has schema version `2.0`, website team number `611`, the SHA-256 of the exact archived descriptor bytes, and a correctly shaped proof. The remote and local ZIP SHA-256 values match exactly.

## 6. Security record

The rotated Team Key remained in its external local file and was sent only as the standard input file handle of the one remote packaging process. The remote script installed it into the native Linux packaging temporary directory with mode `0600`, passed only its path through the official `--team-key-file` option, and registered an exit trap before packaging. The temporary remote file was deleted immediately after both packages were produced, and a subsequent independent existence check confirmed it was absent.

The Team Key content was not placed in command-line arguments, environment variables, repository files, Docker images, GitHub Actions, descriptors, ZIP entries, stdout, stderr, logs, or chat output. A strict JSON-field allowlist plus credential/path pattern scan passed for both packages; no registry credential, GitHub token, local path, or Team Key field was present. The canonical Windows key file was not modified.

## 7. Release status

R3 and R4.1 are packaged, validated, and stored locally with verified hashes. The remote copies are disposable; the local repository paths above are the persistent release artifacts. No CodaBench upload or Development submission was performed, so no submission attempt was consumed.

**R3/R4.1 PACKAGES READY — RULE SNAPSHOT REBASED TO 1c744e1d — AWAITING CODABENCH UPLOAD APPROVAL**
