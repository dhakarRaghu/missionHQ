# Write an article

Load `teaching` first. Its rules on plain English, the story opening, the
planning ledger, headings, length, facts and labels, the employer, the page
and the diagram all apply here and are not repeated. This file adds what an
article needs.

## An article orbits the course

The course is the spine. He works through one phase at a time, and the phase
teaches the model. An article is a short satellite of the **active phase**. It
answers a question the phase cannot answer about itself: does this model
transfer to real systems running today? To a current incident, a new paper, a
changed default, an implementation that does it differently?

So an article never stands alone, and it never repeats the phase. It takes
the phase's model as known and tests it against something real.

## What the brief gives you

- **The phase**: course, slug, title, its question, and its sections.
- **`relationship`**: one of `applies`, `fails`, `measures`, `updates`,
  `challenges`, `extends`. It says what job this article does for the phase.
- **`adds`**: one line saying what this article adds beyond the course.
- **Hunter's digests**, all on one topic.

Before planning, write one sentence for yourself: after this article, what
does he know about the phase's mechanism in the real world that the phase
alone did not give him? Start from `adds`. If the digests cannot support that
sentence, or cannot deliver the relationship, do not stretch them. Write
nothing, and report in a few lines what the digests actually contain and
which relationship they would support. A quiet day honestly reported costs him
two minutes; a forced article costs his trust.

## What each relationship must deliver

This is the body of the article. An article that names a relationship and
does not deliver it has failed, however well it reads.

**`applies`**: a real implementation of the phase's mechanism. Name the
system, the version, and where in its source or docs the mechanism lives.
Trace one request or one write through it, and show which of the phase's
ideas each step is. Point out where the implementation made a choice the
phase did not cover, and why.

**`fails`**: a real incident on the phase's mechanism. Walk it in this shape,
because he asked for it: "teach me things faced in production systems, the
solution, and the learning from it."

1. **The symptom, as it first appeared.** What was on the dashboard at 3am,
   not the tidy description written afterwards.
2. **The wrong theory.** What they chased first, and why it was reasonable.
   The most useful paragraph in any postmortem, and the one summaries drop.
3. **The decisive signal.** The metric, log or trace that ended the search,
   and whether he has that signal in his own system today.
4. **The fix**, split into what stopped the damage and what stopped it
   happening again.
5. **What changed.** The change that outlived the incident, and the same
   failure mode in his own stack, with one check he could add this week.

Do not flatten an incident into an explainer. The price was already paid; do
not waste it by summarising the conclusion.

**`measures`**: a benchmark or experiment on the mechanism, with its
conditions: baseline, hardware, version, workload, and who scored it. Say
whether the result agrees with what the phase predicts, and if not, which
condition explains the gap. Include the case where the result does not hold.

**`updates`**: a changed default, version or API that affects what the phase
teaches. Give the old value, the new value, the version or date it changed,
and the source (a changelog, a release note, the source file at a tag). Show
the code or config that breaks or behaves differently after the change.

**`challenges`**: a counterexample or a real disagreement with the phase's
model. State both positions fairly. Then give the mechanism that explains why
both were observed: usually they measured different things. Do not pick the
tidier side.

**`extends`**: an adjacent concept deliberately outside the course. Say in the
first section that it is outside the course and why it is worth his time now.
Connect it to the phase's mechanism in one clear step, and teach its own
prerequisites here.

## Do not re-teach the course

- **Assume what the phase teaches.** Its `assumes` and `introduces` terms are
  known. Use them without explaining them again. A paragraph re-teaching the
  phase is padding, and the rubric scores it as such.
- **Point, do not repeat.** When you need a phase idea, one clause is enough:
  "the knee from 2.2 is visible here at 78% utilisation".
- **No unexplained prerequisite.** Run the ledger with the phase's terms as
  the known set. A term that is neither in the phase nor defined in the
  article is a forward reference. A term from a later phase is not known yet:
  define it in one or two sentences, or pick another angle.
- **The one exception is `extends`**, which teaches its own new concept, and
  still does not re-teach the phase.

## One topic, several sources

Every digest is on the same topic. Use the sources against each other: where
they agree, where they contradict, what one covers that the others skip, which
one has the real numbers. That is what makes several sources worth more than
the best one.

**Use the independent sources.** Every study note has a section
`## Independent sources`: the pull requests, docs and papers behind the
article, and other sites that confirm or contradict it. Bring them into the
text where the claim is made — "the vLLM post reports X; the pull request
shows Y; an LMSYS benchmark on different hardware measured Z". A number that
only the original authors report is said to be theirs, in the sentence that
uses it.

**One site is not enough.** If every url in the notes is on one site, say so
in "Things I could not verify" and name what a second source would have to
show. Never fill the gap from memory.

**Sources lists every url the article used**, each with one line on what it
contributed, grouped as: the article(s), what they point at (pull requests,
issues, docs, papers), and the independent sources.

**Never weld unrelated material together.** On 2026-09-12 a lesson joined
vLLM's scheduler to MySQL replication under one clever claim. Both halves
were accurate. He could not follow it: "I'm not able to connect the both
topic." If you are ever handed unrelated sources, say so plainly and write
about the strongest one. The system is the example; the mechanism is the
subject.

## The shape

```
_<relationship> · <Course> Phase <N>: <Title> · Adds: <one line>_

# <title: the question the article answers>

## Why you are here: <the situation, named>
## <sections that deliver the relationship, each heading a question>
    the mechanism in the real system, a worked example, where it breaks
## What this changes in the course        (only when it corrects or updates it)
## Fifteen minutes today
## A question to test the transfer
## Things I could not verify
## Two things you could post
## Sources
```

**The header line comes first**, before the title and the story. It names the
relationship, the course and phase it orbits, and what it adds beyond the
course. He should know from one line why this article exists.

**The worked example** is real code, config, or a traced request path that
would actually run, including the hard part. Use the language the material is
in.

**What this changes in the course.** When the article shows the phase is
wrong, stale or incomplete (a default that moved, a model that fails in a
case the phase does not mention), say it in this section: the phase section
number, what it says, what is now true, and the source. He annotates the
phase from this section, so keep it exact. Leave the section out when nothing
in the course changes.

**Fifteen minutes today.** One concrete thing to try: a file to open, a query
to run, a parameter to change. Specific enough to start without deciding
anything.

**A question to test the transfer.** One scenario question that makes him use
the phase's model on the article's system. Name the phase section it
exercises. It must be answerable from the phase plus this article.

## Length

Roughly 8 to 15 minutes of reading. Length follows what the relationship needs
to be delivered well: an incident walked properly needs more room than a
changed default. No padding. The page is the lesson: the whole article is on
the page, as `teaching` says.

## Write it and record it

1. Save the article one section per call with `write_lesson_part`: the
   section's markdown, and its page body in the kit's components (see
   `teaching`). Then call `write_lesson` with the slug, `title`, `subtitle`
   (the question) and `eyebrow` (the header line). A long answer in one call
   can be cancelled by the time limit with nothing saved.
2. `record_lesson` with `kind: "topic"`, `phase_slug` set to the phase's
   slug, `relationship` set to the brief's relationship, and every source url.

## Score it, then fix the lowest

Nine dimensions, 0-10 each:

1. **The relationship is delivered**: `fails` walks all five incident steps,
   `measures` carries every condition, `updates` has the version or date and
   the source. A named relationship that is not delivered scores 3 or below.
2. **Does not repeat the course**: each paragraph that re-teaches a phase idea
   costs 2.
3. **No unexplained prerequisite**: zero forward references is 10; each costs 3.
4. **One topic, several sites**: sources on one topic, used against each
   other. An article whose sources all sit on one site scores 5 or below,
   unless the notes had nothing else and the article says so.
5. **Not obvious**: it says something the phase alone could not.
6. **Concrete**: real code, numbers with conditions, a named failure mode.
7. **Sectioned to be read**: every heading names its question.
8. **The diagram teaches**: mechanism, not outline. Score 8 when it is
   honestly absent and your report says why.
9. **Verification carried**: labels kept, could-not-verify preserved, every
   url from the digests. One invented url or promoted claim scores 0.

Pass is 70 of 90, none under 6, and dimension 9 must be 10. Up to two revise
passes, lowest first. If a pass does not raise the score, stop and say what
you would need.

## What to report

1. Both paths from `write_lesson`.
2. The header line.
3. The section plan and the ledger result.
4. The score, all nine dimensions, and the weakest.
5. Whether the article changes the course, and which phase section.
