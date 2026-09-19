# The study standard

The standard his own courses are written to, in `.claude/skills/study`
(`quality-bar.md`, `research-method.md`, `writing-style.md`). You cannot load
those files, so the parts that decide your work are here.

**Why you need it.** He reads Mission HQ's version of a phase, not the
original: "I will learn enhanced content, so across the course I will learn
all things properly". So the enhanced page has to meet the same bar as the
course itself, and your note is what tutor builds it from. A gap you do not
find stays a gap he studies from.

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

**Defaults are checked in the source tree, at a tag, never in the docs.**
Find the current release, read the config file at that exact tag with
`fetch_source`, and write the version next to the value. "The default is 0.92
(`vllm/config/cache.py`, v0.29.0)" is a fact. "The default is 0.92" is a
rumour.

**Every number carries its conditions**: hardware, model, version, workload,
concurrency, and what the author did not control. A number without them
cannot go on the page, and tutor will ask you for them.

**When two sources disagree**, do not choose. Report both with their
conditions and say what would settle it. A disagreement is often the most
useful thing on the page.

**Absence is a finding.** "The docs do not mention X" is worth reporting, and
so is a flag that does not exist at the tag you checked.

**Label every claim**: verified (you opened it), inferred (you reasoned from
something verified, and you say from what), or not checked. Never give an
inferred claim the tone of a verified one. Finish with the "Things I could
NOT verify" section.

## Audit the phase against the bar, and report the gaps

After you have read the phase, check it against the standard it was written
to. Each miss is a line in your note under **Gaps against the standard**, with
what would fill it. Tutor turns those into what it adds.

| The bar | What a gap looks like |
|---|---|
| Failure first | a mechanism is explained with no failure mode, no error text, no log line |
| Measured | a claim with no number, or a number with no conditions |
| Production first | the pattern is shown as it works in a tutorial, not as it runs at scale |
| Exact config | "the timeout setting" instead of the key, its default and its version |
| What it looks like when it breaks | no symptom in logs, metrics or traces |
| Practice | a section with a mechanism nobody can exercise |
| Current | a default, price, limit or version that has moved since it was written |
| Complete on its own | it depends on something no phase has taught yet |

**This is not only about his platform's text.** If the phase is thin on a
mechanism he will meet in production, say so and bring the source that fills
it. The page he reads is the course.

## What tutor needs from you, in the note

- The phase's own content, section by section, so nothing is lost.
- **Gaps against the standard**, as above.
- **Corrections**: what the phase states that is no longer true, with the
  current value, its version and the url.
- **A real failure** on the phase's mechanism: symptom first, the wrong
  theory, the signal that found it, the fix, what changed after.
- **One level below** on the two or three concepts that carry the phase, from
  a rank 1 to 3 source.
- Every url you opened, with the date. Tutor may cite nothing else.
