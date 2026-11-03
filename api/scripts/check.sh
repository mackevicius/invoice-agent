#!/bin/sh
# Every API check CI runs. Needs TEST_DATABASE_URL (set by Compose and CI).
set -eu
cd "$(dirname "$0")/.."

uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src evals tests conftest.py
uv run --locked pytest
uv run --locked python -m evals.reading --check
uv run --locked python -m evals.reading --sample-dir evals/data/generated-v1 --check
