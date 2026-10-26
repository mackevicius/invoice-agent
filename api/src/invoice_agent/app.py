import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from invoice_agent.database import initialize_database
from invoice_agent.demo_company.api import DemoCompanies
from invoice_agent.invoices.api import create_invoice_router


def create_app(
    database_url: str | None = None, cookie_secure: bool | None = None
) -> FastAPI:
    url = database_url or os.environ["DATABASE_URL"]
    secure = (
        cookie_secure
        if cookie_secure is not None
        else os.environ.get("COOKIE_SECURE", "true").lower() != "false"
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        initialize_database(url)
        yield

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

    companies = DemoCompanies(database_url=url, cookie_secure=secure)
    app.add_api_route(
        "/api/demo-company", companies.start, methods=["POST"], tags=["Demo Company"]
    )
    app.include_router(create_invoice_router(url, companies))
    return app
