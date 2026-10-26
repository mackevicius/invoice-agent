from fastapi import APIRouter

from invoice_agent.services.demo_companies import DemoCompanies


def create_demo_company_router(companies: DemoCompanies) -> APIRouter:
    router = APIRouter(prefix="/api/demo-company", tags=["Demo Company"])
    router.add_api_route("", companies.start, methods=["POST"])
    return router
