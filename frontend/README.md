# OrderDesk frontend

Next.js (App Router) + TypeScript + Tailwind 4 + Redux Toolkit / RTK Query. Light theme only.

## Run

The backend must be running (`docker compose -f infra/docker-compose.yml up`, API on port 8001).

```
cd frontend
cp .env.example .env.local     # API_URL=http://localhost:8001
npm install
npm run dev                    # http://localhost:3000
```

Sign in with a user made by `python -m app.cli.create_admin`.

## How it talks to the API

The browser only calls this Next.js server. `next.config.ts` rewrites `/api/*` and `/auth/*` to FastAPI,
so there is no CORS and the httpOnly refresh cookie (path `/auth`, SameSite=strict) stays same-origin.
The access token is kept in memory only; a page reload restores the session with `POST /auth/refresh`.
A 401 triggers one shared refresh and a retry (`store/api.ts`).

## Screens

| Route | Who | What |
|---|---|---|
| `/login` | everyone | sign in (no public sign-up) |
| `/change-password` | everyone | forced on first sign-in with a temporary password |
| `/inbox` | reviewer, admin | orders by status, search, upload .eml/.pdf, live document status |
| `/orders/[id]` | reviewer, admin | source document left (selected line highlighted), lines right with reason, candidates, catalogue search, qty edit, approve/reject. Keys: j/k, 1-3, a |
| `/metrics` | admin | routing, no-edit rate, timing, LLM usage and cost, latest evals |
| `/users` | admin | add users, change role, deactivate |

Components live in `components/ui` (shadcn-style). `components/ui/sign-in.tsx` is adapted from the
provided sign-in reference: same layout and animations, light only, no social sign-in.
