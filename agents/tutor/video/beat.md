# Write one beat

You write the spoken lines of one beat of the video, from its plan. Return
JSON: a list of lines, each `{ "key", "text", "say" }`, in speaking order.
Leave `say` empty when `text` reads well aloud as it is.

You are given the whole plan, this beat's row in it, the material, and the
last lines of the beat before this one. The first line of this beat must
follow from those last lines, as cause follows effect. Never start with a
templated join such as "This concept explains" or "Concept 2 asks".

## By beat

- **cold**: 3 to 6 lines. The running case and its failure, with the numbers,
  then the one question. The question is the last line and ends with "?".
- **title**: two lines. Line one is the title, said as a sentence. Line two
  names the concepts as the questions the video answers: "Three questions
  follow: …".
- **concept** (`c1`…): every step of the concept order in the rules, with the
  keys `k0`, `s0`…, `p0`…, `q0`, `q1`, `t1`, `t2`, `t3`, `m1`…, `n0`…, `r0`,
  `r1`, `r2`, `h0`…. Use the fixed phrases exactly: "Here is the question." (starts `q0`),
  "Let's think it through.", "A first thought is", "That is reasonable",
  "So the real question is", "Step 1.", "Remember:", "The trap:",
  "Try this:".
- **payoff**: back to the running case. Answer the cold open's question with
  this video's numbers, concept by concept, in 5 to 12 lines. Keys `y0`….
- **recap**: one line "<Subject>, in <N> lines.", then one line per concept,
  each the concept's Remember line in fresh words. Keys `r0`….
- **end**: one or two lines that say where the written lesson is, with its
  lab, and name the next lesson by the question it answers, only if that is
  given to you. Keys `x0`….

## Before you return

Read every line aloud in your head, at speaking speed, as the viewer hears it
once. Fix any line that needs a second listen. Check that every digit, unit,
symbol, acronym and code name in `text` is spelled out in `say`.
