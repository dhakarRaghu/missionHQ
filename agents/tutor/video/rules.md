# Rules for a narrated video

You write the words a voice will speak over a teaching video. The voice is a
local neural voice (Kokoro, `af_heart`), so every word you write is heard
once, at speaking speed, with no way to read it again. The teacher file above
describes the viewer and the plain English he needs. Everything in it applies.
This file adds what changes when the words are spoken.

These rules come from twelve finished episodes and the reviews that corrected
them. Each one is here because a video broke it and had to be rebuilt.

## What the viewer must never get

- **A book read aloud.** A video that walks the lesson section by section is
  skipped. The unit is the concept, and each concept is taught in the order
  below.
- **A pause.** No "pause and think", no countdown, no "take a moment". The
  viewer follows a person reasoning, including the wrong first step.
- **A part name.** Never "Phase 2B", "Part A", "Concept 3" or "in this
  module" in a spoken line. (The screen's small "3 of 6" count on a claim card
  is drawn by the template and is allowed.) A video may say "this lesson" and name an
  earlier lesson by what it taught, never by its number.
- **A promise the video does not keep.** The cold open asks one question, and
  the payoff answers it with this video's numbers.

## The concept, in this order

Every concept beat has these steps, and every line key starts with the step's
letter.

| Key | Step | What is said |
|---|---|---|
| `k0` | Claim | The concept's claim in one sentence: what is true, with its reason. |
| `s0`… | Situation | Where the running case meets this concept, with its one surprising number. |
| `p0`… | Picture | What the thing is, what it does and why it exists. Define every new term here, in the sentence that first uses it. No numbers yet. |
| `q0`, `q1` | The question | `q0` starts with "Here is the question." and sets the scene of the question. `q1` asks it, ending with "?", then "Let's think it through." |
| `t1` | First thought | "A first thought is …, because …" A reasonable engineer's answer, with why it is reasonable. |
| `t2` | What it misses | "That is reasonable …, but …" What the first thought does not account for. |
| `t3` | The real question | "So the real question is …" |
| `m1`… | Mechanism | "Step 1. …", "Step 2. …": two to six steps, each with its reason (because, so). |
| `n0`… | The number | The one number or failure, with its conditions in the same sentence. Constants and units are named before the first number that uses them; then the formula in words; then the numbers; then one sentence on what to notice. |
| `r0` | Remember | "Remember: …" the claim again, as the viewer would say it to a colleague. |
| `r1` | The trap | "The trap: …" the specific wrong move, with its cost. |
| `r2` | Try this | "Try this: …" one action on the viewer's own system. |
| `h0`… | Bridge | What happened next in the running case, which leads to the next concept's question. The last concept's bridge leads to the payoff. |

Questions appear only in the cold open, the title line, and `q0`/`q1`. Nowhere else.

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
- A quote from a source says exactly what the source says. "A common mistake"
  is not "the first mistake". "Millions of users" is not "millions of tasks".
- Keep the material's labels. Verified stays verified, inferred is said to be
  inferred, and anything marked unconfirmed stays out of the voice.
- One price list per video. Name the model, or say "illustrative prices", once,
  and use the same prices everywhere in the video.
- A worked example you built yourself is said to be an example: "for example,
  at these prices, …".

## Length

- A course video teaches every concept of its lesson in full depth: about
  2.5 to 3 minutes per concept, plus about 2 minutes for the cold open,
  title, payoff, recap and end. A ten-concept phase is a thirty-minute video,
  and that is right.
- An article video: the same depth for the article's concepts, usually 6 to
  15 minutes.
- Kokoro speaks about 150 words a minute at speed 0.94.

Length is not the lever. A concept that needs two more sentences gets them.
Never cut the sentence that makes a step clear, and never drop a concept the
lesson teaches to save time.

## A long video is still one story

The depth comes from the lesson; the way it is told comes from the episodes
that worked. One running case from the cold open to the payoff. Every concept
starts from what just happened in that case and ends with what happened next.
The cold open asks one question and the payoff answers it with the video's
own numbers. A viewer who stops at any minute should be able to say what
question the video is answering and how far it has got.
