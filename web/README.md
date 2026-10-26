# Invoice Agent Web

Next.js 16, React 19, Tailwind CSS 4, and shadcn/ui.

See [the repository README](../README.md) for the one-command Docker stack and
all checks. Run that stack first, or start Postgres and the API with
`docker compose up --build api` from the repository root.

For a host-side web development server:

```sh
npm ci
npm run dev
```

Open http://localhost:3000. Requests under `/api` are proxied to the FastAPI
service at `http://127.0.0.1:8000`. Set `API_URL` to change that address.
The browser never reaches Postgres directly.

Invoice code and its Playwright test live together in `src/features/invoices`.
Fonts are self-hosted, so builds do not fetch fonts from Google.
