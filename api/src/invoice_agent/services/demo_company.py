from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from invoice_agent.db.seed import seed_demo_company
from invoice_agent.schemas.demo_company import DemoCompany


@dataclass(frozen=True)
class StartedDemoCompany:
    company: DemoCompany
    new_token: str | None  # None when an existing session was resumed


@dataclass(frozen=True)
class DemoCompanies:
    database_url: str

    def start(self, token: str | None) -> StartedDemoCompany:
        now = datetime.now(UTC)
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                "DELETE FROM demo_companies WHERE expires_at <= %s", (now,)
            )
            if token:
                existing = connection.execute(
                    """SELECT id, expires_at FROM demo_companies
                       WHERE session_hash = %s AND expires_at > %s""",
                    (sha256(token.encode()).hexdigest(), now),
                ).fetchone()
                if existing is not None:
                    return StartedDemoCompany(
                        DemoCompany(id=existing[0], expires_at=existing[1]),
                        new_token=None,
                    )

            company = DemoCompany(id=uuid4(), expires_at=now + timedelta(hours=24))
            new_token = token_urlsafe(32)
            connection.execute(
                """INSERT INTO demo_companies
                   (id, session_hash, created_at, expires_at)
                   VALUES (%s, %s, %s, %s)""",
                (
                    company.id,
                    sha256(new_token.encode()).hexdigest(),
                    now,
                    company.expires_at,
                ),
            )
            seed_demo_company(connection, company.id, now)
        return StartedDemoCompany(company, new_token)

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
