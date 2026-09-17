# Write one course phase

Load `teaching` first. Its rules on plain English, the story opening, the
planning ledger, headings, length, facts and labels, the employer, the page
and the diagram all apply here and are not repeated. This file adds what a
course phase needs.

**One phase per run, full attention.** Length follows the material. Covering
less ground to read lighter is the one trade he has ruled out.

## Two kinds of phase, and which one you have

**Phases written with Claude.** The course is written with Claude and the
/study skill. Its markdown is published to his study platform and kept in the
repo under `learning/study-material/`. Most phases are this kind, and the
brief says "Build the enhanced page". Follow "Building the enhanced page",
below. The planning, page and diagram rules in this skill and in `teaching`
all apply.

**Spec phases.** An older path: a spec in `learning/courses/` written up here
from hunter's note. The evening run no longer starts these; a spec phase is
generated with Claude first. The writing sections below remain for revising a
lesson written this way.

## Building the enhanced page

The original stays on the study platform as markdown. **He reads your
version.** It is the same course, all of it, made into the best page he could
learn from: visual, interactive where that teaches, and carrying what hunter
found after the original was written. It is not a summary and not a set of
notes about the original.

**What you keep, always.** Every numbered section, every exercise with its
exact command and expected output, every checkpoint with its answer sketch,
the references, the cheatsheet, and every number with its conditions. The
original was reviewed and its numbers came from real runs: copy commands,
outputs and numbers exactly. `write_lesson` refuses a page that drops a
numbered section, an exercise id, an exact `Run:` command or an answer
sketch, that teaches fewer words than the original, or that links anywhere
the original and the note do not.

**Corrections go in the text.** When the note shows the original is now
wrong (a default that changed, a model or price that moved), fix the sentence
and every number that follows from it, then put a `correction` box right
there saying what the original said, what is true now, and the source. He
must never read a wrong sentence with the fix only in a side box.

**His employer is never named**, even where the original names it. Older
courses do. Replace each mention with the mechanism in general terms ("a
multi-tenant SaaS platform"). A command or file path that contains the name
is rewritten with a neutral name, with one line saying the file is named
differently in his copy of the code. `write_lesson` refuses any page that
still names it.

**What you improve.**

- **Diagrams.** A box-drawing diagram that shows a flow, a timeline, a
  comparison or a ratio becomes a `figure.diagram` with inline SVG, or a
  `.timeline`, `.compare`, `.stats` or `.bars` block. Keep the exact
  `pre.ascii` when a drawing is already clear. Every number in a drawing comes
  from the original.
- **Interactivity, where it teaches.** For the phase's central mechanisms,
  up to one interactive figure per major section: a slider that moves the
  number the section is about, a toggle between the wrong and the right
  state, a stepper through a sequence. The diagram-check rules in `teaching`
  apply to each.
- **Structure.** `p.why` for the "Why this matters" lead, `div.keypoints`
  for the remember / trap / try lines, `.compare` for WRONG and RIGHT,
  `ol.steps` for walkthroughs, `ul.exercises` for the lab, `details.answer`
  for answer sketches, `pre.cheatsheet` for the cheatsheet.
- **Teaching.** Where a paragraph is dense, split it, add the missing step,
  or put a small worked example beside it. Never replace a precise sentence
  with a vaguer one.

**What you add, from the note.** Put each finding inside the section it
belongs to, as `<aside class="addition" data-kind="…">`:

- `update` — a default, version, price or limit that changed: old value,
  new value, version or date, source.
- `correction` — the original is wrong now. Quote its sentence, give the
  current fact and the source.
- `incident` — a real failure on this mechanism: symptom, wrong first
  theory, the signal that found it, the fix, what it changes for him.
- `deeper` — the level below the section, from a primary source the note read.
- `practice` — an exercise the section lacks, only when the note shows it runs.

Every url in an addition comes from the note. Carry its labels: verified,
inferred, not checked. Few and strong: an addition that restates the section
is worse than none.

**How to write it, so it finishes.**

1. `lesson_draft` first; continue after any saved parts.
2. `read_course_source(slug)` for the section list.
3. For each section in order: `read_course_source(slug, section)`, then
   `write_lesson_part(slug, part, html=…)` with the markdown left empty.
   Write the section body only; the kit adds the page around it. Headings are
   `<h2><span class="num">3.1</span> …</h2>`, keeping the section number.
   One section per call.
4. `write_lesson(slug, title=…, subtitle=…, eyebrow=…)`, then
   `record_lesson` with `kind: "course"`.

## A local spec is a contract

The spec block gives you:

```
question:          the one question the phase answers
minutes:           lesson time (the lab runs longer)
assumes:           terms already taught, with the phase that taught them
introduces:        the new terms this phase owns
leaves-for-later:  terms that belong to a later phase
### Why you're here      a situation, then the open question
### Sections             N.1, N.2, ... a title and one line each
### Lab                  what he builds or breaks
### Demonstrate          the measured result that proves mastery
### Test out             Explain / Predict / Demonstrate
```

- **Every `N.x` section appears in the lesson, in spec order, under its own
  number.** Not merged, not reordered, not dropped. If one needs more room,
  give it sub-headings under its own heading.
- **The section list is the coverage contract.** There is no word floor for a
  local spec. Each section is taught in full, with its three passes.
- **`assumes`** is what you may use without teaching. Do not re-explain it: a
  paragraph re-teaching 1.1 is padding in phase 2.
- **`introduces`** is what you must define here, before first use.
- **`leaves-for-later`** is forbidden. Never pre-teach it. If a sentence needs
  it, name it in one clause as arriving later: "retry budgets, which 6.2
  covers, would change this number."
- **A term in none of the three lists** is either known from earlier phases
  (check the note's Sequence block) or a forward reference you invented.
  Define it where you first use it, and report that the spec was missing it.

## Rewriting a platform module (older lessons only)

The evening run no longer asks for this: published phases get additions,
above. It applies only when a brief explicitly asks for a rewrite of a
platform module lesson written before this change.

- **Teach at least as much as the module.** The note opens with the module's
  measured `shape`. Your teaching sections total at least `shape.words`,
  counted the same way: markdown with code fences removed, and not counting
  the checkpoint, cheatsheet, corrections or sources. That is a floor. Near
  the floor means you compressed something; go back and teach it.
- **Every heading in `shape.sections` maps to somewhere in your plan.** A
  module heading with no row is a section you are about to drop.
- **Keep the module's declared shape.** Where the module has labs, keep them
  runnable. Where it says it has no lab ("This phase has no lab and no Go
  code"), it has none. Do not invent a lab, exercises or a Demonstrate block
  the module left out on purpose.
- **Replace employer sections** as `teaching` says. His modules often anchor
  to a former employer's code.
- **Correct the module** where the note shows it is wrong or stale, plainly,
  with the current value and its version.

## Plan it: the ledger plus the coverage map

Use the ledger from `teaching`, with three more columns:

```
covers   which spec N.x or module heading it serves (or: apparatus)
diagram  what the diagram or code block in this section shows
action   the Try this now / Verify / In Mission HQ it ends with
```

Write the one-sentence outcome as something he can DO: predict a number,
name the failure, build the thing. Not "understands X".

Then run the checks on the plan, not the prose:

1. **The ledger.** No forward references, against the spec's `assumes` and
   the note's Sequence block.
2. **The coverage map.** Local: every `N.x` has a row, every `introduces`
   term is introduced somewhere, no `leaves-for-later` term appears. Platform:
   every `shape.sections` heading has a row, and the planned teaching is not
   smaller than `shape.words`.
3. **The shape.** Every section plans a diagram or code block. Every concept
   section plans an action.

## The shape of a phase

In this order. Keep the spec's number in the heading, then the question:
`## 2.3 Why p99 moves before the mean does`.

```
# <Course> Phase <N> — <Title>
_<one line: course, phase, what it assumes, whether it has a lab>_

## Why you are here: <the situation, named>
## What this phase teaches, and what it does not
    the `introduces` list in arrival order; `leaves-for-later` named as later
## <N.1> <the question this section answers>
    three passes, then the closing labels and the action
## <N.2> ...  one per spec section (or module section), in order
## The lab: <what he builds or breaks>
## Exercises
## Where this breaks in production: <the incident, named and dated>
## Demonstrate: <the result that proves you have it>
## Test out
    Explain / Predict / Demonstrate, from the spec, expanded
## Checkpoint <N>
## In Mission HQ
## Things I could not verify
## Cheatsheet — Phase <N>
## Two things you could post
## Sources
```

A phase with no lab has no lab section and no exercises unless its source
lists them. A platform module has no Demonstrate or Test out unless it carries
them.

## Three passes inside every concept

Every concept is taught three times, at increasing depth, in the same
section. Not three sections.

**Pass 1: the mental model.** Three sentences and one diagram: what it is,
what it does, why it exists. He could repeat it to a colleague after one read.

**Pass 2: the details.** Config keys with defaults and versions, byte sizes,
timeouts, edge cases, code. This is the pass usually missing, and the one that
separates a staff engineer's wiki from a tutorial.

**Pass 3: the failure.** What breaks, the exact error message, what it looks
like in logs, metrics and traces, a real incident from the note, and
something small he can run now that makes the failure appear.

Close the concept with these labels, verbatim:

```
The sentence to remember:     one sentence he could write on a card
The trap:                     the wrong belief this concept corrects
Three things to internalize:  (hard concepts only, exactly three)
Try this now:   a command he can run in under five minutes
Verify:         how he checks he got it right, with the expected output
In Mission HQ:  a file in this repo to open, with a question to answer
```

A concept with no action is not finished.

## Depth calibration

The test: could someone running this system at 3am get what they need from
your section? That means exact config keys ("`max_batch_tokens`, 8192 in
v0.11.0", never "the batch size setting"), byte sizes, timeouts, protocol
versions, the error message copied exactly, and the log line, metric and span
that show the failure. Add **why it was built that way**, with the source (a
design doc, a paper's method section, a commit message): the reason is what
makes it stick. All of it comes from the note, per `teaching`.

## Diagrams and tables

**Maximum five paragraphs before the next diagram or code block.** Count them.

Draw with box-drawing characters in fenced code blocks: `┌ ┐ └ ┘ │ ─ ├ ┤ ► ◄`.
Four kinds, each for one job:

- **Architecture**: what sits where, what talks to what, arrow direction.
- **Timeline**: sequences, rows `t=0`, `t=1`, `t=2`, actor on the left.
- **Before / after**: two blocks, same labels, the changed value marked.
- **Comparison table, with real numbers** and their conditions. Never
  high/medium/low. No numbers means no table.

Label parts with real names. On the page these stay in `<pre>` blocks.

## Code

**Production-grade or not in the phase.**

- Runs as written: no missing import, no `// TODO`, no `...` at the hard part.
- A top comment: what it demonstrates, how to run it, what he should see.
- **Wrong first, then right**, with comments on why the first is wrong.
- Real error handling, never `_ = err`. The error path is usually the lesson.
- **Go by default, Python for the applied-AI course**: the spec's `language:`.

## Exercises

**7 to 12 per phase with a lab, numbered E1, E2, ...** They build on each
other: E4 uses what E3 set up. **At least two are break-it exercises**: kill a
process mid-write, corrupt a file, fill a bounded queue, exhaust a pool, hold
a lock. In the lesson, each one reads:

```
E4 — <what he does, in one line>
Kind:        observe | build | break | debug
Run:         the exact command, from inside the exercise directory
Expected:    the output or number, with a range where it varies
If it fails: the likely cause and the check
Teaches:     the one idea this exercise proves
Verified:    auto (runs in the sandbox) | manual (and why)
```

## The lab files

Write runnable lab code with `write_lab_files(slug, files)`. `slug` is the
phase slug. `files` maps relative paths to file contents. Files land in
`learning/labs/<slug>/`. Allowed extensions: `.go .mod .sum .py .txt .md
.json .sql .sh .yaml .yml .toml`. At most 60 files, 200 KB each.

It MUST include `exercises.json`:

```json
{
  "slug": "<phase slug>",
  "language": "go",
  "exercises": [
    {"id": "E1", "title": "one line", "kind": "observe|build|break|debug",
     "cwd": "e01", "run": "go run .", "expect": ["regex that must match the output"],
     "expect_exit": 0, "timeout_s": 60, "verify": "auto"}
  ]
}
```

**`run` is ONE command**, split into words the way a shell splits them, but
with NO shell: no pipes, no `&&`, no redirects, no `$VAR`. The executable must
be `go` or `python3`: `go run .`, `go test -run TestLeak -count=1 .`,
`python3 main.py --requests 1000`. A break-it exercise that kills a process
does it from inside the program: it starts a child (for example, itself
again with a `-child` flag), kills it, then checks what survived.

**Labs run in a sandbox with NO network, not even localhost, and writes are
allowed only inside a temp copy of the lab.** So:

- **Go standard library only.** No third-party modules. `go.mod` has a
  `module` line and a `go` line and no `require` lines.
- **Python standard library only.** No `pip install`.
- **No listening sockets.** `httptest.NewServer` listens on localhost and
  will fail. Call handlers directly with `httptest.NewRecorder`, connect
  in-process with `net.Pipe`, or model the queue with goroutines and
  channels.
- **Write files only under the exercise's own directory, by relative path.**
  Do not assume `/tmp` or the home directory is writable.
- **Make output matchable.** Timing varies, so print a stable marker line
  and match its shape: print `RESULT p99_ms=412 recovered=true`, expect
  `RESULT p99_ms=\d+ recovered=true`. A break-it exercise normally reports
  what broke and still exits 0.

**An exercise that genuinely needs a network service** (a real Postgres,
etcd, a model API, the running Mission HQ API) sets `"verify": "manual"` and
a `"why_manual"` string. It is reported as unverified, never as passed. Where
the spec's lab targets Mission HQ itself, prove the mechanism in auto
exercises on a self-contained program first, then give the Mission HQ run as
manual exercises. Never mark an exercise auto that cannot run in the sandbox.
Do not pretend.

**The lesson and `exercises.json` must match**: the same ids, the same
commands, the same verify mode. The review run checks this.

A phase with no lab and no exercises does not call `write_lab_files`. Say so
in your report.

## Checkpoint questions

Five to seven. Scenario-based, on systems he actually has: Mission HQ, the
course's lab, a system named in the note. **Never "explain X".** At least one
of each:

1. **Walk me through**: "a task is created at 09:00 and the agent never runs.
   Name every place on the path from the row to the runner where it stops."
2. **A colleague says X, why are they wrong**: a specific, confident belief.
3. **Design under constraints**: "one machine, 16 GB, ten minutes. What do
   you give up?"
4. **Debug from symptoms**: what do you look at first, and what does each
   answer rule out?
5. **Show the math**: a number from the phase's formula, inputs given.

Every question is answerable from your article alone. If one needs something
you did not teach, teach it or cut the question.

## Anchors in Mission HQ

Two to four per phase. Each names a **real file in this repo** and asks a
question he answers by reading it. An anchor pointing at a file that does not
hold the mechanism is worse than none. These are verified:

| File | What it is good for |
|---|---|
| `backend/src/hq/engine.py` | the DBOS workflows: an agent run start to finish, timeouts, the scheduled ticks |
| `backend/src/hq/runner.py` | `flush_outbox_step`, `await_runtime_approval`: where a run blocks and why |
| `backend/src/hq/board.py` | the tickets state machine and the notification outbox insert |
| `backend/src/hq/memory.py` | `search()`: FTS and pgvector run concurrently, fused by reciprocal-rank fusion, with a grep fallback |
| `backend/src/hq/tools/registry.py` | the `@hq_tool` decorator: the single choke point for agent capabilities |
| `backend/src/hq/safety.py` | action classes, budgets, HALT, the deterministic guardrail before any approval ticket |
| `backend/src/hq/loader.py` | `validate_trifecta`: why a web reader may not also write trusted files |
| `backend/src/hq/obs.py` | `emit()`: the Postgres event log every run writes into |
| `backend/src/hq/channels/telegram.py` | `drain_outbox`: delivery, retries, idempotency keys |
| `backend/migrations/*.sql` | the schema as it is, including the event log and the outbox |

Pick the files the mechanism lives in, and write the question so reading the
file changes what he believes: "`memory.search()` fuses both halves. What
happens to `rank` when the vector half returns nothing, and would you notice?"

## References

Three good references beat twelve. Each carries:

```
<title and url>
Why:   what this gives you that the phase does not
Focus: the section, chapter or timestamp, as the note records it
When:  before the lab / after the lab / when you hit this in production
```

A timestamp exists only if the note has one; otherwise "the whole talk".

## The cheatsheet

One screen, before the sources, no prose: **what → command or config** (flags,
keys with defaults and versions), **the one formula** with units, **the three
lines he is most likely to get wrong**, and the one diagram worth keeping. If
he has to re-read the phase to find one flag, the cheatsheet failed.

## The lab card

Saturday. He has time at the weekend, and the weekend is for building. The
card is one page he works from, not a page he reads.

- **It is his phase's own lab**, copied exactly: the commands, the expected
  output, the break-it steps. `read_course_source` gives them; never retype a
  command from memory.
- **Order:** what he will have at the end · what must be running first, with
  the command that proves it · the build, as numbered steps with exact
  commands and the output to look for · at least two things to break on
  purpose, with what the failure looks like · the numbers to write down and
  where each comes from · "done when", as a check, not a feeling · one harder
  extension.
- **Tag every step**: offline, live, or "costs at most $X".
- **This week's articles** may add one extra exercise at the end, when one
  showed a failure worth reproducing or a number worth checking. Say which
  article it came from.
- Record it with `kind: "lab"` and the phase slug as `course_slug`.

## The course and the articles are different reading

He reads the course phase and, on weekdays, articles that orbit it. The
same material in both means he reads it twice. So:

- **Your material is the phase's own study note.** Never open the study
  notes behind the daily articles (`list_readings` shows them), and never
  build a section from them.
- **If the brief lists articles he has already read on this phase**, do not
  retell their incidents, numbers or examples. Where the phase touches one,
  one sentence points at it: "the MiniMax article showed this failing in
  production".
- The phase teaches the mechanism once, in order. The articles show it
  failing, measured or applied in real systems. Keep to your half.

## Write it and record it

1. **One section per call, never the whole phase at once.** A phase is too
   long for one answer: a single call that carries all of it runs past the
   model-request time limit and is cancelled with nothing saved.
   - Call `lesson_draft(slug)` first. If parts are already saved, a
     previous attempt was cut off: continue from the next part.
   - Save each section with `write_lesson_part(slug, part, markdown, html)`,
     `part` counting from 1 in reading order. The opening is part 1 and its
     html starts the document: doctype, head, style, opening body. The
     cheatsheet and sources are the last part, and its html closes the
     document. Each part's html is that section in full on the page, with its
     diagram.
   - Then `write_lesson(slug)` with no markdown. It joins the parts and runs
     the page check on the whole. If the page falls short, fix the parts it
     names and call it again.
2. `write_lab_files` with the lab and `exercises.json`, when the phase has a
   lab.
3. `record_lesson` with `kind: "course"` and `course_slug` set to the phase
   slug.

After you finish, a separate review run of tutor, with no memory of writing
the phase, runs the lab and checks it. If it asks for a revision, you receive
its findings and must fix every one.

## Score it, then fix the lowest

Thirteen dimensions, 0-10 each:

1. **One thread**: it answers the phase's question, not five nearby ones.
2. **Not obvious**: it teaches what he could not have guessed.
3. **Concrete**: real code, numbers with conditions, real failure modes.
4. **Usable today**: the actions are doable in the time claimed.
5. **No padding**: score on restatement only. Length is not padding.
6. **The diagram teaches**: mechanism, not outline.
7. **Taught in order**: re-run the ledger on the finished text. Zero forward
   references is 10. Each term used before it is introduced costs 3. A
   `leaves-for-later` term taught here costs 5.
8. **Sectioned to be read**: every heading names its question. A bare number
   or label scores 4 or below.
9. **Coverage**: local, each missing `N.x` costs 3 and each reordered one 2;
   platform, each dropped module heading costs 3, and teaching words under
   `shape.words` caps this at 4.
10. **Every concept ends with its labels and action**: each missing one costs 2.
11. **Diagram density**: each run of more than five paragraphs without a
    diagram or code block costs 2; a high/medium/low table costs 3.
12. **Lab runnable as written**: each auto exercise that could not pass in the
    sandbox (network, third-party module, a shell pipe, a mismatch with the
    lesson) costs 3. Fewer than seven exercises or fewer than two break-it
    exercises caps this at 5. Score 10 for a phase that correctly has no lab.
13. **References only from the note**: one invented link, guessed timestamp
    or promoted could-not-verify claim scores 0, and the phase does not ship.

Pass is 100 of 130, none under 6, dimension 13 at 10. Up to two revise
passes, lowest first. If a pass does not raise the score, stop and say what
the note is missing.

## Revising after review

The brief will carry the review run's findings, one per line: a location, the
problem, the fix expected.

1. **Fix every finding.** Deterministic ones (a failed exercise, a missing
   section, an unsourced url, an incomplete page) are never debated. If the
   note contradicts a judgement finding, quote the note line in your report.
2. **Re-run the ledger and coverage map** if a fix moved or added a section.
3. **Write both again in full**: every part with `write_lesson_part`, then
   `write_lesson(slug)`, then `write_lab_files` with the whole lab, then
   `record_lesson` as before. Call `read_lab(slug)` before
   rewriting the lab: `write_lab_files` replaces the whole folder, so start
   from the files that are there, not from memory.
4. **Report each finding** with what changed: `<location> → <finding> →
   <what you changed>`. A finding you did not fix is reported as not fixed,
   with the reason.

## What to report

In your answer, not in a file:

1. The lesson paths, and the lab path or "no lab".
2. The section plan with the `covers` column, and the coverage map (platform:
   your teaching words against `shape.words`).
3. The ledger result: forward references fixed, any `leaves-for-later` term.
4. The exercises: id, kind, verify mode, `why_manual` for each manual one.
5. The score, all thirteen dimensions, and the weakest.
6. The Mission HQ anchors, with the question asked of each.
7. What the note could not support, and what you left out because of it.
8. If the spec or module was wrong or thin: which part, in one line.
