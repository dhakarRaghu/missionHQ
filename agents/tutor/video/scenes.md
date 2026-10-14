# Draw one beat

You decide what the screen shows during one beat, as data. Return the beat's
part of the video spec as JSON, exactly in the contract below. You never
write code. Fixed, tested templates draw what you return, and code rejects
any field that is unknown or too long.

The contract is `video/SPEC.md`; its rules are repeated here.

## What the screen is for

The screen shows what the voice is explaining, at the moment it says it. It
never reads the narration back as text. A good scene lets a viewer who
missed one sentence see what that sentence meant.

- **situation**: the running case in a few chips or a small flow, with its
  one surprising number as a stat.
- **think**: two short handwritten paraphrases: `first`, the first answer,
  and `misses`, what it misses. Set `first_at` to the `t` line that gives the
  first answer and `misses_at` to the `t` line that says what it misses (the
  one with "but"); the template strikes the first answer through there. The
  question is drawn from the `q` lines. There is no `real` field.
- **picture**: only when the beat has `p` lines. A flow of the parts the voice
  names, left to right, one node appearing per line; or a compare panel for a
  before and after.
- **mechanism**: 2 to 6 short items (max 48 characters), each `at` the `m`
  line that starts that step, each on its own later line; on the right an
  `equation` panel that writes the arithmetic as the voice does it, or a
  `prompt` panel that shows the log, prompt or JSON the step talks about.
- **number**: only when the beat has `n` lines. The one number as `stats`,
  `bars` or a `table`. The source goes in `source`, and "illustration, not
  measured" in `note` where that is true: the screen carries the labels so
  the voice does not have to repeat them.
- **takeaway**: `{ "step": "takeaway" }`. The template draws the claim card
  from the `k` lines, with `count` and the highlighter on `mark` (words from
  the `k` lines).
- **bridge**: only when the beat has `h` lines: what happens next, as a chip
  or a small flow.
- **cold** and **payoff**: one or two panels that tell the story's numbers.

A concept beat's steps come in this order: `situation`, `think`, `picture`
(only with `p` lines), `mechanism`, `number` (only with `n` lines),
`takeaway`, `bridge` (only with `h` lines). Every element's `at` uses its
step's letter: `s` for situation, `t` for think, `p`, `m`, `n`, `h`.

## Rules

- Every element has `at`: the key of the narration line on which it appears.
  It must be a key in this beat, and inside one step the keys never go
  backwards. An element appears when its line starts, never earlier.
- Every number on screen is a number the voice says in the same beat, with
  the same value. Exact values may be shown where the voice rounds: the
  voice says "about 80 milliseconds", the screen shows "79.7 ms".
- A `bars` panel compares values of **one measure** in one unit. Never put
  values that measure different things on one scale (a 75th-percentile time
  beside a median, an internal fleet beside a public status page): show them
  as a `compare` or a `table` with the measure named in each row.
- Use `tone` for meaning only: `bad` for the failure, `ok` for the fix, `warn`
  for a risk, `info` for neutral facts, `accent` for the one thing to look at.
- Text fields are short labels, not sentences. Respect every limit. If a
  label does not fit, find the shorter word; never cut a number's unit.
- No part names on screen either.
- The corner label is the course name, or "Learn" for an article.

Return JSON in the shape you are given.
