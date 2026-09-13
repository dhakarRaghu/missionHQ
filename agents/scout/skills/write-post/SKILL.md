# Write an X post

Use when writing or rewriting a post for X. Produces finished copy the owner
can paste, then scores it and rewrites until it passes. Never post; the owner
publishes his own work.

## His voice is measured, not guessed

The canonical copy lives in `../voice.md` and is shared with `write-article`.
This file keeps the same numbers inline so a post can be written from this
page alone; if the two ever disagree, re-measure his real posts and update
`voice.md`.

These numbers come from his own last 10 posts, read off his profile on
2026-09-10 (`quarantine/2026-09-10-operator-fc263764.md`). Match them.

| | His actual practice |
|---|---|
| Median sentence | **8 words**. Half his sentences are shorter than that. |
| Whole post | **87 words** median. Short sentences, not a short post. |
| Contractions | **3.1 per post.** "I don't", "it's", "that's", "you're", "should've". |
| Uncontracted ("it is", "cannot", "do not") | **0.2 per post.** He almost never writes them out. |
| "I think" / "I don't think" / "I'd rather" | **0.9 per post.** This is his voice, not a hedge. |
| Em-dashes (—) | **Zero.** In 10 posts. Use a full stop. |
| Emoji, hashtags, bullets, numbered lists | **Zero.** |
| "not just X but Y", "serves as" | **Zero.** He does not write like this. |
| Opening | First person, or a flat claim about a group. |

His real openers, verbatim:

> I broke production three times last month.
> I don't think most support teams have a support problem.
> I've seen teams blame the AI when the real problem is...
> Most support bots fail before they even reply.
> No one tells you this about...

Read four or five of his real posts in that note before drafting anything.
The point is not to copy a sentence. It is to write in a register he would
recognise as his own.

## The six rules

1. **Anchor on "I".** Every post starts or pivots on his direct experience.
   "I broke production", "I've seen", "I don't think", "I have a theory".
   This turns an abstract idea into something owned and lived. A post with no
   "I" in it is a lecture, and he does not write lectures.
2. **State the claim flat — but "I think" is not a hedge, it is him.**
   Cut "maybe", "arguably", "it could be argued", "it is worth noting",
   "in my opinion". Those soften the claim. Keep "I think", "I don't think",
   "I genuinely think", "I suspect", "I'd rather", "I keep coming back to" —
   he opens with them **roughly once a post**, and they make the claim *his*
   rather than a stated fact about the world. "I don't think most support
   teams have a support problem" is a harder claim than "Support teams do not
   have a support problem", because he is standing behind it.

   This rule used to read "no hedging" with no exception, and it deleted his
   most recognisable move from every draft.
3. **Trigger, then reflection, then insight.** Start from a real thing that
   happened: a meme, an incident, a number, something he saw. Move to the
   pattern he noticed. End on the implication. Let it run like spoken
   thought. Do not impose a template on it.
4. **Short lines, no furniture.** Line breaks for punch. No bullets, no
   dashes as list markers, no numbered "5 ways", no emoji, no hashtags. Two
   items beat three. Flowing paragraphs or one-line thoughts, nothing else.
5. **Invite, do not sell.** When it fits: "happy to help", "somebody please
   build this". Builder to builder. No CTA, no "DM me", no link-dropping.
6. **Introspective and forward at once.** "Most systems pull you toward
   average" sits next to a sharp read on where this is going. What he is
   learning now, tied to what it means next.

## Write it spoken, not written

On 2026-09-13 he read a batch back and said it still was not his language.
Length was not the problem. Counted the same way across his ten real posts
and that batch of five, the shape already matched and the register did not:

| | him | the batch |
|---|---|---|
| Words per post | 87 | 84 |
| Median sentence | 8 words | 7 |
| Contractions | **3.1 per post** | **0.4** |
| "it is", "cannot", "do not", "I am" written out | **0.2 per post** | **1.0** |
| "I think" family | **0.9 per post** | **0.0** |

He talks. The drafts wrote.

**Contract everything he would contract.** "I'm spinning up two containers
tonight", not "I am spinning up". "It can't tell you which", not "The number
cannot tell you which". "That's how most teams iterate on their AI agents
right now and it's insane" is his actual sentence, from the pinned post. Full
forms are for emphasis — one per post at most, where the weight belongs.

Before you hand a draft over, count the apostrophes. Under two in a post of
his length, and you have written an essay in his name.

## Say it the way he would say it out loud

He asked for simpler language twice. Simpler does not mean shallower — it
means the reader gets the mechanism without having read the article first.

Three things that broke it in the last batch:

- **"It measures how far behind the applying thread is."** He would say "how
  far behind the replica is at *running* the changes". Name the moving part
  in words a reader can picture, then use the real name once if it matters.
- **"The number everyone dashboards."** A noun used as a verb to sound sharp.
  He writes "the number everyone puts on a dashboard".
- **"A fast thing feeds a slow thing."** So abstract it could mean anything.
  He grounds first: "MySQL pulls changes faster than it can run them."

The test: **could someone who has not read the source article follow this
post?** If following it needs the article, the post is a summary with his name
on it. Spend one plain sentence setting up the thing, then make the turn.

And do not end every post on an aphorism. Five posts closing on five polished
final lines is a template showing through. He ends on a question ("What's one
support tool you'd happily delete tomorrow?"), on a preference ("I'd rather
build a support system that understands where the conversation came from"),
or he just stops.

## Score it. Then fix the worst line and score again.

**Run the register gate first. It is pass/fail, not scored.** A draft that
fails the gate does not get a number; it gets rewritten, however good the
prose is. This is the check the 2026-09-13 batch failed, and the 60-point
score did not catch it because register was one bullet inside one dimension.

Count three things on the draft, against the measured table at the top:

1. **Apostrophes.** Under two in a post of his length, fail. He contracts;
   the gate fails drafts that write out what he would shorten.
2. **Written-out forms.** "it is", "cannot", "do not", "I am", "we are".
   More than one, fail. He averages 0.2 a post.
3. **The "I think" family.** "I think", "I don't think", "I'd rather",
   "I suspect", "I keep coming back". Zero, fail. He averages 0.9 a post.

The gate is cheap to run and it hard-blocks the exact failure you last sent
back. If it fails, fix register before scoring anything else.

Only then score out of 60, six dimensions, ten each. Be harsh: you are
scoring your own work and a generous score costs him a bad post.

1. **I-anchor** — does it open or pivot on his real, specific experience?
2. **The claim** — one clear position, and is it *his*? "I think X" and
   "I don't think X" score full marks; "maybe", "arguably", "it could be
   argued", "it is worth noting" do not. Do not mark a post down for "I
   think": that is the rule this scoring line used to break.
3. **Flow** — trigger to reflection to insight, or a template wearing a
   disguise?
4. **Shape** — median sentence near 8 words, whole post near 87, at least
   three contractions, no bullets, no emoji, no em-dash? Score 5 or below if
   the post writes out "it is", "cannot" or "do not" where he would have
   contracted.
5. **Specifics** — at least one detail only he could know, and no term a
   reader needs the source article to parse. A number, a date,
   a name, a thing that broke on a Tuesday. This is the one pass a tool
   cannot fake, and it is what makes the writing his.
6. **Slop-free** — none of the tells below?

**Pass: 50 or more, and no single dimension under 7.**

Below that, rewrite the lowest-scoring dimension specifically and score
again. Up to three passes. If a pass does not raise the score, stop and say
which dimension you could not fix and what you would need from him — usually
one real detail. Never pad to reach a threshold; a short honest post beats a
long padded one.

Report the final score in your answer, with one line on what the weakest
dimension still is.

## The tells, from the field guide

Vocabulary: delve, leverage, utilize, foster, robust, seamless, empower,
unlock, streamline, testament, underscore, pivotal, crucial, landscape,
realm, tapestry, transformative, game changer, moreover, additionally.

Constructions:
- **Copula avoidance** — "serves as", "functions as", "stands as". Write "is".
- **Negative parallelism** — "not just X, but Y". "It's not about X, it's
  about Y". He never writes this.
- **Rule of three** — "faster, cheaper, and more reliable". Use two.
- **Significance inflation** — "pivotal moment", "highlights the importance
  of", "this matters because" when it plainly does.
- **Pull-quote endings** — a polished universal moral. End on the concrete
  change he made or the thing he still does not understand.
- **Throat-clearing openers** — "Here's the thing", "Let's be honest",
  "In today's world".
- **Adverbs.** Cut them. Nearly all of them.
- **Passive voice.** Every sentence needs a subject doing something.

## What you write

The finished post, ready to paste. Nothing above it, nothing inside it
addressed to him or to you. Working notes go on one `why:` line after it.

A draft worth keeping goes to
`projects/content/drafts/<YYYY-MM-DD>-<slug>.md` as well, so he can find it.

If the brief has no owner-supplied detail — nothing he built, broke, noticed
or believes — do not manufacture one. Write what you can, then ask him the
one question that would unlock it, and stop.

## When the idea came from something he read

Most of these ideas start in an article, a paper or someone's post. That is
fine — it is what reading is for. What is not fine is dressing a borrowed
insight up as something he lived.

**Say where it came from, in his own plain way.** Real openers he could use:

> I was reading about how retrieval actually fails and it made me look at ours.
> Someone wrote this week that agents fail before they even start. I think that is right.
> Read a good breakdown of KV caching today. One line stuck.

Then the post earns its keep by what HE adds: the thing he noticed in his own
system, the place he disagrees, the number from his own runs. The article is
the prompt, not the payload.

**Never write "I built", "I shipped", "I debugged" for something he did not
do.** On 2026-09-12 he read a batch of drafts back and said plainly: "this is
not actually what I'm doing". A post that claims his hands were on something
they were not is the fastest way to lose a reader who knows him — and he has
to defend it in the replies.

Three sourcing shapes that stay honest:

1. **Read it, tried it.** "Read X. Tried it on my own system. Here is what
   happened." Strongest, and only usable when he actually tried it.
2. **Read it, thought about it.** "X argues Y. In my system that would mean Z."
   The claim is his, the source is named, nothing is faked.
3. **Read it, disagree.** "Everyone says X. Having watched my own runs, I do
   not buy it." Best engagement, and only honest when he has the evidence.

If a draft fits none of these, it is a summary of someone else's post with his
name on it. Cut it.

## Sounding like him rather than like a model

He said the drafts still read AI-generated. The tells, in order of how often
they show up in these batches:

- **Written-English register.** Full forms where he would contract, and no
  "I think" anywhere. Measured, this is the loudest tell in the batches he has
  rejected — louder than sentence length, which already matches him.
- **Even, essay-length sentences.** His median is 8 words. Half his sentences
  are shorter than that. A paragraph of 20-word sentences is a loud tell.
- **The tricolon.** Three parallel clauses in a row is a model's favourite
  rhythm and almost nobody's speech.
- **Summary closers.** "The lesson is...", "And that is why...". He stops when
  the thought stops.
- **Abstraction where a detail belongs.** "Production incidents are common"
  instead of "I broke production three times last month".
- **Hedging into authority.** "It is worth noting that", "one could argue"
  — he just says it. Not "I think", which is him saying it.
- **Perfect parallel structure** across bullet points. Real notes are ragged.

Read it aloud once. If it sounds like a conference talk rather than something
he would type into his phone at 1am, rewrite it shorter and more specific.
