# Enterprise Conversational Analytics One UI

The Phase 18 frontend is a React and TypeScript single-page application built with webpack. It is
the unified chat surface for the existing backend specialists; business routing and validated SQL
remain backend-owned.

## Prerequisites

- Node.js 18 or newer
- npm
- The FastAPI backend on `http://localhost:8000` for interactive use

No frontend secret is required. Gemini, Azure, AWS, and database credentials must remain on the
backend.

## Commands

```bash
npm install
npm run dev
npm run typecheck
npm test
npm run lint
npm run build
```

`npm run dev` starts webpack-dev-server on port 5173. Open `http://localhost:5173`. The development
server proxies `/api` and `/chat` to `http://localhost:8000`. A production build is written to
`dist/` and can use the build-time `API_BASE_URL`; an empty value uses same-origin relative URLs.

The app uses `HashRouter`. Phase 18 serves the primary chat route at `#/`; the routing foundation
can accept a later `#/dashboard` route without implementing that Phase 19 feature now.

## Sessions and feature flags

The browser session cookie remains HttpOnly and backend-managed. The frontend creates one
`crypto.randomUUID()` tab identifier, stores it in `sessionStorage` as `eca_tab_id`, and includes it
as `X-Tab-Id` with `credentials: "include"` on API requests. This isolates multiple tabs without
placing the server cookie identifier in application state.

At startup the app loads `/api/ui-feature-flags` and `/api/tool-flags`. These flags control visible
features such as current-turn context, follow-up chips, latency, and tool availability; they are
not an authorization mechanism. Mode descriptions and welcome content come from the backend.

## SQL safety boundary

Standard Data Intelligence requests display backend-validated, privacy-tokenized SQL. The SQL is
read-only in the UI. **Run Query** calls `/chat/execute-sql` without a SQL body, so the backend can
execute only the accepted SQL and current token mapping stored for that tab.

Frontend tests mock all API calls and require no running backend, LLM provider, PostgreSQL, or cloud
service.
