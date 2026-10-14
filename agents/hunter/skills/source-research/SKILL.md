# Source research

Your job is to break the claim, not to confirm it. A study note decides
what is worth learning from a piece of ground and proves it, so a teacher
can state it plainly.

## Open what you cite

- A url goes in the note only if you opened it this run. Never cite a url
  from memory or a guessed address.
- Record the date you read each source beside it.
- If a page would not load or was cut off, say what you did not read.
- A long run keeps itself inside the model's window: a result may come back
  as part 1 of several, or later as an extract with a reference. Both were
  saved whole. Before you quote one or take a number from it, read the part
  that holds it with the call its note gives. Never cite from an extract or
  an outline.

## Rank what you find

| Rank | Source |
|---|---|
| 1 | The source code or config at a release tag (never `main`), the official docs for that version |
| 2 | The paper or the maintainers' design doc |
| 3 | A benchmark with its method: hardware, version, workload, who ran it |
| 4 | An engineer's own write-up of what they built or broke |
| 5 | Secondary blogs and summaries: a lead to the real source, never the source |

Rank 1 beats rank 2 when they disagree. Two independent sites beat one; if
everything rests on one site, say so.

## How a fact is stated

- A number keeps its conditions: "up to 23x against static batching,
  OPT-13B on one A100 40GB". For a range, a maximum or a count, read the
  table's rows, not the paper's summary sentence.
- A default keeps the version it was read at.
- Find where the claim does not hold, and say it.
- When sources disagree, find what explains it (usually they measured
  different things). The story of who said what is not a finding.
- Label every claim: verified (you read it in a rank 1-3 source), inferred
  (you reasoned from what you read), not checked.

## Concepts, not an inventory

The note proposes the concepts a teacher should teach: as many claims as
the brief names, each one he could be wrong about, each letting him predict or decide something new.
Two tests: after this, what can he predict that he could not before; and
could the next release make it false (a default, a version table, a list
of which product supports what fails). Give each concept one piece of
evidence, the strongest, with its conditions and a short exact quote.

History is not a finding. Which version introduced a feature is at most one
line, and only if he will meet the old behaviour.

## The note

Use the sections the brief names. Always end with "Things I could NOT
verify": what you looked for and did not find. It is never empty by neglect.

## Finding writers

When the task is to find people worth reading for months: engineers who
explain how systems work, with their own diagrams and numbers, who publish
regularly. Verify each on their own index page: the newest post is within
90 days, one post explains a mechanism or admits a failure, and it is a
named person. Five verified names beat twelve guesses.
