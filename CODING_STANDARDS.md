# Coding standards

Rules for review. Skip anything ruff, mypy, ESLint or Prettier already enforces.

## API

- Follow `docs/adr/0004-api-organised-by-layer.md`: what each layer holds, the downward import direction, and `app.py` as the only wiring module.
- A feature keeps the same file name in each layer (`routes/invoices.py`, `schemas/invoices.py`, `services/invoices.py`).

## Modules

- Build **deep modules**: a small interface over a lot of behaviour.
- Split a file when it holds two reasons to change; a long file with one job stays whole.

## Tests

- Group tests by **behaviour** seen through the seam (e.g. Price Tolerance, Duplicate Invoice, Auto-Approval), one file per behaviour, with shared builders for test data.

## Web

- Organise by **feature** under `web/src/features/`. Each feature folder holds its code and its tests.
- UI matches the approved prototype in `docs/prototype/variant-b.tsx`: its controls as well as its layout.
