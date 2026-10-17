In your batching phase you computed the service rate of a queue of requests, and you saw that when the arrival rate passes it the queue never drains. Your Mission HQ agents write to the same shared files under a writer-at-a-time convention, so one agent waits while another holds the file, and that convention is cheap because your agents write a few times a day. This week Anthropic published the same story one level up: their coding agents pushed merges from 2,500 a day in May 2026 to 30,000 a day in September, and their git and CI pipeline, built for humans, hit its ceiling.

The question this lesson answers is what happens to a check-before-write pipeline when the writes grow past what that check can carry in a day. You will compute the ceiling of a serial queue like yours, see why adding more machines does not raise it, and see why a system that far past the ceiling has no choice but to check after the write instead of before it.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- A serial verification pipeline lands at most one change per check duration, so any system whose write rate passes that ceiling verifies after the write, not before. Compute when his own CI, review or shared-file locking stops working as agent output grows, and predict which design a system past the ceiling must have.

## What a queue's ceiling is, in one calculation

A serial checker's daily ceiling is one line of arithmetic, and it predicts the whole design.

Your Mission HQ agents share the job ledger and ideas.md under one rule, one writer at a time. That shape has a name: a queue is a line of items waiting for one worker. The worker's service rate is how many items it finishes per unit of time. There, batching, serving several items in one pass, raised that rate. This week Anthropic pushed a merge pipeline past the same limit. So this section turns the shape into a ceiling you can compute for any checker.

Put a queue in front of a CI suite. Each merge waits in line. The checker runs the full suite on one merge, then takes the next. If the suite takes 30 minutes, every other merge waits for that half hour.

  One 30-minute CI suite, one merge at a time

  A merge arrives every five minutes, and merge 1 still has 20 minutes of checking left.

  After 30 minutes one merge has landed and five are waiting.

  Illustration, not measured: the service rate is one merge per 30 minutes, whatever the arrival rate is.

Predict: A serial merge queue runs a 30-minute CI suite per change. How many merges can it land in one day, however many machines you give it?
48. A day has 1,440 minutes, and the checker finishes one merge per 30 minutes. So its service rate is 48 merges a day. More machines do not raise it. Running two checks at once means the second merge is tested against a base that does not contain the first. The check then proves nothing about what main will look like.

The ceiling is the day divided by one check's duration.

minutes in a day                1,440
CI time per merge                     30 min
ceiling  = 1,440 / 30         =       48 merges per day

  Merges per day, by CI duration

  One CI run (minutes)

  Ceiling

Above the ceiling the queue never drains. If a merge arrives every two minutes, fifteen arrive during each 30-minute check and only one leaves. So the backlog grows by fourteen merges per check. The wait grows with it, and engineers start merging with an old base.

Tian Pan's July 2026 analysis computes the same cap, roughly 48 merges a day for a 30-minute suite. Batching raises it, because one CI run can check several merges together. Pan's warning is that flaky tests, not bad code, are what cascade in batched queues. One unrelated failure fails the whole batch, the batch re-runs, and wait times double. Yelp hit this wall in 2023. It added binary search over the batch to find the one bad merge without re-running everything.

Evidence
Tian Pan, "The Merge Queue Is the New Bottleneck", 2026-07-02: a serial queue with 30-minute CI caps at roughly 48 merges/day and argues flaky tests, not code quality, are what cascade in batched queues. Yelp's engineering blog, 2023, documents the same wall at human scale and the binary-search isolation fix.

The same arithmetic runs on your own files. One Mission HQ agent holds the job ledger for about 30 seconds while it reads, computes and writes back. So that ledger can take 86,400 / 30 ≈ 2,880 writes a day. Time one real hold, divide, and you know exactly how far your writer-at-a-time rule reaches.

  A serial checker's daily ceiling is the day divided by one check's duration.

  More machines do not raise a serial ceiling, because parallel checks test unverified bases.

  Time how long one cron agent holds the job ledger, then divide 86,400 seconds by it.

48 a day is a comfortable ceiling for humans, but Anthropic reports 30,000 merges a day, roughly 600x past it. So the next section shows the design that lets those changes land anyway.

## What Anthropic's pipeline looks like at 600x past the ceiling

Anthropic lands 30,000 merges a day against a 48-merge ceiling, so the safety check must have moved.

The math above says no serial gate passes 30,000 changes a day. So this section shows the design that lets them land anyway. Anthropic reports its monorepo was around 2,500 merges a day in May 2026. By September 2026 it was over 30,000 a day. That number is self-reported, and every performance number in this section is.

Predict: they buy 1,000 CI runners. How many merges land per day?
Still 48, because the serial lock, not the hardware, sets the cap. The runners can test one change at a time. So the queue's service rate does not move. That rate is how many items one worker finishes per day. Something in the design itself must change.

What changed is where correctness runs. A serial merge queue is a gate where each change waits. It passes the full test run, and merges only if it passes. Past the ceiling, that gate must go. Anthropic's pipeline uses post-merge testing instead: changes merge as they arrive and the tests run on main afterwards.

  Serial queuePost-merge

- change waitsbehind every change ahead of it

- CI runs, 30 minone change at a time, one global lock

- merge48 a day at most

- change mergesas soon as it is ready, no wait

- tests run on mainpost-merge and pre-deploy, off the write path

- fast reverta bad main is caught after, fixed fast, costs a conflict

The decisions behind it, in order:

- Git's human-scale assumptions broke first. It expects an offline human with a full local copy, but Anthropic's clients were agents and CI jobs that are always online, and the numbers made that stop working.

- So they rebuilt the server, not the lock. Scion stores only the files a change touched plus content-addressed blobs, where each blob is named by a hash of its contents, so identical content gets one name and any server can cache it. Write cost scales with the change, not the 100 GB repo.

- With no global lock left to respect, pre-merge gating stopped making sense. Their own question: what does CI even mean when hundreds of changes merge while one test run is still going?

  load git carriedvalue

  history sizealmost 100 GB

  CI checkouts25 million a day

  naive git trafficover 600 PB a day

  git mirrors at peakseveral hundred

Evidence
All numbers are Anthropic's own, from the Scion engineering post, with no independent measurement. Anthropic calls Scion unsuitable for general use and says it fits only truly enormous monorepos.

The design is not new, and that is the strongest evidence it works. Meta's Mononoke has run the same changeset model, under the name Bonsai, for Meta's monorepo for years. Google's Piper has served tens of thousands of developers a centralized client-server repo since well before 2016. Anthropic is the agent-scale case of a proven pattern, not a risky first.

  Past the serial ceiling, verification moves after the write, because it cannot stay before it.

  A post-merge pipeline trades a bad commit on main for throughput, so reverting must be fast.

  List which of your own project's checks could run after the merge, and which truly cannot.

Anthropic's scale is far from yours, but the ceiling law is the same. So the next section asks where your own stack already faces it.

## Where his own stack hits the same law

Anthropic's scale is far from yours, but the ceiling law and the design choice are the same. Mission HQ already faces them.

Your cron agents write to the same shared files: the job ledger and ideas.md. The convention is one writer at a time, a serial lock, so each agent's write is checked and finished before the next one starts. That lock is your serial gate, exactly like Anthropic's old merge queue. Its service rate, the number of items one checker finishes per unit of time, sets a hard ceiling on writes per day.

The ceiling applies to your evening scale too. A 30 second lock hold caps throughput at 2 writes a minute.

1,440 minutes a day / 0.5 minutes per write = 2,880 writes a day

That sounds like plenty, but the queue breaks long before the ceiling. A lock that is busy half the time already makes a cron job wait on average for half a hold. With six agents firing on the same minute, the last one waits minutes. Jobs that run every five minutes start missing their window.

Predict: you grow from three to six cron agents, each holding the ledger 30 seconds. Under the serial lock, which breaks first as you add agents: conflicting writes or missed cron windows?
Missed windows break first. Conflicts between two writes are rare at six agents, because each write touches the file for seconds in an hour. But every added agent stretches the average wait behind the lock. A wait of a few minutes is enough for a five-minute cron job to start late or run twice. The queue fails from waiting, not from corruption.

That is the same fork Anthropic faced, at smaller stakes. You have two designs for shared files:

  Serial lock. One writer at a time, correctness checked before the write lands. Safe and simple. Costs every agent a wait, and the waits grow with each agent you add. At some point the cron schedule, not the lock, is what breaks.

  Optimistic writes. Agents write whenever they are ready, and conflicts are fixed after the write. This is post-merge testing moved to your scale: verification runs after the write, not before. No agent waits, but you sometimes repair the ledger after two writes crossed.

The choice turns on how expensive a conflict is. Two agents appending to the job ledger rarely touch the same line, so a conflict costs one repair pass. So optimistic writes win. A file where a bad state is costly to undo keeps the serial lock. That includes a file an agent reads to decide what to do next. A wrong read costs more than a wait.

Anthropic reported the same logic at 600x your scale. They accepted that concurrent changes conflict and leaned on fast fixing after the write. The alternative was a queue that could never keep up (self-reported).

Evidence
Anthropic's Scion post says they dropped pre-merge gating for post-merge and pre-deploy testing, accepting conflicts and fixing them fast. Yelp's 2023 merge-queue post and Tian Pan's 2026 analysis show the same serial-versus-batched fork at human scale.

  My serial file lock has the same ceiling math as Anthropic's merge queue, at smaller numbers.

  Adding agents feels safe because conflicts are rare, but the queue fails from waiting first.

  Time one full ledger write from one agent, and divide 1,440 minutes by it.

This section covered who may write and when. What it did not cover is what the agents write. Anthropic found agents satisfy patterns rather than constraints, so the next section asks how you review intent, not lines.

## Lab

E1: Measure your own ceiling

offline about ten minutes

Time one full pass of the slowest serial check in an evening project. That is a full CI run, or one end-to-end run of your eval pipeline. Then divide the minutes in a day by that number.

$ time python -m pytest            # or: one full eval run
# ceiling = 1440 / minutes-per-pass

real    12m10s
→ 1440 / 12 = 120 passes a day, at best

Write that ceiling next to the job ledger, in one line. The number you wrote is the most your pipeline can ever land in a day. That holds if every write waits for that check, no matter how many machines you buy. If your cron agents currently produce far fewer writes than that, your ceiling is idle capacity, not a problem. The exercise changes nothing yet; it gives you the number you will check each time you add an agent.

E2: Sort your checks by where they must run

offline about five minutes

List every check your agent jobs run before a result is written. Split it into two groups.

- Must run before the write: checks whose failure corrupts shared state, like writing a malformed ledger row that later jobs parse.

- Can run after the write: checks whose failure is fixable, like an intent check that each open job still has a row, which a cron job can run and repair on the next pass.

The first group is your serial checker and owns the ceiling you measured in E1. Every check you move to the second group shortens the time each write holds the lock. So the ceiling rises without any new hardware.

You should end with at least one check in the second group. If every check lands in the first, look again for one whose failure another job could detect and undo. That is the role post-merge testing and fast revert play in Anthropic's pipeline.

It asks you to compute where it breaks and pick a design.

## Checkpoint

The lesson said a serial checker lands at most one change per check duration. Here you apply that law to a repo much like the one you might build next, before it exists.

Scenario. Your evening project grows to three agents. CI takes 45 minutes per change.

- What is the ceiling of a serial merge queue on this repo, and does the load pass it?
Answer sketch
1,440 minutes ÷ 45 minutes = 32 merges a day. The three agents propose 60 changes a day, so the load is nearly double the ceiling. The queue never drains. Each added agent makes the waiting line longer, and no extra CI runner helps because the check itself is serial.

- At which agent count does the queue first break?
Answer sketch
At 32 merges a day the queue saturates, so two agents proposing 40 changes a day already pass it. Even one agent at 20 a day leaves only 12 merges of headroom, which means the queue works today and breaks with the first agent you add.

- You can batch merges or verify after merge. Pick one and name its cost.
Answer sketch
Batching raises throughput by testing several changes per 45-minute pass, and its cost is the cascade: when a batch fails, one flaky or bad change fails the whole batch and you must bisect to find it, as Yelp found. Post-merge testing lets changes land at once and checks them behind main, and its cost is that main can carry a broken change between the write and the check, so you need fast detection and a cheap revert. Either choice beats the serial queue past 32 merges a day. The first keeps correctness before the write and pays in complexity. The second pays in a window where main is untrusted.

Next, two post ideas turn this same calculation and the intent-review lesson into something you could publish.

## Posts

- The queue has a ceiling, in one line of math. A serial merge queue with 30-minute CI lands at most 48 changes a day, because 1,440 minutes divided by 30 is 48, and more machines cannot raise it. Tian Pan showed this with queueing math, and Anthropic's 30,000 merges a day put them 600x past it. What makes it yours: compute the ceiling of your own CI tonight and write it next to the job ledger.

- When agents write the code, review intent, not lines. Anthropic found multiple agent-built systems that read the whole commit log linearly to learn when a change merged, because "scan the log" is a familiar pattern, while asking the review tool's API was the constraint they missed. What makes it yours: you run a fleet of agents on shared files, so you have already seen an agent satisfy a pattern and skip the constraint.

## Sources

- Anthropic, "Redesigning source control" is the Scion post behind Sections 2 and 3. Every performance number in this lesson (2,500 to 30,000 merges a day, 200x smaller checkout infrastructure, 99% cache hits) comes from Anthropic and has no independent measurement.

- Meta's Mononoke "Key Concepts" doc in the facebook/sapling repository confirms the changeset and derived-data design is proven prior art that has served Meta's monorepo for years. This is the strongest corroboration in the lesson.

- Yelp Engineering, "Speeding Up Delivery With Merge Queues" (2023) shows the same ceiling at human scale and the batched-merge design with binary-search isolation.

- Tian Pan, "The Merge Queue Is the New Bottleneck" (2026) is the queueing analysis behind the 48 merges a day figure and the claim that flaky tests, not code quality, cascade in batched queues.

- Potvin and Levenberg, "Why Google Stores Billions of Lines of Code in a Single Repository" (2016) shows the centralized monorepo design predates Scion by a decade. The study note could read only the abstract page; cacm.acm.org refused the full text with HTTP 403.