# Mission HQ

A self-hosted personal multi-agent platform. Agents work on a shared task board,
share one markdown vault as memory, and ask for approval before any action that
leaves the system. Telegram is the channel on the go. The web console is the
desk view. One owner, one machine, no public exposure.

## Layout

```
missionHq/
├── backend/    Python 3.12 · DBOS Transact · Pydantic AI · FastAPI · python-telegram-bot
├── frontend/   Next.js 16 · shadcn/ui (Radix) · TanStack Query
├── agents/     one folder per agent: job.md + policy.md + skills/
├── vault/      the second brain: markdown in its own git repo
├── ops/        run scripts, launchd plists, Caddyfile, backups
├── data/       logs/ and snapshots/ (gitignored)
└── docs/       deploy.md and adr/ (decision records)
```

## Dev quickstart

Requirements: PostgreSQL 16, Node 20+, and [uv](https://docs.astral.sh/uv/).

```bash
createdb missionhq
cd backend && cp .env.example .env && uv run python -m hq     # http://127.0.0.1:8000
cd frontend && cp .env.example .env.local && npm run dev       # http://localhost:3000
```

The frontend proxies `/api/*` to the backend, so there is one origin and no CORS.
Add an agent by creating `agents/<name>/job.md` and restarting the backend.

## Ops scripts

| Script | Purpose |
| --- | --- |
| `ops/supervise.sh` | backend service (launchd): install, status, restart, logs |
| `ops/frontend.sh` | `next start` service. Run `npm run build` first, after every frontend change |
| `ops/proxy.sh caddy` | Caddy reverse proxy on 127.0.0.1:8080 (`ops/Caddyfile`), fronted by Tailscale Serve |
| `ops/backup.sh` | `run` (pg_dump + vault push), `list`, `restore-drill` |
| `ops/backup-schedule.sh` | nightly backup at 03:30 (launchd) |

Production setup, systemd units for Linux, Tailscale Serve, and first-boot
checks: [docs/deploy.md](docs/deploy.md). Design decisions: [docs/adr/](docs/adr/).
