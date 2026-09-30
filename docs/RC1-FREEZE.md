## Executive summary (read this first)

RC1 is the immutable fallback for the Track 4 agent. The tag `agenthon-t4-rc1` points to the
algorithm source commit, while the later CI commit only supplied validation and publication
machinery; the submitted runtime files are byte-identical between those points. The published
image is identified only by its immutable digest, and the locally packed ZIP is identified by its
SHA-256. RC1 must not be rebuilt, repacked, or overwritten during RC2 research. It has not been
uploaded to CodaBench and has consumed no Development attempt.

# RC1 freeze record

| Item | Frozen value |
|---|---|
| Algorithm source commit | `0c288e4b775c84ac354c3765cb00974314efc48e` |
| Algorithm source branch | `nightly/t4-agent` |
| Immutable tag | `agenthon-t4-rc1` (local and fork remote; peels to the algorithm source commit above) |
| Publication workflow commit | `4eb8376b1e702d16d9b3820ff2eba19a7fbc95c1` on `ci/docker-validation` |
| GHCR repository | `ghcr.io/jiawei-vita-li/agenthon-track4-agent` |
| Immutable image digest | `sha256:8576cc63daf789cca64fcf60e5f114c5cb516756ad37fae322cd117eea8f644a` |
| Full image reference | `ghcr.io/jiawei-vita-li/agenthon-track4-agent@sha256:8576cc63daf789cca64fcf60e5f114c5cb516756ad37fae322cd117eea8f644a` |
| Descriptor digest | `sha256:eadb55e411d052101fa3c9524f553d7d1413713b47c2642ee1e4aa5eeb97eb95` |
| Derived team ID | `team-a5feec08147ef9378eebcdbd1b1ad1c2` |
| `submission.zip` SHA-256 | `1b0b95cca7e2348381b67792ae2cb5c521936c9856f13f7adc24ae4b560f0023` |
| Exact local ZIP path | `C:\Users\17237\.agenthon\track4-submission\submission.zip` |
| Official packer | `qfbench2-common 2.4.4`, Python 3.13 |
| Image platform | `linux/amd64` |
| Image size | `118,317,522` bytes (approximately `112.84 MiB`) |
| Upload status | `PACKAGE READY — NOT UPLOADED` |

## Validation provenance

- Real linux/amd64 Docker build/run: GitHub Actions run
  [36560450052](https://github.com/jiawei-vita-li/track4-analysis-public/actions/runs/36560450052),
  job `docker-validation`, PASS.
- Platform-like non-root/read-only sandbox: the independent step `Validate platform-like
  non-root read-only sandbox` in the same run
  [36560450052](https://github.com/jiawei-vita-li/track4-analysis-public/actions/runs/36560450052),
  PASS. The hosted runner could not physically provide the official 16 CPU / 128 GiB ceiling, so
  the workflow retained every other sandbox restriction and recorded the resource-only fallback.
- Image publication: GitHub Actions run
  [36599294406](https://github.com/jiawei-vita-li/track4-analysis-public/actions/runs/36599294406),
  PASS.
- Anonymous pull by immutable digest: a fresh runner with an empty Docker configuration in run
  [36599474262](https://github.com/jiawei-vita-li/track4-analysis-public/actions/runs/36599474262),
  PASS; inspection returned `linux`, `amd64`, and interface version `2.0`.
- The runtime diff between the publication branch and `nightly/t4-agent` was empty for
  `baselines/strong_rag_baseline/Dockerfile` and its Python runtime files before publication.

## Immutability boundary

RC2 may read this record and compare against RC1, but it must not mutate the tag, image digest,
descriptor, ZIP, or the files at the frozen algorithm commit. New experiments belong only on
`research/predictive-v2`. This record contains no Team Key, model bearer token, GitHub token,
registry credential, or other secret.
