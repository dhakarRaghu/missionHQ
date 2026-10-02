Phase 3A made your meter agree with the invoice: one usage adapter per provider, and every token priced by its class. The number is now correct. It is also too high. Your team has the same problem the Phase 0 teams had: you send every query to the strong model, because routing easy ones to a cheap model sounds like it returns wrong answers. The alternative your team sketches is a cascade: try the cheap model first, and when its answer looks unsure, ask the strong model instead. The first test shows 88% accuracy at 55% of the cost of the strong model alone, and the room wants to ship it.

Meanwhile the Phase 0 break you could not explain is still invisible to your setup. A timestamp added to the top of your 18,000-token system prompt changes no token count, returns no error and moves no chart you have. Phase 3A showed the response still returns 200 with the same token count, so four months of paying full price for a cached prefix would pass every dashboard you own. This phase connects the two stories. Sending easy queries to a cheap model pays the cheap model even when it loses, so there is an escalation rate where the cascade costs more than the model it avoids. And a break that changes no token count can be caught only by a number that is not a token count. First, the promised saving: at what escalation rate does the cascade stop saving money at all?

This lesson teaches five ideas. They are listed here so you can see where the lesson is going. They will read more clearly once each has been explained below, so come back to this list at the end.

- A cascade pays the cheap model for every query including escalated ones, so it beats deep-only only while the escalation rate stays below 1 minus the price ratio. Predict the escalation rate at which a cascade stops saving, before building anything.
- A cascade with a coin-flip signal still shows good accuracy and low cost, so only a random control that escalates the same count proves the signal carries information. Design the experiment that separates a real signal from an expensive coin flip.
- On strong models, agreement among samples of one model repeats that model's own mistakes, so spend extra confidence calls on different models, not on more samples of one. Choose an escalation signal and reject self-consistency and raw self-reported confidence at a frontier tier.
- A billing-class regression is detected by per-request cost plus per-request cache hit rate, with the floor set just below the measured normal, because the token count never moves. Build the three-rule cost guard that turns a four-month incident into a ten-request incident, and tune its thresholds from the measured normal.
- Every post-hoc cost control enforces against stale spend, so only a pre-call worst-case reservation priced from max_tokens, held at the agent-loop level, can stop spend before it happens. Decide where enforcement must live and bound a retry loop's worst case in currency.

## Where the bill stands after Phase 3A

    Five token classes on the bill

    Phase 3A showed a bill is not input plus output. It has five classes: plain input, cached input, cache write, output and reasoning output, each with its own multiplier.

    Your meter now prices all five, and the invoice finally matches.

    One usage adapter per provider

    OpenAI counts cached tokens inside input_tokens and Anthropic counts them outside it.

    Phase 3A's fix was one adapter per provider that normalises the usage object before your meter sums it.

    The fallback rule in pricing.py

    When the price sheet has no cached price for a model, the code falls back to full price.

    That rule hides a billing class, and this phase shows it can hide a whole incident.

    Cache entries have a break-even

    A cache write is a surcharge, so an entry pays for itself only after enough reads. It needs (write − 1) / (1 − read) reads.

    Phase 3A also showed a broken cache returns 200 OK with the same token count. Only the cached-token count proves it stopped.

Those four ideas make the meter correct. They do not say whether the money is spent well, or whether anyone notices when it stops being spent well. Two stories from Phase 0 are still open.

Story 3 is the team stuck between two bad choices: send every query to the expensive model and overpay on easy ones, or send every query to the cheap model and fail the hard ones. The first half of this phase prices the middle options and shows which choice of signal is worth anything.

Story 1 is the team whose 18,000-token prompt lost its cache for four months while every dashboard stayed green. Phase 3A explained the mechanism, but never built the detector. The second half of this phase builds it. Then it asks what could have stopped the spend instead of only reporting it.

## Why does a cascade pay for some queries twice?

A cascade pays the cheap model for every query, so escalated queries cost more than deep-only ever did.

Story 3's team sits between two bad choices, expensive-everywhere and cheap-everywhere. Both middle options promise the same thing, easy queries on the cheap model and hard ones on the deep model. The two options price that promise differently. So the team can now ask which split of traffic costs less per good answer.

The first option generates before it decides. A cascade sends every query to the cheap model and looks at the answer. Then it sends the hard ones on to the deep model for a second answer. The second option decides before it generates. A router reads the query first and sends it to one model. That model is the only one that runs. In both, the share of queries that land on the deep model is the escalation rate.

    Cascade: decide after generating

- cheap model answersevery query pays Cc

- signal reads the answerfree: the answer already exists

- deep model re-answersescalated fraction e pays Cd again

    Cost per query: Cc + e·Cd

    Router: decide before generating

- classifier reads the querya small fixed cost

- one model answerscheap for 1 − e, deep for e

    Cost per query: (1 − e)·Cc + e·Cd

  Predict: your cheap model costs $1 per million input tokens and your deep model $5. At what escalation rate does the cascade stop saving, and what does the router cost at 35% escalation?
  The cascade breaks even at an 80% escalation rate. At 35% escalation it costs 55% of deep-only, while the router costs 48%. Work it in units of the cheap price Cc = 1 and deep price Cd = 5. The cascade costs 1 + 0.35 × 5 = 2.75 against deep-only's 5. The router costs 0.65 × 1 + 0.35 × 5 = 2.4 against the same 5. The break-even comes from setting 1 + 5e = 5, which gives e = 0.8.

The arithmetic has one step, and it is where the two shapes part. Every query enters the cascade through the cheap model. So Cc appears in its cost with no e in front of it. Escalation then adds a second generation on top of the first instead of replacing it. So an escalated query pays Cc + Cd. That is more than it would have paid going straight to the deep model.

The break-even follows directly. The cascade loses to deep-only when Cc + e·Cd exceeds Cd, which rearranges to one condition:

cascade saves money only while  e < 1 − Cc/Cd
5x price ratio:                 e < 1 − 1/5 = 0.80
at e = 0.35:  cascade  1 + 0.35·5 = 2.75   → 55% of deep-only
              router   0.65 + 0.35·5 = 2.40 → 48% of deep-only

Two things are worth noticing here. The boundary depends only on the price ratio. So a team with an 80% hit rate on the cheap model is sitting exactly at the point. That is where the cascade stops saving. The gap between 55% and 48% is also not about accuracy. It exists even when both signals pick the same queries.

  Cascade and router cost, as a share of deep-only

  Price ratio Cd / Cc

  Escalation rate (%)

  Cascade

  Router

  Cascade breaks even above

The cascade is not strictly worse, because it buys one thing the router cannot. Its escalation signal reads the cheap model's finished answer. So it can notice a wrong-looking or low-confidence response. A classifier reading only the prompt would miss that. The router decides blind, but the cascade decides informed. The informed decision is what the extra Cc on every query pays for.

Measured across five benchmarks and eight models, the structural cost usually wins over the better signal. A lightweight pre-generation router beat the best cascade on four of five datasets. The paper names the double payment, not signal quality, as the cause.

  Evidence
  Bouchard, "Is Escalation Worth It? A Decision-Theoretic Characterization of LLM Cascades" (arXiv:2605.06350, preprint v1, May 2026): five benchmarks across eight models from five providers. Quote: "a lightweight pre-generation router exceeds the best cascade policy on four of five datasets, mainly because it avoids the cheap model's generation cost on queries sent directly to a larger model rather than because of a stronger routing signal." The break-even numbers in this section follow from the algebra alone, so they hold at whatever prices your own invoice shows.

You can run this yourself in this phase's lab: exercise E12 builds the cascade and the random control on the same traffic, and its cascade cost comes close to what the formula predicts: $0.00892 measured against $0.00864.

  A cascade costs Cc + e·Cd per query, so it beats deep-only only while the escalation rate stays under 1 − Cc/Cd.

  "The cheap model handles 80% of queries, so the cascade must be cheaper" is exactly the boundary where it stops saving.

  Take your two models' prices from the sheet and compute 1 − Cc/Cd, then check your measured escalation rate against it.

This section priced the two shapes, but a price says nothing about whether the cascade's signal knows anything. The next section asks which experiment proves the signal works. A broken one can show the same accuracy and cost as a good one.

## The dashboard says the cascade works. Which experiment proves it?

The cascade's dashboard can look perfect while its signal knows nothing, so you need an experiment that convicts it.

You priced Story 3's cascade in the last section, and at 35% escalation it costs 55% of deep-only. That figure is arithmetic, so it comes out the same even when the escalation signal is a coin flip. This section asks what the signal is worth.

### The run that should not look this good

Picture two teams, each with a cascade on the same traffic. In team A the escalation signal is a jitter detector a colleague tuned for a week. In team B it is a random number, and each query escalates with probability 0.35. Now compute what team B's dashboard shows, before looking at team A's.

Predict: both dashboards show 85% accuracy at 69% of deep-only cost. In one, the signal is a coin flip. Which experiment tells them apart, and how is it configured?
The experiment is a random control: same queries, same escalation count, but the escalated queries are picked at random. The real signal beats the random control by less than twice the standard error of the difference. So the dashboard was showing you chance, not information. Configure it by running both on the same traffic and ranking them on dollars per correct answer, explained below.

Why this surprises: you expect a random signal to show a worse accuracy. But swapping the deep model in for 35% of queries at random buys accuracy by luck. It does so at the same cost. The two numbers on the dashboard cannot see the difference.

In the course simulation the coin-flip run prints 85% accuracy at 69.3% of deep-only cost. Those are exactly the lines a team would paste into a review to say "it works". Replacing some cheap answers with deep answers at random buys some accuracy by chance, at the same cost. So a real cascade and a coin-flip cascade look identical on an accuracy and cost dashboard.

### The control that convicts the coin flip

The fix is one more row in the results table. A random control is a cascade that escalates the same number of queries as yours. Those queries are chosen at random, on the same traffic. Your signal earns its cost only when it picks a better 35% of queries than chance picks.

- Run your real cascade and record accuracy and cost per query.

- Run the control with the same escalation rate and random selection, because cost must match for the comparison to mean anything.

- Rank both on dollars per correct answer, the total spend divided by the count of correct answers. Accuracy hides cheap-only's waste and cost hides deep-only's, and this one number punishes both.

- Subtract the control from the real signal, and keep the standard error of that difference, because a gap smaller than about two standard errors can appear by chance alone.

armsignalaccuracycost vs deep-only

cascadereal85%69.3%

cascadecoin flip85%69.3%

The last two rows are identical on the dashboard. So the comparison has to be the bottom row against the one above it. (The phase's coin-flip run, at signal quality 0.5, still showed 85% accuracy at 69.3% of deep-only cost.)

### Why one trial is not enough

Even with the control row in place, one small trial can lie in either direction. With about 20 items per arm, a single accuracy number swings by roughly 7 points between runs. So the gap between signal and control swings by more. Exercise E14 runs the same zero-information signal over three seeds and prints the gap as +10.0, +0.0, and −5.0 points. Seed one would ship the coin flip, and seed three would reject a good signal. The reported number for any cascade experiment is therefore a difference with its interval. It is computed over enough items that twice the standard error fits inside the effect you care about.

This is not a classroom artifact. LLMRouterBench re-ran 10 routing baselines over 400K+ instances. It found that several recent approaches, including commercial routers, fail to reliably outperform a simple baseline. The production version of your coin flip is already sold as a product.

Evidence
The 85%-at-69.3% coin-flip run and the +10.0 / +0.0 / −5.0 seed spread are the course author's simulation runs from 2026-09-17 (E13 and E14), not re-run independently. LLMRouterBench (arXiv:2601.07206, abstract, read 2026-09-30): 10 routing baselines, 400K+ instances from 21 datasets and 33 models. Quote: "several recent approaches, including commercial routers, fail to reliably outperform a simple baseline." The ~7-point swing for a 20-item arm follows from binomial arithmetic.

Exercise E12 builds this experiment end to end. E13 runs it with the coin-flip signal, so you can watch the control row convict it yourself. Reading the E13 output answers one question worth asking first: which of the four rows changed when the signal changed?

A real signal must beat a random control that escalates the same count, ranked on dollars per correct answer.

"88% accuracy at 55% of deep-only cost, so it works" can describe a coin-flip cascade just as well. You then ship noise at deep-model prices.

Open E14, run its three seeds, and check how far one 20-item trial's gap moves between seeds.

This section proved your signal carries information, but it assumed you already chose a signal worth testing. The next section asks which one deserves your extra calls. The most popular choices are the ones this control convicts.

## Which escalation signal deserves your extra calls?

The signal you trust most is the one strong models break worst.

The random control from the last section assumes you have a signal worth shipping. The signals most teams pick first are the ones that control would convict, and the measurements below show why.

A cascade escalates a query when its signal says the cheap model's answer is doubtful. The cheapest signal to build is to ask the same model more than once and check whether the answers agree. If five independent samples all say "Paris", the answer feels safe, so you accept it and skip the deep model. This section shows when that feeling is wrong, and where to spend those extra calls instead.

  One model, 50 samples

  correct answer

  40 of 50 samples agree here, and are wrong

-
  Three models, several samples each

  correct answer

  each model's errors land in a different place

Illustration of the mechanism, not measured data. One model repeats its own mistake, so samples cluster on it. Different models make different mistakes, so only the correct answer collects agreement.

Predict: your audit samples one frontier model 50 times per question, and on 77% of questions the samples strongly agree. What fraction of those agreeing answers do you expect to be wrong?
The measured answer is 48%. Ding drew 265,000 samples across GPQA Diamond and AIME. For the most consistent frontier model, agreement of 0.8 or higher covered 77% of entries, of which 48% were wrong. The stronger the model, the more consistent it is. So the agreeing-and-wrong bucket is a property of the best models, not the weak ones. Agreement was "over-confident yet no more accurate" exactly where the consistency was highest.

Self-consistency is the signal of sampling one model several times and accepting the answer most samples agree on. It fails for a structural reason: the samples are not independent measurements, because they all come from the same weights. A model that has memorised a wrong heuristic produces that wrong answer on every sample. One that favours an answer because of its position in the options produces that wrong answer too. You are not measuring the answer's truth. You are measuring the model's bias, 50 times.

The fix follows from the same cause. Cross-model jury is the signal of sending the same query to two or three different models. It checks agreement across them. Different models are trained differently, so their systematic errors are different. Their wrong answers scatter while the correct answer collects agreement. That is the left panel against the right panel. The same number of calls buys no information from one model and real information from several.

The second popular signal is to ask the model how confident it is, in words or as a percentage. ConfidenceBench scored 15 frontier models on 200 questions using the Brier score. This is the mean squared gap between the stated confidence and whether the answer was right. Lower is better and 0 is perfect:

- The best model scored 0.103, against 0.1875 for a calibrated random guesser, so the best self-reported confidence beats chance but by a modest margin.

- One shipped model scored 0.367, about twice as bad as guessing, so its stated confidence actively misleads.

- The most accurate model was not the best-calibrated one, so you cannot infer a model's signal quality from its answer quality.

Evidence
Ding, "When LLMs Agree, Are They Right?" (arXiv:2607.08065 v2, abstract read 2026-09-30): 53 runners, K=50 samples each. It used 265,000 samples on GPQA Diamond and AIME; agreement-to-correctness correlation 0.20 to 0.59. ConfidenceBench (arXiv:2607.20526, abstract read 2026-09-30): 15 frontier models, 200 private multiple-choice questions; its authors note the 200-question sample is small.

So the rule for choosing where your cascade's extra calls go has three parts:

- Spend extra confidence calls on different models, because their errors are independent and one model's errors are not.

- Reject self-consistency at a frontier tier, because its failure rate on agreeing answers is measured at 48%, not a few percent.

- Calibrate your own model's self-reported confidence on your own queries before trusting it, because published Brier scores show the spread between models is larger than the margin over guessing.

There is no lab exercise for this section, but the arithmetic is worth doing once by hand. Take the Ding numbers above. Assume your cascade accepts every high-agreement answer, and compute the expected error rate among accepted answers. Then compare it with the error rate your eval sample would need. Check whether your random control could even measure a gap.

  Agreement among samples of one model measures that model's bias, so spend confidence calls on different models.

  "Five samples agree, so accept it" accepts 48% wrong answers on the most consistent frontier models, silently.

  Ask your frontier model its confidence on ten questions you know the answers to; compare stated confidence against actual correctness.

With the signal chosen, the cascade and the router have covered traffic where a user is waiting. The next section asks when half price is worth a day of waiting.

## When is half price worth a day of waiting?

Half price for the same tokens, if the answer can wait until tomorrow.

The cascade and the router from the last sections decide while someone is waiting for the answer. Not all of your traffic has anyone waiting. Your nightly eval sweep is in this class. So are the labeling run for a control experiment and the summary job for tomorrow's report. For this traffic both providers sell a third option. A batch API takes a file of requests as one job. Every token in the file is billed at half the usual class price. In return you give up the deadline. The answer arrives within a window of up to 24 hours instead of within seconds.

One job moves through four steps.

- buildone file that holds every request in the job
- submitthe job request points at that file; its body holds no prompt
- waitthe provider completes the job within a window of up to 24 hours
- collectyou download a results file with an answer for each request

The submit step is marked because its request body holds no prompt. That property drives the second half of this phase. First the parameters, which have the same shape on both providers.

  OpenAIAnthropic

    Discount on every token class50%50%

    Completion windowup to 24 hoursup to 24 hours

    File limit50,000 requests or 200 MB100,000 requests or 256 MB

    If the window expirescompleted requests are billed, the rest are notexpired requests are not billed

    Results keptoutput file deleted 30 days after completion29 days

    Prompt-caching discountnot stated on the page readstacks on top of the batch price

Evidence
OpenAI Batch guide, read 2026-09-30: half price, a 24-hour window, 50,000 requests or 200 MB per file. Expired batches bill only completed requests, and output files are deleted 30 days after completion. The Anthropic column is the phase's read of 2026-09-25: 100,000 requests or 256 MB per file. Expired requests are not billed. The caching discount applies on top of the batch price. That column was not re-read since.

The decision rule is one question.

- Is a user waiting for this call?

- yeskeep it live, at full price, routed by the cascade or the router

- nosend it to batch, at half price, answered by morning

Notice what the discount does not change. It halves the cheap model and the deep model by the same factor, so the price ratio is untouched. The cascade's break-even escalation rate still sits at one minus the price ratio. Batch is a choice about time, not about which model answers. The split a team could make runs by workload. User queries stay live on the cascade. Work where no user is waiting, such as an evaluation run, moves to batch. Both halves of the bill drop.

Predict: you submit a 50,000-request batch, and your reservation code must approve the spend before the submit. Which number does it read?
None. The reservation code is the pre-approval check the enforcement sections build later. At the submit call it has nothing to read, because the body carries an endpoint and a reference to the file. The prompts sit inside the file it points at. Your own code could still count the file before submitting, because it just built it. Anything downstream of the submit call sees only the file reference. The first priced rows for the job appear when the results come back, which is after the tokens were spent.

That blind spot is the structural point. A live call carries its prompt and its output cap in the request body. The cap is max_tokens, the field that bounds how many tokens the reply may contain. Your cost code can read both before money moves. A batch submit carries a file reference.

  What your cost code can read before the calllive requestbatch submit

    input tokenscount the messages in the bodyinside the file, unseen

    max_tokens, the output capa field in the bodyinside the file, unseen

    model and endpointin the bodyin the body

- At submit time nothing can price the job, because neither a token count nor an output cap is in the request.

- The provider meters the job while it runs, so the first priced rows exist after the spending started, not before.

- You can still bound it yourself, because you built the file, so count its prompts before the submit and write the total down.

One bookkeeping detail belongs with this. Phase 3A's fallback rule charges any class missing from the price sheet at full price. Batch tokens are their own class. A sheet without batch entries makes every batch job look twice as expensive as it was. The saving you chose batch for would never appear in your ledger.

E12 in the lab, the cascade-versus-control sweep, is exactly this kind of work, because nobody waits on it. On a real provider that sweep is a batch job: same tokens, half price, results in the morning. Before you submit one, check that your price sheet carries the batch entries. Then count the tokens in the file you built, because that count is the only estimate that exists before the submit.

  Batch bills the same tokens at half price whenever the answer can wait until tomorrow.

  The submit call carries only a file reference, so nothing prices the job before spending starts.

  Count the callers of your last eval run who would notice results arriving tomorrow morning.

The next section starts the other half of this phase. It keeps the savings by asking which three rules catch what the token chart cannot.

## Which three rules catch what the token chart cannot?

The routing sections showed how to spend less on each query. This section and the next two keep those savings. They begin with the detector for the failure Phase 3A explained but never caught.

Phase 3A answered why Story 1's dashboards stayed green. A broken cache returns 200 OK with the same token count, because only the billing class changes. What it never covered is the detection setup. This section builds it, as three rules over a per-request ledger.

Predict: tonight a timestamp is added to the top of your 18,000-token system prompt. The response still returns 200 with the same token count. Which of your current dashboards moves, and within how many requests?
None of the token dashboards moves, because the same bytes cross the wire either way. The cache hit rate is the share of input tokens billed at the cached read price. It drops from its normal near 98% to 0% on the first request after the change. The cost per request steps up 5.4x at the same moment. If you record neither per request, the incident is invisible on every chart you have.

### The shape of the failure

In the replay of Story 1, 200 agent steps run and a timestamp enters the system prompt at request 50. Two per-request series tell the whole story.

tokens stay flat through the break cost steps up 5.4x at request 50

The token count is identical on both sides of the break, because the prefix traverses the API either way. The cost jumps from $0.0074 to $0.0398 per request. That is because 18,000 cached tokens at the read price become 18,000 fresh tokens at the full price. Every request after the break costs 5.4 times more, and each one stays far below any extreme value.

Evidence
Author's replay runs of the Story 1 scenario, 2026-09-17, kept in the course material. Cost per request $0.007400 before request 50, $0.039800 after. Firing points: rolling cost at request 52, cache rule at 59 with the default 50% floor. It fires at 51 with a 90% floor, and at 50 with a 5-request window.

### The three rules

One rule is not enough, because cost rising and cache breaking are two facts and you want both. The guard runs three checks on every recorded request.

  RuleWhat it checksWhat it tells you

  Per-request budgetone request's cost against an absolute ceilinga single extreme call, such as an unbounded input

  Rolling cost rulethe mean cost of the last N requests against a baseline multiplethat cost rose, but not why

  Cache hit floorthe windowed cache hit rate against a floorwhy it rose, when the cause is the cache

The rolling cost rule compares the average cost of a recent window against a baseline. It fires at request 52 in the replay, two requests after the break. The cache hit floor compares the windowed hit rate against a threshold, and it fires at request 59. The split matters in an incident at 3am. The first rule says spend moved. The second says the cache is the place to look.

The per-request budget is the rule most teams already have, and it is the one this failure defeats. A regression that raises every request uniformly by 5.4x produces no outlier. Each request is ordinary on its own. A ceiling set high enough to avoid false alarms on long inputs sits above every single one of them. Detection of uniform damage needs an average over recent requests, not a per-request extreme.

### Why the pricing sheet decides whether any of this works

The replay runs twice, once per role, and the difference is Phase 3A's fallback rule. The pricing.py rule from that phase says an unknown price falls back to full price. That is the safe direction for an invoice estimate, and the wrong direction for this detector.

- With a cached price in the sheet, the meter prices cached reads at the discount, so cost per request is low while the cache works and steps up when it breaks.

- Without a cached price in the sheet, the meter prices cached tokens at full price, so the cost line is flat before and after the break, and no cost rule fires on the whole incident.

The cache rule still fires in the second run. It reads the hit rate recorded through the usage adapter. The adapter is the per-provider function that maps each usage object onto the five token classes. The cost rules stay silent. A missing row in a pricing sheet hides a billing-class regression from the cost side completely. So the price sheet is part of the detector and not a reporting detail.

### Two design decisions in the guard worth copying

The guard keeps two small disciplines that make its alerts trustworthy.

- Record one ledger row per request. The row carries the five token classes from the usage adapter, the priced cost per class, the total, and the computed hit rate. Every rule reads this row, so the alert and the invoice always agree about what one request cost.

- Fire once per run per rule. After a rule fires it stays quiet for the rest of the run. A rolling rule over a broken cache would otherwise alert on nearly every request, and the fifty-first identical alert carries no information the first one did not.

  A broken cache moves only the billing class, so detect it with per-request cost and hit rate, not tokens.

  A per-request outlier cap catches nothing here: every request rose 5.4x and each one stayed ordinary.

  Add cost and cache hit rate to one request log line; check that both survive one normal call.

Both rules fired within ten requests of the break. But the cache rule fired second, at request 59, seven after the cost rule. That gap is a tuning mistake with arithmetic behind it. The next section asks why a tidy 50% floor detects nothing.

## Why does a tidy 50% floor detect nothing?

Both rules fired within ten requests. But they fired in the wrong order: the rolling cost rule at request 52, the cache hit floor at 59. That gap is not bad luck, and it is not noise, because the same run produces it every time.

The situation is Story 1. Someone added a timestamp to the top of your 18,000-token system prompt, so every cache read now misses. The cost rule fired fast because the price jumped 5.4x at request 50. The cache hit floor watched the same break and stayed quiet for nine requests.

The reason is one line of arithmetic. The floor counts the distance from your normal hit rate to the threshold, in units of windowed-average travel. Before the break your rolling average sits at 98%. After the break every request reports a hit rate of zero. So the rolling average walks down from 0.98 toward zero, one zero-hit request per step.

gap to cross          = normal − floor = 0.98 − 0.50 = 0.48
travel per bad request ≈ normal / window
requests to fire      ≈ window × (normal − floor) / normal
                      = 20 × 0.48 / 0.98 ≈ 10  (fires at request 59, measured)

A floor of 50% is 48 points below the 98% normal. The walk takes about ten zero-hit requests, so the rule fires at request 59. Seven requests after the cost rule, from the detector built specifically for this failure.

  Requests before the cache rule fires

  Measured normal hit rate

  Floor

  Window (requests)

  Zero-hit requests to fire

Illustration of the mechanism, not measured. The replay's measured firing points are 59 (floor 0.50), 51 (floor 0.90) and 50 (window of 5).

Two knobs close the gap, and both follow from the same formula:

- Raise the floor to just below the measured normal. A floor of 0.90 cuts the gap from 48 points to 8, so the walk is shorter and the rule fires at request 51 in the replay.

- Shrink the window. A 5-request window makes each zero-hit request move the average more, and in the replay both rules then fire at request 50, the first broken one.

The side-effect is also arithmetic. A small window on noisy normal traffic produces false alarms. Two unlucky misses in five requests can dip a 0.98 average below 0.90. A large window absorbs noise but pays for it in detection lag. You are trading false alarms against lag, and the formula above prices the trade.

One more decision matters as much as the numbers. The floor must come from a baseline stored outside the process. It must not be a constant in the code that ships the prompt. The Story 1 failure was a prompt change. So anything measured at startup measures the already-broken system and calls it normal.

Evidence
Firing points are the author's replay of Story 1 (runs of 2026-09-17). The rolling cost rule fired at request 52. The cache rule fired at 59 with the default 0.50 floor. It fired at 51 with a 0.90 floor, and at 50 with a 5-request window. The travel formula is the arithmetic of a rolling average over a window, so it is derived, not measured.

  Set the floor just below the measured normal, because a round number pays the gap in detection lag.

  A tidy 50% floor on a 98% workload fires nine requests late, after the cost rule it was meant to beat.

  Measure your cache hit rate for a week, then compute the lag for floors 0.50 and 0.90 at your window.

Both rules now fire fast and tell a human that cost moved, but nothing so far stops a request. The next section asks what can actually stop spend. The answer depends on when each system learns what you spent.

## Alerting is not enforcing. What can actually stop spend?

Both alert rules from the section above tell a human that cost moved, but nothing so far stops a request from going out.

Stopping spend depends on when each system learns what you spent.

Think about one request, and about every control you could put around it. Your rolling cost rule reads spend after the response lands. Your provider's cap reads spend after the provider records it. The invoice shows spend weeks later. Each of these is a good meter and a bad brake, because by the time any of them reacts, the tokens are already billed.

The picture is a timeline of one request. Every control that reads the bill sits after the call. The only point that can stop the call sits before it.

-

  pre-call
  reservation
  can reject

  provider call
  tokens generated

  post-call
  rolling rule, ledger

  provider cap
  reads recorded spend

  invoice
  weeks later

Three of the four controls react after the tokens exist. Only the pre-call point can refuse.

Predict: you set a hard spend limit with your provider. Does it stop a runaway retry loop?
No, for three separate reasons. The limit runs on a monthly interval, so a loop can spend a large share of the month in an hour before the counter updates. It applies at org or project scope, so it cannot single out one broken job. And OpenAI's own documentation says enforcement is not instantaneous, so recorded spend can exceed the configured amount while the limit state propagates. A provider cap guards the account's month. It does not guard your loop's next call.

The fix has one idea. Charge the call against a budget before you send it. A pre-call reservation prices the call's worst case, holds that amount against the budget, and releases the difference after the response. If the reservation does not fit the budget, the call is rejected and the provider is never contacted.

- Read max_tokens from the request. The output size is the only unknown, so the worst case replaces it with its bound: every input token plus max_tokens output tokens at full price. This is why max_tokens becomes a required field in a cost-controlled system.

- Price the worst case. Multiply by the price sheet your usage adapter from Phase 3A already keeps, one entry per provider and cache class.

- Reserve. Hold that amount against the budget. If it does not fit, reject the call now.

- Call the provider. The call goes out only inside its reservation.

- Settle. The response returns actual usage, so release the reservation and charge the real cost, which is lower in almost every case.

The reservation is a documented pattern, not a proposal. LiteLLM's proxy has budget reservation on by default, and it pre-authorizes the estimated maximum cost before sending the request. Its fail-closed mode revalidates against the database on every request and rejects with a 503 when spend cannot be verified. Proxy deployments without a database fail the other way, with budgets skipped entirely. Decide which way your guard fails: closed, like LiteLLM's 503, or open, where enforcement is gone and no error says so.

Evidence
OpenAI spend-limits doc, read 2026-09-30: hard limits are monthly-interval, org or project scope, and the page states "Enforcement is not instantaneous, so recorded spend can slightly exceed the configured amount while the limit state propagates." LiteLLM budget docs, read 2026-09-30: reservation enabled by default, fail-closed mode rejects with 503, DB-less deployments fail open.

Spending the reservation at worst case feels wasteful, so you might ask whether predicted output length can shrink it. It cannot carry that duty. Output-length predictors report a mean absolute error of roughly 93 to 103 tokens. On a 200-token answer, that average error amounts to about a 50 percent cost error. A predictor is fine for scheduling. The billing bound must be a number you can trust to be high enough, and max_tokens is the only such number in the request.

A batch submission cannot be reserved at all. The batch API from earlier in this phase takes a file reference, and the file can hold thousands of prompts, so nothing can price the submission when you send it. Batch needs a different control, and estimating the file's token count before submitting is the available one.

When a reservation does not fit, you have three responses, not two. You can alert and let the call through, which informs but does not spend. You can hard-stop with an error. Or you can choose a degrade response: route the rejected call to a cheaper model so the work completes at the price your budget allows. LiteLLM's docs note that a zero-cost fallback model bypasses budget checks, which makes this third path possible but also easy to misconfigure.

One gap stays open. A stream that crosses the budget mid-response is a case almost no system documents, so whether the stream is cut, finished or billed is a behaviour you test before you promise it.

Only a pre-call reservation priced at the max_tokens worst case stops spend before it happens.

A provider hard cap feels like a guard, but its monthly clock and propagation lag let a loop overspend inside the limit.

Take one of your calls, price input plus max_tokens output at full price, and compare with its last actual bill.

The reservation bounds one call, but your worst risk is a loop of calls, and a per-request bound multiplied by an unbounded loop bounds nothing. The next section asks: what bounds a loop, not a request?

## What bounds a loop, not a request?

The reservation from the last section bounds one call. But the failure this phase warns about most is a loop of calls. A per-request bound multiplied by an unbounded loop is no bound at all.

Your evening project is a multi-agent system with retry loops. One of those loops calls a model up to 50 times in a session. You have priced the worst case of each call. You have not yet asked what the loop, taken as a whole, can spend.

The picture is a small one. A reservation is a ticket the loop buys before each call. It is priced at the worst case: the full input plus max_tokens of output. A loop of N calls buys up to N tickets. So the worst case of the loop is N times the worst case of one call. That product is the only thing that can stop the loop before it starts spending. The fix is a session budget, a reservation held at the level of the whole loop. At loop start you reserve N times the per-call worst case, and each iteration settles its actual cost against it. The code that enforces the session budget is the iteration cap, and now the cap is arithmetic instead of advice.

- Price one call at worst case: full input tokens plus max_tokens of output, at the price sheet rates. This is the pre-call reservation, a worst-case estimate you hold in the budget before the provider sees the request.

- Multiply by the iteration cap: worst case per call times N is the session's worst case, in dollars, before any call runs.

- Reserve the session, not the request: at loop start, hold that product against the session budget. If it exceeds the budget, stop before the first call.

- Settle each iteration: after each response, replace that call's reservation with its actual cost. The remaining headroom tells you how many iterations are still affordable.

- Stop at the cap, not at the provider: the loop's own code refuses iteration N+1 when the budget is exhausted, because no vendor control fires that early.

Why per-request reservations cannot do this: each new call is priced and approved on its own. It has no memory of the 49 calls before it. The session budget adds exactly that memory: one running total the loop owns, checked before each iteration.

  Worst case of a retry loop

  Iterations

  Input tokens per call

  max_tokens

    Per-call worst case
    Session worst case

With the defaults (18,000 input tokens, 2,000 max_tokens, a $3/Mtok input and $15/Mtok output model, prices chosen to show the shape rather than read from your sheet), one call reserves 18,000 × $3/Mtok + 2,000 × $15/Mtok = $0.084, and 50 iterations reserve $4.20. The two sliders that matter are not the prompt but N and max_tokens: they are the two numbers your code already controls, and the session budget turns both into a hard dollar figure before the first request leaves.

The incident that shows the endpoint of having no such ceiling is METR's. A stolen API key on a fail-open internal app spent about $600,000 of API credits over about three weeks, and the post-mortem names three detection failures: the volume looked normal to a team acclimated to high usage, the dashboard never recorded the rate-limited calls that would have shown the pattern, and "because we were not paying for these tokens, there was no natural token spend ceiling". All three are the same gap at different distances: no per-request baseline, no recorded signal, and no loop-level bound. The session budget is the third one, and unlike the first two it works even when the other two fail, because it does not depend on anyone noticing anything.

Evidence
  METR, "Update on Security at METR", metr.org, 31 August 2026, read 2026-09-30. The dollar figure, the three-week window and the three quoted failures come from the incident post itself. The calculation defaults (18,000 input tokens, $3/Mtok, $15/Mtok) are an illustration chosen to show the shape, not measured values.

Use it on your own code: pick the most expensive loop in your agent project, set its iteration count, its prompt size and its max_tokens in the calc box, and write the session worst case in a comment next to the loop. If the number surprises you, that is the reservation doing its first job: making the worst case visible before it happens.

  The unit of cost control for an agent is the session: iterations times worst-case per call, reserved before the loop starts.

  A per-request reservation on each call of a loop bounds no loop. METR ran three weeks and $600k with no ceiling at all.

  Compute N × (input + max_tokens × rate) for your longest loop and put that number in its source file.

The phase is now complete in what it set out to teach. The recall section collects the five claims, and the next phase, Renting a GPU and Serving a Model, asks what changes when the per-token bill becomes a GPU-hour bill and your metering must live in front of a server you run yourself.

## What you can do now, and what comes next

You started this phase with the invoice reconciled and two stories still open. One was the team locked between expensive-everywhere and cheap-everywhere. The other was the team whose cache broke for four months behind green dashboards. Read the five claims again. They should now read like things you would say to a colleague.

- A cascade pays the cheap model for every query, so it beats deep-only only while the escalation rate stays below 1 minus the price ratio. At a 5x price ratio the cascade stops saving above 80% escalation. The section "Why does a cascade pay for some queries twice?" derived this from one cost line, and the batch section added the third option when no user is waiting.

- A cascade with a coin-flip signal still dashboards well, so only an equal-count random control proves the signal carries information. The broken-signal run showed 85% accuracy at 69.3% of deep-only cost with zero information. The section "The dashboard says the cascade works. Which experiment proves it?" built the control and the standard-error rule.

- On strong models, self-agreement repeats the model's own mistakes, so spend extra confidence calls on different models, not on more samples of one. 48% of a frontier model's high-agreement answers were wrong. The section "Which escalation signal deserves your extra calls?" ranked the signals.

- A billing-class regression leaves the token chart flat, so detection needs per-request cost plus a cache hit floor set just below the measured normal. The two alert sections turned Story 1's four months into ten requests, and showed why a round 50% floor on a 98% system detects late.

- Every post-hoc control enforces against stale spend, so only a pre-call reservation priced from max_tokens, held at the loop level, stops spend before it happens. Provider caps fail three ways, and the session budget is iterations times the worst case per call. The last two sections built both.

After the lab you can ship a routing change behind a control group and gate it. You can also build a cost guard that stops spend before it happens, loops included. Both close the running stories. Story 3 gets a router with an experiment attached, and Story 1 gets the three rules that would have caught it.

One assumption runs under everything this phase taught: the bill arrives per token from someone else's server. The next phase is Renting a GPU and Serving a Model. It asks what changes when the bill becomes a GPU-hour on a server you run. Your metering must sit in front of it. The per-request ledger, the control-group discipline and the reservation all carry over. The pricing inputs do not.

## Lab: replay the incident and break the signal

Each exercise below re-runs one claim from this phase. Run them in order: the first three replay Story 1, the last three replay the cascade experiment. All expected values are the lesson author's run of 2026-09-17. Small differences in your run are fine, but the shape is not.

-
 E9 offline
Replays concept: a billing-class regression leaves the token chart flat, so per-request cost and the cache hit floor are the detectors.
Run the Story 1 replay. A timestamp is inserted at the top of the 18,000-token prompt at request 50, and both alert rules are active.

Run: the incident replay, rules on

Watch two things. The token-per-request line stays flat through the break. The cost per request steps from $0.007400 to $0.039800 at request 50, a 5.4x rise. The same bytes now bill as full-price input instead of cached read. The rolling cost rule fires at request 52, the cache hit rule at 59 with the default 50% floor.

Then run it with a price sheet that has no cached-price row: --role cache_demo removed. So Phase 3A's fallback rule prices every token at full input price both before and after the break. The cost line is flat and no cost rule fires. The incident becomes invisible, because the meter was never told what a cached read costs. This is why the price sheet is part of the detector, not just the invoice.

-
 E10 offline
Replays concept: a round-number floor sits far below the measured normal, so the windowed average must travel the gap before it crosses.
Repeat E9 twice, changing one knob each time. The system's normal hit rate is 98%.

Run: the replay with the cache floor at 0.90, then again with a 5-request window.

With the floor at 0.90 the cache rule fires at request 51, one request before the cost rule, which fires at 52. With a 5-request window both rules fire at request 50, the first broken request. Compare with E9's defaults: floor 0.50 fired at 59. The distance from 98% normal to a 50% floor is 48 points of average to travel. That travel time is the four-month delay in miniature. A smaller window detects sooner but noisier, which is the trade to tune on your own traffic.

-
 E11 offline
Replays concept: the rolling cost rule tells you that cost moved; the cache rule tells you why, and each covers a failure the other misses.
Run: the replay with --no-cache-rule.

Only the rolling cost rule fires, at request 52, and the alert says "cost went up" with no cause. Now picture the opposite run: the price sheet raises the full-input price overnight with the cache healthy. The cost rule fires, the cache rule stays quiet, and the cause is pricing, not caching. One rule is the symptom detector, and one is the cause detector. Removing either leaves a class of incident with no explanation attached.

-
 E12 offline
Replays concept: a cascade beats deep-only only below the break-even escalation rate, and only the random control proves the signal earns it.
Build the cascade from the section on double payment, and run it on the simulated traffic. Then run the equal-count random control: the same number of escalations, chosen at random. Rank both by dollars per correct answer, not by accuracy alone.

Expected shape: accuracy sits between cheap-only and deep-only, and cost sits below deep-only. The cascade row clearly beats the random-control row on dollars per correct answer. If it does not, your signal is buying accuracy by chance, and the next exercise shows what that looks like.

-
 E13 offline
Replays concept: a coin-flip signal still produces a good-looking accuracy-and-cost dashboard.
Run: the cascade with --signal-quality 0.5, a signal no better than a coin flip.

The bare dashboard still reads 85% accuracy at 69.3% of deep-only cost, the kind of line a team would ship. The gap over the random control falls to +0.4 accuracy points, inside two standard errors. Nothing on the accuracy or cost chart tells you the signal carried no information. Only the comparison against the equal-count control convicts it.

-
 E14 offline
Replays concept: small eval sets swing several points per trial, so one trial of the control experiment proves nothing.
Run: the E13 comparison three times, one seed each.

The same zero-information signal prints +10.0, +0.0 and −5.0 accuracy points against the control across the three seeds. One 20-item trial swings about 7 points. So a single run can make a coin flip look like a real signal. A real signal can look like noise. This is why the gating checklist ends with a confidence interval over several trials, not one green run.

Two claims in this phase have no exercise: the bad-signal audit (compute the wrong-answer fraction of a frontier model's high-agreement answers from the numbers in the signal section) and the reservation (price one call at worst case, then multiply by the loop's iteration cap). Both are five minutes of arithmetic on numbers you already have, and the checkpoint asks both.

The checkpoint now asks the same questions without the simulator. It asks the cascade arithmetic at 35% escalation and the control experiment's exact configuration. It asks where a reservation must live to bound a loop.

## Checkpoint 3B

Answer each one in your own words before you open the answer sketch. Every number you need is in the question.

- Cascade versus router. Your cheap model costs $1 per million input tokens and your deep model $5. Your measured escalation rate is 35%. What does the cascade cost as a fraction of deep-only, and what would a pre-generation router cost on the same traffic?
Answer sketch
The cascade pays the cheap model on every query plus the deep model on the escalated fraction, so its cost per query is Cc + e·Cd. Dividing by deep-only: Cc/Cd + e = 1/5 + 0.35 = 0.55, or 55% of deep-only. The router pays once per query: 65% of queries go cheap and 35% go deep, so 0.65·(1/5) + 0.35·1 = 0.13 + 0.35 = 48%. The 7-point gap is the cheap generation the cascade paid for on the escalated queries, and the pre-generation router never pays it.

- The control experiment. Two dashboards both show 85% accuracy at 69% of deep-only cost. In one, the escalation signal is a coin flip. Which experiment tells them apart, and exactly how is it configured?
Answer sketch
Run a random control: a second cascade that escalates the same count of queries, chosen at random, on the same evaluated sample. Rank both by dollars per correct answer, not by accuracy or cost alone, because the coin-flip cascade matches the real one on both. Compare the gap against its standard error: one 20-item trial of this course's simulator swings about 7 accuracy points, so repeat over several seeds and demand a gap beyond two standard errors. The course's signal-quality-0.5 run failed exactly this test: gap of +0.4 points, inside the noise.

- The provider cap. A colleague says a hard spend limit with the provider makes a runaway retry loop safe. Give three independent reasons it does not, and name the one control that bounds the loop.
Answer sketch
The provider's hard limit fails three ways, from its own documentation: the interval is monthly, so the loop can spend the month's budget in an hour while staying inside the cap; the scope is org or project only, so there is no per-job limit and one broken job trips the cap for everyone; enforcement is not instantaneous, so spend overshoots while the limit state propagates. The control that bounds the loop is a session budget at the agent loop: a pre-call reservation priced at worst case (full input plus max_tokens of output) held per session, with a hard iteration cap. Both live in your own code, because the unit of control is the loop, not the request.

- The ship-it proposal. A teammate proposes this escalation signal for your frontier-tier cascade: sample the model five times, and accept the answer without escalating when the samples agree or the model reports confidence above 90%. What is wrong with it?
Answer sketch
Both halves spend extra calls on one model's agreement with itself, which repeats that model's own systematic mistakes. Ding's audit of 265,000 samples found the most consistent frontier model agreed strongly on 77% of entries and 48% of those were wrong, so this signal accepts nearly half of the model's confidently wrong answers and escalates almost nothing. Self-reported confidence is also measured as broken: one shipped model scored a Brier of 0.367, about twice as bad as calibrated guessing at 0.1875. If extra calls buy a signal, spend them on a cross-model jury, because different models make different mistakes and their wrong answers scatter.

- The mid-stream breach. Your reservation passes a request priced at worst case $0.10 against a remaining budget of $0.12. Mid-stream, the model produces a much longer thinking block and the request's true cost crosses $0.12. Is your budget guarantee intact, and what must you verify before promising it?
Answer sketch
The reservation itself is intact, because it was priced at worst case: full input plus max_tokens of output, so no response can cost more than was reserved. The real question is what happens on the next request: settle-to-actual must run before that request's reservation is checked, or the budget reads stale. What mid-stream cancellation does when actual spend would exceed the reservation is undocumented almost everywhere, so test your gateway's behaviour before you promise a caller that a stream stops at the budget line.

- Prediction versus reservation. A plan replaces worst-case reservations with an output-length predictor (error about 100 tokens) and prices each call at the predicted length, arguing this admits more requests under the same budget. Accept or reject?
Answer sketch
Reject for enforcement, keep for scheduling. An error of about 100 tokens is a 50% cost error on a 200-token answer, and the prediction errs in both directions, so under-predictions breach the budget after the call has already started. Enforcement needs a bound, not an estimate: only the worst case from max_tokens guarantees the reservation covers whatever the stream returns. The predictor is still useful where a wrong estimate costs nothing, such as batching or scheduling decisions that can be revised.

A wrong answer on 3, 5 or 6 is one idea revisited: enforcement only works before the spend exists. Re-read the reservation section, then try those three again.

Q1, Q2 and Q4 design and validate the routing change; Q3, Q5 and Q6 keep the savings. The cheatsheet that follows fits all of it on one screen.

## Cheatsheet

ROUTING
  cascade cost = cheap x ALL + deep x escalated     (escalated queries pay twice)
  router  cost = cheap x easy + deep x hard + classifier
  cascade beats deep-only while   escalation rate < 1 - (cheap/deep)
  RANK BY DOLLARS PER CORRECT ANSWER, never by cost alone
  ALWAYS run the random control: escalate the same COUNT at random
  signal strength: cross-model jury > calibrated token confidence >
                   self-reported (varies by model) > self-consistency (weak)
  CPT = the % of strong-model calls needed to hit your quality target

BATCH
  50% off on both major providers | 24h window
  cannot be budget-reserved: the request carries a file, not the prompts
  inside a batch use the 1-hour cache tier, not the 5-minute one

COST ALERTING
  three rules: per-request budget | rolling cost (THAT it rose)
               cache hit floor (WHY it rose)
  set the floor just under your MEASURED normal, not at a round number
  fire each rule once per run; a rule that pages every request gets muted
  record per request: route, cost, naive_cost, uncached_in, cached_in,
                      cache_write, out, cache_hit_rate
  a broken cache does NOT change your token count. Only the class changes.
  no cached price in the sheet -> cost looks flat -> rolling rule is blind

ENFORCEMENT
  alert (traffic continues) | hard stop (429) | degrade (cheaper model, no error)
  only a PRE-CALL RESERVATION stops spend before it happens
    reserve worst case from max_tokens -> reject -> settle to actual
  output length is NOT predictable: best-in-class MAE ~100 tokens
  every other control is enforced against stale spend, by the vendors' own words
  provider caps: monthly only, org or project scope, "not instantaneous"
  mid-stream breach behaviour is undocumented almost everywhere

THE COMMANDS (part B)
  cascade_lab.py --self-test                      -> the scorer, offline
  cascade_lab.py --simulate                       -> cascade vs the control
  cascade_lab.py --simulate --signal-quality 0.5  -> an expensive coin flip
  cascade_lab.py --simulate --trials 1 --seed N   -> how badly one run lies
  budget_guard.py --self-test                     -> the three rules, offline
  budget_guard.py --simulate --role cache_demo    -> Story 1: alerts at 52, 59
  budget_guard.py --simulate --role cache_demo --cache-floor 0.90 -> fires at 51
  budget_guard.py --simulate --role cache_demo --no-cache-rule    -> symptom only

## What you could post

Two post ideas. Each is one claim plus the number that makes it yours.

    The coin flip that dashboards well

    In a cascade lab, a coin-flip escalation signal still showed 85% accuracy at 69% of deep-only cost on the dashboard.

    What makes it yours: you ran the simulation yourself, and only the equal-count random control convicted it.

    The alert floor that detects nothing

    With a cache floor at 50% and a normal hit rate of 98%, the rule designed for the outage fired nine requests late.

    What makes it yours: you can replay Story 1, watch the floor travel the gap. Then move it and catch request 51.

## Sources

Every source below was opened and checked on 2026-09-30. Each line says what this phase took from it.

- arxiv.org/abs/2305.05176 — FrugalGPT, the paper that defined the LLM cascade; the section "Why does a cascade pay for some queries twice?" uses its two-part definition, scorer plus threshold.

- arxiv.org/abs/2605.06350 — Bouchard, the pre-generation router beating the best cascade on four of five datasets, with structural cost named as the cause (verified at abstract level, preprint).

- arxiv.org/abs/2601.07206 — LLMRouterBench, ten routers re-run over 400,000+ instances, several failing to beat a simple baseline; the field-scale version of the coin-flip control.

- arxiv.org/abs/2607.08065 — Ding, "When LLMs Agree, Are They Right?", 265,000 samples; the 48%-wrong high-agreement result and the 0.20 to 0.59 correlations.

- arxiv.org/abs/2607.20526 — ConfidenceBench, 15 frontier models scored by Brier score; best 0.103 against calibrated-random 0.1875, one shipped model at 0.367.

- arxiv.org/html/2406.18665v4 — RouteLLM, the CPT metric and the rule that every routing number names its benchmark.

- metr.org/blog/2026-08-31-security-update — METR's incident post: about $600,000 over three weeks, and the three named detection failures that map onto the three alert rules.

- docs.litellm.ai/docs/proxy/users — LiteLLM budget docs: reservation on by default, pre-authorizing worst-case cost, and the fail-closed mode that rejects with 503.

- developers.openai.com/api/docs/guides/spend-limits — OpenAI spend limits: monthly interval, org or project scope, and the vendor's own line that enforcement is not instantaneous.

- developers.openai.com/api/docs/guides/batch — OpenAI Batch guide: 50% discount, 24-hour window, 50,000 requests or 200 MB per file, and results now documented as deleted 30 days after completion.

  Five papers the study note could not open stay unverified here: the Routing Collapse Index (arXiv:2602.03478), the jury paper (arXiv:2607.10139), UCCI (arXiv:2605.18796), AutoRelAnnotator, and RLM-Cascade. The signal-ranking claim in this phase rests on Ding and ConfidenceBench, both verified. The output-length prediction error of about 100 tokens came with no named source and was not checked.