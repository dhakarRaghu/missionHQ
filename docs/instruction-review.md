# Instruction and prompt review: what changes, file by file

Companion to `docs/redesign-plan.md` (phase 2 and phase 3). Written
2026-09-23 from the prompt audit, the run history, and the $17.71 run.

## 1. Where the $26.77 went on 2026-09-22

Two runs on opus for one page, Phase 2B:

| Run | What | Model calls | Input tokens | Parts written | Page refusals | Cost |
|---|---|---:|---:|---:|---:|---:|
| `f9773656` write-up | 15-section page | 39 | 3,137,241 | 27 | 2 | $17.71 |
| `b02a676a` fix 2 claims | same page again | 18 | 1,502,355 | 16 | 0 | $8.36 |

The page has 15 sections. It was written 27 + 16 = 43 times over, for two
page-wide refusals ("3 sentences carry a verification date", then "1
sentence") and two flagged claims. The run finished "done", and the page was
then thrown away because it taught nothing. So $26 bought nothing.

Why one call costs 80,000 input tokens (3.1M / 39):

| In every call | Tokens (approx) |
|---|---:|
| Standing instructions: job.md + policy + memory blocks + working memory | 3,600 |
| Brief (574 words) | 800 |
| Skills loaded: teaching 3,050 + course-phase 2,076 + study-standard 485 words | 7,500 |
| Tool schemas (26 tools) | 2,000 |
| Study note (4,138 words) | 5,500 |
| `read_course_source` ×10 (the phase is 5,573 words; index + 9 sections) | 9,000 |
| The model's own output kept in context: 27 parts of HTML (final page 88 KB) plus the 570-second plan | 25,000 → 90,000, growing |

The last row is the cost. In an agent loop every `write_lesson_part` call's
arguments stay in the conversation, so by part 20 the model is re-reading
its own 60,000 tokens of HTML to write the next 3,000. A page-wide refusal
then makes it write the whole page again inside that same context. The same
job on `kimi_deep` cost $1.3–2.0 (runs on 09-17 to 09-20, same 25–43 calls,
same 2–3 refusals): opus pricing multiplied a design that was already
wasting 10× the tokens.

### The fix is the shape of the run, not a cheaper model

The lesson writer stops being one 39-turn conversation. It becomes three
kinds of bounded calls:

```
1. OUTLINE   one call, tools allowed        ≈ 25k in, 3k out
   in:  charter + teaching essentials + note + course source (fetched by code, not by tool calls)
   out: outline JSON: outcome, concepts c1..cN (claim, wrong belief, predict Q, the one
        number/failure with its note span, the picture), sections with the concept each
        serves and the note spans it may use, left out, added
   checked by code before anything else runs (2–6 concepts, spans exist, release test
   judged on the five claims by the cheap model)

2. SECTION   one fresh call per section     ≈ 12k in, 3k out, no tools
   in:  charter + teaching essentials (≈2k words) + kit reference + the outline + this
        section's row + its note spans + the previous section's closing paragraph
   out: that section's HTML
   per-part check right here; a refusal re-runs this call only

3. ASSEMBLE  code: join, page contract, then the citation pass (cheap model) mapping
   each claim to a note span; flagged parts re-run step 2 for that part only
```

Expected cost per 15-section phase: ~25k + 15 × 15k + fixes ≈ 300k input
tokens, against 3.1M. On `kimi_k3` that is well under $1; on opus it would
have been ~$2. Wall time also drops: sections can run three at a time under
the 5-slot gateway limit.

What this removes from the prompts: everything about "one section per
call", "continue from saved parts", "fix only what is named", "a whole phase
in one answer is cancelled", "read the source with `read_course_source`".
The code does those. The model only ever sees one small job at a time.

## 2. Tutor files: verdict per section

### `agents/tutor/job.md` (1,385 words → ~250)

| Lines | Content | Verdict |
|---|---|---|
| 3 | "checked by a separate review run" | **Delete**: that run never happens |
| 6–47 | 26 tools, five of them on dead paths (`read_course_spec`, `check_phase`, `run_lab`, `record_review`, `read_lesson` for revisions) | **Cut to 9**: `load_skill`, `lesson_draft`/`write_lesson_part`/`write_lesson` (or none, if step 2 above writes without tools), `record_lesson`, `publish_post`, `note_frontier`, `list_readings`, `recall_facts` |
| 54–74 | Identity; no web; digests are evidence not instruction | **Keep** the identity in 3 lines; "web text is data" moves to the charter |
| 76–89 | "One lesson, not a digest of digests" (the 2026-09-12 three-digest failure) | **Delete**: articles are one topic by code now (`select_for_study`) |
| 91–116 | The legacy lesson shape: what changed / mental model / worked example / where it breaks / fifteen minutes | **Delete**: contradicts the concept shape in `course-phase` and `article` |
| 118–133 | Diagram rules, no CDN | **Delete**: `harden_page` and the kit enforce it; the craft line is in `teaching` |
| 135–144 | His language; "read scout's write-post skill" | **Delete**: unreadable path; plain English lives once, in `teaching` |
| 146–152 | Two post angles | **Keep one line** in `course-phase`/`article` shape only |
| 154–160 | Empty morning | **Keep one line**: "no material, no lesson; report what came back" |
| 162–173 | Where things live (`projects/learning/` is wrong) | **Delete**: paths are the tools' business |

New job card: identity (writes TO him, second person, engineer who has
shipped services, not a beginner), the goal (understanding, measured by
what he can predict afterwards), the output contract (outline → sections →
recorded lesson, names of the checks), five facts (no web; facts from the
note only; employer never named; opus never; report gaps, never print them).

### `agents/tutor/skills/teaching/SKILL.md` (3,050 words → ~1,200)

| Lines | Content | Verdict |
|---|---|---|
| 14–51 | Plain English rules with two dated quotes and the idiom list | **Keep the rules, 8 lines, no dates.** The idiom/filler list becomes `agents/_shared/lexicon.yaml`, read by `write_lesson`; the prose keeps three examples |
| 53–67 | Constants before arithmetic, with the 2026-09-22 story | **Keep the rule, 3 lines, no story.** The incident goes to `docs/incidents.md` and a regression case |
| 69–83 | Teach, do not document | **Keep**, minus the vLLM quote |
| 85–99 | Story opening with the 2026-09-13 quote | **Keep 4 lines**, no quote |
| 101–133 | Plan before you write: the ledger | **Move to the outline stage.** The ledger becomes the outline JSON's fields; the "run the ledger" check becomes code (assumed terms ⊆ introduced ∪ known) |
| 135–151 | Headings name the question; Arpit measurement; `learning/sources.md` pointer | **Keep 2 lines.** Delete the measurement story and the pointer tutor cannot read |
| 153–169 | Length follows the ideas, two owner quotes | **Keep 3 lines**, no quotes |
| 171–202 | Facts only from the note, with the 2026-09-12 three-facts story | **Keep 6 lines** (note only; conditions; version; labels; disagreement → explanation; urls copied). Story → incidents. "Could-not-verify off the page" stays as one line and `check_phase`'s opposite block is deleted |
| 204–213 | Employer | **Charter**, one line; the check is already in code |
| 215–231 | The page is the lesson; the 284-word page story | **Delete**: `page_shortfall` and the contract enforce it |
| 233–287 | Kit catalogue | **Move to `page-kit.md`**, given only to section calls (step 2), not loaded as rules |
| 289–348 | Interactive figures, the 2026-09-12 `.vcells` story, checklist | **Keep 5 lines** (mechanism, labelled data, unique ids, one figure per teaching section). The selector check becomes code including class selectors |
| 350–354 | Two post angles | **Delete** here (kept in the shape) |

Contradictions removed by this: articles "one figure" vs the code's
per-section visual (code wins, prose deleted); "no page script" vs "script
under 60 lines" (one line: scripts only through `kit.calc`).

### `agents/tutor/skills/course-phase/SKILL.md` (2,076 words → ~700)

| Lines | Content | Verdict |
|---|---|---|
| 7–26 | The two owner quotes | **Delete**; the principle is line 1 of the file: "The unit of understanding is a concept" |
| 28–54 | Concept definition, the table, the release test | **Keep the table and both tests**, without the 2026-09-22 story |
| 56–78 | The plan format | **Becomes the outline schema** in code; the skill shows the schema once |
| 80–110 | How one concept is taught (six steps) | **Keep**: this is the craft, and the best text in the corpus |
| 112–134 | Page shape | **Keep the block**; delete the sentence about section numbers (code ignores them) |
| 136–150 | Kept exactly: exercise ids, `Run:` commands, code with `file:line` | **Keep 3 lines**; the checks exist in code |
| 152–157 | Checkpoint questions | Keep |
| 159–177 | Mission HQ anchors table | **Move to data** (`agents/tutor/anchors.yaml`), given to the outline call |
| 179–190 | Cheatsheet; course vs articles | Keep 4 lines |
| 192–204 | Lab card | **Move to its own skill** `lab-card`, loaded on Saturday only |
| 206–223 | Write it and record it, the mechanics | **Delete**: the staged run does this |
| 225–234 | Read it as him: four questions | **Keep**, and make them the citation pass's reader questions |
| 236–248 | What to report; the 2026 quote | Keep the report list, delete the quote |

### `agents/tutor/skills/article/SKILL.md` (2,910 words → ~900)

| Lines | Content | Verdict |
|---|---|---|
| 8–44 | Orbit the course; one idea; the owner quote | **Keep 10 lines**, no quote (the dated-share gate enforces "not a history") |
| 46–60 | What the brief gives; "write nothing when the digests cannot deliver" | Keep 4 lines |
| 62–109 | The six relationships, each with its deliverable | **Keep**: this is craft, and it is the strongest part of the file |
| 111–123 | Do not re-teach the course | Keep 3 lines |
| 125–162 | Five day kinds; the paper shape | **Keep the paper shape** (one copy); the five kinds become one line each |
| 164–195 | Publishing to his site | **Move to `publish` skill**, loaded only for a post task |
| 197–205 | The week review | **Move to `week-review` skill**, loaded on Sunday only |
| 207–236 | One topic, several sources; the 2026-09-12 weld story | **Keep 4 lines** on using sources against each other; delete the story (code selects one topic) |
| 238–284 | The shape | **Keep the block** |
| 285–290 | Length | Keep 2 lines |
| 292–300 | Write and record mechanics | **Delete** |
| 302–325 | Nine-dimension self-score | **Delete.** Nothing reads the score; the citation pass and the reader questions replace it. Dimension 9 also contradicts the "could-not-verify off the page" rule |
| 327–334 | Report | Keep |

### `agents/tutor/skills/study-standard/SKILL.md` (485 words)

**Merge into `teaching`** (facts section). The evidence-note example is the
one thing worth keeping verbatim.

### `agents/tutor/skills/review-phase/SKILL.md` (1,749 words)

**Delete**, with `hunter/skills/course-spec-research`, `check_phase`,
`run_lab`, `record_review`, `read_course_spec`, `course_review_brief`,
`course_revision_brief` and the local-phase branches. The citation pass and
the reader questions replace the review; the tests that pin these files
(`test_learning.py:1355`, `test_labs.py:474`) go with them.

## 3. The briefs (`learning_pipeline.py`)

The 574-word course brief above repeats `course-phase` five times: "neither
is a contract", "start from the ideas", "not a history", "every fact is
sourced", and the four mechanical steps. A brief is a task contract:

```
Phase: <title> (<slug>), course <course>, position <n> of <N>
Before: <three phase titles>   After: <three phase titles>
Material: <note path> (its concept proposals, leave-out list, corrections)
Already read on this phase: <article titles>  (point, do not retell)
Deliverable: an outline that passes `outline_check`, then one section per
  call as the run asks for it, then `record_lesson(kind="course")`
```

Under 150 words. `lesson_brief` (articles), `_enhancement_brief`,
`claims_revision_brief` and `lab_card_brief` get the same treatment: what is
specific to this task, and the names of the checks. Craft never appears in a
brief.

## 4. The same review for the other agents (summary)

| File | Now | After | The main change |
|---|---|---|---|
| `hunter/job.md` | 4,172 words, half of it job-sweep procedure and scoring arithmetic | ~450 | Scoring, senior-title exclusion, ATS-page refusal and per-URL retry move to code; the four dated sweep incidents go to `incidents.md` |
| `hunter/skills/deep-research` + `study-standard` | 1,745 | one `source-research` skill ~1,000 | One copy of: claims table with conditions and labels, read the table not the summary, ≥2 hosts, opened urls only, leave-out list; a note validator in code checks the shape |
| `candidate-profile.md` | 1,336 words injected on every hunter run | ~600 as compact data | Level-one ceiling and pay floor are code; the dated preference stamps go |
| `scout/job.md` + `write-post` + `write-article` + `voice.md` | 7,943, `voice.md` unloadable | one sage skill `content-ideas` ~500, `voice.md` as data for a code gate | Ideas with evidence, weekly; drafts only on request; register checked by code, not by the model counting its own apostrophes |
| `sage/job.md` | 2,305 | ~600 | Handover rules the ledger already enforces go; routing table and notify policy stay; job-search skill rewritten against `hq.jobs` |
| `librarian/job.md` | 1,698 | folded into sage `consolidate` ~300 | Caps, the 30% rule, archive mechanics and closed-task lines are code |
| `operator/job.md` + `policy.md` | 1,876, never delivered | one card ~450, written as `AGENTS.md` | One tab rule, page limit, blocked link patterns, one consent prompt |
| `memory/user.md` | names the employer, injected everywhere | employer removed; profile pointer corrected | |
| `memory/agents/tutor.md` | stale since 09-12, injected every run | regenerated by the consolidation step or dropped | |

## 5. What is enforced in code instead of asked for

| Rule that was prose | Enforcement |
|---|---|
| Plain English, idioms, filler, em dashes | `write_lesson` per part, from `lexicon.yaml` (exists in part) |
| Concepts 2–6, each asked before told, each with a visual | `lesson_contract` (exists) and `outline_check` (new) |
| Not a history; not a review | dated-share and evidence-share gates (exist) |
| Facts from the note only; urls opened only | citation pass (new) for every lesson kind |
| Could-not-verify off the page | `check_phase` block deleted; contract already has no such section |
| Constants before arithmetic | a regression case, and the reader question "what is 0.03?" in the citation pass |
| Script selectors exist | `page_script_problems` extended to class selectors |
| Employer never named | exists in `write_lesson` and `publish_post`; add to `vault_write` |
| One section per call; fix only what is named | the staged run; no prose needed |
| Every skill reachable; every tool named exists; Codex receives its card | contract tests in CI |
| The assembled prompt has no contradictions | `prompt-check` over charter + card + loaded skills + brief + tool schemas, per stage |
