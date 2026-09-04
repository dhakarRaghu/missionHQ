# Mission HQ console

Web console for the Mission HQ agent platform. Next.js 16, TypeScript, Tailwind v4, shadcn/ui, TanStack Query.

- Dev: `npm run dev`, then open http://localhost:3000.
- Needs the FastAPI backend on http://127.0.0.1:8000. All `/api/*` requests are rewritten to it in `next.config.ts`.
- Env vars: copy `.env.example` to `.env.local`. `NEXT_PUBLIC_API_BASE` (browser, default `/api`) and `BACKEND_ORIGIN` (server-only, default `http://127.0.0.1:8000`).
- Live updates come from one SSE stream (`/api/events`) started in `src/components/providers.tsx`.
- Views: Inbox, Board, Runs, Live feed, Agents, Chat (placeholder).
- Checks: `npx tsc --noEmit`, `npx eslint src`, `npm run build`.
- Design rules live in `AGENTS.md`.

## Deploying to Vercel

The console can run on Vercel against a backend hosted elsewhere.

1. In the Vercel project settings, set **Root Directory** to `frontend`.
2. Add the env var `NEXT_PUBLIC_API_BASE` with the absolute backend URL,
   including the `/api` prefix. Example: `https://hq-api.example.com/api`.
   `BACKEND_ORIGIN` is not needed; the dev rewrite is unused in this mode.
3. On the backend, set `API_BEARER_TOKEN` in `backend/.env` and allow the
   Vercel origin in CORS.
4. Open the deployed site. It redirects to `/login`. Paste the value of
   `API_BEARER_TOKEN` and click **Sign in**. The token is stored in
   `localStorage` (`hq.token`) and sent as `Authorization: Bearer <token>`
   on every request. A 401 clears it and returns you to `/login`.
5. The SSE stream (`/api/events`) cannot send headers, so it sends the token
   as `?token=<token>`. Use HTTPS for the backend so the token is not sent in
   clear text.

**Sign out** is the last entry in the sidebar. It appears only when a token is
stored. If the backend has no `API_BEARER_TOKEN` configured, `/login` offers
**Continue without a token** instead.
