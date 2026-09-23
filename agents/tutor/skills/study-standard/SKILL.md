# The study standard

How a fact is stated on a page he will act on. It comes from the standard his
own courses are written to (`.claude/skills/study`). You cannot load those
files, so the parts that decide your work are here.

**What the standard is for.** Rigour is how a teacher earns the right to be
brief. Hunter checked ten things so that you can state one plainly. The
standard governs *how* you state what you teach. It never decides *how much*
you teach: a sourced fact that serves no concept stays out of the lesson.

## How a fact is stated

- **A number keeps its conditions**, in the same sentence: "up to 23x against
  static batching, OPT-13B on one A100 40GB", never "23x faster".
- **A default keeps where it lives**: the key, the value, the version it was
  read at. "`gpu_memory_utilization` is 0.92 at v0.29.0."
- **Teach the current value as the plain fact.** Not the old value with a
  correction beside it, and not the release it changed in. One exception: when
  he will meet the old value in tutorials and be misled, say so in one
  sentence.
- **Carry hunter's labels.** Verified stays verified. Inferred is written as
  inferred, in words. Not checked is left out. You may never promote a label.
- **When the note reports a disagreement, teach its explanation**, not the
  disagreement. "The format request in the prompt costs accuracy, and the
  decoder adds little" is the lesson. Which group said what, and when, goes in
  an evidence note or nowhere.

## Where evidence lives on the page

The mechanism is the lesson. The citation is the receipt.

```
<p>The freeze is one forward pass long. With a 24,000-token prompt at 0.03ms
a token, that is 720ms in which no stream gets a token.</p>

<details class="evidence"><summary>Evidence</summary>
<p>Measured on GPUs rather than simulated: mixing an unchunked prefill into a
decode batch raised time between tokens 28.3x
(<a href="…">Sarathi-Serve</a>, section 3).</p>
</details>
```

One evidence note per concept is usual, under the claim it supports. He can
open it the day he wants to check. `write_lesson` counts how many of your
teaching sentences are about a source rather than the mechanism, and how many
name a year, and sends the page back when it reads like a review.

## What does not go in

- A fact the note cannot support. Not softened, not hedged: out.
- Anything on the note's "Things I could NOT verify" list. There is no
  "could not verify" section on the page: he asked for it off, and a fact too
  weak to state plainly is too weak to teach. It goes in your report.
- A url the note does not mark as opened. Copy urls from the note; never
  rebuild one from memory.
- Whatever the note's **Leave out** section names, and anything else that
  serves none of the lesson's concepts.
