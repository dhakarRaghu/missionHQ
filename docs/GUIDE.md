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

A normal day looks like this, with nothing from you. It all runs in the
evening, after your own day is done, so the work is waiting when you wake up:

| Time | What happens |
|---|---|
| 18:30 | The next phase of your course is studied by hunter and written by tutor, once you have read the last one |
| 21:00 | Hunter sweeps company boards for new roles, verifies them, and scores them into the job ledger |
| 21:15 | Operator runs four LinkedIn searches in your signed-in browser, rotating through eight role families so each is searched every other night; hunter verifies what it finds. If the browser cannot be reached, it tries again twice, 15 minutes apart, before hunter falls back to the public boards |
| 22:00 | The learning run starts today's article (or Saturday's lab card, Sunday's week review) |
| 22:30 | Sage writes the day's note: one thing you did not know, what needs you, and one action |
| 22:50 | The digest goes to your phone, with the day's note at the top |
| 23:30 | Sage checks your memory blocks against the day and writes what should change to `memory/proposals/`; you promote what is right |
| 03:00 | The vault commits once for the day, the search index is rebuilt, and new lessons are published to your phone |
| Monday 09:00 | Sage proposes five roles to act on, with the next step for each |
| Wednesday 09:00 | Sage adds three to five content ideas from what you learned and built |
| Sunday 20:00 | Sage writes the weekly review |

And when you do want something:

> **You:** What is the most important open loop in my vault right now?
>
> **Sage:** Your untaken review of hunter's two quarantine notes, which blocks
> the promote-or-drop step that makes the research pipeline work end to end.

> **You:** Find out what changed in DBOS Transact in the last month.
>
> **Sage:** That is hunter's. I have asked it to research the last month and
> file the note in `quarantine/`. Its result will appear in this chat when it
> finishes, and I will summarise it in tonight's daily note.

The second one is the point. You asked one agent; a different one did the work.

---

## 2. The agents

Three run in-process. One more runs outside it, through an agent CLI.

| Agent | What it is for | Runs |
|---|---|---|
| **sage** | The one you talk to, and the keeper of memory. Routes work, writes the daily note and weekly review, proposes the job shortlist and content ideas, consolidates memory | 22:30 and 23:30 daily, Monday and Wednesday 09:00, Sunday 20:00, and whenever you chat |
| **hunter** | Reads the web and writes what it found: verified roles with a person to reach, and the study notes lessons are built from. It can write nowhere but `quarantine/` | 21:00 daily, and when the learning run asks |
| **tutor** | Your teacher. Plans the concepts worth knowing, writes each lesson a section at a time, checks every sentence against the study note | When the learning run or the course asks |
| **operator** | Reads pages only your signed-in browser can open, read-only, under one contract (`agents/operator/AGENTS.md`), with your approval | 21:15 discovery, and on request |

### Agent or skill?

Most new capability should be a **skill**, not an agent. A skill is a
procedure sage follows on request: a `SKILL.md` under `agents/sage/skills/`,
loaded when needed. It costs nothing to maintain, has no memory of its own,
and needs no new permissions.

An agent earns its own folder only when it needs one of three things:

1. **A different permission set.** Hunter reads the web, so it is walled off
   from acting and may write only to `quarantine/`. That isolation is the
   whole reason it is separate.
2. **Its own runtime.** Operator runs outside the in-process loop.
3. **A separate trust boundary.** Tutor writes the files you read and holds
   no web tool, which is why it may write them.

A schedule is not a reason: sage can hold a cron slot that loads a skill.
Weekly planning was an agent and is now `weekly-plan`, because it needed no
permission sage lacked, no memory of its own, and no separate trust. Building
agents was an agent and is now `new-agent`, for the same reason.

Sage's `new-agent` skill asks this question first, and answers "make it a
skill" most of the time.

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
cap, every write is in one nightly git commit you can revert, and a consolidation that
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

Start here. One number for whether the machine is working:

```bash
cd backend
uv run python -m hq.cli health             # one score, and the trend since last run
```

It reads data already recorded and calls no model, so it is free to run as
often as you like. It weights run success at 30% and vault quality at 25%,
because a system that fails a quarter of its runs, or fills its vault with
near-duplicates, is not healthy however clean the code is. It prints the
weakest line so you know what to fix first.

The rest, when you want the detail behind a low score:

```bash
uv run python -m hq.cli prompt-check all   # contradictions in an agent's instructions
uv run python -m hq.cli vault-health       # duplicates, orphans, unsourced notes
uv run python -m hq.cli board-check        # every task matches its event log
uv run python -m hq.cli reindex            # rebuild the vault full-text index
```

Run `prompt-check` after editing any agent, and `vault-health` weekly. A
separate judge reads what an agent actually sees and reports contradictions,
buried rules and gaps, because an agent cannot detect a contradiction in its
own instructions.

### Talking to one agent from the terminal

The fastest way to see whether an agent's instructions produce anything worth
reading. No Telegram, no board, straight to stdout:

```bash
uv run python -m hq.cli ask hunter "What changed in DBOS Transact this month?"
uv run python -m hq.cli models             # what the gateway serves vs models.yaml
```

`ask` is the command to reach for when an agent behaves oddly: change its
`job.md`, run `ask`, read the answer, repeat. Approvals still work, so a run
that needs one waits for you on Telegram.

### Scoring an agent against past runs

```bash
uv run python -m hq.cli evals export hunter   # build evals/hunter.yaml from finished runs
uv run python -m hq.cli evals run hunter      # score it against the stored answers
uv run python -m hq.cli evals history hunter  # how the score moved over time
```

### The regression set

Real failures, one case each, in `backend/evals/regression/*.yaml`. A case
gives an agent the input it was given on the day and grades what it does
with its production instructions: which tools it called, with what, what it
wrote. Every run calls the model, so it costs money and needs the gateway;
CI does not run it. The same incidents live in `backend/tests/` as checks
on the gates in code, with no model; those run everywhere.

A sage case with a `skill` may carry a `continuity:` block: the text
`hq.continuity` would build from the ledger at dispatch, fixed here as
data, so the case judges what the agent does with a stated last-night lead
or a closed row rather than with whatever the live ledger holds that day.

```bash
uv run python -m hq.cli regress cases                 # every case id and the incident it holds
uv run python -m hq.cli regress run before-$(git rev-parse --short HEAD)
uv run python -m hq.cli regress run after-$(git rev-parse --short HEAD) --k 2   # each case twice
uv run python -m hq.cli regress compare before-abc1234 after-abc1234
```

A result file records, per trial, the sha of the instruction bundle the
agent was sent (the same `bundle_sha` a run row carries). `compare` prints
one line per case, `bundle changed` on the ones whose bundle differs between
the two runs, and a last line with passes and cost: `9/12 pass → 11/12 pass;
$0.812 → $0.790`. It exits 1 on a `REGRESSION`: a case the first run passed
and the second failed. `--k` runs every case that many times; a case passes
only when every trial does.

`scripts/regress-nightly.sh` runs the set as `nightly-<date>` and compares
it with the newest `after-*` result. `docs/deploy.md` says how to schedule
it on the Mac.

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
