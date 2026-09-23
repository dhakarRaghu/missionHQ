# Teach one course phase

Load `teaching` first. Its rules on plain English, the story opening, order,
headings, facts, the employer, the page and the figures all apply here and are
not repeated. This file is what a course phase adds.

## What he asked for

He read a phase that kept every section of his original, cited 26 sources,
carried 237 numbers and passed every check we had. Then he said:

> "I don't feel any value, any concept or anything from it. I'm not reading a
> book that says 2025 had this and now 2026 has this. Why should I care about
> the past if that is not connected and not required? ... It should be a
> teacher who knows everything and now shares the important concepts that I
> should know for becoming better, not anything random."

And about his own phase, which you read through `read_course_source`:

> "That is the course that I generated for learning. If you find the things
> there are not good to learn then you can drop those, and can add things that
> must be learned. That part is for reference."

So you are the teacher, and you have two references: his phase and hunter's
note. Neither is a contract. **The job is understanding, and the unit of
understanding is a concept.**

## A concept, and how to tell

A concept is a claim, one sentence he could be wrong about, that lets him
predict or decide something he could not before.

| A concept | Not a concept |
|---|---|
| Prefill and decode share one forward pass, so a long prompt either waits or freezes every other stream | Chunked prefill (a topic) |
| A schema controls which tokens are legal, never when generation stops | Strict mode guarantees the keys (a fact) |
| A summary keeps what the summariser found interesting, so a rule that must survive is copied, never summarised | Compact at 60% of the window (advice) |

The test: **after this, what can he predict that he could not before?** If the
answer is "nothing, but he knows more facts", it is not a concept.

**A second test, because a fact can be dressed as a claim: could the next
release make it false?** "The token budget has no single default: a B200 API
server starts at 16,384 and an A100 offline run at 8,192" reads like a claim
and is a version table. It shipped as a concept on 2026-09-22, with a predict
question that asked him to recall those values. What survives releases is
"the budget trades time-to-first-token against stream smoothness, so it is a
product decision", and the table under it is one sentence: read the real
value from your startup log. A concept is about how the system must behave.
A default is a detail, however carefully verified, and at most one sentence.

A phase teaches **three to five**. Facts, config keys, numbers and commands
are welcome when they hang from a concept: they are how he uses it. With no
concept above them they are trivia, however well sourced, and they go.

## Plan before any prose

Write this plan in your first answer, before the first `write_lesson_part`.
A lesson that fails does so here, not in its sentences.

```
outcome    one sentence: what he can DO after this that he could not before
c1..c5     the claim · the wrong belief it replaces · the question you will
           ask him first · the ONE number or failure that proves it · the
           picture that shows it · where he uses it (exercise, Mission HQ file)
sections   each teaching section, in order, and the concept it serves
left out   what is in his phase or hunter's note and not in the lesson, and why
added      what is in neither reference's main line and the lesson needs
```

Then run the ledger from `teaching` on it: every term a section assumes was
introduced by an earlier section, an earlier phase, or is known to him.

**`left out` is a decision, not a confession.** Hunter's note names what it
found not worth his time; you may go further. A survey of libraries he will
never choose between, the story of who measured what in which year, the
release a default changed in, a second and third number proving what the first
already proved: leave them out and say so in your report.

## How one concept is taught

In this order. It is the order in which understanding actually arrives.

1. **The situation.** Two or three sentences that put him where not knowing
   this costs something. His stream froze. His parser broke on valid JSON.
2. **Ask before you tell.**
   `<details class="predict"><summary>Predict: three streams are decoding and a
   24,000-token prompt arrives. What happens to their next token?</summary>`
   with the answer and the reason inside. Pick the question a capable engineer
   gets wrong. A concept he guessed wrong is one he keeps. `write_lesson`
   refuses a concept that is told and never asked.
3. **The mechanism, with the picture.** Why it is true, one level below where
   a tutorial stops. This is the body of the section, and it is drawn: a
   figure, a calc box, a before/after. `teaching` has the table of pieces.
4. **The one number, or the one failure.** The measurement with its
   conditions, or the production failure with the symptom first. One. The
   receipt goes in `<details class="evidence">` under it.
5. **Use it.** The exercise from his lab that exercises this idea, copied
   exactly. Then the Mission HQ file where the same mechanism lives, with a
   question that reading it answers.
6. **Close it**, with these labels verbatim:

```
The sentence to remember:   the claim, as he would say it to a colleague
The trap:                   the wrong belief, and what it costs in production
Try this now:               one command, under five minutes, and what to look for
```

If a section is heavy, the fix is never more detail. It is a better question
in step 2 or a better picture in step 3.

## The shape of the page

```
<why he is here: the situation, as a story>              (no h2)
<ol class="concepts">                                    the three to five claims
<h2 data-kind="orientation">  What this builds on, and what it leaves for later
<h2 data-concept="c1">        the question this section answers
<h2 data-concept="c1">        a concept may take more than one section
<h2 data-concept="c2">        …
<h2 data-kind="lab">          the exercises, under the concept each one proves
<h2 data-kind="checkpoint">   scenario questions, answers in <details class="answer">
<h2 data-kind="cheatsheet">   one screen
<h2 data-kind="post">         Two things you could post
<h2 data-kind="sources">      Sources
```

Every `<h2>` carries `data-concept` or `data-kind`. A section that would carry
neither serves no idea and is not apparatus: it does not belong. The concept
list is the first thing on the page after the opening story, written as
`<li id="c1"><b>the claim</b><span>what it lets him do</span></li>`.

Headings name the question, per `teaching`. His phase's section numbers are
not kept: they numbered his outline, and this is not his outline.

## What is kept exactly

His lab was run, and yours was not. So whatever you keep from it is kept to
the character:

- an exercise keeps its id (`E4`), its exact `Run:` command and its expected
  output. `write_lesson` refuses a `Run:` command that is not in his lab, and
  an exercise id his lab does not have.
- you may leave an exercise out when it exercises nothing the lesson teaches.
  Say which in your report. Other phases cite exercises by id, so never
  renumber.
- code is copied from his phase with its `file:line`, never retyped.

Hunter's **Corrections** override his phase: teach the current value as the
plain fact.

## Checkpoint questions

Four to six, each tied to a concept, each a scenario with numbers on a system
he has: Mission HQ, the lab, a system the note names. Never "explain X". The
best ones are the predict questions one step harder: same mechanism, new
situation. Every question is answerable from your lesson alone.

## Anchors in Mission HQ

One per concept where the mechanism genuinely lives in this repo. An anchor
pointing at a file that does not hold the mechanism is worse than none. These
are verified:

| File | What it is good for |
|---|---|
| `backend/src/hq/engine.py` | the DBOS workflows: an agent run start to finish, timeouts, queues, the scheduled ticks |
| `backend/src/hq/runner.py` | `flush_outbox_step`, `await_runtime_approval`: where a run blocks and why |
| `backend/src/hq/board.py` | the task state machine and the notification outbox insert |
| `backend/src/hq/memory.py` | `search()`: FTS and pgvector fused by reciprocal rank; `trim_to_cap`: a context budget enforced by dropping the oldest lines |
| `backend/src/hq/llm.py` | the model registry: per-model timeouts, output caps, the fallback chain |
| `backend/src/hq/tools/registry.py` | the `@hq_tool` decorator: the single choke point for agent capabilities |
| `backend/src/hq/safety.py` | action classes, budgets, HALT, the deterministic guardrail |
| `backend/src/hq/obs.py` | `emit()`: the Postgres event log every run writes into |
| `backend/migrations/*.sql` | the schema as it is |

Write the question so that reading the file changes what he believes.

## The cheatsheet

One screen, no prose: the concepts as one line each, then **what → command or
config**, the one formula with units, and the lines he is most likely to get
wrong. If he has to re-read the phase to find one flag, the cheatsheet failed.

## The course and the articles are different reading

He reads the phase and, on weekdays, articles that orbit it. Your material is
the phase's own study note. If the brief lists articles he has already read,
do not retell their incidents, numbers or examples: one sentence points at
them.

## The lab card

Saturday. One page he works from, not a page he reads.

- It is his phase's own lab, copied exactly: the commands, the expected
  output, the break-it steps. `read_course_source` gives them; never retype a
  command from memory.
- Order: what he will have at the end · what must be running first, with the
  command that proves it · the build, as numbered steps · at least two things
  to break on purpose · the numbers to write down · "done when", as a check ·
  one harder extension.
- Tag every step: offline, live, or "costs at most $X".
- Record it with `kind: "lab"` and the phase slug as `course_slug`.

## Write it and record it

1. `lesson_draft(slug)` first. If parts are already saved, a previous attempt
   was cut off: continue from the next part.
2. **One section per call**: `write_lesson_part(slug, part, markdown, html)`,
   `part` counting from 1 in reading order. A whole phase in one answer runs
   past the time limit and is cancelled with nothing saved.
3. **The html is the body only**: the section itself, built from the kit's
   pieces. No doctype, no `<head>`, no `<style>`, no page script. `write_lesson`
   adds all of that, and refuses a whole document.
4. `write_lesson(slug, title=…, subtitle=…, eyebrow=…)`. It joins the parts and
   checks the whole page.
5. `record_lesson` with `kind: "course"`, `course_slug` set to the phase slug,
   and every source url you used.

**If `write_lesson` sends the page back, fix only what it names.** Every part
you saved is still there. Rewriting the whole phase after one finding doubles
the run.

## Before you call write_lesson, read it as him

Not a score. Four questions, answered honestly:

1. Cover the concept list. From the page alone, could he write those claims?
2. For each concept: what can he now predict that he could not before? If you
   cannot name it, the section taught facts.
3. Find the three sentences he would skip. Cut them.
4. Is any paragraph there because it was in a reference, rather than because
   he needs it? Cut it.

## What to report

In your answer, not in a file:

1. The lesson paths.
2. The plan: outcome, concepts, sections, **left out** and **added**, each
   with its reason.
3. The exercises kept and the exercises left out.
4. The Mission HQ anchors, with the question asked of each.
5. What the note could not support, and what you left out because of it.
   This list is for the report only. He asked for it off the page: "in
   learning it is not required". A fact that is not solid enough to teach
   is left out, not printed with a caveat.
