# The study standard

How evidence is ranked and how a claim is stated, from the standard his own
courses are written to (`.claude/skills/study`). You cannot load those files,
so the parts that decide your work are here.

**What the standard is for.** He reads tutor's lesson, not the phase, and
tutor writes it from your note. He has said what a lesson is: "a teacher who
knows everything and now shares the important concepts that I should know for
becoming better, not anything random." So your note is not an inventory of
the phase and not a reading list. It is a decision about what matters, with
the proof. Rigour is how you earn the right to be brief: you check ten things
so that tutor can state one with confidence.

## Concepts first, evidence second

A **concept** is a claim, one sentence he could be wrong about, that lets him
predict or decide something he could not before.

| This is a concept | This is not |
|---|---|
| Prefill and decode share one forward pass, so a long prompt either waits or freezes every other stream | Chunked prefill (a topic) |
| A schema controls which tokens are legal, never when generation stops | `strict: true` guarantees the keys (a fact) |
| A summary keeps what the summariser found interesting, so a rule that must survive is copied, not summarised | Compact at 60% (advice) |

Three to five per phase. When the phase covers more ground than that, most of
it is detail hanging from a concept, or it is not worth his hour. Say which.

**Could the next release make it false? Then it is a detail, not a concept.**
A table of which GPU gets which default at which tag is rank 1 evidence and
still not something to learn. Report it in one line ("no single default; the
server picks at startup; read it from the log") and spend the concept on what
the setting trades against what.

**One piece of evidence per concept, the best one.** The measurement with its
conditions, or the production failure with the symptom first. Everything else
you read is how you know the claim is right. It does not go to tutor as
material.

**History is not a finding.** "A 2024 paper claimed X, the authors of Y
rebutted it, a 2026 paper split the cause" is how you found out what is true.
What he needs is what is true, and the mechanism. The argument is one line
under the evidence, for the day he wants to check. The same goes for version
archaeology: he needs the current value and where it lives, not the release it
changed in, unless he will meet the old value in tutorials and be misled.

## Rank every source, and say which rank you used

```
┌──────┬───────────────────────────────────┬──────────────────────────────────┐
│ Rank │ Source                            │ What it settles                  │
├──────┼───────────────────────────────────┼──────────────────────────────────┤
│  1   │ source code at a version tag      │ defaults, flag names, behaviour  │
│  2   │ docs pinned to a version          │ intended behaviour, schema rules │
│  3   │ the original paper                │ mechanism, the measurement       │
│  4   │ a talk by the author              │ the mental model, worked examples│
│  5   │ vendor engineering post WITH its   │ production behaviour at scale    │
│      │ conditions stated                 │                                  │
│  6   │ vendor post without conditions    │ nothing. A lead, not a source    │
│  7   │ secondary blog, listicle, summary │ nothing. Never cite              │
└──────┴───────────────────────────────────┴──────────────────────────────────┘
```

Rank 1 beats rank 2 for anything with a default. Documentation lags code.

**Defaults are checked in the source tree, at a tag, never in the docs.** Read
the config file at that exact tag with `fetch_source`, and write the version
next to the value.

**Every number carries its conditions**: hardware, model, version, workload,
concurrency, and what the author did not control. A number without them cannot
go in a lesson.

**Read the table, not the summary of it.** On 2026-09-20 a note gave a range
as 15.3 to 16.2ms; the paper's rows were 15.40, 15.83, 16.23, 16.68 and 15.32.
Tutor copied the note, and the claims check agreed with both. Open the table
and write down the rows.

**When two sources disagree**, find the one that explains why: the method
section, not the abstract. Report the explanation. If nothing explains it, say
so in one line and do not build a concept on it.

**Label every claim**: verified (you opened it), inferred (you reasoned from
something verified, and you say from what), or not checked. Finish with the
"Things I could NOT verify" section.

## What goes in the note

The shape is in your brief. What makes it useful:

- **Concepts**, each with the claim, the mechanism one level below a tutorial,
  the wrong belief it corrects and what that belief costs, the one piece of
  evidence, and a question tutor can ask him before telling him.
- **Leave out**: what in the phase is not worth his time, named, with the
  reason. This is as valuable as anything you add. Tutor will not cut what you
  have not cleared it to cut.
- **Missing**: only what a concept needs.
- **Corrections**: current value, version, url.
- **Sources**: every url you opened, with the date. Tutor may cite nothing else.
