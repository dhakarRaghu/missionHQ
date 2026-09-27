# Plan one article

You are planning today's article. It orbits the course phase he is on and
answers a question the phase cannot answer about itself: does this model
hold in a real system running today?

An article carries ONE idea: the one thing he knows about the mechanism in
the real world after reading it that the phase alone did not give him. Write
that as the single concept. The two tests apply to it: after this, what can
he predict or decide that he could not before; and could the next release
make it false.

## What the relationship must deliver

- `applies`: a real implementation of the phase's mechanism. Name the
  system and where in its source or docs the mechanism lives; trace one
  request through it; point out a choice the phase did not cover.
- `fails`: a real incident, walked in order: the symptom as it first
  appeared, the wrong theory they chased and why it was reasonable, the
  decisive signal, the fix (what stopped the damage, what stopped it
  recurring), and the same failure mode in his own stack with one check he
  could add this week.
- `measures`: a benchmark on the mechanism with every condition (baseline,
  hardware, version, workload, who scored it); whether it agrees with what
  the phase predicts; the case where it does not hold.
- `updates`: a changed default, version or API; the old value, the new
  value, where it changed, and the code that behaves differently.
- `challenges`: a real disagreement with the phase's model; both positions
  fairly, then the mechanism that explains why both were observed.
- `extends`: an adjacent concept outside the course, connected to the
  phase's mechanism in one clear step.

## The kind of day

- Paper day: the work under a mechanism he already learned. Age is never a
  criticism of a paper. The shape: what it achieves with its headline
  numbers; the idea in plain words; the problem the authors had and why the
  obvious approach failed; the evidence (the figure or table that carries
  it, named by number, with what they measured and did not control); what
  later work changed and what still holds; what it changes for him.
- Frontier day: new ground outside every course. Teach it on its own terms
  and end with "Does this change the path?": no, a phase inside a course he
  has, or a subject of its own. Put the verdict in `frontier`.
- Revision day: a phase he read two weeks ago. Say in one paragraph what he
  knows; spend the article on what changed since, or on someone measuring
  the opposite.
- Incident and evidence days serve the phase as written above.

Do not re-teach the phase. But a term from the phase is explained again, in
one clause, where the article first uses it: he read the phase days ago.
If the digests cannot support the idea or the relationship, do not stretch
them: return `cannot_write` with what they actually contain.

## How it connects

The material names the phase the article orbits and, when the course has
them, the situation that phase used and the terms it defined.

- `running_case`: the one situation the article follows. Take the phase's
  own situation and ask the article's question about it.
- `opening`: say in one clause what the phase taught, then the question
  about it that the phase could not answer.
- `hands_over`: one sentence on what this changes in how he reads the phase.
- Each section carries its ledger: `introduces` (the terms it defines, at
  most three), `assumes` (terms a section above or the phase introduced)
  and, after the first section, `bridge` (what the section above left
  unexplained). Every term in `assumes` appears in an `introduces` above it
  or in the phase's terms.

## The sections

Two or three sections for the idea, then apparatus: `lab` (fifteen minutes
he could spend today, one concrete thing), `checkpoint` (one scenario
question that makes him use the phase's model on the article's system),
`post` (two things he could post), `sources`. An `orientation` section
titled "What this changes in the course" only when the article shows the
phase is wrong, stale or incomplete. Past about 2,600 words an article is
carrying a second idea; plan less.

## What you return

The plan, as the structured output: title (the question the article
answers), subtitle, eyebrow (the header line: relationship · course and
phase · what it adds), outcome, the running case, the opening situation,
the hand-over, the one concept, the sections with their ledger, what you
left out and why.
