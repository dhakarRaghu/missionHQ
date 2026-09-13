# Measure recall before you buy infrastructure

**Path: AI systems, topic 2 of 6 — Retrieval that works.** Builds on the 09-12 lesson on judges and self-reporting evals: today we point that measurement instinct upstream, at retrieval. Next step on the path: evaluating an LLM system end to end. One note: today's two sources were a substitution. Neither is on your exemplar list for this topic. Both are by Jason Liu, and they disagree with each other in a useful way.

## Why you are here

Picture the support bot you would ship for Verly. A customer asks something the knowledge base answers plainly. The bot replies with confidence and gets it wrong. You do what everyone does: you edit the prompt. Then you try a newer model. Nothing moves, because the failing part is not the part you are watching. The right chunk never made it into the prompt, so every fix downstream was decoration.

That is the situation both of today's articles are about. One is a methodology for measuring where retrieval fails. The other is a report from a team that hit the top of the SWE-Bench Verified leaderboard (their claim, unverified in the writeup) and found that embeddings were not the bottleneck. Grep was enough. The claim below explains how both can be true.

## What is true, and not obvious

RAG systems fail systematically, not randomly. The failures concentrate upstream, in retrieval, while everyone watches the final answer. And "how good is my retriever" is the wrong question once an agent loop sits on top, because a persistent agent retries and recovers. Persistence masks retriever weakness. So you measure recall at the first stage, per segment, before buying any infrastructure, and you measure end to end once an agent is in the loop.

## The two biases that eat your week

Jason Liu names them. Absence bias: you cannot see what was never retrieved, so you blame the visible part, the generated answer. Intervention bias: you import every new technique from your timeline to feel in control, and end with what he calls a "Franken-system, with 80 half-tested solutions layered on top of each other", where no one can tell which layer fails. The antidote is boring: measure first, change one thing, keep only what moves the number.

## Which number do you measure first?

Recall, not precision. Precision asks how many returned chunks were relevant. Recall asks what fraction of all relevant chunks came back. In RAG, recall is the headache because it is the ceiling. If your recall is 50%, half the time the answer never reaches the prompt, and no prompt fix, model upgrade, or reranker recovers it. A reranker only reorders what the first stage surfaced. Retrieval owns recall; everything downstream lives under its ceiling.

## How do you measure recall with no labels?

Liu's cold-start trick: for each chunk, ask an LLM to generate 5 questions the chunk answers. Now you have question-to-chunk pairs for free. Your recall is the fraction of questions whose source chunk your retriever returns. The caveat is real and worth remembering: the generated questions paraphrase the chunk's own vocabulary, so this eval is skewed toward surface words. Real users ask questions whose words are not in the chunk. Synthetic recall is a first pass, blended with real queries later.

## Does the average hide the failure?

Always. A headline recall of 70% can sit on 5% recall for the segment that matters, his example being multi-hop or date-filtered queries. So you tag every eval question by topic, by complexity, by user role, and you read recall per segment. The numbers here (70%, 5%) are his illustrations, not measurements, but the mechanism is arithmetic: averages sum away the very failures you need to see.

## Is the data missing, or just unsurfaced?

This is the cheapest diagnostic in both articles, and the highest leverage. When a segment fails, the fork is: inventory problem or capability problem. Inventory means the data is not in the system, the subfolder was never ingested, the edit history column was never indexed. No embedding fix touches that; you fix the pipeline. Capability means the data is there but retrieval does not surface it. Teams burn weeks fine-tuning embeddings against inventory problems. Ask the fork first.

## Where do the two articles disagree?

On what to measure first. Liu says measure the retrieval component: recall, segmented, before anything else. Colin Flaherty (founding engineer at Augment, per the post) says start with 5 to 10 real examples, end to end, vibe checks before quantitative evals. His reason is the mechanism that reconciles both: for agentic systems, component metrics stop predicting end-to-end outcomes, because the agent's persistence already compensates for a mediocre retriever. If per-attempt retrieval succeeds 60% of the time and the agent tries 5 times, end-to-end success is 1 - 0.4^5, about 99%. Moving the retriever from 60 to 75 changes the visible component number a lot and the task outcome almost not at all. The agent loop masks the weakness.

So the order depends on the shape of your system. Single-shot RAG: component recall is the bound, measure it first. Agent in the loop: measure end to end first, and instrument components only to explain failures.

## When does grep actually beat embeddings?

Augment's agent used grep and find, reformulating searches until it found what it needed, and embeddings added nothing end to end. But Colin scopes it himself: SWE-Bench is "somewhat artificial", with small repos and (his claim, unsourced) 90% of problems solvable in under an hour. Code is structured and keyword-rich: function names, class names, error strings. That is exactly what grep is strong on. His honest limits: it does not scale to large codebases, it struggles with unstructured text like docs and Slack, and the retry loop burns LLM tokens, the hidden price of "no infrastructure". His decision heuristic: if a tireless human would want the second search tool, the agent probably does too. The recommended end state is hybrid: keep your tuned retriever, expose it to the agent as a tool, and let the loop supply the retry layer.

## A recall harness you can run tonight

This is Liu's 2.3 method as runnable code. It works with any retriever you pass in; a lexical one is included so it runs with zero infrastructure, and your future pgvector query slots into the same function signature.

```python
import re
from collections import Counter

# --- a minimal lexical retriever (swap for pgvector later) ---
def tokenize(text):
    return Counter(re.findall(r"[a-z0-9]+", text.lower()))

def make_retriever(chunks):
    vecs = [tokenize(c) for c in chunks]
    def retrieve(query, k=5):
        q = tokenize(query)
        scores = [sum(min(v[t], q[t]) for t in q) for v in vecs]
        return sorted(range(len(chunks)), key=lambda i: -scores[i])[:k]
    return retrieve

# --- build the synthetic eval set (call your LLM here) ---
def make_eval_set(chunks, llm):
    pairs = []  # (question, source_chunk_index, segment_tag)
    for i, chunk in enumerate(chunks):
        prompt = ("Generate 5 questions that can be answered "
                  f"by this text:\n\n{chunk}")
        for q in llm(prompt):            # one question per line
            tag = "single-hop"           # tag by topic/complexity here
            pairs.append((q.strip(), i, tag))
    return pairs

# --- measure recall, overall and per segment ---
def recall_at_k(pairs, retrieve, k=5):
    by_seg = {}
    for q, src, tag in pairs:
        by_seg.setdefault(tag, []).append(src in retrieve(q, k))
    return {tag: sum(hits) / len(hits) for tag, hits in by_seg.items()}
```

Run it, and the per-segment dict is your dashboard. When a segment is low, you ask the fork: is the answer chunk even in the corpus (inventory), or is it there and unretrieved (capability)? Only the second is a retrieval problem.

## Where this breaks

Three places. The synthetic eval lies gently, since generated questions share vocabulary with their chunks, so your recall number is optimistic for real users. The grep agent breaks at corpus scale: on a large monorepo or unstructured text, the retry loop turns slow and expensive, Liu cites 2 to 10 seconds of latency for multi-step queries as a felt UX range, not a measurement. And the whole discipline breaks if you skip segmentation, because the failing 5% segment is what your users actually hit while the dashboard reads 70%.

## Fifteen minutes today

Take one knowledge corpus you already have, Mission HQ's project notes or any docs folder. Split it into chunks by header. Write the `make_eval_set` prompt against 20 chunks with whatever model you already call, and run the harness with the toy retriever. You will have a real recall number with conditions you can state, and you will know whether your failures are inventory or capability before you have spent a rupee on a vector database.

## Two things you could post

1. "My agent's retriever scored 60% and the agent still won. Persistence is a retrieval strategy." The claim is the masking math, 1 - (1-r)^k, and it is yours because you can show it on your own agent's action log.
2. "I almost bought a vector database. A 40-line script with no dependencies told me I did not need one yet." The angle is the inventory vs capability fork, told from your own corpus.

## Sources

- Jason Liu, *Systematically Improving RAG Applications* — https://jxnl.co/writing/2025/01/24/systematically-improving-rag-applications/ — digest at `quarantine/2026-09-13-systematically-improving-rag-study.md`
- Jason Liu with Colin Flaherty, *Why Grep Beat Embeddings in Our SWE-Bench Agent* — https://jxnl.co/writing/2025/09/11/why-grep-beat-embeddings-in-our-swe-bench-agent-lessons-from-augment/ — digest at `quarantine/2026-09-13-grep-beat-embeddings-swebench-agent-study.md`

This feeds your AI systems build: the hybrid retrieval pipeline with the judge harness written first. Today's harness is the "write the judge before tuning" half of that. Where are you on the build itself? Your rule is that reading must not outrun building, and this is the lesson where that question bites.