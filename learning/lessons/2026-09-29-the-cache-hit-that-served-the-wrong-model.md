Phase 3A of your course is about implicit prefix caching, which makes a repeated prefix cheap. The failures it catalogues are all lost hits: a misaligned breakpoint, a cache write below the break-even length, money spent on a lookup that missed. Each of those failures costs latency or money, and your hit rate makes them visible. In September 2026 an SGLang user on one H200 found the failure the phase did not price: with the cache warm, repeated prompts returned different greedy tokens than cold-cache repeats of the same prompts, and the cache hit rate looked healthy the whole time.

The cause was not a bad lookup. The lookup was perfect. The cache held two kinds of model state that can only be saved at different token positions, one at any token and one only every 64 tokens, and the code stored them under one shared length. A later request matched the stored key exactly and resumed from a state 96 tokens in the future, so the cache reported a hit and served the wrong model. This article explains how a hit becomes a lie your metrics cannot see, and the one check that catches it.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- A prefix-cache hit is only free when key and value live on the same geometry; when they do not, clamping silently stores a correct key against a wrong state. Decide when a cache hit can be trusted, and write the one regression check that detects a value lie.

## What does a hit look like when the value is wrong?

A cache hit that reads healthy can still serve the wrong model state.

Your chat workload sends the same long system prompt on every request. The serving stack notices the repeated prefix and reuses it. This is implicit prefix caching, the automatic reuse of tokens the server already computed, with no flag from you. A cache hit is a lookup where the stored prefix covers your request's prefix, so those tokens are billed as cached instead of computed. The phase priced these hits as nearly free, and the failure modes it priced were all misses.

A SGLang user ran exactly that shape: repeated prompts sharing a long prefix. With a warm cache, the output logprobs drifted. In one of three input groups, the greedy output token changed. With a cold cache, the same repeats matched exactly. That split clears the model, because the same weights produced identical cold output every time. The cache was the only thing that changed between the two runs.

Predict: a request shares exactly 96 tokens with a cached prefix and the lookup returns a hit. Does the hit rate change? Does the user see anything cache-related?
The hit rate rises, because the lookup matched the stored key exactly. The user sees a wrong answer with no cache-related error. Hit rate measures keys, so it cannot report that the stored value behind the key was wrong. That is what happened here.

The name for this failure is a value lie: a hit where the key is correct and the resumed state behind it is not. In the incident, the cache held a state computed 96 tokens past the branch point, stored under a key that ends at the branch. A later request matching 96 tokens resumed from token 192's state, so it skipped work it should have done.

Every metric the phase taught you to watch read this as success. The hit rate climbed. Cached-token billing looked right. Latency improved, because resuming saved prefill work. A miss costs time or money and metrics show it, because the lookup fails. A value lie keeps every saving and costs correctness instead, and no hit counter counts it.

  1 of 3input groups changed their greedy token with a warm cache

  0 of 3changed with a cold cache

Evidence
Warm-cache repeats of three input corpora produced drifting logprobs, and in one of the three the greedy token changed, while cold-cache repeats matched exactly. SGLang issue #38815, one H200, model thinkingmachines/Inkling, page size 1, commit bd087fc, read 2026-09-28. The reporter diagnosed it on paper, not from a crash: nothing in the logs pointed at the insert path.

A hit is two promises, key and value, and hit rate checks only the key.

"A hit means the resumed state is right" costs you wrong tokens that every metric calls a success.

Repeat one cached prompt twice and diff the greedy output; drift with a warm cache means the value lied.

The symptom shows a hit can lie, but not how a serving cache stores a right key next to a wrong value. The next section traces the exact insert that wrote state192 under key96, and why the cache never noticed.

## How did min(96, 192) store a state from the future?

Warm runs drifted while every cache metric read success. But the symptom alone cannot show who put the wrong value in the entry. The put happened in the insert, on the same shared-prefix traffic as your metered chat workload.

This hybrid model keeps two kinds of resume state, and the bug lives between them. The first is the KV cache, the attention keys and values the GPU holds for each request. It is divisible state, a per-token array where any prefix length is a valid slice. A cut at token 96 is exactly the model's state at token 96. The Mamba state is indivisible state, one compressed value that summarizes every token so far. That value updates in place as tokens arrive, so state192 cannot be rolled back into state96. It exists only on a checkpoint grid. Those are the fixed points 64 tokens apart, here 64, 128 and 192, where the system snapshots it.

KV state, a valid mark at every token

-

-

-

-

-

-

-

-

-

-

-

-

-

-

-

-

-
branch at 96
Mamba state, valid only on the grid

-

-

-

-
64
128
192

key96
state192

min(96, 192) writes key96 → state192

The two geometries in one insert. The key sits at the branch, token 96, and the attached value is the checkpoint prefill produced at 192. Illustration of the incident arithmetic, not measured.

Predict: sliding-window attention, the attention layer that keeps keys only for recent tokens, proposes a branch at token 96. Mamba rounds 96 down to 64, finds 64 already cached, and asks for no new write. Prefill runs on to token 192. What entry does the insert write?
The reasonable guess is key96 → state64, because 64 is Mamba's nearest grid point below the branch. The insert actually writes key96 → state192. It stamps the key at 96, the shortest length any component requested. It attaches the only Mamba value the prefill produced, the state at 192.

Here is that insert in the order the scheduler ran it.

- SWA proposes 96its page-aligned branch point

- Mamba rounds to 64already cached, so it asks for no new write

- prefill runs to 192the one fresh Mamba value is state192

- insert takes min(96, 192)the key's length becomes 96

- store key96 → state192a correct key against a state from the future

A later request sharing those exact 96 tokens now gets a clean cache hit on key96. It resumes from state192, so the model reads the request as if it had already processed tokens 97 to 192. Those tokens belong to the earlier request's continuation, not to this one. That is the value lie the metrics counted as a hit.

PR #37584 repairs the write in two moves. Each Mamba value now carries the length it was produced at, passed along in InsertParams. Both commit sites skip the stamp when that length does not match the key's. A truncated finish then stores no checkpoint, so later requests find no wrong state. The sliding-window component also leaves the insertion length to Mamba, so each checkpoint stays attached to its true prefix depth.

Evidence
The guard was validated in PR #37584, merged 2026-09-12. Warm-cache token IDs and logprobs matched cold-cache output exactly across the three input corpora. Removing the guard made all three subcases fail again with 96 != 64. The in-place property the bug abused is stated in the SGLang team's PyTorch Foundation blog, read 2026-09-28. It says: "SSM states are updated in-place, so a request's states cannot be rolled back to represent its prefixes."

Match the stored value's length to the key's length; the minimum of the two is not a match.

"Minimum is conservative" stamps a short key on a newer state, and every later hit lies.

In one cache you own, log each stored value's length next to its key.

The insert is explained, but the hit-rate gauge that scored it green is unchanged. The next section asks what catches a value lie before your users do.

## What catches a value lie before your users do?

The fix guards one insert path, and this check guards every cache you run.

The guard in PR #37584 repaired one insert path. The gauge that scored the incident green is unchanged, because a hit rate counts lookups and never values. That gauge sits in every cache you run, so the incident pays off only as a check you can rerun.

The rule generalizes to any composite cache. When components disagree on a boundary, refuse to store rather than clamp silently. The old insert took clamp-to-min, the shortest length every component asked for. That is an arithmetic decision made at the wrong layer. The key layer cannot know which geometry produced a value.

- Does the stored value's length match the key's length?

- yesstore the entry

- nostore nothing, because a miss costs time and a wrong value costs correctness

Predict: the guard is merged and the team's regression check passes on all three test corpora. Now remove the guard and rerun the same check. How many of the three subcases pass?
None. With the guard removed, all three subcases fail again with 96 != 64. The harness fails exactly when the bug is present. This is what makes it worth copying into your own cache work.

Applied to any cache, that harness becomes the warm-cold equality check. You repeat the same prompts on a cold cache and then on a warm one. You require greedy token IDs and logprobs to match exactly. Hit rate cannot see a value lie, because a correct cache changes cost only and never content. So any drift at temperature 0 on a warm cache is the lie itself, caught before a user sees it.

The shape is not a GPU problem. A row cache keyed per record and a summary cache keyed per span of tokens are two geometries over the same data, and one shared insert length lies for one of them. Your prompt-caching experiments have this shape whenever two state types share a key, so run the equality check there too.

One risk stays open. The reviewer ispobock said the next step is "to align the swa checkpoint with the mamba checkpoint". The two geometries are guarded, not unified. The class of bug is contained, not eliminated, and the check stays necessary.

Evidence
Under the merged guard, warm-cache and cold-cache outputs matched exactly on three input corpora. With the guard removed all three subcases fail with 96 != 64 (PR #37584, merged 2026-09-12). The incident ran on one H200, model thinkingmachines/Inkling, page size 1, at commit bd087fc (SGLang issue #38815). ispobock's quote is from the issue comment thread, read 2026-09-28.

A hit proves the key matched, and only output equality proves the value did.

Hit rate counts lookups, so your dashboard stays green while warm hits serve wrong states.

Repeat one cached prompt cold and warm at temperature 0 and diff the token IDs.

What silently destroys a cache hit now splits in two. Misses lose their savings, and value lies keep the savings and spend correctness. You can now write the one test that detects the second kind. The lab runs it next, proving warm equals cold on your own prompts in fifteen minutes.

## Lab: prove warm equals cold in fifteen minutes

The section above named the check: warm-cache greedy tokens and logprobs must match cold-cache output exactly. Now you run it. The idea is one sentence: a correct cache changes only cost, never content. So any drift at temperature 0 with a warm cache is a value lie, full stop.

-  E1 online Cold baseline. Take your workload's long shared system prompt and fix the generation config: temperature 0 and logprobs requested. To force a cold run, prepend a fresh random nonce string to the prompt, because the cache cannot have seen it before. Save the output token IDs and the logprobs.

-  E2 online Warm repeat. Send the exact same prompt again at once, so implicit prefix caching, the automatic reuse of already-computed prefix tokens, hits the prefix the first request left behind. Save the same two fields.

-  E3 offline Diff. Compare the two runs field by field.

diff cold_tokens.json warm_tokens.json && \
diff cold_logprobs.json warm_logprobs.json && echo EQUAL

You should see EQUAL. Any difference, even one logprob in the fourth decimal, means the warm run resumed from a different model state.

-  E4 online Off the boundary. Nudge the split so the shared prefix ends one token after a cache write breakpoint: change one character before the shared body ends. Rerun the cold and warm comparisons with the new prompt. The outputs must still match exactly, because a correct cache on any boundary changes only what you pay.

Two things to notice. First, the warm run should report cached prompt tokens, so a passing diff costs you almost nothing. You have proven the savings are real and the content is untouched. Second, the nonce trick generalizes. Any provider whose cache you cannot flush directly gives you a cold run. That happens whenever you change one throwaway token at the front.

Evidence
This is the same acceptance test the SGLang team used. Warm-cache token IDs and logprobs match cold-cache output exactly. With the guard removed all three subcases fail (PR #37584, read 2026-09-28).

If all four exercises pass, your cache tells the truth today. The checkpoint next asks the harder question. What changes when your own multi-agent system adds a second cache tier with its own geometry?

## Checkpoint: whose state is it anyway?

Here is the same bug shape, moved onto infrastructure you would build yourself. Answer each question before opening the answer.

Your multi-agent system shares an 8,000-token harness prompt across agents. The main cache, the implicit prefix caching that reuses already-computed prefix tokens, keys on exact prefixes. You add a second tier that snapshots derived summaries every 512 tokens. Last night an agent branched at token 8,000 and the insert path clamped the two lengths to one: it stored the summary snapshot written at token 8,192 under the key for token 8,000. This morning a new agent shared exactly 8,000 tokens, got a hit, and resumed from a state 192 tokens in the future.

- What does the hit-rate dashboard report for this morning's request?

- What does the user of that agent actually see?

- Which single counter pair, and which one equality test, would you add this week?

Answer sketch
1. A healthy hit. The dashboard counts cached tokens against computed tokens, so the request reads as 8,000 tokens saved. Every cost metric shows the cache working. This is the value lie, a hit whose stored state is not the right state: the key matched, so no hit-rate number can see the value was wrong.

2. Output that is subtly wrong, not an error. The resumed state carries 192 tokens of context the agent never sent, so its answers reference a branch it cannot quote. At temperature 0 the outputs are stable and confident, which makes it worse: no retry changes them, and nothing in the logs says why.

3. The counter pair is one counter per geometry at insert time: keys written at branch length, and snapshots written at snapshot length. A gap between the two is a clamp that fired. The equality test is the warm-cold equality check from the lab: a CI job runs the shared harness prompt cold and then warm at temperature 0 and asserts the output token IDs match exactly. A correct cache changes only cost, never content, so any drift fails the build before a user sees it.

The checkpoint shows the incident cost nothing to detect once the right test existed. Next, two short post sketches turn that test into something you can say in public.

## What you could say about this

The incident and the check are now yours to use. Two sketches you could publish from them.

A cache hit is two promises, not one

The key promise is "this prefix matches". The value promise is "this state belongs to that prefix". SGLang stored state192 under key96, and every hit after that resumed a model 96 tokens in the future. The rule for any composite cache: when components disagree on a boundary, refuse to store instead of clamping to the shortest length. It is yours because you can show the arithmetic and the guard, not a retweet of the issue.

Hit rate cannot see a wrong value

Every cache metric in the incident read green while the output drifted. The one test that caught it fits in CI: run the same prompt cold and warm at temperature 0, and assert the token IDs match exactly. A correct cache changes cost, never content. It is yours because you can run this against your own prompt-caching provider this week, and the diff is the proof.

Neither post needs new research. Both need the receipts, which the next section lists.

## Sources

- SGLang issue #38815: the incident itself. The warm-versus-cold symptom, the key96 to state192 arithmetic, and the reproduction setup (one H200, model thinkingmachines/Inkling, page size 1, commit bd087fc). Read 2026-09-28.

- SGLang PR #37584: the merged guard. The length check at both commit sites, and the validation that all three input groups fail with 96 != 64 when the guard is removed. Merged 2026-09-12.

- Hybrid models meet SGLang, PyTorch Foundation blog: the quoted property behind the checkpoint grid. SSM states update in place and cannot be rolled back to a prefix. Same team as the code, so corroboration rather than independence.

- Issue #38815 comment thread: he-yufeng's independent re-derivation of the mechanism before writing the guard, and the reviewer's follow-up that the two geometries are guarded, not unified.

Two things stay unverified. Whether issue #38815 is closed now: the PR carries "Fixes #38815", but the reviewer's follow-up suggests partial closure only, and no closing event appeared in the comments read. And the vLLM design doc on its hybrid KV cache manager returned HTTP 429, so the vLLM-side answer to the same geometry problem is unread. All pages above were read on 2026-09-28.