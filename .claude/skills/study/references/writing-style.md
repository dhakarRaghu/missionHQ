# Writing style. Mandatory for the material and for chat replies

Write for a reader whose first language is not English. Keep the ideas advanced. Make the English simple.

This file wins over every example in `quality-bar.md`.

## Sentence rules

- Keep sentences under 20 words. Split long ones.
- One idea per sentence.
- Use common words. If a simpler word exists, use it.
- No metaphors and no images.
- Do not use em-dashes or brackets in prose. Write a new sentence instead.
  - Allowed: one em-dash as a separator in a heading, such as `## 6.1 — Capacity planning`.
  - Allowed: em-dashes inside code blocks and program output.
  - Allowed: a reference entry in the form `**Title** — URL`.
- Do not use semicolons in prose. Write two sentences.
- Use active voice. Say "the gateway sends the request", not "the request is sent".
- Use the same word for the same thing every time. Do not use synonyms.

## Structure rules

- Give the answer in the first sentence. Then explain it.
- Explain every technical term the first time you use it. One short sentence is enough.
- Use lists, tables, and numbered steps instead of long paragraphs.
- End a long explanation with a one-line summary.

## Task rules

- For learning: give the big picture first, then details.
- For code: explain the purpose and the flow before the syntax.
- For instructions: give steps in order.
- For decisions: give the recommendation first, then the reasons and trade-offs.
- For troubleshooting: give the likely cause, then how to check it, then the fix.
- For abstract topics: give one simple example, and say where the example stops working.

## Words and phrases to avoid

These caused confusion before:

- leverage, bottleneck, on-ramp, canon, altitude, compounds, plumbing, flywheel
- abstract noun phrases, such as "the demo-to-competence layer"
- idioms, such as "earns its place", "might as well not exist", "setting money on fire", "under the hood", "the elephant in the room", "a silver bullet"
- empty emphasis, such as "simply", "just", "easily", "obviously", "the hard truth"
- personification, such as "the GPU switches personalities"

Replacements:

| Avoid | Write |
|---|---|
| setting money on fire | wasting money |
| the bottleneck | the slowest step, or the part that limits throughput |
| under the hood | inside, or in the implementation |
| earns its place | is needed because ... |
| costs a week | give the measured cost, or say the cost is not measured |

## Examples

WRONG:

> Prefix caching is a silver bullet — it slashes TTFT (sometimes by 80%+) and your bill, so leverage it everywhere.

RIGHT:

> Prefix caching reuses work the server already did for the same prompt start. It can cut time to first token. The saving depends on how much of the prompt repeats. Measure it with E4 before you rely on it.

WRONG:

> The same production-trace study reported that the top 29 clients sent 90% of requests.

RIGHT, when the two facts came from two papers:

> ServeGen, a study of Alibaba traces, reported that 29 of 2,412 clients sent 90% of the requests.

## Evidence language

- Verified: "Verified from the paper, Table 4." "Measured on the author's machine on 2026-09-17."
- Inferred: "Inferred from the code, not run." "Inferred from the documented defaults. Time it on your own system."
- Not checked: "Not checked." Then say what check would confirm it.
- When a first draft was wrong, say so in one plain sentence, and show the evidence that corrected it.

## Checks the audit script runs

- Prose sentences over 20 words are listed. Any over 32 words must be split.
- Em-dashes in prose lines are listed.
- Semicolons in prose lines are listed.
- Words from the avoid list are listed.

Fix every listed line, or leave it only when it is a quotation.
