# The courses

Eight courses, in order. This is the spine of the learning system: the
course decides what is taught next, and the daily articles orbit the phase
that is active.

**These files are specs, not content.** Each phase says what it must teach,
what it assumes, what it introduces, and how mastery is proven.

**The phases are written with Claude**, one at a time, with the `/study`
skill (`.claude/skills/study/`, see `references/mission-hq.md`). The spec is
the approved outline. Each phase is reviewed and audited there, published to
the study platform, and pulled into Mission HQ with
`uv run python -m hq.cli sync-courses`. Mission HQ then adds to it (updates,
corrections, production incidents, deeper material) and never rewrites it.
Until a phase is published it shows as planned, and nothing here writes it.

Written 2026-09-14 from four research passes (hiring demand, applied AI
practice, senior/staff backend expectations, the effect of AI on engineering
work) and two outside reviews of the plan. The reasoning behind the order and
the cuts is in `../path.md`.

## Files

```
learning/courses/
  README.md                     this file
  01-performance/course.md      Performance, concurrency and the machine
  02-applied-ai/course.md       Applied AI systems at scale (superseded: see below)
  03-inference/course.md        Inference and AI platform (maps the existing platform course)
  04-storage/course.md          Storage and database internals
  05-distributed/course.md      Distributed systems and verification
  06-reliability/course.md      Reliability, security and change
  07-system-design/course.md    System design and architecture
  08-production-infra/course.md Production infrastructure: change, supply chain and proof
  08-production-infra/notes.md  out-of-scope list and corrections to commonly-repeated facts
```

## Applied AI is the 21-module curriculum

Since 2026-10-17 the Courses page shows path step 2 as the 21 modules of
the applied-AI curriculum. The modules are listed in
`../study-material/_curriculum/README.md`. Each complete module links to
the platform course named in its dossier file, `module-NN-<topic>.md`. Module 1
is `inference-internals`, so it is no longer a separate path step. The
five-phase spec in `02-applied-ai/course.md` stays in git as a reference.
The page does not list it.

The curriculum folder is a copy of `study-material/_curriculum/`. When a
research run changes it there, copy it here again.

## The format, which code reads

Course header, then one `## Phase N — Title` block per phase:

```
# Course 1 — Performance, concurrency and the machine
slug: elite-performance
order: 1
source: local            # local = specs here; platform = phases on the study platform

## Phase 2 — Queueing, saturation and tail latency
question: <the one hard question the phase answers>
minutes: 120
assumes: <terms from earlier phases, with the phase that introduced them>
introduces: <terms this phase defines for the first time>
leaves-for-later: <terms the phase must NOT lean on, with where they arrive>

### Why you're here        <a concrete production situation, then the open question>
### Sections               <N.1 — title: one line each; every one must appear in the lesson>
### Lab                    <what he builds or breaks>
### Demonstrate            <the measured, reproducible evidence of mastery>
### Test out               <Explain / Predict / Demonstrate — pass all three to skip>
```

`assumes` / `introduces` / `leaves-for-later` drive tutor's planning ledger: a
lesson may not use a term that is neither assumed nor introduced earlier, and
may not pre-teach what is left for later. `### Sections` is the coverage
contract: every listed section appears, in order.

## Optional files beside a course.md

A course directory may hold two more files. Read both before generating any
phase of that course. Course 8 has both; courses 1 to 7 have neither yet.

```
NN-<name>/
  course.md     the spec. The approved outline. Required
  sources.md    fetch-verified sources, dated incidents and hard numbers, per phase
  notes.md      topics deliberately out of scope, and facts commonly published wrongly
```

`sources.md` exists so generation does not repeat research that is already
done. It carries the URL, the date it was verified, and the conditions attached
to every number. Re-check version numbers before publishing, because versions
move. Do not re-check the dated incidents.

`notes.md` is the correction list. Several widely published facts about
Terraform, SLSA, SBOM formats and DORA are wrong. Read it before writing a
sentence that repeats one.

If a phase needs a number that neither file carries, it is **not checked**.
Say so in the material rather than reaching for a figure.

## How long it really takes

`minutes:` on a phase is the lesson time — reading and working through the
material. It is not the lab. The labs are the point (a fifty-kill crash
matrix, two hundred adaptive attacks, a model checked in TLA+, two design
documents) and they run five to ten times the lesson time. Plan against
that number, not the one in the field. At eight to ten hours a week the
path is four to five months; test-outs shorten it, hard labs lengthen it.

## Rules that apply to every phase

- **Advanced, not introductory.** He has shipped Go/gRPC services, Kubernetes
  workflows, RAG, MCP, guardrails and an eval pipeline. No phase spends time on
  what those are. Shipping proves exposure, not mastery of the failure modes —
  so the failure modes are exactly what each phase teaches.
- **Mechanism over product.** A tool appears as the example of a mechanism,
  never as the subject.
- **Mission HQ is the laboratory.** Labs run against this repo — its durable
  workflows, approvals, outbox, retrieval, event log — or against the KV-store
  lab that courses 4 and 5 build up.
- **Test out with evidence.** Explain, predict, demonstrate. Passing all three
  skips the phase. Knowing the vocabulary does not.
- **Plain English.** His second language. No idioms; technical words stay.
- **Never his employer, past or present.**
