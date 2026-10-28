import os
from datetime import UTC, datetime
from uuid import UUID

import psycopg


class DailyAILimit:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.visitor_limit = int(os.environ.get("INVOICE_AI_DAILY_VISITOR_LIMIT", "5"))
        self.global_limit = int(os.environ.get("INVOICE_AI_DAILY_GLOBAL_LIMIT", "100"))
        if self.visitor_limit < 0:
            raise ValueError("INVOICE_AI_DAILY_VISITOR_LIMIT must not be negative.")
        if self.global_limit < 0:
            raise ValueError("INVOICE_AI_DAILY_GLOBAL_LIMIT must not be negative.")

    def reserve(self, company_id: UUID) -> bool:
        if self.visitor_limit == 0 or self.global_limit == 0:
            return False
        usage_date = datetime.now(UTC).date()
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """SELECT pg_advisory_xact_lock(
                       hashtext(current_schema() || '.daily_ai_usage'), %s)""",
                (usage_date.toordinal(),),
            )
            usage = connection.execute(
                """SELECT COALESCE(SUM(calls), 0) FROM daily_ai_usage
                   WHERE usage_date = %s""",
                (usage_date,),
            ).fetchone()
            if usage is None or usage[0] >= self.global_limit:
                return False
            reserved = connection.execute(
                """INSERT INTO daily_ai_usage (usage_date, visitor_id, calls)
                   SELECT %s, visitor_id, 1 FROM demo_companies WHERE id = %s
                   ON CONFLICT (usage_date, visitor_id) DO UPDATE
                   SET calls = daily_ai_usage.calls + 1
                   WHERE daily_ai_usage.calls < %s
                   RETURNING calls""",
                (usage_date, company_id, self.visitor_limit),
            ).fetchone()
        return reserved is not None
