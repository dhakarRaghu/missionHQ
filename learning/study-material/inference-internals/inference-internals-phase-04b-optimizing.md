# Phase 4B — Making it faster, and deciding whether to do it at all

Part A started a server and measured it. This part covers two ways to change those numbers. Then it covers the decision that the whole phase exists to answer.

The two methods behave very differently:

- **Quantization changes your model.** It changes the weights, so it can change your outputs. It needs an evaluation gate.
- **Speculative decoding does not change your output distribution.** It needs no gate. It needs a check that it still helps at your traffic level.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  4.4  Quantization             — what it buys, and what it quietly costs │
│  4.5  Speculative decoding     — a bet with published odds               │
│  4.6  The self-host decision   — arithmetic, not preference              │
└──────────────────────────────────────────────────────────────────────────┘
```

Part A is a prerequisite. Section 4.6 needs the throughput number you measured there.

Time: 2 to 3 hours. Five of the seven exercises are offline. Budget about $2 to $3 of rented GPU for the other two.

---

## 4.4 — Quantization (what it buys, and what it quietly costs)

Why this matters: quantization changes the cost table from section 4.1 more than any other setting. It cuts the memory a model needs by half or more. That raises the concurrency that Phase 2 taught you to watch. It also changes your model's weights. So it is a model change, and Phase 3B's rule applies: it needs a gate.

**The short version.** Quantization stores weights, and sometimes activations, in fewer bits. Fewer bits means fewer bytes to read from GPU memory at each decode step. Phase 1 showed that decode speed is limited by memory reads. So quantization usually makes the model faster as well as smaller.

### The formats that matter

```
┌──────────┬──────────────────────┬────────────┬───────────────────────────┐
│ format   │ what it quantizes    │ memory     │ hardware it needs         │
├──────────┼──────────────────────┼────────────┼───────────────────────────┤
│ FP8      │ weights + activations│ 2x smaller │ Ada, Hopper, Blackwell,   │
│ W8A8     │                      │            │ and AMD                   │
│ INT8     │ weights + activations│ ~2x        │ Turing onward, plus CPU   │
│ W8A8     │                      │            │                           │
│ AWQ      │ weights only         │ ~75% off   │ Turing to Hopper, Intel   │
│ W4A16    │                      │ the weights│ GPU, x86 CPU. NOT AMD GPU │
│ GPTQ     │ weights only         │ ~75% off   │ Volta onward              │
│ W4A16    │                      │ the weights│                           │
│ NVFP4    │ weights, sometimes   │ 3.5x vs    │ Blackwell only            │
│          │ activations too      │ FP16       │                           │
│ MXFP4    │ MoE expert weights   │ 4.25 bits  │ Blackwell, AMD ROCm,      │
│          │                      │ per param  │ Hopper through Triton     │
└──────────┴──────────────────────┴────────────┴───────────────────────────┘
```

W8A8 means 8-bit weights and 8-bit activations. W4A16 means 4-bit weights and 16-bit activations.

Two things changed since older material was written. Both were checked in the engines' source on 2026-09-13.

**AutoAWQ is deprecated.** vLLM's own page says the feature moved into `llm-compressor`. AWQ checkpoints still load, but the AutoAWQ tool is no longer maintained. Any guide that tells you to run AutoAWQ is out of date.

**The 4-bit formats are now NVFP4 and MXFP4, not INT4.** MXFP4 arrived as a released weight format, not as a step you run yourself. The gpt-oss models were released with their expert weights already in MXFP4.

### You probably will not quantize anything yourself

This surprises people who expect a conversion step. In 2026, you usually download a checkpoint that someone else already quantized. One vendor organisation alone publishes 773 such models. New ones appear within days of a base model release.

**`--quantization` is for ONLINE quantization, while the model loads.** For an already quantized checkpoint, both engines read the method from its config. You do not pass the flag. SGLang's documentation says so directly.

So the usual decision is "which published checkpoint", not "which algorithm".

**Prefer a checkpoint with a published accuracy table and the command that produced it.** A checkpoint with no published recovery numbers is unevaluated, whoever uploaded it.

### What it costs in quality: two studies that appear to disagree

**The optimistic result.** A 2024 study, revised in May 2026, ran over 500,000 evaluations across the whole Llama-3.1 family. Recovery is the quantized model's accuracy as a percentage of the BF16 original's accuracy:

```
                        8B       70B      405B
  W8A8-FP  (OpenLLM v1)  99.3%    99.7%   100.1%
  W4A16    (OpenLLM v1)  98.7%    99.5%   100.0%
  W8A8-FP  (OpenLLM v2) 101.2%   100.0%    99.9%
  W4A16    (OpenLLM v2)  96.1%    97.4%    98.9%   ← read this row
```

Take two things from this table:

1. FP8 is close to lossless at every size.
2. 4-bit recovery improves with model size, from 96.1% to 97.4% to 98.9%. This happens only on the harder benchmark suite, v2. On the easier suite, every cell is 98.7% or higher, and the size effect disappears.

**The pessimistic result.** A study by a different group used human evaluation as well as automatic benchmarks, on the same quantized checkpoints. Its central finding, quoted:

> automatic evaluations estimate performance deterioration relative to FP16 across tasks at −0.3% (French) and −1.7% (Japanese) vs −16.6% and −16.0% reported by human evaluators.

For Japanese, automatic metrics said 1.7% worse. Human raters said 16.0% worse. It was the same model.

**The two studies do not contradict each other.** The first measures mostly English multiple-choice benchmarks. The second measures open-ended text in several languages, scored by people. **So one checkpoint can recover 99% on a multiple-choice suite and be 16% worse to a human reader.**

Here is where the damage concentrates, ranked by the measured evidence:

1. **Maths and multi-step reasoning.** On a multilingual maths benchmark at 4-bit, one 35B model lost 13.1% on average. It lost 17.3% in Chinese.
2. **Non-Latin scripts.** On the same model, Latin-script tasks lost 0.7% and non-Latin tasks lost 1.9%.
3. **Long context.** See the KV cache section below, and the RULER result further down.
4. General knowledge. The standard suites test this, and the drop here is smallest.

### What it buys in speed, and the split nobody explains

Which step gets faster depends on what you quantized.

```
  WEIGHT-ONLY (W4A16)              WEIGHT AND ACTIVATION (W8A8)
  fewer weight BYTES to move       fewer bytes AND real low-precision
  helps the memory-bound part      matrix multiply
       ↓                                ↓
  DECODE gets faster               DECODE and PREFILL get faster
       ↓                                ↓
  wins at LOW concurrency          wins under LOAD
  (one user waiting on tokens)     (a busy server)
```

The same paper measured this in its serving benchmarks, Tables 5 and 6. Each figure below is for one use case:

- One user, 70B, code completion: BF16 on two A100s took 50.7 seconds. W4A16 on one A100 took 35.0 seconds. That is 1.45x faster.
- Continuous batching, 70B on four A100s, code completion: BF16 served 1.4 queries per second and INT8 W8A8 served 2.4. That is 1.71x. The table's speedup column gives 1.87x for that row.
- Under load, 405B on 16 H100s, docstring generation: FP8 W8A8 raised throughput from 6.1 to 9.6 queries per second. That is 1.57x. The table's speedup column gives 3.04x for that row.

**The practical rule:**

- Low traffic, and latency matters: 4-bit weight-only gives you lower latency.
- High traffic: 8-bit weights and activations give you more throughput.
- Batch size one with short outputs: quantization mostly saves memory, and little else.

### KV cache quantization is a separate decision with a threshold

Phase 2 showed that the KV cache uses most GPU memory at high concurrency. You can quantize it too, with `--kv-cache-dtype fp8` on both engines. This halves the KV storage.

It also has a break-even context length. Below that length, **it makes the server slower**. The vLLM maintainers measured this on an H100 at concurrency 1:

```
┌──────────────────────────┬───────────────────┬──────────────────────┐
│ model                    │ FP8 decode cost   │ break-even context   │
├──────────────────────────┼───────────────────┼──────────────────────┤
│ Llama-3.1-8B             │ 54% of BF16       │ about 7,000 tokens   │
│ gpt-oss-20b              │ 80% of BF16       │ about 22,000 tokens  │
│ gpt-oss-20b, skipping    │ 71% of BF16       │ about 7,700 tokens   │
│ sliding-window layers    │                   │                      │
│ Gemma-4-E2B, head_dim 256│ 68% of BF16       │ TTFT gets 1.6x WORSE │
└──────────────────────────┴───────────────────┴──────────────────────┘
```

Under load, with about 20,000 input tokens, the same 8B model went from 450 to 518 output tokens per second. That is about a 15% gain. Median inter-token latency fell 14.8%.

**The same source gives three warnings. They matter more than the speedup.**

1. Do not turn it on below about 7,000 tokens of context. The fixed extra work makes BF16 faster there.
2. One model shape gets worse, not better. A head size of 256 with prefill-heavy traffic caused a 1.6x TTFT regression.
3. A precision bug in attention accumulation once dropped a 128,000-token retrieval task from **91% accuracy to 13%**. Short-context tests could not show it. The bug is fixed. It shows why a short-context eval cannot approve a long-context deployment.

One more fact makes most published KV cache benchmarks out of date. Between two engine versions, the break-even for that 8B model moved from 24,889 tokens down to 7,010. **Do not trust a KV cache benchmark that is more than about a year old.**

### The failure mode that an accuracy gate cannot see

A 2026 study quantized reasoning models. It measured their output length as well as their accuracy. On a maths benchmark, one 1.5B reasoning model changed like this:

```
  BF16       85.6% accuracy    5,200 tokens of reasoning
  AWQ 3-bit  47.0% accuracy   23,400 tokens of reasoning   ← 4.5x longer
```

Accuracy almost halved. The model also used 4.5 times as many output tokens. **You saved memory, but you pay more in decode time and in output-token cost.**

The study found a specific cause:

- In up to 52% of failures under strong quantization, the model reached the correct answer in a middle step. Then it did not commit to that answer.
- At uncertain token positions, the quantized model produces too many hedging words, such as words that express doubt.
- A simple penalty on those words cut reasoning length by 12% to 23%, with no loss of accuracy.

Conditions: 3-bit on a 1.5B model is the most aggressive end, unlike 4-bit on a 70B. The lesson still applies. **If you serve a reasoning model, put output length in your gate, not only accuracy.** No standard benchmark reports it.

A second effect has weaker evidence. One small study of tool calling found that model family predicted quantization tolerance better than parameter count. Easy benchmark levels also hid a sharp drop. On parallel and multi-tool calls, the drop in schema validity was about five times larger than on simple calls. That study used small models and a different quantization family, so do not transfer the sizes. Do test the hardest version of what your agents do.

### The gate

Phase 3B taught you to gate model changes. Here is the version for quantization. `quant_gate.py` implements it.

```bash
python phase04_serving/quant_gate.py --self-test
python phase04_serving/quant_gate.py \
    --baseline-url http://localhost:8000/v1  --baseline-model <fp16-id> \
    --candidate-url http://localhost:8001/v1 --candidate-model <fp8-id> \
    --max-drop 0.02
```

It sends one labelled set to both endpoints and reports both accuracies and throughputs. It computes the accuracy difference with a 95% interval, using paired bootstrap resampling. That method redraws the items at random, many times, to estimate the noise. It decides SHIP or HOLD from the **worst end** of the interval, not the middle.

**Why the interval is required.** Look at three published quantization results:

- A 4-bit model scored **higher** than its baseline on an AIME benchmark.
- An FP8 model scored 100.8% recovery on a maths benchmark.
- A quantized coding model scored 0.933 against the original's 0.930, on a 164-problem benchmark. That difference is about half a problem.

None of these is a real improvement. They are measurement noise. A gate without a tolerance band reports them as wins, or reports false regressions.

**What a published gate looks like.** One vendor's model card ships the recipe, both scores, and the recovery percentage. It also ships the command that reproduces them. Its numbers show where to aim:

```
  general suite, 4k context      99.59% recovery
  harder suite, 4k context       99.54% recovery
  multimodal                    100.0%  recovery
  long-context suite at 131k     98.16% recovery   ← the lowest row
```

The long-context row is the lowest, and no general suite tests it. The KV cache work above found the same.

**A combined gate, built from those sources.** Require all four:

1. 99% or better recovery on a general suite
2. 98% or better on a suite built from your own task
3. **a long-context evaluation at your real maximum context**
4. a throughput run that proves the speed gain you expected

These thresholds are this course's own. No single source publishes them as policy.

**The sentence to remember:** quantization is a model change, and standard benchmarks under-report its quality cost. Gate it on your own task, at your real context length, with an interval.

**The trap:** you trust a 99% recovery score from a multiple-choice benchmark. It says almost nothing about open-ended text, long context, or reasoning length. Human raters found 16% degradation where automatic metrics found 1.7%.

**Try this now:** run `python phase04_serving/quant_gate.py --self-test` and find the check "a single flip is inside the noise". Then work out what accuracy difference your own eval set can detect, given its size. E11 shows the answer for 20 items.

---

## 4.5 — Speculative decoding (a bet with published odds)

Why this matters: Phase 1 showed that decode speed is limited by memory reads. Each step reads the whole model from GPU memory to produce one token. The arithmetic in the step is cheap by comparison. Speculative decoding uses this fact. If arithmetic costs little, do more of it for each memory read.

**How it works.**

1. A cheap draft proposes k tokens.
2. The target model checks all k tokens in **one** forward pass. That pass costs about the same as generating one token normally.
3. The target keeps every draft token it agrees with, up to the first disagreement.
4. At the first disagreement, the target's own token replaces the rest.

```
  NORMAL DECODE                     SPECULATIVE DECODE (example)
  step 1: read weights → 1 token    draft:  cheap, proposes 4 tokens
  step 2: read weights → 1 token    verify: ONE target pass over all 4
  step 3: read weights → 1 token            3 accepted, 1 rejected
  step 4: read weights → 1 token            + 1 free token from the target
  ────────────────────────────      ────────────────────────────────────
  4 weight reads, 4 tokens          1 weight read, 4 tokens
```

**This guarantee makes it safe.** The original paper proves that the accepted tokens are "distributed identically to those sampled from the target alone". So you can turn it on without running your evaluation suite again. No other optimisation in this phase has that property.

### The published formula, which is also the whole decision

The same paper gives the expected speedup exactly:

```
                     1 - alpha^(k+1)
  improvement =  ───────────────────────
                  (1 - alpha) (k*c + 1)

  alpha  per-position acceptance probability
  k      draft length
  c      cost of one draft step, as a fraction of one target step
```

As k grows, the numerator stops growing. The denominator keeps growing in a straight line. So there is a best k. The best k gets smaller when acceptance falls or when the draft costs more.

`specdec_math.py` computes this formula. Run it:

```bash
python phase04_serving/specdec_math.py
```

Output, run on 2026-09-17 with the default draft cost of 0.10:

```
┌───────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┐
│ alpha │ k=1   │ k=2   │ k=3   │ k=4   │ k=5   │ k=6   │ k=7   │ k=8   │
├───────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┤
│  0.30 │  1.18 │  1.16 │  1.09 │  1.02 │  0.95 │  0.89 │  0.84 │  0.79 │
│  0.50 │  1.36 │  1.46 │  1.44 │  1.38 │  1.31 │  1.24 │  1.17 │  1.11 │
│  0.60 │  1.45 │  1.63 │  1.67 │  1.65 │  1.59 │  1.52 │  1.45 │  1.37 │
│  0.70 │  1.55 │  1.82 │  1.95 │  1.98 │  1.96 │  1.91 │  1.85 │  1.78 │
│  0.80 │  1.64 │  2.03 │  2.27 │  2.40 │  2.46 │  2.47 │  2.45 │  2.40 │
│  0.90 │  1.73 │  2.26 │  2.65 │  2.93 │  3.12 │  3.26 │  3.35 │  3.40 │
└───────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┘
```

Read the 0.30 row. At a 30% acceptance rate, a draft of five tokens is **slower** than no speculation at all. Acceptance rate matters more than any other input.

### The number your server reports is not the number in the formula

vLLM reports a metric called `draft_acceptance_rate`. It is the fraction of **all drafted tokens** that the target accepted, averaged across positions. The formula's `alpha` is the probability that **one** position is accepted. These are different quantities. This identity links them:

```
  mean_acceptance_length = 1 + k * draft_acceptance_rate
```

Here is why this matters. Red Hat published measurements on a real workload: an H200 serving a 120B model with a trained draft head.

```
┌───┬──────────────┬───────────────┬───────────────┬─────────────┐
│ k │ server rate  │ length, theirs│ length, 1+k*r │ true alpha  │
├───┼──────────────┼───────────────┼───────────────┼─────────────┤
│ 2 │       0.454  │          1.91 │         1.908 │       0.577 │
│ 3 │       0.356  │          2.07 │         2.068 │       0.567 │
│ 4 │       0.283  │          2.13 │         2.132 │       0.555 │
└───┴──────────────┴───────────────┴───────────────┴─────────────┘
```

Columns 3 and 4 agree to two decimals, which is all the precision column 3 has. This confirms the identity on real data.

Now read the last column. As k rises, the reported rate falls from 0.454 to 0.283. It looks as if the draft model gets worse. **It does not.** The true per-position acceptance stays roughly flat, between 0.555 and 0.577. The reported rate falls only because it averages over more positions. Each later position is less likely to be accepted than the one before it.

Reproduce this yourself:

```bash
python phase04_serving/specdec_math.py --from-server
```

**What this means in practice:** choose k with the converted alpha. Run on 2026-09-17, default draft cost 0.10, key output line only:

```bash
# WRONG: feed the server's k=4 rate straight into the formula
python phase04_serving/specdec_math.py --best-k --alpha 0.283
# best draft length k = 1, expected speedup 1.17x

# RIGHT: convert it to the per-position alpha first, then choose k
python phase04_serving/specdec_math.py --best-k --alpha 0.555
# best draft length k = 3, expected speedup 1.56x
```

The wrong input also shows k=4 as a loss, at 0.99x. So you would cut k to 1 and lose most of the gain. This conversion is my own derivation from the published numbers, not a quoted result. Check it against your own server's metrics.

### The four methods, and what each costs to set up

```
┌──────────────────┬──────────────┬───────────────────┬────────────────────┐
│ method           │ setup cost   │ measured speedup  │ conditions         │
├──────────────────┼──────────────┼───────────────────┼────────────────────┤
│ n-gram / prompt  │ one config   │ 2.4x average;     │ summarisation and  │
│ lookup           │ line. No     │ 2.8x measured in  │ context QA, where  │
│                  │ model, no    │ vLLM              │ the answer copies  │
│                  │ training     │                   │ from the prompt    │
│ separate draft   │ zero if a    │ 1.5x              │ 70B target at one  │
│ model            │ small sibling│                   │ request per second │
│                  │ exists       │                   │                    │
│ Medusa heads     │ about 5 hours│ 2.2x to 3.6x      │ batch size 1, the  │
│                  │ on one A100  │                   │ paper says so      │
│ EAGLE-3          │ a training   │ up to 6.5x in the │ batch size 1, lab. │
│                  │ run, 1-2 days│ paper; 1.38x      │ Note the gap       │
│                  │ on 8 GPUs    │ throughput at     │ between those two  │
│                  │              │ batch 64          │ numbers            │
└──────────────────┴──────────────┴───────────────────┴────────────────────┘
```

**Start with n-gram.** An n-gram draft looks up the next tokens in text the model has already seen. It needs no model, no extra memory, and no training. On the workloads where it fits, it beats a draft model. It fits when the output copies from the input: summaries, retrieval answers, code edits, and agent loops that repeat context. It does nothing on the first turn of a new chat, because there is nothing to copy yet.

Suffix decoding, a newer method, also looks up sequences from earlier outputs. It reports up to 5.3x on agent workloads, and current vLLM supports it.

### When it makes things worse

The method depends on memory reads being the slowest part of decode. Under load, arithmetic becomes the slowest part. The extra verification tokens then cost real time, and you can gain nothing.

**The engine maintainers measured this, on the same hardware and models as their own speedups:**

> at high QPS, 1.4x slowdown on Llama3-70B on ShareGPT with 4xH100, 1.8x slowdown on Llama3-70B on CNN DailyMail with 4xH100

The configuration that gained 1.5x at one request per second lost 1.4x under load. Only the load changed.

**The EAGLE-3 paper's own table shows a crossover.** Throughput is relative to no speculation:

```
  batch size:    2      4      8     16     24     32     48     56
  EAGLE:      1.30x  1.25x  1.21x  1.10x  1.03x  0.93x  0.82x  0.71x
  EAGLE-3:    1.75x  1.68x  1.58x  1.49x  1.42x  1.36x  1.21x  1.01x
                                            ↑ EAGLE turns into a loss here
```

EAGLE falls below 1.00x between batch 24 and 32. The newer method stays above 1.00x up to batch 56.

**The engine ships a feature for exactly this.** vLLM lets you set the draft length by concurrency. Its own example configuration turns speculation **off completely** above 128 concurrent requests. The third row starts at 129:

```json
"num_speculative_tokens_per_batch_size": [
  [1, 64, 3],
  [65, 128, 1],
  [129, 512, 0]
]
```

That third row is the whole lesson, written as configuration.

Reproduce the shape yourself:

```bash
python phase04_serving/specdec_math.py --sweep-batch
```

Output, run on 2026-09-17, with acceptance rate 0.70 and draft cost 0.10:

```
┌──────────────────┬──────────────────────┬─────────┬──────────────┐
│ verify overhead  │ roughly corresponds  │ best k  │ best speedup │
│ per extra token  │ to                   │         │              │
├──────────────────┼──────────────────────┼─────────┼──────────────┤
│           0.00   │ batch 1, idle        │       4 │       1.98x  │
│           0.05   │ light load           │       3 │       1.75x  │
│           0.15   │ moderate load        │       2 │       1.46x  │
│           0.30   │ heavy load           │       2 │       1.22x  │
│           0.50   │ saturated            │       1 │       1.06x  │
│           0.80   │ saturated, big batch │       1 │       0.89x  │   <- a LOSS
└──────────────────┴──────────────────────┴─────────┴──────────────┘
```

The verify overhead is a stand-in for load. The labels in the second column are the script's rough guide, not measurements.

### The exception that keeps it useful

"A high batch size makes it useless" is the wrong rule. The right question is: **is the target model's step still limited by memory reads?**

Long-context models and mixture-of-experts models stay limited by memory reads for much longer. With a large KV cache, reading it takes most of the step. Published work reports 2.51x at batch sizes between 32 and 256 on long sequences. It also reports about 2.0x at 32,000 tokens of context at batch 32. The 120B measurement above kept its gains up to 200 concurrent requests.

So the decision depends on the workload, not on batch size alone. Measure it.

**The sentence to remember:** speculative decoding is the only optimisation here that provably cannot change your output. It is also the only one whose benefit can turn negative only because your traffic went up.

**The trap:** you benchmark it at batch size 1, ship it, and never measure again. Every headline speedup in the literature is a batch-size-1 number, unless it says otherwise.

**Try this now:** run `python phase04_serving/specdec_math.py --best-k --alpha 0.3 --draft-cost 0.2`. Expected: `best draft length k = 1, expected speedup 1.08x`. Then lower `--alpha` until the speedup reaches 1.00x. Expected: at 0.20 it prints 1.00x and the line "About 1.0x. No gain, only added complexity. Leave it off."

---

## 4.6 — The self-host decision (arithmetic, not preference)

Why this matters: a senior engineer gets asked this question. It often comes in a meeting, from someone who already decided.

**The decision has four inputs. Only one of them is the GPU price.**

```
  1. the hourly rate you pay          ← the number everyone argues about
  2. output tokens per second you     ← the number that decides it
     actually sustain
  3. your UTILISATION                 ← the number everyone forgets
  4. the API price you compare to     ← changes the answer completely
```

Utilisation is the share of paid hours that serve real traffic. Input 3 has the largest effect. A rented GPU bills every hour, whether requests arrive or not. At 10% utilisation, your cost per token is ten times the cost at full load. The hardware is the same.

### Run it

```bash
python phase04_serving/gpu_economics.py --gpu-hourly 3.49 --tps 1200 --role cheap
```

Output, run on 2026-09-17. The inputs are one H100 at $3.49 per hour, the RunPod Secure rate from section 4.1. The server sustains 1,200 output tokens per second. The comparison is a cheap API model at $1.60 per million output tokens.

```
┌──────────────┬────────────────────┬──────────────┬──────────────────┐
│ utilisation  │ output tokens/month│ $ per Mtok   │ vs the API       │
├──────────────┼────────────────────┼──────────────┼──────────────────┤
│         5%   │              158 M │ $   16.1574 │ 10.10x  more     │
│        10%   │              315 M │ $    8.0787 │ 5.05x  more      │
│        20%   │              631 M │ $    4.0394 │ 2.52x  more      │
│        35%   │            1,104 M │ $    2.3082 │ 1.44x  more      │
│        50%   │            1,577 M │ $    1.6157 │ 1.01x  more      │
│        75%   │            2,365 M │ $    1.0772 │ 0.67x  CHEAPER   │
│       100%   │            3,154 M │ $    0.8079 │ 0.50x  CHEAPER   │
└──────────────┴────────────────────┴──────────────┴──────────────────┘

break-even utilisation: 50.5%. Above that the hardware is cheaper per token than the API.
```

Then this line usually decides the discussion:

```
break-even volume, including the engineer: 3,936 million output tokens per month.
this fleet's ceiling at 100% utilisation: 3,154 million output tokens per month.
The break-even volume is ABOVE what this fleet can serve.
```

**Against a cheap API model, this GPU can never pay for itself** once you include a quarter of an engineer. The fleet's maximum output is below its break-even volume. Tuning cannot fix this, because it is a result of the arithmetic, not of efficiency.

Now change one input, the API you compare against:

```bash
python phase04_serving/gpu_economics.py --gpu-hourly 3.49 --tps 1200 --role deep
```

The deep role is a model at $8.00 per million output tokens. Break-even utilisation drops from 50.5% to 10.1%. Including the engineer, break-even volume is 787 million tokens a month. The script says that is roughly 25% of this fleet's capacity. So against a frontier-priced model, the same hardware pays for itself at a small part of its capacity.

**So "should we self-host" starts with a question. Which API are you replacing?** At these numbers, replacing the cheap model does not pay. Replacing the frontier model can pay.

### The engineer line

The script includes a quarter of one engineer at $180,000 a year, which is $3,750 a month. On this one-GPU fleet, the hardware costs $2,548 a month. So the engineer costs about 1.5 times the hardware. At the script's default rate of $2.50 per hour, the hardware costs $1,825, so the engineer costs about twice the hardware.

Change these numbers to yours, but keep the line. A deployment needs an owner for upgrades, incidents, capacity, and the gate from 4.4. Proposals that leave this cost out are often regretted.

### What published break-even estimates say, and why they disagree

Three write-ups from 2026 reach different conclusions on similar hardware:

```
┌────────────────────────────┬───────────────────┬───────────────────────────┐
│ source                     │ assumed throughput│ conclusion                │
├────────────────────────────┼───────────────────┼───────────────────────────┤
│ a cost-tooling vendor      │ ~8,000 tok/s on   │ break-even at ~17% raw,   │
│                            │ one H100          │ 50-80% with ops overhead  │
│ a deployment platform      │ ~1,100 tok/s on   │ against a budget API tier,│
│                            │ one GPU           │ break-even is impossible  │
│ an independent site        │ 620 tok/s across  │ loses even at 100%        │
│                            │ 8 GPUs            │ utilisation, by 11x       │
└────────────────────────────┴───────────────────┴───────────────────────────┘
```

Their throughput assumptions differ by more than 7x. They use different models, batch sizes, and context lengths. **Do not average them, and do not cite any of them as your number.** Two of the three come from companies that sell a related product. None is peer reviewed.

They agree on one useful point. The break-even volume changes by a factor of about 100 depending only on which API you compare against.

### Measure your own throughput or the whole exercise is theatre

Every number above depends on `--tps`, and you cannot look it up. It depends on your model, quantization, context length, batch size, and engine. Run the E5 command from part A. Pass its peak output tokens per second to `--tps`. A vendor's figure came from a workload that is not yours.

### The reasons that are not about money

Cost is the easiest input to compute, and often the wrong reason to decide. Self-hosting also gives you:

- **Data control.** Nothing leaves your network. For some regulated workloads, this decides the question before anyone mentions cost.
- **A model you cannot rent.** A fine-tune, a merged model, or an open-weight model that no provider hosts.
- **Control of the latency floor.** No shared queue, no other tenants, and no provider incidents.
- **Stable prices.** Your cost per token no longer changes when a provider changes its price list.

It also has costs that the arithmetic does not show. You now own capacity planning, GPU supply, engine upgrades, security patches, and the on-call pager.

**The sentence to remember:** self-hosting is a bet on utilisation against one specific API price. Name the API and measure your own throughput before anyone argues about GPU rates.

**The trap:** you compare your GPU cost per token at 100% utilisation against an API's price. Nobody runs at 100%. Run the sweep and find your real utilisation.

**Try this now:** run `gpu_economics.py` twice, once with `--role cheap` and once with `--role deep`. Write down both break-even utilisations. With the inputs above, they are 50.5% and 10.1%. Bring that pair of numbers to the meeting.

---

## 🧪 Hands-on lab — part B

Five of these seven exercises are offline. E12 and E13 need a rented GPU. Together they cost about $2 to $3.

**Run status:** every offline command below was executed on 2026-09-13, and again on 2026-09-17. The printed outputs are from the 2026-09-17 run. No GPU was rented, so E12 and E13 are **UNVERIFIED on a rented GPU**. Their flags were checked against the engine source at the release tags.

- [ ] **E8 (offline).** Find where drafting stops paying.
  - Run: `python phase04_serving/specdec_math.py`
  - Expected: at an acceptance rate of 0.30, a draft length of 5 is already slower than no speculation, at 0.95x. At 0.90, the speedup keeps rising up to k=8, the last column, at 3.40x.
  - Write down the best draft length for each acceptance rate. The script prints them below the table: k=1, 2, 3, 4, 6, and 8 for alpha 0.30 to 0.90.
  - Teaches: in speculative decoding, the acceptance rate matters more than any other choice.

- [ ] **E9 (offline).** Convert your server's metric into the one the formula needs.
  - Run: `python phase04_serving/specdec_math.py --from-server`
  - Expected: columns 3 and 4 agree to two decimals. The reported acceptance rate falls from 0.454 to 0.283. The true per-position rate stays between 0.555 and 0.577. The last line reads `best k = 3, 1.59x at batch 1`, using the mean alpha of 0.566.
  - Teaches: if you tune by watching the reported rate fall, you choose a draft length that is too small.

- [ ] **E10 (break-it, offline).** Watch a 2x speedup become a loss.
  - Run: `python phase04_serving/specdec_math.py --sweep-batch`
  - Expected: the best speedup falls from 1.98x to 0.89x as the verify pass stops being free. The best draft length drops from 4 to 1.
  - Then find the verify overhead where the speedup crosses 1.00x. Run `python phase04_serving/specdec_math.py --best-k --alpha 0.7 --verify-overhead 0.6`, then try 0.65.
  - Expected: 1.00x at 0.60, and 0.97x at 0.65. So the crossover is at 0.60.
  - Teaches: an optimisation measured on an idle GPU can be a regression on a busy one.

- [ ] **E11 (offline).** Find out what your eval set can actually detect.
  - Run: `python phase04_serving/quant_gate.py --self-test`
  - Expected: seven checks pass, including "a single flip is inside the noise".
  - Then answer this. With 20 items, what is the smallest drop your gate can tell apart from zero? Compare it with the 2% `--max-drop` default.
  - Expected, from `bootstrap_ci` at `quant_gate.py:57` with its default seed. With 1, 2, or 3 regressed items out of 20, the interval includes zero. 4 regressed items, a 20% drop, is the smallest that excludes zero. Its interval is −40% to −5%.
  - A single regressed item gives a worst end of −15%. So does one item worse plus one item better. Both are below −2%, so the gate says HOLD.
  - Teaches: when the noise is wider than the threshold, the gate cannot tell noise from a regression. With 20 items, it holds on any single disagreement.

- [ ] **E12 (rented GPU, about $2, UNVERIFIED).** Gate a real quantization change.
  - Serve the unquantized model on port 8000. Serve a published quantized checkpoint of the same model on port 8001. Do not quantize it yourself. Download one whose publisher shipped an accuracy table.
  - Run: `python phase04_serving/quant_gate.py --baseline-url http://localhost:8000/v1 --baseline-model <fp16-id> --candidate-url http://localhost:8001/v1 --candidate-model <quant-id> --max-drop 0.02`
  - Expected: two accuracies, two throughputs, a difference with a 95% interval, and one word, SHIP or HOLD. Also a warning that 20 items is a directional result only. Note whether the interval contains zero.
  - Teaches: the gate is the deliverable, not the quantized model.

- [ ] **E13 (break-it, rented GPU, about $1, UNVERIFIED).** Make an optimisation slower on purpose.
  - Serve with `--kv-cache-dtype fp8`. Benchmark with **short** prompts, well under 7,000 tokens of context.
  - Run `bench_client.py` against this server, and against the same server without the flag.
  - Expected: at short context, the FP8 KV cache is slower or no faster. The published break-even for one 8B model on an H100 is about 7,000 tokens.
  - Then run a long-context trace and watch it reverse.
  - Teaches: below its threshold, an optimisation is a regression, and nothing warns you.

- [ ] **E14 (offline).** Answer the question you will actually be asked.
  - Run `python phase04_serving/gpu_economics.py --gpu-hourly <your rate> --tps <your E5 peak> --role cheap`. Then run it again with `--role deep`.
  - If you have no E5 number yet, use `--gpu-hourly 3.49 --tps 1200` as example values.
  - Expected with those example values: break-even utilisation of 50.5% against the cheap model and 10.1% against the deep model. Against the cheap model, the fleet cannot reach its own break-even volume at all.
  - Teaches: you answer "should we self-host" by naming the API you replace, and then doing arithmetic.

---

## 🔍 Check it yourself

1. Open `phase04_serving/specdec_math.py:87`. This is `alpha_from_length`. Its docstring names a property of `expected_tokens`. Use that property to explain why bisection always converges here. Then read line 96. State what the function returns when the measured length equals k+1, and what that means physically.
2. In the same file, open `speedup` at line 77. Line 83 adds the `verify_overhead` term. Set it to zero on paper, and show that the expression becomes the published theorem. Then explain in one sentence which physical fact makes that term non-zero in production.
3. Open `phase04_serving/quant_gate.py:57`. This is `bootstrap_ci`. It resamples pairs, not each side separately. Explain what that removes from the comparison, and why the interval gets tighter as a result.
4. In the same file, line 191 decides SHIP or HOLD. It uses `lo`, not the point estimate. Explain the failure that the point estimate would cause, and how often it would happen.

---

## ✅ Checkpoint 4B — answer in your own words

1. Show the arithmetic. Your draft model has a true per-position acceptance of 0.65. One draft step costs 12% of a target step.
   (a) Compute the expected tokens per verification at k=3.
   (b) Compute the speedup at k=3, at batch size 1.
   (c) Your server reports a `draft_acceptance_rate` of 0.40 at k=3. Is this consistent with your alpha? Show the arithmetic.
   (d) A colleague sees 0.40 and says "acceptance is poor, lower k to 2". Explain why that reasoning is wrong.

2. A colleague says: "We turned on speculative decoding and measured 2x in staging. We are shipping it." Give two specific reasons why production may be slower than staging. Use section 4.5. Then name the configuration feature that exists for this problem. Describe what its strongest setting does.

3. Show the arithmetic, then decide. You rent two GPUs at $2.79 per hour each. You measure 2,400 output tokens per second, sustained. Your monthly output volume is 900 million tokens. You would replace an API that charges $8.00 per million output tokens.
   (a) Compute the hardware cost per month.
   (b) Compute your utilisation at that volume.
   (c) Add a quarter of an engineer at $180,000 a year, and compare with the API bill.
   (d) Recompute (c) against an API that charges $1.60. Does the decision change?

4. This is broken. You quantized a reasoning model to 4-bit. Your evaluation suite shows accuracy within 1% of the baseline, so the gate passed. Two weeks later, your output-token bill is 40% higher.
   (a) Name the cause.
   (b) Explain why the gate did not catch it.
   (c) Name the metric you must add to the gate.
   (d) Give the published example that shows this effect, with its numbers.

5. Design it. You must present a self-host recommendation to your team. Write the structure. Cover the four inputs to the arithmetic, and which one you must measure. Cover the two break-even numbers you will show. Cover the reasons other than cost that could override the arithmetic. Cover the one line that most proposals leave out.

6. A colleague says: "The benchmarks show engine X is faster, so that settles it." Use the audited comparison in section 4.3. Give the specific reason why you cannot read a single winner from it. Then name two things that any engine benchmark must state before you believe it.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) (1 − 0.65⁴) / (1 − 0.65) = (1 − 0.1785) / 0.35 = 2.347 tokens.
   (b) Speedup = 2.347 / (1 + 3 × 0.12) = 2.347 / 1.36 = 1.73x.
   (c) Mean length = 1 + k × reported rate = 1 + 3 × 0.40 = 2.20. Solving for alpha from a length of 2.20 at k=3 gives about 0.61. `alpha_from_length(2.20, 3)` returns 0.607. An alpha of 0.65 would report (2.347 − 1) / 3 = 0.449. So 0.40 is close to your alpha, but it points to a slightly lower one.
   (d) The reported rate falls as k rises only because it averages over more positions. Each later position is less likely to be accepted. A low reported rate does not show that the draft got worse. Choose k from the formula, using the converted alpha.

2. First, staging is usually idle. There, memory reads limit the target model's step, so the extra verification tokens cost almost nothing. In production, arithmetic limits the step, and the extra tokens cost real time.
   Second, the workload may differ. A draft that matches well on summaries will not match well on translation. For translation, published guidance says the best draft length can be one, or even zero.
   The feature is vLLM's per-batch-size draft length. Its strongest setting maps a concurrency range to a draft length of zero. That turns speculative decoding off completely above that load.

3. (a) 2 × $2.79 × 730 hours = $4,073 per month.
   (b) Capacity at full load is 2,400 × 3,600 × 730 = 6,307 million tokens. So 900 million is about 14.3% utilisation.
   (c) The engineer costs $180,000 × 0.25 / 12 = $3,750, so the total is $7,823. The API bill is 900 × $8.00 = $7,200. The API is cheaper by about $623, even though the hardware alone looks cheap.
   (d) Against a $1.60 API, the bill is $1,440. Self-hosting now costs about $6,383 more. The decision does not change, because the API is cheaper in both cases. Only the gap grows. At $8.00, self-hosting would match the API at $7,823 / $8.00 = about 978 million tokens a month. At $1.60, you would need $7,823 / $1.60 = about 4,889 million. That is 78% of this fleet's 6,307 million capacity. `gpu_economics.py --gpus 2 --gpu-hourly 2.79 --tps 2400 --monthly-output-mtok 900` prints the same totals.

4. (a) After quantization, the reasoning model writes much longer chains of reasoning.
   (b) The gate measured only accuracy, and accuracy barely moved. No standard benchmark reports output length.
   (c) Mean output tokens per item, compared with the baseline, with a threshold.
   (d) A 1.5B reasoning model on a maths benchmark: BF16 scored 85.6% with 5,200 reasoning tokens. 3-bit AWQ scored 47.0% with 23,400 tokens. That setting is more aggressive than yours, but the cause is the same. In up to 52% of failures, the model found the right answer in a middle step. Then it did not commit to it.

5. The four inputs are the hourly rate, the sustained output tokens per second, the utilisation, and the API price you replace. You must measure throughput, because it depends on your model, quantization, context length, and batch size.
   Show two break-even numbers for each candidate API. The first is the utilisation where the hardware beats the API. The second is the monthly token volume where the total cost, including people, beats the API.
   The reasons other than cost are data control, a model nobody hosts, control of the latency floor, and stable prices.
   The line most proposals leave out is the engineer. In section 4.6, on one GPU at $3.49 per hour, the engineer costs about 1.5 times the hardware.

6. In that submission, the winner changes with the quantization path. SGLang led by 18 to 19% on the pre-quantized model. vLLM led by 2 to 12% with dynamic quantization, on the same machine and driver. A single winner means one chosen row.
   Before you believe any engine benchmark, ask for the engine release tags. Also ask for the exact flag values on both sides.

</details>

---

## References & Further Learning

Every URL was fetched and checked on 2026-09-13. Part A holds the references for serving, benchmarking, and GPU rental. This document holds the references for quantization, speculative decoding, and the economics.

### Quantization

- **vLLM quantization index** — https://docs.vllm.ai/en/latest/features/quantization/
  Read the hardware compatibility matrix, the only table of which format runs on which GPU. For exact flag spellings, use the engine source.

- **"Give Me BF16 or Give Me Death"? Accuracy-Performance Trade-Offs in LLM Quantization**, Kurtic, Marques, Pandit, Kurtz, Alistarh — https://arxiv.org/abs/2411.02355
  The accuracy baseline for section 4.4. Focus on the recovery tables, then on Tables 5 and 6 for serving speed. The serving figures come from vLLM 0.6.4 on A6000, A100, and H100 GPUs.

- **How Does Quantization Affect Multilingual LLMs?**, Marchisio et al., Cohere — https://arxiv.org/abs/2407.03211
  Read it right after the paper above, as the correction. It is the only study found that ran **human** evaluation next to automatic benchmarks on the same checkpoints. Focus on the human-evaluation and maths results.
  Honest note: the paper is from July 2024 and tested model families from that time. Treat it as the last check with human raters, not as a current measurement.

- **The State of FP8 KV-Cache and Attention Quantization in vLLM** — https://vllm.ai/blog/2026-04-22-fp8-kvcache
  The best single source on KV cache quantization, including a regression the team caused and fixed. Focus on the break-even table and the "when not to use it" list.

- **A published quantization gate** — https://huggingface.co/RedHatAI/Llama-4-Scout-17B-16E-Instruct-quantized.w4a16
  Read it as an example of a process, and copy its shape for your own gate. Its most useful row is the long-context suite at 131,000 tokens.

- **Quantized Reasoning Models Think They Need to Think Longer, but They Do Not**, Lotfi, Kirichenko, Li, Liu — https://arxiv.org/abs/2606.00206
  Focus on the tables of accuracy and length, and on the failure analysis. Its main example is 3-bit on a 1.5B model. Treat the cause as general and the sizes as not transferable.

### Speculative decoding

- **Fast Inference from Transformers via Speculative Decoding**, Leviathan, Kalman, Matias, ICML 2023 — https://arxiv.org/abs/2211.17192
  This paper defines the method and proves that it is safe. Read Section 2.3 for the sampling rule. Read Appendix A.1 for the proof that accepted tokens are "distributed identically to those sampled from the target alone".
  The arithmetic you will use is Equation 1 and Theorem 3.8, which `specdec_math.py` implements. These section numbers come from the HTML version, not the published PDF. Confirm them before you quote them in a slide.

- **Performance improvements with speculative decoding in vLLM for gpt-oss**, Red Hat Developer, 2026-04-16 — https://developers.redhat.com/articles/2026/04/16/performance-improvements-speculative-decoding-vllm-gpt-oss
  The only source found with acceptance rate, acceptance length, and throughput for the same runs. Focus on the draft-length table. Conditions: vLLM 0.13.0, an H200, and a 120B mixture-of-experts target with a trained draft head.

- **The slowdown, measured by the maintainers** — https://vllm.ai/blog/2024-10-17-spec-decode
  Read it for the sentence quoted in section 4.5. The stated cause is that the system is already limited by compute. A talk by a vLLM contributor shows the same effect at 19:26 of https://www.youtube.com/watch?v=9ih0EmcXRHE.

- **EAGLE-3** — https://arxiv.org/abs/2503.01840
  Read its batch-size table, not its headline. The table names no GPU and uses no tree, with a maximum chain length of 2. Treat the crossover as a pattern, not as your number.

- **Dynamic speculative decoding** — https://docs.vllm.ai/en/v0.29.0/features/speculative_decoding/dynamic_speculative_decoding/
  The engine's own answer to the slowdown. Note that the older `speculative_disable_by_batch_size` field no longer exists.

- **Measuring acceptance on your own server** — https://docs.vllm.ai/en/v0.29.0/features/speculative_decoding/acceptance_metrics/
  The flag is `--per-request-spec-decode-metrics summary`. It reports `mean_acceptance_length`, `draft_acceptance_rate`, and an acceptance histogram. Read section 4.5 before you interpret the second one.

- **Prompt lookup decoding** — https://github.com/apoorvumang/prompt-lookup-decoding
  Try this method first. Its 2.4x figure used a 7B model on one A100. Its README states the limit: gains are much smaller on the first turn of a chat.

- **Deep Dive: Optimizing LLM inference**, Julien Simon, 36 minutes — https://www.youtube.com/watch?v=hMs8VNRy5Ys
  Phase 1 used the first half of this talk. Its chapters: 11:15 continuous batching. 16:17 speculative decoding. 25:28 a small ready-made draft model. 26:40 n-grams. 30:25 Medusa.
  Watch 11:15 to 16:17 first. Continuous batching is why speculative decoding stops helping under load.

### Economics

Three of the four break-even estimates found come from companies that sell a related product, and none is peer reviewed. Section 4.6 summarises three of them. Measure your own throughput instead.

---

## Cheatsheet — part B

```
QUANTIZATION FORMATS
  FP8 W8A8    weights+activations  2x smaller  Ada/Hopper/Blackwell, AMD
  INT8 W8A8   weights+activations  ~2x         Turing onward, plus CPU
  AWQ W4A16   weights only         ~75% off    Turing-Hopper, NOT AMD GPU
  GPTQ W4A16  weights only         ~75% off    Volta onward
  NVFP4       weights (+acts)      3.5x vs FP16  Blackwell only
  MXFP4       MoE expert weights   4.25 bits/param
  AutoAWQ is DEPRECATED; the tooling moved to llm-compressor
  You usually DOWNLOAD a quantized checkpoint. --quantization is for ONLINE
  quantization only; a pre-quantized checkpoint is detected from its config.

WHAT IT COSTS IN QUALITY
  FP8 ~ lossless at every size (99.3%-101.2% recovery)
  4-bit recovery rises with model size: 96.1% / 97.4% / 98.9% at 8B/70B/405B
    and ONLY on a hard enough suite
  automatic metrics said -1.7%. HUMAN raters said -16.0%. Same checkpoint.
  damage concentrates: maths and reasoning > non-Latin scripts > long context
  reasoning models get LONGER as well as worse:
    85.6% acc / 5,200 tokens  ->  47.0% acc / 23,400 tokens   (3-bit, 1.5B)
    put OUTPUT LENGTH in the gate; no standard benchmark reports it

WHAT IT BUYS IN SPEED
  weight-only (W4A16)  -> DECODE faster   -> wins at LOW concurrency  (1.45x)
  weight+activation    -> decode AND      -> wins under LOAD          (1.87x)
    (W8A8)                prefill faster
  batch size 1 + short outputs -> mostly just memory

KV CACHE QUANTIZATION
  --kv-cache-dtype fp8  halves KV storage, and has a BREAK-EVEN in context:
    ~7,000 tokens (8B on H100) | ~22,000 tokens (another model)
    BELOW the threshold it is SLOWER
  head_dim 256 + prefill-heavy -> 1.6x TTFT REGRESSION
  a precision bug once took 128k retrieval from 91% -> 13%, invisible at 4k
  break-even moved 24,889 -> 7,010 tokens between two versions:
    ANY KV-CACHE BENCHMARK OVER A YEAR OLD IS OUT OF DATE

THE GATE
  >=99% on a general suite | >=98% on YOUR task suite
  + a LONG-CONTEXT eval at your real maximum | + a throughput run
  judge on the WORST end of the interval, not the midpoint
  20 items: 1 flip -> interval [-15%, 0%]; smallest clear drop = 4 of 20
  published noise that is NOT a win: 4-bit AIME above baseline,
    FP8 100.8% on maths, 0.933 vs 0.930 on 164 problems (= half a problem)

SPECULATIVE DECODING
  the guarantee: output is distributed IDENTICALLY to the target. Not similar.
    so it needs no eval re-run. Quantization does.
  improvement = (1 - a^(k+1)) / ((1 - a)(k*c + 1))        Theorem 3.8
    a = per-position acceptance | k = draft length | c = draft cost ratio
  YOUR SERVER REPORTS A DIFFERENT NUMBER:
    mean_acceptance_length = 1 + k * draft_acceptance_rate
    reported 0.454 -> 0.283 as k rises, but TRUE alpha stays 0.555-0.577
    WRONG --alpha 0.283 -> k=1, 1.17x | RIGHT --alpha 0.555 -> k=3, 1.56x
  methods: n-gram (zero setup, 2.4-2.8x) | draft model (1.5x) |
           Medusa (~5 GPU-hours, 2.2-3.6x) | EAGLE-3 (days, 6.5x lab)
  START WITH N-GRAM when the output copies from the input
  IT CAN LOSE: measured 1.4x and 1.8x SLOWDOWNS at high load, same hardware
    EAGLE crosses below 1.00x between batch 24 and 32
    vLLM ships num_speculative_tokens_per_batch_size to turn it OFF above a
    concurrency threshold
  the right question is NOT "is batch high" but "is the target still
    memory-bound". Long context and MoE stay memory-bound far longer.

THE SELF-HOST DECISION
  four inputs: hourly rate | sustained output tok/s | UTILISATION | which API
  MEASURE the throughput. It is the only input you cannot look up.
  $/Mtok = (hourly x gpus) / (tok_s x 3600 x utilisation / 1e6)
  1 H100 at $3.49, 1,200 tok/s: $0.81/Mtok at 100%, $8.08 at 10%
  include the engineer: $3,750/mo = ~1.5x the $2,548 hardware at $3.49/h
  against a CHEAP API ($1.60): break-even 50.5%, and with the engineer the
    fleet NEVER pays (needs 3,936M tok/mo, ceiling 3,154M)
  against a FRONTIER API ($8.00): break-even 10.1% utilisation
  non-cost reasons that override the arithmetic: data control, a model nobody
    hosts, a latency floor you own, price stability

THE COMMANDS
  specdec_math.py                          the speedup table, offline
  specdec_math.py --from-server            convert the reported rate
  specdec_math.py --sweep-batch            find where it becomes a loss
  specdec_math.py --best-k --alpha X       optimal draft length
  quant_gate.py --self-test                the statistics, offline
  quant_gate.py --baseline-url ... --candidate-url ...   the gate, live
  gpu_economics.py --gpu-hourly X --tps Y --role cheap   then --role deep
```
