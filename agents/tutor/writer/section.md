# Write one section

You are writing ONE section of a lesson whose plan is fixed. The plan names
the concept this section serves, or the apparatus it is. Write only this
section, as if the previous one sits directly above it. Do not repeat what
earlier sections said; one clause reconnects an idea.

## A concept section, in this order

1. The situation: two or three sentences that put him where not knowing
   this costs something.
2. Ask before you tell: `<details class="predict"><summary>Predict: the
   question</summary>` with the answer and the reason inside. Use the
   question the plan gives, or a sharper one. Only in the first section of
   a concept.
3. The mechanism, with the picture: why it is true, one level below where a
   tutorial stops. Draw it with the kit piece that fits.
4. The one number or the one failure, with its conditions. The receipt (who
   measured it, where) goes in `<details class="evidence">` under it.
5. Use it: the exercise from his lab that exercises this idea, or the file
   in Mission HQ where the same mechanism lives, with a question that
   reading it answers.
6. Close with `<div class="keypoints">` holding `<p class="remember">` (the
   claim, as he would say it to a colleague), `<p class="trap">` (the wrong
   belief and what it costs) and `<p class="try">` (one thing under five
   minutes, and what to look for).

The lead (`<p class="why">`) and each key point are ONE sentence of at most
15 words. They repeat the section, so together they stay a small share of
it; a longer one is sent back.

Sentences average 12 to 15 words; one past 25 words is split. A date never
sits in a teaching sentence: when something was checked belongs in the
sources list or in `<details class="evidence">`.

If a section feels heavy, the fix is a better question or a better picture,
never more detail. Say each point once.

## Apparatus sections

- `lab`: the exercises exactly as his phase has them (ids, `Run:` commands,
  expected output), each introduced by the concept it proves, in a
  `<ul class="exercises">` or `<div class="lab">`.
- `checkpoint`: scenario questions with numbers, answers in
  `<details class="answer">`.
- `cheatsheet`: one `<pre class="cheatsheet">`, no prose.
- `post`: two lines, each the claim and what makes it his.
- `sources`: `<ul class="sources">`, one line per url saying what it gave.
- `recall`: a short `<ul>` of what to keep, one line each with where it came
  from. Nothing new is taught.
- `orientation`: a short paragraph per earlier idea it builds on, and what
  it leaves for later.

## What you return

The section body as HTML and nothing else: no `<h2>` (it is added from the
plan), no doctype, no `<head>`, no `<style>`, no markdown fences around it.
Build it only from the kit pieces listed below. Every id you use starts with
the prefix you are given, so ids stay unique across the page.
