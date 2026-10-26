from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import Cookie, HTTPException, Response
from psycopg.rows import dict_row

from invoice_agent.db.seed import seed_demo_company
from invoice_agent.schemas.demo_company import DemoCompany


@dataclass(frozen=True)
class DemoCompanies:
    database_url: str
    cookie_secure: bool

    def start(
        self,
        response: Response,
        demo_company: Annotated[str | None, Cookie()] = None,
    ) -> DemoCompany:
        now = datetime.now(UTC)
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                "DELETE FROM demo_companies WHERE expires_at <= %s", (now,)
            )
            if demo_company:
                existing = connection.execute(
                    """SELECT id, expires_at FROM demo_companies
                       WHERE session_hash = %s AND expires_at > %s""",
                    (sha256(demo_company.encode()).hexdigest(), now),
                ).fetchone()
                if existing is not None:
                    return DemoCompany(id=existing[0], expires_at=existing[1])

            company = DemoCompany(id=uuid4(), expires_at=now + timedelta(hours=24))
            token = token_urlsafe(32)
            connection.execute(
                """INSERT INTO demo_companies
                   (id, session_hash, created_at, expires_at)
                   VALUES (%s, %s, %s, %s)""",
                (
                    company.id,
                    sha256(token.encode()).hexdigest(),
                    now,
                    company.expires_at,
                ),
            )
            seed_demo_company(connection, company.id, now)
        response.set_cookie(
            "demo_company",
            token,
            max_age=86400,
            expires=company.expires_at,
            httponly=True,
            secure=self.cookie_secure,
            samesite="lax",
        )
        return company

    def identify(self, demo_company: Annotated[str | None, Cookie()] = None) -> UUID:
        if demo_company is None:
            raise HTTPException(status_code=401, detail="Start a Demo Company first.")
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            company = connection.execute(
                """SELECT id FROM demo_companies
                   WHERE session_hash = %s AND expires_at > %s""",
                (sha256(demo_company.encode()).hexdigest(), datetime.now(UTC)),
            ).fetchone()
        if company is None:
            raise HTTPException(status_code=401, detail="Start a Demo Company first.")
        return UUID(str(company["id"]))
