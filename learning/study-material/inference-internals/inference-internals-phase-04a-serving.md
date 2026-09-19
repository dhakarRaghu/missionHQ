# Phase 4A — Renting a GPU and serving a model

Phases 1 to 3 measured someone else's server. In this phase you run the server yourself. It is also the first phase that costs real money for hardware.

That changes the work. Until now a mistake cost you a few cents of API calls. Now a mistake costs you an hour of a rented GPU. The most common mistakes happen before the server generates a single token. So part A covers the practical parts:

- what an hour of GPU time really costs
- how to start the server
- how to measure it in a way you can defend to someone who disagrees

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

Your Mac cannot do this phase. Both engines need CUDA, the NVIDIA GPU programming platform. Apple Silicon can run llama.cpp or MLX. Those are good tools, but this phase does not teach them.

Time: 2 to 3 hours. About one hour of that is on rented hardware. Budget about $3 to $5 for part A.

Setup, before you rent anything:

```bash
cd ~/Desktop/project/code/study-material/inference-internals/code
pip install -e .
python phase04_serving/bench_client.py --dry-run
```

In a uv environment with no `pip`, skip the install line and prefix each command with `uv run`. `pyproject.toml` documents both ways.

---

## 4.1 — Renting a GPU for an hour (and not being surprised by the bill)

Why this matters: this is the first phase that needs hardware you do not have. vLLM and SGLang are the two serving engines this phase uses, and both need CUDA. So you will rent a GPU for about an hour. The goal of this section is that nothing on the invoice surprises you.

**Budget for this phase: about $5 to $10**, if you follow the advice on downloads below. It is possible to spend more by accident. The rest of this section shows how to avoid that.

### What an hour actually costs

Prices were read on 2026-09-13. Prices change, so read them again and write the date next to your own numbers.

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

The CoreWeave figures and the AWS A100 figure are eight-GPU instance prices divided by eight. AWS publishes the H100 figure directly for a single-GPU instance. Most comparisons miss this, because they quote only the eight-GPU price.

**Correct a claim you will read everywhere.** People say that specialist clouds are 10x cheaper than the hyperscalers. Today's list prices do not support this. The widest verified gap on an H100 is **3.68x**, which is $6.88 divided by $1.87. CoreWeave, the most managed specialist in the table, is within **12%** of AWS. Only interruptible marketplace bids come close to 10x. The provider can take those machines away during your run.

### Three ways the bill surprises people

**One: per-minute billing and idle charges.** One provider in the table bills in one-minute steps. Its pricing page says it bills an instance while the instance runs. It does not matter whether you use it. If you start an instance and go to lunch, you pay for lunch. Per-second providers with no idle charge remove this whole class of mistake.

**Two: storage keeps billing after you stop.** On one marketplace, stopping a pod does not stop the volume charge. It **doubles** the rate, from $0.10 to $0.20 per GB per month. A 140 GB model on a stopped pod costs $28 a month and does nothing. Also, if your balance reaches zero, the provider can delete the volume. You then lose the cached model you paid to keep.

**Three: the download is billed at GPU rates. This is the largest one.** The clock starts when the container starts, not when the weights arrive.

```
  140 GB model, download time and what it costs on a $3.49/hour GPU

  link speed          time        GPU cost while waiting
  ────────────────────────────────────────────────────────
  500 MB/s            4.7 min     $0.27
  400 MB/s            5.8 min     $0.34
  200 MB/s           11.7 min     $0.68
  125 MB/s (1 Gbps)  18.7 min     $1.09
   34 MB/s (276 Mbps) 67.6 min     $3.93   ← longer than your rental
```

The last row is a real machine that a marketplace offered on 2026-09-13. Its listing showed the measured downlink. **On that machine the download alone takes longer than a one-hour rental.** Marketplaces publish a measured downlink for each machine. Read it before you rent.

These times are arithmetic from the providers' stated link rates. Nobody measured the downloads. Treat them as the right order of magnitude. Each cost is the time in hours multiplied by $3.49. For the last row, 67.6 / 60 × $3.49 = $3.93.

### How to make the download cheap

- **Start small.** An 8B model is roughly 16 GB and downloads in a minute or two. Do the whole phase on an 8B model first. Then repeat one measurement on a larger model if you want.
- **Use the current tool.** Many tutorials still tell you to set `HF_HUB_ENABLE_HF_TRANSFER=1`. The Hugging Face documentation now marks that package as deprecated. It points to `hf_xet`, which ships with recent `huggingface_hub`. On a fast machine with plenty of RAM, set `HF_XET_HIGH_PERFORMANCE=1`.
- **Check the size before you start.** `hf download --dry-run` prints the exact byte count.
- **Consider not downloading all of it.** `hf-mount` mounts a repository read-only. It fetches only the bytes your code reads.
- **Decide about a cached volume with arithmetic.** Downloading 140 GB again costs roughly $0.34 to $1.09 of GPU time. A standard network volume costs about $9.80 a month. $9.80 / $1.09 is about 9, and $9.80 / $0.34 is about 29. So the volume is cheaper once you download the model again more than 9 to 29 times a month. Below that, download it again. There is also a cost that is not money. A volume ties you to one datacentre, and that reduces the GPUs you can get.

**For a single one-hour learning session, the serverless option is the cheapest.** Its volume storage is free below a terabyte. It bills per second, and it charges nothing while idle.

### What you are actually paying for

```
  THE RENTAL CLOCK — one hour, and where it goes (example times)

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

Typing faster does not fix this. Write every command down before t=0:00. Learn your provider's storage behaviour before you press stop.

### Before you start the clock

Put these in a text file. Then you spend the paid minutes on serving, not on typing.

1. The exact model id you will serve, and its size in GB.
2. Your access token, if the model is gated.
3. The full launch command, copied from section 4.2.
4. The benchmark command from section 4.3, with your model id already in it.
5. A note of where you will paste the results.

**The sentence to remember:** you are renting a clock, not a GPU, and the clock runs during the download.

**The trap:** you stop an instance to save money, and the volume keeps billing at double the running rate.

**Try this now:** before you rent anything, open your provider's pricing page. Write down three numbers with today's date: the hourly rate, the billing step, and the storage rate while stopped. You will use the first one in section 4.6.

---

## 4.2 — Serving it (two engines, and the flags that are not named alike)

Why this matters: Phase 2 taught you what a serving engine does. In this section you run one. The first deployment usually fails for simple, avoidable reasons. This section covers those reasons.

Everything below was checked against the source code at the release tag on 2026-09-13:

- **vLLM 0.29.0**, released 2026-09-09
- **SGLang 0.5.19**, released 2026-09-05

Check your own versions. These engines release new versions every month.

### The two commands

```bash
# vLLM. Serves an OpenAI-compatible endpoint on port 8000.
vllm serve Qwen/Qwen3-8B

# SGLang. Serves on port 30000.
sglang serve Qwen/Qwen3-8B
```

Older tutorials get both entrypoints wrong. An entrypoint is the command that starts the server.

- `python -m vllm.entrypoints.openai.api_server` is deprecated as of vLLM 0.29.0. Use `vllm serve`.
- `python -m sglang.launch_server` still works. It now prints a warning that `sglang serve` is the recommended entrypoint. The official install page still shows the old form.

### The flag map

The two engines do the same things with different flag names. Keep this table open on your first day.

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

**The memory flags are not equivalent. This causes real benchmark errors.** `--gpu-memory-utilization` and `--mem-fraction-static` count memory in different ways. If you set both to 0.90, the two engines do not get the same KV cache.

A public benchmark of the two engines was retracted by its own author. He had not known that `--max-model-len` maps to `--context-length`, and he had used a different flag. Another contributor then explained two more facts. The two memory flags allocate differently, and the engines have different batching defaults. Assume a head-to-head comparison is wrong until you have checked the flag mapping.

### The one flag that solves most first-day problems

```bash
vllm serve Qwen/Qwen3-8B --max-model-len auto
```

With `auto`, vLLM searches for the largest context that fits in your GPU memory. This behaviour is in the source code, but the documentation barely mentions it. It removes the most common first failure. Use it and read the number it picks. Then set that number explicitly, so your deployment is reproducible.

### The defaults are not what the documentation implies

vLLM chooses its batching defaults at startup. It uses the GPU memory **and** whether you run a server or offline Python code:

```
  GPU memory                      max_num_batched_tokens   max_num_seqs
  under 70 GiB, or any A100                        2,048            256
  70 to 160 GiB, not an A100                       8,192          1,024
  160 GiB or more                                 16,384          1,024
```

The table shows the server values. The offline Python class gets different values on the same hardware. So a script and an endpoint do not batch the same way by default. A benchmark that compares them compares two configurations.

SGLang also tunes itself from total GPU memory. It chooses a chunked prefill size as follows:

- 2,048 below 35 GB
- 4,096 up to 60 GB
- 8,192 up to 160 GB
- 16,384 above that

SGLang computes its memory fraction from a reserve formula. When it cannot read the GPU memory, it uses 0.88.

**What this means in practice:** before you compare anything, set the batching flags explicitly on both sides. Otherwise you measure two different servers.

### When it will not start

Three failures cover almost every case, and each needs a different fix.

**One: no room for the KV cache at all.** vLLM prints this exact text:

> No available memory for the cache blocks. Try increasing `gpu_memory_utilization` when initializing the engine

**Two: the model loads, but your context does not fit.** This vLLM message is the useful one. It computes the answer for you:

> To serve at least one request with the model's max seq len (N), (X GiB KV cache is needed, which is larger than the available KV cache memory (Y GiB). Based on the available memory, the estimated maximum model length is Z. Try increasing `gpu_memory_utilization` ... or decreasing `max_model_len`

Take the Z it prints and set `--max-model-len` to it. Or use `auto` and skip this step.

**Three: a raw allocator failure from PyTorch.** The message mentions fragmentation. It suggests `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. This failure usually means the memory fraction is set too high.

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

There is a fourth failure that comes before any memory check. You ask for more context than the model supports. The vLLM 0.29.0 source, `vllm/config/model.py:2501`, raises a `ValueError` for this. Qwen3-8B's `config.json` sets `max_position_embeddings` to 40960.

```bash
# WRONG: ask for a context longer than the model was built for
vllm serve Qwen/Qwen3-8B --max-model-len 1000000
# ValueError: User-specified max_model_len (1000000) is greater than
# the derived max_model_len (...)

# RIGHT: let vLLM fit the context to memory, then pin the value it logs
vllm serve Qwen/Qwen3-8B --max-model-len auto
```

The error text comes from the vLLM 0.29.0 source, fetched on 2026-09-17. It was not produced by a run, because no GPU was rented. This document shortens the rest of the message to `(...)`. Its exact values depend on the model's config files.

**SGLang's fix goes in the opposite direction, and this confuses people.** Its message reads:

> Loaded weights leave no GPU memory for the KV cache under --mem-fraction-static=&lt;v&gt;. Raise --mem-fraction-static above &lt;suggested&gt;

On vLLM you usually lower the context. On SGLang you usually **raise** the memory fraction. The flag names suggest they do the same thing. The fixes point in opposite directions.

Both engines ship a diagnostic command. Run it before you open a bug report: `vllm collect-env` and `python -m sglang.check_env`.

### Things that will cost you the first fifteen minutes

**The two engines need different drivers and CUDA versions.**

- The default vLLM wheel is built against CUDA 12.9. It needs a 575-series NVIDIA driver or newer.
- SGLang 0.5.19 depends on CUDA 13. It needs a 580-series driver.
- **A machine with a 570-series driver runs vLLM, but it does not run SGLang natively.**

Check the driver before you pick the engine. This matters most on a marketplace machine.

**Gated models need a human step.** A Llama checkpoint is gated. Someone must get approval on the model page before any access token works. Set `HF_TOKEN`, or pass `--hf-token` to vLLM. Do this before you start the clock.

**Some repositories contain the weights twice.** One 8B checkpoint is 16.06 GB of safetensors files. The whole repository is 32.13 GB, because it also holds a copy in another format. The engines read only the safetensors files. Filter your download. Otherwise you pay GPU rates to download twice the bytes for nothing.

### Structured output when you serve it yourself

Phase 2 section 2.5 said this topic would come back in Phase 4. This is that section.

Structured output means the engine forces the model's output to match a schema. It does this with constrained decoding: at each step, it blocks tokens that would break the schema. With a hosted API, you cannot see how this works. When you serve the model, you choose the engine behind it. The two engines behave very differently on the same schema.

**vLLM picks a backend for you, and falls back to another one.** The default is `auto`, and the chain is:

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

These keywords move a request off xgrammar:

- `multipleOf` on numbers
- `uniqueItems`, `contains`, `minContains`, and `maxContains` on arrays
- a `format` outside xgrammar's supported list
- a string that combines `pattern` or `format` with `minLength` or `maxLength`
- `patternProperties` or `propertyNames` on objects

**If you pin a backend, the fallback disappears.** The comment in the source says "xgrammar with no fallback". An unsupported keyword then returns HTTP 400 instead of a silent switch.

**One constraint surprises almost everyone.** vLLM chooses the backend **once for the whole engine**, not once per request. The source comment says so directly. So the first structured-output request your server receives decides the backend for every later request. If that first request used `multipleOf`, your whole server now runs outlines.

**SGLang never falls back for a schema.** Its `--grammar-backend` defaults to `xgrammar`. The code sets this default. The server-arguments page does not document it. When a schema fails to compile, SGLang aborts that request with a message that names the failure. It never tries another backend.

SGLang has exactly one fallback, and it is worse than no fallback if you do not know about it. At startup, xgrammar may not support the model's tokenizer. SGLang then logs a warning and sets the backend to `none`. That **turns off structured output for the entire server**. Your requests then return unconstrained text, and nothing reports an error.

**The request fields differ too:**

```
  vLLM     json   regex   choice   grammar   json_object   structural_tag
  SGLang   json_schema   regex   ebnf   structural_tag
```

vLLM's `grammar` is SGLang's `ebnf`. SGLang has no `choice` field.

**What to do with this.** The same schema can give three different outcomes across the two engines:

1. a silent backend switch, with different latency
2. an HTTP 400
3. unconstrained output

Test your real schemas against your chosen engine before you ship. Log which backend the engine chose.

**The sentence to remember:** the two engines differ in flag names, defaults, and the direction of each fix. Check the mapping before you copy a flag value.

**The trap:** you benchmark the engines against each other on default settings. Their defaults depend on GPU size, on server or offline mode, and on how each counts memory. So the comparison measures the defaults, not the engines.

**Try this now:** before you rent anything, write out the full launch command for both engines. Use `--max-model-len auto` on vLLM and a fixed `--context-length` on SGLang. Then check your target machine's driver version against the CUDA requirements above.

---

## 4.3 — Benchmarking it (the number that decides everything else)

Why this matters: section 4.6 needs one number from you. That number is the output tokens per second your server sustains. Every self-host cost estimate depends on it, and you cannot look it up. This section shows how to measure it honestly.

### The rule that makes a comparison valid

**Use one client against both servers.** Do not run each engine's own benchmark tool against its own engine.

Both engines ship a benchmark harness, and each harness can drive the other engine. vLLM's request functions include an OpenAI-compatible path that works against SGLang on port 30000. SGLang's harness includes vLLM backends directly. So there is no reason to run two different clients and compare their outputs.

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

This matters more than it seems. People showed that three public comparisons of these engines were wrong. None of the errors was in the engines:

- One benchmark used 50 requests. A rerun with 2,000 prompts cut the gap from about 2x to 8.6%.
- One author retracted his own result after he learned the flag mapping from section 4.2. The memory use turned out to be "basically the same".
- One comparison ran each engine on its own batching defaults.

**Both projects have now stopped publishing head-to-head numbers.** vLLM removed its cross-engine benchmark path because nobody maintained it. An independent benchmarking project stated that it assigns one engine per model. Its reason was to avoid restarting the argument.

### The course client

`bench_client.py` is the neutral client. It uses the OpenAI streaming API. So the same code and the same timing logic drive vLLM, SGLang, a gateway, or a hosted API.

```bash
python phase04_serving/bench_client.py --dry-run
python phase04_serving/bench_client.py --base-url http://localhost:8000/v1 \
    --model Qwen/Qwen3-8B --concurrency 1,4,16,64 \
    --trace phase04_serving/traces/support.jsonl --out vllm.json
```

Then run the same command against the other engine. Change only the URL and the output file:

```bash
python phase04_serving/bench_client.py --base-url http://localhost:30000/v1 \
    --model Qwen/Qwen3-8B --concurrency 1,4,16,64 \
    --trace phase04_serving/traces/support.jsonl --out sglang.json
```

For each concurrency level, it reports what Phase 1 and Phase 2 taught you to watch. TTFT is time to first token. ITL is inter-token latency, the gap between two tokens in one stream.

```
┌─────────────┬──────────┬──────────┬─────────┬─────────┬───────────┬─────┐
│ concurrency │ TTFT p50 │ TTFT p99 │ ITL p50 │ ITL p99 │ out tok/s │ err │
└─────────────┴──────────┴──────────┴─────────┴─────────┴───────────┴─────┘
```

Most benchmarks leave out the `ITL p99` column. It is the stream-freeze number from Phase 2 section 2.4. It is the delay a user actually notices.

### Read the shape, not one number

A concurrency sweep has a typical shape, and the shape is the result:

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

The point where throughput flattens is your server's useful capacity. The TTFT at that point is what your users get at capacity. Together, these two numbers are your operating point. Section 4.6 needs the first one.

### The engines' own tools, if you want them

Both tools are worth knowing. Their trace-replay support is better than the course client's.

```bash
# vLLM
vllm bench serve --backend vllm --model <id> --endpoint /v1/completions \
  --dataset-name sharegpt --dataset-path <path> --num-prompts 10

# SGLang. Note: `sglang.bench_serving` is deprecated and now warns.
python -m sglang.benchmark.serving --backend sglang --port 30000 \
  --dataset-name random --num-prompts 100 \
  --random-input-len 256 --random-output-len 32
```

Both engines can replay a real traffic trace with its own timestamps:

- vLLM: `--dataset-name timed_trace`
- SGLang: `--dataset-name mooncake --use-trace-timestamps`

Both read JSONL with a timestamp for each request, and send each request at its time. That is closer to production than a fixed arrival rate. I did not confirm that one trace file works in both harnesses.

vLLM also has `vllm bench startup`, which measures cold and warm engine startup. SGLang has no equivalent. On a rented GPU, startup time costs money.

### What the only audited comparison found

Only one comparison of these two engines used the same hardware and the same model, with an independent audit. It is a submission to MLPerf Inference v5.1.

Conditions:

- one machine with eight H200 GPUs, one CUDA version, and one driver
- Llama-3.1-70B in FP8, with 24,576 samples
- latency limits of 2,000 ms time to first token and 200 ms per output token
- the submitter tuned each engine

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

**The winner changes with the quantization path.** SGLang leads by 18 to 19% on the pre-quantized model. vLLM leads by 2 to 12% with dynamic quantization. Accuracy was the same for both.

Anyone who quotes a single winner from this submission has picked one row. That is the most useful lesson in the table, and it applies generally. **No engine is "the faster engine". Only a configuration is faster, on one workload.**

The table has real limits. Those engine versions are from mid-2025. That is roughly twenty vLLM releases before the version in section 4.2. No audited comparison exists for the current versions.

**One number you will see and should not use.** People often cite a "3.1x faster" figure. It comes from a July 2024 post by one of the two engine teams. The post tested a 2024 vLLM version, with a flag that turned off the other engine's prefix caching. It tells you nothing about either engine today.

### Cost per million tokens, which is the point

Take the peak throughput from your sweep and turn it into money:

```bash
python phase04_serving/gpu_economics.py --gpu-hourly <your rate> --tps <your peak>
```

This command leads into section 4.6. A throughput number without a cost does not help a decision.

**The sentence to remember:** use one client, both servers, pinned flags, and a trace. Otherwise you measure your configuration, not the engines.

**The trap:** you benchmark with a single prompt length. Real traffic has a spread of prompt sizes, and prefill cost grows with prompt size. The shipped trace mixes three size groups for that reason.

**Try this now:** run `python phase04_serving/bench_client.py --dry-run --trace phase04_serving/traces/support.jsonl` and confirm that it reports 20 prompts. Then open the trace file and check the spread of prompt lengths yourself.

---

## 🧪 Hands-on lab — part A

**Read this before you rent anything.** E1 and E2 are offline and cost nothing. Do them first. They are the preparation that keeps the paid exercises short. E3 to E7 need a rented GPU. Together they should cost about $3 to $5 if you work from your prepared notes.

**Run status:** every offline command below was executed on the author's machine. The first run was on 2026-09-13, and the offline commands were run again on 2026-09-17 with the same output. No GPU was rented, so E3 to E7 are **UNVERIFIED on a rented GPU**. Their commands, flag names, and defaults were checked against the vLLM 0.29.0 and SGLang 0.5.19 source at their release tags. Run them and record what you see.

- [ ] **E1 (offline).** Look at the traffic before you measure it.
  - Run: `python phase04_serving/bench_client.py --dry-run --trace phase04_serving/traces/support.jsonl --concurrency 1,4,16,64`
  - Expected: `prompts: 20 prompts from phase04_serving/traces/support.jsonl` and `total  : 256 requests`. That is 64 requests at each of 4 levels.
  - Then open `phase04_serving/traces/support.jsonl` and measure the prompt lengths yourself. Write down the shortest and the longest.
  - Expected: the `prompt` field is 50 characters at its shortest and 5,507 at its longest. The lengths form three groups: 50 to 93, 1,102 to 1,197, and 5,448 to 5,507 characters. Measured with a short Python loop over the file on 2026-09-17.
  - Teaches: a benchmark on one prompt length measures one point on a curve you have not drawn.

- [ ] **E2 (offline).** Write the whole session down before the clock starts.
  - Write a text file with these items:
    - your chosen model id and its size in GB
    - the full vLLM launch command and the full SGLang launch command
    - the benchmark command, with your model id already in it
    - your provider's hourly rate, with today's date
  - Then check your target machine's NVIDIA driver version. Otherwise it can waste your first fifteen minutes. vLLM's default build needs 575 or newer. SGLang 0.5.19 needs 580 or newer.
  - Teaches: on rented hardware, preparation controls cost.

- [ ] **E3 (rented GPU, about $1, UNVERIFIED).** Serve a model and let the engine choose its own context size.
  - Run: `vllm serve Qwen/Qwen3-8B --max-model-len auto`
  - Expected: the server starts and logs the context length it chose. Write that number down. Then restart with that number set explicitly.
  - If it fails: compare the error with the cases in section 4.2 before you change anything.
  - Teaches: `auto` removes the most common first failure. Setting the result explicitly afterwards keeps the deployment reproducible.

- [ ] **E4 (break-it, rented GPU, UNVERIFIED).** Make the server run out of KV cache memory on purpose. Then let it tell you the fix.
  - Do not use a context above the model's limit. An earlier version of this exercise used `--max-model-len 1000000`. The vLLM 0.29.0 source shows that it fails earlier, with the `ValueError` from section 4.2.
  - Run: `vllm serve Qwen/Qwen3-8B --max-model-len 40960 --gpu-memory-utilization 0.25`
  - Expected: the server refuses to start with one of the two KV messages from section 4.2. If it prints an estimated maximum model length, copy that number.
  - Restart with `--max-model-len <that number>` and the same memory flag. Confirm that it starts.
  - Why 0.25 should fail, inferred and not run: 0.25 of an 80 GB GPU is 20 GB. The 8B weights take about 16 GB. For Qwen3-8B, one token of KV cache needs 2 × 36 × 8 × 128 × 2 bytes = 147,456 bytes. The factors are 36 layers, 8 KV heads, a head size of 128, and 2 bytes per value. So 40,960 tokens need about 6.0 GB. The config values come from Qwen3-8B's `config.json`.
  - If it fails: if the server starts anyway, lower `--gpu-memory-utilization` in steps of 0.02. If you get the first message instead, raise it a little.
  - Teaches: in this stack, the useful error computes the answer for you. Read it before you rent a bigger GPU.

- [ ] **E5 (rented GPU, about $1, UNVERIFIED).** Produce the number section 4.6 needs.
  - Run: `python phase04_serving/bench_client.py --base-url http://localhost:8000/v1 --model Qwen/Qwen3-8B --concurrency 1,4,16,64 --trace phase04_serving/traces/support.jsonl --out vllm.json`
  - Expected: throughput rises and then flattens. TTFT p99 rises the whole time. Record the peak output tokens per second, and the concurrency where it occurred.
  - Teaches: your server's capacity is where the throughput curve flattens, not where errors start.

- [ ] **E6 (rented GPU, about $1, UNVERIFIED).** Compare the engines without fooling yourself.
  - Start SGLang on the same machine: `sglang serve Qwen/Qwen3-8B`
  - Run the **same** client command as E5. Change only `--base-url` to port 30000 and `--out` to `sglang.json`.
  - Before you compare, set the batching flags explicitly on both sides. Use the mapping in section 4.2. The defaults depend on GPU size and on server or offline mode.
  - Expected: two files you can compare honestly. The difference may be small. A small difference is a valid result.
  - Teaches: use one client, both servers, and pinned flags. Three public comparisons of these engines were wrong for exactly the reasons this exercise controls.

- [ ] **E7 (break-it, rented GPU, UNVERIFIED).** Send a schema that makes the two engines behave differently.
  - Build a JSON schema that uses `multipleOf` on a number field, or `patternProperties` on an object. Send it to each engine as a structured-output request.
  - Expected on vLLM with the default `auto` backend: the request succeeds. The engine has silently switched backends for the whole server.
  - Expected on SGLang: the engine aborts the request with a compile failure.
  - Then pin vLLM's backend with `--structured-outputs-config.backend xgrammar` and send the schema again. Expect HTTP 400.
  - Teaches: the same schema has three possible outcomes across these engines. Phase 2 promised this section, and this exercise shows it.

---

## 🔍 Check it yourself

1. Open `phase04_serving/bench_client.py:72`. This is `one_request`. Find where it adds a value to `r.gaps`, at line 99. Explain why the code leaves out the first token from that list. Name the metric in the output table that depends on this.
2. In the same file, go to line 102. This branch runs when `r.out_tokens == 0` after the stream ends. Explain what server behaviour causes it. Explain why the code uses a labelled approximation instead of a silent zero.
3. Open `phase04_serving/traces/support.jsonl`. It cycles through three prompt-size groups. Suppose a benchmark uses only the shortest group. Use Phase 2 section 2.4 to explain why the server then looks better than it is.
4. Find the NVIDIA driver version on any GPU machine you can reach, or on a provider's spec page. Then use section 4.2 to decide which of the two engines you could run today without an upgrade.

---

## ✅ Checkpoint 4A — answer in your own words

1. Show the arithmetic. You rent one H100 at $3.49 per hour. Your model is 140 GB. The machine's measured downlink is 276 Mbps.
   (a) How long does the download take?
   (b) What does that download cost in GPU time?
   (c) You plan eight one-hour sessions this month. Compare downloading each time against a cached volume at $9.80 per month.
   (d) Name the cost of the volume that is not money.

2. A colleague says: "I benchmarked both engines on defaults. vLLM was faster, so we should use vLLM." Give three specific reasons why that result may mean nothing. Use sections 4.2 and 4.3. One reason is about batching defaults, one is about memory flags, and one is about the client.

3. This is broken. Your server refuses to start with a message about KV cache memory.
   (a) Name the two different vLLM messages this could be, and how you tell them apart.
   (b) For the second one, name the number in the message that tells you what to do.
   (c) State what the matching SGLang message asks you to do. Explain why the direction is the opposite of what the flag name suggests.

4. Walk through what happens. Your vLLM server has served plain chat for an hour. A new client sends its first structured-output request. Its schema uses `multipleOf` on a price field.
   (a) Trace what the engine does with that schema.
   (b) State what happens to every later structured-output request, and why.
   (c) Name the one-line change that would have turned this into an error. Say whether you would want that.

5. Design it. You have one hour of rented GPU. You want a defensible comparison of the two engines for your workload. Write the plan. Cover what you prepare before the clock starts, which client you use and why, which flags you pin, what traffic you replay, and the two numbers you take away.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) 276 Mbps is 34.5 MB/s. 140,000 MB / 34.5 = about 4,058 seconds, which is 67.6 minutes.
   (b) 67.6 minutes at $3.49 per hour is about $3.93. On that machine the download alone is longer than a one-hour rental.
   (c) On a fast link, each download costs roughly $0.34 to $1.09. Eight downloads cost $2.72 to $8.72. So at eight sessions the $9.80 volume is close to break-even, but still slightly more expensive. The volume becomes cheaper above about 9 to 29 downloads a month. On the slow machine above, eight downloads cost 8 × $3.93 = $31.44, so the volume is much cheaper.
   (d) A network volume ties your work to one datacentre. That reduces the GPUs you can get and removes failover options.

2. First, each engine chooses batching defaults from GPU memory and from server or offline mode. So the defaults differ before you type anything.
   Second, `--gpu-memory-utilization` and `--mem-fraction-static` count memory differently. Equal-looking values do not give equal KV cache.
   Third, each engine's own benchmark client is different. A fair test uses one client for both engines.
   A public benchmark was retracted because of a flag-mapping error. Another fell from a 2x gap to 8.6% when the request count was raised from 50 to 2,000.

3. (a) The first says there is no available memory for cache blocks at all. The weights used everything. The second says the model's maximum sequence length needs more KV cache than exists, and it prints both sizes.
   (b) The second message prints an estimated maximum model length. Set `--max-model-len` to that value, or use `--max-model-len auto`.
   (c) SGLang asks you to **raise** `--mem-fraction-static`. That flag is the share of memory reserved for the engine, not an upper limit on it. The two flag names look alike, but the fixes point in opposite directions.

4. (a) With the default `auto` backend, vLLM checks the schema against xgrammar. xgrammar does not support `multipleOf` on numbers, so vLLM falls back. It then checks whether the schema uses a feature that guidance does not support. It routes to guidance or to outlines based on the answer.
   (b) Every later structured-output request uses the same backend. vLLM chooses the backend once per engine, not per request, and the source says so. One client's schema has changed the server for every client.
   (c) Pin `--structured-outputs-config.backend xgrammar`. This removes the fallback and turns the request into an HTTP 400. In production you usually want this. A clear failure on one request is better than a silent change that affects all requests.

5. Before the clock starts, write both launch commands and the client command with the model id in it. Also note the driver check and the model size. If you will repeat the session, download to a cached volume.
   Use one client, `bench_client.py`, against both servers, because each engine's own harness is different.
   Pin `--max-model-len` and `--context-length` to the same value. Pin the batched-token and concurrent-sequence flags on both sides, using the mapping table. Do not accept two different sets of defaults.
   Replay the mixed-size trace instead of one prompt. Prefill cost grows with prompt length, and real traffic has a spread of lengths.
   Take away the peak output tokens per second and the TTFT p99 at that concurrency. Those two numbers are the operating point. The first one feeds the cost arithmetic.

</details>

---

## References & Further Learning

Every URL was fetched and checked on 2026-09-13. Every flag and default was checked against the engine source at its release tag, not against documentation text. This matters more here than anywhere else in the course. On several points the documentation and the source disagree. When they disagree, trust the source.

### Must-read before you rent

- **vLLM quickstart, pinned to the release** — https://docs.vllm.ai/en/v0.29.0/getting_started/quickstart/
  Keep the version in the URL. The `latest` docs describe an unreleased developer preview and show no version number. A flag you read there may not exist in the version you install. On your first pass, read only the serve command.

- **vLLM serve CLI reference** — https://docs.vllm.ai/en/v0.29.0/cli/serve/
  Use it as a lookup while the server runs. Two defaults are worth knowing: `--gpu-memory-utilization` is 0.92, and `--enable-chunked-prefill` is on. The batching defaults are not on this page. vLLM chooses them at startup from GPU memory and from server or offline mode.

- **SGLang server arguments** — https://docs.sglang.io/docs/advanced_features/server_arguments
  Read it next to the flag map in section 4.2. Note one gap. The page does not say that `--grammar-backend` defaults to xgrammar. That default is set in the code.

- **Fast LLM Serving with vLLM and PagedAttention**, Woosuk Kwon and Zhuohan Li, 32 minutes — https://www.youtube.com/watch?v=5ZlavKF_98U
  The authors derive PagedAttention from the problem it solves. Phase 2 cited this talk for the mechanism. Watch it before your first deployment, so the memory flags make sense.
  Timestamps come from the caption track, because the video has no chapters. 2:55 what the KV cache is. 5:00 the three kinds of memory waste, with the 20 to 40 percent utilisation figure. 6:56 PagedAttention. 8:53 the block table. 11:26 sharing and copy-on-write. 18:49 the results.
  Focus on 5:00 to 11:00. Skip 19:00 onward, which is 2023 adoption history and out of date.

### Deep dives

- **vLLM Office Hours: Intro to vLLM V1**, Michael Goin, 59 minutes — https://www.youtube.com/watch?v=jmzIvQZCLZM
  This is the most detailed public explanation of why the current scheduler exists. Watch it after you have run a server once. It explains why the flags have their current shape.
  Timestamps from captions. 20:14 why they changed the architecture. 27:58 the scheduler now counts only the tokens for the next forward pass. 29:30 a chunked prefill walkthrough against a token budget. 33:28 piecewise CUDA graphs. 42:45 features they removed on purpose. Focus on 27:58 to 32:30.

- **Efficient LLM Inference with SGLang**, Lianmin Zheng, 24 minutes — https://www.youtube.com/watch?v=Ny4xxErgFgQ
  This is the only talk that explains grammar-constrained decoding step by step. That is why it belongs next to the structured-output part of section 4.2.
  Timestamps from captions. 4:29 SGLang's page size of one token, against 16 or 32 in the other engine. 9:55 RadixAttention. 10:51 building the radix tree across a session. 12:19 recursive eviction. 14:41 constrained decoding with a live demo. 15:55 the path from schema to regex to state machine to token mask. 16:59 jump-forward decoding. Focus on 9:55 to 17:00.

- **State of vLLM 2025**, Simon Mo, 31 minutes — https://www.youtube.com/watch?v=tN_-nktp1Hk
  Watch one moment, at 12:39. He explains clearly why serving is hard. Prefix caching, speculative decoding, chunked prefill, and structured output all change the same scheduler. That fact explains most of the interactions in Phases 2 and 4.

- **Introduction to LLM serving with SGLang**, Yineng Zhang, 43 minutes — https://www.youtube.com/watch?v=Ahtaha9fEM0
  This is the only hands-on talk in this list. It has real chapters, so these timestamps do not come from captions. Use 6:49 to 30:02 while you start a server.

### Benchmarking

- **vLLM benchmark CLI** — https://docs.vllm.ai/en/v0.29.0/benchmarking/cli/
  It lists the commands and the exact metric labels they print. Its `--dataset-name timed_trace` mode replays a JSONL trace with each request's own timestamp. That is closer to production than a fixed arrival rate. You can configure the trace field names.

- **SGLang serving benchmark**, the module `python -m sglang.benchmark.serving`
  Note the module path. `sglang.bench_serving` is now a deprecated wrapper that prints a warning. Every documentation page checked still teaches the old path. Its trace replay mode is `--dataset-name mooncake` with `--use-trace-timestamps`.

- **MLPerf Inference v5.1, Krai submission** — https://github.com/mlcommons/inference_results_v5.1/tree/main/open/Krai
  This is the only audited comparison of the two engines on the same hardware and the same model. Focus on the four throughput rows, and on the fact that the winner changes with the quantization path.
  The systems JSON gives the conditions: eight H200 GPUs, one CUDA version and driver for both, Llama-3.1-70B in FP8, 24,576 samples, and stated latency limits. The submitter tuned each engine separately, so this is not an untuned baseline.
  Its limits: the engine versions are from mid-2025, roughly twenty vLLM releases before the current one. No audited comparison of today's versions exists.

- **InferenceX** — https://github.com/SemiAnalysisAI/InferenceX
  This is the best live source that still compares the engines. It uses one neutral load generator, forked from vLLM's own. Read the configs, not the dashboard. Three caveats:
  - Vendors supply the hardware and submit the configurations.
  - Engine versions are often nightly images pinned by commit, not release tags.
  - Release-tag coverage is not the same for the two engines.

### Do not cite these

- People often repeat a "3.1x faster" figure. It comes from a July 2024 post by one of the two engine teams. The post tested a 2024 version of the other engine, with a flag that turned off that engine's prefix caching.
- Two often-quoted MLPerf v5.0 throughput numbers compare the two engines on **different models**. They are wrong, not only out of date.
- Both projects have stopped publishing head-to-head numbers. One removed its cross-engine benchmark path because nobody maintained it. Before you believe any current head-to-head claim, ask for its versions and flags.

### GPU rental

Read your provider's own pricing page on the day you rent, and write the date next to the number. The prices in section 4.1 were read on 2026-09-13 from the providers' public pages. One marketplace's pricing page shows no figures at all, so its prices were read through its public offers API.

Look up three things instead of assuming them: the billing step, whether an idle instance is billed, and the storage rate while an instance is stopped. One provider bills per minute and charges while idle. One doubles the volume rate when you stop the pod.

- **Hugging Face download tooling** — https://huggingface.co/docs/huggingface_hub/en/guides/download
  Read one paragraph. `HF_HUB_ENABLE_HF_TRANSFER` is deprecated. The replacement is `hf_xet`, with `HF_XET_HIGH_PERFORMANCE=1` on a fast machine. Many tutorials still teach the deprecated variable. Two more useful commands: `hf download --dry-run` prints the byte count before you start, and `hf-mount` fetches only the bytes your code reads.

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
  140GB download: 4.7 min at 500 MB/s ... 67.6 min ($3.93) at 276 Mbps
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
  THE FLAG TO USE FIRST: --max-model-len auto   (searches for what fits)

DEFAULTS ARE NOT FIXED
  vLLM batching depends on GPU memory AND serve-vs-offline:
    <70 GiB or any A100 -> 2048 / 256    70-160 GiB -> 8192 / 1024
    >=160 GiB -> 16384 / 1024
  SGLang auto-tunes chunked prefill by GPU memory; fraction falls back to 0.88
  PIN THEM EXPLICITLY before comparing anything

WHEN IT WILL NOT START
  "max_model_len ... is greater than the derived" -> above the model's limit
                                  (Qwen3-8B max_position_embeddings = 40960)
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

Part B uses the throughput number you measured here for three decisions. Should you quantize? Should you use speculative decoding? Should you self-host at all?
