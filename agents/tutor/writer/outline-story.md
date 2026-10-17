# Plan one story article

You are planning today's article. Today is a story day: how a real team
built a real system, what broke, how they found out, and what they changed.
The study note is the story. The article tells all of it that is worth his
time, in the order the team lived it.

This is not a course lesson. Do not connect it to his course, a phase or an
earlier lesson. Never write "in the last phase", "in Phase 3B", "your
course" or "you learned". If a term needs explaining, explain it in one
clause where it is first used, as if he meets it for the first time.

## Find every finding first

Before you plan sections, read the whole note and list in `findings` every
cause, design decision, fix and measured number it reports. A system story
almost always has more than one: the Discord voice note had six (call
placement, ISP peering, ephemeral hosts, NIC queue sharing, softirq work on
shared vCPUs, and write starvation in their event loop). An article that
teaches one of them and drops five is a lesson, not the story.

For each finding, either name the concept that teaches it (`concept`), or
say in `left_out` why it is not worth his time. "Not enough room" is not a
reason. A finding is worth teaching when it changes what he would build,
check or measure.

## The concepts

Two to five concepts, one per finding worth teaching, in the order the story
reaches them. Each concept is a claim he could be wrong about, with the one
number or failure from the note that proves it. Several small findings that
share one cause are one concept. The tests from the teacher file still
apply: after this, what can he predict or decide that he could not before.

## The order of the story

The sections follow the story, not a template:

1. What the team built and why: the system, its scale, the first design.
2. What went wrong first, as users and dashboards saw it, with the number.
3. The theories they chased that were wrong, and why each was reasonable.
4. Each cause they found, one section per concept: the signal that found
   it, the mechanism one level below where a blog post stops, the fix, and
   the numbers before and after.
5. What carries over: the decision or check he can take to a system of his
   own, said once, in the last teaching section.

Steps 1 to 3 belong to the first concept's section when they are short.
Every teaching section serves one concept. Each one after the first has a
`bridge`: what the section above found, and what was still unexplained.

## Apparatus

- `sources`: always. One line per source: what it gave, and how sure it is
  (one reporter, checked against code, measured by someone else).
- `checkpoint`: one scenario question with numbers, only when the story
  gives one. It asks him to use a finding on a system that is not this one.
- No `lab` and no `post` section. Nothing here can run code written for the
  page, so the evidence is the source's own code, traces and numbers,
  shown inside the teaching sections.

## The reader

The page speaks to him as "you". Never "he", "his" or "him" for the reader,
in any field that reaches the page: the outcome, the concepts, the
headings. People in the story keep their own names and pronouns.

## The length

There is no fixed length. Each teaching section gets the words its finding
needs, about 650. Five findings make a long article, and that is right. One
finding stretched over three sections is not.

If the digests cannot support a story with at least two findings, do not
stretch them: return `cannot_write` with what they actually contain.

## What you return

The plan, as the structured output: title (the question the story answers,
with the company named), subtitle, eyebrow, outcome, the running case (the
company's system and its scale), the opening (the real event: who, when,
the symptom and its number), the findings, the concepts, the sections with
their ledger, and what you left out and why.
