# Phase 4A — Renting a GPU and serving a model

Phases 1 to 3 measured someone else's server. This phase is the first one where you run the server, and it is the first one that costs real money for hardware.

That changes the shape of the work. Until now a mistake cost you a few cents of API calls. Now a mistake costs you an hour of a rented GPU, and the most common mistakes happen before a single token is generated. So part A is about the boring parts: what an hour actually costs, how to start the server, and how to measure it in a way you could defend to someone who disagrees with you.

Phase 4 is split into two documents.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, this document                                                    │
│  4.1  Renting a GPU            — prices, billing traps, and the download │
│  4.2  Serving it               — two engines, and the flags that are not │
│                                  named alike                             │
│  4.3  Benchmarking it          — the number every later decision needs   │
│                                                                          │
│ PART B, the next document                                                │
│  4.4  Quantization             — what it buys, and what it quietly costs │
│  4.5  Speculative decoding     — a bet with published odds               │
│  4.6  The self-host decision   — arithmetic, not preference              │
└──────────────────────────────────────────────────────────────────────────┘
```

Your Mac cannot do this phase. Both engines need CUDA. Apple Silicon can run llama.cpp or MLX, which are good tools and are not what this phase teaches.

Time: 2 to 3 hours, of which about one hour is on rented hardware. Budget about $3 to $5 for part A.

Setup, before you rent anything:

```
cd ~/Desktop/project/code/study-material/inference-internals/code
pip install -e .
python phase04_serving/bench_client.py --dry-run
```

---

## 4.1 — Renting a GPU for an hour (and not being surprised by the bill)

Why this matters: this is the first phase that needs hardware you do not have. Your Mac cannot run vLLM or SGLang, because both need CUDA. Apple Silicon can run llama.cpp or MLX, which are excellent and are not what this phase is about. So you will rent, for about an hour, and the goal of this section is that nothing about the invoice surprises you.

**Budget for this phase: about $5 to $10**, assuming you follow the section on downloads. It is easy to spend more than that by accident, and the rest of this section is how not to.

### What an hour actually costs

Prices read on 2026-09-13. They move, so re-read them and write the date next to your own numbers.

```
┌──────────────────────┬───────────────┬───────────────┬────────────────────┐
│ provider             │ H100 80GB $/h │ A100 80GB $/h │ billing            │
├──────────────────────┼───────────────┼───────────────┼────────────────────┤
│ Vast.ai (market)     │ 1.87 - 2.00   │ not available │ per second         │
│ RunPod Community     │ 1.99 (PCIe)   │ 1.19 (PCIe)   │ per second         │
│ RunPod Secure        │ 3.49 (SXM)    │ 1.59 (SXM)    │ per second         │
│ Modal (serverless)   │ 3.95          │ 2.50          │ per second, no     │
│                      │               │               │ idle charge        │
│ Lambda               │ 3.99          │ 2.79          │ per MINUTE, and    │
│                      │               │               │ billed while idle  │
│ CoreWeave            │ 6.16          │ 2.70          │ not stated         │
│ AWS p5.4xlarge       │ 6.88          │ 3.43          │ per second         │
└──────────────────────┴───────────────┴───────────────┴────────────────────┘
```

The CoreWeave and AWS A100 figures are divided down from eight-GPU instance prices. The AWS H100 figure is published directly for a single-GPU instance, which most comparisons miss because they quote only the eight-GPU price.

**Correct a claim you will read everywhere.** "Specialist clouds are 10x cheaper than the hyperscalers" is not supported by today's list prices. The widest verified gap on an H100 is **3.68x**, and the most managed specialist sits within **12%** of AWS. Only interruptible marketplace bids reach anything like 10x, and those can be taken away mid-run.

### Three ways the bill surprises people

**One: per-minute billing and idle charges.** One provider in that table bills in one-minute increments and states plainly that instances are billed for as long as they are running, whether or not you are using them. If you start an instance, go to lunch, and come back, you paid for lunch. Per-second providers with no idle charge remove the whole category of mistake.

**Two: storage keeps billing after you stop.** On one marketplace, stopping a pod does not stop the volume charge. It **doubles** the rate, from $0.10 to $0.20 per GB per month. A 140 GB model sitting on a stopped pod costs $28 a month to do nothing. Worse, if your balance reaches zero the volume can be deleted, which destroys the cached model you were paying to keep.

**Three, and this is the big one: the download is billed at GPU rates.** The clock starts when the container starts, not when the weights arrive.

```
  140 GB model, download time and what it costs on a $3.49/hour GPU

  link speed          time        GPU cost while waiting
  ────────────────────────────────────────────────────────
  500 MB/s            4.7 min     $0.27
  400 MB/s            5.8 min     $0.34
  200 MB/s           11.7 min     $0.68
  125 MB/s (1 Gbps)  18.7 min     $1.09
   34 MB/s (276 Mbps) 67.6 min     $2.19   ← longer than your rental
```

That last row is a real machine that was on offer today, in a marketplace listing that showed its measured downlink. **On that machine the download alone takes longer than a one-hour rental and costs more than the compute.** Marketplaces publish a measured downlink per machine. Read it before you rent.

These times are arithmetic from providers' stated link rates, not measured downloads. Treat them as the right order of magnitude.

### How to make the download cheap

- **Start small.** An 8B model is roughly 16 GB and downloads in a minute or two. Do the whole phase on an 8B model first, then repeat one measurement on something larger if you want.
- **Use the current tool.** Many tutorials still tell you to set `HF_HUB_ENABLE_HF_TRANSFER=1`. The Hugging Face documentation now describes that package as deprecated and points to `hf_xet`, which ships with recent `huggingface_hub`. On a fast machine with plenty of RAM, set `HF_XET_HIGH_PERFORMANCE=1`.
- **Check the size before you start.** `hf download --dry-run` prints the exact byte count.
- **Consider not downloading it all.** `hf-mount` mounts a repository read-only and fetches only the bytes your code reads.
- **Decide about a cached volume with arithmetic.** Re-downloading 140 GB costs roughly $0.34 to $1.09 of GPU time. A standard network volume costs about $9.80 a month. So the volume pays for itself somewhere between 9 and 29 re-downloads a month. Below that, re-download. There is a hidden cost too: attaching a volume pins you to one datacentre, which reduces GPU availability.

**For a single one-hour learning session, the serverless option is the cheapest answer**, because its volume storage is free below a terabyte, it bills per second, and it charges nothing while idle.

### What you are actually paying for

```
  THE RENTAL CLOCK — one hour, and where it goes

  t=0:00   container starts          ◄── billing starts HERE
  t=0:00   pull the engine image         paid
  t=0:02   download 16 GB of weights     paid
  t=0:06   engine loads, profiles KV     paid
  t=0:08   server ready                  paid
  t=0:08   you run the benchmark         paid, and this is the only part
  t=0:20   you read the output           paid       you actually wanted
  t=0:25   you stop the instance     ◄── compute billing stops HERE
  t=0:25   the volume keeps billing  ◄── and on one provider it now costs
                                         DOUBLE the running rate

  work you wanted: 12 minutes.  billed: 25 minutes, plus storage.
```

The fix is not to type faster. It is to have every command written down before t=0:00, and to know your provider's storage behaviour before you press stop.

### Before you start the clock

Have these ready in a text file, so that the expensive minutes are spent serving and not typing:

1. The exact model id you will serve, and its size in GB.
2. Your access token, if the model is gated.
3. The full launch command, copied from section 4.2.
4. The benchmark command from section 4.3, with your model id already substituted.
5. A note of where you will paste the resulting numbers.

**The sentence to remember:** you are renting a clock, not a GPU, and the clock runs during the download.

**The trap:** stopping an instance to save money while a volume keeps billing at double the running rate.

**Try this now:** before renting anything, open your chosen provider's pricing page and write down three numbers with today's date: the hourly rate, the billing increment, and the storage rate while stopped. You will use the first one in section 4.6.
---

## 4.2 — Serving it (two engines, and the flags that are not named alike)

Why this matters: Phase 2 taught you what a serving engine does. This section is where you run one. The first deployment fails for boring reasons, so this covers the boring reasons.

Everything below was verified against the source at the release tag on 2026-09-13: **vLLM 0.29.0**, released 2026-09-09, and **SGLang 0.5.19**, released 2026-09-05. Check your own versions, because these change monthly.

### The two commands

```bash
# vLLM. Serves an OpenAI-compatible endpoint on port 8000.
vllm serve Qwen/Qwen3-8B

# SGLang. Serves on port 30000.
sglang serve Qwen/Qwen3-8B
```

Two notes on the entrypoints, both of which older tutorials get wrong.

`python -m vllm.entrypoints.openai.api_server` is deprecated as of vLLM 0.29.0. Use `vllm serve`.

`python -m sglang.launch_server` still works but now prints a warning saying `sglang serve` is the recommended entrypoint. The official install page still shows the old form.

### The flag map

The engines do the same things with different words. This table is the thing to keep open on your first day.

```
┌──────────────────────────┬──────────────────────────┬─────────────────────┐
│ what you want            │ vLLM 0.29.0              │ SGLang 0.5.19       │
├──────────────────────────┼──────────────────────────┼─────────────────────┤
│ the model                │ positional               │ positional or       │
│                          │                          │ --model-path        │
│ maximum context          │ --max-model-len          │ --context-length    │
│ share of GPU memory      │ --gpu-memory-utilization │ --mem-fraction-     │
│                          │ (default 0.92)           │ static (computed)   │
│ concurrent sequences     │ --max-num-seqs           │ --max-running-      │
│                          │                          │ requests            │
│ tokens per iteration     │ --max-num-batched-tokens │ --chunked-prefill-  │
│                          │                          │ size                │
│ GPUs to shard across     │ --tensor-parallel-size   │ --tp-size           │
│ quantization             │ --quantization           │ --quantization      │
│ KV cache precision       │ --kv-cache-dtype         │ --kv-cache-dtype    │
│ speculative decoding     │ --speculative-config     │ --speculative-      │
│                          │ (JSON)                   │ algorithm (+ flags) │
│ structured-output engine │ --structured-outputs-    │ --grammar-backend   │
│                          │ config.backend           │                     │
│ default port             │ 8000                     │ 30000               │
└──────────────────────────┴──────────────────────────┴─────────────────────┘
```

**The memory flags are not equivalent, and this is a real source of wrong benchmarks.** `--gpu-memory-utilization` and `--mem-fraction-static` account for memory differently. Setting both to 0.90 does not give the two engines the same KV cache. A public benchmark comparing the engines was retracted by its own author after he learned that `--max-model-len` maps to `--context-length` and not to a different flag he had used. Another contributor had to explain that the two memory flags allocate differently and that the engines' batching defaults differ. Assume a head-to-head comparison is wrong until you have checked the flag mapping.

### The one flag that solves most first-day problems

```bash
vllm serve Qwen/Qwen3-8B --max-model-len auto
```

vLLM will binary-search the largest context that actually fits in your GPU memory. It is verified in the source, it is barely documented, and it removes the most common first failure. Use it, read the number it picks, then pin that number explicitly so your deployment is reproducible.

### The defaults are not what the documentation implies

vLLM chooses its batching defaults at startup from GPU memory **and** from whether you are serving or running offline:

```
  GPU memory                      max_num_batched_tokens   max_num_seqs
  under 70 GiB, or any A100                        2,048            256
  70 to 160 GiB, not an A100                       8,192          1,024
  160 GiB or more                                 16,384          1,024
```

The offline Python class gets different values from the server on the same hardware. So a script and an endpoint do not batch alike by default, and a benchmark that compares them is comparing two configurations.

SGLang auto-tunes too, from total GPU memory, choosing a chunked prefill size of 2,048 below 35 GB, 4,096 up to 60 GB, 8,192 up to 160 GB, and 16,384 above. Its memory fraction is computed from a reserve formula, falling back to 0.88 when GPU memory cannot be determined.

**The practical consequence:** if you are comparing anything, pin the batching flags explicitly on both sides. Otherwise you are measuring two different servers.

### When it will not start

Three failures cover almost everything, and they need different fixes.

**One: no room for the KV cache at all.** vLLM says, verbatim:

> No available memory for the cache blocks. Try increasing `gpu_memory_utilization` when initializing the engine

**Two: the model loads, but your context does not fit.** vLLM's message is the useful one, because it computes the answer for you:

> To serve at least one request with the model's max seq len (N), (X GiB KV cache is needed, which is larger than the available KV cache memory (Y GiB). Based on the available memory, the estimated maximum model length is Z. Try increasing `gpu_memory_utilization` ... or decreasing `max_model_len`

Take the Z it prints and set `--max-model-len` to it. Or use `auto` and skip the step.

**Three: a raw allocator failure from PyTorch**, which mentions fragmentation and suggests `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. This one is usually a symptom of pushing the memory fraction too high.

```
  WHICH FAILURE DID YOU GET?

  server will not start
        │
        ├── "No available memory for the cache blocks"
        │        the weights filled the GPU. Nothing left for KV.
        │        → smaller model, more GPUs, or a quantized checkpoint
        │
        ├── "estimated maximum model length is Z"
        │        the model fits; your CONTEXT does not.
        │        → --max-model-len Z   (the message computed it for you)
        │        → or --max-model-len auto and let it search
        │
        └── "CUDA out of memory ... expandable_segments"
                 a raw allocator failure, usually fragmentation
                 → lower the memory fraction, do not raise it
```

**SGLang's fix goes the opposite direction, which catches people.** Its message reads:

> Loaded weights leave no GPU memory for the KV cache under --mem-fraction-static=&lt;v&gt;. Raise --mem-fraction-static above &lt;suggested&gt;

On vLLM you usually lower the context. On SGLang you usually **raise** the memory fraction. The flags are named as if they do the same thing and the remedies point in opposite directions.

Both engines ship a diagnostic worth running before you open a bug report: `vllm collect-env` and `python -m sglang.check_env`.

### Things that will cost you the first fifteen minutes

**Driver and CUDA differ between the engines.** The default vLLM wheel builds against CUDA 12.9, which needs a 575-series driver or newer. SGLang 0.5.19 depends on CUDA 13, which needs a 580-series driver. **A machine on a 570-series driver will run vLLM and will not run SGLang natively.** Check the driver before you pick the engine, especially on a marketplace machine.

**Gated models need a human step.** A Llama checkpoint is gated, which means someone must be approved on the model page before any token works. Set `HF_TOKEN`, or pass `--hf-token` to vLLM. Do this before you start the clock.

**Some repositories ship the weights twice.** One 8B checkpoint is 16.06 GB of safetensors and 32.13 GB if you download the whole repository, because it also carries a duplicate copy in another format. The engines read only the safetensors. Filter your download or you pay for twice the bytes, at GPU rates, for nothing.

### Structured output when you serve it yourself

Phase 2 section 2.5 said this would arrive here. This is that debt.

When you use a hosted API, constrained decoding is a black box. When you serve, you choose the engine behind it, and the two engines behave very differently on the same schema.

**vLLM picks a backend for you, and falls back.** The default is `auto`, and the chain is:

```
  your schema
      │
      ▼
  try xgrammar ────── supported? ──yes──► use xgrammar
      │ no
      ▼
  does the schema use a guidance-unsupported feature?
      │ yes ──────────────────────────────► use outlines
      │ no
      ▼
  use guidance
```

The keywords that push a request off xgrammar are specific: `multipleOf` on numbers, `uniqueItems`, `contains`, `minContains` and `maxContains` on arrays, a `format` outside its supported list, a string combining `pattern` or `format` with `minLength` or `maxLength`, and `patternProperties` or `propertyNames` on objects.

**Pin a backend and the fallback disappears.** The comment in the source is literally "xgrammar with no fallback". An unsupported keyword then becomes an HTTP 400 rather than a silent switch.

**And there is a constraint that surprises everyone.** vLLM resolves the backend **once for the whole engine**, not per request. The source comment says so directly. So the first structured-output request your server sees decides the backend for every later one. If that first request happened to use `multipleOf`, your entire server is now running outlines.

**SGLang does not fall back per schema at all.** Its `--grammar-backend` defaults to `xgrammar`, a default that is resolved in code and not documented on the server-arguments page. When a schema fails to compile, SGLang aborts that request with a message naming the failure. It never tries another backend.

It has exactly one fallback, and it is worse than no fallback if you do not know about it. At startup, if xgrammar cannot handle the model's tokenizer, SGLang logs a warning and sets the backend to `none`, which **disables structured output for the entire server**. Your requests then return unconstrained text and nothing errors.

**The request fields differ too:**

```
  vLLM     json   regex   choice   grammar   json_object   structural_tag
  SGLang   json_schema   regex   ebnf   structural_tag
```

vLLM's `grammar` is SGLang's `ebnf`. There is no `choice` in SGLang.

**What to do with this.** Give the same schema to both engines and you can get three different outcomes: a silent backend switch with different latency, a 400, or unconstrained output. Test your real schemas against your chosen engine before you ship, and log which backend resolved.

**The sentence to remember:** the two engines do the same job with different words, different defaults, and different failure directions, so never carry a flag value across without checking the mapping.

**The trap:** benchmarking the engines against each other on default settings. Their defaults differ by GPU size, by serve-versus-offline mode, and by memory accounting, so the defaults comparison measures the defaults, not the engines.

**Try this now:** before renting anything, write out your full launch command for both engines, with `--max-model-len auto` on one and `--context-length` pinned on the other. Then check your target machine's driver version against the CUDA requirements above.
---

## 4.3 — Benchmarking it (the number that decides everything else)

Why this matters: section 4.6 asks you for one number, the output tokens per second your server actually sustains. Every self-host cost estimate depends on it, and it is the one input you cannot look up. This section is how you produce it honestly.

### The rule that makes a comparison valid

**Use one client against both servers.** Not each engine's own benchmark tool against itself.

Both engines ship a benchmark harness, and both harnesses can drive the other engine. vLLM's request functions include an OpenAI-compatible path that works against SGLang on port 30000. SGLang's include vLLM backends directly. So you have no excuse for running two different clients and comparing the outputs.

```
  THE ONLY FAIR SHAPE

                    ┌─────────────────────┐
                    │  ONE client         │
                    │  one trace file     │
                    │  one set of flags   │
                    └──────────┬──────────┘
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        ┌────────────────┐          ┌────────────────┐
        │ engine A       │          │ engine B       │
        │ port 8000      │          │ port 30000     │
        │ flags PINNED   │          │ flags PINNED   │
        └────────────────┘          └────────────────┘
                 │                           │
                 └─────────────┬─────────────┘
                               ▼
                    two result files you can
                    actually put side by side

  THE SHAPE THAT PRODUCES WRONG ANSWERS

        engine A's own client  ──►  engine A on its defaults
        engine B's own client  ──►  engine B on its defaults
                               ──►  you compared four things at once
```

This matters more than it sounds. Three public comparisons between these engines were shown to be wrong, and none of the errors were in the engines:

- One benchmark used 50 requests. Rerun with 2,000 prompts, the gap fell from about 2x to 8.6%.
- One author retracted his own result after learning the flag mapping from section 4.2. Memory use turned out to be "basically the same".
- One comparison ran the engines on their own different batching defaults.

**Both projects have now stopped publishing head-to-head numbers.** vLLM removed its cross-engine benchmarking path as unmaintained. An independent benchmarking project stated it assigns one engine per model specifically to avoid restarting the argument.

### The course client

`bench_client.py` is the neutral client. It speaks the OpenAI streaming API, so it drives vLLM, SGLang, a gateway, or a hosted API with the same code and the same timing logic.

```
python phase04_serving/bench_client.py --dry-run
python phase04_serving/bench_client.py --base-url http://localhost:8000/v1 \
    --model Qwen/Qwen3-8B --concurrency 1,4,16,64 \
    --trace phase04_serving/traces/support.jsonl --out vllm.json
```

Then the same command against the other engine, changing only the URL and the output file:

```
python phase04_serving/bench_client.py --base-url http://localhost:30000/v1 \
    --model Qwen/Qwen3-8B --concurrency 1,4,16,64 \
    --trace phase04_serving/traces/support.jsonl --out sglang.json
```

It reports, per concurrency level, exactly what Phase 1 and Phase 2 taught you to care about:

```
┌─────────────┬──────────┬──────────┬─────────┬─────────┬───────────┬─────┐
│ concurrency │ TTFT p50 │ TTFT p99 │ ITL p50 │ ITL p99 │ out tok/s │ err │
└─────────────┴──────────┴──────────┴─────────┴─────────┴───────────┴─────┘
```

The `ITL p99` column is the one most benchmarks omit. It is the stream-freeze number from Phase 2 section 2.4, and it is the metric a user actually feels.

### Read the shape, not one number

A concurrency sweep has a characteristic shape, and the shape is the result:

```
  output tok/s                        TTFT p99
      ▲                                   ▲
      │        ╭──────────                │                    ╱
      │      ╱                            │                 ╱
      │    ╱                              │            ╱
      │  ╱                                │      ╱
      │╱                                  │╱
      └──────────────► concurrency        └──────────────► concurrency
        throughput flattens                 latency never stops rising
```

Where throughput flattens is your server's useful capacity. The TTFT at that point is what your users experience at capacity. Those two numbers together are your operating point, and section 4.6 needs the first one.

### The engines' own tools, if you want them

Both are worth knowing, because their trace-replay support is better than the course client's.

```bash
# vLLM
vllm bench serve --backend vllm --model <id> --endpoint /v1/completions \
  --dataset-name sharegpt --dataset-path <path> --num-prompts 10

# SGLang. Note: `sglang.bench_serving` is deprecated and now warns.
python -m sglang.benchmark.serving --backend sglang --port 30000 \
  --dataset-name random --num-prompts 100 \
  --random-input-len 256 --random-output-len 32
```

For replaying a real traffic trace with its own timestamps, vLLM has `--dataset-name timed_trace` and SGLang has `--dataset-name mooncake --use-trace-timestamps`. Both read JSONL with per-request timestamps and schedule by them, which is closer to production than a fixed arrival rate. I did not confirm that one trace file works in both harnesses.

vLLM also has `vllm bench startup`, which measures cold and warm engine startup. SGLang has no equivalent. On a rented GPU, startup time is money.

### What the only audited comparison found

There is exactly one same-hardware, same-model, independently audited comparison of these two engines: a submission to MLPerf Inference v5.1.

Conditions: one machine with eight H200 GPUs, one CUDA version, one driver, Llama-3.1-70B in FP8, 24,576 samples, with latency limits of 2,000 ms time to first token and 200 ms per output token. Each engine was tuned by the submitter.

```
┌──────────────────────┬──────────────┬─────────────┬─────────────┐
│ quantization path    │ scenario     │ SGLang      │ vLLM        │
├──────────────────────┼──────────────┼─────────────┼─────────────┤
│ pre-quantized FP8    │ offline tok/s│  31,383     │  26,319     │
│ pre-quantized FP8    │ server tok/s │  30,304     │  25,628     │
│ dynamic FP8          │ offline tok/s│  27,697     │  30,893     │
│ dynamic FP8          │ server tok/s │  26,435     │  26,903     │
└──────────────────────┴──────────────┴─────────────┴─────────────┘
```

**The winner flips with the quantization path.** SGLang leads by 18 to 19% on the pre-quantized model. vLLM leads by 2 to 12% on dynamic quantization. Accuracy matched between them.

Anyone quoting a single winner from this submission is choosing a row. That is the most useful thing this table teaches, and it generalises: **there is no "faster engine", only a faster configuration on a workload.**

Its limits are real. Those engine versions are from mid-2025, roughly twenty vLLM releases before the one in section 4.2. There is no audited comparison for the current versions.

**One number you will see and should not use.** A frequently cited "3.1x faster" figure comes from a July 2024 post written by one of the two engine teams, testing a vLLM version from 2024, with a flag that disables the other engine's prefix caching. It is not evidence about either engine today.

### Cost per million tokens, which is the point

Take the peak throughput from your sweep and turn it into money:

```
python phase04_serving/gpu_economics.py --gpu-hourly <your rate> --tps <your peak>
```

That is the handoff into section 4.6. A throughput number with no cost attached is trivia.

**The sentence to remember:** one client, both servers, pinned flags, and a trace instead of a fixed prompt, or your comparison is measuring your configuration rather than the engines.

**The trap:** benchmarking with a single prompt length. Real traffic is a distribution of prompt sizes, and prefill cost scales with it. The shipped trace deliberately mixes three size tiers for that reason.

**Try this now:** run `python phase04_serving/bench_client.py --dry-run --trace phase04_serving/traces/support.jsonl` and confirm it reports 20 prompts. Then open the trace file and check the spread of prompt lengths for yourself.
---

## 🧪 Hands-on lab — part A

**Read this before you rent anything.** Exercises E1 and E2 are offline and cost nothing. Do them first, because they are the preparation that keeps the paid exercises short. E3 to E7 need a rented GPU and together should cost about $3 to $5 if you work from your prepared notes.

**Live-run status, stated honestly:** every offline script in this phase was executed on the author's machine on 2026-09-13, and the outputs printed in the sections above are real outputs from those runs. No GPU was rented, so E3 to E7 were **not executed**. Their commands, flag names and defaults were verified against the vLLM 0.29.0 and SGLang 0.5.19 source at their release tags. Run them and record what you see.

- [ ] **E1 (offline).** Look at the traffic before you measure it.
  - Run: `python phase04_serving/bench_client.py --dry-run --trace phase04_serving/traces/support.jsonl --concurrency 1,4,16,64`
  - Expected: it reports 20 prompts and a plan of 256 requests.
  - Then open `phase04_serving/traces/support.jsonl` and measure the spread of prompt lengths yourself. Write down the shortest and the longest.
  - Teaches: a benchmark on one prompt length measures one point on a curve you have not drawn.

- [ ] **E2 (offline).** Write the whole session down before the clock starts.
  - Produce a text file containing: your chosen model id and its size in GB, the full vLLM launch command, the full SGLang launch command, the benchmark command with your model id already substituted, and your provider's hourly rate with today's date.
  - Then check one thing that will otherwise waste your first fifteen minutes: your target machine's NVIDIA driver version. vLLM's default build needs 575 or newer. SGLang 0.5.19 needs 580 or newer.
  - Teaches: on rented hardware, preparation is a cost-control measure.

- [ ] **E3 (needs a GPU, about $1).** Serve a model and let the engine size itself.
  - Run: `vllm serve Qwen/Qwen3-8B --max-model-len auto`
  - Expected: the server starts and logs the context length it chose. Write that number down, then restart with it pinned explicitly.
  - If it fails: read the error against the three cases in section 4.2 before changing anything.
  - Teaches: `auto` removes the most common first failure, and pinning the result afterwards keeps the deployment reproducible.

- [ ] **E4 (break-it, needs a GPU).** Make it run out of memory on purpose, then let it tell you the fix.
  - Run: `vllm serve Qwen/Qwen3-8B --max-model-len 1000000`
  - Expected: it refuses to start and prints a message containing an estimated maximum model length. Copy that number.
  - Restart with `--max-model-len <that number>` and confirm it starts.
  - Teaches: the useful error in this stack computes the answer for you. Read it before reaching for a bigger GPU.

- [ ] **E5 (needs a GPU, about $1).** Produce the number section 4.6 needs.
  - Run: `python phase04_serving/bench_client.py --base-url http://localhost:8000/v1 --model Qwen/Qwen3-8B --concurrency 1,4,16,64 --trace phase04_serving/traces/support.jsonl --out vllm.json`
  - Expected: throughput rises then flattens, TTFT p99 rises throughout. Record the peak output tokens per second and the concurrency where it occurred.
  - Teaches: your server's capacity is where the throughput curve flattens, not where it stops erroring.

- [ ] **E6 (needs a GPU, about $1).** Compare the engines without fooling yourself.
  - Start SGLang on the same machine: `sglang serve Qwen/Qwen3-8B`
  - Run the **same** client command as E5, changing only `--base-url` to port 30000 and `--out` to `sglang.json`.
  - Before comparing, pin the batching flags on both sides using the mapping in section 4.2. Their defaults differ by GPU size and by serve-versus-offline mode.
  - Expected: two files you can compare honestly. The difference may be small. That is a legitimate result.
  - Teaches: one client, both servers, pinned flags. Three public comparisons of these engines were wrong for exactly the reasons this exercise controls.

- [ ] **E7 (break-it, needs a GPU).** Send a schema that splits the two engines.
  - Build a JSON schema using `multipleOf` on a number field, or `patternProperties` on an object. Send it as a structured-output request to each engine.
  - Expected on vLLM with the default `auto` backend: the request succeeds, and the engine has silently switched backends for the whole server. Expected on SGLang: the request is aborted with a compile failure.
  - Then pin vLLM's backend with `--structured-outputs-config.backend xgrammar` and send it again. Expect HTTP 400.
  - Teaches: the same schema has three possible outcomes across these engines. Phase 2 promised you this section; this exercise is the proof.
---

## 🔍 Check it yourself

1. Open `phase04_serving/bench_client.py` and find `one_request`. Locate where it records a value into `r.gaps`. Explain why the first token is deliberately excluded from that list, and name the metric in the output table that depends on the exclusion.
2. In the same file, find the branch that runs when `r.out_tokens == 0` after the stream ends. Explain what server behaviour triggers it and why the code prefers a labelled approximation over a silent zero.
3. Open `phase04_serving/traces/support.jsonl`. It cycles three prompt-size tiers. Explain, using Phase 2 section 2.4, why benchmarking with only the shortest tier would make a server look better than it is.
4. On any machine you can reach with a GPU, or on a provider's spec page: find the NVIDIA driver version. Then decide from section 4.2 which of the two engines you could run today without upgrading it.

---

## ✅ Checkpoint 4A — answer in your own words

1. Show the math. You rent one H100 at $3.49 per hour. Your model is 140 GB and the machine's measured downlink is 276 Mbps. (a) How long does the download take? (b) What does that download cost in GPU time? (c) You plan eight one-hour sessions this month. Compare re-downloading each time against a $9.80 per month cached volume. (d) Name the non-money cost of the volume.

2. A colleague says: "I benchmarked both engines on defaults and vLLM was faster, so we should use vLLM." Give three specific reasons that result may be meaningless, using section 4.2 and 4.3. One reason is about batching defaults, one about memory flags, and one about the client.

3. This is broken. Your server refuses to start with a message about KV cache memory. (a) Name the two different vLLM messages this could be and how you tell them apart. (b) For the second one, name the specific number in the message that tells you what to do. (c) State what the equivalent SGLang message asks you to do, and why the direction is the opposite of what the flag name suggests.

4. Walk me through what happens. Your vLLM server has been up for an hour serving plain chat. A new client sends its first structured-output request, using a schema with `multipleOf` on a price field. (a) Trace what the engine does with that schema. (b) State what happens to every structured-output request that arrives after it, and why. (c) Name the one-line change that would have made this an error instead, and say whether you would want that.

5. Design it. You have one hour of rented GPU and want to produce a defensible comparison of the two engines for your workload. Write the plan. Cover: what you prepare before starting the clock, which client you use and why, which flags you pin, what traffic you replay, and the two numbers you will take away.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) 276 Mbps is 34.5 MB/s. 140,000 MB / 34.5 = about 4,058 seconds, which is 67.6 minutes. (b) 67.6 minutes at $3.49 per hour is about $3.93 on that machine, and the download alone exceeds a one-hour rental. (c) Eight downloads at roughly $0.34 to $1.09 each on a fast link is $2.72 to $8.72, so a $9.80 volume is close to break-even at eight sessions and clearly worth it above about nine to twenty-nine. On the slow machine above, one download already costs more than the volume. (d) A network volume pins your workloads to one datacentre, which reduces GPU availability and removes failover options.

2. First, the engines choose batching defaults from GPU memory and from whether you are serving or running offline, so their defaults differ before you type anything. Second, `--gpu-memory-utilization` and `--mem-fraction-static` account for memory differently, so equal-looking values do not give equal KV cache. Third, each engine's own benchmark client differs, and a fair test needs one client driving both. A public benchmark was retracted for exactly the second reason, and another was corrected from 2x to 8.6% by raising the request count.

3. (a) One says there is no available memory for cache blocks at all, which means the weights consumed everything. The other says the model's maximum sequence length needs more KV cache than exists, and it names both figures. (b) The second message prints an estimated maximum model length. Set `--max-model-len` to it, or use `--max-model-len auto`. (c) SGLang asks you to **raise** `--mem-fraction-static`, because that flag is the share reserved for the engine rather than a ceiling on it. The two flags are named as if they match and their remedies point in opposite directions.

4. (a) With the default `auto` backend, vLLM validates the schema against xgrammar, finds `multipleOf` unsupported on numbers, and falls back. It then checks whether the schema uses a guidance-unsupported feature, and routes to guidance or outlines accordingly. (b) Every later structured-output request uses that same backend, because vLLM resolves the backend once per engine and not per request. The source says so explicitly. So one client's schema has reconfigured the server for everyone. (c) Pinning `--structured-outputs-config.backend xgrammar` removes the fallback and turns that request into an HTTP 400. You usually do want that in production, because a loud failure on one request is better than a silent reconfiguration affecting all of them.

5. Before the clock: write both launch commands, the client command with the model id substituted, the driver check, and the model size. Download to a cached volume if you will repeat the session. Use one client, `bench_client.py`, against both servers, because each engine's own harness differs. Pin `--max-model-len` against `--context-length`, and pin the batched-token and concurrent-sequence flags on both sides using the mapping table, rather than accepting two different sets of defaults. Replay the mixed-size trace rather than one prompt, because prefill cost scales with prompt length and real traffic is a distribution. Take away the peak output tokens per second and the TTFT p99 at that concurrency. Those two numbers are the operating point, and the first one feeds the cost arithmetic.

</details>
---

## References & Further Learning

Every URL was fetched and checked on 2026-09-13, and every flag and default was verified against the engine source at its release tag rather than from documentation prose. That distinction matters here more than anywhere else in the course: on several points the documentation and the source disagree, and the source wins.

### Must-read before you rent

**vLLM quickstart, pinned to the release** — https://docs.vllm.ai/en/v0.29.0/getting_started/quickstart/
Pin the version in the URL. The `latest` docs describe an unreleased developer preview and carry no version number, so a flag you read there may not exist in the version you install. Focus on the serve command and nothing else on your first pass.

**vLLM serve CLI reference** — https://docs.vllm.ai/en/v0.29.0/cli/serve/
Use it as a lookup while the server is running, not as reading. The defaults worth knowing are `--gpu-memory-utilization` at 0.92 and `--enable-chunked-prefill` on by default. The batching defaults are not on this page; they are chosen at startup from GPU memory and from whether you serve or run offline.

**SGLang server arguments** — https://docs.sglang.io/docs/advanced_features/server_arguments
Read it next to the flag-mapping table in section 4.2 rather than on its own. Note what it does not say: the page does not document that `--grammar-backend` resolves to xgrammar by default. That default lives in code.

**Fast LLM Serving with vLLM and PagedAttention** — Woosuk Kwon and Zhuohan Li, 32 minutes.
https://www.youtube.com/watch?v=5ZlavKF_98U
The authors deriving PagedAttention from the problem rather than presenting it as a feature. Phase 2 cited this for the mechanism; watch it here before your first deployment so the memory flags make sense. Timestamps, taken from the caption track because the video has no chapters: 2:55 what the KV cache is, 5:00 the three kinds of memory waste with the 20 to 40 percent utilisation figure, 6:56 PagedAttention, 8:53 the block table, 11:26 sharing and copy-on-write, 18:49 the results. Focus on 5:00 to 11:00. Skip 19:00 onward, which is stale 2023 adoption history.

### Deep dives

**vLLM Office Hours: Intro to vLLM V1** — Michael Goin, 59 minutes.
https://www.youtube.com/watch?v=jmzIvQZCLZM
The most mechanical public explanation of why the current scheduler exists. Watch it after you have run a server once and want to know why the flags are shaped the way they are. Timestamps from captions: 20:14 why they rearchitected, 27:58 the core idea that the scheduler now counts only the tokens for the next forward pass, 29:30 a chunked prefill walkthrough against a token budget, 33:28 piecewise CUDA graphs, 42:45 features deliberately dropped. Focus on 27:58 to 32:30.

**Efficient LLM Inference with SGLang** — Lianmin Zheng, 24 minutes.
https://www.youtube.com/watch?v=Ny4xxErgFgQ
The only talk that explains grammar-constrained decoding mechanically, which is why it belongs next to section 4.2's structured-output material. Timestamps from captions: 4:29 SGLang's one-token page size against the other engine's 16 or 32, 9:55 RadixAttention, 10:51 building the radix tree across a session, 12:19 recursive eviction, 14:41 constrained decoding with a live demo, 15:55 the schema to regex to state machine to token mask pipeline, 16:59 jump-forward decoding. Focus on 9:55 to 17:00.

**State of vLLM 2025** — Simon Mo, 31 minutes. https://www.youtube.com/watch?v=tN_-nktp1Hk
Watch one moment: at 12:39 he gives the clearest statement of why serving is hard, that prefix caching, speculative decoding, chunked prefill and structured output all modify the same scheduler. That sentence explains most of the interactions in Phases 2 and 4.

**Introduction to LLM serving with SGLang** — Yineng Zhang, 43 minutes.
https://www.youtube.com/watch?v=Ahtaha9fEM0
The only hands-on talk in this list, and it has real chapters rather than caption-derived timestamps. Use 6:49 to 30:02 while you are actually starting a server.

### Benchmarking

**vLLM benchmark CLI** — https://docs.vllm.ai/en/v0.29.0/benchmarking/cli/
The commands and the exact metric labels it prints. Its `--dataset-name timed_trace` mode replays a JSONL trace using each request's own timestamp, which is closer to production than a fixed arrival rate. The trace field names are configurable.

**SGLang serving benchmark** — `python -m sglang.benchmark.serving`
Note the module path. `sglang.bench_serving` is now a deprecation shim that warns, and every documentation page checked still teaches the old path. Its trace replay is `--dataset-name mooncake` with `--use-trace-timestamps`.

**MLPerf Inference v5.1, Krai submission** — https://github.com/mlcommons/inference_results_v5.1/tree/main/open/Krai
The only audited, same-hardware, same-model comparison of the two engines. Focus on the four throughput rows and on the fact that the winner flips with the quantization path. Conditions are in the systems JSON: eight H200 GPUs, one CUDA version and driver for both, Llama-3.1-70B in FP8, 24,576 samples, with stated latency limits. Both engines were separately tuned, so this is not an untuned baseline.
Its limits: the engine versions are from mid-2025, roughly twenty vLLM releases before the current one, and there is no audited comparison of today's versions.

**InferenceX** — https://github.com/SemiAnalysisAI/InferenceX
The best live source that still pairs the engines, using a single neutral load generator forked from vLLM's own. Read the configs rather than the dashboard. Three caveats: hardware is vendor-supplied and vendors submit configurations, engine versions are often nightly images pinned by commit rather than release tags, and release-tag coverage is asymmetric between the two engines.

### Do not cite these

- A widely repeated "3.1x faster" figure comes from a July 2024 post written by one of the two engine teams, testing a 2024 version of the other engine, with a flag that disables the other engine's prefix caching.
- Two frequently quoted MLPerf v5.0 throughput numbers compare the two engines on **different models**. They are wrong rather than merely stale.
- Both projects have stopped publishing head-to-head numbers, and one removed its cross-engine benchmarking path as unmaintained. Treat any current head-to-head claim as needing its versions and flags stated before you believe it.

### GPU rental

Read your provider's own pricing page on the day you rent, and write the date next to the number. The prices in section 4.1 were read on 2026-09-13 from the providers' public pages, with one marketplace read through its public offers API because its pricing page carries no figures at all.
Three things to look up rather than assume: the billing increment, whether an idle instance is billed, and the storage rate while an instance is stopped. One provider bills per minute and charges while idle. One doubles the volume rate when you stop the pod.

**Hugging Face download tooling** — https://huggingface.co/docs/huggingface_hub/en/guides/download
Read one paragraph. `HF_HUB_ENABLE_HF_TRANSFER` is deprecated and the replacement is `hf_xet`, with `HF_XET_HIGH_PERFORMANCE=1` on a fast machine. Many tutorials still teach the deprecated variable. Also useful: `hf download --dry-run` prints the byte count before you start, and `hf-mount` fetches only the bytes your code reads.

---

## Cheatsheet — part A

```
RENTING
  budget for this phase: $5-10        the clock runs during the DOWNLOAD
  H100 $/hr on 2026-09-13: market 1.87-2.00 | RunPod 1.99-3.49 |
    Modal 3.95 | Lambda 3.99 | CoreWeave 6.16 | AWS p5.4xlarge 6.88
  the real specialist-vs-hyperscaler gap is 3.68x, NOT the 10x you will read
  billing: Modal/RunPod/Vast per SECOND | Lambda per MINUTE and while IDLE
  stopping a pod can DOUBLE the volume rate, from $0.10 to $0.20/GB/mo
  140GB download: 4.7 min at 500 MB/s ... 67.6 min at 276 Mbps
  volume pays for itself at ~9-29 re-downloads/month, and pins you to one region
  use hf_xet, NOT hf_transfer (deprecated) | hf download --dry-run | hf-mount

LAUNCH
  vllm serve <model>                      port 8000
  sglang serve <model>                    port 30000
  deprecated: python -m vllm.entrypoints.openai.api_server
  warns:      python -m sglang.launch_server

FLAG MAP                vLLM 0.29.0                 SGLang 0.5.19
  context               --max-model-len             --context-length
  memory share          --gpu-memory-utilization    --mem-fraction-static
                        (0.92)                      (computed, NOT equivalent)
  concurrent seqs       --max-num-seqs              --max-running-requests
  tokens per iteration  --max-num-batched-tokens    --chunked-prefill-size
  GPUs                  --tensor-parallel-size      --tp-size
  grammar engine        --structured-outputs-       --grammar-backend
                        config.backend
  THE FLAG TO USE FIRST: --max-model-len auto   (binary-searches what fits)

DEFAULTS ARE NOT FIXED
  vLLM batching depends on GPU memory AND serve-vs-offline:
    <70 GiB or any A100 -> 2048 / 256    70-160 GiB -> 8192 / 1024
    >=160 GiB -> 16384 / 1024
  SGLang auto-tunes chunked prefill by GPU memory; fraction falls back to 0.88
  PIN THEM EXPLICITLY before comparing anything

WHEN IT WILL NOT START
  "No available memory for the cache blocks"  -> weights ate everything
  "estimated maximum model length is Z"       -> use Z, or --max-model-len auto
  PyTorch CUDA OOM + fragmentation hint       -> memory fraction too high
  SGLang says RAISE --mem-fraction-static     -> opposite direction to vLLM
  diagnostics: vllm collect-env | python -m sglang.check_env
  drivers: vLLM cu129 needs 575+ | SGLang 0.5.19 needs 580+
           a 570-series box runs vLLM and NOT SGLang

STRUCTURED OUTPUT WHEN YOU SERVE
  vLLM default backend = auto, falls back xgrammar -> outlines/guidance
    pushed off xgrammar by: multipleOf, uniqueItems, contains, minContains,
    maxContains, unsupported format, pattern+minLength, patternProperties,
    propertyNames
  PINNED backend = NO fallback = HTTP 400
  vLLM resolves the backend ONCE PER ENGINE: the first structured request
    decides it for every later one
  SGLang default = xgrammar, NO per-schema fallback, compile failure aborts
    its only fallback sets backend=none, disabling structured output SERVER-WIDE
  fields: vLLM json/regex/choice/grammar/json_object/structural_tag
          SGLang json_schema/regex/ebnf/structural_tag   (grammar == ebnf)

BENCHMARKING
  ONE client against BOTH servers. Both harnesses can drive the other engine.
  pin the flags, replay a trace, never compare defaults
  read the SHAPE: throughput flattens, TTFT p99 never stops rising
  capacity = where throughput flattens; the TTFT there is what users get
  ITL p99 is the stream-freeze number most benchmarks omit
  trace replay: vLLM --dataset-name timed_trace | SGLang mooncake
                + --use-trace-timestamps
  the only audited comparison: the winner FLIPS with the quantization path

THE COMMANDS
  bench_client.py --dry-run --trace ...            plan it, offline
  bench_client.py --base-url ... --model ...       measure it
  vllm bench serve / python -m sglang.benchmark.serving   the engines' own
  vllm collect-env / python -m sglang.check_env    before filing a bug
```

Part B takes the throughput number you just measured and turns it into a decision: whether to quantize, whether to speculate, and whether to self-host at all.
