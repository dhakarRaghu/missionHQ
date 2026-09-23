# Research a local course phase spec

Use this when the brief names a phase whose source is `local`: a spec block in
`learning/courses/<NN>-<course>/course.md`, with no study module behind it.
Load `deep-research` first and work to it. This file does not repeat its
rules; it says what the note must contain.

## Why this note is different

A platform module already carries the content, and your note adds to it. A
spec carries none. It lists the sections, the terms and the lab, and nothing
else. So **every default, error message, number, incident and reference that
tutor writes must be in your note, or it does not get written.** Tutor has no
web access. It may only state what your note supports.

After tutor writes the phase, a separate review run checks it. Every url in
the lesson must appear in your note, and every fact must trace back to a
labelled claim in it. A thin note produces a thin phase or a failed review.

## Order of work

1. **`read_course_phase(slug)`.** It returns the spec, its sections and a
   `sequence` block naming the phase before and after.
2. **Read the neighbours.** Call `read_course_phase` on the previous and next
   phases. You are answering two questions: what has he already been taught,
   and what belongs to a later phase that this one must not lean on.
3. **Research each spec section**, by source rank, as `deep-research` says.
   Go to rank 1 or 2 for the mechanism: the source at a version tag, versioned
   docs, the paper's method section. Use `fetch_source` for defaults and error
   messages, because the exact words matter.
4. **Find the incident.** A postmortem or production writeup on the phase's
   mechanism.
5. **Judge the lab** against the sandbox it will run in.
6. **Write the note**, then `record_reading`.

Spend searches on what you cannot name, within the brief's budget. A section
where you found nothing is still a block in the note, saying what you looked
for.

## The note

Write it to `quarantine/<YYYY-MM-DD>-<slug>-study.md`, with the usual
frontmatter (`source_urls` listing every url you opened, `confidence`). Then
these sections, in this order.

### `## Spec`

Copy the spec block verbatim: from `## Phase N — <title>` to the end of
`### Test out`. Do not summarise it. The review run checks the lesson against
this copy.

### `## Sequence`

- **Earlier phases taught:** the terms and ideas he already has, each with the
  phase that taught it. Take them from the spec's `assumes` and the previous
  phase.
- **This phase introduces:** the `introduces` list, in the order the sections
  need them.
- **Later phases own:** the `leaves-for-later` list, plus anything the next
  phase's spec introduces that this phase might be tempted to use.

### `## <N.x> <section title>`, one block per spec section

Every section in the spec gets its own block, in spec order, with the spec's
number and title. Each block carries:

```
## 2.5 Pools that fill

Mechanism (verified): 3 to 6 lines on how it works.
Source: <url> — rank 1, <tag or version>, <file or section>

Defaults and config keys:
- `SetMaxOpenConns` = 0 (unlimited) — Go 1.23 — database/sql/sql.go at go1.23.0 — verified

Error messages:
- `<the exact text, copied>` — when it appears — <url> — verified

What the failure looks like:
- logs: <the line he would grep for> — <source> — <label>
- metrics: <the metric that moves, and which way> — <source> — <label>
- traces: <the span that grows or goes red> — <source> — <label>

Numbers:
- <number>, against <baseline>, on <hardware>, <version>, <workload> — <url> — <label>

Looked for and not found: <what, and where you looked>
```

- **Every claim carries a label**: verified (you opened the source this run),
  inferred (you reasoned it), or not checked.
- **A default without a version and the file or doc it was read from is not
  a default.** Read the source at a tag, not `main`.
- **An error message is copied exactly**, from the source or from a real log
  in a writeup. A paraphrase is labelled as one.
- **A section with no config** (a formula, a model) says so: "no config keys:
  this section is arithmetic". Do not leave a heading empty, and do not
  invent a key to fill it.
- The example line above shows the format. Its value is illustrative; check
  every value you write.

### `## Incident`

At least one real production failure on the phase's mechanism, with its url
and date, in this shape:

1. The symptom, as it first appeared.
2. The wrong theory they chased first.
3. The decisive signal that located it.
4. The fix: what stopped the damage, and what stopped it happening again.
5. What changed afterwards.

Name which spec section it illustrates. If you found none, say so plainly,
with what you searched. Never present a vendor listicle or an invented
scenario as an incident.

### `## Lab feasibility`

Tutor must write the lab as runnable files. They run in a sandbox with **no
network, not even localhost**, **writes only inside a temp copy of the lab**,
the **Go or Python standard library only**, and one command per exercise with
no shell.

For the spec's `### Lab`, write:

- **What the lab needs**: processes, files, services, data, timing.
- **What can run in the sandbox**: the parts provable with a self-contained
  program (a simulated queue, an in-process pool, a child process killed
  mid-write, a file corrupted on purpose), and the output that proves each.
- **What must be `verify: manual`, and why**: anything that needs a real
  network service (Postgres, etcd, a model API, the running Mission HQ API).
- **Expected results** where a source gives them, with conditions and a label.

### `## References`

Only urls you actually opened this run. Each entry:

```
<title> — <url>
Why:   what it gives him that the phase will not
Focus: the section or chapter; a timestamp ONLY if you saw it yourself
When:  before the lab / after the lab / in production
```

Three good references beat twelve. If no worthwhile video exists on the
mechanism, write that sentence. Never guess a timestamp or a docs path.

### `## Things I could NOT verify`

Mandatory, in the format `deep-research` gives. An empty list is a mistake
unless it is genuinely true.

## Before you file

- Every `N.x` in the spec has its own block.
- Every url in the note is in `source_urls`, and every one was opened this
  run.
- Nothing came from memory. A value you remember but did not read is either
  checked now or written under "Things I could NOT verify".

Then call `record_reading` exactly as the brief says. Do not write the
lesson. End your reply with the note path and a three-line summary: sections
covered, whether an incident was found, and what the lab can verify
automatically.
