# Phase 2 — Internals (the phase where you stop guessing about other people's requests)

Phase 1 gave you one request in isolation. You measured its TTFT, its TPOT, and its bill. That model is correct and it is incomplete. A real inference server never runs one request. It runs a loop over a batch, and your request shares a GPU with strangers.

This phase opens that loop. After it you can answer questions that Phase 1 could not:

- Why did my TTFT triple at 3pm when my prompt did not change?
- Why did the stream freeze for 800ms in the middle of a sentence?
- Why does the same prompt cost 4x less on the second call, and how do I make that happen every time?
- Why did my strict JSON schema make the answers worse?
- My agent died with a 400 after 40 turns. What is the correct fix, and why is a retry not it?

Two of these you already met. Phase 1 exercise E7 overflowed the context window on purpose and got a 400 back. Phase 1 exercise E11 truncated a JSON answer and told you constrained decoding exists. This phase pays both debts. Section 2.6 builds the compaction trigger. Section 2.5 builds the constrained decoding lesson and measures its cost.

Time: 3 to 4 hours. Two of the five lab scripts need no API key and no GPU.

## What we cover in Phase 2:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  2.1  The scheduler loop        — continuous batching, and why your      │
│                                   latency depends on strangers           │
│  2.2  The paged KV cache        — why the server fits 18x more requests  │
│  2.3  Prefix caching inside     — the radix tree, block granularity,     │
│       the server                  eviction, and what your layout costs   │
│  2.4  Chunked prefill           — the TTFT and TPOT tug of war           │
│  2.5  Constrained decoding      — token masking, and the constraint tax  │
│  2.6  Context budget and        — the trigger that prevents E7, and the  │
│       compaction                  backstop that catches it anyway        │
└──────────────────────────────────────────────────────────────────────────┘
```

Setup once:

```
cd ~/Desktop/project/code/study-material/inference-internals/code
pip install -e .       # or: uv sync
```

Scripts that need no API key: `paging_lab.py`, `prefix_cache_sim.py`, `batching_sim.py`, `compactor.py --simulate`, and `structured_lab.py --self-test`. Everything else needs `export OPENAI_API_KEY=sk-...` or any OpenAI-compatible endpoint through `--base-url` and `--key-env`.

---

## 2.1 — The scheduler loop (your latency depends on strangers)

Why this matters: you cannot explain a latency spike until you know what the server does between your requests. The answer is a loop, and your request is one row inside it.

Here is the loop that vLLM, SGLang, TensorRT-LLM and every hosted provider run. The names differ. The shape does not.

```
┌──────────────────────────────────────────────────────────────────────┐
│  ONE SCHEDULER ITERATION                                             │
│                                                                      │
│  1. look at the waiting queue and the running set                    │
│  2. pick work that fits a token budget and a memory budget           │
│  3. run ONE forward pass over all of it together                     │
│  4. every decoding request gets exactly ONE new token                │
│  5. finished requests leave; freed memory returns to the pool        │
│  6. go to step 1                                                     │
└──────────────────────────────────────────────────────────────────────┘
```

Step 4 is the fact that surprises people. One iteration produces one token per request, no matter how many requests are in the batch. So 40 requests in a batch finish 40 tokens in the time one request finishes 1 token.

That is possible because of what a decode step actually does. It reads the entire model weights from GPU memory once. Then it does a small amount of arithmetic for each sequence in the batch. The memory read dominates. Adding a sequence adds arithmetic, and arithmetic is the cheap part.

**Static batching was the old way.** The server collected N requests, ran them together, and waited for the last one to finish before admitting anyone new.

```
STATIC BATCHING — the slowest request holds the whole batch hostage

  slot 1  ████████████░░░░░░░░░░░░░░░░░░░   done at t=1.2s, then idle
  slot 2  ████████████████████████░░░░░░░   done at t=2.4s, then idle
  slot 3  ██████████████████████████████░   done at t=3.1s
  slot 4  ██████░░░░░░░░░░░░░░░░░░░░░░░░░   done at t=0.6s, then idle
          └──────────── new requests wait here ─────────────┘
          t=0                                            t=3.1s
  ░ = a slot that holds GPU memory and produces nothing
```

**Continuous batching is the current way.** The scheduler runs admission every iteration. A finished request leaves immediately and a waiting one takes its place on the next step.

```
CONTINUOUS BATCHING — a freed slot is refilled on the next iteration

  slot 1  ████████████▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓   req A done → req E starts
  slot 2  ████████████████████████▓▓▓▓▓▓▓   req B done → req F starts
  slot 3  ██████████████████████████████▓   req C running
  slot 4  ██████▓▓▓▓▓▓▓▓████████████████▓   req D done → G → H
          t=0                                            t=3.1s
  no ░ anywhere. That is the whole idea.
```

This is called iteration-level scheduling. The Orca paper introduced it in 2022 and every serving engine adopted it.

**Measure it yourself.** `batching_sim.py` simulates this loop. Run it:

```
python phase02_internals/batching_sim.py
```

Output from this machine, 40 requests at 6 arrivals per second:

```
┌────────────┬───────────┬───────────┬───────────┬────────────┬────────────┐
│ policy     │ mean TTFT │ p99 TTFT  │ mean TPOT │ worst gap  │ throughput │
├────────────┼───────────┼───────────┼───────────┼────────────┼────────────┤
│ static     │    5357ms │    9187ms │    19.4ms │       20ms │   2.3 rq/s │
│ continuous │     867ms │    2642ms │    25.4ms │      764ms │   3.6 rq/s │
│ chunked    │     925ms │    2694ms │    25.5ms │       81ms │   3.5 rq/s │
└────────────┴───────────┴───────────┴───────────┴────────────┴────────────┘
```

Read the first two rows now. Ignore `chunked` until section 2.4. Continuous batching cut mean TTFT from 5,357ms to 867ms and raised throughput by 57%. It also raised mean TPOT from 19.4ms to 25.4ms. That is not a bug. A busier batch decodes slightly slower per token, and you traded that for a 6x better TTFT.

Now look at the `worst gap` column: 764ms for continuous batching. That is the longest pause between two tokens of one answer. Section 2.4 explains where it comes from.

**What you actually control.** You do not control the provider's scheduler. You control four inputs to it:

```
┌────────────────────────┬──────────────────────────────────────────────┐
│ Your input             │ What it does to the batch                    │
├────────────────────────┼──────────────────────────────────────────────┤
│ prompt length          │ a long prefill occupies the token budget and │
│                        │ delays every decoding request in the batch   │
│ output length          │ a long generation holds a slot and its KV    │
│                        │ memory for the whole time                    │
│ arrival pattern        │ 50 requests at once queue; 50 spread out do  │
│                        │ not                                          │
│ prefix reuse           │ a cached prefix skips prefill entirely, so   │
│                        │ it never competes for the token budget       │
└────────────────────────┴──────────────────────────────────────────────┘
```

**The sentence to remember:** one scheduler iteration gives every running request exactly one token, so throughput comes from batch size and latency comes from what else is in the batch.

**The trap:** you will try to fix a TTFT spike by adding retries. A retry adds one more request to the same queue. Under load that makes the queue longer and the spike worse. Phase 1 Story 2 is exactly this mistake, and Phase 5 builds the correct signal.

**Try this now:** run `python phase02_internals/batching_sim.py --rate 12` and compare the static and continuous rows against the default run. Note which column changes most when arrivals get faster.

---

## 2.2 — The paged KV cache (why the server fits 18x more requests)

Why this matters: Phase 1 told you the KV cache costs bytes per token. That explains memory. It does not explain concurrency. This section explains concurrency, and concurrency is what sets queue time.

Start with the naive allocator, because it shows the problem. The server admits a request. It does not know how long the answer will be. To be safe it reserves memory for the worst case, which is `max_model_len`.

```
CONTIGUOUS RESERVATION — one 32,768-token reservation per request

  request A  ┌──────────────────────────────────────────────┐
             │██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│  4.00 GB held
             └──────────────────────────────────────────────┘
              ↑ 1,800 tokens used      ↑ 30,968 tokens wasted

  56 GB KV pool ÷ 4.00 GB = 14 concurrent requests, and 52.9 GB idle
```

PagedAttention fixes this with an idea taken from operating system virtual memory. The KV cache for one sequence does not have to be one contiguous region. Split it into fixed-size blocks. Allocate a block only when the sequence needs it. Keep a block table that maps logical positions to physical blocks.

```
PAGED BLOCKS — 16 tokens per block, allocated on demand

  request A block table:  [ #91 ][ #14 ][ #55 ][ #7 ] ... 113 blocks
                             │      │      │     │
  physical KV pool  ┌────┬────┬────┬────┬────┬────┬────┬────┬────┐
                    │ #7 │#14 │ .. │#55 │ .. │#91 │ .. │free│free│
                    └────┴────┴────┴────┴────┴────┴────┴────┴────┘
  blocks need not be adjacent, and nothing is reserved for the future
```

Run the arithmetic yourself:

```
python phase02_internals/paging_lab.py
```

Output on this machine for llama-3-8b on one 80GB GPU:

```
┌────────────────────────┬────────────────────┬────────────────────┐
│                        │ contiguous         │ paged              │
├────────────────────────┼────────────────────┼────────────────────┤
│ reserved per request   │         32,768 tok │          1,808 tok │
│ bytes per request      │            4.00 GB │            0.22 GB │
│ concurrent requests    │                 14 │                253 │
│ memory actually used   │             3.1 GB │            55.6 GB │
│ memory wasted          │            52.9 GB │             0.2 GB │
└────────────────────────┴────────────────────┴────────────────────┘

paging admits 18.1x more concurrent requests here.
internal waste per request under paging: 8 tokens
```

18.1x more concurrent requests on the same hardware. No model change, no new GPU. That is why PagedAttention mattered enough to become the default everywhere.

The paper measured the same problem on real systems rather than in a simulator. It found that only 20.4% to 38.2% of KV cache memory held actual token state. The rest was reserved slots and fragmentation. Paging cut that waste to about 4%, a number the vLLM authors state in their own talk.

**Three things to internalize:**

1. **Block size sets the leftover waste.** A request holding 1,800 tokens with a 16-token block holds 113 blocks, which is 1,808 token slots. The 8 unused slots are internal fragmentation. It is small and it is the only waste paging leaves.
2. **Identical blocks can be shared.** Two requests with the same first 1,200 tokens can point at the same physical blocks. The server stores that prefix once. Section 2.3 is entirely about this.
3. **Running out of blocks does not return an error.** The scheduler preempts. It evicts a running sequence's blocks and puts the request back in the queue. The request resumes later, and the server must redo the prefill it threw away. Your symptom is a sudden TTFT spike on a request that had already started.

**Preemption looks like this in time:**

```
  t=0.0s   request R decoding normally, 40 blocks held
  t=1.2s   a burst arrives; the block pool runs out
  t=1.2s   scheduler preempts R: its 40 blocks are freed
  t=1.2s   R goes back to the WAITING queue, tokens already streamed stay streamed
  t=2.9s   blocks free up; R is admitted again
  t=2.9s   R's prompt is prefilled AGAIN — that work was thrown away
  t=3.1s   R resumes streaming

  what the user saw: the answer stopped for 1.9 seconds, then continued
  what your logs saw: nothing, unless you record inter-token gaps
```

**The sentence to remember:** paging turns "how much memory could this request need" into "how much does it need right now", and that single change is what makes high concurrency possible.

**The trap:** `gpu_memory_utilization` looks like a safety setting and behaves like a capacity setting. vLLM 0.29.0 defaults it to 0.92. Lowering it to 0.70 on an 80GB GPU removes about 17GB from the KV pool. In the table above that is most of your concurrency. The lab script defaults to 0.90 so the arithmetic stays round. Pass `--gpu-util 0.92` to match vLLM.

**Try this now:** run `python phase02_internals/paging_lab.py --model llama-3-70b --gpu-gb 80`. Read the error. Then run it with `--gpu-gb 320` for a four-GPU node and compare the concurrency number against the 8B model.

---

## 2.3 — Prefix caching inside the server (the radix tree and the eviction that ends it)

Why this matters: Phase 1 exercise E6 showed you that one changed character early in the prompt destroys the cache hit. You measured the effect. Now you learn the mechanism, because the mechanism tells you exactly where the boundary is.

Section 2.2 said identical blocks can be shared. The server needs a way to find them fast. It keeps a tree keyed by the token sequence. SGLang calls its version RadixAttention. vLLM calls its version automatic prefix caching. The structure is the same.

```
THE PREFIX TREE — three requests that share a system prompt

                    [ root ]
                       │
          ┌────────────┴─────────────┐
          │  blocks 0..74            │   ← 1,200-token system prompt
          │  "you are a support..."  │      stored ONCE, shared by all
          └────────────┬─────────────┘
              ┌────────┼────────┐
              │        │        │
        ┌─────┴───┐ ┌──┴────┐ ┌─┴──────┐
        │ user A  │ │user B │ │ user C │  ← private blocks, one set each
        │ history │ │history│ │history │
        └─────────┘ └───────┘ └────────┘

  A new request walks down from the root. It reuses every node it matches.
  It stops at the first block that differs. Everything below that is a miss.
```

The matching rule has three parts, and each one is a place teams lose money:

1. **Matching starts at token 0 and moves forward.** There is no partial match in the middle. A change at position 10 invalidates positions 10 to the end.
2. **Matching happens in whole blocks.** With a 16-token block, a prefix of 1,210 tokens shares only 75 full blocks, which is 1,200 tokens. The last 10 tokens sit in a partial block and cannot be shared.
3. **Entries expire.** The tree has a fixed size. Blocks leave under a least-recently-used rule. Hosted providers also apply a time limit, commonly a few minutes of inactivity.

**Measure the layout cost.** `prefix_cache_sim.py` builds this tree for an agent loop, under two layouts holding the same information.

```
python phase02_internals/prefix_cache_sim.py
```

```
┌────────────────┬──────────┬─────────────┬─────────────┬──────────┬───────────┐
│ layout         │ requests │ input toks  │ cached toks │ hit rate │ cost      │
├────────────────┼──────────┼─────────────┼─────────────┼──────────┼───────────┤
│ volatile-first │       30 │     148,560 │           0 │     0.0% │ $  0.0594 │
│ stable-first   │       30 │     148,560 │     136,656 │    92.0% │ $  0.0184 │
└────────────────┴──────────┴─────────────┴─────────────┴──────────┴───────────┘

stable-first costs 3.22x less on input for the same information.
```

Identical token count. Identical information. 3.22x difference in price. The only change is the order of the blocks in the prompt.

Here is the wrong layout and the right one, as code:

```python
# WRONG: the timestamp is in the system message, so byte ~40 changes every call.
# Every later token is a cache miss. Hit rate measured by the simulator: 0.0%.
messages = [
    {"role": "system", "content":
        f"Current time: {datetime.now().isoformat()}\n"      # <-- volatile, position 0
        f"{SYSTEM_PROMPT}\n{TOOL_SCHEMAS}"},                 # <-- stable, after it
    *history,
]

# RIGHT: stable content first, volatile content last.
# Everything above the timestamp matches from token 0 on every call.
messages = [
    {"role": "system", "content": f"{SYSTEM_PROMPT}\n{TOOL_SCHEMAS}"},
    *history,
    {"role": "user", "content":
        f"{user_text}\n\n[context] Current time: {datetime.now().isoformat()}"},
]
```

The failure the wrong version produces is silent. There is no error and no warning. Your bill is 3x higher and your TTFT is worse, and nothing in your logs says why. That is the reason this section exists.

**What eviction does to a good layout.** A correct layout still goes cold when the cache fills. Run the simulator with a small cache:

```
python phase02_internals/prefix_cache_sim.py --capacity-blocks 500 --users 5 --steps 12
```

Hit rate on this machine falls from 92.0% to 68.8%, and the simulator reports 5,615 evictions. Nothing about your prompt changed. Other tenants filled the cache.

Real deployments report the same range. The SGLang paper measured production hit rates on Chatbot Arena traffic: 52.4% for LLaVA-Next-34B and 74.1% for Vicuna-33B. Across its benchmarks the range was 50% to 99%. A hit rate near 100% is a property of a synthetic test, not of production traffic.

**The sentence to remember:** the cache matches whole blocks from token 0 forward, so put what never changes first and what changes every call last.

**The trap:** a cache hit is never guaranteed, so never build a cost model that assumes one. Model the cached and uncached price, and alert on the hit rate. Phase 3 extends `prices.yaml` with the cached-input price so your meter can do this arithmetic.

**Try this now:** run the simulator with `--block-size 64` and compare the hit rate against the default of 16. Larger blocks share less at the edges.

---

## 2.4 — Chunked prefill (the tug of war between TTFT and TPOT)

Why this matters: section 2.1 left a number unexplained. Continuous batching produced a 764ms worst gap between two tokens of one answer. Your user sees that as the stream freezing. This section explains the cause and the fix.

Go back to the scheduler loop. One iteration runs one forward pass. That pass can do prefill work, decode work, or both. Now a new request arrives with a 24,000-token prompt.

Without chunking, the server has two bad options. It can run the whole 24,000-token prefill in one iteration. Every decoding request in that batch produces no token during that iteration. Or it can wait until decodes finish, which makes the new request's TTFT terrible.

```
NO CHUNKING — one giant prefill stalls every stream in the batch

  iteration:      1      2      3           4           5      6
  prefill  :      -      -      -    [24,000 tokens]    -      -
  decode   :   A B C  A B C  A B C        none       A B C  A B C
  duration :    20ms   20ms   20ms        720ms       20ms   20ms
                                       ▲
                          A, B and C all freeze for 720ms here
```

Chunked prefill splits that prompt. Each iteration takes a slice of the prefill plus all the decodes, under one token budget. In vLLM that budget is `max_num_batched_tokens`.

```
CHUNKED PREFILL — the same work, spread across iterations

  iteration:    1        2        3        4        5        6
  prefill  :    -     2,045    2,045    2,045    2,045    2,045   ... (12 total)
  decode   : A B C    A B C    A B C    A B C    A B C    A B C
  duration : 20ms      81ms     81ms     81ms     81ms     81ms
                       ▲
         the new request's TTFT gets slightly worse, and nobody freezes
```

The budget is shared. With `max_num_batched_tokens=2048` and 3 decoding requests, the iteration spends 3 tokens on decode and up to 2,045 on prefill.

Run the comparison:

```
python phase02_internals/batching_sim.py --long-prompt 48000 --rate 10 --requests 60
```

Output on this machine:

```
│ policy     │ mean TTFT │ p99 TTFT  │ mean TPOT │ worst gap  │ throughput │
│ static     │    8690ms │   14381ms │    19.5ms │       20ms │   2.7 rq/s │
│ continuous │    3028ms │    6957ms │    25.5ms │     1460ms │   3.8 rq/s │
│ chunked    │    3140ms │    7024ms │    24.9ms │       81ms │   3.8 rq/s │
```

Chunked prefill costs 112ms of mean TTFT. It buys a drop in the worst inter-token gap from 1,460ms to 81ms. That is an 18x improvement in the number your users actually feel during a stream.

The Sarathi-Serve paper measured this effect on real hardware. Mixing a prefill into a decode batch without chunking raised time between tokens by 28.3x compared with a decode-only batch. That is the freeze, measured rather than simulated.

Chunking is not free either, and the same paper says so. At a 512-token budget it measured about 25% overhead on Yi-34B, because splitting a prefill repeats work at the chunk boundaries. So the setting has a floor. Below it you buy smoothness with throughput.

This is a real trade, and the direction depends on your product:

```
┌──────────────────────────┬────────────────────────┬───────────────────────┐
│                          │ larger token budget    │ smaller token budget  │
├──────────────────────────┼────────────────────────┼───────────────────────┤
│ TTFT for long prompts    │ better                  │ worse                 │
│ inter-token smoothness   │ worse                   │ better                │
│ good for                 │ batch jobs, summarising │ chat, voice, streaming│
│ vLLM setting             │ max_num_batched_tokens  │ same setting, lower   │
└──────────────────────────┴────────────────────────┴───────────────────────┘
```

One correction worth carrying into Phase 4. `max_num_batched_tokens` has no single default in vLLM 0.29.0. The server picks it at startup from the GPU class, and from whether you run the offline `LLM` class or the API server. On an H100 through the API server it is 8,192. On most other GPUs including the A100 it is 2,048. The constant named `DEFAULT_MAX_NUM_BATCHED_TOKENS` exists only for tests.

**What this means when you use a hosted API.** You cannot set `max_num_batched_tokens` on someone else's server. You still see the effect, and you can still act on it in two ways. First, record inter-token gaps, not just TTFT and total time. A frozen stream is invisible in an average. Second, keep your own prompts smaller, because your giant prefill is somebody else's freeze, and on a single-tenant deployment it is your own.

**The sentence to remember:** prefill and decode compete for the same forward pass, so a long prompt either delays itself or freezes everyone else, and chunking chooses which.

**The trap:** teams measure TTFT and total latency and declare the stream healthy. Neither number can see an 800ms freeze in the middle. Add a maximum inter-token gap metric before you promise a streaming experience.

**Try this now:** in `batching_sim.py`, run `--token-budget 512` and then `--token-budget 8192`. Watch mean TTFT and worst gap move in opposite directions.

---

## 2.5 — Constrained decoding and the constraint tax

Why this matters: Phase 1 exercise E11 truncated a JSON answer and your parser broke. The lesson there was about `finish_reason`. The other half of that lesson is this: asking a model for JSON in the prompt is a request, not a guarantee. Constrained decoding turns it into a guarantee. It also has a price, and most teams never measure it.

### How the server enforces a schema

Decoding picks one token at a time. Before the pick, the model produces a score for every token in the vocabulary. Those scores are called logits. Sampling then chooses one.

Constrained decoding inserts a step between those two. It sets the score of every token that would break the schema to negative infinity. Those tokens then have zero probability. The model can only choose a legal continuation.

```
ONE DECODE STEP, WITH AND WITHOUT A GRAMMAR MASK

  model logits        mask (from the schema)      masked logits
  ┌──────────────┐    ┌──────────────────┐        ┌──────────────┐
  │ "Sure"  4.1  │    │ illegal here  ✗  │   →    │ "Sure"  -inf │
  │ "{"     3.8  │    │ legal         ✓  │   →    │ "{"      3.8 │  ← chosen
  │ "Here"  3.5  │    │ illegal here  ✗  │   →    │ "Here"  -inf │
  │ "["     2.9  │    │ illegal here  ✗  │   →    │ "["     -inf │
  └──────────────┘    └──────────────────┘        └──────────────┘

  The state machine now moves to "expecting a key or }". The next step gets a
  different mask. Prose can never appear, because prose tokens are never legal.
```

The mask comes from a state machine compiled from your schema. The engine walks your JSON Schema or grammar, builds the states, and precomputes which vocabulary tokens are legal in each state. Three libraries do this work today: Outlines, XGrammar, and llguidance. vLLM and SGLang use them underneath.

Building that machine costs time, and the cost depends on the engine. JSONSchemaBench measured median grammar compilation time on the same schemas: about 0.01s for Guidance, 0.11s to 0.30s for XGrammar, and notably higher for Outlines, which converts JSON Schema into a regular expression first. XGrammar overlaps its compilation with the prefill, so you often do not see it.

On a hosted API the picture changed recently, and this is a place where older material is now wrong. OpenAI's current structured outputs page scopes the first-request schema latency to fine-tuned models only. Its words are that other models do not have this limitation. No time bound is published either way. So measure your own provider rather than repeating a rule.

### The three levels, and what each one actually promises

```
┌────────────────────┬───────────────────┬──────────────────┬─────────────────┐
│                    │ prompt only       │ json_object      │ json_schema     │
│                    │                   │                  │ strict: true    │
├────────────────────┼───────────────────┼──────────────────┼─────────────────┤
│ valid JSON         │ not guaranteed    │ guaranteed       │ guaranteed      │
│ correct keys       │ not guaranteed    │ NOT guaranteed   │ guaranteed      │
│ values within enum │ not guaranteed    │ not guaranteed   │ guaranteed      │
│ prose wrapping     │ happens           │ cannot happen    │ cannot happen   │
│ first-call cost    │ normal            │ normal           │ engine compiles │
│                    │                   │                  │ the grammar     │
│ can still truncate │ yes               │ yes              │ yes             │
└────────────────────┴───────────────────┴──────────────────┴─────────────────┘
```

Read the last row twice. A schema controls which tokens are legal. It does not control when generation stops. If `max_tokens` runs out mid-object, you get a truncated document that is still schema-shaped and still unparseable. `finish_reason` is the only thing that tells you. Phase 1 E11 is that failure, and strict mode does not remove it.

### The constraint tax

Here is the part that most material skips. Forcing a schema can change answer quality, not only answer shape. The literature on this disagreed loudly for two years, and a 2026 paper explains why. You need both parts.

**The original claim.** A 2024 EMNLP paper, "Let Me Speak Freely?", reported large drops on reasoning tasks. On GSM8K, claude-3-haiku scored 86.99 in plain JSON mode and 23.44 once a schema constraint was added. gpt-3.5-turbo fell from 74.70 to 49.25. Two details matter. The standard deviations were enormous, 22.9 and 12.0 across 9 prompts. And the same paper's own appendix shows constraints HELPING classification tasks: on DDXPlus, gemini went from 41.6 to 60.3 and claude-3-haiku from 33.8 to 52.0.

**The rebuttal.** The authors of Outlines re-ran the same model and tasks and measured the opposite: GSM8K 0.77 unstructured against 0.78 structured, Last Letter 0.73 against 0.77. Their objection was that the original paper never confirmed that a provider's JSON mode is grammar-constrained decoding at all. The original paper says it "is assumed". A third group's benchmark, JSONSchemaBench, also measured small gains.

**The 2026 resolution.** A paper called "The Format Tax" tested 6 open-weight and 4 closed-weight models across 4 formats and 4 tasks, and separated the two possible causes. Asking for a format in the prompt cost 3.9 points on average. Adding grammar-constrained decoding on top cost a further 1.6 points. Of 39 statistically significant effects, 36 were already present from the prompt alone and only 3 came from constrained decoding alone. So the tax is real, and the decoder is the smaller half of it.

Two more results from the same paper are directly useful to you:

- Recent closed-weight models showed no tax at all. claude-haiku-4.5 scored +1.2 and grok-4.1-fast +2.5 against their own freeform baseline. Small open models lost 5 to 9 points. Any statement of the form "structured output costs X percent" is wrong unless it names the model.
- Constraints raised format validity from 55.7% to 92.2% while accuracy moved from 57.3% to 55.7%, against a freeform baseline of 61.5%. The paper's summary of that is worth memorising: higher compliance does not translate into better reasoning.

**The scoring warning.** Every group in this argument was caught by the same problem. Tam et al. used a model to parse answers, and their own table shows parser choice moving a score by up to 42 points. The Format Tax authors switched from a rule-based extractor to a model judge and watched their measured tax shrink from 10.1 points to 6.6. About a third of it was a scoring artifact. So when you measure your own tax, fix the parser first and report it. A number without its parser means nothing.

So measure it. `structured_lab.py` runs the same 12 labeled tickets through all three modes:

```
python phase02_internals/structured_lab.py --self-test     # no key needed
export OPENAI_API_KEY=sk-...
python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap
```

The script reports accuracy, parse failures, output tokens, mean latency, first-call latency, and cost per mode. The accuracy gap between `prompt` and `strict` is your constraint tax on this task. It can be negative, which means the schema helped.

Then test the standard mitigation:

```
python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --reasoning-field
```

This adds one free-text field to the schema, placed before the constrained fields:

```python
# The ORDER of the properties is the whole point. Decoding runs left to right,
# so a field can only influence fields that come AFTER it.
{
  "type": "object",
  "properties": {
    "reasoning": {"type": "string"},              # free text, generated FIRST
    "category":  {"type": "string", "enum": CATEGORIES},
    "priority":  {"type": "string", "enum": PRIORITIES},
  },
  "required": ["reasoning", "category", "priority"],   # ALL keys must be here
  "additionalProperties": False,                        # this is mandatory
}
```

Put `reasoning` last and it changes nothing. The answer is already chosen by then. This is one of the few schema design rules with a mechanical reason behind it, and it has direct evidence. Tam et al. found that 100% of gpt-3.5-turbo JSON-mode answers put the answer key before the reason key, which turns step-by-step reasoning into direct answering. JSONSchemaBench used the opposite order and measured constrained decoding matching or beating unconstrained on the same three tasks.

Two other mitigations have measured numbers, from The Format Tax:

```
┌────────────────────────────┬──────────────┬───────────────┬────────────────┐
│ mitigation                 │ improved     │ made worse    │ average gain   │
├────────────────────────────┼──────────────┼───────────────┼────────────────┤
│ two calls: answer freely,  │ 42 of 72     │ 2 of 72 (3%)  │ +6.8 points    │
│ then reformat              │              │               │                │
│ thinking enabled before    │ 43 of 72     │ 11 of 72 (15%)│ +9.2 points    │
│ the structured answer      │              │               │                │
└────────────────────────────┴──────────────┴───────────────┴────────────────┘
```

Two calls is the safer choice and costs one extra request. Thinking is stronger on maths and unhelpful on writing. Neither is free, so pick after you measure.

**Three schema rules to get right on day one.** Every property must appear in `required`. `additionalProperties` must be `false`. An optional field is expressed as a union with null, such as `"type": ["string", "null"]`, never by leaving a key out of `required`.

The list of unsupported JSON Schema keywords has shrunk, so check the current page rather than an older blog post. As of September 2026 OpenAI's page lists `pattern`, `format`, `multipleOf`, `minimum`, `maximum`, `minItems` and `maxItems` as supported for normal models, and not yet supported for fine-tuned models. Still unsupported everywhere: `allOf`, `not`, `dependentRequired`, `dependentSchemas`, `if`, `then`, `else`. Several other keywords are simply absent from the page, so their status is undocumented. Test before you depend on one.

**When you serve this yourself, the engine picks a backend.** You meet this in Phase 4, and the behaviour matters now because it changes both errors and latency. vLLM 0.29.0 defaults to `auto`, which validates your schema against XGrammar, then falls back to Guidance, then to Outlines when a keyword is unsupported. If you pin a backend instead, the same unsupported keyword becomes an error. SGLang 0.5.19 defaults to XGrammar and has no per-schema fallback at all. The compile costs quoted above differ by an order of magnitude between these backends, so a silent switch is also a latency change.

**The sentence to remember:** constrained decoding masks illegal tokens at every step, so the shape is guaranteed, the stopping point is not, and the quality effect is yours to measure.

**The trap:** you will read an older article saying every new schema costs a first-request compile, and you will design around a cost your provider may no longer charge. Measure it. Keep the habit of defining schemas once at import time anyway, because a self-hosted engine does pay that cost per distinct schema.

**Try this now:** run `python phase02_internals/structured_lab.py --model gpt-4.1-mini --modes strict --repeat 3` and compare the `first call` column against the `mean lat` column. A large gap means your provider compiles per schema. A gap near zero matches what OpenAI's current documentation says for non-fine-tuned models. Record which one you got, with the date.

---

## 2.6 — The context budget and the compaction trigger

Why this matters: Phase 1 exercise E7 sent an oversized prompt and got a 400 back. The exercise promised you the fix here. This section is that fix, and it is more than a try and except block.

### First, the reason a bigger window does not solve this

You might think a one million token window ends the problem. It does not, for three separate reasons, and each one has evidence.

**Reason 1: accuracy falls as input grows.** Chroma's context rot study tested 18 models across Claude, GPT, Gemini and Qwen families. It ran deliberately simple retrieval tasks at many input lengths. Performance fell as length grew in every family. On the LongMemEval part, every model scored higher on a focused input of about 300 tokens than on the full input of about 113,000 tokens containing the same answer.

**Reason 2: position inside the window matters.** The Lost in the Middle study measured accuracy against where the needed document sat. With 20 documents, GPT-3.5-Turbo scored 75.8% when the answer was first and 53.8% when it sat in the middle. The middle score fell below the 56.1% the model scored with no documents at all. The models are from 2023, so treat the numbers as the shape of the effect, not as today's values.

**Reason 3: the cost is linear and the window is not free.** A 400,000-token prompt on every step of a 50-step loop is 20 million input tokens. At the `deep` role price in `prices.yaml`, that is $40 for one conversation.

```
THE SHAPE OF THE PROBLEM

  accuracy                                   cost
    ▲                                          ▲
    │████▄▄                                    │              ▗▄▞▘
    │      ▀▀▄▄▄                               │         ▗▄▞▘
    │           ▀▀▄▄▄▄                         │    ▗▄▞▘
    │                 ▀▀▀▄▄▄                   │▗▄▞▘
    └────────────────────────► tokens          └────────────────► tokens

  You are paying more, per token, for tokens that help less.
```

### The budget: zones with caps

A context window is a fixed resource that several producers write into. Without caps, the loudest producer wins, and the loudest producer is usually a tool that returned a large payload.

```
┌──────────────────────────────────────────────────────────────────┐
│ CONTEXT BUDGET for a 32,000-token window                         │
├──────────────────┬───────────┬───────────────────────────────────┤
│ zone             │ cap       │ rule                              │
├──────────────────┼───────────┼───────────────────────────────────┤
│ system           │   1,000   │ never changes; first in the prompt │
│ tools            │   6,000   │ changes on deploy only            │
│ carry-over       │   2,000   │ written by compaction             │
│ history          │  10,000   │ oldest turns leave first          │
│ retrieval/tools  │   6,000   │ truncate results, keep pointers   │
│ headroom for the │   7,000   │ the reply needs room, and so does │
│ answer           │           │ the summarising call              │
└──────────────────┴───────────┴───────────────────────────────────┘
```

That last row is the one people forget. If you fill the window to the edge, you cannot even run the summarisation call that would rescue you.

### The trigger: fire early, on a threshold you chose

Do not wait for the error. Count tokens before every call and compact when the total crosses a threshold you set.

Shipped products use thresholds well below the window. Anthropic's context editing tool clears old tool results at a default trigger of 100,000 input tokens and keeps the last 3 tool uses. Anthropic's server-side compaction feature defaults to a 150,000 input-token trigger and refuses values below 50,000. Claude Code compacts at about 967,000 tokens on models with a one million token window, and at the 200,000 boundary otherwise. The pattern is the same in all three: a fixed number, chosen ahead of time, below the limit.

There is a newer idea worth knowing. The Self-Compacting Language Model Agents paper argues that a token threshold fires at an arbitrary moment, sometimes in the middle of a derivation. It lets the model decide, guided by a rubric: compact when a sub-task resolves, and never mid-derivation or while stuck. It reports gains of up to 18.1 points on math benchmarks and 5 to 9 points on agentic search, at 30 to 70 percent lower cost per question. Treat this as the direction of travel. Start with a threshold, because a threshold is simple and testable.

### What to preserve, and the number that proves it matters

A summary keeps what the summariser thought was interesting. That is the failure. The specific things a later turn cannot re-derive are decisions, constraints, and open items.

Here is the evidence that constraints are the dangerous one. The ConstraintRot study ran 1,323 episodes across seven model families, with policy constraints stated in the context and tool calls graded deterministically. With the policy fully visible the violation rate was 0%. After compaction it rose to 30% on average and 59% for the worst model. Split by whether the constraint survived the summary: 0% when it survived, 38% when it was dropped. Copying the constraint text verbatim into the post-compaction context returned violations to 0%.

Read that as an engineering rule. Do not let a language model decide whether your safety rule is worth keeping. Copy constraints across the boundary as literal text.

```
COMPACTION BOUNDARY — what crosses it

  BEFORE (18,900 tokens)                AFTER (2,270 tokens)
  ┌─────────────────────────┐           ┌─────────────────────────┐
  │ system                  │──verbatim→│ system                  │
  │ tools                   │──verbatim→│ tools                   │
  │ turn 1  ─┐              │           │ [COMPACTED]             │
  │ turn 2   │              │           │  Summary: 45 turns ...  │
  │  ...     ├─ summarised ─┼──────────→│  Decisions: ...         │
  │ turn 44  │              │           │  Constraints: COPIED    │
  │ turn 45 ─┘              │           │  Open items: ...        │
  │ turn 46 ─┐              │           │ turn 46                 │
  │ turn 47  ├─ kept as is ─┼──verbatim→│ turn 47                 │
  │ turn 48  │              │           │ turn 48                 │
  │ turn 49 ─┘              │           │ turn 49                 │
  └─────────────────────────┘           └─────────────────────────┘
```

### The backstop: catch the 400, compact, retry once

The trigger can still be wrong. A tool can return far more than you expected. So keep a second layer, and make it loud.

```python
# WRONG: the classic retry. It resends the SAME oversized prompt.
# The provider rejects it again, in about the same time, for the same reason.
for attempt in range(3):
    try:
        return client.chat.completions.create(model=m, messages=msgs)
    except Exception:
        time.sleep(2 ** attempt)        # waiting changes nothing here

# RIGHT: change the input, then retry exactly once.
try:
    return client.chat.completions.create(model=m, messages=msgs)
except Exception as e:
    if not is_context_overflow(e):
        raise
    log.error("compaction trigger missed; backstop fired")   # this is a bug report
    msgs = compact(msgs)                                     # the input changed
    return client.chat.completions.create(model=m, messages=msgs)
```

Detect the error on its machine-readable fields, not its wording. The stable parts are HTTP status 400, an error `type` of `invalid_request_error`, and an error `code` of `context_length_exceeded`. OpenAI's public error-codes page does not list this error at all, so any exact message string you hardcode today can change without notice. `compactor.py` shows the detection order: code first, status second, message text last.

### See all of it run

```
python phase02_internals/compactor.py --simulate --turns 40
```

The trigger fires on this machine at turn 25:

```
  24 │     18,631 │
  25 │     19,409 │ trigger fired
    COMPACTED (threshold): 19,409 -> 2,270 tokens, 45 turns summarised, 4 kept verbatim
  25 │      2,270 │
```

Now watch the same loop without the trigger:

```
python phase02_internals/compactor.py --simulate --turns 60 --no-compaction
```

```
  41 │     31,857 │
  42 │     32,635 │ STOP: prompt exceeds the window. This is the E7 failure.
```

Turn 42 is where Phase 1's exercise ended. With the trigger on, that turn never arrives.

### The honest limits of compaction

Compaction is not a solved problem, and material that says otherwise is selling something.

- **Compaction can lower accuracy.** The Slipstream paper describes a validation gap: the compactor must shorten the context without knowing what the agent will need later. It reports up to 8.8 percentage points of accuracy recovered by validating candidate summaries and running them off the critical path, with up to 39.7% lower end-to-end latency.
- **Repeated compaction destabilises execution.** An August 2026 study on AppWorld found that compression weakens the influence of recent turns, which increases blocked actions and repeated work, and makes results vary between runs.
- **The horizon problem is not only about tokens.** A study of 10,664 trajectories across nine models found that task success decays with the number of steps rather than the context length. Restricting the context window made the decay steeper, not shallower. Per-step reliability rises with model scale but stays below 1, so long enough tasks fail regardless.
- **Compaction is billed.** Anthropic's compaction feature runs as a separate sampling iteration whose tokens are excluded from the top-level usage counts. You must add up `usage.iterations` to see the real total. Your own summarising call has exactly the same property: it is a second call, and your meter must count it.

**The sentence to remember:** compact on a threshold you chose, copy constraints across the boundary as literal text, and treat a 400 as a bug in your trigger rather than a normal event.

**The trap:** anything a summary drops is gone permanently. The measured cost of dropping a policy constraint is a jump from 0% to 38% violations. Decide what is copied verbatim before you decide what is summarised.

**Try this now:** run `python phase02_internals/compactor.py --simulate --turns 12 --inject-overflow 5` and read the backstop lines. Then find the line in `compactor.py` that decides whether to retry, and confirm it changes the input before retrying.

---

## 🧪 Hands-on lab — the exercises that teach Phase 2

Setup: `cd ~/Desktop/project/code/study-material/inference-internals/code && pip install -e .`

Seven of these twelve exercises need no API key and no GPU. They are simulations and arithmetic, and they are marked "offline". The rest need `export OPENAI_API_KEY=sk-...` or another OpenAI-compatible endpoint through `--base-url` and `--key-env`.

**Live-run status, stated honestly:** every script in this phase was executed on the author's machine in offline mode, and the outputs printed in sections 2.1 to 2.6 are real outputs from those runs. The API-calling paths were not executed against OpenAI, because no API key was available on this machine on 2026-09-12. Command flags were checked against the shipped scripts. Exercises E7 to E10 are therefore marked UNVERIFIED against a live provider. Run them and record what you see.

Record every number. Phase 3 reuses your cache hit rate, and Phase 5 reuses your gap measurements.

- [ ] **E1 (offline).** Measure what paging buys.
  - Run: `python phase02_internals/paging_lab.py`
  - Expected: contiguous admits 14 concurrent requests, paged admits 253, and the tool prints the multiplier. Internal waste is 8 tokens per request.
  - If the numbers differ: you changed `--avg-tokens` or `--block-size`. Both move the result, which is the point.
  - Teaches: concurrency is a memory allocation question, not a model question.

- [ ] **E2 (offline).** Find the model that does not fit.
  - Run: `python phase02_internals/paging_lab.py --model llama-3-70b --gpu-gb 80`
  - Expected: a clear failure saying 140 GB of weights do not fit in 80 GB at 0.90 utilisation.
  - Then run: `python phase02_internals/paging_lab.py --model llama-3-70b --gpu-gb 320 --avg-tokens 6000`
  - Expected: it fits, and the concurrency number is far below the 8B model's.
  - Teaches: weights come out of the same memory as the KV cache, so a bigger model cuts concurrency twice.

- [ ] **E3 (offline).** Static against continuous batching.
  - Run: `python phase02_internals/batching_sim.py`
  - Expected: mean TTFT about 5,357ms for static and about 867ms for continuous, with higher throughput for continuous and slightly higher mean TPOT.
  - Teaches: iteration-level scheduling trades a little per-token speed for a large latency and throughput win.

- [ ] **E4 (offline).** Find the token budget trade.
  - Run: `python phase02_internals/batching_sim.py --token-budget 512` then `--token-budget 8192`.
  - Expected: mean TTFT and worst gap move in opposite directions. Write both numbers down.
  - Then read the honest limit: the simulator does not model chunking overhead. Sarathi-Serve measured about 25% overhead at a 512-token budget on Yi-34B. Treat a very small budget as a real throughput cost, not a free win.
  - Teaches: `max_num_batched_tokens` is a product decision, because chat and batch jobs want opposite settings.

- [ ] **E5 (offline).** Price two prompt layouts holding the same information.
  - Run: `python phase02_internals/prefix_cache_sim.py`
  - Expected: volatile-first hits 0.0%, stable-first hits about 92.0%, and stable-first costs about 3.22x less.
  - Teaches: prompt order is a pricing decision.

- [ ] **E6 (break-it, offline).** Make a correct layout go cold.
  - Run: `python phase02_internals/prefix_cache_sim.py --capacity-blocks 500 --users 5 --steps 12`
  - Expected: the stable-first hit rate falls from about 92% to about 69%, and the tool reports thousands of evictions.
  - Then run `--capacity-blocks 200` and watch it fall further.
  - Teaches: your hit rate depends on other tenants. Never model cost as if a hit is guaranteed.

- [ ] **E7 (UNVERIFIED against a live provider).** Watch your own concurrency.
  - Run, from the `code` directory:
    ```
    for i in 1 2 3 4 5 6 7 8; do
      python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 1 &
    done; wait
    ```
  - Expected: TTFT spread across the eight runs is wider than the spread you measured in Phase 1 E4 with `--runs 8` sequentially. You may also see a 429 rate-limit error, which is itself the lesson.
  - If every run is identical: your account's rate limit is high and eight requests are nothing to the provider. Raise the loop to 32.
  - Costs at most: about $0.05.
  - Teaches: on a shared endpoint you observe queueing, you do not control it.

- [ ] **E8 (UNVERIFIED against a live provider).** Measure the constraint tax on a real task.
  - Run offline first: `python phase02_internals/structured_lab.py --self-test` and confirm all six parser cases pass.
  - Then run: `python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap`
  - Expected: `prompt` mode records at least one parse failure across 12 tickets. `json` and `strict` record zero. The accuracy column shows your tax, which may be positive or negative.
  - Costs at most: about $0.02 for all three modes.
  - Teaches: the shape guarantee and the quality question are two different things.

- [ ] **E9 (UNVERIFIED against a live provider).** Test the mitigation.
  - Run: `python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --reasoning-field`
  - Expected: output tokens rise, cost rises, latency rises. Accuracy may or may not rise. Compare against E8 and decide whether the trade is worth it on this task.
  - Teaches: a free-text field before the constrained fields is a measurable change, not a belief.

- [ ] **E10 (break-it, UNVERIFIED against a live provider).** Truncate a schema-perfect answer.
  - Run: `python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --modes strict --reasoning-field --max-tokens 15`
  - Expected: the `truncated` column fills up, and parse failures appear even though every answer obeyed the schema while it lasted.
  - Teaches: a strict schema guarantees legality, never completion. `finish_reason` remains mandatory, exactly as Phase 1 E11 said.

- [ ] **E11 (offline).** Watch the compaction trigger fire.
  - Run: `python phase02_internals/compactor.py --simulate --turns 40`
  - Expected: the prompt grows to 19,409 tokens, the trigger fires at turn 25, and the prompt drops to 2,270 tokens. 45 turns are summarised and 4 are kept verbatim.
  - Then run `--trigger-ratio 0.3` and `--keep-last 10` and note how the sawtooth changes.
  - Teaches: the trigger is a number you choose, and the choice is visible in the token graph.

- [ ] **E12 (break-it, offline).** Reproduce Phase 1 E7, then catch it.
  - Run: `python phase02_internals/compactor.py --simulate --turns 60 --no-compaction`
  - Expected: the run stops at turn 42 with "prompt exceeds the window. This is the E7 failure."
  - Then run: `python phase02_internals/compactor.py --simulate --turns 12 --inject-overflow 5`
  - Expected: call 5 fails with a context-length error, the backstop compacts, one retry succeeds, and the run continues. The summary line reports `backstops: 1` and tells you to lower the trigger ratio.
  - Teaches: the trigger is the fix, the backstop is the seatbelt, and a backstop firing is a bug report.

---

## 🔍 Check it yourself — questions against the course code

You have no anchor repository configured for this course, so these questions target the exercise code you now own. The last one works against any repository you happen to have.

1. Open `code/phase02_internals/prefix_cache_sim.py` and find `PrefixCache.lookup_and_fill`. Locate the line that sets `still_hitting = False`. Explain in one sentence why the method never re-enters the hitting state after that line runs, and name the real-world rule this reproduces.
2. Open `code/phase02_internals/compactor.py` and find `ContextManager.render`. The zones are concatenated in a fixed order. Explain why moving `self.carry.render()` above the tools block would raise your bill, using section 2.3. Then find the one field in `CarryOver` that ConstraintRot says you must copy verbatim rather than summarise.
3. Open `code/phase02_internals/batching_sim.py` and find the three cost constants above the `Req` class: `BASE_DECODE_MS`, `PER_SEQ_DECODE_MS`, and `MS_PER_PREFILL_TOKEN`. They are the only physics in the file, and `iteration_cost_ms` is the one function that uses them. `PER_SEQ_DECODE_MS` is 0.12 while `BASE_DECODE_MS` is 18.0. Explain what physical fact that 150x gap represents, and predict what happens to the static-versus-continuous gap if you set `PER_SEQ_DECODE_MS` to 5.0. Then run it and check.
4. In any agent repository you own: find where the model messages are assembled. Write down the byte offset region where anything time-dependent, request-dependent, or user-dependent first appears. Everything after that point is a cache miss on every call. If you find nothing volatile in the first 1,000 tokens, say so. That is a pass, and it is worth confirming rather than assuming.

---

## ✅ Checkpoint 2 — answer in your own words

1. Your streaming support answers look fine in the dashboard: median TTFT 600ms, median total 4.2s. Users report the text "stops for a second" in the middle. Nothing in your metrics shows it. (a) Name the server behaviour in section 2.4 that produces this. (b) Name the one metric you must add. (c) Your provider will not change its token budget for you. Name two things you can still change.

2. Show the math. You run llama-3-8b on one 80GB GPU at `gpu_memory_utilization=0.90`. Weights take 16GB, and KV costs 128 KB per token. Your traffic averages 1,800 tokens held per request. (a) How many concurrent requests fit under paged allocation with a 16-token block? (b) Your platform team proposes lowering utilisation to 0.70 for safety. How many requests fit then? (c) State the percentage of capacity that decision costs.

3. A colleague says: "We moved the timestamp out of the system prompt, so our cache hit rate is fixed and we can bill our customers using the cached price." Give the two separate reasons this is wrong, using section 2.3. One reason is about the block rule and one is about eviction.

4. This is broken. Your classification service returns valid JSON matching the schema on every call, `finish_reason` is `stop`, but accuracy dropped 9 points after you enabled strict mode last week. (a) Give the most likely cause from section 2.5. (b) Describe the exact schema change you would test, including where in the property order it goes. (c) Name the measurement that would settle it, and say why re-running once is not enough.

5. Design it. You are building an agent that runs 200 tool-calling steps over several hours, with a policy rule that says it must never issue a refund above 200 EUR. Design the context strategy. Cover: the trigger, what is copied verbatim, what is summarised, what is dropped, and where the summarising call's tokens appear in your cost accounting. Use the ConstraintRot numbers to justify one of your choices.

6. A colleague says: "Compaction fixed our long-running agent. We compact at 60% and tasks now finish." Give the counter-argument from the 2026 research in section 2.6, naming the specific finding about step count versus context length, and say what you would measure to tell the two explanations apart.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) A long prefill from another request ran in one iteration without chunking, so every decoding request produced no token during that pass. (b) Maximum inter-token gap per response, recorded at stream time. Median TTFT and total latency cannot see a freeze. (c) Shorten your own prompts so your prefills are small, and move long-context work to a separate endpoint or a batch path so it does not share a batch with interactive traffic. A fallback provider for interactive traffic is a third option.

2. (a) Usable memory is 80 x 0.90 = 72GB. KV pool is 72 - 16 = 56GB. A 1,800-token request holds ceil(1800/16) = 113 blocks = 1,808 token slots, which is 1,808 x 128KB = 0.2207GB. 56 / 0.2207 = about 253 requests. (b) At 0.70: 80 x 0.70 = 56GB usable, minus 16GB of weights = 40GB pool. 40 / 0.2207 = about 181 requests. (c) (253 - 181) / 253 = about 28% of capacity lost. Check both with `paging_lab.py --gpu-util 0.70`.

3. First, the cache matches whole blocks from token 0. A prefix of 1,210 tokens with 16-token blocks shares only 1,200 of them, so part of the prefix is never shared. More importantly, any remaining volatile content later in the prompt still cuts everything after it. Second, cache entries are evicted under memory pressure from other tenants and expire after a few minutes of inactivity. Your hit rate is a measured rate, not a guarantee, so billing that assumes a hit will under-collect.

4. (a) The schema forces the first token, so the model commits to a label with no room to reason in text first. (b) Add a `reasoning` string field and place it first in the properties, before the constrained fields. Add it to `required` and keep `additionalProperties: false`. Placing it last changes nothing, because decoding is left to right. (c) Run the same labeled set through both schemas with `structured_lab.py`. One run is not enough because sampling varies between runs, so a 9-point gap can appear by chance on 12 items. Repeat with `--repeat` and compare across runs before believing the number.

5. Trigger at a fixed token threshold well below the window, for example 50% to 60%, checked before every call. Copy verbatim: the refund limit rule, any other policy constraint, and the last few turns. Summarise: earlier conversation into decisions, constraints, and open items. Drop: full tool payloads, replaced by pointers such as an order id you can re-fetch. Justification: ConstraintRot measured 0% violations when the constraint survived compaction and 38% when it was dropped, so the refund rule must never depend on a summariser's judgement. Accounting: the summarising call is a second billed call, so add it to the same run record. Anthropic's own compaction feature excludes it from top-level usage, which is a reminder that a naive meter will undercount.

6. The 2026 study of 10,664 trajectories found that task success decays with the number of steps rather than the context length, and that restricting the context window made the decay steeper, with a logit slope of -0.69 against -0.44. So a compaction win may come from lower cost or from luck, not from fixing degradation. To tell the explanations apart, hold the step count fixed and vary the context length, then hold the context length fixed and vary the step count. Measure task success in each. If success tracks steps in both, compaction was not the cause.

</details>

---

## References & Further Learning

Every link below was fetched and checked on 2026-09-12. Where a source blocked automated fetching, the entry says so. Read the "must" list before the lab. Read the rest after.

### Must-read before the lab

1. **Orca: A Distributed Serving System for Transformer-Based Generative Models** — Yu, Jeong, Kim, Kim, Chun. OSDI 2022.
   https://www.usenix.org/conference/osdi22/presentation/yu
   Why this one: it invented iteration-level scheduling. Every blog post about continuous batching retells this paper. Focus on section 3, which names the two problems directly: requests that finish early and requests that arrive late. Then read section 4.2 and Algorithm 1, which is the scheduler loop in section 2.1 of this phase.
   The headline number, quoted: to hold a median normalised latency of 190ms on a 175B model, FasterTransformer served 0.185 requests per second and Orca served 6.81, a 36.9x speedup. Conditions: GPT-3 175B in fp16 on 16 A100 40GB GPUs, input lengths drawn uniformly from 32 to 512 tokens and generation lengths from 1 to 128. Note the honest case in Figure 10a, where Orca does not win on a 101B model at low load. The gain comes from scheduling, so it needs load to appear.
   Access note: usenix.org blocks automated fetching and returns 403. The link works in a browser.

2. **How continuous batching enables 23x throughput in LLM inference while reducing p50 latency** — Anyscale, 22 June 2023.
   https://www.anyscale.com/blog/continuous-batching-llm-inference
   Why this one: it separates three things that most posts merge, measuring naive batching, continuous batching, and continuous batching plus paged memory as distinct steps. Conditions: OPT-13B on one A100 40GB, 1,000 requests, 512 input tokens each, generation lengths from an exponential distribution. Numbers: up to 23x with continuous batching plus paged memory, up to 8x with continuous batching alone, up to 4x with FasterTransformer. Read the condition carefully. The 23x figure is against naive static batching, not against a tuned server, so always quote it with its baseline.

3. **Efficient Memory Management for Large Language Model Serving with PagedAttention** — Kwon, Li, Zhuang, Sheng, Zheng, Yu, Gonzalez, Zhang, Stoica. SOSP 2023.
   https://arxiv.org/abs/2309.06180 and the readable version at https://ar5iv.labs.arxiv.org/html/2309.06180
   Why this one: it is the source of section 2.2, and it contains the measurement that justifies the whole design. Focus on section 3 with Figure 2 for the waste breakdown, section 4 for the block table, section 4.4 for sharing and copy-on-write, and section 7.2 for block size.
   Numbers: only 20.4% to 38.2% of KV cache memory held real token state in the systems it measured. The default block size is 16 tokens, and the sweep in section 7.2 found 16 to 128 performed best. Throughput is 1.7x to 2.7x over Orca with an oracle output length, and 2x to 4x over FasterTransformer and Orca at similar latency.

4. **Fast LLM Serving with vLLM and PagedAttention** — Woosuk Kwon and Zhuohan Li, the vLLM creators. 24 minutes.
   https://www.youtube.com/watch?v=5ZlavKF_98U
   Why this one: the authors animate the block table, which the paper cannot do. Watch 6:11 to 14:41 as the single best explanation of paging and copy-on-write. Timestamps, taken from the caption track because the video has no chapters: 3:07 what the KV cache is, 3:52 the memory budget for a 13B model on a 40GB GPU, 4:40 internal fragmentation, 5:26 reservation and external fragmentation with the 20 to 40 percent utilisation figure, 6:11 the virtual memory comparison, 8:30 logical blocks, physical blocks and the block table, 10:03 why block size bounds the waste, 10:50 the claim that vLLM wastes about 4%, 13:54 copy-on-write worked through, 20:04 the Chatbot Arena deployment at about 40,000 conversations per day with half the GPUs.
   Watch it before reading the paper.

5. **vLLM automatic prefix caching design** — official design document.
   https://docs.vllm.ai/en/latest/design/prefix_caching.html
   Why this one: it describes the exact data structure `prefix_cache_sim.py` reproduces. Focus on the hash construction. Each block's hash includes the parent block's hash plus that block's tokens plus extras such as LoRA id. That parent chain is why a prefix match cannot restart in the middle. Eviction is least-recently-used, and freed blocks enter the free queue in reverse order so later, less reusable blocks go first. The page names `--prefix-caching-hash-algo`, with `sha256` as the default. Read it right after exercise E5.

6. **vLLM optimization and tuning guide** — official documentation.
   https://docs.vllm.ai/en/latest/configuration/optimization.html
   Why this one: it states the section 2.4 trade in the project's own words. Smaller values such as 2048 for `max_num_batched_tokens` "achieve better ITL because there are fewer prefills slowing down decodes", and higher values "achieve better time to first token". Chunked prefill "is enabled by default whenever possible" in V1.
   Defaults confirmed against the v0.29.0 source tree on 2026-09-12, because the `latest` docs carry no version number: `enable_prefix_caching` is `True`, `enable_chunked_prefill` is `True`, `block_size` resolves to 16, `gpu_memory_utilization` is 0.92, the scheduling policy is `fcfs`, and `max_num_batched_tokens` is chosen at startup from the GPU class rather than fixed.

### Deep dives

7. **Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve** — Agrawal, Kedia, Panwar, Mohan, Kwatra, Gulavani, Tumanov, Ramjee. OSDI 2024.
   https://arxiv.org/abs/2403.02310 and https://ar5iv.labs.arxiv.org/html/2403.02310
   The source of section 2.4. Focus on section 3 for why a long prefill spikes inter-token latency, section 4 for chunked prefills and the token budget, and section 5.4.1 with Figure 14 for the overhead, which is the part that stops people setting the budget too low.
   Numbers: hybrid batching without chunking raised time between tokens by 28.3x against a decode-only batch. Serving capacity rose 2.6x for Mistral-7B on one A100, up to 3.7x for Yi-34B on two A100s, and 6.3x for LLaMA2-70B on eight A40s against Orca. Chunking overhead was about 25% at a 512-token budget on Yi-34B. Token budgets used in the paper: 512 for a strict latency target, 2048 for a relaxed one.
   Section numbers come from the arXiv rendering, so they may shift by one against the camera-ready.

8. **SGLang: Efficient Execution of Structured Language Model Programs** — Zheng, Yin, Xie, Sun, Huang, Yu, Cao, Kozyrakis, Stoica, Gonzalez, Barrett, Sheng. NeurIPS 2024.
   https://arxiv.org/abs/2312.07104 and https://arxiv.org/html/2312.07104v2
   The source of RadixAttention. Focus on section 3, which gives the radix tree over token sequences, the rule that eviction removes the least recently used leaf first, and the cache-aware scheduling heuristic. Read it after the PagedAttention paper, because the tree is easier once block hashing is familiar.
   Numbers: production cache hit rates from Chatbot Arena were 52.4% for LLaVA-Next-34B and 74.1% for Vicuna-33B. Benchmark hit rates ranged 50% to 99%, and cache-aware scheduling reached about 96% of the best achievable hit rate. Throughput up to 6.4x higher and latency up to 3.7x lower.

9. **Inside vLLM: Anatomy of a High-Throughput LLM Inference System** — Aleksa Gordic, 5 September 2025.
   https://vllm.ai/blog/2025-09-05-anatomy-of-vllm
   The bridge between the papers and the current source. It walks the engine loop, the scheduler, the paged KV cache with its free block queue, and prefix caching with worked hash examples. Read it between the papers and the code exercises.

10. **2x faster inference with KV cache-aware routing** — Baseten, 16 March 2026.
    https://www.baseten.co/blog/how-baseten-achieved-2x-faster-inference-with-nvidia-dynamo/
    The production story for section 2.3, and the answer to a question the phase raises. A prefix cache is useless if your load balancer sends the request to a replica that does not hold the prefix. Baseten routes with a radix tree over cached prefixes.
    Numbers, with conditions. Synthetic test on Qwen3 Coder 480B A35B with about 50,000-token inputs and four replicas: 89% cache hit rate, 50% lower TTFT, 34% lower TPOT. Shadowed production traffic: 48% lower P95 latency, 49% lower P99, 61% more requests per second. Read it after exercise E6.

11. **Predicted-Latency Based Scheduling for LLMs** — llm-d project, 13 March 2026.
    https://llm-d.ai/blog/predicted-latency-based-scheduling-for-llms
    Read it beside the Baseten post, because it argues the opposite pressure. It reports KV cache utilisation spiking from 30% to over 70%, erratic queue depths across pods, and prefix cache hit rates that "collapse frequently as traffic patterns shift and cached prefixes get evicted". Its central point supports exercise E6: routing for cache reuse concentrates load, and routing for low utilisation spreads it.

12. **LLM Inference Performance Engineering: Best Practices** — Databricks and the MosaicML team, 12 October 2023.
    https://www.databricks.com/blog/llm-inference-performance-engineering-best-practices
    The arithmetic behind why a bigger batch raises throughput without raising per-token speed. Numbers to check your own intuition against: MPT-7B on one A100 40GB shows 46ms TTFT at 512 input tokens and batch size 1, while Llama2-70B on four A100s shows 114ms. Throughput moves from 0.4 to 1.7 requests per second at batch size 1 up to 36.5 at batch size 128. Model bandwidth utilisation at batch size 1 is about 55% to 60%, which is the memory-bound decode fact from Phase 1, measured.

13. **Optimizing AI Inference at Character.AI** — 20 June 2024.
    https://blog.character.ai/optimizing-ai-inference-at-character-ai/
    Read it for scale rather than for technique. About 20,000 queries per second, under one cent per hour of conversation, and serving costs cut at least 33x since launch. Honest note: the deeper technical post it used to link, covering multi-query attention and cross-layer KV sharing, now redirects to the blog index and is gone. Do not cite its numbers from a live link.

### Constrained decoding

14. **Efficient Guided Generation for Large Language Models** — Willard and Louf, the Outlines paper.
   https://arxiv.org/abs/2307.09702
   The mechanism in section 2.5. Focus on section 2.2 for the mask formula and section 3 for the index that maps each state machine state to its set of legal tokens. That index is what makes the per-step mask cost about constant instead of proportional to the vocabulary. Honest note: section 3.2's timing comparison is a single plot from one timing run, and the authors hedge it themselves. Do not quote a speedup from it.

15. **XGrammar blog and paper** — MLC.
    https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar and https://arxiv.org/abs/2411.15100
    The best explanation of why masking can be nearly free. Focus on the split between context-independent tokens, which are precomputed, and context-dependent ones. The blog states that more than 99% of tokens are usually context-independent, and reports up to 3.5x faster mask generation on JSON schema and up to 10x on context-free grammars.

16. **XGrammar-2** — https://blog.mlc.ai/2026/05/04/xgrammar-2-fast-customizable-structured-generation and https://arxiv.org/abs/2601.04426
    Read this for Structural Tag, which is the current answer to the constraint tax: the model writes free text, a trigger token switches the constrained region on, and the schema applies only there. vLLM exposes it as `structural_tag`. The blog reports compilation on complex JSON schemas dropping from 534ms to 5.37ms. Note that no accuracy measurement is published for Structural Tag yet, so treat it as an engineering fix, not proven quality.

17. **JSONSchemaBench** — https://arxiv.org/abs/2501.10868
    The compile-time numbers used in section 2.5, in Table 3, and the accuracy table in Table 8. Its setup puts the reasoning field before the answer field, which is exactly the ordering rule section 2.5 gives, and its results show constrained decoding matching or beating unconstrained under that ordering.

18. **Let Me Speak Freely?** — Tam et al., EMNLP 2024 Industry Track.
    https://arxiv.org/abs/2408.02442
    Read it for Table 1, Table 7 and Table 8. Read Table 8 especially, because it shows constraints helping classification even though the abstract does not say so. Read section 2 to see the paper's own words that the implementation "is assumed" to be constrained decoding, which is the weakness the rebuttals attack.

19. **Say What You Mean: A Response to "Let Me Speak Freely"** — .txt, the Outlines authors.
    https://blog.dottxt.ai/say-what-you-mean.html
    The rebuttal, with a re-run on the same model. Focus on the parser sensitivity numbers: the same task scores 0.35 with a strict regular expression parser and 0.61 with a flexible one. That single result is the most practical lesson in the whole dispute.

20. **The Format Tax** — Lee, D'Antoni, Berg-Kirkpatrick, April 2026.
    https://arxiv.org/abs/2604.03616
    The paper that settles the argument by splitting the cause. Focus on section 4.2 for the attribution result and section 4.3 with Table 5 for the two mitigations. Honest note: this is a preprint with no peer-review venue found, so weigh it accordingly.

21. **OpenAI Structured Outputs guide** — official documentation.
    https://developers.openai.com/api/docs/guides/structured-outputs
    Bookmark it, because the supported-keyword list changes. Check the "Supported schemas" section before you design a schema. Note that the old platform.openai.com URL now redirects here.

### Context management

22. **Effective context engineering for AI agents** — Anthropic, 29 September 2025.
    https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
    Focus on the compaction section and the structured note-taking section. It names what to preserve: architectural decisions, unresolved bugs, implementation details. Honest note: it gives no numeric threshold, so do not repeat one attributed to it.

23. **Context editing and compaction reference** — Anthropic platform documentation.
    https://platform.claude.com/docs/en/build-with-claude/context-editing and https://platform.claude.com/docs/en/build-with-claude/compaction
    These are where the real numbers live. Context editing defaults to a 100,000 input-token trigger and keeps 3 tool uses. Compaction defaults to a 150,000 input-token trigger and rejects values under 50,000. Two details worth copying into your own design: clearing tool results invalidates cached prompt prefixes, and compaction runs as a separate billed iteration whose tokens are excluded from the top-level usage counts.

24. **Context Rot: How Increasing Input Tokens Impacts LLM Performance** — Chroma Research, 14 July 2025.
    https://www.trychroma.com/research/context-rot
    Focus on the LongMemEval section, which compares a focused input of about 300 tokens against a full input of about 113,000 tokens. 18 models across Claude, GPT, Gemini and Qwen families. Honest note: the accuracy curves are published as charts and the page gives no accuracy percentage at a specific token count. The widely repeated "30% drop" figure does not appear on the page. Do not quote it.

25. **Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents** — June 2026.
    https://arxiv.org/abs/2606.22528
    The strongest number in section 2.6 and the reason the `constraints` list exists in `compactor.py`. 1,323 episodes across seven model families. Violations 0% with the policy visible, 30% on average after compaction, 59% for the worst model, 0% when the constraint survived the summary and 38% when it did not. Copying the constraint verbatim returned violations to 0%.

26. **Slipstream: Trajectory-Grounded Compaction Validation for Long-Horizon Agents** — May 2026.
    https://arxiv.org/abs/2605.08580
    Read it for the validation gap argument: the compactor must shorten the context without knowing what the agent will need later. Reports up to 8.8 percentage points of accuracy and up to 39.7% lower end-to-end latency by validating summaries off the critical path.

27. **Self-Compacting Language Model Agents** — June 2026.
    https://arxiv.org/abs/2606.23525
    The counter-argument to token thresholds. Focus on the rubric that fires compaction when a sub-task resolves and suppresses it mid-derivation. Reports up to 18.1 points on math and 5 to 9 points on agentic search at 30 to 70 percent lower cost per question.

28. **How Fast Do Agents Rot?** — August 2026.
    https://arxiv.org/abs/2609.01660
    Read it last. 10,664 trajectories, nine models, from 1.2B parameters to deployed proprietary systems. Its finding reframes the phase: degradation tracks step count rather than context length, and restricting the context made decay steeper, with a logit slope of -0.69 against -0.44.

29. **Lost in the Middle: How Language Models Use Long Contexts** — Liu et al., TACL 2024.
    https://arxiv.org/abs/2307.03172
    Figure 5 is the position-versus-accuracy curve quoted in section 2.6. Treat the models as historical and the shape as current.

30. **Context Engineering for AI Agents: Lessons from Building Manus** — 18 July 2025.
    https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
    The practitioner view of section 2.3. It names the timestamp-in-the-system-prompt mistake directly, and gives the append-only rule for history. Its quoted 10x gap between cached and uncached input was Claude Sonnet list pricing in July 2025, so re-check the current numbers before you reuse them.

---

## Cheatsheet

```
THE SCHEDULER LOOP
  one iteration = one forward pass = ONE token for every decoding request
  static batching     : batch runs to completion; freed slots stay idle
  continuous batching : a freed slot is refilled next iteration
  your levers on a hosted API: prompt length, output length, arrival
  pattern, prefix reuse

PAGED KV CACHE
  contiguous : reserve max_model_len per request  → 14 concurrent (example)
  paged      : ceil(tokens / block) blocks on demand → 253 concurrent
  waste under paging = unused tail of the last block only
  out of blocks = PREEMPTION, not an error: prefill is redone later
  gpu_memory_utilization is a capacity setting, not a safety setting

PREFIX CACHE
  key = hash(this block's tokens + parent block's hash)  → prefix-only match
  match starts at token 0, moves forward, stops at the first difference
  whole blocks only; a partial tail block is never shared
  eviction is LRU, and other tenants share the pool
  RULE: stable content first, volatile content last
  measured: same tokens, 0.0% vs 92.0% hit rate, 3.22x cost difference

CHUNKED PREFILL
  no chunking : one big prefill freezes every stream in the batch
  chunking    : prefill shares max_num_batched_tokens with the decodes
  smaller budget → better inter-token smoothness, worse TTFT
  larger budget  → better TTFT, worse smoothness
  measure MAX INTER-TOKEN GAP; TTFT and total latency cannot see a freeze

CONSTRAINED DECODING
  mask illegal tokens each step → shape guaranteed, stopping NOT guaranteed
  prompt only → no guarantee | json_object → valid JSON | json_schema+strict
  → schema obeyed
  finish_reason still mandatory: a truncated schema-shaped answer is a
  parse failure
  schema rules: every key in required, additionalProperties false,
  optional = union with null
  THE TAX: format-requesting prompt ≈ -3.9 pts, the decoder itself ≈ -1.6 pts
  reasoning field goes FIRST or it does nothing
  mitigations: two calls (+6.8 avg, worsens 3%), thinking (+9.2 avg, worsens 15%)
  always state the model and the parser with any number you report

CONTEXT BUDGET AND COMPACTION
  zones with caps + headroom for the reply AND for the summarising call
  TRIGGER on a token threshold you chose, before the call
    shipped references: context editing 100k, compaction API 150k (min 50k)
  COPY VERBATIM: constraints. 0% violations when kept, 38% when dropped
  SUMMARISE: decisions, open items.  DROP: tool payloads, keep pointers
  BACKSTOP: HTTP 400 + code context_length_exceeded → compact → retry ONCE
    never match on the message text; never retry the same prompt unchanged
  compaction is billed: your summarising call is a second call

THE COMMANDS
  paging_lab.py                       → concurrency and waste, offline
  batching_sim.py                     → policy comparison, offline
  prefix_cache_sim.py                 → layout cost and eviction, offline
  structured_lab.py --self-test       → parser and scorer, offline
  structured_lab.py --model ...        → the constraint tax, live
  compactor.py --simulate --turns 40  → the trigger firing, offline
  compactor.py --simulate --no-compaction → the E7 failure, offline
```
