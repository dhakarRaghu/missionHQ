# Write an article

Use for long-form: a blog post, a technical write-up, an essay. Everything in
the `write-post` skill about his voice and the AI tells applies here
unchanged — load it first and keep it open. This skill covers only what is
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

## Length, honestly

Write to the material, not to a target. Most of what he has to say is 600 to
1,200 words. If it is 400 words of real content, publish 400 words. Padding
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
