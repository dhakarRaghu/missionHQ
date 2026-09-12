# Write the daily lesson

Use every morning, once hunter's digests are in. Produces two files — the
lesson and its page — and a score you report in your answer.

## The topic is the thread — do not invent one

Every digest you are given is on the same topic. The selection guarantees it.
So your job is not to find a clever connection; it is to teach that one topic
properly, using the sources as evidence.

Use them against each other: where they agree, where they contradict, what
one covers that the others skip, which one has the real numbers. That is what
makes reading three articles worth more than reading the best one.

**Never stretch to connect unrelated material.** On 2026-09-12 a lesson welded
vLLM's scheduler to MySQL replication under one clever claim. Both halves were
accurate. He could not follow it: "I'm not able to connect the both topic."
The selection no longer hands you unrelated sources — and if it ever does, say
so plainly and teach the strongest one rather than building a bridge.

**Teach the mechanism, not the product.** A source deep on one tool is
evidence about how that class of system works. He said it directly: "I'm not
a fan of vLLM to learn this in depth — we will learn LLM or applied AI." Name
the tool as the example, never as the subject.

Write one sentence for yourself before you start: what does he understand at
the end of this that he did not at the start? If you cannot write it, you do
not have a lesson yet.

## When the reading is an incident, use its shape

He asked for this directly: "teach me things faced in production systems, the
solution, and the learning from it." When the day's reading is a postmortem
or an outage report, do not flatten it into an explainer. Walk it:

1. **What broke, as it first appeared.** The symptom on the dashboard at
   3am, not the tidy description written afterwards.
2. **The wrong theory.** What they chased first, and why it was reasonable.
   This is the most useful paragraph in any postmortem and the one most
   summaries drop.
3. **The signal that actually located it.** Which metric, log or trace ended
   the search — and whether he has that signal in his own system today.
4. **The fix**, separated into the thing that stopped the bleeding and the
   thing that stopped it recurring.
5. **What it costs him.** The same failure mode in his own stack, named
   concretely, with the one check he could add this week.

An incident is worth more than an explainer because the price was already
paid. Do not waste it by summarising the conclusion.

## The shape

No fixed template, but every lesson carries these, in roughly this order:

1. **The claim.** Three or four lines. What is true, and why it is not
   obvious. No preamble, no "in today's fast-moving world". Start where the
   substance starts.
2. **The mental model.** How to hold the idea. Plain words. One analogy at
   most, and only if it does real work.
3. **The worked example.** Real code, config, or a traced request path — an
   agent, a service, a data path. It must be something that would actually
   run. A worked example with a `# ...` where the hard part goes is worse
   than none, because the hard part is the lesson. Use the language the
   material is in; he is not reading for a language.
4. **Where it breaks.** The failure mode, the cost, the number. What bites at
   ten times the volume. Most writing stops before this; it is the part he
   will still remember next month.
5. **Fifteen minutes today.** One concrete thing he could try before work.
   Specific enough to start without deciding anything: a file to open, a
   query to run, a parameter to change.
6. **Two things he could post.** One line each: the claim, and what makes it
   his rather than a rehash. Scout turns these into posts; you only supply
   the angle.
7. **Sources.** Every url, with the digest path beside it.

## Write it plainly

He told you straight on 2026-09-12: "make the language simpler, it is kind of
hard for me to digest". He is an engineer — the ideas are not too hard. The
sentences were.

- **One idea per sentence.** If it has two clauses joined by a comma and an
  "and", it is probably two sentences.
- **Define a term the first time you use it, in that sentence.** "the KV
  cache — the attention keys and values the GPU must hold", not "the KV cache"
  and a hope.
- **Short sentences carry hard ideas.** Depth comes from the mechanism, never
  from the sentence length. A dense paragraph does not make the reader feel
  clever; it makes them reread.
- **Say the thing, then explain it.** Claim first, mechanism after.
- **Prefer the concrete noun.** "the relay log file" beats "the buffering
  layer".
- **Cut the throat-clearing.** "It is worth noting that" and "in essence" add
  nothing.
- Read it back once. If a sentence needs a second pass to parse, split it.

Jargon is fine — he wants the real words — as long as each one is unpacked
the first time it appears.

## Length

800 to 1,200 words for the markdown. Padding is the tell: if a paragraph
restates the one above in a different register, cut it. Cut, not tighten.

The test for each paragraph is the same one `write-article` uses: does he
know something after it that he did not know before it?

## The page, and the diagram

Write the same lesson as `<slug>.html`, self-contained:

- One `<style>` block. System font stack. A readable column, around 70
  characters. It is rendered on both light and dark backgrounds, so set your
  own background and text colour explicitly rather than inheriting.
- **Nothing loaded from the internet.** No CDN script, no web font, no remote
  image. The frame it renders in blocks outside loads, so anything remote
  simply will not appear.
- Inline SVG for the diagram, drawn by you. Not an image, not mermaid.
- A little JavaScript when it makes the mechanism clearer, inline in a
  `<script>` tag: stepping through a request path, hovering a box to explain
  it, dragging a slider to show how a number changes the outcome. Keep it
  under about 60 lines and make it work with one click or hover.

The diagram must show the **mechanism**, not the outline. A box per heading
is decoration. What earns its place: where a request actually goes, where
the time is spent, what happens to the data at each hop, what the tradeoff
curve looks like.

Label the parts with the real names from the material, so the picture and the
prose teach the same vocabulary.

If a lesson has no mechanism worth drawing — some days it is an argument, not
a system — write the page without a diagram and say in your answer why. A
forced diagram is worse than none.

### Check the diagram actually runs

A broken diagram looks exactly like a working one in the source. On
2026-09-12 a lesson shipped with `querySelectorAll('.vcells .vcell')` against
markup that said `id="vcells"` — the selector matched nothing, so half the
animation was dead and the page looked fine. Before you finish:

- **List every id and class your script queries. Confirm each one exists in
  the markup you wrote**, with the same spelling and the same kind (`id=` is
  `#`, `class=` is `.`).
- **Build repeated shapes in the script, not by hand.** Twelve near-identical
  `<rect>` elements pasted in the markup is where drift starts. Create them in
  a loop and you cannot mistype one.
- **Give the diagram at least two states worth comparing**, reachable from the
  controls, plus a legend for any colour that carries meaning. A picture with
  one state is a static drawing with extra buttons.
- **Say what changed in words too.** A line of text under the diagram that
  updates with the state is what makes it teach rather than decorate.

## Facts you state, and where they came from

Three claims in that same lesson were wrong in ways he could not have caught:
`Seconds_Behind_Master` described as the size of the backlog (it measures
applier delay and reads zero when disconnected), `NOW()` listed as unsafe for
statement-based replication (it is safe — `SYSDATE()` is the unsafe one), and
a config variable that had been deprecated in the very version the example
pinned.

Each came from writing fluently past the edge of what the digest supported.

- **A default value, a flag name, a version behaviour, or "X is unsafe" must
  come from the digest.** If the digest does not say it, either leave it out
  or mark it: "I believe, not from the source".
- **Prefer the mechanism you can explain over the detail you half-remember.**
- **When a number matters, name where it came from** — the article, the docs,
  or your own reasoning.

He will run this code. A wrong flag costs him an evening.

## Score it, then fix the lowest

Six dimensions, 0-10 each:

1. **One thread** — it is a lesson, not a digest of digests.
2. **Not obvious** — it teaches something he could not have guessed.
3. **Concrete** — real code, real numbers, real failure modes.
4. **Usable today** — the fifteen-minute thing is genuinely fifteen minutes.
5. **No padding** — every paragraph earns its place.
6. **The diagram teaches** — it shows mechanism, or it is honestly absent
   (score this 8 when you explain why there is none).

Pass is 45 of 60, none under 6. Up to two revise passes, lowest dimension
first. If a pass does not raise the score, stop and say what you would need —
usually a digest that failed to fetch, or a topic where the day's reading was
thin.

Report the score, the weakest dimension and both paths in your answer.
