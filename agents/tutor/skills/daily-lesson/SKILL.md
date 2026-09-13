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

1. **Why you are here, as a story.** This comes FIRST, before the claim. He
   asked for it on 2026-09-13: "the starting part is not giving any idea,
   this should give me reasoning why we are learning this, story type".

   Two short paragraphs. Put him in a concrete situation where not knowing
   this costs something — a deploy he watches go sideways, a number he cannot
   explain, a thing that works until it does not. Then the question that
   situation leaves open. Only then the claim.

   This is not throat-clearing. Throat-clearing is empty — "in today's
   fast-moving world", "it is worth noting". A story lead is specific: a real
   situation, named parts, a cost. **If your opening could sit on top of a
   different lesson, it is throat-clearing.** Rewrite it.

2. **The claim.** Three or four lines. What is true, and why it is not
   obvious, now that he wants to know.
3. **The mental model.** How to hold the idea. Plain words. One analogy at
   most, and only if it does real work.
4. **The worked example.** Real code, config, or a traced request path — an
   agent, a service, a data path. It must be something that would actually
   run. A worked example with a `# ...` where the hard part goes is worse
   than none, because the hard part is the lesson. Use the language the
   material is in; he is not reading for a language.
5. **Where it breaks.** The failure mode, the cost, the number. What bites at
   ten times the volume. Most writing stops before this; it is the part he
   will still remember next month.
6. **Fifteen minutes today.** One concrete thing he could try before work.
   Specific enough to start without deciding anything: a file to open, a
   query to run, a parameter to change.
7. **Two things he could post.** One line each: the claim, and what makes it
   his rather than a rehash. Scout turns these into posts; you only supply
   the angle.
8. **Sources.** Every url, with the digest path beside it.

## Break it into small sections, the way he reads

He named the writer he wants these to read like: "check Arpit Bhayani's posts
and articles and these videos, his writing style is simple, easier to
understand — improve it according to that."

Six of those essays were measured on 2026-09-13, and the finding is not what
it sounds like. **His sentences are no shorter than ours.** His median is 14
words; the Kubernetes lesson he found hard was 13. The readability is
structural:

- His first section is always the motivation, named as such — "Why Bloom
  Filters Matter", "Why Increase Partitions".
- His headings name the question the section answers, in plain words: "What
  Happens to Existing Data", "The Key Ordering Problem". Never clever, never
  a bare label like "Architecture", and never a bare number like "0.3 The
  architecture".
- He opens with one plain sentence saying what the thing is, then the
  question the piece answers. "A Bloom filter is a probabilistic data
  structure that answers a very specific question — have I seen this thing
  before? — while using almost no memory. There is a trade-off, though."
- He asks the reader a question about three times per piece, usually to open
  a section.
- He puts a heading every 110 to 210 words. **Our lessons already do** — the
  one he found hard ran 141. A first pass at this claimed 325 by counting
  only top-level headings in ours against every heading in his. Do not chase
  this number; it is already met. It is here so nobody "fixes" it again.

So the gap is naming, not density. **A section is one idea** — past roughly
250 words it is two wearing one heading — but splitting is not the lever it
looked like. The lever is that every heading should tell him what question
the next 150 words answer.

`learning/sources.md` carries the measurements and the method. Re-measure
rather than trusting them; he keeps writing.

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
- **Say the thing, then explain it.** Claim first, mechanism after — inside
  a section. Across the lesson it runs the other way: the reason comes before
  the first claim, or he has no reason to read the claim.
- **Prefer the concrete noun.** "the relay log file" beats "the buffering
  layer".
- **Cut the throat-clearing.** "It is worth noting that" and "in essence" add
  nothing.
- Read it back once. If a sentence needs a second pass to parse, split it.

Jargon is fine — he wants the real words — as long as each one is unpacked
the first time it appears.

## Length

**A course lesson has no word limit, and no target belongs in this file.**
It replaces a module he wrote to study from: cover everything the module
covers, then the deeper mechanism, then the production failure. Nothing gets
left out. He said it plainly: "don't leave anything or limit the content
size."

**Never teach less than the module does.** `read_course_phase` measures the
module and hands hunter a `shape.words`; that is the floor, and it travels
with the material instead of living here. Count your own teaching sections
against it — apparatus on neither side — and if yours is smaller, go back and
teach the parts you compressed.

Two warnings, both learned the hard way on 2026-09-13. **Measure both sides
the same way**, from the markdown with code fences stripped: an early
comparison read the module off its rendered web page, counted code and page
chrome, and reported it 50% larger than it is. And treat the floor as a
floor — covering the module's ground and stopping adds nothing over the
module. What he ruled out is reading better while covering less: "I'm not
saying to reduce anything."

This paragraph used to claim his phases run 8,000 to 9,000 words. They do
not — the framing phases are a fraction of that — and tutor wrote to the
number instead of to the module in front of it. **Do not put a figure back
here.** A length written into a skill is wrong the next time he edits a
module. `read_course_phase` hands you the module itself; that is the measure.

And when a lesson reads as heavy, do not reach for the delete key. He was
explicit on 2026-09-13: **"I'm not saying to reduce anything. I'm saying we
improve the teaching ways, as I'm learning, so it generates the best readable
content."** Weight is almost never word count. It is ideas arriving in the
wrong order, or a term used before it was introduced. Fix the order, not the
length — and see the course rules in the brief for how.

**The daily topic lesson** is a different object: 800 to 1,200 words. Padding is the tell: if a paragraph
restates the one above in a different register, cut it. Cut, not tighten.

The test for each paragraph is the same one `write-article` uses: does he
know something after it that he did not know before it?

## The page, and the diagram

**The page is the lesson. It is the file he opens.** Not a summary of the
lesson, not a landing page for the diagram — every section that is in the
markdown is on the page, in the same order, with the same words.

On 2026-09-13 a lesson ran 1,449 words over fourteen sections and its page
carried 284 words and three headings. He opened it, found a slider and almost
no prose, and said: "there is no content to read, did you cut things." The
markdown was complete. Everything below this line about the diagram is what
got written instead of the lesson, because this section leads with the
diagram and mentions the lesson once.

`write_lesson` now refuses a page carrying materially less than the markdown
and tells you which sections are missing. Do not treat that as a limit to
squeeze past: a page that is 76% of the lesson is still a page missing a
quarter of it.

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

## Carry the verification through — do not launder it

Hunter now researches to the `deep-research` standard: numbers arrive with
their baseline and conditions, defaults with the version and file they were
read from, and every note ends with "Things I could NOT verify".

That labelling is the point, and it dies if you smooth it away.

- **A number keeps its conditions.** Not "23x faster" but "up to 23x against a
  naive static-batching baseline, OPT-13B on one A100 40GB". A bare number is
  how he ends up repeating something false.
- **A default keeps its version**: "the default is 16 in v0.11.0", never a
  bare "the default is 16".
- **Anything on hunter's could-not-verify list is left out, or stated as
  unverified in words.** Never promote it to fact because it sounded right.
- **Where sources disagreed, say so**, and give the mechanism that explains
  the disagreement rather than picking the tidier side.
- **If a claim rests on an abstract rather than results**, say that.

He builds from this. Confidence he cannot check is worse than a gap he can
see.

## Never his employer, past or present

His own study modules anchor to internal code from a company he has left, and
he cannot use or show that work. Any section of a source module that maps onto
an employer's private systems is replaced, not translated: find the same
mechanism in something public — an engineering blog, a postmortem, an
open-source repository — and anchor there.

Never name his current or former employer in a lesson. If the original's only
worked example was internal, say the original anchored internally and give the
public equivalent.

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

## Plan the teaching before you write a word

The lesson he rejected was written straight through: forty thousand tokens of
prose with no plan behind it. It scored 53 of 60 on the rubric below and he
still could not read it, because every defect he named — a mental model stated
before he wanted it, a term used before it was introduced, sections three
times longer than they should be — is a **planning** failure. None of them are
visible sentence by sentence, and none of them can be fixed by writing more
carefully. They have to be decided before the writing starts.

So plan first, in your own working notes, and do not begin the prose until
the plan survives the checks.

**1. Write the one-sentence outcome.** What does he understand at the end
that he did not at the start? If you cannot write it, you do not have a
lesson yet — say so rather than writing around the gap.

**2. List the sections, in order.** For each one, four things:

```
heading      — the question this section answers, in plain words
one idea     — the single thing it teaches (if you write two, split it)
assumes      — terms it relies on, each already introduced or known
introduces   — the new term or idea it defines here for the first time
```

**3. Run the ledger.** Read your `assumes` column top to bottom against the
`introduces` column above it, plus what the study note's Sequence block says
earlier phases already taught. **Every assumed term must appear earlier, or
be listed as already known.** A term that appears in neither is a forward
reference, and forward references are the single commonest reason a lesson
reads as too hard. Move the introduction earlier, or introduce it where it is
first used. Do not leave it and hope.

**4. Check the three shape rules against the plan**, not the prose:
   - Is the first section the motivation, named as such?
   - Is any section carrying more than one idea? Split it.
   - Are there enough sections? A heading every 150 words or so — so a
     4,000-word lesson wants roughly twenty, not thirteen.

**5. Only then write**, section by section, against the plan.

This costs a few hundred tokens against a lesson that runs tens of thousands,
and no cap is anywhere near binding: the run he rejected cost $0.30 of an $8
allowance and finished in half its time budget. There is no reason to skip
it, and no credit for writing fast.

Keep the plan. Report it with the lesson, so a bad lesson can be traced to
the decision that caused it rather than re-read line by line.

## Score it, then fix the lowest

Eight dimensions, 0-10 each:

1. **One thread** — it is a lesson, not a digest of digests.
2. **Not obvious** — it teaches something he could not have guessed.
3. **Concrete** — real code, real numbers, real failure modes.
4. **Usable today** — the fifteen-minute thing is genuinely fifteen minutes.
5. **No padding** — every paragraph earns its place. Note what this is not:
   a long lesson is not padded, and splitting a section adds none. Padding is
   a paragraph restating the one above it.
6. **The diagram teaches** — it shows mechanism, or it is honestly absent
   (score this 8 when you explain why there is none).
7. **Taught in order** — score this by re-running the ledger against the
   finished text. Zero forward references is 10. **Each term used before it
   is introduced costs 3.** This is the dimension the rubric was missing: the
   lesson he rejected would have passed every other one.
8. **Sectioned to be read** — does every heading name the question its
   section answers, in plain words? A numbered label ("0.3 The architecture")
   scores 4 or below however good the prose under it. Words per section
   should sit near 110-210; over 250 on average, split — never cut.

Pass is 60 of 80, none under 6. Up to two revise passes, lowest dimension
first. If a pass does not raise the score, stop and say what you would need —
usually a digest that failed to fetch, or a topic where the day's reading was
thin.

Report the score, the weakest dimension, both paths, and the section plan in your answer.
