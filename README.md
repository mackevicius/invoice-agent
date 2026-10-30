# Invoice Agent

Checks supplier Invoices against Purchase Orders and Goods Receipts.
Visitors get a private, seeded Demo Company and can upload an Invoice to watch
its fields being read, its Supplier looked up, and its Three-Way Match in the
Split view. No model calls are needed to browse the samples. Uploaded Invoices
finish In Review with every failed check listed, or **All checks passed** until
Auto-Approval is implemented. Known Suppliers are checked for Duplicate Invoices
and Possible Duplicates.

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

## Roles and Review Queue

**Viewing as** selects Submitter, Reviewer, or Admin. Each role is one fixed
demo person within the Demo Company, not a login. Everyone can upload, and the
server records who uploaded each Invoice. Submitters start on **Mine**,
Reviewers on **Review Queue**, and Admins on **All**. The four tabs show counts;
**Done** contains Auto-Approved, Approved, and Rejected Invoices.

Only a Reviewer can approve or reject an In Review Invoice, and never one they
uploaded. Their own uploads show a lock notice instead of decision buttons.
Processing must finish before a decision, and final decisions cannot be changed.
Reject requires a non-blank Rejection Reason, which Submitters can read on the
rejected Invoice. The agent's review reasons are kept separately.

Every Invoice request resolves the Company and person through one server
dependency (ADR 0003). `X-Demo-Role` accepts `Submitter`, `Reviewer`, or `Admin`;
omitting it selects Submitter. The Demo Company cookie is still required.

- `GET /api/invoices?view=all|mine|review-queue|done` returns filtered headers.
- `GET /api/invoices/counts` returns `all`, `mine`, `review_queue`, and `done`
  counts across the Company, with Mine scoped to the current person.
- `GET /api/invoices/{id}` includes `submitted_by`, `can_decide`,
  `decision_block_reason`, `rejection_reason`, and `received_at`.
- `POST /api/invoices/{id}/approve` approves; `POST /api/invoices/{id}/reject`
  rejects with `{"rejection_reason": "The goods did not arrive."}`. Reasons
  are trimmed and limited to 2,000 characters. Permissions, Company isolation,
  and status transitions are enforced by the API, not just the controls.

## Daily AI Limits

Live Invoice reads default to **5 per visitor** and **100 across all visitors**
per UTC calendar day. Override the limits with non-negative integers when
starting the API:

```sh
INVOICE_AI_DAILY_VISITOR_LIMIT=3 INVOICE_AI_DAILY_GLOBAL_LIMIT=50 docker compose up --build
```

At either limit, no model is called. The Invoice finishes In Review with the
reason **daily AI limit reached**, and later steps are Skipped. Setting either
limit to `0` disables live reads. Scripted reads and seeded sample Invoices do
not consume the allowance and remain available after the limit is reached.

A separate HttpOnly visitor cookie preserves the allowance across Demo Company
renewals. It lasts two days and does not grant access to Invoice data; the Demo
Company session cookie still expires after 24 hours. Clearing cookies creates a
new anonymous visitor, but does not reset the global allowance.

Usage is reserved in Postgres before the live call, including attempts that fail
or return an unreadable result. Reservations are atomic across workers and
survive API restarts. Provider SDK retries are disabled, so one reservation sends
at most one request. Counts start again at midnight UTC without a scheduled reset.
Previous usage stays stored even when a Demo Company expires, so deleting a
company's records cannot restore the global allowance.

## ERP Tools

After reading, the processing graph calls `ERPTools.find_supplier`, which looks
up the Supplier in the Demo Company's ERP tables. Every ERP read goes through
`ERPTools`, so a real ERP can replace it without changing the graph (ADR 0002).

Lookup ignores case, punctuation and spacing. A unique match records the
Supplier's ID and canonical name in the Find Supplier step. No match or an
ambiguous name sends the Invoice In Review with the reason **Unknown Supplier**.
An unavailable tool records a failed lookup and a separate review reason.
In both cases, later steps are marked Skipped.

For a known Supplier, `ERPTools.get_purchase_order` fetches the Purchase Order
number printed on the Invoice, scoped to that Supplier and Demo Company.
`ERPTools.get_goods_receipt` fetches its Goods Receipts and totals received
quantities per Purchase Order line. A missing Purchase Order or unavailable
Purchase Order lookup sends the Invoice In Review and skips dependent steps.
When a Goods Receipt is missing or unavailable, available Purchase Order checks
still run so their failures are listed alongside the missing-receipt reason.

## Three-Way Match

Invoice reading captures the printed Purchase Order number and optional item
codes. Deterministic code pairs lines by a unique identical item code or an
identical description. Conflicting codes, ambiguous matches and unpaired lines
require review; a Purchase Order line cannot be reused by another Invoice line.

- A unit price up to 2% above the Purchase Order passes; a lower price passes
  too. The grid retains the signed amount and percentage difference.
- Invoiced quantity must equal received quantity, and received quantity must
  not exceed ordered quantity. Partial deliveries pass.
- Each line has one Invoice / Purchase Order / Goods Receipt comparison table.
  Mismatched cells are red, and every review reason appears below the tables.

The model only reads the Invoice; it does not compute pass/fail or decide the
Invoice Status. Successful checks still finish In Review with **All checks
passed**. Duplicate checks run even when matching fails or the Purchase Order
is missing.

The default fake Invoice names Baltic Office Supplies, which is not seeded,
so it demonstrates the unknown-Supplier path. An alternate fake response can
exercise a passing Three-Way Match with Supplier **Paper & Co.**, Purchase Order
**PO-1002**, and description **Recycled A4 paper, box**, quantity **24**, unit
price **111.60**. Use `purchase_order_number` on the Invoice and optional
`item_code` on each line in the JSON response.

## Duplicate Invoices

`ERPTools.find_earlier_invoices` reads earlier Invoices for the same Supplier
and Demo Company, excluding the current Invoice and later uploads.

- The same Invoice number is a **Duplicate Invoice**, regardless of age or total.
- A different Invoice number with the same total, received within 30 days,
  is a **Possible Duplicate**. Exactly 30 days is included; the window uses
  when the Invoice was received, not its printed date.

Both finish In Review. Every earlier Invoice is named in a reason that opens
its record in the detail pane; the link also works in a new tab. Matching and
duplicate reasons appear together. An unavailable history lookup fails the
Check Duplicates step and sends the Invoice to review with a clear reason.

## Checks and Tests

API tests use real Postgres with pgvector and a separate, disposable schema per
test. They exercise the HTTP API and the public Process an Invoice interface
with a scripted model, not internal database functions or paid providers.
Supplier tests use the real ERP tables, including name variations,
unknown Suppliers, ERP failures and isolation between Demo Companies.
Three-Way Match tests use the same public interface, with separate files for
Price Tolerance, quantities, missing records and simple line pairing.
Duplicate Invoice tests cover both rules, the 30-day boundary, combined failure
reasons, history failures, saved record links, and Company/Supplier isolation.
Daily AI limit tests cover both caps, concurrent workers, Demo Company renewal,
midnight UTC reset, zero limits, and scripted reads. The live SDK retry checks
use a local HTTP endpoint; no paid provider is contacted.
Role and Review Queue tests exercise permissions, uploader tracking, final
decisions, required Rejection Reasons, view filters, and counts through the
HTTP API.

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
upload through the real API and worker, switching from Submitter to Reviewer
and approving from the Review Queue, links to earlier Invoices, and the comparison grid's mismatch
colors, lower-price differences and mobile layout. The grid rendering check
uses a fixed HTTP response; processing rules are tested against real Postgres.
CI runs Python
lint, formatting, types and tests, then web types, lint, a production build, and
the browser tests against that production build. CI uses the scripted model;
no cloud credentials or paid services are required.

## Layout

The API is organised by layer (ADR 0004). A feature keeps the same file name in
each layer, for example `routes/invoices.py`, `schemas/invoices.py` and
`services/invoices.py`.

- `api/src/invoice_agent/routes/`: HTTP endpoints, cookies and status codes.
- `api/src/invoice_agent/schemas/`: shapes of data in and out.
- `api/src/invoice_agent/services/`: business rules and SQL: Demo Company
  sessions, the Process an Invoice graph, Invoice lookups and ERP Tools.
- `api/src/invoice_agent/clients/`: Invoice readers for AI models, the fake
  reader and its response fixture.
- `api/src/invoice_agent/workers/`: local Invoice queue and worker thread.
- `api/src/invoice_agent/db/`: Postgres schema with pgvector, its startup
  script, and Demo Company sample data.
- `api/tests/`: API tests, one file per behaviour.
- `web/src/features/invoices/`: API client, Split view, and its browser test.
- `web/src/components/ui/`: generated shadcn/ui components.

The browser reaches only the HTTP API through a same-origin Next.js rewrite.
There is no database access or locally mocked Invoice data in the web app.
See `CONTEXT.md` for domain language and `docs/adr/` for architecture decisions.
