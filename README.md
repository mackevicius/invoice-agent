# Invoice Agent

Checks supplier Invoices against Purchase Orders and Goods Receipts.
Visitors get a private, seeded Demo Company and can upload an Invoice to watch
its fields being read in the Split view. No model calls are needed to browse
the samples. Supplier lookup and Three-Way Match are later steps; uploaded
Invoices currently finish In Review and are never Auto-Approved.

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

## Invoice Reading

Choose **Upload Invoice** to open the upload page in the right pane. Select or
drop one PDF, PNG, JPEG, WebP or GIF up to 10 MB. After upload, the new Invoice
is selected automatically. Its fields and saved agent steps refresh once a
second while it is Processing. Unreadable files finish In Review with a reason.

Compose defaults to `INVOICE_MODEL_PROVIDER=openai`. Set `OPENAI_API_KEY` in your
local environment before uploading with the real model. To use Anthropic, set
`ANTHROPIC_API_KEY` and restart with:

```sh
INVOICE_MODEL_PROVIDER=anthropic docker compose up --build
```

No code changes are needed to switch providers. `INVOICE_MODEL` optionally
overrides the default model (`gpt-4.1-mini` or `claude-haiku-4-5-20251001`).
Never commit API keys. A missing key or provider failure sends the Invoice
In Review with a reading-unavailable reason.

For free, deterministic local runs and the browser tests, use:

```sh
INVOICE_MODEL_PROVIDER=fake docker compose up --build
```

The fake returns the fixed fields in
`api/src/invoice_agent/clients/fixtures/readable.json` for every file;
it does not read the document. `INVOICE_FAKE_RESPONSE` can point to another JSON
response with the same `{"invoice": ...}` shape, or `{"invoice": null}` for an
unreadable result. The path must be accessible inside the API container.

The API stores the file and a Processing Invoice in Postgres, then queues the
Demo Company and Invoice IDs through `InvoiceQueue`. The local adapter runs a
LangGraph worker on its own thread. Files and step records are deleted with
their Demo Company. This in-process queue is for local development: restarting
the API loses queued jobs. Deployment will add SQS and S3 (ADR 0001).

## Checks and Tests

API tests use real Postgres with pgvector and a separate, disposable schema per
test. They exercise the HTTP API and the public Process an Invoice interface
with a scripted model, not internal database functions or paid providers.

```sh
docker compose run --rm api uv run --locked pytest
docker compose run --rm api uv run --locked mypy src tests conftest.py
docker compose run --rm api uv run --locked ruff check .
docker compose run --rm api uv run --locked ruff format --check .
docker compose exec web npm run typecheck
docker compose exec web npm run lint
```

To compile production assets and run the browser tests, install Node.js 24 and
start the stack with `INVOICE_MODEL_PROVIDER=fake`, then run:

```sh
cd web
npm ci
npm run build
npx playwright install chromium
PLAYWRIGHT_BASE_URL=http://localhost:3000 npm test
```

The browser tests cover Invoice selection, Demo Company persistence and expiry,
and upload through the real API and worker on desktop and mobile. CI runs Python
lint, formatting, types and tests, then web types, lint, a production build, and
the browser tests against that production build. CI uses the scripted model;
no cloud credentials or paid services are required.

## Layout

The API is organised by layer (ADR 0004):

- `api/src/invoice_agent/routes/`: HTTP endpoints (Demo Company, Invoices).
- `api/src/invoice_agent/schemas/`: Pydantic shapes of data in and out.
- `api/src/invoice_agent/services/`: Demo Company sessions, Process an Invoice
  graph, and SQL.
- `api/src/invoice_agent/clients/`: Invoice readers for AI models and the fake
  response fixture.
- `api/src/invoice_agent/workers/`: local Invoice queue and worker thread.
- `api/src/invoice_agent/db/`: Postgres schema with pgvector, and Demo Company
  sample data.
- `api/tests/`: API tests, one file per behaviour.
- `web/src/features/invoices/`: API client, Split view, and its browser test.
- `web/src/components/ui/`: generated shadcn/ui components.

The browser reaches only the HTTP API through a same-origin Next.js rewrite.
There is no database access or locally mocked Invoice data in the web app.
See `CONTEXT.md` for domain language and `docs/adr/` for architecture decisions.
