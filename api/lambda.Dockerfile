# Image for the AWS Lambda functions in infra/template.yaml.
FROM public.ecr.aws/lambda/python:3.12

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
ENV UV_NO_CACHE=1 FASTEMBED_CACHE_PATH=/opt/fastembed

COPY pyproject.toml uv.lock ./
RUN uv export --locked --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt \
    && uv pip install --compile-bytecode -r /tmp/requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY src/invoice_agent "${LAMBDA_TASK_ROOT}/invoice_agent"
RUN python3 -c "from invoice_agent.clients.embeddings import LocalEmbeddings; LocalEmbeddings().embed(['Purchase Order'])"

# Lambda's disk is read-only, so the embedding model must load from the image.
ENV HF_HUB_OFFLINE=1

CMD ["invoice_agent.app.handle_api_request"]
