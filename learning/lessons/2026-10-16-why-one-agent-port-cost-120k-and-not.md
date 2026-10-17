In Phase 3B you saw the serving side reuse work: the KV cache, the attention keys and values the GPU keeps for each request, lets a shared prefix be computed once and never again. That phase put you inside the server, so it could not answer what the same idea does when you are the customer paying the bill. Your own agent loop sends the whole conversation with every turn, and you cannot see which parts the provider treated as already computed and which it processed fresh at full price.

The Copilot runtime port answers it with a receipt: 128 porting PRs over 14.5 weeks, driven by agent sessions that sent 136.3 billion input tokens and got 96.22% of them back as already-computed prefix. This phase shows you the one property of prompt assembly that makes that fraction possible, and which single edit near the start destroys it, so you can read your own loop and predict what each turn will cost before you ship it.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- A long agent session only stays cheap because everything before the newest turn is treated as a processed prefix; one edit near the start forces all of it to be processed again. Predict which change to his agent's prompt assembly turns a cheap turn into a full reprocess, before he ships it.

## What the $120,000 was actually buying

Almost every token in this project was billed at the reuse rate, and this section shows what that rate bought.

GitHub rewrote the Copilot runtime from TypeScript to Rust, about 832,000 lines of production code. Long autonomous agent sessions drove the work, producing 128 porting PRs across 14.5 weeks. Those sessions used 136.3 billion total tokens, and the token bill came to about $120,000.

That last number is the surprise. If each turn had been billed as fully new input, the bill would have been roughly ten times larger. It was not, because 96.22% of the input-side token volume was billed as work the server had already done. This section shows what the money was actually paying for.

### The picture: processing once, reading many times

In Phase 3B you met the KV cache, the attention keys and values the GPU keeps for each request. Computing keys and values for a token is the expensive part of reading a prompt. A token whose keys and values already exist in cache does not need that compute again.

Prefix reuse is the server skipping that compute for a prompt part it has already processed. Your agent sends the whole conversation with every turn, so most of turn fifty is identical to turn forty-nine. The server recognises the identical head of the prompt and charges it as a cache read, not fresh input.

The part the server recognises is the processed prefix. It is the leading run of tokens, byte-identical to a prompt it has seen before. Everything in that run is priced at the read rate. Everything after it, the newest turn, is priced as new work.

  One turn's prompt, late in a session

Predict: the sessions ran for days and one compacted 647 times, yet 96.22% of tokens were read as already-processed prefix. What property of the harness makes that fraction possible at all?
The prompt head stays byte-identical across every turn, and each turn only appends to the tail. If the harness changed anything early in the prompt, for example a per-turn timestamp, the run of identical tokens would break there, and everything after that point would be processed fresh. Only a discipline of never editing the prefix keeps the fraction at 96%.

### The mechanism: where the 136.3 billion tokens went

The reported breakdown, with the price each class pays because of prefix reuse:

- 130.6 billion cache-read tokens. The processed prefix, billed at the read rate. Anthropic prices a 5-minute cache read at 0.1x the base input price, so these tokens cost a tenth of fresh input.

- 4.2 billion cache-write tokens. New tokens entering the cache for the first time, billed at 1.25x base input by Anthropic's pricing. These are the turns' new work being stored for later turns to reuse.

- 0.9 billion fresh input tokens. Tokens processed with no reuse, at full base price. This is 0.71% of input-side volume.

So per turn, the agent paid full price for the new turn's tokens. It paid a tenth of the price for the whole conversation behind it. Session length stopped driving cost. What drove cost instead was how often the prefix survived intact.

This is the wrong belief to drop. You would reasonably expect each turn to cost roughly the tokens it adds. So a multi-day session's cost grows with what the agent does. The belief is reasonable because most API calls you have written were one request with one price. In an agent loop the request is the whole conversation. The bill depends on how that conversation is assembled, not on what the agent did this turn.

### The one number

96.22%of input tokens billed as already-processed prefix

~$120,000total token bill for 136.3B tokens

0.71%of input tokens processed with no reuse

A rough back-of-envelope check shows why the fraction matters. At a 0.1x read price, reprocessing all input as fresh would multiply the input-side bill by about ten. Drop the hit rate and the same sessions cost near a million dollars. This is the difference this phase's title names.

Evidence
The token breakdown, the hit rate and the $120,000 bill are author-reported in the GitHub blog post, from private session logs, and cannot be measured independently. The author's own definition: "The prompt-cache hit rate was 96.22%: cache reads divided by all input-side token volume." The 0.1x read and 1.25x write prices come from Anthropic's prompt-caching documentation, verified against the first-party docs on 2026-10-15.

### Use it

Open the prompt assembly of any agent you have on hand and find the newest-turn boundary. Everything before it is the tokens that become the processed prefix, and you can now say what each part costs. If the boundary moves because something early in the prompt changes between turns, you have found where the bill would multiply.

A long agent turn pays full price for the new tail and a tenth for everything before it.

Expecting cost to track what the agent did this turn; one unstable head multiplies the whole session's bill.

Sum your last agent run's input tokens per turn, and check whether the turn-over-turn growth was billed or reused.

This section showed the prefix held across 14.5 weeks of sessions, but not what kept it true. The next section answers why the prefix holds, and what silently breaks it.

## Why the prefix holds, and what silently breaks it

The section above showed only the tail of each turn was ever new. It did not show what kept that true across sessions that ran for days. The answer is a discipline the harness follows on every turn, and this section is that discipline.

The prefix order is a contract: what goes first must stay fixed, or the conversation gets processed again.

### The order the server expects

Prefix reuse is the server skipping compute for a prompt part it has already processed. It does not match "text that looks similar". It matches an exact byte-for-byte prefix of this request against one it has in the KV cache. The KV cache is the attention keys and values the GPU keeps for each request. Provider caches define a fixed order for the prompt: tool definitions first, then the system prompt, then the conversation messages. A match for one level only counts if every level before it also matched.

So a change at any level invalidates that level and everything after it. This is prefix invalidation. The moment any byte early in the prompt differs, the processed prefix ends there. Then the server computes the rest of the prompt fresh at full input price.

- tool definitionschecked first; a byte change here ends the prefix for everything

- system promptchecked second; a change here keeps the tools cached, loses the conversation

- conversationgrows at the tail each turn; only this part is expected to change

- new turnappended; the only tokens the server should ever process fresh

The Copilot harness held this order across 14.5 weeks. It kept tools and system prompt byte-identical and treated the conversation as append-only. Even compaction, which rewrote long stretches of history, ended at a stable summary the harness re-anchored. So one session survived 647 compactions and still read most of its tokens as processed prefix.

### One timestamp, and the cache is gone

Predict: turn 41 differs from turn 40 only by a timestamp written into the system prompt. The prompt behind the new turn is 2,000 + 4,000 + 90,000 tokens, and the new turn is 1,000. How many tokens does the server process fresh?
About 95,000. The timestamp sits in the system prompt, so the prefix match ends there. The system prompt (4,000), the whole conversation (90,000) and the new turn (1,000) are all processed fresh. Only the 2,000 tool-definition tokens before the change still count as a hit. The temptation is to answer 1,000, because nothing in the conversation changed. But the server never looks at the conversation as a separate thing.

Append-only promptTimestamp in system prompt

Turn 41, prefix intact · 1,000 tokens fresh

Turn 41, timestamp changed · 95,000 tokens fresh

read as processed prefixprocessed fresh

The two bars have identical content and nearly identical cost to write. The difference is 95 times the fresh-token bill on this turn. The gap grows with the conversation, so the same timestamp costs more every hour the session runs.

Evidence
The prefix order is tools, then system, then messages. The rule that editing a level invalidates that level and everything after it comes from Anthropic's prompt-caching documentation. Both are verified against the first-party docs on 2026-10-15. The 647 compactions in one session are author-reported in the GitHub blog post. So is the append-only discipline of the Copilot harness.

### The three ways your own agents break it

Each pattern below is a small, reasonable-looking edit. Each one ends the processed prefix at the level it touches.

- Re-sorting tool definitions, for example listing tools in the order they were registered: tools sit first, so the whole prompt is processed fresh on every turn where the order changes.

- A timestamp or session id in the system prompt: the tools stay cached, but the system prompt changes hourly or per run, so the entire conversation behind it is recomputed each time.

- Editing mid-session history, for example trimming or rewriting an old tool result: everything from the edited message onward leaves the cache, because the messages before it no longer match byte for byte.

None of these shows up as an error. The agent keeps working and the logs look the same. The only signal is the cache-read share of input tokens dropping in your provider's usage metrics. That is why a silent break is discovered on the invoice rather than in a test.

### Use it

Read your own prompt assembly as a contract your harness signs every turn. Whatever you place first must stay byte-identical for the life of the session. Anything that must change belongs at the tail. The lab below has you audit one Mission HQ agent against exactly this rule.

Prefix reuse needs byte-identical stability, and one early edit recomputes everything after it.

Assuming an unchanged conversation stays cached no matter what; a timestamp in the system prompt recomputes all of it.

Diff two consecutive prompts from one agent run and find the first byte that differs.

You can now predict which prompt-assembly edits force a full reprocess before you ship them. The lab puts that on your own agents. Audit one Mission HQ agent's prompt assembly and mark each part stable or time-varying.

## Fifteen minutes: audit one agent's prompt assembly

You now know the rule: anything in the prompt that changes between turns invalidates the prefix from that level onward. This lab checks one of your own agents against that rule, and it takes about fifteen minutes.

Pick one Mission HQ agent that talks to a cached model. Open the code that assembles its prompt each turn, not its memory or instructions, just the string-building step.

-  L1 offline List, in order, every part that goes into the prompt: tool or skill definitions, system prompt and standing instructions, then conversation history. Write it as a one-line-per-part list, in assembly order.

-  L2 offline Mark each part stable or time-varying. A part is time-varying if a date, clock time, run id, or live status appears inside it, or if the code sorts or filters it per turn.

-  L3 offline For each time-varying part, name the level it sits in: tools, system, or messages. That level and everything after it is recomputed on every turn while the agent runs.

-  L4 offline If any time-varying part sits above the conversation, write the fix: move it to the end of the system block, or better, into the newest user message, so it lands in the part that changes anyway.

-  L5 offline If you have logs for a recent long run, compute the cache-read share: cached-read tokens over all input tokens. The Copilot harness held 96.22% across sessions that compacted 647 times; a prefix break shows up here before anywhere else.

If every part came back stable, run the assembly twice for the same session state and diff the two outputs. A random id or a set printed in arbitrary order passes a code read and fails the diff.

The audit converts the prefix rule into a per-agent checklist you can re-run after any prompt change. The checkpoint next tests your prediction on a real change. A teammate adds a per-run session id to a nightly agent's system prompt.

## Could you spot a prefix break before the invoice?

You audited one agent you can open. Now reverse the direction: someone else's change, and you only see the metrics.

The scenario

A teammate adds two lines to the system prompt of your nightly digest agent: the current date and a per-run session id. The agent runs one long session each night, about 40 turns, and each turn appends tool results to the conversation. Nothing else changed.

Using the invalidation rule from this phase, answer two questions.

- The system prompt sits before the messages, so it is part of the processed prefix, the part the server has already computed. What fraction of each turn's prompt is now processed fresh?

- Which metric moves first, before the invoice arrives?

Answer sketch
Question 1: effectively all of it, every turn. The session id changes once per run, so the first turn of every night is a full fresh process. The date is worse: it is time-varying text inside the system prompt block. The invalidation rule says a change at the system level discards that level and everything after it, and messages come after system. So the whole accumulated conversation, which last night was served as processed prefix, is processed again from token one.

In numbers from the running case: the Copilot harness held 96.22% of input tokens as prefix reads and 0.71% as fresh input. This change flips the ratio. Every turn now bills the full conversation at fresh-input prices, so the cache-read share drops toward zero and the input bill rises by roughly the read discount, about 10x at Anthropic's 0.1x read price.

Question 2: the cache-read share of input tokens. Cache reads divided by all input tokens is the metric, the same ratio the article reports as 96.22%. It falls within one night's run. Total input tokens per turn also climbs, because last night's conversation is reprocessed instead of read. Cost per run follows both, but it is the last signal to move, not the first.

The same rule covers both directions. In your audit you searched your own code for unstable prefix items. Here you inferred one from a metric you did not control. In both cases the question is identical: does anything before the newest message ever change?

You can now predict a prefix break from a one-line config diff. The last section turns the two claims of this phase into posts.

## Two things worth posting

Two posts, each one claim plus the number that makes it yours.

One: the prefix did the work. A 136.3-billion-token agent project stayed affordable because 96.22% of input tokens were read as an already-processed prefix, not computed fresh. The reason was harness discipline: tool definitions first, then system prompt, then a conversation that only ever grows at the tail. Your line: "The port did not cost $120k because the model was cheap. It cost $120k because 96% of the prompt was never processed twice."

Evidence
Token breakdown and cache-hit rate are author-reported in the GitHub blog post. The 0.1x read price that turns 96% reuse into roughly a 10x saving is from Anthropic's prompt-caching docs, verified 2026-10-15.

Two: assembly order is a cost decision. The processed prefix follows tools, then system, then messages, and one edit invalidates its level and everything after. Your checklist of the three silent breaks: re-sorted tool definitions, a timestamp in the system prompt, edited mid-session history. Your line: "Prompt assembly order is a correctness-of-cost decision. One stable field moved one position earlier in the string can multiply your input bill by ten."

## Sources

Two sources carry this lesson, and they carry different weights: one reports the session numbers, the other verifies the mechanism.

- github.blog/ai-and-ml/migrating-the-github-copilot-runtime-to-rust-using-copilot/ — the experience report behind every session figure here: 136.3B input tokens, the 96.22% cache-read share, the 647 compactions, the $120,000 bill. Single author, private session logs, none of it independently measurable.

- platform.claude.com/docs/en/build-with-claude/prompt-caching — the first-party docs that verify the mechanism: the prefix order tools, then system, then messages, the invalidation of a changed level and everything after it, and cache reads billed at 0.1x base input. Opened and checked 2026-10-15.

- medium.com/airbnb-engineering/accelerating-large-scale-test-migration-with-llms-9565c208023b and arxiv.org/abs/2501.06972 — two independent large-scale migrations that corroborate the shape, not the numbers.

The rule to keep: the harness discipline and the pricing are verified; the session statistics that prove their payoff are one engineer's report.