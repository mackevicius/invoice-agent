# Invoice Agent

Checks supplier Invoices against Purchase Orders and Goods Receipts.
This walking skeleton provides a private, seeded Demo Company and its Invoice list
and header in the Split view. No model calls are needed to browse the samples.

## Run Locally

Install and start Docker Desktop, then run from the repository root:

```sh
docker compose up --build
```

Open http://localhost:3000. This starts Postgres 17 with pgvector, the FastAPI
HTTP API, and Next.js with shadcn/ui. Source changes reload automatically.
The API documentation is at http://localhost:8000/docs.

On first visit, the API creates a Demo Company with Suppliers, Purchase Orders,
Goods Receipts, and five sample Invoices. An opaque HttpOnly cookie resumes the
same Demo Company for 24 hours. Expired sessions cannot read data; expired
companies and their records are removed when the next session starts.
Closing the browser does not reset the Demo Company.

```sh
docker compose down
```

Data stays in the Postgres volume. To explicitly remove local demo data as well,
run `docker compose down --volumes`.

If a default port is occupied, override it when starting the stack:

```sh
WEB_PORT=3001 API_PORT=8001 POSTGRES_PORT=55433 docker compose up --build
```

These are development-only database credentials and HTTP cookies. The API uses
Secure cookies by default outside Compose; a hosted deployment requires HTTPS.

## Checks and Tests

API tests use real Postgres with pgvector and a separate, disposable schema per
test. They exercise the HTTP API, not internal database functions.

```sh
docker compose run --rm api uv run --locked pytest
docker compose run --rm api uv run --locked mypy src conftest.py
docker compose run --rm api uv run --locked ruff check .
docker compose run --rm api uv run --locked ruff format --check .
docker compose exec web npm run typecheck
docker compose exec web npm run lint
```

To compile production assets and run the smoke test against the local
development server, install Node.js 24, then with the stack running:

```sh
cd web
npm ci
npm run build
npx playwright install chromium
PLAYWRIGHT_BASE_URL=http://localhost:3000 npm test
```

The test covers real Invoice selection and Demo Company persistence on desktop
and mobile. CI runs Python lint, formatting, types and HTTP tests, then web
types, lint, a production build, and the browser test against that production
build on every push and pull request. No cloud credentials or paid services are
required.

## Layout

- `api/src/invoice_agent/demo_company/`: session startup, expiry, seeding, and tests.
- `api/src/invoice_agent/invoices/`: company-scoped Invoice HTTP endpoints and tests.
- `api/src/invoice_agent/schema.sql`: Postgres schema and pgvector extension.
- `web/src/features/invoices/`: API client, Split view, and its browser test.
- `web/src/components/ui/`: generated shadcn/ui components.

The browser reaches only the HTTP API through a same-origin Next.js rewrite.
There is no database access or locally mocked Invoice data in the web app.
See `CONTEXT.md` for domain language and `docs/adr/` for architecture decisions.
