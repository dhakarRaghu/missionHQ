Phase 3B left your hosted bill under control. Your meter matches the invoice, the cascade runs behind a random control, and a pre-call reservation stops runaway spend. Now management asks the next question: would renting a GPU and serving the model yourself cost less? You get one hour and $5 to $10 of rented GPU time to return the first honest number. You pick the cheapest H100 on the marketplace, paste the launch command, and wait. Sixty-eight minutes later the model is still downloading, the rental is over, and no server ever started. No error appears anywhere on your screen, and the failure happened in the machine listing you picked before you typed anything.

So the question is not only what a GPU costs per hour. It is which minutes of that hour you actually get to use, why two serving engines on identical hardware behave differently, and which startup errors mean the GPU is too small versus which ones mean one setting is wrong. Answer those, and the one number you hand back at the end of the hour is one you can defend.

This lesson teaches five ideas. They are listed here so you can see where the lesson is going. They will read more clearly once each has been explained below, so come back to this list at the end.

- A rented GPU bills from container start, so the weight download is billed at GPU rates and can cost more than the serving you came for. Price a session before renting, pick the machine by its measured downlink, and prepare commands offline.
- A serving default is a function evaluated at startup from GPU memory and the entry point you used, so the same hardware yields different servers depending on how you launched them. Explain why two honest benchmarks disagree, and pin flags before measuring anything.
- No engine is the faster engine; only one configuration is faster on one workload, so a defensible comparison is an experiment design: one client, pinned flags, a traffic-shaped trace, and a curve read by its shape. Design an engine comparison he could defend, and reject a bad one with specific questions.
- A startup memory failure is a budget equation, not an event: weights plus KV for your context must fit the memory fraction, and the useful error prints the value to set. Classify any startup failure into weights, context or fragmentation, and apply the right fix instead of renting a bigger GPU.
- Structured output is a deploy-time, engine-wide decision wearing a per-request API: the first structured request picks the grammar backend for every later request on vLLM, and SGLang's only fallback disables the feature server-wide. Decide whether to pin a backend, predict what a tenant's exotic schema does to everyone else, and read log lines as guarantees lost.

## Where you are, and what your first rental just bought

Three phases ago you measured someone else's server. Phase 3B ended with your hosted bill under control. It was a cascade behind a random control, and a guard that reserves the worst case before each call. Now management asks a different question. Would it be cheaper to rent a GPU and serve the model yourself? You get one hour and $5 to $10 of GPU time to answer it with one number. That number is sustained output tokens per second on your traffic.

Everything in this phase follows that one session. You rent the machine, start a server on it, and measure it. The first thing the session teaches is a surprise. Billing starts the moment the container starts, and the model still has to download. On the wrong machine, a 140 GB model takes 68 minutes to arrive. That is longer than your one-hour rental, and the whole fee went to waiting. This phase is how you make the hour pay instead.

The KV cache (Phase 2A)

While a request runs, the GPU keeps its attention keys and values in memory. That store is the KV cache, and its size sets how much context your requests can afford. Self-serving means you size and budget this memory yourself, so a startup memory error becomes an equation you can solve.

Prefill and decode (Phase 2B)

Serving one request has two phases with different costs. Prefill processes the whole prompt at once and gets slower as the prompt grows. Decode makes tokens one at a time and is memory-bound. A benchmark at one prompt length measures one point on a curve, so your trace must mix prompt sizes.

TTFT and ITL (Phases 1 and 2B)

TTFT is the wait for the first token, and ITL is the gap between later tokens. Your users feel both, so a bare throughput number is not enough. This phase reports throughput together with TTFT p99, the slowest first-token wait users see at capacity.

Success proves nothing (Phase 3A)

A broken cache still returns 200 OK, and the usage object was the only proof. The same pattern returns three times here. Vendor defaults differ silently. A comparison looks settled and is not. A grammar backend switches with no error message. A green dashboard never proves the thing you did not check.

These four ideas meet an order of operations this time. The sequence is where the money and the mistakes go:

- plan the sessionwrite every command and check every number before the clock starts

- rent the machinepick it by its measured network, not its hourly price

- start the serverpin the flags, and read any memory error as a budget equation

- measure and compareread the curve by its shape, not a single number

Phase 3B taught you to distrust a bill until you could reproduce it. This phase teaches you to distrust a server the same way, including the one you started yourself.

## What does an hour of GPU time actually buy?

A rented GPU bills from container start, so the model download can cost more than the serving you came for.

Management wants to know whether self-serving beats the hosted bill, so you get one hour and $5 to $10 of GPU time for the first honest number. Your budget exercise from Phase 3B taught you to price a call before making it. Renting hardware needs the same habit, because the meter here runs on time, not tokens.

You likely believe an hour of H100 at $3.49 buys an hour of experimenting. It does not. The rental clock, the interval from container start to instance stop, bills every second in between. The GPU sits idle during the image pull, the weight download and the engine load, and each second bills at the GPU's hourly rate. The only part you wanted is the benchmark in the middle.

one rental: what each span bills
image pull
download 16 GB weights
engine load
benchmark · the work you wanted

- t=0:00 container starts, billing starts

- t=0:25 instance stops
Every span left of the benchmark is billed at the same hourly rate. The download span stretches or shrinks with the machine's network, and it is the one span you can predict before renting. Illustration, not measured.

Predict: you rent one H100 at $3.49 per hour to benchmark a 140 GB model, and the machine's downlink is 276 Mbps (34.5 MB/s). What does the download cost, and what do you get inside a one-hour rental?The download takes 67.6 minutes and costs $3.93. You get nothing, because the rental ends before the download finishes. The arithmetic is 140,000 MB divided by 34.5 MB/s, which is about 4,058 seconds, and at $3.49 per hour that time costs $3.93. The same model on a 500 MB/s link takes 4.7 minutes and costs $0.27, so the two machines differ by more than a factor of ten on cost before any benchmark runs.

Why does the download set the price of the session? Three steps, each billed:

- The container starts and billing starts with it, because rental prices instance uptime, not GPU use.

- The weights arrive over the machine's own network link, so your office connection is irrelevant once you rent.

- Marketplace machines vary by more than ten times in link speed, so two listings at the same hourly price deliver very different sessions.

Step 2 has a counterweight: the listing tells you the number. A marketplace publishes the measured downlink, the download speed the provider recorded on that specific machine, because it varies so much. Read it before you rent, the same way you would read a server error before retrying it.

Download time and its share of the rental

Model size GB

Measured downlink MB/s

Download , costing  at $3.49/h

Move the model-size slider to 16 and the problem mostly disappears. This is why the whole phase uses an 8B model first: 16 GB downloads in a minute or two on a fast link, and in about 8 minutes even at the listing's 34.5 MB/s. Run one larger measurement only after the small loop works.

Three more ways to make the download cheap, each one free:

- Check the byte count first with hf download --dry-run, so a repository larger than the card promises fails for free at your desk.

- Use hf_xet, the download backend bundled with recent huggingface_hub, because the older hf_transfer package that tutorials name is deprecated.

- Do the cached-volume arithmetic: a network volume at $9.80 per month breaks even against 9 to 29 re-downloads, and it pins you to one datacentre.

One price row for calibration: an H100 runs from about $1.87 on a marketplace to $6.88 on AWS per hour. The durable correction is the ratio, not the row. The specialist-versus-hyperscaler gap you read quoted as 10x is 3.68x at list prices, and CoreWeave, the most managed specialist in the table, sits within 12% of AWS. Re-read your provider's page on the day you rent, write the date next to your numbers, and distrust any gap larger than four.

Two billing traps survive good download planning, and both charge while you do nothing:

- A provider that bills per minute and while idle charges for your lunch, so prefer per-second billing with no idle charge for a one-hour session.

- Stopping the instance does not stop the volume: on one marketplace the storage rate doubles on a stopped pod, and a zero balance deletes the cached model you paid to keep.

EvidenceThe 276 Mbps (34.5 MB/s) figure comes from a marketplace machine listing read 2026-09-13; the download arithmetic is recomputed from the stated link rate, so treat the times as the right order of magnitude, not measurements. Prices in this section were read 2026-09-13 and churn weekly; the 3.68x gap divides $6.88 by $1.87. hf_xet is bundled with huggingface_hub 0.32.0 and later, and the deprecation of hf_transfer is in the Hugging Face download guide, read 2026-10-04. hf-mount is omitted: it could not be confirmed in the guide.

You rent a clock, not a GPU, and the clock runs during the download.

Believing the download is free costs you the whole rental if you skip the listing's measured downlink.

Move the calc sliders to your real model and a slow link, and watch the download pass the hour.

The download is the part of the clock you cannot shorten but can predict; the next section asks what you prepare before t=0:00 so the paid minutes go to serving: why is typing the launch command the last thing you do?

## Why is typing the launch command the last thing you do?

The download is priced by the machine, but the rest of the rental clock is priced by your preparation.

The previous section priced the download at 67.6 billed minutes on a slow machine. That block sits on the rental clock. The rental clock is the billing timeline that starts when your container starts, whether you are ready or not. You cannot speed up the machine's measured downlink, the link rate the marketplace publishes for that specific machine. You can delete almost every other minute from the clock. Those minutes are you reading docs and typing commands while the meter runs.

The fix is a session plan: one text file you write before the rental starts. It holds every command and value the session needs. Writing it costs nothing, because you write it on your laptop with the clock stopped. Copying from it during the session turns paid minutes into paste and run.

The plan has five lines, and each line removes a specific kind of paid fumbling:

- The model id and its size in GB. Write Qwen/Qwen3-8B and 16 GB, so the download arithmetic from the previous section uses a real number, not a guess.

- The access token, if the model is gated. A gated checkpoint needs approval on its model page before any token works, and that approval is a human step you cannot do while the GPU bills you.

- Both full launch commands. The vLLM command and the SGLang command, copied complete, so a $3.49-an-hour machine is not waiting while you look up a flag.

- The client command with the model id already in it. A benchmark command that fails on a wrong model name spends paid minutes on a typo.

- Where the results go. One open document, so the numbers you paid for land somewhere before you stop the instance.

Two checks belong in the plan itself, because each can veto the machine before you pay for it.

The first is the driver version. The default vLLM wheel needs a 575-series NVIDIA driver, and SGLang 0.5.19 needs a 580-series driver. A marketplace machine with a 570-series driver runs vLLM and does not run SGLang natively. The listing shows the driver. This is a reason to reject a machine at zero cost, before the container starts.

Predict: the listing shows a 570-series driver. Which of the two engines can your session use?
vLLM only. Its wheel needs a 575-series driver or newer, and 570 is close but below it. SGLang 0.5.19 needs a 580-series driver, so it does not run on this machine at all. The tempting answer is "both, drivers are usually backward compatible". That belief costs you a rental: you find out after the image pull, on the clock.

The second check is what the download actually contains. One 8B checkpoint repository totals 32.13 GB, but only 16.06 GB of that is the safetensors files the engines read. The other half is a duplicate of the same weights in a second format.

Predict: the repository totals 32.13 GB. How many GB must you download to serve the model?
16.06 GB. The engines read only the safetensors files. The other 16 GB is bytes you would download at GPU rates for nothing. The obvious answer is 32.13, because hf download takes the whole repository by default. Filtering the download to the safetensors files halves the download block on your clock. That is why the size line in the plan says 16 GB for this model and not 32.

This is where hf download --dry-run earns its place in the plan. It prints the exact byte count before anything downloads. You see the 32.13 versus 16.06 split on your laptop, with the clock stopped. hf_xet is the download backend bundled with recent huggingface_hub. It replaced the deprecated hf_transfer. Combined with it, the download line of the plan becomes a known number of minutes instead of a surprise.

Every command and value the session needs goes in a text file before t=0:00. Writing is free and typing is billed.

The wrong belief: "I will figure out flags once the server is up". One 8B repository doubles your download to 32.13 GB. A 570-series driver rejects SGLang after you have paid for the image pull.

Write the five-line plan now for Qwen3-8B. It lists model id and 16 GB, token decision, both launch commands, the client command, and the results destination.

Your plan now ends in two launch commands. Two servers started from the same model id on the same machine are not yet the same server. The next section answers why they batch differently.

## You launched two servers on one GPU. Why do they batch differently?

Defaults are computed at startup from your GPU and launch method, so identical machines can run different servers.

Your plan from the last section ends in two launch commands. But two servers started from the same model id on the same machine are not yet the same server.

You are on the rented H100. The weights are cached and the clock is running. You start vLLM with vllm serve Qwen/Qwen3-8B. A colleague on an identical machine loads the same model through the Python LLM class in a notebook. Both succeed. Both benchmarks disagree, and neither of you set a single flag.

### Defaults are a function, evaluated at startup

The word "default" suggests a fixed, vendor-tested value. In vLLM 0.29.0 a default is the output of a function, and the function runs at startup. Its inputs are the GPU's total memory and the entry point you used. This is the command or class that started the server. This is why the same hardware yields different servers under different launch commands.

- How much total memory does the GPU report?

- under 70 GiB, or any A100server: 2,048 batched tokens, 256 concurrent sequences

- 70 to 160 GiB, not an A100server: 8,192 tokens, 1,024 sequences · Python class: 16,384 tokens

- 160 GiB or moreboth entry points: 16,384 tokens, 1,024 sequences

vLLM 0.29.0's defaults: memory buckets first, then the entry point. Verified against arg_utils.py at the v0.29.0 tag.

Predict: you run the same model through vLLM's Python LLM class and through vllm serve on the same 80 GB H100. Do they batch identically by default?
No. The 80 GB card lands in the 70 to 160 GiB bucket, and that bucket splits by entry point. The server gets 8,192 maximum batched tokens and the Python class gets 16,384. The reasoning most people give is "defaults are defaults". But here the default is a function and the entry point is one of its arguments.

The mechanism, from the source, in order:

- At startup the engine reads the GPU's total memory, a hardware measurement, not a setting.

- It selects a bucket. The middle bucket covers most rented cards, and it splits further by usage context.

- The server context gets half the batched tokens of the offline Python context in that bucket, so a notebook and an endpoint are different servers by default.

- The A100 exclusion is a device-name string check, added after a measured throughput regression on that card.

- There is a third channel: --performance-mode throughput doubles both values when they are unset, so one more flag silently changes the "default" server.

SGLang plays the same game with less visible rules. Its chunked_prefill_size, mem_fraction_static and max_running_requests all default to None in 0.5.19. A startup pipeline resolves them against the measured hardware. The concrete tier numbers live in that pipeline. The study note did not read it, so treat any published SGLang default table as unverified.

Evidence
The bucket code and the 8,192 versus 16,384 split are verified in vllm/engine/arg_utils.py at v0.29.0, read 2026-10-04, rank 1: "on one non-A100 80 GB GPU, the server defaults to 8,192 batched tokens and the Python class to 16,384". The throughput-mode doubling is in the same file. SGLang's None defaults are verified in server_args.py at v0.5.19; the resolved numbers were not checked.

### The flag map, and why 0.90 is not 0.90

Defaults explain why two launches on one engine differ. Comparing two engines adds a second problem, because the same idea lives under a different flag name on each side. The table that translates between them is the flag map. It is the thing you keep open on your first day.

what you wantvLLM 0.29.0SGLang 0.5.19

maximum context--max-model-len--context-length

share of GPU memory--gpu-memory-utilization (0.92)--mem-fraction-static (computed)

concurrent sequences--max-num-seqs--max-running-requests

tokens per iteration--max-num-batched-tokens--chunked-prefill-size

The memory row hides the real trap. --gpu-memory-utilization is a fraction of the GPU's total memory. --mem-fraction-static counts a different whole. So 0.90 on both flags gives two different KV cache sizes. The KV cache is the memory the engines keep for each request's attention keys and values. A comparison run at "0.90 both sides" compares two servers with unequal memory budgets.

This failure has already happened in public. A published benchmark of the two engines was retracted by its own author. He had not known that --max-model-len maps to --context-length and had used a different flag. His numbers were honest measurements of two unmatched servers. The same fate waits for any blog table that never lists flags.

Rule for the rest of the phase: before you measure anything, write down the context, the batched-tokens value, the concurrent-sequences value and the memory share explicitly on both engines. Unpinned, you are measuring the defaults, not the engines.

Use it in E6. The lab's cross-engine exercise asks you to pin this table row by row on both engines before the first request. The result answers one question. Which flags, once pinned, move the outcome at all? A small difference after honest pinning is a valid result.

The default is a function of your GPU memory and your entry point. So unpinned flags mean you measured the defaults.

The wrong belief: "0.90 on both engines is the same memory". Those flags count different wholes, so the KV caches differ and so does the comparison.

Write the vLLM and SGLang equivalents of one launch, pinning context, batched tokens, sequences and memory share on both.

Defaults explain why two launched servers differ. A launch that fails entirely has the same cause one level down. The engine reads the memory budget before it serves anything. The next section answers which of three failures yours is.

## The server will not start. Which of three failures did you get?

A startup memory failure is a budget equation read back to you, and the useful error prints the fix.

vLLM's defaults are a startup function of GPU memory and entry point. A launch that fails entirely has the same cause one level down. The engine also computes its memory budget before it serves one request.

### Your rental, five minutes in

Your session plan ended in one running command against Qwen3-8B. The weights download, the engine starts to load, and the process exits. The log says something about KV cache memory. No request was ever sent, so load is not the cause. Your rented GPU is still billing. That is why you want to read this error as an equation instead of reaching for a bigger machine.

### The picture: one GPU, one budget

Both engines allocate memory upfront, in a fixed order. The weights load first and take what they need. The engine then measures what remains and carves out a pool for the KV cache. The KV cache is the attention keys and values the GPU keeps for each running sequence. Everything above that sits unused. The budget line itself is the memory fraction. This is the share of total GPU memory the engine is allowed to occupy. It is 0.92 by default on vLLM 0.29.0 and computed from a reserve formula on SGLang 0.5.19.

One 80 GB GPU, budget at 0.92 (illustration, not measured)

The equation is one line: weights plus the KV your context needs must fit inside the fraction. Allocation happens once, at startup. A shortage so always shows up before the first request, with exact numbers in the error.

Predict: your server fails at startup on KV cache memory before any request arrives. Which two quantities trade against each other inside the budget, and which error message tells you the value to set?
The trade is context length against concurrency, priced in KV bytes: a longer context needs more KV per sequence, so fewer sequences fit in the pool. The message that carries the answer is vLLM's KV-fit error, which prints the estimated maximum model length that fits in the memory you gave it. Set --max-model-len to that number and the budget balances.

### Why the error can compute the answer

The error reads as magic until you see where the numbers come from. Before sizing the KV pool, the engine runs a profiling pass. This is one forward pass of the model with dummy inputs, run only to measure peak activation memory. The sequence is deterministic:

- Load the weights, because their size is fixed and known.

- Run the model once with dummy inputs, because activation memory peaks during a real forward pass and cannot be predicted from config files.

- Subtract weights and measured activations from the fraction budget, because the remainder is all the KV pool can ever be.

- Divide the remainder by the bytes one token of KV costs, because that converts memory into the largest context the GPU can serve.

Step 4 is where the error gets its number. The derived max model length, the largest context that fits after the profiling pass, is printed inside the failure message. The engine does not complain about memory; it solves the equation and reports the boundary.

### Which failure did you get?

Three failures cover almost every startup case, and each has a fix pointing a different way.

- Weights filled everything. vLLM prints "No available memory for the cache blocks". No context length fits beside these weights, so the fixes are a smaller model, more GPUs, or a quantized checkpoint.

- The model fits, your context does not. vLLM prints that serving the model's max seq len needs X GiB of KV against Y GiB available, and names the estimated maximum model length, Z. Set --max-model-len to Z, or raise the fraction.

- A raw allocator failure. The PyTorch message mentions fragmentation and suggests PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True. Here the cause is usually a fraction set too high, so lower it, do not raise it.

A fourth failure comes before all of these. Asking for more context than the model's trained limit, for example --max-model-len 1000000 against Qwen3-8B's 40,960 ceiling, raises a ValueError from model.py before any memory is checked. An escape hatch exists: VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 converts the error to a warning, and the source warns that positions past the limit produce NaN or out-of-bounds behaviour. Leave it alone unless you know why the length is safe.

engineerror you gotfix direction

vLLM 0.29.0context does not fitlower --max-model-len, or raise --gpu-memory-utilization

SGLang 0.5.19no room for KV under mem_fraction_staticraise --mem-fraction-static above the suggested value

SGLang 0.5.19runtime OOM, general caseits own flag help says use a smaller --mem-fraction-static

The last two rows look like a contradiction, and they are the point. SGLang's no-KV error says raise the fraction because the weights need more of the GPU. Its flag help says lower the fraction on OOM because fragmentation needs slack. The flag name tells you nothing; the error you received tells you which way to move it.

### The shortcut and the pin

--max-model-len auto runs the search for you. It tries the model's full context, then finds the largest length that fits the measured memory. Read the number it logs, then write that number into your launch command. A pinned value makes the deployment reproducible on the next machine, where the profiling pass could pick a different one.

Evidence
The ValueError text, the VLLM_ALLOW_LONG_MAX_MODEL_LEN guard with its NaN and out-of-bounds warning, and the auto search behaviour were verified in vLLM v0.29.0 model.py, read 2026-10-04. SGLang's two conflicting texts were verified in v0.5.19 server_args.py: the help text "Use a smaller value if you see out-of-memory errors" and the no-KV error's "raise --mem-fraction-static above <suggested>". vLLM's KV-fit error texts are quoted from the phase's 2026-09-17 source read, not re-read this run. E4's arithmetic: 40,960 tokens of KV for Qwen3-8B need about 6.0 GB, which does not fit beside 16 GB of weights inside a 0.25 fraction on 80 GB.

### Use it

In the lab, E4 forces this failure on purpose. The launch pins the fraction at 0.25 and the KV requirement exceeds what remains. The error then prints the estimated maximum model length. The exercise is reading the number out of the message and setting it, which is the entire fix. Under five minutes of GPU time replaces the instinct to rent a bigger card.

A startup memory failure is a budget equation, and vLLM's KV-fit error prints the answer.

"OOM at startup means the GPU is too small" costs a bigger rental. The fix was one context value or one flag, moved in the direction the error names.

Read E4's error in the lab and confirm the printed Z matches the arithmetic. That is 6.0 GB of KV beside 16 GB of weights inside 20 GB.

You can now start a server, pin its flags, and recover from the launch that fails. What you still cannot do is say what the running server is worth. That is the next section's question: why does capacity live where the curve flattens?

## Why does capacity live where the curve flattens?

A sweep has a shape, and the shape tells you where capacity is.

You can now start a server with pinned flags and fix the launches that fail. So the rented hour finally has a running server in it. What is left unexplained is what to measure on it. Filling GPU utilisation at 100% is not the same thing as knowing what the server is worth.

Your management asked for one number, the sustained output tokens per second on your traffic. You have about twenty billed minutes left to produce it. The easy thing is to run the client at concurrency 64 and report the total. That single number cannot tell you whether concurrency 64 was two times the server's capacity or half of it.

Two curves describe any serving benchmark. The first plots output tokens per second against concurrency, and it rises and then flattens, because past some load the GPU has no idle cycles left to give. The second plots TTFT p99, the 99th percentile of the time from sending a request to its first token, against the same concurrency, and it keeps rising the whole way. The operating point is the pair of numbers read where the first curve flattens: the peak output tokens per second, and the TTFT p99 at that concurrency.

output tok/s vs concurrency

-

-

-
plateau
capacity
concurrency
TTFT p99 vs concurrency

-

-

-
same point
user experience at capacity
concurrency

Throughput flattens at the plateau; TTFT p99 keeps rising past it. Illustration of the shape, not measured.

Predict: your sweep shows output tok/s still rising 5% from concurrency 64 to 128, and TTFT p99 has doubled. Do you have capacity left, and what do you report?
Add another level, because you have not found the plateau yet. A 5% rise means the GPU still had room at 64. The peak you report must come from a concurrency where the curve flattens. The TTFT p99 you report must be read at that same concurrency. Reporting only the tok/s at 128 hides that each user's first token now waits twice as long.

### Why each curve has its shape

- Throughput rises while the GPU has idle room. Each added concurrent sequence fills cycles that were unused, so total output tokens per second climb almost linearly at low load.

- Throughput flattens when compute or memory bandwidth saturates. Decode, the step that emits one token per sequence per pass, is memory-bound, so once every pass is busy, more concurrency adds queueing and not output.

- TTFT p99 rises without a plateau. Prefill, the one pass that processes the whole prompt before the first token, competes with decode for the same GPU, so each added sequence pushes every new prompt further back in the queue.

- Errors start long after the plateau. The server queues almost indefinitely before it drops requests, so "no errors" is not evidence of spare capacity.

One more column belongs in the result table, and most published benchmark tables leave it out. It is ITL p99, the 99th percentile of the gap between two tokens in one stream. Phase 2B showed that a high ITL is the mid-stream freeze a user actually sees. So a plateau measurement without it is missing the number your users feel.

### Why one prompt length is one point on an un-drawn curve

Prefill cost grows with prompt size while decode cost does not. So a sweep run only on 200-token prompts measures a regime your 4,000-token prompts will never visit. A support workload with short questions and long retrieved-context queries lives at several points at once. The course trace mixes three prompt-size groups for exactly this reason. So the measured plateau is the plateau of traffic that resembles yours and not of one synthetic length.

### The two numbers you carry away

From the whole session you keep the operating point. It is peak output tok/s, and TTFT p99 at the concurrency that produced it. The first is the number Phase 4B's economics consume, through one conversion:

python phase04_serving/gpu_economics.py --gpu-hourly 3.49 --tps <your measured peak>

The output is cost per million tokens, which is the figure that compares against the hosted bill. A throughput number with no cost attached cannot decide anything. A cost built on a non-plateau throughput is wrong in the direction that flatters self-hosting.

Evidence
The curve shapes and the plateau rule come from his phase section 4.3, which presents them as the typical shape of a concurrency sweep. The bench_client.py table columns (TTFT p50, TTFT p99, ITL p50, ITL p99, out tok/s, err), the gpu_economics.py command, and the three-group trace are quoted from the same section. The specific numbers in his figures come from his own lab runs, so nothing here is asserted as measured throughput.

### Use it

In the lab, E5 runs this sweep against one engine. E1 is its offline half. Open the trace and check the spread of prompt lengths yourself. Then when the plateau number comes out you can say which traffic shape it belongs to. The question is whether the tok/s you hand to Phase 4B came from the flat part of the curve. Or whether they came from somewhere on the slope. Reading the sweep answers this.

Capacity is where throughput flattens; the operating point is that peak plus the TTFT p99 at the same concurrency.

"No errors and rising throughput" at one concurrency is the slope talking. Reporting it as capacity overstates the server and every cost figure built on it.

Run bench_client.py --dry-run on the trace and confirm it reports 20 prompts across three size groups. Do this before any GPU minute is spent.

You can now read one server's measurement honestly. But a colleague will arrive with a blog post claiming the other engine is 2x faster. The next section gives you the questions to ask of that claim.

## A blog says engine B is 2x faster. What do you ask?

Believing a 2x claim from one row buys the wrong engine for a year.

The section above showed how to read one server honestly, with capacity at the plateau and the operating point as peak output tok/s plus the TTFT p99 at that concurrency. The next event in your rental story is a colleague forwarding a benchmark that says the other engine is 2x faster. Management asks whether you are testing the wrong one. A comparison of two servers adds three new ways to fool yourself, and each one pairs with a fix you already own.

The claim names the wrong unit. Section 4 showed that a server computes its defaults at startup. The defaults come from the GPU's memory and the entry point you used. So two runs of the same engine can already be two different servers. What a measurement compares is one configuration against another on one workload, never one engine against another. Drawn as a shape, the fair comparison looks like this.

one client (bench_client.py)
one trace file · one pinned flag set

vLLM · port 8000
flags pinned

SGLang · port 30000
flags pinned

two result files
safe to put side by side

The fair shape. One client drives both engines with one trace and one pinned flag set, so the only difference left between the two runs is the engine.

The shape that manufactures wrong answers runs each engine's own benchmark tool against that engine on its own defaults. That changes the engine, the client, the flag set and the traffic mix all at once. So the gap it reports has four candidate causes and no way to choose among them.

Predict: you run one engine's own benchmark tool at concurrency 64 and record 2,900 output tok/s. Your colleague runs the other engine's own tool the same way and records 1,400. Management asks which engine to buy for a year. What does each number fail to tell you, and what do you change about both runs?
Each number hides three things.

- Each engine ran on its own computed-at-startup defaults from section 4, so the pair of runs may compare two different servers rather than two different engines.

- Each harness issues and times requests in its own way, so part of the 2,900-against-1,400 gap may live in the client rather than the server.

- Concurrency 64 is one point on a curve nobody drew, and the same load can be routine for one server and heavy for the other.

With few requests the gap can also be manufactured, as in the published result that fell from about 2x at 50 requests to 8.6% at 2,000. So the change to both runs is the same: one client, one trace shaped like your traffic, equivalent flags pinned from the flag map, and a full sweep read by its shape. The three checks below are those fixes, one by one.

### Check one: whose client produced the number?

Both engines ship a benchmark harness, and each harness can drive the other engine. vLLM's has an OpenAI-compatible path that works against SGLang on port 30000, and SGLang's includes vLLM backends directly. So two numbers from two harnesses mix the client's timing and request pattern into the server's score. Nothing forces that, because either harness could have driven both. The fix is one client and one trace, run against both servers, changing only the base URL.

### Check two: do the flags describe the same server?

Section 4 showed that both engines compute their batching and memory defaults from the GPU they find. Their memory flags also count memory differently, so the same 0.90 on both sides is not the same KV cache. A comparison run "on defaults" therefore measures whatever two startup functions happened to pick, plus the engines.

One published comparison was retracted by its own author for exactly this reason. His vLLM flag --max-model-len did not map to the SGLang flag he had used. Once he corrected the mapping, the memory difference he had reported came out "basically the same". The fix is to pin equivalent flags on both sides, using the flag map, before you measure anything.

### Check three: how many requests, and whose traffic?

Short runs manufacture gaps. One published comparison showed about 2x at 50 requests, and a rerun with 2,000 requests shrank it to 8.6%. A run at one prompt length has the same weakness turned sideways. Prefill cost grows with prompt size, so it measures one point on a curve nobody drew. The fix is a trace shaped like your own traffic, with enough requests to fill the shape. Then read the sweep like section 6 read it. Use the plateau and the TTFT p99 at it, instead of one number at one concurrency.

If you later need to replay production traffic with its real arrival times, both harnesses can do it: vLLM with --dataset-name timed_trace and SGLang with --dataset-name mooncake --use-trace-timestamps, both reading JSONL with a timestamp per request. Whether one trace file works unchanged in both harnesses was not confirmed, so test that before the paid hour.

### What the only audited comparison found

An audited comparison is a benchmark submitted to an outside body that checks the submitter followed the rules. For these two engines exactly one exists, a Krai submission to MLPerf Inference v5.1. The conditions were one machine with eight H200 GPUs, one CUDA version, one driver and Llama-3.1-70B in FP8. The run used 24,576 samples under latency limits of 2,000 ms TTFT and 200 ms per output token. The submitter tuned each engine. No other public comparison fixes the hardware, the model and the latency limits this completely. So its rows are worth reading.

quantization pathscenarioSGLangvLLM

pre-quantized FP8offline tok/s31,38326,319

pre-quantized FP8server tok/s30,30425,628

dynamic FP8offline tok/s27,69730,893

dynamic FP8server tok/s26,43526,903

The winner flips with the quantization path. Pre-quantized means the checkpoint already ships FP8 weights, and dynamic means the engine applies the quantization itself. SGLang leads by 18 to 19% on the pre-quantized checkpoint. vLLM leads by 2 to 12% on the dynamic path, same machine, same model, same accuracy. Anyone quoting a single winner from this submission picked a row and ignored the rest.

The table has limits too. Those engine versions are from mid-2025, roughly twenty releases behind the vLLM you would rent today. No audited comparison of the current versions exists. So the table's real lesson is not which engine won. It is how far the answer moved when only the quantization path changed.

A number you will be quoted and should not use. A July 2024 blog post by one of the two engine teams reported its own engine as 3.1x faster. It tested a 2024 version of the other engine with that engine's prefix caching disabled, and prefix caching, the reuse of stored attention keys and values for a repeated prompt prefix, is on in any real deployment. The figure describes neither engine today. Both projects have since stopped publishing head-to-head numbers, vLLM removed its cross-engine benchmark path for lack of a maintainer, and one independent benchmarking project assigns one engine per model to avoid restarting the argument.

Evidence
The Krai submission's existence and conditions were checked against the public MLPerf Inference v5.1 results tree on 2026-10-04. The four row values come from the phase and were not re-read this run. The 2x to 8.6% rerun and the retracted comparison are reported in the phase. The retraction is public but was not re-read. The July 2024 figure and the retreat from head-to-head numbers are also phase-reported. On 2026-10-04 the current releases were vLLM v0.30.0 and SGLang 0.5.20. So the Krai rows describe engines roughly twenty releases old. A purchase decision needs a fresh run on current versions.

### Use it

The lab's E6 applies the whole design end to end. You launch SGLang with the flags that match your vLLM server from the earlier exercises. Then run the course client against both. bench_client.py is the neutral client. It speaks the OpenAI streaming API, so the same timing logic drives both servers. Only the base URL and the output file change:

python phase04_serving/bench_client.py --base-url http://localhost:8000/v1 \
    --model Qwen/Qwen3-8B --concurrency 1,4,16,64 \
    --trace phase04_serving/traces/support.jsonl --out vllm.json

python phase04_serving/bench_client.py --base-url http://localhost:30000/v1 \
    --model Qwen/Qwen3-8B --concurrency 1,4,16,64 \
    --trace phase04_serving/traces/support.jsonl --out sglang.json

Put the two files side by side and compare the operating points, not a single row. Do not treat two close operating points as a wasted hour. A small, stable difference means the engine choice costs little on your traffic, so you can pick on operability instead. The question E6 answers is not which engine is fastest. It is which configuration is fastest on your trace and by how much.

The unit of any benchmark claim is one configuration on one workload, never the engine.

Two harnesses, two default flag sets and one number each compare four things at once.

Check any engine benchmark for three names: the client, the flags and the request count.

A throughput table never shows which grammar backend served your answers. The next section explains why one tenant's schema can set it for the whole server.

## One tenant's schema changes the whole server. Why?

One tenant's schema can silently change what the whole server guarantees to every other tenant.

The comparison is now defensible, but one configuration choice stays invisible inside any benchmark, because it reaches every tenant and nothing reports it. In Phase 2B you saw constrained decoding, the engine blocking tokens that would break a schema at each generation step, and the phase said this topic would return when you serve the model yourself. This is the return. Your running case is now a self-hosted server at the plateau you measured, and five tenants send JSON-schema requests to it. The question is what one strange schema does to the other four.

### The picture

Constrained decoding needs a library that can read your schema and produce, at each step, the set of tokens that stay legal. That library is the grammar backend, and three of them exist in this course's versions, named xgrammar, outlines and guidance. Phase 2B already fixed what a schema controls: at each step, the engine blocks tokens that would break the schema. What is new here is who picks the library. With the default setting on vLLM, the server picks it for you, once, and the choice binds for every request that follows.

The default setting is auto backend resolution, which means the engine reads the first structured request's schema, classifies it, and picks a backend it keeps for its whole lifetime. The vLLM v0.29.0 source says so directly, in a comment naming the reason: only a single backend is supported, and different backends per request are not.

Predict: you serve JSON-schema responses to five tenants on vLLM with the default auto backend, and a sixth tenant's schema uses multipleOf. No error appears in any dashboard. What changed, and for whom?
The whole server's grammar backend moved. If the sixth tenant's request was the first structured one after startup, the engine classified multipleOf as something xgrammar does not support, chose a fallback backend, and stored that choice. Every later structured request from the other five tenants now runs through that fallback. No request failed, so no alert fired. The schema is still enforced on all of them, what changed is which library enforces it, and the study note could not re-read the latency difference this run, so the honest version is this: the discovery path in production is a log line, not an error.

### The mechanism on vLLM

- At startup the engine has no backend yet, so no cost has been paid and no choice has been made.

- The first structured request arrives, and the engine reads its schema and checks whether xgrammar supports it.

- If xgrammar supports it, the engine pins xgrammar. If not, the engine pins one of the fallback backends, which one depends on which feature the schema uses.

- Every later structured request reuses the pinned backend, because the engine stores the choice once and the source comment says one backend is supported per engine.

The features the source lists as pushing a schema off xgrammar are specific, so you can scan a tenant's schema for them before it arrives:

- multipleOf on numbers.

- uniqueItems, contains, minContains or maxContains on arrays.

- A format outside xgrammar's supported list.

- A string combining pattern or format with minLength or maxLength.

- patternProperties or propertyNames on objects.

Timing matters here, and so does request order. Plain chat requests arrive all evening and change nothing, because only a structured request triggers the classification. Among structured requests, whichever one arrives first decides for all the rest, so the tenant whose schema reaches your server first after each restart sets the backend for everyone.

default auto backend

plain chat requests, no effect

first structured: multipleOf schema

xgrammar
supports?

-

-
no → fallback, pinned for life

all later structured requests run through the fallback
backend pinned at launch (xgrammar)

HTTP 400 on the unsupported schema
the server stays on xgrammar for everyone
One server under both settings. With auto, the first structured schema picks the backend for the engine's lifetime. Pinned at launch, the same schema returns 400 and everyone else stays on xgrammar.

Pinning the backend with --structured-outputs-config.backend xgrammar changes the failure from invisible to visible. An unsupported schema then returns HTTP 400 instead of a silent switch, and the failing request is the one the tenant can fix. For a multi-tenant server this is usually what production wants, because the repair lands on the tenant whose schema caused it.

### SGLang takes the opposite design

SGLang resolves --grammar-backend to xgrammar and applies no per-schema fallback. When a schema fails to compile, that one request aborts with a message naming the failure, and the other tenants are untouched. That is the safer half of the story.

The other half is its one fallback, at startup. If xgrammar cannot handle the model's tokenizer, SGLang logs a warning and sets the backend to none. Structured output is then off for the whole server, and requests return unconstrained text with 200 OK. This is Phase 3A's pattern again, a success code that proves nothing, so the backend name belongs in your logs and your startup checks.

Evidence
The single-backend comment, the initialize-on-first-request code path and the auto docstring were read this run in vLLM v0.29.0 (vill/v1/structured_output/__init__.py, vllm/config/structured_outputs.py), verified on 2026-10-04. SGLang's grammar-backend choices including none were verified in v0.5.19 server_args.py. The tokenizer-unsupported auto-fallback to none is from the phase's source check on 2026-09-13 and was not re-read this run. The latency difference between backends is inferred from the mechanism and was not measured.

### Use it

In the lab, E7 sends one multipleOf schema at both engines and gets three outcomes from one request. On vLLM with auto, a silent server-wide backend switch. On vLLM with the backend pinned, HTTP 400. On SGLang, one aborted request and nothing else touched. The request-field differences, such as vLLM's grammar field being SGLang's ebnf and SGLang having no choice, are in the cheatsheet.

With vLLM's default auto, the first structured request picks the grammar backend for every later request.

Constrained decoding feels per-request like temperature, but the backend is engine-wide, so one tenant's schema decides for all tenants.

Scan one tenant schema for multipleOf, then check your logs for which backend the engine resolved.

You can now plan a rented session so the paid minutes go to serving, start vLLM and SGLang with flags you pinned on purpose, read a startup memory error as an equation, and carry away two numbers, peak output tokens per second and TTFT p99 at that concurrency. Phase 4B asks the question those two numbers answer, whether quantization and speculative decoding change the arithmetic enough to beat your hosted bill.

## What you can do now, and what comes next

You started this phase with one hour, $5 to $10, and a question from management: does self-serving beat hosted prices? The hour went to a download. The sections above turned that failure into five claims. Read them again now; they should read like things you would say yourself.

- The rental clock bills the download. Billing starts at container start, so a 140 GB model on a 34.5 MB/s link costs 67.6 minutes at GPU rates, longer than the rental. (Section 1 and 2.)

- A default is a startup function. vLLM reads GPU memory and your entry point before it picks batching defaults, so the same machine yields different servers depending on how you launched them. (Section 3.)

- A startup memory failure is a budget equation. Weights plus KV for your context must fit the memory fraction, and the KV-fit error prints the value to set. (Section 4.)

- Only a configuration is faster on one workload. So a comparison is an experiment design: one client, pinned flags, a traffic-shaped trace, and a curve read by its shape. (Sections 5 and 6.)

- Structured output is an engine-wide decision. On vLLM the first structured request picks the grammar backend for every later request, while a pinned backend returns HTTP 400 instead. (Section 7.)

You can now plan a rented session so the paid minutes go to serving. You can start both engines with flags you pinned on purpose. You can read a startup memory error as an equation instead of renting a bigger GPU. And you carry away two numbers: peak output tokens per second, and TTFT p99, the time to the first token, at that concurrency.

Phase 4B asks the question those two numbers answer. Quantization buys something there, at a cost that section makes explicit. Speculative decoding changes decode speed, so it moves your plateau. The question is whether both together change the arithmetic enough to beat the hosted bill.

## Lab: plan it offline, break it on the clock, defend the number

-
 E1 offline
Look at the traffic before you measure it. This proves the workload half of a defensible comparison: a benchmark on one prompt length measures one point on a curve you have not drawn.

python phase04_serving/bench_client.py --dry-run --trace phase04_serving/traces/support.jsonl --concurrency 1,4,16,64

Expected: prompts: 20 prompts from phase04_serving/traces/support.jsonl and total : 256 requests. That is 64 requests at each of 4 levels.

Then open phase04_serving/traces/support.jsonl and measure the prompt lengths yourself. Write down the shortest and the longest.

Expected: the prompt field is 50 characters at its shortest and 5,507 at its longest. The lengths form three groups: 50 to 93, 1,102 to 1,197, and 5,448 to 5,507.

EvidenceThe offline commands were run and the lengths were measured with a short Python loop over the file, last re-run 2026-09-17.

-
 E2 offline
Write the whole session down before the clock starts. This is the lever from Section 1: when the rental clock bills everything, preparation controls cost.

Write a text file with these items:

- Your chosen model id and its size in GB.

- The full vLLM launch command and the full SGLang launch command.

- The benchmark command, with your model id already in it.

- Your provider's hourly rate, with today's date.

Then check your target machine's NVIDIA driver version, because a wrong driver wastes your first fifteen paid minutes. vLLM's default build needs 575 or newer, and SGLang 0.5.19 needs 580 or newer.

-
 E3 rented GPU, about $1, UNVERIFIED
Serve a model and let the engine choose its own context size. This applies the flag map and the budget equation together: auto removes the most common first failure, and pinning the result keeps the deployment reproducible.

vllm serve Qwen/Qwen3-8B --max-model-len auto

Expected: the server starts and logs the context length it chose. Write that number down, then restart with that number set explicitly.

If it fails, compare the error with the cases in Section 4 before you change anything.

EvidenceUNVERIFIED on a rented GPU. Commands, flag names and defaults were checked against the vLLM 0.29.0 and SGLang 0.5.19 source at their release tags.

-
 E4 break-it, rented GPU, UNVERIFIED
Run out of KV cache memory on purpose, then let the error tell you the fix. This is Section 4's budget equation read from a real error message.

vllm serve Qwen/Qwen3-8B --max-model-len 40960 --gpu-memory-utilization 0.25

Do not use a context above the model's limit, because vLLM 0.29.0 fails an over-limit context earlier with a ValueError, before any memory check.

Expected: the server refuses to start with one of the two KV messages from Section 4. If it prints an estimated maximum model length, copy that number. Restart with --max-model-len <that number> and the same memory flag, and confirm it starts.

0.25 of an 80 GB GPU        = 20 GB budget
Qwen3-8B weights            = ~16 GB
KV per token: 2 × 36 layers × 8 KV heads × 128 head size × 2 bytes
                            = 147,456 bytes
40,960 tokens of KV         = ~6.0 GB, which does not fit beside the weights

If the server starts anyway, lower --gpu-memory-utilization in steps of 0.02. If you get the first KV message instead, raise it a little.

EvidenceThe KV arithmetic is inferred, not run; the config values come from Qwen3-8B's config.json. UNVERIFIED on a rented GPU.

-
 E5 rented GPU, about $1, UNVERIFIED
Produce the number Phase 4B's economics need. This is the shape-reading from Section 5: capacity is where the throughput curve flattens, not where errors start.

python phase04_serving/bench_client.py --base-url http://localhost:8000/v1 --model Qwen/Qwen3-8B --concurrency 1,4,16,64 --trace phase04_serving/traces/support.jsonl --out vllm.json

Expected: throughput rises and then flattens, while TTFT p99 rises the whole time. Record the peak output tokens per second and the concurrency where it occurred.

EvidenceUNVERIFIED on a rented GPU; checked against the vLLM 0.29.0 source.

-
 E6 rented GPU, about $1, UNVERIFIED
Compare the engines without fooling yourself. This is the experiment design from Sections 3 and 6 applied end to end: one client, both servers, flags pinned.

sglang serve Qwen/Qwen3-8B

Run the same client command as E5, changing only --base-url to port 30000 and --out to sglang.json. Before you compare, set the batching flags explicitly on both sides, using the mapping from Section 3, because the defaults depend on GPU size and on which entry point you used.

Expected: two files you can compare honestly. The difference may be small, and a small difference is a valid result.

EvidenceThree public comparisons of these engines were wrong for exactly the reasons this exercise controls. UNVERIFIED on a rented GPU.

-
 E7 break-it, rented GPU, UNVERIFIED
Send one schema that makes the two engines behave differently. This shows Section 7's claim: the same schema has three different outcomes across these engines.

Build a JSON schema that uses multipleOf on a number field, or patternProperties on an object. Send it to each engine as a structured-output request.

- On vLLM with the default auto backend the request succeeds, because the engine has silently switched backends for the whole server.

- On SGLang the engine aborts the request with a compile failure.

- Pin vLLM's backend with --structured-outputs-config.backend xgrammar and send the schema again, and expect HTTP 400.

EvidenceUNVERIFIED on a rented GPU; backend behaviour verified at vLLM v0.29.0 source.

Do E1 and E2 before you rent anything, because they are the preparation that keeps the five paid exercises inside $3 to $5. Work E3 to E7 from the notes you wrote in E2, and record what you see wherever an expected value is marked unverified.

## Checkpoint 4A

Five scenarios, each one a situation from the phase. Write your own answer before you open the sketch.

-
 Q1 rental clock
Show the arithmetic. You rent one H100 at $3.49 per hour. Your model is 140 GB. The machine's measured downlink is 276 Mbps.

- How long does the download take?

- What does that download cost in GPU time?

- You plan eight one-hour sessions this month. Compare downloading each time against a cached volume at $9.80 per month.

- Name the cost of the volume that is not money.

Answer sketch
(a) 276 Mbps is 34.5 MB/s. 140,000 MB / 34.5 = about 4,058 seconds, which is 67.6 minutes. (b) 67.6 minutes at $3.49 per hour is about $3.93, so on that machine the download alone is longer than a one-hour rental. (c) On a fast link each download costs roughly $0.34 to $1.09, so eight downloads cost $2.72 to $8.72 and the $9.80 volume is close to break-even; it becomes cheaper above about 9 to 29 downloads a month. On the slow machine above, eight downloads cost 8 × $3.93 = $31.44, so the volume is much cheaper. (d) A network volume ties your work to one datacentre, which reduces the GPUs you can get and removes failover options.

-
 Q2 defaults
A colleague says: "I benchmarked both engines on defaults. vLLM was faster, so we should use vLLM." Give three specific reasons why that result may mean nothing. One reason is about batching defaults, one is about memory flags, and one is about the client.
Answer sketch
First, each engine chooses its batching defaults at startup from GPU memory and from the entry point used, so the defaults differ before you type anything. Second, --gpu-memory-utilization and --mem-fraction-static count memory differently, so equal-looking values do not give equal KV cache. Third, each engine's own benchmark client is different, so a fair test uses one client against both servers. Two public comparisons went wrong in exactly these ways: one was retracted over a flag-mapping error, and another fell from a 2x gap to 8.6% when the request count rose from 50 to 2,000.

-
 Q3 startup failure
Your server refuses to start with a message about KV cache memory.

- Name the two different vLLM messages this could be, and how you tell them apart.

- For the second one, name the number in the message that tells you what to do.

- State what the matching SGLang message asks you to do, and explain why the direction is the opposite of what the flag name suggests.

Answer sketch
(a) The first message says there is no memory for cache blocks at all, because the weights consumed everything inside the budget. The second says the requested context needs more KV than the remainder allows, and it prints both sizes. (b) The second message prints the estimated maximum model length, so set --max-model-len to that value or use --max-model-len auto. (c) SGLang asks you to raise --mem-fraction-static, because that flag is the share of memory the engine reserves, so raising it enlarges the budget inside which the KV pool must fit. The flag names look alike, but the fixes point in opposite directions depending on which error you got.

-
 Q4 grammar backend
Your vLLM server has served plain chat for an hour. A new client sends its first structured-output request, and its schema uses multipleOf on a price field.

- Trace what the engine does with that schema.

- State what happens to every later structured-output request, and why.

- Name the one-line change that would have turned this into an error, and say whether you would want that.

Answer sketch
(a) With the default auto backend, vLLM checks the schema against xgrammar. xgrammar does not support multipleOf on numbers, so vLLM checks whether the schema uses a feature the fallback backends do not support and routes it to guidance or outlines. (b) Every later structured-output request uses that same backend, because the engine resolves the backend once on the first structured request and the source says it does not support different backends per request, so one client's schema has changed the server for every client. (c) Pin --structured-outputs-config.backend xgrammar, which removes the fallback and returns HTTP 400 for that schema. In production you usually want this, because a clear failure on one request is better than a silent change that affects all requests.

-
 Q5 experiment design
You have one hour of rented GPU and want a defensible comparison of the two engines for your workload. Write the plan. Cover what you prepare before the clock starts, which client you use and why, which flags you pin, what traffic you replay, and the two numbers you take away.
Answer sketch
Before the clock starts, write both launch commands and the client command with the model id already in it, note the driver check and the model size, and use a cached volume if you will repeat the session. Use one client, bench_client.py, against both servers, because each engine's own harness is different. Pin the context flags to the same value on both sides, and pin the batched-token and concurrent-sequence flags using the flag map, so two different sets of defaults do not sneak into the comparison. Replay the mixed-size trace instead of one prompt, because prefill cost grows with prompt length and real traffic has a spread of lengths. Take away peak output tokens per second and TTFT p99 at that concurrency, which together are the operating point, and the first feeds Phase 4B's cost arithmetic.

## Cheatsheet

RENTING
  budget for this phase: $5-10        the clock runs during the DOWNLOAD
  H100 $/hr on 2026-09-13: market 1.87-2.00 | RunPod 1.99-3.49 |
    Modal 3.95 | Lambda 3.99 | CoreWeave 6.16 | AWS p5.4xlarge 6.88
  the real specialist-vs-hyperscaler gap is 3.68x, NOT the 10x you will read
  billing: Modal/RunPod/Vast per SECOND | Lambda per MINUTE and while IDLE
  stopping a pod can DOUBLE the volume rate, from $0.10 to $0.20/GB/mo
  140GB download: 4.7 min at 500 MB/s ... 67.6 min ($3.93) at 276 Mbps
  volume pays for itself at ~9-29 re-downloads/month, and pins you to one region
  use hf_xet, NOT hf_transfer (deprecated) | hf download --dry-run

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
    --performance-mode throughput DOUBLES both
  SGLang auto-tunes chunked prefill by GPU memory; fraction falls back to 0.88
  PIN THEM EXPLICITLY before comparing anything

WHEN IT WILL NOT START
  "max_model_len ... is greater than the derived" -> above the model's limit
                                  (Qwen3-8B max_position_embeddings = 40960)
  "No available memory for the cache blocks"  -> weights ate everything
  "estimated maximum model length is Z"       -> use Z, or --max-model-len auto
  PyTorch CUDA OOM + fragmentation hint       -> memory fraction too high
  SGLang says RAISE --mem-fraction-static, its help says LOWER it on OOM
                                  -> the direction depends on which error you got
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
  the only audited comparison (Krai, MLPerf v5.1, 8xH200, Llama-3.1-70B):
    SGLang +18-19% on pre-quantized FP8 | vLLM +2-12% on dynamic FP8
    -> the winner FLIPS with the quantization path

THE COMMANDS
  bench_client.py --dry-run --trace ...            plan it, offline
  bench_client.py --base-url ... --model ...       measure it
  vllm bench serve / python -m sglang.benchmark.serving   the engines' own
  vllm collect-env / python -m sglang.check_env    before filing a bug

VERSION DRIFT
  flags pinned to vLLM 0.29.0 and SGLang 0.5.19
  current as of 2026-10-04: vLLM 0.30.0, SGLang 0.5.20
  re-check every flag against current source before the paid session

## What you could post

- The download bar chart: same 140 GB model, same $3.49 GPU, one machine at 276 Mbps bills $3.93 for 67.6 minutes of download, and another at 500 MB/s bills $0.27 for 4.7 minutes. It is his because he re-derived both numbers himself from the listing's measured downlink, not from a vendor page.

- The one question for any engine benchmark: which flags, which client, how many requests. In the audited Krai table the winner flips with the quantization path, and a 2x gap in one benchmark became 8.6% with 2,000 requests instead of 50.

## Sources

- https://raghu-monitoring.vercel.app/study/inference-internals-phase-04a-serving — his phase; pinned to vLLM 0.29.0 and SGLang 0.5.19, prices and listings read 2026-09-13.

- https://raw.githubusercontent.com/vllm-project/vllm/v0.29.0/vllm/engine/arg_utils.py — the batching-defaults buckets by GPU memory and entry point, the A100 name check, and --performance-mode throughput doubling both; read 2026-10-04.

- https://raw.githubusercontent.com/vllm-project/vllm/v0.29.0/vllm/config/structured_outputs.py — the auto grammar backend docstring: opinionated per request contents, subject to change per release; read 2026-10-04.

- https://raw.githubusercontent.com/vllm-project/vllm/v0.29.0/vllm/v1/structured_output/__init__.py — the single engine-wide backend, initialized from the first structured request; read 2026-10-04.

- https://raw.githubusercontent.com/vllm-project/vllm/v0.29.0/vllm/config/model.py — the --max-model-len auto docstring, the over-context ValueError, and VLLM_ALLOW_LONG_MAX_MODEL_LEN; read 2026-10-04.

- https://raw.githubusercontent.com/sgl-project/sglang/v0.5.19/python/sglang/srt/server_args.py — None-defaults resolved against the hardware, the mem_fraction_static help text, and the grammar backend choices; read 2026-10-04.

- https://github.com/vllm-project/vllm/releases — v0.30.0 is current; read 2026-10-04.

- https://github.com/sgl-project/sglang/releases — 0.5.20 is current, with a changed mem-fraction fallback and chunked-prefill floor; read 2026-10-04.

- https://huggingface.co/docs/huggingface_hub/en/guides/download — hf_transfer deprecated, hf_xet the replacement, hf download --dry-run prints the byte count; read 2026-10-04.

- https://github.com/mlcommons/inference_results_v5.1/tree/main/open/Krai — the one audited head-to-head on identical hardware; conditions verified, row values from the phase; read 2026-10-04.

Every flag claim in this phase is pinned to vLLM 0.29.0 and SGLang 0.5.19. As of 2026-10-04, vLLM v0.30.0 and SGLang 0.5.20 are current, and 0.5.20 already changed the mem-fraction fallback from 0.88 to 0.95. Re-check every flag against the source tag you install before the paid session, and write the date next to each number you re-read.