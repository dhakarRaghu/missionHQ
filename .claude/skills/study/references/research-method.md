# Research method. Deep technical research for study material

## What this method changes

Normal research finds sources that agree with a claim. This method tries to break the claim first, then reports what survived.

The output is not a list of links. The output is a list of claims, each carrying:

1. the exact number or fact,
2. the conditions that produced it,
3. the URL that was actually opened,
4. a label of verified, inferred, or not checked.

A claim without conditions is not a finding. "Continuous batching gives 23x throughput" is not a finding. "Up to 23x against a naive static batching baseline, OPT-13B on one A100 40GB, 1,000 requests of 512 input tokens, generation lengths from an exponential distribution" is a finding.

---

## Rule 1: Fetch every URL. A search result is not a source

A web search returns titles and snippets written by a ranking system. It does not prove the page exists, says what the snippet says, or still says it today.

- Open every URL you plan to cite.
- If the fetch fails, say so in the output. Do not quietly drop the source and do not cite it as if you read it.
- If a site blocks automated fetching, use a browser tool. `usenix.org` returns HTTP 403 to plain fetchers and loads fine in a browser. So does much of ACM and IEEE.
- Record the date you fetched it. Docs pages change.

The failure this prevents: a number that everyone repeats and nobody sourced. In one real case, "context rot causes a 30% accuracy drop" appeared in a dozen blog posts. The primary research page publishes its results as charts and states no such number anywhere. The correct output was "this figure does not appear on any first-party page; do not cite it".

## Rule 2: Rank sources, and say which rank you used

```
┌──────┬──────────────────────────────────┬──────────────────────────────────┐
│ Rank │ Source                           │ What it settles                  │
├──────┼──────────────────────────────────┼──────────────────────────────────┤
│  1   │ Source code at a version tag     │ defaults, flag names, behaviour  │
│  2   │ Official docs pinned to a version│ intended behaviour, schema rules │
│  3   │ The original paper               │ mechanism, the measurement       │
│  4   │ A talk by the author             │ the mental model, worked examples│
│  5   │ Vendor engineering blog WITH      │ production behaviour at scale    │
│      │ stated conditions                │                                  │
│  6   │ Vendor blog without conditions    │ nothing. Use for leads only.     │
│  7   │ Secondary blog, listicle, summary │ nothing. Never cite.             │
└──────┴──────────────────────────────────┴──────────────────────────────────┘
```

Rank 1 beats rank 2 for anything that has a default value. Documentation lags code. In one real case the docs page named two backends for a feature and the source listed five, with a fallback chain the docs never mentioned.

## Rule 3: Verify defaults against the source tree, not the docs

Docs that say "latest" carry no version. Pin the check.

```bash
# 1. What is the current release, and when did it ship?
curl -s https://pypi.org/pypi/<package>/json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['info']['version'])"

# 2. Read the config file at that exact tag, not at main
curl -s https://raw.githubusercontent.com/<org>/<repo>/v<VERSION>/<path>/config.py

# 3. Prove the docs match the release you checked
#    Compare the docs source file at main against the same file at the tag.
curl -s https://raw.githubusercontent.com/<org>/<repo>/main/docs/<page>.md   | shasum
curl -s https://raw.githubusercontent.com/<org>/<repo>/v<VERSION>/docs/<page>.md | shasum
```

Report the version you checked, next to every default you state.

## Rule 4: Every number carries its conditions and its baseline

Copy these five fields with any number you report:

| Field | Example |
|---|---|
| the number | 36.9x speedup |
| the baseline | FasterTransformer with a custom dynamic-batching scheduler |
| the hardware | 16 A100 40GB GPUs over NVLink |
| the model | GPT-3 175B, fp16 |
| the workload | inputs uniform 32 to 512 tokens, outputs uniform 1 to 128 |

A number whose baseline you cannot name is unusable. "23x throughput" against naive static batching is a different claim from "23x" against a tuned server, and only one of them is true.

Also hunt for the case where the result does NOT hold. Papers usually include one. Orca's own figure shows it losing on a smaller model at low load. That single fact teaches more than the headline, because it tells you the mechanism needs load.

## Rule 5: When sources disagree, do not pick a side. Find the paper that splits the cause

Disagreement is a signal that two groups measured different things.

The real example worth copying:

1. A 2024 paper reported that forcing JSON output cost a model 63 points on a maths benchmark.
2. The authors of the constraint library published a rebuttal measuring the opposite on the same model and tasks.
3. A third group's benchmark measured small gains.
4. A 2026 paper separated the two possible causes and found that asking for a format in the prompt cost about 3.9 points, while the constrained decoder added about 1.6. Of 39 significant effects, 36 came from the prompt alone.

The correct output reports all four positions, then names the mechanism that explains the disagreement. In this case the 2024 paper's own text said it "assumed" its provider used constrained decoding, and never checked. That single sentence, found by reading the method section, resolved a two-year argument.

**Where to look for the crux:** the method section, not the abstract. Abstracts state conclusions. Method sections state assumptions.

## Rule 6: Check the measurement instrument before you trust the measurement

Ask how the result was scored. In every study of the example above, the scoring method moved the result more than the thing being studied.

- One paper used a model to parse answers. Its own table shows parser choice moving a score by up to 42 points.
- The rebuttal showed the same task scoring 0.35 with a strict regular expression and 0.61 with a flexible one.
- The 2026 paper switched its own scorer and watched its measured effect shrink from 10.1 points to 6.6. A third of the effect was a scoring artifact.

So: find the scorer, report the scorer, and distrust any number that does not name one.

## Rule 7: Absence is a finding. Report it explicitly

Say these out loud in the output:

- "The keyword `oneOf` appears zero times on the current schema page. Its status is undocumented."
- "The official error-codes page does not list this error at all."
- "The abstract claims improvements but states no numbers. They are in the PDF, which I did not read."
- "The technical post that carried this number now redirects to the blog index. It is gone."

An honest gap protects the reader. A confident guess sends them into a wall.

## Rule 8: Check for churn before you cite anything version-dependent

Technical facts rot in four specific ways. Check all four.

| Rot type | How to check |
|---|---|
| Renamed flags | grep the old name in the source at the current tag. Zero hits means removed. Then find the release that removed it. |
| Moved documentation | follow redirects. `platform.openai.com/docs/...` now 301s to `developers.openai.com/api/docs/...`. Cite the destination. |
| Relaxed restrictions | a limitation from 2024 may be gone. Re-read the current page rather than trusting a remembered rule. |
| Deleted pages | a number with no live first-party URL cannot be cited, even if you remember it. |

Build a small version timeline when a rename matters:

```
v0.10.2  GuidedDecodingParams only
v0.11.0  StructuredOutputsParams added, old one deprecated
v0.12.0  guided_* fields removed        ← the breaking release
```

---

## The pipeline

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. DECOMPOSE   split the topic into 2-4 clusters that share sources    │
│ 2. FAN OUT     one specialist agent per cluster, launched in parallel  │
│ 3. VERIFY      every agent fetches every URL; no exceptions            │
│ 4. MERGE       read the reports; find claims that contradict the draft │
│ 5. CORRECT     rewrite the draft, and SAY what changed and why         │
│ 6. REPORT      publish with labels: verified / inferred / not checked  │
└────────────────────────────────────────────────────────────────────────┘
```

### Step 1: Decompose by source family, not by subtopic

Wrong split: one agent per section of your document. The agents then fetch the same pages and return overlapping work.

Right split: one agent per family of sources, so each agent becomes expert in one literature.

Worked example for a phase on inference internals:

| Agent | Cluster | Source family |
|---|---|---|
| A | batching, paging, prefix caching, chunked prefill | systems papers, serving-engine source and docs, maintainer talks |
| B | constrained decoding and its quality cost | constraint-library papers, provider schema docs, the benchmark disagreement |
| C | context windows and compaction | vendor engineering posts, agent-behaviour papers, product documentation |

Each cluster has its own vocabulary and its own venues. That is what makes the split work.

### Step 2: Launch them at the same time

Send all agents in one message so they run in parallel. Three agents took about 7, 13 and 18 minutes in the real run. Sequentially that is 38 minutes of waiting.

While they run, keep writing. Draft the material from what you already know. The agents will correct it, and correcting a draft is faster than writing from an empty page.

### Step 5: Expect to be wrong, and say so

In the real run, the research contradicted two things I had already written:

1. I wrote that every first call with a new schema pays a compilation cost. The current provider documentation scopes that to fine-tuned models only. I rewrote the section and told the reader which claim changed.
2. I wrote that the evidence on output constraints "simply disagrees". A 2026 paper had already split the cause. I replaced hand-waving with numbers.

If research never contradicts your draft, your research was too shallow or your draft was too vague to be wrong.

---

## The research agent prompt template

Copy this. Replace the bracketed parts. The constraints are doing the work, so do not soften them.

```
You are gathering VERIFIED references and HARD NUMBERS for [DELIVERABLE].
Audience: [AUDIENCE]. Today's date: [DATE].

You must fetch every URL and confirm it loads and says what you claim.
Never include an unverified link. If a site blocks automated fetching, use a
browser tool and say that you did.

Find:
1. [The original paper for X] - URL, and the SPECIFIC sections and figures that
   contain the mechanism and the measurement. Quote the headline numbers with
   their baseline, hardware, model and workload.
2. [The current official documentation for Y] - URL, and the EXACT current flag
   or parameter names. State the version you checked. If the docs page carries
   no version, verify each default against the source tree at the matching
   release tag and say which file and tag you read.
3. [The provider API reference for Z] - the exact rules, limits and restrictions
   as of today. Explicitly list which keywords or options are ABSENT from the
   page, because absence means undocumented, not unsupported.
4. [The controversial claim] - find the measured evidence on BOTH sides,
   including rebuttals. Report the actual numbers with their conditions. If the
   sources conflict, report the conflict and find the methodological difference
   that explains it. Read method sections, not only abstracts.
5. At least one talk by an author or maintainer, with KEY TIMESTAMPS. If the
   video has no chapters, pull the caption track and say your timestamps came
   from captions.
6. At least one production engineering post or postmortem that reports numbers
   WITH conditions. Reject posts with no conditions.

For every source return: title, URL, why it beats the alternatives, exactly what
to focus on (section numbers, figure numbers, timestamps), when to read it, and
every hard number with its conditions.

End your report with a section titled "Things I could NOT verify". List every
claim you could not confirm, every page that failed to load, every number whose
primary source you could not find, and every abstract you read without reading
the body. This section is mandatory. An empty one will be treated as a mistake.
```

### Why each constraint is there

| Constraint | The failure it prevents |
|---|---|
| "fetch every URL" | citing a dead or hallucinated link |
| "state the version you checked" | a default that was true two releases ago |
| "list which keywords are ABSENT" | treating undocumented as unsupported |
| "read method sections" | inheriting a paper's unstated assumption |
| "timestamps from captions, and say so" | fake precision on a video you skimmed |
| "reject posts with no conditions" | marketing numbers entering technical material |
| "Things I could NOT verify is mandatory" | silence being read as confirmation |

---

## Tool techniques

### Search

- Search for the artifact, not the topic. "Orca OSDI 2022 iteration-level scheduling" beats "how does batching work".
- Include the year when recency matters. Add the current year to catch renames and deprecations.
- Search for the rebuttal on purpose. Query the claim plus "response", "rebuttal", "reproduction", "criticism".
- Search the exact number you want to verify, in quotes. If only secondary blogs carry it, that is your answer.

### Fetch

- Prefer a readable rendering of a paper over the PDF. `ar5iv.labs.arxiv.org/html/<id>` gives section and figure numbers you can cite.
- Note when section numbers come from a preprint rather than the camera-ready. They shift.
- Follow redirects and cite the destination URL.
- For source files use `raw.githubusercontent.com` with a tag, never `main`.

### Browser

Use it when a plain fetch returns 403 or an empty shell:

- academic publishers, `usenix.org`, some ACM and IEEE pages
- single-page applications that render content with JavaScript
- video pages, when you need the caption track for timestamps

Say in the report that a browser was needed. It tells the reader the link works for humans.

### Video

- Pull the caption track rather than watching. It gives text and times.
- Check whether the publisher supplied chapters. If not, label your timestamps as caption-derived and accurate to a few seconds.
- Give 8 to 12 timestamps for a talk you recommend, not 2. The value is in being able to jump.

---

## The report format an agent must return

```markdown
## [Cluster name]

### [Source title]
- **URL:** <url> (verified, fetched <date>)  |  (verified via browser, fetch returns 403)
- **Authors / date / venue:** ...
- **Why this one:** what it settles that the alternatives do not.
- **Focus on:** section numbers, figure numbers, timestamps.
- **Hard numbers (verified):**
  - <number>, conditions: <baseline, hardware, model, workload>
  - the case where it does NOT hold: ...
- **When to read:** before or after which exercise.
- **Flags:** anything about this source the reader must know.

## Things I could NOT verify - do not state these as fact
1. <claim> - <why it could not be confirmed> - <what check would confirm it>
```

---

## Anti-patterns

| Anti-pattern | What to do instead |
|---|---|
| Citing an abstract as the result | read the method and the results section, then cite the table |
| Reporting a headline number bare | attach baseline, hardware, model, workload |
| Repeating a number many blogs share | find the first-party source, or report that none exists |
| Quoting a default from memory | read the config file at the release tag |
| Hardcoding an error message string | match on status code and error code; message wording is unstable |
| Treating silence as support | say the page does not mention it |
| Averaging two conflicting studies | report both and find the methodological difference |
| Dropping a source that failed to load | list it under "could not verify" |
| One agent for everything | split by source family and run in parallel |
| Finishing when sources agree with you | search for the rebuttal before you stop |

---

## Final checklist before publishing

- [ ] Every URL in the output was opened, and the date is recorded.
- [ ] Every number carries its baseline and conditions.
- [ ] Every default names the version and the file it came from.
- [ ] Every disagreement in the literature is reported, not resolved by preference.
- [ ] Every measurement's scoring method is named.
- [ ] The "could not verify" list exists and is not empty unless that is genuinely true.
- [ ] Any claim in the draft that the research contradicted is corrected, and the correction is stated plainly.
- [ ] Nothing is presented as verified that was inferred.


---

## Additions from building the first course

These rules came from mistakes that the method above did not catch on its own.

### A1. Extract the agent's final report to a file before using it

A background agent's output file holds its whole transcript. Only the last text message is the report. Extract it, save it, and work from the file:

```python
import json
last = None
for line in open(OUTPUT_FILE):
    d = json.loads(line)
    if d.get("type") == "assistant":
        text = "".join(x.get("text", "") for x in d["message"]["content"]
                       if x.get("type") == "text")
        if text:
            last = text
open("report_<cluster>.md", "w").write(last or "")
```

Then list every URL in the report, and fetch-check the ones you plan to cite:

```bash
grep -o 'https\?://[^ )>"]*' report_*.md | sort -u
```

### A2. Keep each fact tied to its own source through the merge

When you merge several reports, write the source name next to each fact in the draft. Never write "the same study" unless you checked that both facts share a URL.

Real error caught in review: a burstiness figure from one paper and a client-concentration figure from another were both credited to "the same production-trace study".

### A3. Re-check quotations yourself

An agent may paraphrase inside quotation marks. Before you publish a quote, fetch the page and grep for it.

Real error caught in review: "its alerts are actionable" was published as a quote. The source says "those alerts are actionable".

### A4. Name the source in the prose

The reader must be able to find the claim. Write "the AWS EKS inference guide says", not "one cloud provider's guidance says". Anonymous attribution also hides which facts are vendor claims.

### A5. Carry the limits into the material

Every item under "Things I could NOT verify" that the text depends on becomes a sentence in the text:

- "Inferred from the code, not run."
- "Posted one day ago and not peer reviewed."
- "The research found no published runbook for this."

### A6. Read source code at a tag for engine behaviour, and say that you did not run it

For serving engines and gateways, the agent should clone or fetch the release tag and cite `file:line`. Behaviour that depends on runtime, such as preemption timing, stays labelled "inferred from the code" until someone runs it.

Real value: this found that two engines order priority numbers in opposite directions. Neither engine's docs page made that clear.

### A7. Split agents by source family. Proven splits

| Phase type | Agents |
|---|---|
| systems internals | papers and engine source; provider API docs; production engineering posts |
| capacity and operations | queueing theory and SRE books; production traces and cold-start measurements; autoscaling docs |
| multi-tenant and fairness | scheduling papers; engine and gateway source at tags; security papers on shared caches |
| incidents and design review | SRE books and incident-response docs; design-document and decision-record sources; vendor ML operations guidance |

### A8. Draft while agents run, then expect corrections

Write the code and the sections that do not depend on the agents. When a report arrives, compare every claim in the draft against it. In the first course, every research round changed at least one claim in the draft.

### A9. Add these lines to the agent prompt

```
Label every claim verified, inferred, or not checked.
For source code, state the release tag and the file:line you read.
For every number, give the source's own table or figure number.
If two sources disagree, report both, with conditions.
Quote only text you can see on the page, word for word.
Name the exact organisation or authors behind each source.
```
