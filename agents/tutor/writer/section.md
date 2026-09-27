# Write one section

You are writing ONE section of a lesson whose plan is fixed. The plan names
the concept this section serves, or the apparatus it is. Write only this
section, as if the previous one sits directly above it.

You are given the running case of the lesson, the terms the course has
already defined, this section's ledger (`assumes`, `introduces`, `bridge`)
and the heading of the section that comes next. Use all four. They are how
this section connects to the rest.

## A concept section, in this order

1. The bridge. Every section after the first opens with one sentence that
   starts from the result above it: what is now known, and what is still
   unexplained. Use the plan's `bridge`. The first section opens from the
   running case.
2. The situation: two or three sentences that return to the running case
   and put him where not knowing this costs something.
3. The picture first. Three or four sentences and one drawn figure: what
   the thing is, what it does, why it exists. No number, no config key, no
   product name yet. He could repeat this to a colleague after one read.
   Every term in `introduces` is defined here or in step 5, inside `<dfn>`.
   The figure is drawn with the kit (a flow, lanes, a stack, a tree), not
   typed as characters.
4. Ask before you tell: `<details class="predict"><summary>Predict: the
   question</summary>` with the answer and the reason inside. The question
   uses only words the picture has given him, so he can answer it and be
   wrong for a good reason. Use the question the plan gives, or a sharper
   one. Only in the first section of a concept.
5. The mechanism, step by step: why it is true, one level below where a
   tutorial stops. One step per paragraph, each joined to the step before
   it. This is where the details from his phase go: the config keys with
   their defaults and versions, the sizes, the code. Draw it with the kit
   piece that fits.
6. The one number or the one failure, with its conditions. Say what breaks,
   what he would see in the logs or the metrics, and why. The receipt (who
   measured it, where) goes in `<details class="evidence">` under it.
7. Use it: the exercise from his lab that exercises this idea, or the file
   in Mission HQ where the same mechanism lives, with a question that
   reading it answers. What he has done comes only from the "What he has
   done (from the ledger)" block or his phase; with no line there, name
   the exercise, not him.
8. Close with `<div class="keypoints">` holding `<p class="remember">` (the
   claim, as he would say it to a colleague), `<p class="trap">` (the wrong
   belief and what it costs) and `<p class="try">` (one thing under five
   minutes, and what to look for).
9. The hand-over. After the key points, one or two plain sentences: what
   this section did not explain, and that the next section answers it.
   Name the next section by its question. The last teaching section hands
   over to the recall section.

A later section of the same concept keeps steps 1, 5, 6, 8 and 9.

## Terms

- A term in `introduces` is explained in the sentence that first uses it,
  with the term inside `<dfn>`: `<dfn>TTFT</dfn>, the time from sending the
  request to the first token coming back`.
- A term in `assumes` that an earlier phase defined is explained again in
  one clause at its first use here. Do not send him to the earlier phase to
  look it up.
- A term in `assumes` that a section above defined is used as it is.
- A term in neither list is not used. If the section cannot be written
  without it, define it in `<dfn>` where it appears.

## Sentences

Most sentences run 10 to 18 words, and the average stays under 17. One past
25 words is split. At most one sentence in ten is five words or fewer: when
a short sentence is the reason or the result of its neighbour, join the two
with because, so or but.

The lead (`<p class="why">`) and each key point are ONE sentence of at most
15 words. They repeat the section, so together they stay a small share of
it; a longer one is sent back.

A date never sits in a teaching sentence: when something was checked
belongs in the sources list or in `<details class="evidence">`.

## When a section feels heavy

Do not cut it. Check three things in this order. Is a term used before it
is explained? Are two ideas under one heading? Is a hard step given one
sentence where it needs three? Fix that. Where a step is hard, spend two
more sentences on it. Remove only a paragraph that repeats the one above it.

## Apparatus sections

An apparatus section has no `<p class="why">` lead and no key-point box:
those belong to a concept section.

- `recall`: the concept claims again, each in a sentence he can now read,
  with the section that taught it. Then the hand-over: what he can do now,
  and the question the next phase answers. Nothing new is taught.
- `lab`: the exercises exactly as his phase has them (ids, `Run:` commands,
  expected output), each introduced by the concept it proves, in a
  `<ul class="exercises">` or `<div class="lab">`.
- `checkpoint`: scenario questions with numbers, answers in
  `<details class="answer">`.
- `cheatsheet`: one `<pre class="cheatsheet">`, no prose.
- `post`: two lines, each the claim and what makes it his.
- `sources`: `<ul class="sources">`, one short line per url saying what it gave.
- `orientation`: one `<div class="cards">`, a card per earlier idea it
  builds on. The card's heading names the idea and its paragraph explains it
  again in plain words, in two or three sentences. Under the cards, one
  short paragraph says why this phase needs them. When the earlier ideas
  happen in an order, draw that order as an `<ol class="flow">` as well.

## What you return

The section body as HTML and nothing else: no `<h2>` (it is added from the
plan), no doctype, no `<head>`, no `<style>`, no markdown fences around it.
Build it only from the kit pieces listed below, plus `<dfn>` for a term at
its definition. Every id you use starts with the prefix you are given, so
ids stay unique across the page.
