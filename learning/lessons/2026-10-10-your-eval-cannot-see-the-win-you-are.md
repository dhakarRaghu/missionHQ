A score can rise for two reasons, and only one of them is your change.

You have an eval pipeline from your RAG work, and it runs. A prompt change is ready, so you run the eval over your test questions, and the score moves from 62% to 68%. The reasonable belief is that the change helped, and that more test data is a nicety for later. What this belief misses is that every score coming out of a finite set of questions carries a random part, because a different draw of questions or a different run would have given a different number even with no change at all. Before you keep or drop a change, you owe yourself one calculation you have probably never done.

This phase teaches that calculation. You will learn how large the random part of your score is for a given number of questions and runs, and so the smallest real improvement your eval can tell apart from luck. After reading it, you can decide the size of your eval from the change you want to detect, before you spend money on runs.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- A pass-rate eval has a noise floor of roughly 1/sqrt(n x reps), so an improvement smaller than that floor is indistinguishable from luck. Decide his eval size from the change he wants to detect, before he spends money on runs.

## What does a pass rate actually measure?

A score can rise for two reasons, and only one of them is your change.

Your RAG eval runs over 30 questions. The new prompt scores 68%, the old one scored 62%. Should you keep it? Answering that needs one idea this section builds: what the 68% actually measures.

An eval is a fixed set of test inputs you score a system against. Your 30 questions are one. A pass rate is the share of those cases the grader marks as passing, so 68% means the grader passed 68 of 100, or about 20 of 30. These two terms carry the whole lesson.

The wrong belief is that the pass rate is a property of the prompt, like its token count. It is not. Think of each question as a coin flip whose weight is set by the prompt. The true weight is the pass rate you would get over every question you will ever face. Your 30 flips only estimate that weight, and a different set of 30 flips would give a different number even with no change at all.

-
0%
100%

your run: 68%

reruns of the same unchanged prompt land in this band
somewhere inside it sits the true weight of the coin
One measured score is a point; the band around it is where rerunning with no change would land. Illustration, not measured.

That band is the noise floor, the range of scores a rerun of the same, unchanged system will produce. If a new score sits inside the band, the eval cannot tell your change from luck. A win you can act on must clear the band.

Predict: you run your eval over 25 cases, twice. The new prompt scores 6 points higher. Should you keep it?
No, not on this evidence. At 25 cases x 2 repetitions the noise floor is about plus or minus 14 percentage points, so a 6-point gap sits well inside it. The same runs with no prompt change could easily produce a 6-point gap. Keeping the prompt now is a coin toss, not a measurement. Anthropic's own eval skill file gives the floor as roughly 1/sqrt(n x reps), which the next section works through.

This is why "the score went up" is not yet information. It becomes information only next to the noise floor. A 6-point gain with a 7-point floor means something; the same gain with a 14-point floor does not. The reasonable belief was reasonable because nobody hands you the floor next to the score. You have to compute it yourself.

A pass rate is an estimate with a noise band, never a property of the prompt.

Reading a higher score as "it helped" mistakes luck for signal on small evals.

Rerun your eval with no change twice, and look at how far the two scores sit apart.

What this section did not give you is the size of the band. The next section answers where the 1/sqrt(n x reps) rule comes from.

## Where does the 1/sqrt(n x reps) rule come from?

The first section left you knowing that every score carries a band of luck around it, but not how wide the band is.

Sizing it takes one more term. A repetition is one full run of the same eval over the same cases. Each run re-rolls the model's luck on every case, so repetitions multiply your sample count the way extra cases do.

The square root comes from how independent luck cancels.

- Each case is an independent draw of luck, because a lucky hit on one question says nothing about the next.

- Independent luck cancels only partially. Flip a fair coin 100 times and the count strays from 50 by about sqrt(100)/2 = 5.

- As a score, that leftover is 5 flips divided by 100, so 5 points. A safety band at twice that wobble is plus or minus 10, exactly 1/sqrt(100).

- Generalise this: the leftover grows like the square root of the draws while the score divides by all the draws, so the band is 1/sqrt(n × reps).

noise floor ≈ 1 / sqrt(n × reps)

 15 cases × 1 run    1/√15   ≈ ±26 percentage points
 25 cases × 2 runs   1/√50   ≈ ±14
 30 cases × 1 run    1/√30   ≈ ±18    (your eval)
100 cases × 2 runs   1/√200  ≈ ±7

The table below shows the same floors as a grid, in percentage points.

cases1 run2 runs4 runs

15±26±18±13

25±20±14±10

30 (your eval)±18±13±9

50±14±10±7

100±10±7±5

  Your eval's noise floor

  Cases

  Repetitions

  Noise floor

  Can it see a 5-point gain?

Small evals cannot see small wins. At your 30 questions and one run, the band is plus or minus 18 percentage points, and halving it costs four times the draws, because sqrt(4) is two.

Predict: you want to see a 5-point gain. Your eval has 100 cases, run once. Can it see it?
No. At 100 cases the floor is 1/sqrt(100), plus or minus 10 points, so a 5-point gain stays inside the band. Run the rule backwards: a 5-point floor needs sqrt(n × reps) to reach 20, so n × reps must reach 400. That is 100 cases run 4 times, or 400 cases run once.

That backwards direction is how you should use the rule. The smallest detectable improvement is the smallest gain your floor can tell from luck, and it fixes the design order. Decide first what improvement you would act on, and that number sets n × reps. If only a 5-point win is worth keeping, you need 400 draws, and no cheaper experiment can show it.

Evidence
Anthropic's eval-construction skill file (build-eval.md in anthropics/skills, read at main on 2026-10-10) states this floor as roughly 1/sqrt(n × reps) and works the same 25 cases × 2 reps = ±14 points example. The square-root wobble of independent counts is standard statistics, and the 1/sqrt(n × reps) form is Anthropic's rough version of it.

Your floor is 1/sqrt(n × reps), so four times the data halves the noise.

Shipping a gain smaller than your floor means shipping luck.

Compute 1/sqrt(30 × 1) for your eval, then write the smallest gain it can see.

All of this assumes the score itself is honest, and the next section answers what else must be true before the number means anything.

## What else must be true before the number means anything?

The sizing rule assumed an honest judge, and this section covers when it is not.

Your RAG judge is a second model. It reads each answer against a rubric, its scoring instructions, and returns pass or fail. The pass rate counts those verdicts, so a judge that misses failures bends every score. The move from 62% to 68% last run could be a real gain. Or a judge could be reading the new answers more kindly. Grader calibration tells the two apart. Compare the judge's verdicts with your own on a handful of cases before trusting any score.

- 30 answersone per test question

- judge gradeseach answer against the rubric, with its own misses

- pass ratethe share of verdicts marked pass

Predict: your system fails on 6 of 30 answers. The judge passes 95% of good answers and lets half the bad ones pass. What rate does it report?
About 87%, against a true 80%. Roughly 23 of the 24 good answers pass, and 3 of the 6 bad ones slip through. A judge that misses half the failures misses half the fixes too. So repairing 3 of the 6 is a true 10-point gain, but the reported score moves by about half. Your floor at 30 cases is ±18 points, so the judge can hide a real win.

The check is one loop:

- Run the judge on five pilot cases, since five is enough to surface a mismatch.

- Grade the same five yourself before reading its verdicts, so its answer cannot steer yours.

- Compare case by case, and treat each disagreement as a wrong or incomplete rubric, never a wrong case.

- Rewrite the rubric and repeat until you would not change a single verdict.

An uncalibrated judge fails asymmetrically. As a judge, gpt-3.5-turbo caught 95% of factually consistent summaries but only 30 to 60% of inconsistent ones. The misses land on the bad answers, the ones every prompt change is meant to fix. This is bias, not luck, so more cases do not shrink it the way they shrink the noise floor.

Evidence
Eugene Yan's survey (eugeneyan.com/writing/llm-evaluators/) reports the 95% versus 30 to 60% gap and, from the underlying papers, a defect recall of 0.73 for criteria aligned with human judgment against 0.49 for an automated baseline. Anthropic's build-eval.md (read at main on 2026-10-10) sets the bar for ready: "Would you have scored any of these differently?" One yes means "the rubric isn't ready".

Use it this week: your eval already holds both ingredients, graded cases and judgment. Take five cases from the last run, grade them before you read the verdicts, and count the disagreements. Each disagreement is a rubric fix that pays off in every later run.

Calibrate the judge on five hand-graded cases before you trust any score it reports.

An unchecked judge shows each real fix at half size, inside the noise floor.

Hand-grade five cases from your last run, then count where the judge disagreed.

A calibrated judge scores each case correctly, but the score can still stop measuring real questions. The next section asks what tuning the prompt against the scored cases does.

## Does this change the path?

The three ideas you just worked through are not the end of the inference course. They are the start of a different subject.

The noise floor

A pass rate is an estimate, and rerunning the same unchanged system lands within plus or minus 1/sqrt(n x reps) of it. An improvement smaller than that band is luck, not signal.

Grader calibration

An LLM judge is a second unreliable model until you check it. Grade a handful of cases yourself and compare, because an unchecked judge catches the easy failures and misses the costly ones.

The held-out split

Tuning against the cases you score on fits the test set. A second set, excluded from every tuning round, is what makes a kept change evidence.

None of these three ideas is about serving requests. The inference phases taught you how a model runs: batching, the KV cache, the bill. This lesson taught you how to know a change to that model's behaviour was real, and that question has its own name, eval engineering.

The verdict for your path is that eval engineering wraps around everything the course teaches. Every later phase ends with a change you might adopt: a new router, a new cache policy, a quantized model. Each adoption raises the same question your RAG pipeline raises now: did it help, and can your measurement see the difference. The inference course gives you the changes. This subject gives you the instrument that judges them, and no inference phase answers it for you.

You carry one tool into every later phase: before adopting any change, compute the noise floor of the eval that would judge it.

## Lab: size your own eval in fifteen minutes

You have the instrument now, so the last step is to point it at your own pipeline. This lab takes fifteen minutes and needs no code changes. It needs only the noise floor formula from earlier: plus or minus 1/sqrt(n x reps). A repetition is one full run of the same eval over the same cases.

-  L1 offline Open your RAG eval and count the cases. Write the count as n. If you run the eval once per experiment, your reps is 1.

-  L2 offline Compute the noise floor twice: once at n x 1, once at n x 2. For 30 cases that is about plus or minus 18 points at one repetition and plus or minus 13 at two, because the floor shrinks with the square root of the total samples.

-  L3 offline Write down your smallest detectable improvement: the smallest gain that would make you keep a new prompt or parser. Be honest. A 3-point gain you would not act on does not count.

-  L4 offline Compare the two numbers. If your floor is larger than the gain you would act on, your decision is made: add cases or repetitions before the next prompt experiment, not after. A run whose floor hides the win tells you nothing and still costs the money.

-  L5 offline Set aside a held-out split now, before any tuning round. Mark a share of your cases as off-limits to prompt edits, and score on them only when a change survives the rest.

L2 worked example, 30 cases. The floor at one repetition:

floor = 1 / sqrt(30 x 1) ≈ 0.18  →  ±18 points
floor = 1 / sqrt(30 x 2) ≈ 0.13  →  ±13 points

If the smallest gain you would act on is 8 points, both floors are larger. So one run over 30 cases cannot see the win you are tuning for.

Keep the three numbers from L2 and L3 in the eval's README. The next time a run shows a 6-point jump, you will know in one glance whether to trust it.

The lab sized your own eval. The checkpoint tests the same judgment on Anthropic's numbers, where the tool reported a 98.9% win. Only the held-out split shows what survived.

## Checkpoint: the tool that beats your model

You sized your own eval in the lab. Here is the same judgment tested on someone else's numbers, where the win looked too big to question.

Anthropic built a tool that rewrites your prompt against an eval, round by round, and published what it did to a customer-support benchmark with 44 tickets. The table has everything the tool reported.

SetupSearch set (30 tickets)Held-out split (14 tickets)

Stronger model, original prompt74.4%78.6% baseline

Cheaper model, tuned prompt98.9%90.5%

Three questions. Answer each before you open the answer box.

- If the 14 held-out tickets did not exist, which number would you have shipped on? What does that number actually measure?
Answer sketch
You would have shipped on 98.9%. That number measures how well the tuned prompt fits the 30 tickets the tuner was allowed to see, because the tool kept only changes that improved that exact set. It is the search set answering its own exam.

- Which number predicts production, and how big is the real win?
Answer sketch
The held-out split predicts production: 90.5% against a 78.6% baseline, a real gain of about 12 points. The 24-point gap between 98.9% and 90.5% is what fitting the test set bought, and it vanishes on tickets the tuner never saw.

- The held-out split has 14 tickets. What is its noise floor, and does the 12-point gain clear it? A noise floor is roughly 1/sqrt(n x reps), the band reruns of an unchanged system land in.
Answer sketch
1/sqrt(14) is about plus or minus 27 points at one run, larger than the 12-point gain. So even the honest number needs repetitions or more held-out tickets before you trust it. Two protections, two different jobs: the split keeps the measurement honest, and sizing keeps it readable.

Evidence
All four scores (74.4, 98.9, 90.5, 78.6), the 44-ticket split and the cost figures are Anthropic's own report of its own tool, from its hill-climbing blog post. No third party has rerun them, so treat the sizes as the report's, not as reproduced fact.

The answer you could publish: the worked noise-floor table, or what the tool's own doctrine warned against.

## What you could post

Two things here are worth posting, because each is a claim your last hour of work can prove.

- The noise-floor table at common eval sizes, framed as the calculation nobody shows before sharing a benchmark. What makes it yours: you ran it on your own RAG eval's case count and found the floor was larger than the 6-point "win" you almost shipped. The table is boring; the sentence "my eval could not have seen this improvement" is not.

- The doctrine that survived its implementation. Anthropic's own skill file says "One flow per eval; don't try to build a grand unified benchmark", and Hamel Husain then watched the plugin build one bundled evaluator that mixed four failures into a single `protocol_ok` check. What makes it yours: you can name the same gap in your own pipeline, where your grader judges three failure modes in one pass.

## Sources

- hamel.dev/blog/posts/claude-auto-evals/ — the review that taught the workflow order: error analysis first, one failure per eval.

- raw.githubusercontent.com/anthropics/skills/main/skills/claude-api/shared/evals/build-eval.md — the source of the 1/sqrt(n x reps) floor and the 15-to-100 sizing rule. Read 2026-10-10.

- claude.dev/blog/automating-eval-design-and-hillclimbing/ — the hill-climb results, including the 98.9% and 90.5% numbers.

- aicatchup.com/news/claude-code-automated-evals-hillclimb — the independent report that confirmed the train and held-out mechanics.

- eugeneyan.com/writing/llm-evaluators/ — the survey behind the grader-calibration evidence: 95% catch on correct summaries, 30 to 60% on wrong ones.

The 98.9%, 90.5% and 74.4% scores and the 4.6-cents-to-1-cent cost change are all Anthropic's own report of Anthropic's own tool, with no third-party rerun. Treat them the way the noise-floor rule says to treat any unverified number: a claim to check, not a fact to plan on.