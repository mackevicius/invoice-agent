import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from functools import cache
from typing import Any

import psycopg
from fastapi import FastAPI, Request, Response
from mangum import Mangum
from starlette.middleware.base import RequestResponseEndpoint

from invoice_agent.clients.embeddings import TextEmbeddings
from invoice_agent.clients.invoice_files import InvoiceFileStore, S3InvoiceFiles
from invoice_agent.clients.invoice_reader import InvoiceReader
from invoice_agent.clients.line_pairing import LinePairer
from invoice_agent.clients.parameters import read_parameters
from invoice_agent.clients.reader_settings import (
    configured_embeddings,
    configured_line_pairer,
    configured_reader,
)
from invoice_agent.clients.tracing import RunTracing, configured_tracing
from invoice_agent.db.initialize import initialize_database
from invoice_agent.routes.demo_company import create_demo_company_router
from invoice_agent.routes.invoices import create_invoice_router
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.demo_company import DemoCompanies
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoice_processing import InvoiceProcessing
from invoice_agent.workers.demo_company import InProcessDemoCompanyCleanup
from invoice_agent.workers.invoice_queue import (
    InProcessInvoiceQueue,
    InvoiceQueue,
    SqsInvoiceQueue,
    process_sqs_messages,
)

LambdaHandler = Callable[[dict[str, Any], Any], None]


def create_app(
    database_url: str | None = None,
    cookie_secure: bool | None = None,
    *,
    reader: InvoiceReader | None = None,
    embeddings: TextEmbeddings | None = None,
    line_pairer: LinePairer | None = None,
    invoice_queue: InvoiceQueue | None = None,
    invoice_files: InvoiceFileStore | None = None,
    tracing: RunTracing | None = None,
) -> FastAPI:
    url = database_url or os.environ["DATABASE_URL"]
    secure = (
        cookie_secure
        if cookie_secure is not None
        else os.environ.get("COOKIE_SECURE", "true").lower() != "false"
    )
    embedding_model = embeddings or configured_embeddings()
    run_tracing = tracing or configured_tracing()
    processing = _create_processing(
        url,
        reader=reader,
        embeddings=embedding_model,
        line_pairer=line_pairer,
        invoice_files=invoice_files,
        tracing=run_tracing,
    )
    queue_url = os.environ.get("INVOICE_QUEUE_URL")
    queue = invoice_queue or (
        SqsInvoiceQueue(queue_url)
        if queue_url
        else InProcessInvoiceQueue(processing.process)
    )
    companies = DemoCompanies(database_url=url, embeddings=embedding_model)
    cleanup = InProcessDemoCompanyCleanup(companies)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        initialize_database(url)
        cleanup.start()
        try:
            processing.erp_tools.index_purchase_order_lines()
            if isinstance(queue, InProcessInvoiceQueue):
                queue.start()
            try:
                yield
            finally:
                if isinstance(queue, InProcessInvoiceQueue):
                    queue.close()
        finally:
            cleanup.close()
            run_tracing.close()

    app = FastAPI(title="Invoice Agent", lifespan=lifespan)

    @app.middleware("http")
    async def prevent_private_caching(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        with psycopg.connect(url) as connection:
            connection.execute("SELECT 1")
        return {"status": "ok"}

    app.include_router(create_demo_company_router(companies, cookie_secure=secure))
    app.include_router(create_invoice_router(companies, processing, queue))
    return app


def cleanup_expired_demo_companies() -> None:
    removed = DemoCompanies(os.environ["DATABASE_URL"]).cleanup_expired()
    print(f"Removed {removed} expired Demo Companies.")


def create_invoice_worker() -> LambdaHandler:
    tracing = configured_tracing()
    processing = _create_processing(
        os.environ["DATABASE_URL"], embeddings=configured_embeddings(), tracing=tracing
    )

    def handle(event: dict[str, Any], context: Any) -> None:
        try:
            process_sqs_messages(processing.process, event)
        finally:
            # Lambda freezes after returning, so traces must be sent first.
            tracing.flush()

    return handle


def load_cloud_parameters() -> None:
    path = os.environ.get("INVOICE_PARAMETER_PATH")
    if path:
        os.environ.update(read_parameters(path))


def handle_api_request(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return _cloud_api()(event, context)


def handle_invoice_messages(event: dict[str, Any], context: Any) -> None:
    _cloud_worker()(event, context)


def handle_cleanup(event: dict[str, Any], context: Any) -> None:
    load_cloud_parameters()
    cleanup_expired_demo_companies()


def handle_migration(event: dict[str, Any], context: Any) -> None:
    load_cloud_parameters()
    url = os.environ["DATABASE_URL"]
    initialize_database(url)
    ERPTools(url, configured_embeddings()).index_purchase_order_lines()


@cache
def _cloud_api() -> Mangum:
    load_cloud_parameters()
    return Mangum(create_app(), lifespan="off")


@cache
def _cloud_worker() -> LambdaHandler:
    load_cloud_parameters()
    return create_invoice_worker()


def _create_processing(
    url: str,
    *,
    embeddings: TextEmbeddings,
    tracing: RunTracing,
    reader: InvoiceReader | None = None,
    line_pairer: LinePairer | None = None,
    invoice_files: InvoiceFileStore | None = None,
) -> InvoiceProcessing:
    bucket = os.environ.get("INVOICE_FILES_BUCKET")
    return InvoiceProcessing(
        url,
        reader=reader or configured_reader(),
        erp_tools=ERPTools(url, embeddings),
        daily_ai_limit=DailyAILimit(url),
        line_pairer=line_pairer or configured_line_pairer(),
        tracing=tracing,
        invoice_files=invoice_files or (S3InvoiceFiles(bucket) if bucket else None),
    )
