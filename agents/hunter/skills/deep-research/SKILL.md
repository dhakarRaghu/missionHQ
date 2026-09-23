# How to research something he will build from

Use for a lesson or a course phase. Not for a job posting.

The difference from ordinary reading: **you are trying to break the claim, not
confirm it.** A note that only contains things you found agreeing with each
other has not been checked.

Three of your own mistakes are the reason this exists:

- A guessed address, `rubyhack.ai`, reached his reading list carrying "exact
  post URL unverified" in its own justification.
- A 60k truncation cut an article in half and the lesson admitted it in the
  sources line, after the fact.
- Three facts went into a lesson wrong: a metric described as measuring the
  wrong thing, a function listed as unsafe that is safe, and a config variable
  deprecated in the very version the example pinned. He would have hit all
  three while running the code.

## Open what you cite

`web_search` gives you titles and snippets written by a ranking system. They
are leads, not sources.

- **`web_fetch`** for reading an article — it returns extracted facts.
- **`fetch_source`** when the exact words matter: a default value, a method
  section, a changelog, whether a keyword appears on a page at all. It returns
  the real text, because you cannot check a number through a summariser.
- **`browser_read`** when a fetch returns 403 or an empty shell. Publishers
  like usenix.org and ACM do this. Say in the note that a browser was needed.
- If something will not load, **say so in the note**. Never drop it silently,
  never cite it as if you read it.
- Record the date you fetched. Pages change under their own URLs.

## Prefer the thing the summary was written about

| Best | | Worst |
|---|---|---|
| source at a version tag → versioned docs → the paper → a maintainer's talk → a vendor post **with conditions** | | a vendor post without conditions, then a blog summarising someone else | 

Two rules that follow from it:

- **For any default, read the source, not the docs.** Docs lag code. Use
  `raw.githubusercontent.com/<org>/<repo>/v<VERSION>/<path>` — a **tag**, never
  `main` — and state the version beside the value.
- **A secondary blog is a lead to its source, never a citation.**

## A number without conditions is unusable

Carry these with every number: **the number, what it was compared against, the
hardware, the model or version, and the workload.**

"23x faster" is not a finding. "Up to 23x against naive static batching,
OPT-13B on one A100 40GB, 1,000 requests of 512 input tokens" is.

Then find the case where it does **not** hold. Papers usually state one, and
it teaches more than the headline because it tells you what the mechanism
needs to work.

## Go looking for the disagreement

Before you finish, search for the rebuttal on purpose: the claim plus
"rebuttal", "reproduction", "criticism". If two sources disagree, they usually
measured different things — report both and find the difference in method,
rather than choosing the tidier one.

The crux lives in the method section. Abstracts state conclusions; method
sections state assumptions, including the ones the authors never checked.

Where a result is scored by a model, a parser or a regex, **name the scorer**.
Scoring frequently moves a result more than the thing being studied.

## Say what is not there

- "That keyword appears zero times on the current page — undocumented, which
  is not the same as unsupported."
- "The abstract claims a gain and gives no numbers; they are in the PDF, which
  I did not read."
- "The post carrying this number now redirects to the blog index."

An honest gap protects him. A confident guess sends him into a wall.

## Check for rot on anything version-dependent

Flags get renamed, docs move, limits relax, pages disappear. Grep the old name
in the source at the current tag; follow redirects and cite the destination;
re-read the current page rather than trusting a remembered rule. When a rename
matters, give the three-line version timeline showing which release broke it.

## Spend searches on what you cannot name

Search for the artifact, not the topic: "Raft extended paper section 5.4"
beats "how does consensus work". Add the year when recency matters. Searching
the exact number in quotes is the fastest way to learn that only secondary
blogs carry it — which is itself the answer.

Searches are metered and shared across the system. Index pages and source
files are free; reach for those first.

## End every study note with this

```
## Things I could NOT verify — do not state these as fact
1. <claim> — <why it could not be confirmed> — <what would confirm it>
```

Mandatory. An empty list is a mistake unless it is genuinely true, because
tutor will write whatever you leave standing, and silence reads as
confirmation.

Label each claim in the note **verified** (you opened the source),
**inferred** (you reasoned it), or **not checked**. Tutor is required to keep
those labels; it cannot promote an inference to a fact.
