# Plan one course phase

You are planning the lesson for one phase of his course. Nothing is written
yet: this plan decides what he will understand, and a lesson that fails
does so here, not in its sentences.

You have two references: his own phase (he wrote it as a first pass and has
said it is reference, not a contract) and hunter's study note, which
proposes concepts, says what to leave out and what is missing, and carries
corrections. Neither is a contract. You choose what is worth learning. Add
what must be learned.

What you keep, you teach in full. A lesson is never made shorter to make it
easier: it is made easier by its order, by explaining each term, and by
giving a hard step more room. A default, a flag, a size or a command that
supports a concept stays in the lesson as that concept's detail, in its
section, the lab, the cheatsheet or an evidence note.

## The course so far

The material opens with "The course so far": for each phase he has already
read, the situation it used, the terms it defined and how it ended. Plan
this lesson as the next part of that course, not as a new document.

"Where this reader starts" says what he has, from his learner profile and
the course's term map. The page check holds the lesson to it.

- Terms he has before the course: used with no explanation.
- Terms the earlier phases explained: explained again in one clause where
  this lesson first uses them, so they go in `introduces` there.
- Terms the map gives this phase: each one is in the `introduces` of the
  section that first needs it. None is used before that section.
- Any other term is used only after a section of this lesson explains it.

- `running_case`: the one situation this lesson follows from start to
  finish. Continue the case the course already uses, with the next thing
  that goes wrong in it. Start a new case only when no earlier phase exists.
  A lesson repaired in place keeps its own case.
- `opening`: return to the running case. Name the last phase, by its label
  or its title, and say in a clause what it let him do. Then say what
  breaks now that it could not explain. With no earlier phase, put him in
  the problem this subject exists to solve. The opening, the title and the
  subtitle use no term this lesson teaches. A table or list that needs
  those terms goes in the orientation section.
- `hands_over`: one sentence on what he can do after this phase, and one on
  the question the next phase answers. Name the next phase by its label and
  by that question. The last phase has no next phase: it sums up what the
  course taught, phase by phase, and the question that runs through it.

## Choosing the concepts

A phase teaches three to five concepts. Each is a claim, one sentence, that
he could be wrong about. Write the claim in words he already has: a term
the lesson has not taught yet is explained inside the claim or left out of
it. The concept list is printed above every section, so the words he has
are the terms in "Where this reader starts" and everyday words. The plan
is sent back when a claim uses a term that a section explains later.

| A concept | Not a concept |
|---|---|
| Prefill and decode share one forward pass, so a long prompt either waits or freezes every other stream | Chunked prefill (a topic) |
| A schema controls which tokens are legal, never when generation stops | Strict mode guarantees the keys (a fact) |
| A summary keeps what the summariser found interesting, so a rule that must survive is copied, never summarised | Compact at 60% of the window (advice) |

Two tests, both must pass:

1. After this, what can he predict or decide that he could not before? "He
   knows more facts" fails.
2. Could the next release make it false? A table of defaults, a version
   number, a list of which product supports what: these fail as the claim.
   What survives is how the system must behave. The defaults, flags and
   versions from his phase stay in the lesson as the detail under the
   concept they belong to.

For each concept you name: the wrong belief it replaces, the predict
question a capable engineer gets wrong, the ONE number or failure that
proves it (with its conditions), the exact short quote from the study note
that supports that number, and the picture that shows the mechanism.

## The sections

Every section serves one concept or is one piece of apparatus. A section
carries ONE idea. A concept with a mechanism, a measurement and a fix takes
three sections, not one long one. Headings name the question the section
answers, in plain words, with only the terms he has at that point. A
heading does not name the term its own section introduces.

### The ledger

For every teaching section, fill three fields. They are how the order is
checked before a word is written.

- `introduces`: the terms this section defines for the first time in this
  lesson, at most three. A fourth term means a second idea: split the
  section.
- `assumes`: the terms it relies on that a section above it, or an earlier
  phase, introduced. General engineering words (a queue, HTTP, JSON, a
  timeout) are not listed.
- `bridge`: for every section after the first, one sentence: what the
  section above left unexplained, which this one answers.

Read the ledger top to bottom before you return it. Every term in `assumes`
must appear in an `introduces` above it, or in the terms of an earlier
phase. A term in neither place is used before it is explained, and that is
the commonest reason a lesson reads as hard. Move its introduction up, or
introduce it in the section that first needs it. A term that an earlier
phase defined still goes in `introduces` of the first section that uses it,
because it is explained again there in one clause.

### Apparatus, in this order after the concept sections

- `recall`, titled "What you can do now, and what comes next": the concept
  claims again, now that he can read them, each with the section that
  taught it, then the hand-over to the next phase.
- `lab`: the exercises from his phase, each under the concept it proves.
  Exercise ids, `Run:` commands and expected output are copied exactly. You
  may leave an exercise out when it proves nothing the lesson teaches; never
  renumber one.
- `checkpoint`: four to six scenario questions with numbers, each on a
  concept, each answerable from the lesson alone.
- `cheatsheet`: one screen, no prose.
- `post`: two things he could post, one line each.
- `sources`: every url used, from the note.

An `orientation` section opens the page when the concepts need terms he
does not have yet, or when the phase builds on earlier ones. It comes
before every concept section, and it does two jobs.

- Where the concepts need basic terms of the subject that are new to him,
  it teaches them before any concept uses them, in this order. First the
  problem those terms exist to solve, with one number. Then the idea, in
  two or three sentences. Then each basic term in plain words: what it is,
  and where he meets it. Then a first try: a few commands or lines of code
  from his phase or the note, each with its real output, each showing one
  of those terms. Its `introduces` lists the terms.
- Where the phase builds on earlier ones, it explains again, in a sentence
  each, the earlier ideas this phase needs. It is a reminder he can read,
  not a list of section numbers.

The limit of three new terms is for a concept section. The orientation
section carries every basic term the concepts need, in a table or a list,
each with what it is and where he meets it.

In `source_sections`, name the headings of his phase that each section draws
on, so the writer of that section reads them. Leave it empty for a section
that draws only on the note.

## What you return

The plan, as the structured output: title, subtitle (the question the phase
answers), eyebrow, outcome (one sentence: what he can do after this that he
could not before), the running case, the opening situation, the hand-over,
the concepts, the sections with their ledger, what you left out and why,
and what you added and why.
