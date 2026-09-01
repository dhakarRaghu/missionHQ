# Mission HQ

A self-hosted personal multi-agent platform. Agents work on a shared task board,
share one markdown vault as memory, and ask for approval before anything leaves
the system. Telegram is the channel on the go; the web console is the desk view.

## Layout

```
missionHq/
├── backend/    Python 3.12 · DBOS Transact · Pydantic AI · FastAPI · python-telegram-bot
├── frontend/   Next.js 16 · shadcn/ui (Radix) · TanStack Query
├── agents/     one folder per agent: job.md + policy.md + skills/
├── vault/      the second brain: markdown in its own git repo
└── docs/adr/   decision records
```

## Run it

Requirements: PostgreSQL running locally, Node 20+, and [uv](https://docs.astral.sh/uv/).

```bash
createdb missionhq
cd backend && cp .env.example .env   # fill in gateway + Telegram values
uv run python -m hq                  # http://127.0.0.1:8000
```

```bash
cd frontend && cp .env.example .env.local
npm run dev                          # http://localhost:3000
```

The frontend proxies `/api/*` to the backend, so there is one origin and no CORS.

## Environments

Everything environment-specific lives in `backend/.env` (never in code). Moving
to Neon later means pasting its DSN into `DATABASE_URL`, nothing else:

```
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
```

`models.yaml` is the only place a provider or model id is named. Agents refer to
models by role (`cheap`, `default`, `deep`) or by registry name, so swapping a
provider is a one-line edit.

## Safety rules built into the code

- **One enqueue path** (`engine.dispatch`) and **one task write path** (`board.apply`),
  which appends an event and updates the projection in a single transaction.
- **Approval tickets** for any outward action. The ticket row is the source of
  truth, so the web console and Telegram resolve the same ticket and a second
  resolution is a visible no-op.
- **Scoped trifecta rule**: an agent that reads the web may not also send outward
  or write outside `quarantine/**`. Violations fail loudly at load, not at runtime.
- **Quarantined reader**: raw web text never reaches a privileged agent, only a
  validated struct, with any embedded instructions quoted as inert evidence.
- **Budgets**: per-run cost and tool-call limits, per-agent and system daily caps,
  and a notification cap so the system cannot train you to ignore it.
- **Kill switches**: a `HALT` file at the repo root, plus per-agent pause/resume
  from either interface.

## Adding an agent

Create `agents/<name>/job.md` with YAML frontmatter (tools, model role, caps,
cron) and a markdown body as its system prompt. Restart. No code changes.
