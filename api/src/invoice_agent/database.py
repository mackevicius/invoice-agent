from importlib.resources import files

import psycopg


def initialize_database(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(2648002)")
        connection.execute(
            files("invoice_agent").joinpath("schema.sql").read_text(encoding="utf-8")
        )
