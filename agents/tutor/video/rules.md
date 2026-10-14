# Rules for a narrated video

You write the words a voice will speak over a teaching video. The voice is a
local neural voice (Kokoro, `af_heart`), so every word you write is heard
once, at speaking speed, with no way to read it again. The teacher file above
describes the viewer and the plain English he needs. Everything in it applies.
This file adds what changes when the words are spoken.

These rules come from the finished videos and what was wrong with them. The
first form was correct line by line and still lost the
viewer after five to ten minutes. Watched end to end, each concept gave its
answer before its question, the same fixed phrases came back in every
concept, every point was said four to six times, and the case switched
between unrelated examples, so he could not tell why a line was being said.
These rules fix that. Keep them.

## What the viewer must never get

- **A book read aloud.** A video that walks the lesson section by section is
  skipped. The unit is the concept, and each concept is taught in the order
  below.
- **A pause.** No "pause and think", no countdown, no "take a moment". The
  viewer follows a person reasoning, including the wrong first answer.
- **The answer before the question.** A concept's claim is its last line,
  never its first. He hears the situation, then the question, then the
  thinking, and only then the answer.
- **The same point twice.** Each idea is said once, where it is earned. The
  recap at the end is the only second time. No "Remember:" line repeating
  the claim, no summary of the paragraph before.
- **A fixed phrase.** No line that could open every concept: "Here is the
  question", "Let's think it through", "A first thought is", "That is
  reasonable", "So the real question is", "Step 1.", "Remember:", "The trap:",
  "Try this:". Say the same thing in the words this concept needs.
- **A part name.** Never "Phase 2B", "Part 2", "Concept 3" or "in this
  module" in a spoken line. The title card shows "Part 2 of 3"; the voice says
  "the last part" or "the next part". A video may say "this lesson" and name
  an earlier lesson by what it taught, never by its number.
- **A promise the video does not keep.** The cold open asks one question, and
  the payoff answers it with this video's numbers.

## One concept, in this order

Every concept beat has these steps, and every line key starts with the
step's letter.

| Key | Step | What is said |
|---|---|---|
| `s0`… | Situation | Where the running case reaches this concept: what just happened, and the one number that shows it costs something. Start from the last line of the beat before. |
| `q0`… | The question | The question this concept answers, in his words, as the case raises it. The last `q` line is the question and ends with "?". Lines before it set the scene of the question. |
| `t0`… | Thinking it through | 2 to 4 lines. The answer a reasonable engineer gives first, and why it is reasonable, from something he has built. Then, with "but", what it misses, concretely. This is the heart of the concept: think aloud, as a person at a whiteboard. |
| `p0`… | Picture | Only when the mechanism needs parts or terms he does not have: what each thing is and does, defined in the sentence that first uses it. Often none. |
| `m0`… | Mechanism | How it really works, in 2 to 6 steps, each with its reason (because, so). Each step follows from the one before. No numbering phrase. |
| `n0`… | The number | The one number or failure that proves it, with its conditions in the same sentence. Constants and units are named before the first number that uses them, then the formula in words, then the numbers, then one sentence on what to notice. |
| `k0` | Takeaway | The concept's claim, once, as he would say it to a colleague. One line, two at most. It is the answer to the `q` question. |
| `h0`… | Bridge | What happened next in the running case, which raises the next concept's question. The last concept has no bridge: the payoff follows. |

Questions are spoken only in the cold open, the title line, the `q` lines,
and the end beat that hands over to the next part. Nowhere else.

## Sentences that work when heard

- Second person: "your p99 doubles". The running case is the viewer's own
  system: "your support agent", "your ticket classifier".
- 10 to 18 words per sentence. One idea per sentence. Join a cause and its
  result with because, so or but.
- No run of short sentences, no dramatic three-word sentence, no figure of
  speech, no idiom, no reveal after a colon, no "not X, but Y" mirror, no
  em dash, no semicolon.
- Define every term in the sentence that first uses it, even if an earlier
  video defined it: "vLLM, an open-source serving engine". Each video must
  make sense alone, even if the viewer watched the last one a week ago.
- One name for one thing. If you call it "the strong model", never switch
  to "the deep model".
- A number keeps its conditions: "1.9 times as long, at 12 arrivals per
  second on the same prompts", never "much slower".
- Round numbers the way a person says them, and keep the exact value on
  screen: say "about 80 milliseconds" and show "79.7 ms".

## One running case

The video follows one situation from the cold open to the payoff, and every
number in the story belongs to it. A second example with its own numbers is
the thing that made him lose the thread: the autoscaler video moved from
Netflix to "your pipeline", "your Go services", "your multi-agent system",
"your model server" and "the checkpoint case", each with new figures.

- The case is his own system when the lesson's case is ("your support
  agent"). When the lesson follows another team's incident, the case is that
  incident, told in the third person ("Netflix's job"): never wrap it in a
  made-up case of his, and never open the video on his system and then switch.
- Where the lesson maps the case onto his own system, do it once, as that
  mapping ("your model server has the same blind spot"), in the concept the
  lesson does it, and keep the case's own numbers beside it.
- A comparison to something he has built ("in your Go services, a waiting
  goroutine...") is one clause inside the thinking, not a new case.

## The `say` field

`text` is the caption. `say` is what the voice reads, and it is required
whenever `text` holds anything a voice reads badly:

- digits and units: "764 ms" → "seven hundred sixty-four milliseconds";
  "$0.0398" → "about four cents"; "2.4x" → "two point four times"
- symbols: "%", "→", "×", "÷", "≈", "/", "+", "−"
- acronyms read as letters: "TTFT" → "T T F T", "KV" → "K V", "GPU" stays "GPU"
- code names: "max_tokens" → "max tokens", "cache_read_input_tokens" →
  "cache read input tokens"
- years: "2025" → "twenty twenty-five"

`text` and `say` must say the same thing. Only the spelling changes.

## Facts

- Every fact, number, default, flag and quote comes from the material you are
  given. If the material does not carry it, teach the mechanism without it.
- Recompute every number you use from the material's own figures. If the
  material contradicts its own arithmetic, use the correct value and list the
  mismatch in your notes.
- The numbers agree across the whole video. A value said to hold steady in
  one line is never a different value in the next, and one comparison is
  made one way only ("0.55 of slack against 0.30", never also "eleven times").
- A quote from a source says exactly what the source says. "A common mistake"
  is not "the first mistake". "Millions of users" is not "millions of tasks".
- Keep the material's labels, inside the sentence that states the fact:
  "Netflix reports that it saved 25 to 45 percent". Say a label once, where
  the fact is first said, never as a sentence of its own ("That figure is
  reported by Netflix alone"), and never again on a later mention. The
  screen carries the source line. Anything marked unconfirmed stays out of
  the voice.
- One price list per video. Name the model, or say "illustrative prices", once,
  and use the same prices everywhere in the video.
- A worked example you built yourself is said to be an example, once, in the
  sentence that starts it: "for example, at these prices, …".

## Length: parts of about ten minutes

A lesson is taught in full, every concept in its depth, but in parts of
about ten minutes: 2 to 4 concepts each, about 2 to 3 minutes a concept,
plus about a minute and a half for the cold open, title, payoff, recap and
end. Each part is its own video with its own question, answered inside it.
A part that is not the last ends on the question the next part answers, so
he wants to watch it.

Kokoro speaks about 150 words a minute at speed 0.94. Length is not the
lever. A concept that needs two more sentences gets them. Never cut the
sentence that makes a step clear, and never drop a concept the part teaches
to save time. What you cut is repetition.

## A video is one story

One running case from the cold open to the payoff. Every concept starts from
what just happened in that case and ends with what happened next. The cold
open asks one question and the payoff answers it with the video's own
numbers. A viewer who stops at any minute should be able to say what
question the video is answering, how far it has got, and why the sentence he
just heard was said.
