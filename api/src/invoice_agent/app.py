import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from invoice_agent.clients.invoice_reader import InvoiceReader
from invoice_agent.clients.reader_settings import configured_reader
from invoice_agent.db.initialize import initialize_database
from invoice_agent.routes.demo_company import create_demo_company_router
from invoice_agent.routes.invoices import create_invoice_router
from invoice_agent.services.demo_company import DemoCompanies
from invoice_agent.services.invoices import InvoiceProcessing
from invoice_agent.workers.invoice_queue import InProcessInvoiceQueue, InvoiceQueue


def create_app(
    database_url: str | None = None,
    cookie_secure: bool | None = None,
    *,
    reader: InvoiceReader | None = None,
    invoice_queue: InvoiceQueue | None = None,
) -> FastAPI:
    url = database_url or os.environ["DATABASE_URL"]
    secure = (
        cookie_secure
        if cookie_secure is not None
        else os.environ.get("COOKIE_SECURE", "true").lower() != "false"
    )
    processing = InvoiceProcessing(url, reader=reader or configured_reader())
    queue = invoice_queue or InProcessInvoiceQueue(processing.process)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        initialize_database(url)
        if isinstance(queue, InProcessInvoiceQueue):
            queue.start()
        try:
            yield
        finally:
            if isinstance(queue, InProcessInvoiceQueue):
                queue.close()

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

    companies = DemoCompanies(database_url=url)
    app.include_router(create_demo_company_router(companies, cookie_secure=secure))
    app.include_router(create_invoice_router(companies, processing, queue))
    return app
