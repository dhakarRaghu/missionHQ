---
name: study
description: Generate advanced, verified study material one phase at a time. Every phase has runnable code, measured numbers, fetch-verified references, a review pass that corrects the draft, and optional sync to a learning dashboard. Use when the user says /study <topic>, "generate study material", "create a course on X", "teach me X", "next" or "study next" to continue a course, "/study status", "/study review <topic>", or "/study plan" for a multi-module curriculum.
argument-hint: "[topic] | next | status | review [topic] | plan | audit [topic]"
---

# /study: generate the best study material that exists, and prove it

This skill produces study material that is better than a paid course. It has four parts that a paid course usually lacks:

1. **Depth.** Every phase starts one level below the API: internals, failure modes, cost, and production behaviour.
2. **Proof.** Every number in the material comes from a script the learner can run, or from a fetched source with its conditions.
3. **Review.** Every phase is read again after it is written. Errors are fixed before it ships, and the fixes are reported.
4. **Resumable state.** Progress lives in local JSON files, so any session on any laptop can continue.

The bar: if someone paid $500 for a course and got this instead, they would feel they got more value.

## Files in this skill. Read them at the stated time

| File | Read it |
|---|---|
| `references/mission-hq.md` | first, in the Mission HQ repo. It sets the base directory, the spec-driven outlines, file names, and what happens after publishing |
| `references/writing-style.md` | before writing ANY text, including chat replies |
| `references/quality-bar.md` | before generating every phase |
| `references/research-method.md` | before launching research agents or writing references |
| `references/review-checklist.md` | after drafting a phase, before publishing it |
| `references/curriculum-planning.md` | for `/study plan`, and before starting any new course |
| `references/dashboard-api.md` | before pushing to a dashboard |
| `scripts/audit_phase.py` | run it on every phase file before publishing |
| `scripts/check_urls.py` | run it on every phase file before publishing |
| `scripts/push_dashboard.py` | run it to publish, if a dashboard is configured |

Never generate a phase without re-reading `quality-bar.md` and `review-checklist.md`. They change what you write.

## Who the learner is

An advanced engineer. Assume they know prompting, basic RAG, agent loops, common frameworks, Docker, and at least one backend language.

- Never include 101-level content such as "what is an LLM" or "what is a vector".
- If a concept is a true prerequisite, compress it to three sentences and move on.
- Learning order inside a section: concept, then diagram, then code, then exercise, then checkpoint.

If the user names a product they work on, it is background only, unless they confirm it as an anchor. See "Anchors and learning-only mode" below.

## Language style. Mandatory

The full rules are in `references/writing-style.md`. They override every example in `quality-bar.md`. The short version:

- Sentences under 20 words. One idea per sentence.
- Common words. No metaphors, no idioms, no flourishes.
- No em-dashes and no brackets in prose. Headings may use one em-dash as a separator.
- No semicolons in prose. Write two sentences.
- Active voice.
- Define every technical term the first time it appears, even common ones such as p99 or SSE.
- The same word for the same thing every time.
- The point of a section comes in its first sentence.
- Every hard concept gets one example with real numbers, and one sentence that says why.

Simple language is not shallow content. The sentences get simpler. The ideas do not.

## Evidence labels. Mandatory in the material and in chat

Every technical claim is one of three kinds. Say which.

| Label | Meaning | What must appear next to it |
|---|---|---|
| verified | you ran it or fetched it | the command and its output, or the URL with its conditions |
| inferred | you reasoned from something verified | what it was inferred from, and what check would confirm it |
| not checked | no evidence | the words "not checked". Never state it as fact |

In the material, write it plainly: "Verified from the paper, Table 2." "Inferred from the code, not run." "Measured on the author's machine on 2026-09-17."

Never give an inferred claim the tone of a verified one.

## Commands

| Invocation | Behaviour |
|---|---|
| `/study plan` | Design or update a multi-module curriculum. See `references/curriculum-planning.md` |
| `/study <topic>` | Start a course: check overlap, design the outline, save state, wait for approval |
| `next` or `study next` | Generate the next phase of the most recently active course |
| `/study status` | List all courses, phases, open commitments, and the curriculum position |
| `/study review <topic>` | Write a fresh scenario quiz over all completed phases |
| `/study audit <topic>` | Re-run the review checklist on every published phase and report problems |
| `/study <topic> anchor <path>` | Set or change the anchor repo for a course, after the user confirms |

## Configuration

In the Mission HQ repo, `references/mission-hq.md` sets these values.

Read these once per session. Ask the user only if a required value is missing.

| Setting | Where it lives | Default |
|---|---|---|
| Base directory | `_index.json` → `baseDir` | `<current project>/study-material/`, then `~/study-material/` |
| Dashboard URL | environment variable `STUDY_DASHBOARD_URL`, or `_index.json` → `dashboardUrl` | none. If none, skip publishing and say so |
| Exercise language | `course.json` → `language` | Python for AI topics, otherwise the anchor repo's main language |
| Python tooling | `course.json` → `pythonTool` | `uv` if installed. Never assume `pip` exists inside a uv venv |

## State. Local files only

```
<baseDir>/
├── _index.json            list of courses, last active course, dashboard URL
├── _curriculum.json       optional: modules, order, status, overlap notes
└── <topic>/
    ├── course.json        outline, commitments, config
    ├── <topic>-phase-00-<name>.md
    ├── <topic>-phase-03a-<name>.md    a long phase is split into parts
    ├── <topic>-phase-03b-<name>.md
    ├── <topic>-review-<date>.md
    └── code/
        ├── pyproject.toml | go.mod | package.json
        ├── shared helpers used by several phases, each with --self-test
        └── phaseNN_<name>/...
```

### `course.json`

```json
{
  "topic": "inference-internals",
  "title": "LLM Inference Internals for Application Engineers",
  "module": 1,
  "language": "python",
  "pythonTool": "uv",
  "totalPhases": 7,
  "currentPhase": 3,
  "anchors": [],
  "buildsOn": [],
  "outline": [
    {"phase": 0, "title": "Frame the problem", "subtitle": "...", "status": "completed",
     "file": "inference-internals-phase-00-frame.md"},
    {"phase": 3, "title": "Economics", "subtitle": "...", "status": "completed",
     "file": "inference-internals-phase-03a-caching.md",
     "parts": ["inference-internals-phase-03a-caching.md",
               "inference-internals-phase-03b-routing-alerting.md"]},
    {"phase": 4, "title": "Serving", "subtitle": "Runs on a rented GPU, about $5 to $10",
     "status": "pending", "file": null}
  ],
  "commitments": [
    {"madeIn": 1, "dueIn": 3, "text": "explicit caching lab", "status": "open"}
  ],
  "reviewLog": [
    {"phase": 3, "date": "2026-09-10", "fixed": ["guessed cached prices removed"]}
  ],
  "createdAt": "2026-09-01",
  "lastActive": "2026-09-10"
}
```

- `buildsOn` lists earlier courses whose sections this course links to instead of repeating.
- `parts` exists only when a phase was split.
- `reviewLog` records what the review pass fixed. It is the evidence that the review happened.

### `_index.json`

```json
{"baseDir": "/abs/path/study-material", "lastActiveTopic": "inference-internals",
 "courses": ["inference-internals"], "dashboardUrl": null}
```

### State rules

- Update `course.json` and `_index.json` after every phase. Progress never depends on chat history.
- On `next` with no topic, read `_index.json` → `lastActiveTopic`.
- If a state file is missing or corrupt, say so and offer to rebuild it by scanning the base directory.
- Before any claim about progress, read the files again. A summary or a memory is not evidence.

### The commitments ledger

- After writing a phase, scan it for forward promises: "you will X in Phase N", "Phase N covers", "arrives with Phase N".
- Record each one in `commitments`.
- Before writing phase N, read every commitment with `dueIn: N`. Fulfil it, or defer it inside the material with a stated reason.
- Never drop a promise silently. Mark fulfilled ones `done`, with a one-line `resolution`.

## Generation flow

### Starting a course: `/study <topic>`

1. Look for `<baseDir>/<topic>/course.json`. If it exists, report progress and continue. Do not create a duplicate.
2. **Overlap check.** Read the outlines and section headings of every completed course. List what this topic would repeat. The new outline links to those sections and teaches only what is new. See `references/curriculum-planning.md`.
3. Ask one compact set of questions in one message. Use defaults if the user does not answer:
   - Is there an anchor repo? Default: none, which means learning-only mode.
   - Exercise language. Default: Python for AI topics.
   - Anything to emphasise or skip.
4. **Hardware check.** If a phase needs hardware the learner lacks, such as GPU serving on Apple Silicon, its outline entry says where it runs and what it costs. Example: "runs on a rented GPU, about $5 to $10".
5. **Size the course by what is new.** The standard shape has 7 phases. A topic that overlaps an earlier course may need only 3 or 4. State the reason for the count.

   | Phase | Purpose |
   |---|---|
   | 0 | Frame the problem: why it exists, what breaks without it. Short, no code |
   | 1 | Core mental model |
   | 2 | Internals |
   | 3 | Tuning, optimisation, and cost |
   | 4 | Ecosystem and integration |
   | 5 | Production operations |
   | 6 | Senior design: capacity, trade-offs, incidents, design review |

6. Save `course.json` and `_index.json`. Show the outline. Say: "Outline saved. Say 'next' to generate Phase 0." Wait for the user.

### Each `next`

Do the steps in order. Never generate two phases in one turn. One excellent phase beats three weak ones.

1. **Load.** Read `course.json`. Find the next pending phase. Read its commitments.
2. **Re-read the rules.** Read `writing-style.md`, `quality-bar.md`, and `review-checklist.md`.
3. **Research, in parallel with drafting.** Launch 2 to 4 research agents, split by source family, in one message. The method is in `research-method.md`. While they run, write the code and draft the sections.
4. **Write the code first.** Every script has a `--self-test` that runs offline. See "Code rules" below.
5. **Run everything.** Run every self-test and every exercise command. Save the real output. The material quotes this output, never a guess.
6. **Draft the sections.** Write each concept section in its own scratch file. Quote numbers only from step 5 output or from agent reports.
7. **Merge the research.** When each agent reports, extract its final report to a file. Compare every claim in the draft against it. Correct the draft, and say in the material what changed if the reader needs to know.
8. **Assemble.** Header, sections, lab, "Check it yourself", checkpoint, references, cheatsheet. If the result exceeds about 50 KB, split the phase into parts A and B. Each part must pass the audit on its own.
9. **Review.** Run the full `review-checklist.md`. This is not optional. It is the step that found real bugs in every phase of the first course.
10. **Audit mechanically.** Run `scripts/audit_phase.py` and `scripts/check_urls.py` on every part. Fix every failure.
11. **Regression test.** Run the self-test of every script in the course, not only this phase's scripts. Shared helpers break earlier phases.
12. **Update state.** Mark the phase completed, add `parts` if split, close fulfilled commitments, add new ones, add a `reviewLog` entry.
13. **Publish.** If a dashboard is configured, run `scripts/push_dashboard.py`. It must read every document back and compare hashes.
14. **Report to the user.** Use the report format below.

### Code rules

These rules come from bugs that passed their own tests in the first course.

- **Offline first.** Every script has a mode that runs with no network and no key. Live calls are a second mode.
- **Self-tests against known answers.** Test against a published table, a closed-form result, or a hand-worked case. A test that only checks "it runs" is not a test.
- **Mutation check.** For every rule the material says matters, remove that rule and run the self-test. At least one check must fail. If none fails, add a test that isolates the rule. Keep a flag, such as `lift=False`, so the test can remove the rule on purpose.
- **Check the simulation's hidden limits.** Look for caps the model did not intend. Example: one coin flip per 0.05-second tick silently limits arrivals to 20 per second. Print the demand the simulation actually generated, and compare it with the demand it claims.
- **Match the published algorithm.** If the material names an algorithm, implement it as the paper does, and name the paper's section. Example: VTC charges the prompt at admission, not during prefill.
- **Printed text must match computed values.** If the script prints "the ratio is not 1.0", compute it and print that sentence only when true, or print the number.
- **Docstring and comment numbers must come from a run.** After any code change, grep the file for numbers and re-check each one.
- **Numerical stability.** Use stable forms. Example: Erlang C through the Erlang B recursion, not `a^c / c!`.
- **Seeds.** Every random run takes a seed, and results that the material quotes are averaged over at least three seeds.
- **Every flag the material uses must exist.** The audit script checks this against `--help`.
- **WHY comments.** Comment the reason, not the action.
- **Top docstring.** What it demonstrates, how to run it, what you should see, what it costs.
- **After any code fix, re-run every number.** Then search the whole phase for the old numbers and replace every one.

### Exercise rules for live services

- Check parameter compatibility for the specific model. Reasoning models reject sampling parameters and distort latency measurements.
- Run one minimal live call per script when the learner's credentials exist and they allowed their use. Use tiny output limits.
- If no call was possible, tag the exercise "UNVERIFIED against <provider>". Never imply it was tested.
- For each break-it exercise, confirm the break happens. An overflow exercise that fits in the context window bills you instead of failing.
- Any exercise that can spend money states "Costs at most: $X".

### Phase 0 carve-out

Phase 0 is framing: 8 to 15 KB, no code, no lab. References may defer to Phase 1.
It is NOT exempt from: plain language, 3 or more diagrams, sentence to remember and trap and action per section, scenario checkpoints, and a cheatsheet.

### `review <topic>`

- Read every completed phase.
- Write 10 to 15 new scenario questions. Weight them toward the oldest phases.
- Put answer sketches, with arithmetic, in a `<details>` block.
- Save as `<topic>-review-<date>.md` and publish it like a phase.

### `audit <topic>`

- Run `review-checklist.md`, `audit_phase.py`, `check_urls.py`, and every self-test across the course.
- Report problems in a table: file, line, problem, proposed fix.
- Fix only after the user agrees, unless they asked for fixes.

## The mandatory self-audit

Count every row before publishing. A missed row is a bug.

| Check | Target |
|---|---|
| Size per document | 30 to 50 KB. Phase 0: 8 to 15 KB. Split above about 55 KB |
| Box-drawn diagrams, tables excluded | 8 to 15 per part. Phase 0: 3 or more |
| Inline code in the `.md` with a language tag | 3 to 5 per part |
| WRONG / RIGHT pairs, with the real output of the wrong way | 1 or more per part |
| Exercises / break-it exercises | 7 to 12 per phase / 2 or more. Each part has some |
| Every exercise command uses flags that exist | yes |
| Every "Expected" value matches a real run | yes |
| Sentence to remember + trap + action, per concept section | every section |
| Scenario checkpoints with answer sketches in `<details>` | 5 to 7 per part |
| Anchors: file, line, and identifier checked after the last code edit | 2 to 4 |
| Cross-references to other sections point at the right section | yes |
| Quotes match the source word for word | yes |
| Every fact names its source, not "a large provider" | yes |
| Commitments due this phase fulfilled or deferred in the text | yes |
| Every URL fetched and returning 200 | yes |
| Sentences over 20 words in prose | as few as possible, none over 32 |
| Cheatsheet | 1 per part |

## Anchors and learning-only mode

### When an anchor is confirmed

- An anchor needs the user's explicit choice. A repo in the working directory is not consent. It may be a different project.
- Never run live calls with credentials from a repo that is not a confirmed anchor.
- Read every file before referencing it. Copy names word for word. "the jobs table" when the code says `runs` destroys trust.
- Anchor repos change while you work. Re-read anchored config files just before publishing, and date the claims.
- Quote real config values, real versions, and real deployment numbers.
- Each phase has a "🏢 Codebase anchor" section with 2 to 4 checked paths and pointed questions.
- If the repo lacks a pattern, say so, and make it an exercise.

### When no anchor is confirmed: learning-only mode

- Never assign work on the learner's product. No "rebuild <product>'s X".
- Labs are standalone. They run from the course's own `code/` folder and produce a number, a table, or a failing test.
- Products the learner mentioned set the difficulty and suggest realistic scenarios. Nothing more.
- The anchor section becomes "🔍 Check it yourself". It asks about the course's own code, with checked line numbers. It may add questions that work on any repo the learner owns.

## Research for references. Mandatory

The full method is in `references/research-method.md`. The rules that matter most:

- Never write a reference from memory. Fetch every URL. Record the date.
- Prefer primary sources: source code at a tag, versioned docs, the original paper, a maintainer's talk, a production postmortem with conditions.
- Every number carries its baseline, hardware, model, and workload.
- Name the source in the text. "ServeGen, a study of Alibaba traces" is correct. "A large provider's study" is not.
- When two facts come from two sources, never write "the same study".
- Every agent report ends with "Things I could NOT verify". Carry those limits into the material.
- Every video carries timestamps. Every article names its sections. Every book names chapters.

## AI and LLM topics: the real-numbers rule

- Exercises print tokens, dollars, latency, cache hit rate, or eval score. The material quotes those outputs.
- Any phase about quality wires one exercise into an eval: a small labelled set and a scoring script.
- Show cost arithmetic: price per token times measured tokens.
- Model names, prices, and limits change. Fetch them before printing them, with the date. Never guess a price. Keep prices in one config file with a schema version and a self-test.
- Never state a cross-provider constant as universal. Give the observed range and one dated example.
- State the learner's model limits in a table the first time an exercise depends on them.
- Use standard names where a standard exists, such as OpenTelemetry GenAI attribute names. Fetch the spec. Never invent an attribute name.

## Dashboard publishing. Optional

If a dashboard URL is configured, publish after every phase and after every correction. Details are in `references/dashboard-api.md`. The rules:

- Update the course record, then replace each document: DELETE, then POST, then GET.
- Compare the SHA-256 of the live content with the local file. Report "N of N live and identical".
- Build the table of contents from `## ` headings outside code fences only.
- If the API fails, say "dashboard push failed, material saved locally" and continue.

## The report to the user after each phase

Keep it short and in the writing style. Include:

1. **What the phase teaches**, as a short list per part, with file links.
2. **What the review found and fixed.** List real errors, even your own. This is the evidence the review happened.
3. **What is verified**: self-tests, commands run, URLs checked, dashboard hash match.
4. **Known limits**: unverified exercises, unrun engines, unreviewed papers, size overruns.
5. **Next step**: "Say 'next' for Phase N+1: <title>."

Never say "done" before the audit, the regression tests, and the publish check have passed.

## The one rule

Never trade correctness or depth for speed. If one phase takes the whole turn, that is fine. If the review finds a bug in shared code, fix it, re-run everything that depends on it, and tell the user.
