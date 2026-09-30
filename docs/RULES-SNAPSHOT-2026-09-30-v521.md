## Executive summary (read this first)

This snapshot pins the Track 4 development baseline to official track commit `fe313cee` and
scorer 5.2.1. The scoring change caps interval credit by prediction credit and strengthens the
numeric consistency check for claims; it does not change the prediction metric, structural gates,
metric domain, or failure floor. The current submission toolkit is `qfbench2-common` 2.5.1, but
its C5 descriptor, packer, team-claim, and Track 4 Development fixture are byte-identical to
2.4.4. The frozen RC1 package therefore remains current-contract compatible and was not repacked.
Public outcomes remain unavailable, so this document makes no predictive-quality claim.

# Source hierarchy and immutable identities

The hierarchy used for every conclusion below is: executable scorer and toolkit contracts first,
official tests second, current track documentation third, README and `docs/CONCEPTS.md` fourth,
and historical notes last. A prose statement that conflicts with code is identified explicitly
under "Known inconsistencies" and is not used as a rule.

| Item | Current official value |
|---|---|
| Track upstream | `Agenthon-2026/track4-analysis-public` |
| Track commit | `fe313cee2865fbfbe47b65a8fcf7b830a40ea141` |
| `qfbench2_track_analysis/scoring.py` Git blob | `76b922d9f706b71ab073ed54634d55d41929a6a6` |
| `scoring.py` file SHA-256 | `3af317c6fd9b851a11a5ce901d731316ec2c224bf715c312a6b6731c8e7584ba` |
| `SCORER_VERSION` | `5.2.1` |
| `qfbench2_track_analysis/numeric.py` Git blob | `772907c77af341ac99dbcba5d6c19c701de1732b` |
| `numeric.py` file SHA-256 | `e821d77b9ce66e137c126bd23e4f88ea90c12027ec1f38d8d0ccee345f2b7f35` |
| Toolkit tag / package | `v2.5.1` / `qfbench2-common 2.5.1` |
| Toolkit tag commit | `50fb2dc2b39c70f4cf81fcd269943782eddfaed0` |
| Track package dependency | `qfbench2-common>=2.5.0,<3`; participant docs pin `v2.5.1` |
| Submission interface | `2.0` |
| Development descriptor fixture | `contracts/fixtures/c5/analysis_dev.json`, C5 `schema_version = 1.0.0` |
| Fixture Git blob | `56724ffb7b6dc91e5b266baba8c6445399091a3f` |

The fixture's example model row is illustrative. An actual House submission uses the disclosure
in the current official `docs/HOUSE-MODEL.md`, reproduced by reference rather than treating the
fixture's example values as a model grant.

# Current public unit revisions

These are Git blob identities at the track commit above. They pin the participant-visible task,
card, and top-level manifest without copying any outcome material.

| Unit | `card.toml` blob | `task.json` blob | `manifest.json` blob |
|---|---|---|---|
| `t4-auction-btc-202411-us7` | `7f6c7d0cbfed7aea3bd234a25311e61fbadca68a` | `848a476d1831d6dc1d2d0c4168f94a5748d631d0` | `3a5f5abf358b5bd6e439df2185a8a34505ee7714` |
| `t4-cotpos-202411-us10` | `cae7516dd814925be440370be92c4c246931fce0` | `325b228e24c19c71ce044bf348312e81f1931fc9` | `dac8a12bc841462bcfd6a654af815048578c7e7f` |
| `t4-cpicomp-202410-us11` | `6f174fbe09198fe05a77dbb485319ed0cc4c6a59` | `e7e06e61047e30695b92c7b4c7b6779a8236c4b9` | `f3b2e4e6604993c367c3667aa06a7d7290f7cacb` |
| `t4-credit-event-2023` | `bfe4da776e128183dd269527202812b64ac7eddf` | `b2ecd4f75dc7a878f597e05396fda6903933509a` | `31a792ff783ebacfa22196ccdfe3fc99f81de44f` |
| `t4-eps-growth-2024Q3-banks` | `12504a6f68c5b3a5fed9f0059301a60bf5d891c8` | `6a21de470578f056d2a841b7fb13c134f9b363b6` | `fb7a854f57c98caeba2f562f83a9e3f4065bf1ae` |
| `t4-eps-yoy-2023Q2-mixed` | `c6747e3a01af5bf58bf86e8dddac5fe1723fd7fc` | `d2400ac94467b0756a8a515fa5405ab122237b73` | `bde758d5b0769677d1cd026423aca0fb0270460f` |
| `t4-EXAMPLE-eps-beat` | `1cad52bbc0274e16a394f74f14e4c238993623ad` | `2b3e0789f5fe40826a712993de3318cd9241203c` | `0f63a238a68cd9a1c66e0b8e02451b4d223a1e0c` |
| `t4-fomc-curve-20220728` | `2d0881fba015be6cff604cff664a9936e4090c3e` | `5b095a05128f9b24e818d5329cad7ade40bdd781` | `deace4b1ee6472f63b782a869dea472b5c74da8f` |
| `t4-fomc-curve-20240918` | `a2d621b55f1e977702468790a97d9fa00d9f7772` | `1c7ddc85e81d18d5bd98cb149845ac6fc3b5560b` | `4a3baf3f14b2e3fba0df4df13826e04af410663c` |
| `t4-macrorev-20240930-us6` | `c6dc06e96b29ccac74c8a1230fc70a700de40650` | `89a2c0495da354da50e7918c5589cc9a39b2f1f6` | `e9d57b6e7959aae517ca8bfbd2ca854ccfd09c2e` |
| `t4-postearn-20240201-megacap` | `2f13b2148717aaefe93101aa8278fad0ded70ad2` | `e79d4bc85ec1ca557ac171d5dfe612ce93b42a99` | `05062fa48ef59455b9de0e1428adaab0f9018fff` |

Between scorer snapshots 5.2.0 (`febb5d2f`) and 5.2.1 (`fe313cee`), no corpus document changed.
Task changes are publication-status wording; cards and manifests move with that wording. The
target schemas, rosters, features, cutoffs, and corpus contents used by the agent did not change.

# Scorer 5.2.0 to 5.2.1 implementation diff

| Area | Executable 5.2.1 behavior | Impact classification |
|---|---|---|
| Predictive leg | No implementation change to classification accuracy, regression soft MAE ratio, ranking Spearman anchoring, or naive prediction anchor. | No direct prediction-algorithm change. |
| Interval leg | Computes `raw_interval_quality = naive_IS / (naive_IS + own_IS)`, then `interval_quality = min(raw_interval_quality, max(0.5, predictive_quality))`. Below 0.5 the raw penalty is unchanged. | Affects interval strategy and couples it to prediction quality. |
| Interval diagnostics | Adds `raw_interval_quality`; it is `None` when no interval leg is scored. | Diagnostic only. The scorer says diagnostics are operator-only and not serialized into a participant result. |
| Equivalent number forms | Fractions of points, number words before units, and glued `bp`, `bps`, `pp`, `ppt`, `pt`, `pts`, `x`, currency-`mm`, and related extraction forms are normalized. | Affects claim generation and local claim checking. |
| False numeric positives | Month/day dates, two-day meeting dates, index bases, period labels, and rule/section numbers are excluded more carefully. | Affects claim generation; reduces accidental false claims. |
| Own-value exemption | Uses exact, float-noise-free equality at the passage matcher's permitted scale steps; no rounding. Written rise/fall direction must agree with the submitted value's sign. | Affects claim generation, not prediction values. |
| Interval claim figures | A written `±` value is exempt only when it exactly equals half the scored interval width. The unit interval level is exempt only beside interval wording. | Affects interval prose and claim generation. |
| Faithfulness | Still the 5.2.0 per-claim false-claim penalty. No 0.80 admission gate returns. Prediction relevance remains recorded but unenforced. Numeric changes can alter whether a claim is `unanchored`. | Claim scoring changed only through numeric consistency. |
| Structural gates | Schema, exact roster, citation resolution, cutoff/resource, malformed payload, and organizer-fault behavior are unchanged. Structural failure still assigns the unit worst case. | Submission contract unchanged. |
| Domain and floor | Direction `desc`, domain `[0, 1]`, participant worst case `W = 0.0`. | Unchanged. |

The cap has a direct optimization consequence: an interval trick cannot compensate for weak point
predictions. Copying the naive points gives predictive quality 0.5 and therefore caps interval
quality at 0.5 even if the submitted band has a better raw interval score.

# Current runtime and House budget

The current official Development runtime grants Track 4 16 CPU quota, 128 GiB memory, a
600-second container ceiling, and restricted House access. The common sandbox is non-root with a
read-only root and `/input`, writable `/output`, a 64 MiB `noexec,nosuid,nodev` tmpfs at `/tmp`,
256 PIDs, `nproc` 256, `nofile` 1024, dropped capabilities, no-new-privileges, at most 64 MiB per
file and for the accepted output tree, and a requested 1 GiB writable-layer quota even though the
root stays read-only. Swap is disabled and the selected Development OCI runtime is `runc`.

The House allowance is 25 admitted generation requests per unit and at most 4,000 output tokens
per request. There is no cumulative input/output token allowance per unit. An admitted request is
charged before forwarding and an upstream error does not refund it. The descriptor disclosure is
the five-field row in the current official `docs/HOUSE-MODEL.md`: model
`nvidia/nemotron-3-super-120b-a12b`, version and revision `rl-030326-fp8`, training cutoff
`unpublished`, access `api`.

# Toolkit 2.4.4 to 2.5.1 submission audit

The following five files have identical Git blobs at tags `v2.4.4` and `v2.5.1`:

| Contract surface | Identical blob |
|---|---|
| `contracts/descriptor.py` | `a73f7d49613f9f7944b8f99c5f8c3b97306f6eb2` |
| `schemas/submission.schema.json` | `9c71b5252d930d314c9898629ca9f5153f39b948` |
| `contracts/fixtures/c5/analysis_dev.json` | `56724ffb7b6dc91e5b266baba8c6445399091a3f` |
| `team_claim.py` | `9fc1c84635ea2ae54bdc658e00efaf75fdc9a587` |
| `cli.py` | `0e0552ee91ed0c59026a57c1c3e0c91356624810` |

Therefore C5 `schema_version` support, descriptor fields, team alias derivation, canonical sealing,
team-claim schema/proof construction, `image_access`, `models`, `competition_id`, `category`, and
pack behavior did not change. The JSON Schema accepts C5 `1.0.0` and `1.1.0`, while the parser
accepts compatible major version 1; the current Track 4 fixture and RC1 both use `1.0.0`. Toolkit
2.5.1 changes other contracts and Track 4 answer/scoring primitives, but not the participant
submission package format.

The historical RC1 ZIP was read without modification by a clean Python 3.13 / toolkit 2.5.1
environment. `SubmissionDescriptor.from_mapping` passed; re-running `seal_descriptor_digest`
produced the existing descriptor byte-for-byte; the claim's `descriptor_sha256` matched the exact
`submission.json` member; the claim has exactly its four schema-2.0 fields; and the archive has
exactly `submission.json` and `team-claim.json`. Its House disclosure equals the current official
five-field disclosure. The proof was not recomputed because policy permits the Team Key only as a
packer `--team-key-file` input; the proof algorithm and packer are byte-identical across the two
toolkit tags.

Answers to the compatibility questions are consequently:

1. The existing RC1 ZIP validates under the current 2.5.1 descriptor and structural claim checks.
2. Its descriptor passes current `SubmissionDescriptor.from_mapping`.
3. Its descriptor digest remains valid.
4. Its House model disclosure remains current.
5. Its team-claim format remains current and its descriptor binding is valid.
6. Repacking is unnecessary. No `RC1-v251-package` was generated.

# RC1 current-compatibility evidence

The frozen source commit `0c288e4b775c84ac354c3765cb00974314efc48e` was executed in mock
mode against all 11 current public units. It emitted 78/78 roster rows and 78 grounded claims.
Every unit passed the current 2.5.1 answer schema, exact ordered roster, finite-value, ranking
shape, citation offset, and cutoff checks; current 5.2.1 numeric checking found zero unanchored
claims. Comparing the same deterministic source on the frozen RC1 unit files and current unit
files produced identical answer bytes for all 11 units.

Official Linux CI for upstream commit `fe313cee` is run
`36673151195`: scorer and judge tests report 955 passed and 1 skipped; baseline/firewall tests
report 152 passed and 2 skipped; lint, type checking, manifest validation, and public-safety all
pass. A Windows rerun correctly failed closed where the secure corpus walker requires Linux
`O_DIRECTORY`/`O_NOFOLLOW`; it was not treated as a scorer failure. Local Docker could not be
rerun because Docker Desktop again hit its known stale `dockerInference` AF_UNIX object. The
immutable RC1 manifest remains anonymously inspectable at its frozen digest, the runtime contract
did not change in this rebaseline, and the prior real linux/amd64 plus platform-sandbox validation
recorded in `docs/RC1-FREEZE.md` remains the applicable runtime evidence.

No outcome was read or reconstructed. These are contract and behavior checks only:
**NO PREDICTIVE QUALITY CLAIM**.

# Known inconsistencies and cautions

- Current `card.toml` prose still says a unit is admissible when at least 0.80 of claims are
  supported. Executable scorer 5.2.1 instead applies a per-claim penalty and never refuses a unit
  for faithfulness. The executable scorer wins; `faithfulness_threshold = 0.80` is a legacy value
  mapped to the fixed penalty rule.
- The track `pyproject.toml` states the executable compatibility floor
  `qfbench2-common>=2.5.0,<3`, while participant installation documentation pins `v2.5.1`.
  These are different purposes rather than conflicting contracts; participant tooling should use
  the current exact tag.
- The Development runtime document labels its House timing activation change as pending deployment
  and verification. The resource limits and request allowance are current, but the pending timing
  text must not be treated as evidence that deployment has completed.
- `raw_interval_quality` is documented as a unit diagnostic, while scorer code explicitly keeps
  diagnostics operator-only and out of the participant projection. Do not depend on receiving it
  in a participant-visible artifact.

