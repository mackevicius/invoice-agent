FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY tests ./tests
COPY conftest.py ./
RUN uv sync --locked
RUN uv run --locked python -c "from invoice_agent.clients.embeddings import LocalEmbeddings; LocalEmbeddings().embed(['Purchase Order'])"

CMD ["uv", "run", "--locked", "uvicorn", "invoice_agent.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload"]
