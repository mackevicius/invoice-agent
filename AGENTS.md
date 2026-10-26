## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues. See `docs/agents/issue-tracker.md` before issue operations.

### Triage labels

Use the five default triage labels. See `docs/agents/triage-labels.md` before triaging or changing labels.

### Domain docs

Single-context: root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md` before exploring the codebase.

## Code layout

- **API (`api/`)**: organise by **layer**: `routes/` (HTTP: endpoints, cookies, status codes), `schemas/` (data shapes), `services/` (business logic and SQL), `clients/` (outside systems: AI models, ERP), `workers/` (background jobs), `db/` (schema and seed). A feature keeps the same file name in each layer. Follow the import rule in ADR 0004. Tests live in `api/tests/`.
- **Web (`web/`)**: organise by **feature** (Invoice reading, matching, Review Queue, ERP tools). Each feature folder holds its code and its tests.
- Build **deep modules**: a small interface over a lot of behaviour. Split a file when it holds two reasons to change; a long file with one job stays whole.
- Group tests by **behaviour** seen through the seam (e.g. Price Tolerance, Duplicate Invoice, Auto-Approval), one file per behaviour, with shared builders for test data.
