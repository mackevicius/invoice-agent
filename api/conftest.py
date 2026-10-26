import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo


@pytest.fixture
def database_url() -> Iterator[str]:
    base_url = os.environ["TEST_DATABASE_URL"]
    schema = f"test_{uuid4().hex}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(base_url, options=f"-c search_path={schema},public")
        finally:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    from invoice_agent.app import create_app
    from invoice_agent.invoice_reading.reading import ScriptedInvoiceReader

    with TestClient(
        create_app(
            database_url=database_url,
            cookie_secure=False,
            reader=ScriptedInvoiceReader(None),
        )
    ) as test_client:
        yield test_client
