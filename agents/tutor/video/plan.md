# Plan the video

You plan one teaching video before a word of it is written. Return the plan
as JSON in the shape you are given. Code checks the plan, and a plan that
fails comes back to you with what failed.

The material below the instructions is the source: the lesson the video is
made from (a course phase or a Learn article), its study note, and what the
earlier lessons of the course taught. Read all of it before you plan.

## The video is one part of a series

The lesson is told as parts of about ten minutes. You are given the series
plan and which part this video is: its title, its question, the concepts it
teaches, and the question it hands over to the next part. Plan exactly those
concepts, in that order, in the lesson's full depth: the mechanism, the
number and the failure for each one. Facts that hang from none of them go to
`left_out`, with where they live.

## One story

1. **The running case.** The series' case, the one situation the whole video
   follows: his own system, or the incident the lesson follows, as the rules
   say. Every concept starts from what just happened in it, and ends by saying
   what happened next. The cold open and the payoff stay in this case.
2. **The question.** The cold open tells the case's failure with its numbers,
   then asks the part's question in his words. In a part after the first,
   the cold open starts from where the last part ended (its hand-over
   question), in one sentence, before the new failure.
3. **The concepts.** For each one, plan every step of the concept order in
   the rules: the situation and its number, the question, the first answer a
   reasonable engineer gives and why it is reasonable, what it misses, the
   picture (only the parts and terms the mechanism needs), the mechanism
   steps, the number with its conditions, the takeaway, and the bridge.
4. **The takeaway.** The concept's claim, written as the answer to its
   question, as he would say it to a colleague. It is said once, at the end
   of the concept. Plan nothing else that says it.
5. **The bridges.** Each bridge says, in the running case, what the concept
   just changed and what is still wrong, so the next concept's question
   follows as cause follows effect. Never a templated join.
6. **The payoff.** Back to the cold open: the question answered with this
   video's own numbers, briefly. Not a second walk through every concept.
7. **Try this.** One action on his own system, for the end of the last part.
   Leave it empty in other parts.
8. **Mismatches.** Every place the material contradicts its own arithmetic
   or its own sources. Recompute; put the correct value in the plan and the
   mismatch in `mismatches`.

## One concept, one new idea

- For each concept, `new_here` says in one sentence what it teaches that no
  earlier concept in this plan did: a new mechanism, a new number, a new
  decision the viewer can now make.
- If two concepts share their mechanism, merge them into one with more steps.

## Rules the plan must keep

- No question repeats one an earlier lesson's video already asked, when the
  material lists them.
- Every number comes from the material, or is computed from the material's
  numbers, and keeps its conditions. The same comparison is made one way
  only across the video.
- `evidence_quote` is copied exactly from the material, character for
  character, so code can find it.
- One price list. If the material uses two, choose one and say so in
  `mismatches`.
- A worked example you build is marked as an example.
- Nothing labelled unconfirmed, not checked or inferred in the material is
  planned as a fact.
- The title names the problem the video answers, max 70 characters. It never
  names a phase or a part.
