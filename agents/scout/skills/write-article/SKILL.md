# Write an article

Use for long-form: a blog post, a technical write-up, an essay.

Voice is shared, not copied. Read `../voice.md` first and keep it open — it
holds his measured numbers, the six rules, the register gate, and the AI
tells, and both skills read it from the same place, so an article is never
written without them. The register gate there is pass/fail and runs before
any scoring here, the same as for a post. This skill covers only what is
different about length.

## Length changes the failure mode

A bad post is generic. A bad article is *padded*: the same thought restated
in three registers, a section that exists because the outline said so, a
conclusion that summarises what the reader just read. AI drafts run about a
third longer than they need to. Assume yours does.

The test for every paragraph: **does the reader know something after it that
they did not know before it?** If not, cut it. Not tighten. Cut.

## Evidence first, in every section

Lead each section with the concrete thing — the incident, the number, the
code, the screenshot — and explain after. Never the reverse. "Durable
execution matters because..." is an essay nobody finishes. "A restart turned
one approval into two prompts" is one they do.

He has more of this material than he thinks: real incidents from Mission HQ,
real numbers from his own runs, real decisions he made and can defend. An
article with no incident in it is a summary of other people's ideas, and he
should not publish those.

## Shape

Open the way a post opens: first person, a real moment, no throat-clearing.
An article earns no extra warm-up. If the first two sentences would work as
a standalone X post, the opening is right.

Then: what happened, what he expected, what was actually true, what he
changed. That is the arc, and it does not need section headings to exist. Use
headings only when the reader would otherwise lose the thread — usually past
1,000 words, and rarely more than four.

Close on the concrete: the change he made, the thing still unsolved, the
question he is now sitting with. Never a summary of the article. Never "the
key takeaway is". Never a call to subscribe.

Sub-headings are sentences, not labels. "The approval was never lost" beats
"Root cause analysis".

## Section it the way Arpit does

He named the target on 2026-09-13: "check Arpit Bhayani's posts and articles
and these videos, his writing style is simple, easier to understand — improve
it according to that." Six of those essays were measured the same day, and
the finding is structural, not verbal — his sentences are no shorter than
ours.

- **A heading every 110 to 210 words.** His essays carry 7 to 21 headings
  across 1,500 to 2,600 words, counting every heading level. A section is one
  idea; past roughly 250 words it is two wearing one heading.
- **Name the section after the question it answers.** "What Happens to
  Existing Data", "The Key Ordering Problem", "Why Increase Partitions".
  Never clever, never a bare label like "Architecture".
- **The first section is the motivation, named as such.** "Why Bloom Filters
  Matter" comes before any mechanism.
- **Open with one plain sentence saying what the thing is, then the question
  the piece answers.** "A Bloom filter is a probabilistic data structure that
  answers a very specific question — have I seen this thing before? — while
  using almost no memory. There is a trade-off, though."
- **Ask the reader a question about three times**, usually to open a section.

`learning/sources.md` holds the measurements and the method; re-measure
rather than trusting them. His blog is arpitbhayani.me/blogs and his video
breakdowns, with notes and slides, are at arpitbhayani.me/videos.

This is a shape rule, not a length rule. Splitting a section removes nothing.

## Length, honestly

Write to the material, not to a target. A technical piece built on a lesson
usually lands where his do, between 1,500 and 2,600 words; a piece built on
one incident of his own is often 600 to 1,200. If it is 400 words of real content, publish 400 words. Padding
to hit a length is the single most detectable thing in AI writing, and the
field guide lists content inflation as its own category for that reason.

## Score it

Same six dimensions as `write-post`, same threshold — 50 of 60, none under 7
— plus two that only apply at length:

7. **No padding** — every paragraph earns its place. Score 10 only if you
   tried to cut one and could not.
8. **Evidence density** — how many paragraphs open on something concrete
   rather than on a claim? Under half is a fail.

Pass is 65 of 80, none under 7. Up to three revise passes, lowest dimension
first, same rule: if a pass does not improve the score, stop and say what you
would need from him.

Before the final pass, read it once as if it appeared in his feed under his
name. If any sentence would embarrass him — because it overclaims, because it
sounds like a brand account, or because he could not defend it in a reply —
cut that sentence.

## Where it goes

`projects/content/articles/<YYYY-MM-DD>-<slug>.md`, with a `sources:` line at
the end naming the vault notes and URLs it drew on. Report the score and the
weakest dimension in your answer.
