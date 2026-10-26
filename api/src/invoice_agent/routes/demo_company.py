from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException, Response

from invoice_agent.schemas.demo_company import DemoCompany
from invoice_agent.services.demo_company import DemoCompanies


def create_demo_company_router(
    companies: DemoCompanies, cookie_secure: bool
) -> APIRouter:
    router = APIRouter(prefix="/api/demo-company", tags=["Demo Company"])

    @router.post("")
    def start_demo_company(
        response: Response,
        demo_company: Annotated[str | None, Cookie()] = None,
    ) -> DemoCompany:
        started = companies.start(demo_company)
        if started.new_token is not None:
            response.set_cookie(
                "demo_company",
                started.new_token,
                max_age=86400,
                expires=started.company.expires_at,
                httponly=True,
                secure=cookie_secure,
                samesite="lax",
            )
        return started.company

    return router


def require_demo_company(
    companies: DemoCompanies,
) -> Callable[[str | None], UUID]:
    """Build a FastAPI dependency that turns the session cookie into a company ID."""

    def current_company_id(
        demo_company: Annotated[str | None, Cookie()] = None,
    ) -> UUID:
        company_id = companies.identify(demo_company)
        if company_id is None:
            raise HTTPException(status_code=401, detail="Start a Demo Company first.")
        return company_id

    return current_company_id
