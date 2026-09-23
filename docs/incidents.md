# Incidents

The history that used to live inside prompts ("on 2026-09-12 a run did X, so
never Y"). Prompts now carry only the principle; the incident lives here,
once, with what now holds it: a regression case in
`backend/evals/regression/`, a code gate, or both. One incident is one
entry, keyed by a fingerprint, however many files it was repeated in.

Run the cases with `uv run python -m hq.cli regress run <label>` and compare
two runs with `regress compare <before> <after>`. A case that passed before
and fails after is a regression, and the change does not ship.

| Fingerprint | When | What happened | Principle | Held by |
|---|---|---|---|---|
| `hung-model-call` | 09-08 to 09-22 | 20 model calls (1%) ran over 20 minutes and took 75% of all model time; runs went silent for 80–103 minutes | Every call is bounded; a hung call hands over to a spare | code: `llm.StreamingModel` wall clock, step limit covers the chain; tests `test_model_calls.py` |
| `gateway-300s-cut` | 09-23 | The article died on `ReadError` at ~304s on all three models: the gateway drops a silent non-streamed request at 300s | Every call is streamed | code: `llm.StreamingModel`; test `test_a_stream_that_breaks_midway_goes_to_the_spare` |
| `single-turn-too-long` | 09-23 | After reading its sources, the tutor's next turn was longer than any model's limit (kimi-k3 480s, sonnet 300s) | A lesson is written in bounded pieces, never in one turn | phase 4 (staged writer); case `tutor-article-paper-day` |
| `opus-27-dollar-page` | 09-22 | One 2B page: 39 calls, 3.1M input tokens, 27 part writes, 2 page-wide refusals, $17.71, then $8.36 to fix two claims; the page taught nothing | Concepts are decided in an outline before prose; a refusal names a part | phase 4; case `tutor-phase-2b` |
| `survey-not-concepts` | 09-20, 09-22 | 2B read as a book of versions and papers; a version table shipped as a concept | Three to five concepts a teacher would pick, each one that survives the next release | code: `lesson_contract`; case `tutor-phase-2b` |
| `constants-undefined` | 09-22 | "18 + 0.12 × 3 = 18.4ms" with 18, 0.12 and 0.03 defined in another document | Name every constant with its unit before the number | case `tutor-phase-2b`, `tutor-article-paper-day` (judge) |
| `forced-article` | 09-12 | A lesson was built from digests that could not support it | No material, no lesson; say what came back | case `tutor-article-thin-material` |
| `welded-topics` | 09-12 | vLLM's scheduler welded to MySQL replication; "I'm not able to connect the both topic" | One topic per piece | code: `select_for_study` |
| `three-wrong-facts` | 09-12 | A metric described wrongly, a safe function called unsafe, a config deprecated in the pinned version | Facts come from the note; the citation pass checks them | code: claims check (citation pass in phase 4) |
| `table-not-summary` | 09-20 | TPOT range given as 15.3–16.2ms; the paper's rows ran to 16.68 | Read the table's rows, not a summary | claims brief; citation pass |
| `guessed-url` | 09-12 | `rubyhack.ai` reached the reading list without ever being fetched | Cite only what was opened | code: leads keep only fetched urls |
| `plain-english` | 09-12, 09-13 | "make the language simpler"; "my first language is not English" | One idea per sentence, plain verbs, no idioms | code: `write_lesson` reading-ease gate; lexicon (phase 3) |
| `empty-page` | 09-13 | A 1,449-word lesson shipped a 284-word page | The page is the lesson | code: `page_shortfall` |
| `dead-selector` | 09-12 | A script queried `.vcells` against `id="vcells"`; half the figure was dead | Script selectors must exist | code: `page_script_problems` (class selectors in phase 4) |
| `senior-titles-sweep` | 09-10 | A sweep spent 285,000 tokens; three of four roles were manager or lead | The title check is the first filter | code: `record_job` closes them; case `hunter-senior-title-is-not-opened` |
| `ats-page-render` | 09-09 | `browser_read` on an Ashby page took 112s and a fifth of the run | A board's answer is not re-read from its page | case `hunter-senior-title-is-not-opened`; code gate in phase 7 |
| `portal-detour` | 09-12, 09-23 | A complete LinkedIn lead was lost chasing the company portal; task `9822e6ac` called `detect_job_board` five times for leads it had | A complete LinkedIn listing is verification | case `hunter-linkedin-lead-is-verification` |
| `sage-polled` | 09-08 | Sage delegated, then polled `read_activity` until judged stalled | A handover is the whole answer | case `sage-handover-is-the-answer`; stall counter (phase 5) |
| `hunter-cannot-read-linkedin` | 09-12 | Private pages were sent to hunter, which cannot open them | A signed-in page goes to operator first | case `sage-private-page-goes-to-operator` |
| `not-what-im-doing` | 09-12 | A draft claimed first-hand work he had not done: "this is not actually what I'm doing" | Borrowed insight is named as reading; ask for his detail | cases `sage-topic-only-content-asks-first`, `scout-no-owner-detail-no-draft` |
| `written-not-spoken` | 09-13 | A post batch averaged 0.4 contractions against his 3.1 | His register is measured and gated in code | register gate (phase 7) |
| `stale-task-line` | 09-12 to 09-16 | "task b3be878b at needs_approval" survived four nights after the task was done | A line naming a task is true only while it is open | case `librarian-closed-task-line-is-dropped`; code in phase 6 |
| `own-account-low-confidence` | 09-10 | Memory said "no content posted yet" while he had 64 posts | His own accounts are first-party evidence | phase 6 (own-account filing) |
| `backfill-burst` | 09-20, 09-22 | After restarts, every missed cron slot ran at once (7 tasks in one second) | Only a schedule's newest slot runs | code: `_make_cron` skip; test `test_a_backfilled_cron_slot_is_skipped` |
| `notification-flood` | 09-07 to 09-23 | 180 of 274 notifications held by the daily cap | One owner-facing voice | phase 5 |
| `stray-lesson-row` | 09-22 | A 2B row filed under the course slug kept the course gate shut | One row per phase | data fixed 09-23; `record_lesson` checks in phase 4 |
