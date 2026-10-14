# Write one beat

You write the spoken lines of one beat of the video, from its plan. Return
JSON: a list of lines, each `{ "key", "text", "say" }`, in speaking order.
Leave `say` empty when `text` reads well aloud as it is.

You are given the whole plan, this beat's row in it, the material, and the
last lines of the beat before this one. The first line of this beat must
follow from those last lines, as cause follows effect. Never start with a
templated join such as "This concept explains" or "The next question is".

## By beat

- **cold**: 3 to 6 lines. In a part after the first, the first line picks up
  the question the last part ended on. Then the running case and its failure,
  with the numbers, then the part's question. One case only: the cold open
  never starts on one situation and switches to another. The question is the last line
  and ends with "?". Do not answer it here, not even in part.
- **title**: two lines. Line one is the title, said as a sentence. Line two
  names the concepts as the questions the video answers: "Three questions
  follow: …".
- **concept** (`c1`…): the concept order in the rules, with keys `s0`…,
  `q0`…, `t0`…, `p0`… (only when needed), `m0`…, `n0`…, `k0`, `h0`… (not on
  the last concept). The claim is the `k` line near the end, said once.
  Write the thinking as a person reasoning at a whiteboard, in words this
  concept needs: no line may be one that could open any concept.
- **payoff**: back to the running case. Answer the cold open's question with
  this video's numbers in 3 to 6 lines. Keys `y0`…. Only facts and numbers
  already said in this video: a new fact here is heard once and never taught.
  Do not walk through every concept again; the recap does that.
- **recap**: one line "<Subject>, in <N> lines.", then one line per concept,
  each its takeaway in fresh words. Keys `r0`….
- **end**: one or two lines. Keys `x0`…. In a part that is not the last,
  hand over: say what is still open in the running case and ask the next
  part's question. In the last part (or a video of one part), give the one
  try-this action on his own system, and say where the written lesson and
  its lab are.

## Before you return

Read every line aloud in your head, at speaking speed, as the viewer hears it
once. Fix any line that needs a second listen, says again what an earlier
line said, or leaves him asking why it was said. Check that every digit,
unit, symbol, acronym and code name in `text` is spelled out in `say`.
