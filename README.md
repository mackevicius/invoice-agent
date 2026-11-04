# Invoice Agent

Checks supplier Invoices against Purchase Orders and Goods Receipts.
Visitors get a private, seeded Demo Company and can upload an Invoice to watch
its fields being read, its Supplier looked up, and its Three-Way Match in the
Split view. No model calls are needed to browse the samples. Uploaded Invoices
are Auto-Approved only when every rule passes and the total is under the
Auto-Approval Limit. Otherwise they finish In Review with every failed check
listed. Known Suppliers are checked for Duplicate Invoices and Possible Duplicates.

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
same Demo Company for 24 hours. Expired sessions cannot read, decide, or download
Invoices; the next visit starts a fresh Demo Company. The local API removes expired
companies, their records, and uploaded files at startup and every minute, even
when no visitors return.
Closing the browser does not reset the Demo Company.

To run cleanup once, without starting the API server:

```sh
docker compose run --rm api uv run --locked invoice-agent-cleanup
```

An external scheduler can run the same command with `DATABASE_URL` set.
For Lambda deployment, use an external schedule rather than the local API's
background thread.

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
local environment, or copy `.env.example` to `.env` and fill it in, before
uploading with the real model. To use Anthropic, set
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

## Langfuse Tracing

Tracing is optional. Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in your
local environment, then restart the API with `docker compose up --build`.
Never commit these keys or expose the secret key to the browser.
`LANGFUSE_BASE_URL` defaults to `https://cloud.langfuse.com`; override it for
another region or a self-hosted Langfuse v4 server (v4.59.0 or newer).

Each agent run creates one trace containing every graph step, ERP tool call,
Invoice-reading model call, and semantic line-choice model call. Model names,
input/output token usage, and elapsed time are recorded by the Langfuse
LangChain integration. Langfuse calculates USD cost from its model definitions;
custom models need a matching price definition in Langfuse.

The trace URL is saved on the Invoice and shown as **Langfuse trace** in its
header, opening in a new tab. Failed reads keep a trace, including the final
In Review outcome and Skipped steps. Concurrent runs have separate traces.
Seeded sample Invoices have no agent run and no trace link.

With either key missing, or `LANGFUSE_TRACING_ENABLED=false`, new runs continue
normally without a trace link. A Langfuse project-lookup failure also leaves the
link empty without preventing an Invoice decision. Events export in the
background and flush after the worker stops at application shutdown.

Langfuse retains trace data independently of the Demo Company's 24-hour cleanup.
Choose appropriate access and retention settings in your Langfuse project.

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
  `decision_block_reason`, `rejection_reason`, `received_at`, and the saved
  `auto_approval_limit` used for its decision. `trace_url` is the saved Langfuse
  link, or `null` when no link is available.
- `GET /api/invoices/{id}/file` downloads the original uploaded file. Other
  visitors and sample Invoices without a file return 404. Downloads require an
  unexpired Demo Company session and cannot be cached.
- `POST /api/invoices/{id}/approve` approves; `POST /api/invoices/{id}/reject`
  rejects with `{"rejection_reason": "The goods did not arrive."}`. Reasons
  are trimmed and limited to 2,000 characters. Permissions, Company isolation,
  and status transitions are enforced by the API, not just the controls.

## Daily AI Limits

Live model requests default to **5 per visitor** and **100 across all visitors**
per UTC calendar day. Each Invoice read and each semantic line choice consumes
one request. Local embeddings, exact line matches, and scripted choices are free.
Override the limits with non-negative integers when starting the API:

```sh
INVOICE_AI_DAILY_VISITOR_LIMIT=3 INVOICE_AI_DAILY_GLOBAL_LIMIT=50 docker compose up --build
```

At either limit, the next live request is blocked. The Invoice finishes In Review
with the reason **daily AI limit reached**. If reading is blocked, later steps
are Skipped. If pairing is blocked, available deterministic checks and Duplicate
Invoice checks still run. Setting either limit to `0` disables live requests.
Scripted reads and choices and seeded sample Invoices do not consume the allowance
and remain available after the limit is reached.

A separate HttpOnly visitor cookie preserves the allowance across Demo Company
renewals. It lasts two days and does not grant access to Invoice data; the Demo
Company session cookie still expires after 24 hours. Clearing cookies creates a
new anonymous visitor, but does not reset the global allowance.

Usage is reserved in Postgres before each live call, including attempts that fail
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

`ERPTools.search_purchase_order_lines` retrieves up to five candidates by cosine
distance in pgvector, scoped to the same Demo Company and named Purchase Order.
Already paired lines and conflicting item codes are excluded. This remains a
plain service, not an MCP server, following ADR 0002.

Purchase Order lines receive 384-dimensional embeddings when the Demo Company
is seeded. FastEmbed runs `sentence-transformers/all-MiniLM-L6-v2` locally on the
CPU, with no paid embedding API. The Docker build downloads and caches the model;
the first non-Docker run needs network access to download it. Startup backfills
existing lines and rebuilds vectors when the configured embedding model changes.
Vectors carry their model name, so fake and real vectors are never mixed in a
search.

## Three-Way Match

Invoice reading captures the printed Purchase Order number and optional item
codes. Deterministic code pairs lines by a unique identical item code or an
identical description first. For unresolved lines, the model chooses a candidate
by meaning, or chooses none if no candidate fits. A choice outside the supplied
candidates is ignored. Conflicting codes, unresolved ambiguity and unpaired lines
require review; a Purchase Order line cannot be reused by another Invoice line,
and semantic choices cannot take lines reserved by exact matches. Search or model
failures leave the line unpaired with a clear review reason.

- A unit price up to 2% above the Purchase Order passes; a lower price passes
  too. The grid retains the signed amount and percentage difference.
- Invoiced quantity must equal received quantity, and received quantity must
  not exceed ordered quantity. Partial deliveries pass.
- Each line has one Invoice / Purchase Order / Goods Receipt comparison table.
  Mismatched cells are red, and every review reason appears below the tables.

The model reads the Invoice and chooses line pairs; it does not compute pass/fail
or decide the Invoice Status. The Pair Lines step saves the candidates and chosen
pairs. The grid retains the original Invoice description beside the chosen
Purchase Order description. Successful checks are considered for Auto-Approval
by the rules below. Duplicate checks run even when matching fails or the
Purchase Order is missing.

In fake mode, semantic choices default to none. Set `INVOICE_FAKE_LINE_CHOICES`
to a JSON object mapping Invoice descriptions to chosen Purchase Order
descriptions, for example
`{"A4 recycled paper in boxes":"Recycled A4 paper, box"}`. A null value means
no candidate fits. Fake mode uses scripted embeddings and never downloads a model
or contacts a paid provider.

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

## Auto-Approval

The agent Auto-Approves only for a known Supplier, a passing Three-Way Match,
no Duplicate Invoice or Possible Duplicate, and a total strictly under the
Auto-Approval Limit. The default is **EUR 5,000.00**. A total equal to or above
the limit goes In Review with a reason, alongside every matching or duplicate
failure. An Invoice in another currency also requires review. Reading and line
pairing can use the model; the final decision is always computed in code.

Only **Admin** sees the Auto-Approval Limit editor in the sidebar footer.
Amounts must be non-negative and have at most two decimal places. Setting the
limit to `0` disables Auto-Approval.

- `GET /api/demo-company/auto-approval-limit` returns the Company's current
  setting, such as `{"amount": "5000.00", "currency": "EUR"}`.
- `PUT /api/demo-company/auto-approval-limit` accepts `{"amount": "2500.50"}`
  with `X-Demo-Role: Admin`. The API refuses Submitter and Reviewer changes.

The agent reads the limit when it decides, not when the Invoice is uploaded.
The limit and decision are saved together, and the Invoice detail shows the
saved amount. Reviewer Approve and Reject decisions also record the current
limit. Later limit changes never alter Auto-Approved, Approved, or Rejected
Invoices, and the agent's recorded steps remain unchanged.

## Checks and Tests

API tests use real Postgres with pgvector and a separate, disposable schema per
test. They exercise the HTTP API and the public Process an Invoice interface
with a scripted model, not internal database functions or paid providers.
Supplier tests use the real ERP tables, including name variations,
unknown Suppliers, ERP failures and isolation between Demo Companies.
Three-Way Match tests use the same public interface, with separate files for
Price Tolerance, quantities, missing records and line pairing. Semantic pairing
tests use scripted embeddings and model choices with real pgvector search. They
cover ranked candidates, refused and invalid choices, exact-match priority,
Company/Purchase Order isolation, failures, and embedding model changes.
Duplicate Invoice tests cover both rules, the 30-day boundary, combined failure
reasons, history failures, saved record links, and Company/Supplier isolation.
Daily AI limit tests cover both caps, concurrent workers, Demo Company renewal,
midnight UTC reset, zero limits, and scripted reads. The live SDK retry checks
use a local HTTP endpoint for both Invoice reading and line pairing; no paid
provider is contacted.
Role and Review Queue tests exercise permissions, uploader tracking, final
decisions, required Rejection Reasons, view filters, and counts through the
HTTP API. Isolation tests cover cross-company lists, reads, decisions, downloads,
and ERP reads. Expiry tests cover session replacement at exactly 24 hours,
uploaded files, preservation of unexpired companies, and unattended cleanup
both at startup and on the recurring schedule.

Auto-Approval tests cover the strict amount boundary, unknown Suppliers,
Possible Duplicates, currency mismatches, combined review reasons, and a limit
change between upload and decision. Limit API tests cover Admin permissions,
invalid amounts, Company isolation, zero limits, future decisions, and immutable
Auto-Approved, Approved, Rejected, and sample decisions.

Tracing tests use the real Langfuse SDK with an in-memory OpenTelemetry exporter
and a local project response. Both model-provider clients use local HTTP
responses, so token usage and timing are checked without cloud charges. Tests
cover a single trace per run, concurrent-run isolation, all steps and ERP calls,
failed reads, persisted links, disabled configuration, and Langfuse outages.

With the stack running, run every check CI runs except the build and browser
tests:

```sh
docker compose exec -T api scripts/check.sh
npm --prefix web run check
```

To format staged files on every commit, enable the pre-commit hook once per
clone. It needs `npm --prefix web ci` and `uv sync --directory api` on the host.

```sh
git config core.hooksPath .githooks
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
and approving from the Review Queue, the Admin-only limit editor and saved
decision limit, optional Langfuse links, links to earlier Invoices, and the comparison grid's mismatch
colors, lower-price differences, differently worded paired descriptions and
mobile layout. The grid rendering check
uses a fixed HTTP response; processing rules are tested against real Postgres.
CI runs Python
lint, formatting, types and tests, then web types, lint, a production build, and
the browser tests against that production build. CI uses the scripted model;
no cloud credentials or paid services are required.

## Reading Accuracy

The reading eval processes three fixed, labelled Invoice images through the same
Process an Invoice interface as the app. It reports accuracy for each labelled
field and overall, then saves a JSON report with the date, model, sample version
and checksum, source credit, expected and read values, and mistakes.

Run it with one command:

```sh
docker compose run --rm api uv run --locked python -m evals.reading --check
```

This uses a scripted fake with deliberate mistakes: a wrong total, a wrong
quantity, and an unreadable Invoice. Its **71.11% (32/45)** baseline proves the
scorer catches errors; it is not a measurement of a real model. CI runs the same
command and fails if any field score or the overall score changes. Reports are
saved under `api/evals/results/` and uploaded as the `invoice-evaluations` CI
artifact, including failed baseline checks. Each run gets its own file.

The separate [generated sample](api/evals/data/generated-v1/README.md) adds two
PNGs, a single-page PDF, and a two-page PDF with lines and totals on page two.
Run it with:

```sh
docker compose run --rm api uv run --locked python -m evals.reading --sample-dir evals/data/generated-v1 --check
```

Its fake baseline is **83/84 (98.81%)**, with one deliberately incorrect total.
CI runs both samples and keeps their reports separately. The generated examples
are fictional, not Kaggle data. Fake runs check the evaluation workflow and
scoring; real-model runs are needed to measure actual reading accuracy.

Data: [High-Quality Invoice Images for OCR](https://www.kaggle.com/datasets/osamahosamabdellatif/high-quality-invoice-images-for-ocr)
by **osama hosam Abdellatif**, dataset version **3**. The database and derived
labels are licensed under [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/);
individual contents use [DbCL 1.0](https://opendatacommons.org/licenses/dbcl/1-0/).
See the [sample attribution and scoring notes](api/evals/data/reading-v1/README.md).
Only annotated fields are scored; absent labels do not become errors. This tiny
sample is a repeatable check, not a representative quality estimate, and some
source images may be synthetic. Use the live evaluations below to measure a
real model's accuracy, cost and time.

## Decision Accuracy

The decision eval runs 14 fixed synthetic cases through the same Process an
Invoice interface as the app, using real Postgres and scripted model responses.
It covers clean Auto-Approval, prices above tolerance and below the Purchase
Order, quantity mismatches, partial deliveries, excess receipts, different
wording, missing Purchase Orders and Goods Receipts, both duplicate rules,
unknown Suppliers, the Auto-Approval Limit, and unmatched lines.

```sh
docker compose run --rm api uv run --locked python -m evals.decisions --check
```

The baseline is **14/14 (100%)** with **zero wrong Auto-Approvals**. A decision
counts as correct only when its Invoice Status and every review reason match
the case's labels. Each case gets an isolated Demo Company; model responses
are scripted, but matching and decisions use the application's real rules.

Any wrong Auto-Approval fails the command, even without `--check` and even if
the saved baseline accepts it. With `--check`, changes to scores, case IDs,
statuses, or reasons also fail. Reports retain the date, model, sample checksum,
and expected and actual decisions under `api/evals/results/`, including failed
checks. CI runs this gate and archives reports in `invoice-evaluations`.

See the [case and baseline notes](api/evals/data/decisions-v1/README.md) before
updating the sample or baseline. These cases prove deterministic decision
behavior, not real-model reading or pairing accuracy.

## Live Model Evaluations

Eval commands default to the fake model, regardless of `INVOICE_MODEL_PROVIDER`.
Paid calls require an explicit `--provider openai` or `--provider anthropic`.
`--model` overrides `INVOICE_MODEL`; without either, the defaults are
`gpt-4.1-mini` and `claude-haiku-4-5-20251001`. `--check` is fake-only.

Live runs need the chosen provider's `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`,
both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`, and enabled tracing.
`LANGFUSE_BASE_URL` selects the Langfuse region or server. Configure model
pricing in Langfuse for custom model names.

```sh
docker compose run --rm api uv run --locked python -m evals.reading --provider openai --model gpt-4.1-mini
docker compose run --rm api uv run --locked python -m evals.decisions --provider openai --model gpt-4.1-mini
```

Reading uses the real vision reader. Decisions keep the labelled Invoice fields
and use real model line pairing, so document-reading errors do not obscure the
decision score. Both use local embeddings and the same Process an Invoice
interface as the app. Live evals create Demo Companies, Invoices and usage in
`TEST_DATABASE_URL`; use a dedicated evaluation database. The usual daily AI
limits still apply.

Each JSON report includes provider, model, date, sample checksum and scoring
version, plus a trace link, USD cost and elapsed seconds for each Invoice.
Cost sums the Langfuse generation and embedding observations; time is the
completed root **Invoice run** span, not just model latency. Report averages
include every evaluated Invoice. Fake runs have `null` measurements, not zero.
Missing traces or pricing also stay `null`, with `metrics_error` explaining why;
live commands save those reports and fail rather than report a partial average.
The collector flushes tracing, follows observation pages and retries delayed
or unavailable trace data for up to 60 seconds per Invoice. It records the
actual model-call count and waits for those generation observations before
accepting a cost, so a partially ingested trace cannot look like a free run.
An Invoice that genuinely makes no model calls can still have zero cost.

### Manual CI

In GitHub Actions, choose **Real-model evaluations**, then **Run workflow**.
Select the provider and optionally a model. Add the provider API key and both
Langfuse keys as repository secrets first; set the optional repository variable
`LANGFUSE_BASE_URL` for another Langfuse region or server.

The [manual workflow](.github/workflows/evaluate.yml) runs both reading samples
and all decision cases against a fresh Postgres database. It keeps running the
other evals after a failure, retains the wrong-Auto-Approval gate, and uploads
JSON reports plus a comparison summary in an `invoice-evaluations-<provider>-...`
artifact for 30 days. Normal push and pull-request CI stays fake and free.

### Comparing Models

Download artifacts from different runs into the same results directory, then run:

```sh
docker compose run --rm api uv run --locked python -m evals.compare evals/results
```

File paths also work. The Markdown tables put models side by side for accuracy,
wrong Auto-Approvals, average cost and average time. Only reports with the same
eval kind, sample version, checksum and scoring version share a table; different
samples remain separate. Missing measurements are shown as unavailable.

## Layout

The API is organised by layer (ADR 0004). A feature keeps the same file name in
each layer, for example `routes/invoices.py`, `schemas/invoices.py` and
`services/invoices.py`.

- `api/src/invoice_agent/routes/`: HTTP endpoints, cookies and status codes.
- `api/src/invoice_agent/schemas/`: shapes of data in and out.
- `api/src/invoice_agent/services/`: business rules and SQL: Demo Company
  sessions, the Process an Invoice graph (`invoice_processing.py`), Invoice
  lookups and Reviewer decisions (`invoices.py`) and ERP Tools.
- `api/src/invoice_agent/clients/`: Invoice readers for AI models, the fake
  reader and its response fixture.
- `api/src/invoice_agent/workers/`: local Invoice queue and worker thread.
- `api/src/invoice_agent/db/`: Postgres schema with pgvector, its startup
  script, and Demo Company sample data.
- `api/tests/`: API tests, one file per behaviour.
- `web/src/features/invoices/`: API client, Split view, and its browser test.
- `web/src/features/demo-company/`: Demo Company expiry and the Auto-Approval
  Limit editor.
- `web/src/components/ui/`: generated shadcn/ui components.

The browser reaches only the HTTP API through a same-origin Next.js rewrite.
There is no database access or locally mocked Invoice data in the web app.
See `CONTEXT.md` for domain language and `docs/adr/` for architecture decisions.
