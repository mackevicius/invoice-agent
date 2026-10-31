from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response

from invoice_agent.schemas.demo_company import (
    AutoApprovalLimit,
    DemoCompany,
    DemoPerson,
    DemoRole,
)
from invoice_agent.services.demo_company import (
    DemoCompanies,
    DemoCompanyPermissionDenied,
)


def create_demo_company_router(
    companies: DemoCompanies, cookie_secure: bool
) -> APIRouter:
    router = APIRouter(prefix="/api/demo-company", tags=["Demo Company"])
    current_person = require_demo_person(companies)

    @router.post("")
    def start_demo_company(
        response: Response,
        demo_company: Annotated[str | None, Cookie()] = None,
        visitor_id: Annotated[str | None, Cookie()] = None,
    ) -> DemoCompany:
        try:
            visitor = UUID(visitor_id) if visitor_id else None
        except ValueError:
            visitor = None
        started = companies.start(demo_company, visitor)
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
        response.set_cookie(
            "visitor_id",
            str(started.visitor_id),
            max_age=172800,
            httponly=True,
            secure=cookie_secure,
            samesite="lax",
        )
        return started.company

    @router.get("/auto-approval-limit")
    def get_auto_approval_limit(
        person: Annotated[DemoPerson, Depends(current_person)],
    ) -> AutoApprovalLimit:
        limit = companies.get_auto_approval_limit(person.company_id)
        if limit is None:
            raise HTTPException(status_code=401, detail="Start a Demo Company first.")
        return limit

    @router.put("/auto-approval-limit")
    def set_auto_approval_limit(
        limit: AutoApprovalLimit,
        person: Annotated[DemoPerson, Depends(current_person)],
    ) -> AutoApprovalLimit:
        try:
            saved = companies.set_auto_approval_limit(person, limit)
        except DemoCompanyPermissionDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        if saved is None:
            raise HTTPException(status_code=401, detail="Start a Demo Company first.")
        return saved

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


def require_demo_person(
    companies: DemoCompanies,
) -> Callable[[UUID, DemoRole], DemoPerson]:
    current_company_id = require_demo_company(companies)

    def current_person(
        company_id: Annotated[UUID, Depends(current_company_id)],
        role: Annotated[DemoRole, Header(alias="X-Demo-Role")] = "Submitter",
    ) -> DemoPerson:
        return DemoPerson(company_id=company_id, id=role.lower(), role=role)

    return current_person
