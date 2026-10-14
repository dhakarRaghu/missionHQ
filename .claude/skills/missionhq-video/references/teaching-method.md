# Teaching method for lesson videos

A lesson video must teach, not read. Reading the lesson aloud section by section produces a video
that people skip. This file is the method that a user approved on 2026-10-03, after rejecting three
other forms.

## What was rejected, and why

| Form | What the user said |
|---|---|
| The lesson read aloud, one beat per section | "like a book reader … I just skip it" |
| Generic devices: a whiteboard tutor, or a tutor-and-student dialogue | "not like this, use the teaching method we use in Mission HQ, concept wise" |
| "Pause and think" cards with a countdown | "don't give me this or pause, just give the thinking" |

## The unit is the concept

A concept is a claim the viewer could be wrong about, which lets them predict or decide something they
could not before. A written lesson usually lists its concepts near the top; when it does not, use its
numbered sections. Each concept becomes one beat (one YouTube chapter).

Measured on the first two full builds (2026-10-03), Kokoro `af_heart` at speed 0.94:

| Video | Concepts | Length | Per concept |
|---|---|---|---|
| Inference Phase 1 | 6 | 20:33 | about 3:00 |
| Inference Phase 2 (two lessons) | 10 | 27:31 | 2:15–2:45 |

Plan about 2.5–3 minutes a concept, plus about 1.5 minutes for cold open, title, map and recap.

Facts, numbers and config keys stay only when they hang from a concept. The rest goes into the
YouTube description ("teach the core, list the rest").

## The order inside one concept (story order, spec version 2)

The first order (claim card, rail, think it through with fixed phrases, key points) taught
correctly and still lost the viewer: the answer came before the question, the same phrases came
back in every concept, and the claim was said three times. Since 2026-10-14 a concept asks first
and answers once:

| Step | What is said | What is on screen |
|---|---|---|
| Situation (`s`) | where the running case reaches this concept, with the number that makes it matter | the case in a small diagram and its one surprising number |
| Question (`q`) | the question, in his words; the last `q` line ends with "?" | the question, handwritten large |
| Thinking it through (`t`) | the first answer a reasonable engineer gives, why it is reasonable, then with "but" what it misses; in this concept's own words, no fixed phrase | "First answer" handwritten, struck through at `misses_at`; "What it misses" in orange |
| Picture (`p`, optional) | the parts and terms the mechanism needs | a flow that builds up as the voice names each part |
| Mechanism (`m`) | how it works, each step with its reason; no "Step N." | numbered items on the left, the math written live on the right |
| The number (`n`, optional) | the number that proves it, with its conditions | chart or table; the source line carries the labels |
| Takeaway (`k`) | the claim, once, now earned | the claim card, "2 of 3", highlighter on the key phrase |
| Bridge (`h`) | what happened next, which raises the next question | a small panel |

No step rail. The recap is the only second time a claim is said.

## Narration rules (from the Mission HQ teacher)

- Talk to the viewer in the second person: "your p99 doubles".
- Sentences of 10–18 words. Join a cause and its result with "because", "so" or "but". A run of very
  short sentences sounds like a list of facts.
- No dramatic short sentences, no figures of speech, no questions except the one in "think it through".
- Show the behaviour before naming it. Show the wrong belief before the right one.
- Name every constant and its unit before the first number that uses it. Then the formula in
  words, then the numbers, then one sentence on what to notice.
- Every number comes from the lesson, with its conditions.

## Check the lesson before teaching it

A trap line or a worked number in the lesson can be wrong. Recompute every number the video shows,
and report each mismatch to the user. The first four builds found eight:

| Lesson said | Its own numbers | What the video said |
|---|---|---|
| 80% hit rate on the cheap model is the cascade break-even (3B) | break-even is 80% *escalation* | a trap built from the lesson's own cost line |
| the 6 → 12 arrivals run "tripled" TTFT (2A) | 867 → 1,674 ms, 1.9x | "almost twice" |
| a 512-token budget "cost 25% throughput" (2B) | its evidence says "at most ~25% overhead" | "at most about 25 percent" |
| a model "gained 1.2" with constraints (2B) | its evidence note says "+1.2 without" | left out |
| 79.8 ms (2B) | 2,045 × 0.03 + 18.36 = 79.7 | "about 80 ms" |
| a coin flip at 0.35 escalation shows 69.3% of deep-only cost (3B) | at the lesson's 5x ratio, 35% escalation costs 55%; 69.3% is a simulator run with unstated prices | showed 85% and 69%, never tied to 0.35 |
| a 5-request window fires at request 50 (3B) | its own formula gives 5 × 0.48 / 0.98 ≈ 2.4, so request 52 at the 0.50 floor | taught the window as a trade-off, without that number |
| output-length predictors miss by about 100 tokens (3B) | the lesson's sources say this has no named source | left out of the video and the description |

The worked example below is the first of these.
Example: the Phase 3B lesson said "a team with an 80% hit rate on the cheap model is sitting exactly
at the point" where a cascade stops saving. That is wrong: an 80% hit rate means 20% escalation,
which costs 1 + 0.2 × 5 = 2, or 40% of deep-only. The break-even is 80% escalation. The video used a
correct trap built from the lesson's own mechanism, and the error was reported to the user.

## Files in Mission HQ

- `video/src/spec/templates/concept.tsx`: the concept templates the pipeline
  draws from a spec. `ConceptBeatV2` is the story order above (spec version
  2, keys `s q t p m n k h`); `ConceptBeat` is the first order (version 1),
  kept for the ep12 example and videos made before.
- `video/src/kit-sketch/teach.tsx`: `ConceptRail`, `Handwrite` (live writing
  with a pen, `strikeAt`), `Circled`, `Tick`, `KeyPoint`.
- `video/examples/ep12/`: a full real episode as narration and spec (version 1);
  `ep12-v2/` and `stress-v2/` are the same in version 2, written by `examples/v2.py`.

## A lesson told as parts of about ten minutes (2026-10-14)

The owner watches these videos to understand a phase he is reading, so they keep the lesson's
full depth: every concept, the mechanism, the number and the failure. One video per lesson ran
20 to 49 minutes and was not watched to the end, so the lesson is told as a series: a series task
plans parts of 2 to 4 concepts, each part is its own video with its own question, and every part
but the last ends on the question the next part answers. What each part takes from the YouTube
episodes:

- One running case from the cold open to the payoff, owned by the viewer ("your support agent").
  Every concept starts from what just happened in it. No second example with its own numbers.
- A cold open that tells the case's failure with its numbers and asks one question. The payoff
  answers it with the video's own numbers, briefly.
- A bridge at the end of every concept: what it changed in the case, and what is still wrong.
- Source labels said once, inside the sentence, and carried on screen; never a sentence of their own.
- No thumbnail, no description, no end-screen space: the video is for learning, not for an audience.

Mission HQ makes these when he presses "Generate video": `docs/video-pipeline.md` in the Mission HQ
repo, and the `missionhq-video` skill in that repo (`.claude/skills/missionhq-video`).
