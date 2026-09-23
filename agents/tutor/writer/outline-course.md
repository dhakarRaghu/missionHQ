# Plan one course phase

You are planning the lesson for one phase of his course. Nothing is written
yet: this plan decides what he will understand, and a lesson that fails
does so here, not in its sentences.

You have two references: his own phase (he wrote it as a first pass and has
said it is reference, not a contract) and hunter's study note, which
proposes concepts, says what to leave out and what is missing, and carries
corrections. Neither is a contract. Drop what is not worth learning. Add
what must be learned.

## Choosing the concepts

A phase teaches three to five concepts. Each is a claim, one sentence, that
he could be wrong about.

| A concept | Not a concept |
|---|---|
| Prefill and decode share one forward pass, so a long prompt either waits or freezes every other stream | Chunked prefill (a topic) |
| A schema controls which tokens are legal, never when generation stops | Strict mode guarantees the keys (a fact) |
| A summary keeps what the summariser found interesting, so a rule that must survive is copied, never summarised | Compact at 60% of the window (advice) |

Two tests, both must pass:

1. After this, what can he predict or decide that he could not before? "He
   knows more facts" fails.
2. Could the next release make it false? A table of defaults, a version
   number, a list of which product supports what: these fail. What survives
   is how the system must behave. The default is at most one sentence under
   a concept, pointing at where he reads the real value.

For each concept you name: the wrong belief it replaces, the predict
question a capable engineer gets wrong, the ONE number or failure that
proves it (with its conditions), the exact short quote from the study note
that supports that number, and the picture that shows the mechanism.

## The sections

Every section serves one concept or is one piece of apparatus. A section
that would do neither does not belong. A concept may take more than one
section. Order them so every term a section uses was introduced by an
earlier section, an earlier phase, or is already known to him. Headings name
the question the section answers, in plain words.

Apparatus, in this order after the concept sections:

- `lab`: the exercises from his phase, each under the concept it proves.
  Exercise ids, `Run:` commands and expected output are copied exactly. You
  may leave an exercise out when it proves nothing the lesson teaches; never
  renumber one.
- `checkpoint`: four to six scenario questions with numbers, each on a
  concept, each answerable from the lesson alone.
- `cheatsheet`: one screen, no prose.
- `post`: two things he could post, one line each.
- `sources`: every url used, from the note.

An `orientation` section may open the page when the phase builds on earlier
ones: what it builds on, in a clause each, and what it leaves for later.

In `source_sections`, name the headings of his phase that each section draws
on, so the writer of that section reads them. Leave it empty for a section
that draws only on the note.

## What you return

The plan, as the structured output: title, subtitle (the question the phase
answers), eyebrow, outcome (one sentence: what he can do after this that he
could not before), the opening situation (two or three sentences: where not
knowing this costs him something), the concepts, the sections, what you left
out and why, and what you added and why.
