_fails · Inference Internals Phase 1: The Request Lifecycle · Adds: two real lifecycle failures the course cannot stage, one KV bug hidden behind green dashboards and one 223-second queue stall, and the five questions that found them_

# Why were the dashboards green while the model talked nonsense?

## Why you are here: a green dashboard over a broken model

Picture your own inference server. KV cache on, tokens coming out at the expected rate, latency charts flat. Your load test passes. Nothing in the serving stack is complaining.

Then someone runs an eval against the served model and it scores near zero. Not zero points because prompts failed to parse. Zero because the model is reading corrupted state and producing confident garbage, at full speed. Both incidents in this article happened exactly that way. The dashboards reported a healthy system, and the system was wrong.

The source is a vLLM engineering post about running MiniMax M3, a sparse mixture-of-experts model, on AMD's MI355X GPU. I do not care about the GPU or the 3.14x speedup. I care about the failures they documented on the way, because those failures live exactly where Phase 1 lives: prefill, the KV cache, decode, and the queue in front of all of it.

## Nothing was slow. Everything was wrong.

The first bug, tracked as vLLM #45720. The model served fine with an FP8 KV cache on an AMD MI300X. Tokens per second normal. Latency normal. When the team ran GSM8K, a grade-school maths benchmark scored by strict match, the result was 0.0099. Close to zero correct answers. Serving metrics alone would never have caught it, because generation still produced tokens at the expected rates.

The wrong theory was the most natural one: the FP8 KV cache "was just working". The code assumed the way FP8 values are laid out in memory was portable across all ROCm, AMD's GPU platform. On this hardware the values are stored in a variant called FNUZ, and the code was viewing the cached keys and values through the wrong format. The fast path ran. It did the wrong math.

The signal that ended the search was not a metric. It was a correctness gate: the GSM8K eval, run beside the performance gate. That mismatch was the only contradiction available. The fix was to correct the FP8 KV view on FNUZ devices. Strict match went from 0.0099 to 0.9575.

A sibling bug, #47158, passed the wrong expert-parallel mask to the kernel library. The detector there was cosine similarity against a reference model: 0.527 instead of 1.0. Notice the shape. Wrong math still produced plausible text. Phase 1 names every stage of the request lifecycle. Nothing in that lifecycle can see this, because every stage completed normally.

## The same bug at the prefill-decode boundary

The second failure is the one closest to your phase. Phase 1 runs prefill and decode on the same GPU. Prefill/decode disaggregation splits them onto different workers: one worker fills the KV cache, ships it over the network, a second worker decodes from it. That transfer is a lifecycle stage the course assumes is trivial. It is not.

Symptom, in the authors' words: "The transfer completed and throughput looked healthy, but GSM8K fell to roughly 0.0008." Token salad. Every serving dashboard was green.

The wrong theory: the transfer code assumed the first layer's KV layout represented every layer. In fact this model has three different KV geometries: separated K and V tensors, interleaved K and V tensors, and a key-only index cache. Layer 1 told the truth only about layer 1.

The signal was again the eval, the only instrument contradicting the dashboards. The fix took three pull requests. #46039 computed transfer geometry and byte offsets per layer, with no sharing of layer metadata. #46290 counted the writes scheduled per request, sealed the count after the forward pass, and released buffers only after those writes completed. Ownership and completion, not fire-and-forget. #46332 handled mismatched parallelism: with prefill at TP4 and decode at TP8, two decode ranks consume one prefill rank's output, so both must acknowledge before the prefill rank may reuse its block.

The generalized rule, from a related cache bug: a cache key must contain every invariant that changes the cached object. Layout is an invariant. Parallelism topology is an invariant. If either can change and the key does not see it, you cache garbage correctly.

## Did the fast path even run?

One more failure, and this time the victim was the authors themselves. The post originally attributed part of a speedup to INT4 QuickReduce, a compressed communication path. On audit they found INT4 was configured with a 256KB threshold, but the roughly 1.5MB decode collective never passed QuickReduce's separate 16MB eligibility gate. The code path the gain was attributed to never executed.

Their words: "configured != eligible != executed". Three facts, and each is cheap to verify and easy to assume. You will flip flags in vLLM or any other serving stack: cache offloading, quantization backends, fused kernels. The flag being set, the path being eligible, and the kernel actually running are three different claims with three different proofs. A profiler or dispatch trace answers the third one. Config answers only the first.

## Why can 2,000 tokens a second be unusable?

The last failure is about the queue, and it is the one the course least prepares you for. The first public disaggregated profile, InferenceX run #1762, used one TP8 prefill worker and one TP8 decode worker at concurrency 1024 on an 8K input / 1K output workload. It reached 2,084.6 total tokens/s/GPU. It also had a median time to first token of 223.20 seconds. The throughput number described a system nobody could use.

The hidden assumption: more aggregate throughput means a working deployment. The signal that located the problem, in their phrase, "the prompt queue was the signal". Requests were waiting in admission, in front of prefill, not in any kernel.

Run #2144 moved every worker to TP4, searched the prefill-to-decode ratio, and landed on two TP4 prefill workers feeding one TP4 decode worker at concurrency 512. Result: 6,370.5 tokens/s/GPU with a 1.32 second median TTFT. Three times the throughput, 169 times faster to first token, and no kernel got faster. The interesting detail: mean TPOT, the time per output token during decode, got worse, from 31.26 ms to 54.60 ms. That is not a contradiction. The extra prefill capacity drained the admission queue, and the chosen decode point ran each active sequence slower. A disaggregated deployment has at least two latency objectives: time to first token and time per output token. A fix can move them in opposite directions on purpose. Publish both.

## The five questions, and the bug each one caught

The post's real result is a method: five diagnostic questions you apply to one decode step, escalating up the stack as each level's bottleneck flattens. Each one found something concrete.

1. **What shape reached this rank?** Kernels see local GEMM shapes after sharding and head replication, not the model card's global dimensions. Found: decode and prefill need different kernel launchers (7.8 to 9.4% at TP8).
2. **What work repeats?** Found: the shared expert in every MoE layer ran as a separate dense pass. Fusing it: +30.2% throughput at concurrency 1, +5.6% at 128. The shrinking gain is the signature of launch-overhead amortization.
3. **Which bytes move?** Weights, persistent KV state, and communication are three byte planes with separate contracts. "The model is MXFP4" says nothing about which plane is quantized.
4. **Did the intended fast path run, with the intended math?** Found: the FP8 KV bug, the transfer bug, the mask bug, and the QuickReduce retraction.
5. **When kernels flatten, which queue grows?** Found: the admission queue, and finally an OS limit: one high-concurrency run exhausted the container's file-descriptor cap and died on TCP failures.

The arc is the lesson. The bottleneck moves from kernel tiles, to repeated work, to KV state, to the queue. The diagnostic question has to move with it. It ends at: follow the queue.

## What a correctness gate looks like

The cheapest version of the instrument that caught incidents one and two is a fixed prompt set with a known-answer check. This runs against any OpenAI-compatible server, stdlib only:

```python
import json, re, urllib.request

PROMPTS = [
    ("Natalia sold clips to 48 friends in April, and half as many in May. "
     "How many clips did she sell altogether in April and May?", 72),
    ("A robe takes 2 bolts of blue fiber and half that much white fiber. "
     "How many bolts in total does it take?", 3),
    ("Weng earns $12 an hour for babysitting. She babysat 50 minutes. "
     "How much did she earn?", 10),
]  # extend to 30-50 items; three is enough to expose a layout bug

URL = "http://localhost:8000/v1/chat/completions"

def ask(server, prompt):
    body = json.dumps({
        "model": "minimax-m3", "temperature": 0,
        "messages": [{"role": "user",
                      "content": prompt + " End with '#### <number>'."}],
        "max_tokens": 512,
    }).encode()
    req = urllib.request.Request(server, data=body,
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    return r["choices"][0]["message"]["content"]

def strict_match(text):
    m = re.search(r"####\s*(-?[\d,]+(?:\.\d+)?)", text)
    return float(m.group(1).replace(",", "")) if m else None

score = sum(strict_match(ask(URL, p)) == a for p, a in PROMPTS) / len(PROMPTS)
print(f"strict match: {score:.4f}  ({len(PROMPTS)} prompts, temperature 0)")
```

Pin temperature to 0 so the number is stable. Run it in CI, or after any change to the KV cache, quantization, or a fast-path flag. A strict-match drop with flat throughput is incident one. This harness costs an evening once and pays out the first time a config change corrupts state.

## Fifteen minutes today

Take the script above, point it at whatever model you serve locally, and run it once to get a baseline. Then flip one serving flag you have set (KV quantization, cache offload, anything) and run it again. If the load test was your only gate, you now have two gates. Fifteen minutes, and it answers the question behind this whole article.

## A question to test the transfer

You enable an FP8 KV cache on your decode workers and long-context replies start reading as garbage under load, while every latency chart is flat. Using the lifecycle from Phase 1, which stage do you instrument first, and what single number do you check before any throughput chart? (A correct answer names the KV cache's storage contract and the strict-match score on a fixed prompt set, and can say why TTFT and TPOT cannot see the problem.)

## Things I could not verify

- Every performance number is from the post's own text. I did not cross-check against SemiAnalysis InferenceX's independent database (runs #1762, #2144, #2187).
- The pull request numbers are quoted from the post; none were opened.
- MiniMax M3's spec (60 layers, 57 sparse, MXFP8/MXFP4 checkpoints) is as the post states; not checked independently.
- The file-descriptor incident is one sentence with no PR number; treat it as an anecdote.
- This is a vendor post about the vendor's own benchmark. It is an unusually honest one (it retracts a claim against itself), but the numbers stay the authors' numbers.
- The QuickReduce threshold details (256KB codec, 16MB gate, BF16 at TP4) are the authors' reading of their own pinned config, not a source file I checked.

## Two things you could post

1. "Your inference server can hit 2,084 tokens/s/GPU with a 223-second TTFT." Claim: throughput is a vanity metric until you publish the queue. Yours because Mission HQ has real admission queues and you can show same shape in an agent executor.
2. "Configured is not eligible is not executed." Claim: the flag you flipped may never have run; ask for the dispatch trace before believing the speedup. Yours because you can walk one gated fast path in your own stack to the kernel level.

## Sources

- [Following the Bottleneck: Optimizing MiniMax M3 on AMD Instinct MI355X](https://vllm.ai/blog/2026-09-10-minimax-m3-mi355x) (vLLM blog, 2026-09-10; all numbers are the post's own, not cross-checked)
