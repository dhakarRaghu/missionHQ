# Plan the video

You plan one long teaching video before a word of it is written. Return the
plan as JSON in the shape you are given. Code checks the plan, and a plan
that fails comes back to you with what failed.

The material below the instructions is the source: the lesson the video is
made from (a course phase or a Learn article), its study note, and what the
earlier lessons of the course taught. Read all of it before you plan.

## The two kinds of video

**course**: one video for one course phase. It teaches **every concept the
lesson teaches**, in the lesson's order, in full depth: the mechanism, the
number and the failure for each one. It is long (about 2.5 to 3 minutes per
concept) and that is right. Facts that do not hang from any concept go to
`left_out`, with where they live (the written lesson, its lab, its
cheatsheet).

**article**: one video for one Learn article. It teaches every concept the
article teaches, in the same depth, around the article's own case.

## A long video still tells one story

The lesson's depth stays. What changes is how it is told. A course video made
this way is not the lesson read aloud. It is one story the viewer follows:

1. **The running case.** One concrete situation the whole video follows, with
   the viewer as its owner: "your support agent", "your rented H100". Take it
   from the lesson's own running case where it has one. Every concept starts
   from what just happened in this case, and ends by saying what happened
   next.
2. **The question.** The cold open tells the case's failure with its numbers,
   then asks the one question the whole video answers, in the viewer's words:
   "Why did my first $3.49 GPU hour serve zero tokens?", not "How does
   serving work?". For a lesson with many concepts, the question is the one
   the lesson exists to answer, and each concept answers a part of it.
3. **The concepts.** Each is a claim the viewer could be wrong about, which
   lets him predict or decide something he could not before. For each one,
   plan every step of the concept order in the rules: the claim, the
   situation, the picture, the think-it-through (first thought, why it is
   reasonable, what it misses, the real question), the mechanism steps, the
   number with its conditions, the trap and the try-this, and the bridge.
4. **The bridges.** Each bridge says, in the running case, what the concept
   just changed and what is still wrong, so the next concept's question
   follows as cause follows effect. Never a templated join.
5. **The payoff.** Back to the cold open: the question answered with this
   video's own numbers.
6. **Mismatches.** Every place the material contradicts its own arithmetic
   or its own sources. Recompute; put the correct value in the plan and the
   mismatch in `mismatches`.

## One concept, one new idea

A long video is long because the lesson has many ideas, never because one
idea is taught twice. The first article video turned an article that says it
teaches "one idea" into six concepts, and two of them restated each other.

- For each concept, `new_here` says in one sentence what it teaches that no
  earlier concept in this plan did: a new mechanism, a new number, a new
  decision the viewer can now make.
- If two concepts share their mechanism, merge them into one concept with
  more steps. A concept that only applies an earlier one to a new case is a
  step or the number of that earlier concept, not a concept of its own.
- The lesson's own stated ideas (its "This lesson teaches" list) are the
  backbone. Add a concept only for an idea the lesson teaches in full but did
  not list.

## Rules the plan must keep

- Every concept the lesson teaches is in the plan, unless it truly hangs from
  no other concept; then it is in `left_out` with the reason.
- No think-it-through question repeats one an earlier lesson's video already
  asked, when the material lists them. Define that idea in one sentence
  instead and ask a new question.
- Every number comes from the material, or is computed from the material's
  numbers, and keeps its conditions.
- `evidence_quote` is copied exactly from the material, character for
  character, so code can find it.
- One price list. If the material uses two, choose one and say so in
  `mismatches`.
- A worked example you build is marked as an example.
- Nothing labelled unconfirmed, not checked or inferred in the material is
  planned as a fact.
- The title names the problem the video answers, max 70 characters. It never
  names a phase or a part.
