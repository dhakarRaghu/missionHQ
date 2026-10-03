# Phase 2A — Scheduling and memory (how the server shares one GPU between strangers)

Phase 1 looked at one request on its own. You measured its TTFT, its TPOT, and its bill. TTFT is the time to first token. TPOT is the time per output token after the first. That model is correct, but it is not complete. A real inference server never runs one request. It runs a loop over a batch, and your request shares a GPU with requests from other people.

This phase opens that loop. After it, you can answer questions that Phase 1 could not:

- Why did my TTFT nearly double at 3pm when my prompt did not change?
- Why does the same prompt cost 4x less on the second call? How do I make that happen every time?
- Why did the stream freeze for 800ms in the middle of a sentence?
- Why did my strict JSON schema make the answers worse?
- My agent failed with a 400 after 40 turns. What is the correct fix? Why is a retry not the fix?

Phase 2 is split into two documents. It covers six topics, and one document would be too long to study in one sitting. This is part A. It answers the first two questions. Part B answers the last three.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, this document                                                    │
│  2.1  The scheduler loop        — continuous batching, and why your      │
│                                   latency depends on other requests      │
│  2.2  The paged KV cache        — why the server fits 18x more requests  │
│  2.3  Prefix caching inside     — the radix tree, block granularity,     │
│       the server                  eviction, and what your layout costs   │
│                                                                          │
│ PART B, the next document                                                │
│  2.4  Chunked prefill           — the trade between TTFT and TPOT        │
│  2.5  Constrained decoding      — token masking, and the constraint tax  │
│  2.6  Context budget and        — the trigger that prevents Phase 1 E7,  │
│       compaction                  and the backstop that catches it       │
└──────────────────────────────────────────────────────────────────────────┘
```

This part also explains a result you already have. Phase 1 exercise E6 showed that one changed character early in the prompt ends the cache hit. Section 2.3 shows the mechanism behind that result.

Time: 1.5 to 2 hours. All three scripts in this part run with no API key and no GPU. Only exercise E7 calls a live API.

Setup once:

```bash
cd ~/Desktop/project/code/study-material/inference-internals/code
pip install -e .       # or: uv sync
```

The scripts for this part are `batching_sim.py`, `paging_lab.py`, and `prefix_cache_sim.py`. They need no key. Exercise E7 needs `export OPENAI_API_KEY=sk-...`. You can also use any OpenAI-compatible endpoint through `--base-url` and `--key-env`.

---

## 2.1 — The scheduler loop (your latency depends on other requests)

Why this matters: you cannot explain a latency spike until you know what the server does between your requests. The server runs a loop, and your request is one row inside it.

vLLM, SGLang, TensorRT-LLM, and hosted providers all run this loop. The names differ between them. The steps are the same. Three terms first:

- **Prefill** is the pass that reads your whole prompt. It produces the first token.
- **Decode** is each later pass. Each decode pass produces one more token.
- **A forward pass** is one run of the model over a set of tokens.

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

Step 4 surprises most people. One iteration produces one token per request. The batch size does not change this. So a batch of 40 requests produces 40 tokens in about the time that one request produces 1 token.

The reason is what a decode step does. It reads all the model weights from GPU memory once. Then it does a small amount of arithmetic for each sequence in the batch. The memory read takes most of the time. One more sequence adds only a little arithmetic.

The simulator in this part uses that fact as its cost model. From `batching_sim.py:49` and `batching_sim.py:73`, comments shortened, logic unchanged:

```python
BASE_DECODE_MS = 18.0        # one decode iteration with a batch of 1
PER_SEQ_DECODE_MS = 0.12     # extra cost per additional sequence in the batch
# Prefill is compute-bound: about 33,000 tokens per second in this model.
MS_PER_PREFILL_TOKEN = 0.03

def iteration_cost_ms(prefill_tokens: int, decode_seqs: int) -> float:
    """Time for one forward pass over this mixed batch."""
    cost = prefill_tokens * MS_PER_PREFILL_TOKEN
    if decode_seqs:
        cost += BASE_DECODE_MS + PER_SEQ_DECODE_MS * decode_seqs
    return cost
```

With these constants, a batch of 16 decoding requests costs 18.0 + 0.12 × 16 = 19.92ms per iteration. A batch of 1 costs 18.12ms. Sixteen times the tokens cost 10% more time. The file says it is a teaching model. The shape of its results matches real servers. Its absolute numbers do not match any specific GPU.

**Static batching was the old way.** The server collected N requests and ran them together. It admitted no new request until the last one in the batch finished.

```
STATIC BATCHING — the slowest request holds the whole batch (example timings)

  slot 1  ████████████░░░░░░░░░░░░░░░░░░░   done at t=1.2s, then idle
  slot 2  ████████████████████████░░░░░░░   done at t=2.4s, then idle
  slot 3  ██████████████████████████████░   done at t=3.1s
  slot 4  ██████░░░░░░░░░░░░░░░░░░░░░░░░░   done at t=0.6s, then idle
          └──────────── new requests wait here ─────────────┘
          t=0                                            t=3.1s
  ░ = a slot that holds GPU memory and produces nothing
```

**Continuous batching is the current way.** The scheduler admits new work on every iteration. A finished request leaves at once. A waiting request takes its slot on the next step.

```
CONTINUOUS BATCHING — a freed slot is refilled on the next iteration (example)

  slot 1  ████████████▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓   req A done → req E starts
  slot 2  ████████████████████████▓▓▓▓▓▓▓   req B done → req F starts
  slot 3  ██████████████████████████████▓   req C running
  slot 4  ██████▓▓▓▓▓▓▓▓████████████████▓   req D done → G → H
          t=0                                            t=3.1s
  no ░ anywhere: no slot sits idle while requests wait
```

This method is called iteration-level scheduling. The Orca paper introduced it in 2022. Serving engines adopted it after that.

**Measure it yourself.** `batching_sim.py` simulates this loop. Run it:

```bash
python phase02_internals/batching_sim.py
```

Output on the author's machine, 40 requests at 6 arrivals per second. The run was repeated on 2026-09-17 with the same result:

```
┌────────────┬───────────┬───────────┬───────────┬────────────┬────────────┐
│ policy     │ mean TTFT │ p99 TTFT  │ mean TPOT │ worst gap  │ throughput │
├────────────┼───────────┼───────────┼───────────┼────────────┼────────────┤
│ static     │    5357ms │    9215ms │    19.4ms │       20ms │   2.3 rq/s │
│ continuous │     867ms │    2649ms │    25.4ms │      764ms │   3.6 rq/s │
│ chunked    │     925ms │    2701ms │    25.5ms │       81ms │   3.5 rq/s │
└────────────┴───────────┴───────────┴───────────┴────────────┴────────────┘
```

p99 TTFT is the value that 99% of requests stay at or below. Throughput is finished requests per second.

Read the first two rows now. The `chunked` row belongs to section 2.4 in part B. The numbers show three effects:

1. Mean TTFT fell from 5,357ms to 867ms. That is 6.2 times better.
2. Throughput rose from 2.3 to 3.6 requests per second. That is 57% more.
3. Mean TPOT rose from 19.4ms to 25.4ms. A fuller batch decodes each token a little slower.

The third effect is not a bug. You traded a slower token for a 6x better TTFT.

Now look at the `worst gap` column. Continuous batching shows 764ms. That is the longest pause between two tokens of one answer. Section 2.4 explains the cause.

```
THE SAME RUN AS BARS, mean TTFT in ms (from the table above)

  static      █████████████████████████████████████████████  5357
  continuous  ███████                                          867
              0                                               5400
```

**What you control.** You do not control the provider's scheduler. You control four inputs to it:

```
┌────────────────────────┬──────────────────────────────────────────────┐
│ Your input             │ What it does to the batch                    │
├────────────────────────┼──────────────────────────────────────────────┤
│ prompt length          │ a long prefill uses the token budget and     │
│                        │ delays every decoding request in the batch   │
│ output length          │ a long generation holds a slot and its KV    │
│                        │ memory for the whole time                    │
│ arrival pattern        │ 50 requests at once wait in a queue;         │
│                        │ 50 spread out do not                         │
│ prefix reuse           │ a cached prefix skips prefill, so it does    │
│                        │ not compete for the token budget             │
└────────────────────────┴──────────────────────────────────────────────┘
```

The arrival pattern is the input you feel most. Run the same workload at 12 arrivals per second instead of 6. Continuous batching mean TTFT rises from 867ms to 1,674ms. Static rises from 5,357ms to 6,551ms. The worst gap stays at 764ms. The prompts did not change. Only the arrival rate changed. This is the answer to "why did my TTFT nearly double at 3pm": 867ms to 1,674ms is 1.9x.

**The sentence to remember:** one scheduler iteration gives every running request one token. Throughput comes from batch size. Latency comes from what else is in the batch.

**The trap:** you will try to fix a TTFT spike with retries. A retry adds one more request to the same queue. Under load, the queue gets longer and the spike gets worse. Phase 0 Story 2 describes this mistake. Phase 5 section 5.3 measures it.

**Try this now:** run `python phase02_internals/batching_sim.py --rate 12`. Compare it with the default run. Expect mean TTFT for continuous batching to move from 867ms to 1,674ms, while the worst gap stays at 764ms.

---

## 2.2 — The paged KV cache (why the server fits 18x more requests)

Why this matters: Phase 1 showed that the KV cache costs bytes per token. That explains memory use. It does not explain how many requests run at once. This section explains that number, which is called concurrency. Concurrency decides how long requests wait in the queue.

The KV cache holds the key and value vectors of every token the model has seen. The model reads them on every decode step, so they must stay in GPU memory.

Start with the simple allocator, because it shows the problem. The server admits a request. It does not know how long the answer will be. So it reserves memory for the worst case. The worst case is `max_model_len`, the longest sequence the server accepts.

```
CONTIGUOUS RESERVATION — one 32,768-token reservation per request

  request A  ┌──────────────────────────────────────────────┐
             │██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│  4.00 GB held
             └──────────────────────────────────────────────┘
              ↑ 1,800 tokens used      ↑ 30,968 tokens wasted

  56 GB KV pool ÷ 4.00 GB = 14 concurrent requests, and 52.9 GB idle
```

PagedAttention fixes this with an idea from operating system virtual memory. The KV cache of one sequence does not need one continuous region. The server does four things:

1. It splits the KV cache into fixed-size blocks.
2. It allocates a block only when the sequence needs it.
3. It keeps a block table for each sequence.
4. The block table maps each logical position to a physical block.

```
PAGED BLOCKS — 16 tokens per block, allocated on demand (block ids are examples)

  request A block table:  [ #91 ][ #14 ][ #55 ][ #7 ] ... 113 blocks
                             │      │      │     │
  physical KV pool  ┌────┬────┬────┬────┬────┬────┬────┬────┬────┐
                    │ #7 │#14 │ .. │#55 │ .. │#91 │ .. │free│free│
                    └────┴────┴────┴────┴────┴────┴────┴────┴────┘
  blocks need not be adjacent, and nothing is reserved for the future
```

The arithmetic is two short functions. From `paging_lab.py:46` and `paging_lab.py:67`, copied as shipped:

```python
def kv_bytes_per_token(layers: int, kv_heads: int, head_dim: int, dtype: str) -> int:
    """2 (K and V) x kv_heads x head_dim values per layer, per token."""
    return 2 * kv_heads * head_dim * BYTES_PER_VALUE[dtype] * layers


def blocks_for(tokens: int, block_size: int) -> int:
    """Ceiling division. A request holding 1 token still holds a whole block."""
    return -(-tokens // block_size)
```

For llama-3-8b in fp16: 2 × 8 KV heads × 128 × 2 bytes × 32 layers = 131,072 bytes. That is 128 KB per token.

Run the full comparison:

```bash
python phase02_internals/paging_lab.py
```

Output for llama-3-8b on one 80GB GPU. The run was repeated on 2026-09-17 with the same result:

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

Paging admits 18.1x more concurrent requests on the same hardware. The model did not change. The GPU did not change. That result is why PagedAttention became the default in serving engines.

The PagedAttention paper measured the same problem in real systems. In those systems, only 20.4% to 38.2% of KV cache memory held real token state. Reserved slots and fragmentation used the rest. The vLLM authors state in their talk that paging cut that waste to about 4%.

**Three facts to remember:**

1. **Block size sets the remaining waste.** A request that holds 1,800 tokens needs 113 blocks of 16 tokens. That is 1,808 token slots. The 8 unused slots are internal fragmentation. This is the only waste that paging leaves. With `--block-size 32`, the waste grows to 24 tokens per request and concurrency drops from 253 to 251.
2. **Identical blocks can be shared.** Two requests with the same first 1,200 tokens can point at the same physical blocks. The server stores that prefix once. Section 2.3 covers this.
3. **When blocks run out, the server does not return an error.** The scheduler preempts instead. It frees a running sequence's blocks and puts the request back in the queue. The request resumes later. The server must then redo the prefill it threw away. You see a sudden pause in a request that had already started.

Sharing changes the capacity number a lot. Run `paging_lab.py --shared-prefix 1200`:

```
CONCURRENT REQUESTS on one 80GB GPU, llama-3-8b, 1,800 tokens held per request
  shared prefix = the same first 1,200 tokens in every request

  contiguous             █                                    14
  paged                  ███████████                         253
  paged, shared prefix   ██████████████████████████████████  752
                         0                                   752

  shared blocks stored once: 75      private blocks per request: 38
```

Here is the arithmetic. The 56 GB pool holds 28,672 blocks of 16 tokens at 128 KB per token. Each request needs ceil(600 / 16) = 38 private blocks. So (28,672 - 75) / 38 = 752 requests. That is 2.97x more than paging without sharing.

**Preemption looks like this in time:**

```
PREEMPTION TIMELINE (example times)

  t=0.0s   request R decoding normally, 40 blocks held
  t=1.2s   a burst arrives; the block pool runs out
  t=1.2s   scheduler preempts R: its 40 blocks are freed
  t=1.2s   R goes back to the WAITING queue; tokens already sent stay sent
  t=2.9s   blocks free up; R is admitted again
  t=2.9s   R's prompt is prefilled AGAIN; the first prefill was thrown away
  t=3.1s   R resumes streaming
  ──────────────────────────────────────────────────────────────────────
  what the user saw:  the answer stopped for 1.9 seconds, then continued
  what your logs saw: nothing, unless you record inter-token gaps
```

**The sentence to remember:** paging reserves only the memory a request needs now, not the most it could need. That change makes high concurrency possible.

**The trap:** `gpu_memory_utilization` looks like a safety setting. It works as a capacity setting. vLLM 0.29.0 sets it to 0.92 by default. Lowering it to 0.70 on an 80GB GPU removes 17.6 GB from the KV pool. For llama-3-8b, concurrency then falls from 260 to 181 requests. That is 30% of your capacity. The lab script defaults to 0.90 to keep the arithmetic round. Pass `--gpu-util 0.92` to match vLLM.

**Try this now:** run `python phase02_internals/paging_lab.py --model llama-3-70b --gpu-gb 80` and read the error. Then run it with `--gpu-gb 320` for a four-GPU node. At 1,808 tokens held per request, the 70B node admits 268 requests. The 8B model admits 253 on one GPU. The 70B model needs four times the GPU memory to reach that number.

---

## 2.3 — Prefix caching inside the server (the radix tree and the eviction that ends it)

Why this matters: Phase 1 exercise E6 showed that one changed character early in the prompt ends the cache hit. You measured the effect there. This section shows the mechanism. The mechanism tells you exactly where the cache stops matching.

A prefix is the start of a prompt. Section 2.2 said identical blocks can be shared. The server needs a fast way to find them. It keeps a tree keyed by the token sequence. SGLang calls its version RadixAttention. vLLM calls its version automatic prefix caching. The structure is the same.

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

The matching rule has three parts. Teams lose money on each part:

1. **Matching starts at token 0 and moves forward.** There is no match that starts in the middle. A change at position 10 ends the match for positions 10 to the end.
2. **Matching happens in whole blocks.** Take a 16-token block and a prefix of 1,210 tokens. Only 75 full blocks are shared, which is 1,200 tokens. The last 10 tokens sit in a partial block. The server cannot share them.
3. **Entries leave the cache.** The tree has a fixed size. When it is full, the least recently used blocks leave first. This rule is called LRU. Hosted providers also remove entries after a time limit. The limit is commonly a few minutes without use. Phase 3A section 3.2 gives the provider details.

The simulator implements all three parts in one method. From `prefix_cache_sim.py:67`, docstring shortened, logic unchanged:

```python
def lookup_and_fill(self, tokens: list[str]) -> int:
    """Return how many TOKENS of this prompt were already cached."""
    hit_blocks = 0
    chain: tuple = ()
    n_blocks = len(tokens) // self.block_size  # partial tail block is never cached
    still_hitting = True
    for b in range(n_blocks):
        block = tuple(tokens[b * self.block_size:(b + 1) * self.block_size])
        chain = chain + (hash(block),)
        self.clock += 1
        if still_hitting and chain in self.store:
            self.store[chain] = self.clock
            hit_blocks += 1
        else:
            still_hitting = False
            self.store[chain] = self.clock
            self._evict_if_needed()
    return hit_blocks * self.block_size
```

The key is `chain`, not `block`. Each key includes the hashes of every earlier block. So an identical block after a difference has a different key. vLLM builds its block hash the same way. Its design document says so.

**Measure the layout cost.** `prefix_cache_sim.py` builds this tree for an agent loop. It tests two layouts that hold the same information:

```bash
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

The script prices tokens with `gpt-4.1-mini` at $0.40 per million input tokens. It prices cached tokens at 0.25x. Both layouts send the same tokens and the same information. The price differs by 3.22x. The only change is the order of the parts of the prompt.

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

The wrong version fails without a sign. There is no error and no warning. Your bill is 3x higher and your TTFT is worse. Nothing in your logs says why.

```
WHERE THE MATCH STOPS — same content, two orders

  volatile-first   [time][system prompt ......][tools ......][history ...]
                    ▲
                    differs on every call: 0 blocks match

  stable-first     [system prompt ......][tools ......][history ...][time]
                    ─────────────── matches ──────────────────────►  ▲
                                                           differs here only
```

**What eviction does to a good layout.** A correct layout still loses its hits when the cache fills. First run a bigger workload with no size limit: `--users 5 --steps 12`. Stable-first then hits 93.5%. Now give the cache only 500 blocks:

```bash
python phase02_internals/prefix_cache_sim.py --capacity-blocks 500 --users 5 --steps 12
```

The stable-first hit rate falls from 93.5% to 68.8%. The simulator reports 5,615 evictions. Your prompt did not change. Other conversations filled the cache. At `--capacity-blocks 200`, the hit rate falls to 0.0%.

```
STABLE-FIRST HIT RATE vs CACHE SIZE (5 users, 12 steps, measured)

  no limit     ███████████████████████████████████████████████  93.5%
  500 blocks   ███████████████████████████████████              68.8%
  200 blocks                                                    0.0%
```

Real deployments report a similar range. The SGLang paper measured hit rates on Chatbot Arena traffic. It found 52.4% for LLaVA-Next-34B and 74.1% for Vicuna-33B. Across its benchmarks the range was 50% to 99%. A hit rate near 100% comes from a synthetic test. Production traffic rarely shows it.

**The sentence to remember:** the cache matches whole blocks from token 0 forward. Put what never changes first. Put what changes on every call last.

**The trap:** a cache hit is never guaranteed. Do not build a cost model that assumes one. Model both the cached and the uncached price, and alert on the hit rate. Phase 3A adds the cached input price to `prices.yaml`, so your cost meter can do this arithmetic.

**Try this now:** run `python phase02_internals/prefix_cache_sim.py --block-size 64` and compare it with the default block size of 16. Expect the stable-first hit rate to fall from 92.0% to 91.5%, and the saving from 3.22x to 3.19x. Larger blocks share less at the edge of a prefix.

---

## 🧪 Hands-on lab — part A

Setup: `cd ~/Desktop/project/code/study-material/inference-internals/code && pip install -e .`

Five of these six exercises need no API key and no GPU. They are simulations and arithmetic, and they are marked "offline". E7 needs `export OPENAI_API_KEY=sk-...` or another OpenAI-compatible endpoint through `--base-url` and `--key-env`.

**Run status:** every offline command below was run on 2026-09-17, and the output matched the numbers printed here. E7 calls a live API. It was not run, because no API key was available on this machine on 2026-09-12. The command flags were checked against the shipped scripts.

**Exercise numbers:** part A holds E1, E2, E3, E5, E6, and E7. The numbers are the same as in the original single Phase 2 document, because other phases cite them. **E4** teaches section 2.4, so it is in part B.

Record every number. Phase 3A uses your cache hit rate.

- [ ] **E1 (offline).** Measure what paging buys.
  - Run: `python phase02_internals/paging_lab.py`
  - Expected: contiguous admits 14 concurrent requests and paged admits 253. The tool prints "paging admits 18.1x more concurrent requests here." Internal waste is 8 tokens per request.
  - If the numbers differ: you changed `--avg-tokens` or `--block-size`. Both change the result. That is the point of the flags.
  - Teaches: concurrency is a memory allocation question, not a model question.

- [ ] **E2 (break-it, offline).** Find the model that does not fit.
  - Run: `python phase02_internals/paging_lab.py --model llama-3-70b --gpu-gb 80`
  - Expected: the script exits with code 1 and prints `weights (140 GB) do not fit in 80.0 GB x 0.9`. The same line then tells you to use a bigger GPU or a smaller model.
  - Then run: `python phase02_internals/paging_lab.py --model llama-3-70b --gpu-gb 320 --avg-tokens 6000`
  - Expected: it fits. The KV pool is 148.0 GB, and the paged column admits 80 concurrent requests. The 8B model admits 253 in E1.
  - Teaches: weights use the same memory as the KV cache. A bigger model has less room for KV, and each token costs more KV. For the 70B model, each token costs 320 KB instead of 128 KB.

- [ ] **E3 (offline).** Compare static and continuous batching.
  - Run: `python phase02_internals/batching_sim.py`
  - Expected: mean TTFT is 5,357ms for static and 867ms for continuous. Throughput is 2.3 and 3.6 requests per second. Mean TPOT is 19.4ms and 25.4ms.
  - Teaches: iteration-level scheduling gives up a little speed per token. In return it gives a large gain in TTFT and throughput.

- [ ] **E5 (offline).** Price two prompt layouts that hold the same information.
  - Run: `python phase02_internals/prefix_cache_sim.py`
  - Expected: volatile-first hits 0.0% and stable-first hits 92.0%. Stable-first costs 3.22x less.
  - Teaches: prompt order is a pricing decision.

- [ ] **E6 (break-it, offline).** Make a correct layout lose its cache hits.
  - Run: `python phase02_internals/prefix_cache_sim.py --capacity-blocks 500 --users 5 --steps 12`
  - Expected: the stable-first hit rate is 68.8%. The same workload with no size limit hits 93.5%. The tool reports 5,615 evictions for stable-first.
  - Then run it with `--capacity-blocks 200`. Expected: both layouts hit 0.0%, with 19,465 evictions each.
  - Teaches: your hit rate depends on other tenants. Never model cost as if a hit is guaranteed.

- [ ] **E7 (live, UNVERIFIED against a live provider).** Watch concurrency from the client side.
  - Run, from the `code` directory: `for i in 1 2 3 4 5 6 7 8; do python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 1 & done; wait`
  - Expected: the TTFT spread across the eight runs is wider than in Phase 1 E4. In E4 the runs were sequential. You may also see a 429 rate-limit error. That error is also part of the lesson.
  - If every run is identical: your account's rate limit is high, and eight requests are small for the provider. Raise the loop to 32.
  - Costs at most: about $0.05.
  - Teaches: on a shared endpoint you can observe queueing. You cannot control it.

---

## 🔍 Check it yourself — questions against the course code

This course has no anchor repository. These questions use the exercise code you now have. The last question works on any repository.

1. Open `code/phase02_internals/prefix_cache_sim.py:86`. This line sets `still_hitting = False` inside `PrefixCache.lookup_and_fill`. Explain in one sentence why the method never returns to the hitting state after this line. Name the real rule from section 2.3 that this reproduces.
2. Open `code/phase02_internals/batching_sim.py:49`. Three cost constants sit above the `Req` class: `BASE_DECODE_MS`, `PER_SEQ_DECODE_MS`, and `MS_PER_PREFILL_TOKEN`. They are the only physics in the file. `iteration_cost_ms` at line 73 is the one function that uses them. `PER_SEQ_DECODE_MS` is 0.12 and `BASE_DECODE_MS` is 18.0. Explain what physical fact that 150x gap represents. Predict what happens to the gap between static and continuous batching if you set `PER_SEQ_DECODE_MS` to 5.0. Then test it on a copy of the file.
3. Open `code/phase02_internals/paging_lab.py:282`. The shared prefix uses floor division: `args.shared_prefix // args.block_size`. The private part uses `blocks_for` at line 67, which rounds up. Explain why the two directions differ. Use the 1,210-token example from section 2.3.
4. In any agent repository you own, find where the model messages are built. Find the first point where anything depends on the time, the request, or the user. Everything after that point is a cache miss on every call. If you find nothing volatile in the first 1,000 tokens, record that. It is a pass, and you should confirm it rather than assume it.

---

## ✅ Checkpoint 2A — answer in your own words

1. **Show the arithmetic.** You run llama-3-8b on one 80GB GPU at `gpu_memory_utilization=0.90`. The weights take 16GB. The KV cache costs 128 KB per token. Your requests hold 1,800 tokens on average. (a) How many requests fit at once under paged allocation with a 16-token block? (b) Your platform team wants to lower utilisation to 0.70 for safety. How many requests fit then? (c) What percentage of capacity does that decision cost?

2. **A colleague says:** "We moved the timestamp out of the system prompt. Our cache hit rate is now fixed. So we can bill customers at the cached price." Argue against this with two separate reasons from section 2.3. One reason is about the block rule. The other is about eviction. Use the numbers from `prefix_cache_sim.py`.

3. **This is broken.** Your chat service shows mean TTFT of 870ms in the morning and about 1,700ms at 3pm. The prompts are the same. Mean TPOT barely moves. Your team plans to add a retry when TTFT passes 1,500ms. (a) What is the likely cause? (b) How do you check it with the simulator and with your own metrics? (c) Why does the retry make it worse?

4. **Walk through what happens** in this case. Request R is decoding and holds 40 blocks. A burst of new requests uses up the block pool. List each step the scheduler takes. Say what the user sees, and what your logs show if you record only TTFT and total latency.

5. **Given these constraints, design** the memory plan. One 80GB GPU runs llama-3-8b at 0.90 utilisation. Every request starts with the same 1,200-token system prompt and holds 1,800 tokens in total. Prefix caching is on. How many requests fit at once? Show the block arithmetic. A deploy then adds a 10-token date line to the top of the system prompt. What happens to the count?

6. **A colleague says:** "Continuous batching makes every token slower. So it is worse for streaming." Argue for or against, with the numbers from E3.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) Usable memory is 80 × 0.90 = 72GB. The KV pool is 72 - 16 = 56GB. A 1,800-token request holds ceil(1800 / 16) = 113 blocks, which is 1,808 token slots. That is 1,808 × 128 KB = 0.2207 GB. 56 / 0.2207 = 253 requests. (b) At 0.70: 80 × 0.70 = 56GB usable. Minus 16GB of weights, the pool is 40GB. 40 / 0.2207 = 181 requests. (c) (253 - 181) / 253 = 28.5% of capacity lost. Check both with `paging_lab.py --gpu-util 0.70`.

2. First, the cache matches whole blocks from token 0. With 16-token blocks, a 1,210-token prefix shares only 1,200 tokens. Any volatile content later in the prompt still ends the match for everything after it. Second, entries leave the cache when other tenants need the memory. Hosted providers also remove them after a few minutes without use. In the simulator, the same good layout fell from 93.5% to 68.8% with 500 blocks. With 200 blocks it fell to 0.0%. The hit rate is a measured rate, not a guarantee. Billing that assumes a hit will collect too little.

3. (a) More requests arrive at 3pm. They wait in the queue and share the batch, so TTFT rises while TPOT stays about the same. (b) In `batching_sim.py`, raise `--rate` from 6 to 12. Continuous mean TTFT moves from 867ms to 1,674ms, about 1.9x, with the same prompts. In production, plot TTFT against requests per second or queue depth. (c) A retry adds one more request to the same queue. Each retry makes the queue longer, so TTFT rises further. Phase 0 Story 2 describes this.

4. The pool runs out. The scheduler preempts R and frees its 40 blocks. R goes back to the waiting queue. The tokens already sent stay with the user. When blocks free up, R is admitted again and its prompt is prefilled again. Then R resumes streaming. In the example timeline, the user sees the answer stop for 1.9 seconds. TTFT and total latency do not show the pause as a pause. Only an inter-token gap metric shows it.

5. The pool is 56GB. One block costs 16 × 128 KB = 2,048 KB. So the pool holds 56 × 1024 × 1024 / 2048 = 28,672 blocks. The shared prefix is 1,200 / 16 = 75 blocks, stored once. Each request needs ceil((1800 - 1200) / 16) = ceil(37.5) = 38 private blocks. (28,672 - 75) / 38 = 752 requests. `paging_lab.py --shared-prefix 1200` prints the same 752. The date line at the top changes the first block once a day. Within one day, the count stays near 752, because all requests still share the same first blocks. When the date changes, every new request misses the whole prefix. The old blocks stay in memory until eviction removes them, so capacity drops for a while. Put the date at the end instead.

6. Argue for continuous batching. Mean TPOT rises from 19.4ms to 25.4ms, which is 31% slower per token. Mean TTFT falls from 5,357ms to 867ms, which is 6.2x faster. Throughput rises from 2.3 to 3.6 requests per second, which is 57% more. A user waits 4.5 seconds less for the first token and pays about 6ms more per token. For a 200-token answer, 6ms × 200 = 1.2 seconds. The trade still favours continuous batching. The colleague is right about one thing: the worst gap of 764ms is real, and section 2.4 addresses it.

</details>

---

## References & Further Learning

Every link below was fetched and checked on 2026-09-12. The vLLM tuning guide was fetched again on 2026-09-17 and returned 200. When a source blocked automated fetching, the entry says so. Read the first group before the lab. Read the rest after.

### Read before the lab

- **Orca: A Distributed Serving System for Transformer-Based Generative Models, Yu, Jeong, Kim, Kim, Chun, OSDI 2022** — https://www.usenix.org/conference/osdi22/presentation/yu
  Focus on: section 3, which names the two problems. Some requests finish early and some arrive late. Then read section 4.2 and Algorithm 1, which is the scheduler loop in section 2.1.
  The headline number, with conditions: FasterTransformer served 0.185 requests per second at a median normalised latency of 190ms. Orca served 6.81, which is a 36.9x speedup. The test used GPT-3 175B in fp16 on 16 A100 40GB GPUs. Input lengths were drawn uniformly from 32 to 512 tokens. Output lengths were drawn from 1 to 128.
  Also read Figure 10a. There, Orca does not win on a 101B model at low load. The gain comes from scheduling, so it needs load to appear.
  Access note: usenix.org blocks automated fetching and returns 403. The link works in a browser.

- **How continuous batching enables 23x throughput in LLM inference while reducing p50 latency, Anyscale, 22 June 2023** — https://www.anyscale.com/blog/continuous-batching-llm-inference
  Focus on: the three separate steps it measures. They are simple batching, continuous batching, and continuous batching with paged memory.
  Conditions: OPT-13B on one A100 40GB, 1,000 requests, 512 input tokens each. Output lengths followed an exponential distribution.
  Numbers: up to 23x with continuous batching plus paged memory. Up to 8x with continuous batching alone. Up to 4x with FasterTransformer. The 23x figure compares against simple static batching, not against a tuned server. Always quote it with that baseline.

- **Efficient Memory Management for Large Language Model Serving with PagedAttention, Kwon et al., SOSP 2023** — https://arxiv.org/abs/2309.06180
  Readable version: https://ar5iv.labs.arxiv.org/html/2309.06180
  Authors: Kwon, Li, Zhuang, Sheng, Zheng, Yu, Gonzalez, Zhang, Stoica.
  Focus on: section 3 with Figure 2 for the waste breakdown. Section 4 for the block table. Section 4.4 for sharing and copy-on-write. Section 7.2 for block size. This paper is the source of section 2.2.
  Numbers: only 20.4% to 38.2% of KV cache memory held real token state in the measured systems. The default block size is 16 tokens. The sweep in section 7.2 found that 16 to 128 performed best. Throughput is 1.7x to 2.7x over Orca with an oracle output length. It is 2x to 4x over FasterTransformer and Orca at similar latency.

- **Fast LLM Serving with vLLM and PagedAttention, Woosuk Kwon and Zhuohan Li, 24 minutes** — https://www.youtube.com/watch?v=5ZlavKF_98U
  Focus on: 6:11 to 14:41, the clearest explanation of paging and copy-on-write. The authors animate the block table, which the paper cannot do. Watch it before you read the paper.
  Timestamps, taken from the caption track because the video has no chapters:
  - 3:07 what the KV cache is
  - 3:52 the memory budget for a 13B model on a 40GB GPU
  - 4:40 internal fragmentation
  - 5:26 reservation and external fragmentation, with the 20 to 40 percent utilisation figure
  - 6:11 the comparison with virtual memory
  - 8:30 logical blocks, physical blocks, and the block table
  - 10:03 why block size limits the waste
  - 10:50 the claim that vLLM wastes about 4%
  - 13:54 copy-on-write, step by step
  - 20:04 the Chatbot Arena deployment, about 40,000 conversations per day with half the GPUs

- **vLLM automatic prefix caching design, official design document** — https://docs.vllm.ai/en/latest/design/prefix_caching.html
  Focus on: the hash construction. Each block's hash includes the parent block's hash, the block's tokens, and extras such as the LoRA id. That parent chain is why a prefix match cannot restart in the middle.
  Eviction is least recently used. Freed blocks enter the free queue in reverse order. So later blocks leave first, because they are less likely to be reused. The page names `--prefix-caching-hash-algo`, with `sha256` as the default. Read it right after exercise E5.

- **vLLM optimization and tuning guide, official documentation** — https://docs.vllm.ai/en/latest/configuration/optimization.html
  Focus on: the defaults. Section 2.4 in part B uses the same page for the token budget trade.
  Defaults were confirmed against the v0.29.0 source tree on 2026-09-12. The check used the source because the `latest` docs carry no version number. `enable_prefix_caching` is `True`. `block_size` resolves to 16. `gpu_memory_utilization` is 0.92. The scheduling policy is `fcfs`, first come first served.

### Deep dives

- **SGLang: Efficient Execution of Structured Language Model Programs, Zheng et al., NeurIPS 2024** — https://arxiv.org/abs/2312.07104
  HTML version: https://arxiv.org/html/2312.07104v2
  Authors: Zheng, Yin, Xie, Sun, Huang, Yu, Cao, Kozyrakis, Stoica, Gonzalez, Barrett, Sheng.
  Focus on: section 3. It gives the radix tree over token sequences and the cache-aware scheduling rule. It also states that eviction removes the least recently used leaf first. Read it after the PagedAttention paper. The tree is easier to follow once you know block hashing.
  Numbers: production cache hit rates from Chatbot Arena were 52.4% for LLaVA-Next-34B and 74.1% for Vicuna-33B. Benchmark hit rates ranged from 50% to 99%. Cache-aware scheduling reached about 96% of the best possible hit rate. Throughput was up to 6.4x higher, and latency up to 3.7x lower.

- **Inside vLLM: Anatomy of a High-Throughput LLM Inference System, Aleksa Gordic, 5 September 2025** — https://vllm.ai/blog/2025-09-05-anatomy-of-vllm
  Focus on: the engine loop, the scheduler, the free block queue, and the worked hash examples for prefix caching. It connects the papers to the current source code. Read it between the papers and the code exercises.

- **LLM Inference Performance Engineering: Best Practices, Databricks and the MosaicML team, 12 October 2023** — https://www.databricks.com/blog/llm-inference-performance-engineering-best-practices
  Focus on: the arithmetic for why a bigger batch raises throughput without raising per-token speed.
  Numbers: MPT-7B on one A100 40GB shows 46ms TTFT at 512 input tokens and batch size 1. Llama2-70B on four A100s shows 114ms. Throughput moves from 0.4 to 1.7 requests per second at batch size 1, up to 36.5 at batch size 128. Model bandwidth utilisation at batch size 1 is about 55% to 60%. That is the memory-bound decode fact from Phase 1, measured.

- **Optimizing AI Inference at Character.AI, 20 June 2024** — https://blog.character.ai/optimizing-ai-inference-at-character-ai/
  Focus on: the scale numbers, not the technique. About 20,000 queries per second. Under one cent per hour of conversation. Serving costs cut at least 33x since launch.
  Note: the deeper technical post it used to link now redirects to the blog index. That post covered multi-query attention and cross-layer KV sharing. Do not cite its numbers from a live link.

### Prefix caching in production

- **2x faster inference with KV cache-aware routing, Baseten, 16 March 2026** — https://www.baseten.co/blog/how-baseten-achieved-2x-faster-inference-with-nvidia-dynamo/
  Focus on: why the load balancer matters. A prefix cache does not help when the load balancer picks the wrong replica. That replica does not hold the prefix. Baseten routes with a radix tree over cached prefixes. Read it after exercise E6.
  Synthetic test: Qwen3 Coder 480B A35B, about 50,000-token inputs, four replicas. Results: 89% cache hit rate, 50% lower TTFT, 34% lower TPOT.
  Shadowed production traffic: 48% lower P95 latency, 49% lower P99, 61% more requests per second.

- **Predicted-Latency Based Scheduling for LLMs, llm-d project, 13 March 2026** — https://llm-d.ai/blog/predicted-latency-based-scheduling-for-llms
  Focus on: the opposite pressure to the Baseten post. Read them together. It reports KV cache utilisation rising from 30% to over 70%, and uneven queue depths across pods. It says prefix cache hit rates "collapse frequently as traffic patterns shift and cached prefixes get evicted". Quote checked on 2026-09-17.
  Its main point supports exercise E6. Routing for cache reuse concentrates load. Routing for low utilisation spreads it.

- **Context Engineering for AI Agents: Lessons from Building Manus, 18 July 2025** — https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
  Focus on: the timestamp in the system prompt, which it names as a mistake, and the append-only rule for history. This is the practitioner view of section 2.3.
  Its 10x gap between cached and uncached input was Claude Sonnet list pricing in July 2025. Check current prices before you reuse the number.

---

## Cheatsheet — part A

```
THE SCHEDULER LOOP
  one iteration = one forward pass = ONE token for every decoding request
  static batching     : batch runs to completion; freed slots stay idle
  continuous batching : a freed slot is refilled next iteration
  measured (batching_sim, 40 req, 6/s):
    static      TTFT 5357ms  TPOT 19.4ms  2.3 rq/s
    continuous  TTFT  867ms  TPOT 25.4ms  3.6 rq/s   worst gap 764ms
  arrival rate 6/s → 12/s: continuous TTFT 867ms → 1674ms, same prompts
  your inputs on a hosted API: prompt length, output length,
    arrival pattern, prefix reuse
  never answer a TTFT spike with retries: they lengthen the queue

PAGED KV CACHE
  KV bytes/token = 2 x kv_heads x head_dim x bytes x layers
    llama-3-8b fp16 → 128 KB/token
  contiguous : reserve max_model_len per request   → 14 concurrent
  paged      : ceil(tokens / block) blocks on demand → 253 concurrent
  paged + 1,200-token shared prefix                 → 752 concurrent
  waste under paging = unused tail of the last block (8 tokens at 16)
  out of blocks = PREEMPTION, not an error: prefill is redone later
  gpu_memory_utilization: capacity setting. vLLM 0.29.0 default 0.92
    0.92 → 0.70 on 80GB: 260 → 181 requests (-30%)

PREFIX CACHE
  key = hash(parent chain + this block's tokens) → prefix-only match
  match starts at token 0, moves forward, stops at the first difference
  whole blocks only; a partial tail block is never shared
  eviction is LRU, and other tenants share the pool
  RULE: stable content first, volatile content last
  measured: same tokens, 0.0% vs 92.0% hit rate, 3.22x cost difference
  eviction: 93.5% → 68.8% at 500 blocks → 0.0% at 200 blocks
  production hit rates (SGLang paper): 52.4% and 74.1%

THE COMMANDS (all offline)
  paging_lab.py                              → concurrency and waste
  paging_lab.py --shared-prefix 1200         → what sharing buys
  batching_sim.py [--rate 12]                → policy comparison
  prefix_cache_sim.py                        → layout cost
  prefix_cache_sim.py --capacity-blocks 500 --users 5 --steps 12
                                             → eviction
```

Part B covers three topics: chunked prefill and the stream freeze, constrained decoding, and the compaction trigger.
