<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Finding things

- **Next.js docs**: file search skips `node_modules`. Search `web/node_modules/next/dist/docs/` with ignored files included, starting from `index.md`. Files are `.md`.
- **UI design**: the approved design is Variant B in `docs/prototype/variant-b.tsx`. Before UI work, read the parts you are building and match its controls and layout. It uses mocked data; copy no prototype code paths into the app.
