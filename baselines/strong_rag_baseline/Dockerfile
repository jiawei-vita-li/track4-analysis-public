# Competition candidate: stdlib BM25 + task-level House predictor.
# linux/amd64 manifest for python:3.13.15-slim-trixie, resolved 2026-09-29.
FROM python:3.13-slim@sha256:37134a49d21d2120e4c4d73bb76f8a4ab9aef31f096f7ec2ead48c2feead4332

LABEL qfbench2.interface_version="2.0"
LABEL org.opencontainers.image.title="Agenthon Track 4 task-level predictor"

ENV PYTHONHASHSEED=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY baselines/strong_rag_baseline/*.py /app/baselines/strong_rag_baseline/

# The harness appends the required `analyze` verb and mounted input/output paths.
ENTRYPOINT ["python", "-m", "baselines.strong_rag_baseline.cli"]
CMD ["analyze", "--help"]
