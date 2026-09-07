# Mission HQ: brief for a new agent session

Paste this whole file as your first message to Codex (or any coding agent) in
a fresh clone. It is the context that is not obvious from the code.

---

## What this is

Mission HQ is a self-hosted personal multi-agent system. Six agents run on a
schedule, write markdown notes into a git-tracked vault, and stop for the
owner's approval before anything reaches the outside world. It is built to be
owned: any model, the owner's data, the owner's rules.

The owner is a software developer. He is building this as a product he keeps
growing, not a one-off script, so prefer a correct small change over a clever
large one.

## Run it

```bash
brew services start postgresql@17      # the app schema is hq, DBOS owns dbos
cd backend && uv sync
cp .env.example .env                   # then fill in the values below
cd .. && ./ops/supervise.sh install    # launchd; the plist is a template
cd frontend && npm install && npm run dev
```

`.env` needs, at minimum: `DATABASE_URL`, `GATEWAY_BASE_URL`,
`GATEWAY_API_KEY`, `API_BEARER_TOKEN` (any 64 hex chars), `OWNER_CHAT_ID` and
`TELEGRAM_BOT_TOKEN` if you want Telegram. Console at localhost:3000; sign in
with `API_BEARER_TOKEN`.

Checks that must pass before any commit:

```bash
cd backend  && uv run ruff check src && uv run mypy src
cd frontend && npx tsc --noEmit && npx eslint src && npm run build
```

## The rules that hold the system up

Break one of these and the safety story stops being true. They are enforced in
code, not asked for in prompts.

1. **One enqueue path** (`engine.dispatch`) and **one task write path**
   (`board.apply`, which writes an event and a projection and validates the
   transition). Never write `hq.tasks` directly.
2. **The tickets table is the source of truth for approvals.** The DBOS message
   is only a wake-up; the table decides.
3. **`@hq_tool`** makes a function a DBOS step, registers it, sets its action
   class, and logs the call with its arguments and result. A tool that is not
   registered does not exist.
4. **The scoped trifecta**, checked at load: an agent that reads the web may
   hold no outward tool, no `notify_owner`, no `create_subtask`, and no vault
   scope except `quarantine/**`. One poisoned page must never become a
   standing instruction.
5. **Web text never reaches a privileged agent.** `web_fetch` and
   `browser_read` pass every page through a zero-tool reader that returns a
   fixed struct. An instruction found in a page is logged as evidence, never
   obeyed.
6. **`memory.write` is the only writer** to the vault, one git commit per
   write. Anything that writes must go through it and its gates.
7. **Per-agent working memory (`memory/agents/*.md`) is exempt from the
   destructive-edit gate.** It is rewritten every run by design. Applying the
   gate to it broke every scheduled run for three days.

## Where things are

- `backend/src/hq/` — `engine.py` (dispatch, workflows, cron, watchdog),
  `runner.py` (the agent loop, approvals, guardrails), `loader.py` (manifests,
  trifecta, prompt assembly), `memory.py` (vault + gates), `board.py`,
  `tools/`, `runtimes/`, `api/`.
- `agents/<name>/job.md` — the manifest. Frontmatter is the contract; the body
  is the prompt. `policy.md` sits beside it and is injected first.
- `vault/` — its own git repo, gitignored by the parent. The agents' output.
- `frontend/` — Next.js console. Read `frontend/AGENTS.md` before touching it.

## State as of this handoff

- 81 runs recorded, about $1.10 total. Six agents active; `operator` is a draft.
- Vault: daily notes, a weekly review, three quarantine notes, memory blocks.
- `BROWSER_ENABLED=true` — `browser_read` opens its own Chrome for open-web
  reading. Social platforms are refused in code.
- `CODEX_RUNTIME_ENABLED=false` — turn it on where the ChatGPT extension works.

## What to do first, on this machine

1. **Confirm the browser is reachable:**
   ```bash
   codex exec --skip-git-repo-check "use browser through browser extension and tell me what tabs are open"
   ```
   Tabs listed means it works. Nothing else matters until it does.
2. Set `CODEX_RUNTIME_ENABLED=true`, flip `agents/operator/job.md` to
   `status: active`, restart the backend.
3. Give operator a task. It will stop at `needs_approval` **before running**.
   Approve it in the Inbox, watch the tab open, and check the result lands in
   `quarantine/`.

## Open work, roughly in order of value

1. **`vault/memory/user.md` is 583 of 4000 characters and names no goals.**
   Every agent reads it before every run, so they are all working on Mission HQ
   itself rather than on the owner. This is the owner's to write, and it is
   worth more than any code change on this list.
2. **Three quarantine notes have never been reviewed.** The research pipeline
   is stalled at the owner's step, which is why scout keeps reusing one source.
3. **Hunter cannot search**, only read a URL it is given or can guess. Brave
   Search API or a self-hosted SearXNG, behind the same quarantine rule.
4. **Follow-up turns for the external runtimes.** One turn per run today. The
   session id is captured, so `codex exec resume <id>` is a small change.
5. **A bookmarklet clipper**, so pages the owner is reading land in
   `vault/inbox/`. Sage already files anything found there.
6. **YouTube via its official API; X via its official API** (about $6.50/month
   at this volume). Do not automate LinkedIn: its terms prohibit it and the
   account at risk is the owner's.

## Things already decided, do not redo them

- **No LangGraph.** The workload is linear; DBOS checkpoints the whole program.
- **No LiteLLM proxy.** The gateway is hit directly.
- **No forge / GitHub agent.** It was removed on purpose.
- **No Discord.**
- **Two themes only**, light and dark. Accent presets were built and removed.
- **The board is read-only.** Status is machine-driven, so a draggable card
  would promise a move the engine ignores.
- **No automated test suite.** The owner decided this is personal software.
- **kimi does not work through Codex** (a gateway bug on that API path), and
  the gateway's own `/v1/responses` route only serves some models. Check before
  assuming a model works on a given path.

## How to work here

- Verify against the running system, not by reading. Dispatch a real task and
  read `hq.runs` and `hq.events`.
- `uv run python -m hq.cli prompt-check <agent>` finds contradictions in an
  agent's assembled prompt. `vault-health` finds duplicate, orphaned and
  unsourced notes. `board-check` proves the projections match the event log.
- Never commit or push unless asked. Never print a secret.
- When something fails, find the cause before changing anything. Three of the
  worst bugs here were misdiagnosed first, and the wrong diagnosis was written
  into the agents' memory, where it became the next week's plan.
