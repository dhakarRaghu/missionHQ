# Research brief for one curriculum module

You are writing the research dossier for ONE module of an advanced applied-AI curriculum. The dossier is the reference that a later session uses to generate the module's course with the `/study` skill. If the chat history is lost, this file must be enough.

Today is 2026-09-17. Facts change fast in this field. Research what is true now.

## Read first

1. `~/.claude/skills/study/references/research-method.md` — the research method. Follow every rule. Fetch every URL. Every number carries its conditions. Report what you could not verify.
2. `~/.claude/skills/study/references/writing-style.md` — the writing style. Short sentences, plain words, no metaphors, no em-dashes in prose.
3. `~/.claude/skills/study/references/curriculum-planning.md` — how modules are sized.
4. `/Users/raghvendra.dhakar/Desktop/project/code/study-material/_curriculum/module-01-coverage.md` — what Module 1 already teaches. Do not plan to repeat it. Link to its sections instead.

## The learner

- An advanced engineer who builds AI products. Knows prompting, basic RAG, agent loops, common frameworks, Docker, and a backend language.
- Finished Module 1, "LLM Inference Internals for Application Engineers".
- Is LEARNING, not changing a product. Labs are standalone exercises that run from the course's own `code/` folder and produce a number, a table, or a failing test. They run offline first. Live API exercises are optional and labelled.
- Their product background, for difficulty and scenario choice only: an AI customer-support platform with web chat, WhatsApp, voice, knowledge-base upload, human escalation, model switching, and a learning loop. Never assign work on that product.
- Hardware: an Apple Silicon laptop. Anything that needs a GPU or a cluster must say where it runs and what it costs.

## Output

Write exactly one file: the path given in your task. Use this structure and these headings:

```
# Module NN — <title>

Research date: 2026-09-17. Status: research dossier, not course material.

## 1. What this module is for
<3 to 6 sentences. The problem, why an applied-AI engineer needs it now, what breaks without it.>

## 2. Scope
### In scope
### Out of scope, and where it lives instead
### Overlap with earlier modules
<table: topic | where it is already taught (module and section) | what this module adds>

## 3. What changed recently
<table: change | date | source | why it matters. Only fetched, dated facts.>

## 4. Core concepts, with verified facts
<one subsection per concept. For each: a 2 to 4 sentence explanation, then a bullet list of hard facts.
Each fact: the claim, its conditions, its source name, and a label: verified / inferred / not checked.>

## 5. Proposed phase outline
<table: phase | title | what it teaches | labs it needs | runs where, costs what>
<one paragraph: why this number of phases, based on what is new versus covered>

## 6. Lab ideas
<8 to 15 standalone, offline-first labs. For each: what the script does, the number or table it prints, the break-it variant, and what a self-test would check against a known answer. Mark any that need an API key, a GPU, or paid services, with an estimated cost.>

## 7. Failure stories and case studies
<real, sourced incidents and postmortems with numbers and conditions.>

## 8. Primary sources
<grouped by theme. Each: **Title, venue or org, year** — URL, fetched 2026-09-17, HTTP status.
Then: focus on (sections, figures, timestamps), and why this source.>

## 9. Tools and versions to pin
<table: tool | current version | release date | source | notes on breaking changes>

## 10. Open questions and disagreements
<where sources disagree, with both sides and their conditions.>

## 11. Things I could NOT verify
<mandatory, non-empty unless truly nothing. Each: claim, why not verified, what check would confirm it.>

## 12. Notes for the course generator
<traps to avoid when writing this module, numbers that go stale fastest, what to re-check before generating.>
```

## Rules

- Fetch every URL you cite, and record the HTTP status. Never cite a search result you did not open.
- Prefer primary sources: specs, source code at a release tag, versioned docs, original papers, maintainer talks, postmortems with conditions.
- Name the organisation or authors behind every fact in the text.
- Every number gets its baseline, hardware, model, and workload where they apply.
- Label every fact: verified, inferred, or not checked.
- Quote only text you can see on the page, word for word.
- For tools, check the current release on PyPI, npm, or GitHub releases, and record the date.
- Aim for 15,000 to 35,000 characters. Depth over breadth.
- Write only your one file. Do not touch any other file. Do not use git. Do not publish anything.
- End your reply with: the file path, its character count, the number of URLs cited and how many returned 200, and the three most important findings.
