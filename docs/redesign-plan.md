# Mission HQ, rebuilt from the ground (v2)

Status: proposal, 2026-09-23. Nothing is built. Supersedes v1 of the same
day; the changes from v1 are listed in §0.

Sources: five first-round reviews (structure, 16 days of run history, the
prompt audit, comparable systems, tonight's failed run) and five
second-round reviews that traced the effects of every proposed change
through the code and researched how the strongest current platforms are
built. They are in the repo:

- `docs/reviews/effects-runtime.md`: phases 1 and 4 traced through
  `llm.py`, `engine.py`, `runner.py`, DBOS and pydantic-ai internals
- `docs/reviews/effects-instructions.md`: the loader, crons, tool sets,
  Codex delivery, memory, tests, frontend
- `docs/reviews/effects-learning-jobs.md`: learning pipeline, reader, jobs,
  content, quarantine, operator, with live DB counts
- `docs/reviews/research-platforms.md`: Grok Bot, squad.so, OpenAI,
  Anthropic, LangGraph, Temporal, DBOS, Letta, Magentic-One, OpenClaw,
  Devin, Manus, Hermes, 12-factor; ten decisions and where v1 was wrong
- `docs/instruction-review.md` (tutor) and `docs/instruction-review-part2.md`
  (everyone else): line-level verdicts, brief replacements, draft cards
- `docs/rule-ledger.md`: every rule and incident, and where it goes

## 0. What changed from v1, and why

| v1 said | Evidence | v2 |
|---|---|---|
| One attempt per model; fall back on any error | Rate limits are waited out; context overflow must never fall back to a smaller model; only timeouts and server errors move to the spare (OpenClaw failover; pydantic's `FallbackModel` fires on every 4xx/5xx) | Errors are classified before anything else (§6.1) |
| A process semaphore and two lanes | A semaphore resets on restart and cannot prioritise; there are three queues today (`tasks`, `courses`, `chat`), not one; a streamed response must hold its slot until the body closes | Admission at the transport tied to stream close, and DBOS queues for scheduling with priority and dedup (§6.2) |
| Catch-up creates every missed slot | `_catch_up_missed` already takes the newest slot; the burst is DBOS's own backfill in `fire` | Skip older backfilled slots in `fire`; no backfill; auto-pause after two failures (§6.3) |
| Approval waits need a timeout because they hold a lane | Platforms let runs park; but DBOS cancels a workflow at its deadline even while it waits in `recv` (verified) | Short waits bounded below the cap; long human waits get an approval-first workflow that dispatches the run (§6.5) |
| Evals are phase 8 | Anthropic and OpenAI put eval fixtures before prompt changes | Regression set and rule ledger are phase 1 (§11) |
| Librarian becomes a sage skill | Skills run inside the calling session and accumulate context; Letta and OpenClaw run consolidation isolated | Sage keeps the identity; consolidation is its own scheduled, isolated workflow (§4) |
| Consolidation: code + model judgement, diff reviewed next morning | OpenClaw and Managed Agents: the model emits operations, code applies them under a loss cap into a candidate that never replaces live memory until promoted | Operations → candidate → owner promotes (§7) |
| Stall → LLM judge verdict | Magentic-One: stall → replan with cleared context, at most 2 resets, then a best-effort report | Stall → replan, bounded (§6.4) |
| Word targets per run | The strong systems enforce in tokens at load time | Token budget enforced in `loader.py`; bundle SHA recorded per run (§5) |
| `kimi_k3` has no price; job statuses missing | Price exists (`models.yaml:104`); `applied/interviewing/offer` exist in code | Dropped; what is missing is sage's read access and the console action |
| Streaming "fixes" the 300s cut | Under streaming, a mid-stream `ReadError` is a raw httpx error and the chain does **not** fall back unless it is re-raised as `ModelAPIError`; httpx read timeouts reset per byte, so a per-attempt wall clock is needed; usage on streams verified for kimi-k3, kimi and sonnet | The streaming wrapper does all three (§6.1) |
| Tutor's per-article `notify_owner` is the noise | The engine's cron completion card (`engine.py:526-546`) is the largest source of held notifications and is not an agent | The card goes; only sage notifies (§6.6) |

## 1. What the platform is for

Four things, in the order you use them:

1. **Learning.** One course phase at a time plus a weekday article that
   orbits it, written as a teacher who knows the field and picks the
   concepts worth knowing. Read on the laptop or the phone.
2. **Job search.** Level-one roles, India or India-remote, 25 LPA or more,
   verified at the source, with a person to reach. You apply; nothing
   applies for you.
3. **Content.** Ideas anchored in what you actually did, in your register.
   Nothing posted for you.
4. **A memory of you** that every run reads: who you are, what you decided,
   what is open.

The kill metric stays: **a value week**. Today the platform produces far
more than you consume (11 lessons, 67 leads, ~32 content appends, 14 daily
notes in 16 days; 8 lesson reads, 0 applications, 0 posts). v2 optimises
for use, not output, and measures it (§10).

## 2. What is actually wrong

| Symptom | Root cause |
|---|---|
| 1% of model calls (20 hung requests) ate 75% of model time and blocked lanes for whole evenings | No per-call boundary; the fixes in `2e843a3` bound them, but there is still no per-attempt record and no admission control |
| Tonight's article died twice with `ReadError` at ~304s on all three models | The gateway closes idle non-streaming connections at 300s (probe: 303s failed, 377s streamed OK) |
| One 2B page cost $26 across two opus runs and was thrown away | 39-turn agent loop re-sending its own HTML (80k tokens a call), page-wide refusals, whole-page rewrites, opus pricing |
| Lessons that taught nothing | No artifact where concepts are decided before prose; the fix went into prose, and prose is advisory |
| Rules dropped, contradictions, dead text | 35,900 words; 8,600–15,000 per tutor run; 82 dated incidents; 27 contradictions; ~6,150 words unreachable, including operator's whole `job.md` (never sent to Codex) |
| The ledger judge: 91.5% "satisfied", one 3.6h hang | A model call per turn for stalls detectable in code |
| Sage burns four model runs a day to make one tool call each | Crons written as prompts for dispatches that need no model |
| The roster merge has never completed; the course review has never run | Tutor cannot write `learning/sources.md`; the review dispatch sits after a `return` |
| 66% of notifications held | The engine's cron completion card, plus two notifying agents |
| Job pipeline stops at "referral" | Sage cannot read `hq.jobs`; no shortlist; exhausted sweeps repeat (7 zero-result YC-India runs); the fit score lives in prose the code contradicts |
| Operator 30% no-output | Extension signed out; own-account reads have no URL and are not filed; its instructions never reach Codex |
| Costs invisible where wasted | Abandoned/failed runs record $0; fallback answers billed at the primary's price; Codex $0 |
| ~110 restarts; evening bursts | DBOS backfills every missed slot on restart |
| The course gate is shut right now | A stray `hq.lessons` row (`485e5953`, `course_slug='inference-internals'`) duplicates 2B unread |

## 3. Design rules

1. **Enforcement in code, judgement in the model.** "Never" and "always
   before" become tool constraints, gates or tests. Prompts carry identity,
   goal, contract and craft.
2. **One home per rule.** Charter, card, skill, code, data or test. Never
   two.
3. **Incidents become tests.** `docs/incidents.md` keeps the history; each
   entry has a fingerprint and a regression case.
4. **Fixed artifacts between stages**, each checked by code before the next
   stage runs; a refusal names the part.
5. **Every model call is bounded, classified and recorded.** Streamed, one
   wall-clock per attempt, error class decides wait / fallback / shrink, one
   row per attempt.
6. **Fresh context per scheduled run.** A run gets the charter, its card,
   the one skill its stage needs, its brief and the last run's record. Never
   a stale notebook, never its own earlier output re-sent.
7. **Independent, isolated, read-mostly runs.** Roles exist for isolation
   and tool scope. Agents do not talk to each other; they write to the store
   and the board.
8. **Approval never reverses; ask-first wins.** Every tool declares an
   effect; outward effects wait; a parked run costs nothing.
9. **The owner's decisions live in one file** (`memory/decisions.md`). No
   rule pre-empts an open decision.
10. **Output is throttled by consumption.** Unread, unactioned or unused
    above a threshold turns the next run into triage.

## 4. The roster

| Today | v2 | Notes |
|---|---|---|
| sage | **sage**: chat, `daily-note`, `weekly-review`, `job-shortlist`, `content-ideas`, `new-agent`, `weekly-plan`. The only holder of `notify_owner`. Gains `list_jobs`, `list_lessons`, `read_lesson`, `retire_fact` | Its four "call one tool and stop" crons become direct dispatches from code |
| librarian | **retired.** Consolidation is a scheduled, isolated workflow (`memory.consolidate`) under sage's identity: code proposes operations, one model call judges, the result is a candidate you promote | Not a chat-loop skill (context accumulation); retire with deletion or `status: draft`, never `paused` (a paused agent's crons still fire) |
| hunter | **hunter**: research only. `job-research`, `source-research` (merges deep-research, study-standard, the claims method). Sweep procedure, rotation, fit score and exclusions move to code | Keeps `job_board` for verification; drops `social_lookup`, `read_board` (never used) |
| tutor | **tutor**: `teaching` (≤1,400 words), `course-phase`, `article`, `publish`, `lab-card`, `week-review`. Writes through the staged writer (§8), not a 39-turn loop | Tools cut from 26 to ~9; five were on dead paths |
| scout | **retired.** Content becomes sage's weekly `content-ideas`: 3–5 ideas, each with the experience or number it hinges on; drafts only on request, under a register gate in code | Its own-X-numbers operator read has no code path today; the engine dispatches it weekly |
| operator | **operator**: the most restricted. One contract delivered as `AGENTS.md` in a dedicated `--cd` directory (not the vault); the browse guard reads the same text; `no_artifact` becomes an outcome; Codex is costed | Today its card is never sent and contradicts its policy |

Model policy: `kimi_k3` (reasoning high) for the outline and section
calls and for study notes; `kimi` elsewhere; judges on `cheap`; opus never.

## 5. Instructions

```
agents/_shared/charter.md      ≤300 words, every agent (draft in instruction-review-part2 §12)
agents/_shared/voice.yaml      his measured register; read by the register gate and content briefs
agents/_shared/lexicon.yaml    idioms, filler, AI tells; read by write_lesson and the gate
agents/_shared/owner.yaml      handles, accounts, pillars
agents/<name>/job.md           ≤200 lines: identity, goal, output contract, 5–10 facts (drafts in part2 §10)
agents/<name>/skills/*/SKILL.md ≤500 lines, no dates, one loaded per stage, injected by the brief builder
agents/hunter/profile.yaml, title_variants.yaml; agents/tutor/anchors.yaml, page-kit.md
memory/decisions.md            owner-only; injected as a block; read by code (fit score, sweep filters)
docs/incidents.md              the history, fingerprinted, each → a test
backend/evals/<agent>.yaml     the regression set
```

- Briefs are task contracts ≤150 words generated by code (replacements
  written in part2 §7): deliverable, inputs, named checks, envelope. A brief
  names one skill and the pipeline injects it; no `load_skill` round trips.
- `loader.py` assembles the bundle in a fixed order (charter → card → skill
  → memory blocks → brief) so the stable prefix caches, enforces a token
  budget per run, and records the bundle SHA on `hq.runs`.
- `prompt-check` audits what a stage actually sends, not the files on disk.
- Contract tests in CI: every skill reachable from a brief; every tool a
  prompt names is held; Codex receives its card; only sage holds
  `notify_owner`; the set of `(agent, schedule)` crons equals the intended
  table; no contradictions per stage; bundle under budget.
- Deleted: `review-phase`, `course-spec-research`, `voice.md` at its path,
  scout's and librarian's manifests, `operator/policy.md` (merged), every
  empty `policy.md`, the local-phase branches, `course_review_brief`,
  `course_revision_brief`, `roster_merge_brief` as a model task, every
  self-score rubric, every "write it and record it" block, the prose-pinning
  tests (listed in the ledger §5).

Targets: hunter sweep ~3,000 words; hunter scan ~4,500; tutor outline call
~4,500 and section calls ~2,500; sage chat ~2,500. Enforced in tokens.

## 6. Reliability

### 6.1 The model-call layer (`llm.py`)

A `StreamingModel` wrapper inserted in `_build_one`, below `FallbackModel`
and `DBOSModel`, so judges, the reader and every agent get it and the DBOS
step boundary (one step = one chain) is unchanged:

- `request()` opens `request_stream()`, consumes it, returns
  `StreamedResponse.get()`; usage from the final chunk (`include_usage`).
- **Mid-stream errors are re-raised as `ModelAPIError`** so the chain
  falls back (pydantic's `request_stream` only falls back on errors while
  opening the stream; mid-stream failures propagate raw).
- A wall clock per attempt (`asyncio.timeout(timeout_s)`), because httpx
  read timeouts reset per byte.
- **Error classes**: 429 → wait for a slot (exists in the transport);
  timeout / 5xx / connection → next model; context overflow → never fall
  back, shrink the input and retry once; anything else → fail the attempt.
- A `hq.model_calls` row per attempt: run, agent, registry model, wire
  model, ms, tokens, cost priced by the **answering** model, error class,
  `usage_source` (`reported|estimated`). Run cost is the sum of its rows,
  so abandoned and failed runs are costed; `spend_today_usd` reads the
  rows and counts in-flight spend.
- Verified 2026-09-23: the gateway sends the usage chunk on streams for
  kimi-k3, kimi and sonnet (sonnet also reports cache read/write tokens),
  so streaming keeps cost accounting. Keep the estimate path as a guard.
- Codex costed from its own token counts with a `codex` price entry.

### 6.2 Admission and scheduling (`llm.py`, `engine.py`)

- **Admission**: one module-level limit of 5 on the gateway key, acquired
  in the transport and released when the streamed body closes (not when
  headers return). Verified: `DBOS.launch()` runs in the FastAPI lifespan
  and adopts the uvicorn loop, so workflows, chat and judges share one loop
  and an `asyncio.Semaphore` is correct. Consider 4 shared + 1
  reserved for chat.
- **Scheduling**: DBOS queues with `worker_concurrency` 2 for `tasks`,
  `priority` (chat above nightly work), `deduplication_id = cron:slot` so a
  restart cannot enqueue a slot twice. Keep the `courses` queue and
  `COURSE_TIMEOUT_S` until the staged writer replaces course runs, then
  delete both.

### 6.3 Crons (`engine.py`)

- In `fire`, skip any slot older than the newest for that entry
  (`cron.skipped_backfill`); no backfill.
- `hq.crons`: `consecutive_failures`, `paused_reason`, `last_slot`. Pause
  after two consecutive failures; one notification, not one per failure.
  After a week of owner inactivity, ask whether to keep routines running.
- Crons that exist to make one tool call are direct dispatches.
- Cron keys are list indices: append entries, never reorder within 12h of
  a run.

### 6.4 Stalls (`registry.py`, `runner.py`)

- In `_audited`: a per-run counter of `(tool, sha(args))`; second identical
  call returns a tool result saying so; third raises `StallDetected`.
  Calls-since-last-artifact and spend-with-no-artifact-delta (from
  `model_calls`) are the other two signals. Counters are seeded from
  `hq.events` on recovery.
- On stall: one bounded model call that returns a **new plan**, the context
  is cleared to charter + card + skill + plan, at most two resets, then the
  run ends with a report. The per-turn ledger call goes; `exit_status`
  keeps the `stalled:` prefix; the `ledger` event stays for the frontend
  with `via: stall`.

### 6.5 Gates and approvals (`registry.py`, `runner.py`)

- Every tool declares `effect: read | reversible | outward` (a table in
  `registry.py`). `read` never reaches approval; `reversible` is
  auto-approved without a model; `outward` gets the deterministic check,
  then the LLM guard, then you. Ask-first wins.
- The browse guard's "bounded" test becomes deterministic (named origins,
  URL count from the brief); the model only decides the residue.
- Verified: a parked workflow is **not** exempt. `_schedule_workflow_timeout`
  cancels at the deadline whatever the workflow is doing, so an approval
  wait longer than the 40-minute task cap kills the run today. Approval
  waits are bounded below the cap (e.g. 30 min); on expiry the call is
  denied and the run continues, or ends if the tool is marked
  end-on-timeout. Long human waits (operator runs) get their own
  approval-first workflow with no model steps and a 24h cap, which then
  dispatches the capped run once approved.
- Per-agent daily caps on outward actions; per-run budget from the task
  kind checked between model calls (`UsageLimits` incl. `cost_limit`).

### 6.6 Notifications

- Only sage holds `notify_owner`; tutor's per-article notify becomes a
  `note.line` event that the daily note reads. The engine's cron completion
  card is removed (the digest and the note cover it), kept only for
  failures and `no_artifact`.
- Injection detector: allow-list documentation hosts (19 of 19 hits were
  false positives).

## 7. Memory

- Blocks: `user.md` (employer removed), `decisions.md` (owner-only),
  `active_projects.md`, each ≤4k chars, selected per agent through a
  `memory:` manifest field. Blocks are read-only for every run except
  consolidation. Working notebooks (`memory/agents/*.md`) are dropped; the
  last run's record goes in the brief.
- `memory.consolidate` (scheduled, isolated): code gathers the day's
  changed notes and the board, drops lines naming closed tasks, expires
  facts (`valid_until`), proposes a diff; one model call returns keep/drop
  operations; code applies them under a loss cap (≤25% of prior lines)
  into a **candidate**; you promote it from the console. Nothing replaces
  live memory unattended.
- Quarantine: promote/drop actions in the console (move + reindex +
  ledger entry). Your own account data (X, LinkedIn metrics via operator)
  is filed by the engine to `projects/content/metrics/` with provenance
  `owner-account`, even without a source URL.
- `vault_write` refuses the employer's name; the literal in
  `discovery_brief` reads `settings.private_employers`.
- Vault commits once a day (done).

## 8. Learning pipeline

```
hunter: research note ──► note_check (code) ──► tutor: OUTLINE (one call, kimi_k3)
   claims table, spans,     headings, labels,        outcome · c1..cN (claim, wrong belief,
   leave-out, ≥2 hosts,     urls opened, hosts,      predict Q, one number/failure + span,
   dated urls               confidence               picture) · sections · left out · added
──► outline_check (code) + release-test judge on the claims (cheap) ──► stored in hq.lesson_outlines
──► SECTION calls, one fresh no-tool agent run per section (charter + teaching essentials +
    page-kit + outline + this row + its spans + terms already introduced), UsageLimits
    request_limit=1, per-part check → re-run that section only, ≤2 retries
──► assemble (code): page contract, script check, wrap ──► citation pass (cheap, no tools):
    each claim ↔ a note span; unmapped → re-run the owning section with "remove or source"
──► record ──► export to the phone ──► "got it / lost me" per concept ──► next outline reads it
```

- Implemented as pre-launch, DBOS-durable no-tool agents called in the
  workflow body: each request is its own checkpointed step; a restart
  resumes at section k+1. Sequential first; parallel sections later if
  the 5-slot limit leaves room.
- `write_lesson` and `record_lesson` bodies are extracted into plain
  functions the workflow calls; the tools wrap them for ad-hoc runs. A
  synthetic `tool.called {record_lesson}` keeps the artifact assertion.
- Page-wide refusals (concept count, repeated sentences) map to "re-run the
  outline" once, never to every part.
- The citation pass replaces hunter's `claims_check` and the dead
  `course_review`; articles, lab cards and week reviews get it too (today
  articles get no fact check). `review_status` vocabulary becomes
  `pending | clean | revise`; the teach gate keeps blocking on `revise`.
- Cost target: a 15-section phase ≈ 25k + 15 × 15k input tokens (~300k,
  against 3.1M), under $1 on kimi_k3; an article under $0.50.
- Reader signal: the kit posts `{concept, verdict}` to the parent page;
  the outer `/read` page keeps it in its own `localStorage` and the console
  writes it to `hq.concept_signals`; a small authenticated POST over the
  tailnet is the upgrade if you are always on it. No secret goes to Vercel.
- Nightly `export-reader` after reindex; commit and push **only the reader
  bundle, only when the lesson set changed, on a `reader` branch that
  Vercel deploys from**, so `main` and your uncommitted work are never
  touched (decision 4).
- Data hygiene first: delete the stray `485e5953` row, clear the two
  `.drafts` folders, backfill `review_status` on the 7 course rows.

## 9. Jobs

- The sweep is code: rotation state in `hq.job_sweeps`, board APIs,
  dedupe against the ledger, back-off after three zero-result runs,
  senior / level-2 / intern titles never returned, `private_employers`
  skipped. The model writes the person brief and the note for fit ≥ 6.
- `fit_score()` from structured fields (`lane`, `pay_lakh` parsed from
  compensation, years, stack overlap with `profile.yaml`, domain from the
  company brief) stored as `fit_parts jsonb`, plus a bounded model
  adjustment with its reason. `record_job` requires pay and band for fit
  ≥ 6.
- Statuses exist (`seen, shortlisted, referral, applied, interviewing,
  offer, rejected, closed`); the console gets the actions and sage gets
  `list_jobs`. `job-shortlist` writes five rows with a next action each.
- Verification standard, one line: a `job_board` record or a complete
  primary listing is verification; a search title is not.
- Open decisions (Jobgether, founding titles, relocation) are read from
  `decisions.md`, not hard-coded.

## 10. Content, observability, evals

- `content-ideas` weekly under sage; register gate on
  `projects/content/**` writes from `voice.yaml`; never auto-post.
- `hq.model_calls`, bundle SHA per run, cost on every outcome, Codex
  costed; a weekly value report (reads, taps, leads acted on, ideas used,
  cost per lesson) drives the throttle rule; a one-line morning summary
  ("N done overnight, nothing sent without you").
- `backend/evals/`: 20–50 cases per role from real failed runs, graders in
  a fresh context, code graders first, failures fingerprinted so one
  incident is one case. Runs in CI on every prompt change.

## 11. Build order

Each phase ships whole, with its tests, verified on a real run before the
next. Blast radius is from the effect reviews.

| # | Phase | Delivers | Verified by | Blast |
|---|---|---|---|---|
| 0 | **Data hygiene** | stray lesson row, `.drafts`, pending vault writes | course gate opens | none |
| 1 | **Ledger and baseline** | you approve `docs/rule-ledger.md`; freeze current prompts; 20 regression cases per role from real runs with graders; `docs/incidents.md` | the set runs green on today's prompts, red on the known failures | new files only |
| 2 | **Model-call layer** | streaming wrapper, error classes, per-attempt wall clock, admission tied to stream close, `hq.model_calls`, cost by responder, Codex cost, cron `fire` skip, `tasks` concurrency 2 | tonight's article completes; no `ReadError` for a week; usage non-zero on kimi-k3 | `llm.py`, `engine.py`, `runner.py`, `safety.py`, `rest.py`, one migration, ~3 tests changed, ~12 added |
| 3 | **Instruction architecture** | charter, data files, cards and skills at the caps, briefs as contracts injected by code, `_shared` loading, per-agent blocks, bundle SHA and token budget, `prompt-check` per stage, contract tests, dead text and dead tools removed, sage's tool-call crons → dispatches | per-run tokens at target; contract tests green; the regression set passes everything it passed before plus the targeted failures; shadow week (§11a) | `loader.py`, `promptcheck.py`, `memory.py`, all of `agents/`, ~30 tests replaced, frontend static text |
| 4 | **Staged writer** | outline table and check, section calls, assemble, citation pass for every kind, review vocabulary, delete the review path and `courses` lane, tutor tools cut | Phase 3A and three articles under the cost target, read by you with taps | ~10 backend files, 2 frontend, 1 migration, ~22 tests |
| 5 | **Stalls, gates, notifications** | stall counter and replan, effect table, deterministic browse test, parked approvals, sage-only notify, cron card removed, injection allow-list | ledger model calls → 0 except on stall; held notifications < 20% | `registry.py`, `runner.py`, `engine.py`, `board_tools.py`, `digest.py`, 1 test changed, ~11 added |
| 6 | **Memory** | `decisions.md`, read-only blocks, consolidation workflow with candidate + promote, quarantine promote/drop, own-account filing, employer removed from memory | a week of candidates you promote | `memory.py`, `api/vault.py`, console pages |
| 7 | **Jobs and content** | sweep in code, `fit_score`, back-off, console status actions, `job-shortlist`, `content-ideas`, register gate, scout and librarian folders retired | a shortlist you act on; an idea you use | `job_tools.py`, `job_pipeline.py`, one migration, jobs UI |
| 8 | **Operator** | `AGENTS.md` via dedicated `--cd`, guard reads the contract, `no_artifact` outcome, consent ticket lists pages | a LinkedIn discovery run whose transcript shows the contract | `runner.py`, `codex_cli.py`, `engine.py` |
| 9 | **Reader and value loop** | taps, `hq.concept_signals`, nightly export on the `reader` branch, weekly value report, morning summary, throttle | new content on the phone by morning; the report drives one decision | `reader_export.py`, `lesson_kit.py`, `/read`, a cron |

Phases 0–2 are about two sessions; 3 and 4 are the largest; 5–9 one each.
Phase 2 starts as soon as you approve, because the article cannot land
without it, and it changes no prompt.

## 11a. The guarantee: no agent gets worse

1. **Rule ledger first** (`docs/rule-ledger.md`): every rule has a
   destination or it is not deleted. You approve it before any prompt is
   edited.
2. **Baseline before change**: freeze the current prompts; 20–50 real tasks
   per role with deterministic graders where possible and a cheap-model
   judge only for "does it teach", calibrated on the lessons you already
   judged.
3. **Old vs new on the same tasks**: new prompts ship only when they pass
   everything the old ones passed plus the failures they were written to
   fix. Cost per run is part of the score.
4. **Shadow week**: the new tutor writes Phase 3A and three articles you
   read on the phone; the new sage writes the daily note beside the old
   one for seven days. The switch is your verdict.
5. **One role per commit, rollback in one edit**; contract tests in CI on
   every prompt change.
6. **Weekly value report**; two weeks of decline reopens the role's design.

## 12. Decisions for you

1. Retire scout; content becomes sage's weekly ideas skill, drafts only on
   request?
2. Retire librarian; consolidation as an isolated scheduled workflow that
   produces a candidate you promote (nothing replaces live memory
   unattended)?
3. Replace the never-run course review with the citation pass and delete
   `review-phase`, `course-spec-research`, `check_phase`, `run_lab`,
   `record_review`?
4. Nightly export of the reader bundle committed and pushed on a `reader`
   branch (never `main`), only when the lesson set changed?
5. Only sage notifies; the engine's cron completion card is removed except
   for failures?
6. Reader taps: start with the phone keeping them locally and the console
   recording them, or add a small authenticated POST over the tailnet?
7. Sage's four tool-call crons become direct dispatches (no model run)?
8. Approve `docs/rule-ledger.md` as the destination map for every rule.
