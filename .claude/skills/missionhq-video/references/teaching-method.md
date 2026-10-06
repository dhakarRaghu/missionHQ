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

## The order inside one concept

The order comes from the Mission HQ tutor (`agents/tutor/writer/section.md`). A rail under the
heading (`ConceptRail` in `video/src/kit-sketch/teach.tsx`) shows the viewer which step they are in.

| Step | What is said | What is on screen |
|---|---|---|
| Claim card | "Concept 1." and the claim in one sentence | "Concept 1 of 5" and the claim, with a highlighter on the key phrase |
| Situation | the running case, where not knowing this costs something | the case in a small diagram and its one surprising number |
| Picture first | what the thing is, what it does, why it exists, with no numbers | a flow or lanes that build up as the voice names each part |
| Think it through | the question; the first thought a reasonable engineer has and why it is reasonable; what it misses; the real question | "First thought" handwritten, then struck through (`Handwrite strikeAt`); "What it misses" in orange; the real question in a box |
| Mechanism | numbered steps, each with its reason ("so", "because") | numbered list on the left, the math written live on the right (`Handwrite`, `Circled`) |
| The number | the one number or failure, with its conditions | chart or table; the source on an `Evidence` sticky note |
| Key points | Remember, The trap, Try this | three `KeyPoint` cards |
| Next | what is still unexplained, and the next concept's question | an "up next" card with that question |

Think aloud. Do not stop the video and wait for the viewer. The viewer follows a person reasoning,
including the wrong first step and how it gets corrected.

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

- `video/src/spec/templates/concept.tsx`: the concept template the pipeline
  draws from a spec. It fixes the order, the step rail, the think-it-through
  layout and the key points. The narration keys must follow the convention in
  `video/SPEC.md`: `k` claim, `s` situation, `p` picture, `q` `t` think it
  through, `m` mechanism, `n` the number, exactly three `r` key points, `h`
  bridge.
- `video/src/kit-sketch/teach.tsx`: `ConceptRail`, `Handwrite` (live writing
  with a pen, `strikeAt`), `Circled`, `Tick`, `KeyPoint`.
- `video/examples/ep12/`: a full real episode as narration and spec.

## A long course video, told like an episode (2026-10-06)

The owner watches course videos to understand a course phase he is reading.
So a course video keeps the lesson's full depth: every concept, the
mechanism, the number and the failure. What it takes from the YouTube
episodes is the way the story is told, because that is what made them easy
to follow:

- One running case from the cold open to the payoff, owned by the viewer
  ("your support agent"). Every concept starts from what just happened in it.
- A cold open that tells the case's failure with its numbers and asks one
  question. The payoff answers it with the video's own numbers.
- A bridge at the end of every concept: what this concept changed in the
  case, and what is still wrong, so the next question follows.
- The think-it-through in every concept, with the fixed phrases.
- No thumbnail, no description, no end-screen space: the video is for
  learning, not for an audience.

Mission HQ makes these automatically after a course phase is written:
`docs/video-pipeline.md` in the Mission HQ repo, and the `missionhq-video`
skill in that repo (`.claude/skills/missionhq-video`).
