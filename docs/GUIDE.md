# Mission HQ

A personal team of AI agents that runs on your own machine.

They work while you sleep, keep notes in plain markdown files you own, and
stop and ask you before anything reaches the outside world. There is no cloud
account holding your data, no per-seat pricing, and no model you are locked
into. A week of everything running costs roughly a dollar.

This document is the whole picture: what it does for you, how you use it,
what keeps it safe, and how to set it up from an empty machine.

---

## 1. What it actually does

You talk to one agent, **sage**. It answers what it can and hands the rest to
whoever owns that work. You never need to know which agent to ask.

A normal day looks like this, with nothing from you:

| Time | What happens |
|---|---|
| 02:00 | The librarian folds yesterday's notes into your long-term memory, without letting it grow past its size cap |
| 08:00 | Scout reads the newest research and adds ranked content ideas |
| 09:00 Mondays | Planner reads the board and your last seven daily notes and writes one page on the week ahead |
| 21:00 | Sage writes the day's note: what the agents did, anything you filed, one suggestion, and one question for you |
| Sunday 20:00 | Sage writes the weekly review |

And when you do want something:

> **You:** What is the most important open loop in my vault right now?
>
> **Sage:** Your untaken review of hunter's two quarantine notes, which blocks
> the promote-or-drop step that makes the research pipeline work end to end.

> **You:** Find out what changed in DBOS Transact in the last month.
>
> **Sage:** That is hunter's. I have asked it to research the last month and
> file the note in `quarantine/`. I will summarise it in tonight's daily note.

The second one is the point. You asked one agent; a different one did the work.

---

## 2. The agents

Six run in-process. One more runs outside it, and is off by default.

| Agent | What it is for | Runs |
|---|---|---|
| **sage** | Your second brain and the one you talk to. Daily notes, weekly reviews, answers from the vault, and handing work to the others | 21:00 daily, Sunday 20:00, and whenever you chat |
| **librarian** | Keeps memory small and current. Merges the day's notes into the shared memory blocks and retires what is no longer true | 02:00 daily |
| **hunter** | Reads the web and writes what it found. The only agent with web access, and it can write nowhere but `quarantine/` | On request |
| **scout** | Content for YouTube and X. Turns hunter's research into ideas and drafts. Never posts without your approval | 08:00 daily |
| **planner** | Reads the board and your daily notes, writes one page on the week | 09:00 Mondays |
| **factory** | Builds new agents. Describe one in plain words and it writes the folder for you to approve | On request |
| **operator** | Reads pages in the browser *you are signed into*, through the Codex or Claude CLI. Every run needs approval first | On request, off by default |

Adding an agent is adding a folder: `agents/<name>/job.md` plus a
`policy.md`. Or ask factory to write it for you.

---

## 3. How you use it

Four ways in, all showing the same system.

**Chat.** Open the console and talk to sage. Each turn is a real run: it can
read your whole vault and use its tools. A reply takes 20 to 60 seconds
because it is doing work, not autocompleting. Type `@` to name an agent, `#`
to link a note.

**The board.** Every task an agent is doing, grouped by state: needs you, in
flight, blocked, backlog. Click one to read its full event log — every tool
call, its arguments, its result, and what it cost.

**Telegram.** The same approvals and summaries on your phone. `/board`,
`/costs`, `/agents`, `/digest`. Approving there and approving in the console
resolve the same ticket.

**The files.** The vault is ordinary markdown in a git repository. Open it in
Obsidian, edit it in any editor, or read it with `cat`. Nothing is locked in
a database. If Mission HQ disappeared tomorrow, your notes would not.

---

## 4. The rules that make it safe to leave running

An agent that can read the web, write your memory, and message the world is
one bad web page away from doing real damage. Five rules prevent that, and all
five are enforced in code rather than asked for in a prompt.

**Nothing reaches the outside world without you.** Every tool is classified.
Reading and note-taking are free. Anything that acts outward or spends money
stops the run, opens a ticket in your Inbox, and waits. Answer in the console
or in Telegram; the run resumes where it stopped, even days later.

**Web text is quarantined.** A fetched page never reaches the agent that asked
for it. It goes to a separate reader with no tools and no memory, which
returns only a fixed set of facts. If the page contains instructions aimed at
an AI, they come back quoted as evidence in a field marked "this page tried to
instruct you" — never as something to obey. Anything web-derived lands in
`quarantine/` and stays there until you promote or drop it.

**A web-reading agent cannot act.** Enforced when the agent loads, not at run
time. Hunter holds web access, so it is refused any outward tool and may write
nowhere but `quarantine/`. Getting this wrong stops the agent loading, loudly.

**Memory cannot be quietly destroyed.** Each shared memory block has a size
cap, every write is one git commit you can revert, and a consolidation that
drops more than 30% of a file is refused.

**There is an off switch.** Create a file called `HALT` in the repo root and
no agent starts a run. Per-agent pause and daily spend caps sit above that.

---

## 5. Setting it up

Requirements: macOS or Linux, PostgreSQL 16+, Node 20+, and
[uv](https://docs.astral.sh/uv/).

```bash
git clone <your fork> missionHq && cd missionHq
createdb missionhq
cd backend && uv sync && cp .env.example .env
```

Fill in `backend/.env`. The four that matter:

| Setting | What it is |
|---|---|
| `DATABASE_URL` | `postgresql://localhost:5432/missionhq` |
| `GATEWAY_BASE_URL`, `GATEWAY_API_KEY` | Any OpenAI-compatible endpoint. No provider is named anywhere in the code |
| `TELEGRAM_BOT_TOKEN`, `OWNER_CHAT_ID` | Optional. Talk to @BotFather, then send your bot a message and read the chat id from the log |
| `API_BEARER_TOKEN` | `openssl rand -hex 32`. You paste this once to sign in to the console |

Pick your models in `backend/models.yaml`. Agents ask for a *role* — `cheap`,
`default`, `deep` — and that file maps roles to real model names. Point `deep`
at a stronger model and only the agents that need it get more expensive.

Then start both halves:

```bash
cd .. && ./ops/supervise.sh install        # backend under launchd, restarts on crash
cd frontend && npm install && npm run dev  # http://localhost:3000
```

Sign in with your `API_BEARER_TOKEN`. You should see six agents.

### The one step people skip

Open **Memory → About you → Write** and say who you are: your goals, your
audience, what you are working on, how you like things done.

Every agent reads that file before every run. Left empty, they are competent
and generic — they will write about the only subject they can see, which is
the system itself. Ten minutes here changes every reply the system will ever
give you. It is worth more than any code you could add.

---

## 6. Your first week

1. **Fill in `memory/user.md`.** As above.
2. **Let sage run for seven days** and read the daily notes.
3. **Answer what lands in your Inbox.** Each ticket is an agent paused,
   waiting.
4. **Review the quarantine notes** hunter files. Nothing is promoted into your
   real memory until you say so, so an unreviewed queue stalls the research
   pipeline.
5. **At the end of the week, judge it honestly.** If you ignored half of what
   it sent you, the output quality is wrong — fix that before building more.
   That measurement is on the Inbox page as "value week", and it is the metric
   this project is designed to be killed by.

---

## 7. Keeping it healthy

```bash
cd backend
uv run python -m hq.cli prompt-check all   # contradictions in an agent's instructions
uv run python -m hq.cli vault-health       # duplicates, orphans, unsourced notes
uv run python -m hq.cli board-check        # every task matches its event log
```

Run `prompt-check` after editing any agent, and `vault-health` weekly. A
separate judge reads what an agent actually sees and reports contradictions,
buried rules and gaps, because an agent cannot detect a contradiction in its
own instructions.

`./ops/backup.sh run` dumps the database and pushes the vault.
`./ops/backup.sh restore-drill` proves the backup actually restores.

---

## 8. When something looks wrong

| Symptom | Cause |
|---|---|
| Every scheduled run failed with a long duration and no tokens | The machine slept mid-run. The backend holds a wake assertion on AC power; on battery it will still sleep |
| A run says "no artifact" | It claimed to write something and did not. That is the check working |
| A task sits in "needs approval" | An agent is paused waiting for you. Inbox, or Telegram |
| The console shows a tool an agent does not have | The manifest changed but the backend has not restarted. `./ops/supervise.sh restart` reports the pid change |
| Everything is stuck | Check for a `HALT` file, then `./ops/supervise.sh status` |

Every run is on the Runs page with its model, tokens, real cost, and every
tool call it made. That page is the first place to look, not the log.

---

## 9. What it costs

About **$1.19 for 84 runs over a week**, on a mid-range model through a
gateway. A daily cap and a per-run cap are in the settings, and the Runs page
shows spend against them.

The external runtimes are different: Claude Code bills your Claude account per
token, and Codex uses your ChatGPT plan. Those runs are approved one at a time
for that reason.

---

## 10. What it deliberately does not do

- **No bulk collection from social platforms.** Their terms prohibit it and
  the account at risk is yours. `browser_read` refuses them in code. Use their
  APIs, or read a page yourself with the browser agent while you are there.
- **No posting without you.** Scout writes drafts. Publishing is an outward
  action and stops for approval.
- **No agent writes a standing rule.** An agent can propose one; only you can
  make it a rule.
- **No hosted service.** One owner, one machine, not exposed to the internet.
  For access away from home, put it behind Tailscale — see
  [deploy.md](deploy.md).

---

## Further reading

- [deploy.md](deploy.md) — production setup, Linux units, Tailscale, backups
- [external-runtimes.md](external-runtimes.md) — running an agent through the
  Codex or Claude CLI so it can use the browser you are signed into
- [adr/](adr/) — why particular decisions were made
- `frontend/AGENTS.md` — console design rules
