from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from invoice_agent.clients.embeddings import TextEmbeddings
from invoice_agent.db.seed import SAMPLES, seed_demo_company
from invoice_agent.schemas.demo_company import (
    AutoApprovalLimit,
    DemoCompany,
    DemoPerson,
)


class DemoCompanyPermissionDenied(PermissionError):
    pass


@dataclass(frozen=True)
class StartedDemoCompany:
    company: DemoCompany
    new_token: str | None  # None when an existing session was resumed
    visitor_id: UUID


@dataclass(frozen=True)
class DemoCompanies:
    database_url: str
    embeddings: TextEmbeddings | None = None

    def start(
        self, token: str | None, visitor_id: UUID | None = None
    ) -> StartedDemoCompany:
        now = datetime.now(UTC)
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                "DELETE FROM demo_companies WHERE expires_at <= %s", (now,)
            )
            if token:
                existing = connection.execute(
                    """SELECT id, expires_at, visitor_id FROM demo_companies
                       WHERE session_hash = %s AND expires_at > %s""",
                    (sha256(token.encode()).hexdigest(), now),
                ).fetchone()
                if existing is not None:
                    return StartedDemoCompany(
                        DemoCompany(id=existing[0], expires_at=existing[1]),
                        new_token=None,
                        visitor_id=existing[2],
                    )

            company = DemoCompany(id=uuid4(), expires_at=now + timedelta(hours=24))
            new_token = token_urlsafe(32)
            visitor_id = visitor_id or uuid4()
            connection.execute(
                """INSERT INTO demo_companies
                   (id, visitor_id, session_hash, created_at, expires_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    company.id,
                    visitor_id,
                    sha256(new_token.encode()).hexdigest(),
                    now,
                    company.expires_at,
                ),
            )
            vectors = (
                self.embeddings.embed([sample[4] for sample in SAMPLES])
                if self.embeddings is not None
                else None
            )
            seed_demo_company(
                connection,
                company.id,
                now,
                vectors,
                self.embeddings.model_name if self.embeddings is not None else None,
            )
        return StartedDemoCompany(company, new_token, visitor_id)

    def get_auto_approval_limit(self, company_id: UUID) -> AutoApprovalLimit | None:
        with psycopg.connect(self.database_url) as connection:
            company = connection.execute(
                """SELECT auto_approval_limit, currency FROM demo_companies
                   WHERE id = %s AND expires_at > %s""",
                (company_id, datetime.now(UTC)),
            ).fetchone()
        return (
            None
            if company is None
            else AutoApprovalLimit(amount=company[0], currency=company[1])
        )

    def set_auto_approval_limit(
        self, person: DemoPerson, limit: AutoApprovalLimit
    ) -> AutoApprovalLimit | None:
        if person.role != "Admin":
            raise DemoCompanyPermissionDenied(
                "Only an Admin can change the Auto-Approval Limit."
            )
        with psycopg.connect(self.database_url) as connection:
            company = connection.execute(
                """UPDATE demo_companies SET auto_approval_limit = %s
                   WHERE id = %s AND expires_at > %s
                   RETURNING auto_approval_limit, currency""",
                (limit.amount, person.company_id, datetime.now(UTC)),
            ).fetchone()
        return (
            None
            if company is None
            else AutoApprovalLimit(amount=company[0], currency=company[1])
        )

    def identify(self, token: str | None) -> UUID | None:
        if token is None:
            return None
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            company = connection.execute(
                """SELECT id FROM demo_companies
                   WHERE session_hash = %s AND expires_at > %s""",
                (sha256(token.encode()).hexdigest(), datetime.now(UTC)),
            ).fetchone()
        return None if company is None else UUID(str(company["id"]))
