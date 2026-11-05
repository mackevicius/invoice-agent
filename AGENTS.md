## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues. See `docs/agents/issue-tracker.md` before issue operations.

### Triage labels

Use the five default triage labels. See `docs/agents/triage-labels.md` before triaging or changing labels.

### Domain docs

Single-context: root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md` before exploring the codebase.

## Code layout

- **API (`api/`)**: by layer: `routes/`, `schemas/`, `services/`, `clients/`, `workers/`, `db/`; tests in `api/tests/`. A feature keeps the same file name in each layer. The Process an Invoice graph is `services/invoice_processing.py`.
- **Web (`web/src/features/`)**: by feature (`invoices/`, `demo-company/`), each folder holding its code and tests. See `web/AGENTS.md` before UI work.
- **Infra (`infra/`)**: AWS SAM stack (ADR 0005), deployed by CI from `main`. Human setup steps live in `scripts/setup-aws-deploy.sh`.
- **Checks**: `docker compose exec -T api scripts/check.sh` and `npm --prefix web run check` (on the host: the web container cannot see the root Prettier config). CI runs the same.
- **Review rules**: `CODING_STANDARDS.md`.
