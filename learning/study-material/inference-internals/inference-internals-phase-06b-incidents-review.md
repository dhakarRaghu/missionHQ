# Phase 6B — Quality incidents and the design review

Part A sized the fleet and shared it fairly. This part covers the two moments when that work is tested by other people. The first is an incident. The second is a design review.

Both moments have the same requirement. You must answer "what changed, and how do you know" with a number and its source.

This part also closes Module 1. Section 6.4 collects the numbers from every earlier phase into one design defence.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  6.3  Quality incidents  — triage by slice, attribution, rollback        │
│  6.4  The design review  — the document, the questions, the defence      │
└──────────────────────────────────────────────────────────────────────────┘
```

Part A is a prerequisite, because section 6.4 uses its fleet plan. Phase 5B is also a prerequisite, because section 6.3 uses its run record.

Every exercise runs offline. Two of them are written exercises with no code.

Time: 2 to 3 hours.

---

## 6.3 — When the failure is "quality dropped"

Why this matters: a server that is down pages you. A model that got slightly worse does not. This section is the procedure for the second kind of incident. It also shows why each field you recorded in Phase 5B is needed.

### It is still an incident, by the standard definition

The Google SRE book lists postmortem triggers. They include "user-visible downtime **or degradation** beyond a certain threshold". They also include "a monitoring failure", which usually means someone outside the team noticed first. A quality drop fits both. The threshold is the quality indicator from section 5.4.

So the answer to "is this worth an incident?" is not a feeling. It is whether the quality indicator is burning its budget.

The same source gives three reasons to declare an incident. A second team must help. Customers can see it. Or it is still unsolved after an hour of focused work. It also says to declare early and often. A declared incident that turns out small costs a short meeting. An undeclared one has no commander, no single operator, and no timeline. That cost is inferred from the roles below, not measured.

### The roles do not change

Quality incidents use the same roles as any other:

```
┌──────────────────────┬──────────────────────────────────────────────────┐
│ incident commander   │ holds the overall state and makes the decisions  │
│ operations lead      │ the ONLY person changing the system              │
│ communications lead  │ tells users and other teams what is happening    │
│ scribe               │ records the timeline and every decision          │
└──────────────────────┴──────────────────────────────────────────────────┘
```

The operations rule matters more here than in an outage. During a quality incident, several people will want to "just try" a prompt tweak. Only one person changes the system, or you will not know which change fixed it.

And when unsure of severity, pick the higher one and argue about it in the postmortem, not during the incident.

### The triage, as a procedure

The priority order is the standard one: stop the damage, restore service, keep the evidence.

```
  1. IS IT REAL?
     compare the quality indicator against its baseline, with a
     significance test, not by eye
        │
        ▼
  2. DID A RECORDED FIELD CHANGE?
     test every NEW value of every axis against the baseline,
     whatever the overall average says
        │
     ┌──┴───────────────────────────┐
     │ yes                          │ no
     ▼                              ▼
  3a. ROLL BACK THAT FIELD       3b. the fourth axis: serving
      to the known-good              infrastructure. Compare against
      baseline and confirm           a second provider or a pinned
      the indicator recovers         copy on the same eval set.
```

`incident_drill.py` runs exactly this on a seeded ledger:

```
python phase06_design/incident_drill.py --scenario prompt
python phase06_design/incident_drill.py --scenario model
python phase06_design/incident_drill.py --scenario infra
python phase06_design/incident_drill.py --scenario noise
```

Each scenario changes one thing and the drill names it. The `infra` scenario changes no recorded field and still drops quality. The drill reports that the drop is real and that no recorded axis explains it. The `noise` scenario changes nothing and the drill declines to open an incident.

### The mistake in my first version, and why it matters to you

My first triage checked step 1, the overall pass rate, and only then looked for causes. I seeded an 18-point quality drop on the support route after a prompt change, from 88% to 70%. The drill found it in **1 of 20 runs** at 1,000 records.

The reason is arithmetic. That route carried a quarter of the traffic. So the average diluted an 18-point drop to about 4 points, which is inside the noise. With the default seed, the changed slice on its own was 3.5 standard errors below the baseline.

```
  overall pass rate    89.0% -> 87.8%     z = 0.6   looks fine
  prompt v7 slice      89.0% -> 75.0%     z = 3.5   a real regression
```

Both numbers come from one function, `incident_drill.py:52`. It asks whether two pass rates differ by more than sampling noise:

```python
def two_proportion_z(p1: float, n1: int, p2: float, n2: int) -> float:
    """z statistic for the difference between two pass rates."""
    if n1 == 0 or n2 == 0:
        return 0.0
    p = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return (p1 - p2) / se if se > 0 else 0.0
```

`se` is the standard error: how much the difference would move by chance alone. The result is the difference measured in standard errors. The drill treats 3.0 or more as real. A smaller sample gives a larger `se`, which is why the diluted 4-point drop on 400 records looked like noise.

The fixed version tests every new field value directly, whatever the average says. At the same sample size, it finds that regression in **17 of 20** runs. On pure noise, it names a false suspect in **0 of 20** runs.

```python
# WRONG: gate everything on the overall average. A regression confined to
# one slice is diluted below significance and never reaches step 2.
if two_proportion_z(p_base, n_base, p_recent, n_recent) < 3.0:
    return "no incident"

# RIGHT: a field that took a NEW value is tested against the baseline on its
# own, always. The average decides only whether an UNEXPLAINED drop is real.
for axis in AXES:
    for value, passes in recent_by_value(axis).items():
        if value not in baseline_values[axis]:
            if two_proportion_z(p_base, n_base, rate(passes), len(passes)) >= 3.0:
                suspects.append((axis, value))
```

The prompt-regression study in Phase 5B shows the same lesson. Model updates helped some prompts and hurt others. An average hides exactly that.

### Rolling back a prompt or a model

The published guidance with the most concrete numbers is the AWS Well-Architected Agentic AI Lens, practice AGENTOPS02-BP03. Treat it as a vendor recommendation, not an industry standard. The research found no other primary source with numbers:

- **Target time to restore: under five minutes** for a behavioural change.
- **Exercise the rollback quarterly.** A rollback nobody has run is a plan, not a capability.
- **Start a new version at 5 to 10% of traffic.**
- **Roll back to a known-good baseline, not to the previous version.** The previous version may be an hour old, and it was never proven stable.
- And the anti-pattern it names: treating prompt changes as low-risk because they are not code changes.

**Know how long your rollback actually takes to reach clients.** The Langfuse prompt client serves the version labelled `production`. It caches that version for 60 seconds by default, then refreshes it in the background. So moving the label back reaches a running client after roughly one cache period. That figure is inferred from the documented defaults, not measured. Time it once on your own system.

```
  10:00:00   operator moves label "production" from v7 back to v6
                 │
  host A     ────┼──v7──v7──┤refresh├──v6──v6──v6──────────────
  host B     ────┼──v7──v7──v7──v7──v7──┤refresh├──v6──v6──────
  host C     ────┼──v7──┤refresh├──v6──v6──v6──v6──────────────
                 │                              │
             10:00:00                       10:01:00
                          each host refreshes when its own cache
                          expires, so the switch is spread over
                          up to one cache period (60 s default)

  a host still serving v7 after that window has a different cause:
  a baked-in prompt file, a hard-coded fallback, or a longer TTL
```

The diagram is an example of the documented behaviour, not a recording. Your run record from Phase 5B shows the real switch, because every call records its prompt version and host.

**And compare against a control group, not against yesterday.** The Google SRE workbook's canary chapter warns that time is one of the biggest causes of change in metrics. Traffic mix changes by hour and by day. Quality indicators move with it. A before-and-after comparison can show a regression that is really a change in who was asking.

```
  BEFORE/AFTER (misleading)       │ CONTROL GROUP (what to do)
  ────────────────────────────────┼────────────────────────────────────
                                  │
  Monday     v6   88% pass        │ Tuesday, same hours, split traffic
  Tuesday    v7   84% pass        │   90% of traffic   v6   85% pass
                                  │   10% of traffic   v7   84% pass
                                  │
  "v7 lost 4 points"              │ "v7 lost 1 point"
                                  │
  but Tuesday had more hard       │ Tuesday was harder for both
  support questions               │ versions, and the split shows it
```

The numbers in that diagram are an example. The method comes from the canary chapter. Split live traffic at the same time, and compare the two groups.

### What a quality postmortem needs that an outage postmortem does not

The standard template has the usual sections: summary, impact, root causes, trigger, resolution, detection, action items, lessons learned, and timeline. Three things are worth adding for a quality incident:

1. **The evidence of the drop**, with its sample size and significance, so a reader can tell it was not noise.
2. **Which attribution axis moved**, or an explicit statement that none did.
3. **Why detection took as long as it did.** For quality incidents this is usually the most important section. Two published postmortems in Phase 5B both said their existing evaluations did not catch the problem.

Keep it blameless. That means you look for contributing causes, not for a person to blame. You assume everyone acted in good faith on the information they had. Review every postmortem. An unreviewed postmortem changes nothing.

**One honest gap.** The research found no published, step-by-step runbook for an LLM quality incident from a primary source. The Coalition for Secure AI incident response framework lists "model drift" as one incident type. It says to roll back to a prior model and add temporary guardrails. It gives no procedure. The NIST AI Risk Management Framework playbook describes a duty to disengage a system that exceeds its risk thresholds. It gives no numbers. The procedure above combines general practice with the Phase 5 evidence. Read it that way.

**The sentence to remember:** find a quality incident by testing what changed, slice by slice. The average hides a slice regression.

**The trap:** gating the investigation on the overall pass rate. A real regression on a quarter of traffic can look like noise in the average.

**Try this now:** run `python phase06_design/incident_drill.py --scenario prompt --records 1000` and read the first line. The overall z-score is about 0.6. Then read the table below it.

---

## 6.4 — Defending an architecture in a design review

Why this matters: every number you produced in this course only matters if other people accept the decision it supports. A design review is where that happens. This section turns the course into the document you bring and the questions you should expect.

### The document

Two primary descriptions agree on the shape.

Malte Ubl, a former Google engineering director, describes design docs with five sections. They are context and scope, goals and non-goals, the design, **alternatives considered**, and cross-cutting concerns. A larger project runs roughly 10 to 20 pages. A small change needs a 1 to 3 page version. It also says when not to write one: when the solution is obvious and there are no trade-offs to discuss. This is one engineer's account, not official company policy.

Michael Nygard's Architecture Decision Record, from 2011, is shorter. It records one decision in five parts: a title, the context, the decision written as "We will ...", a status, and the consequences. Consequences include positive and negative ones. Records are numbered and never renumbered. A replaced decision is kept and marked superseded. It is never deleted.

Two definitions from those sources are worth using exactly:

- A **non-goal** is something that could reasonably be a goal and is deliberately not. "The system should not crash" is not a non-goal. It is a negated goal.
- The **alternatives considered** section covers "the trade-offs that each respective design makes and how those trade-offs led to the decision". An option listed without its trade-off tells a reviewer nothing.

A decision record for the fleet in section 6.1 looks like this. It uses the five parts in order:

```markdown
# 7. Serve the assistant from a self-hosted fleet of 6 replicas

## Status
Accepted. Supersedes 4.

## Context
Measured peak is 22.8 requests/s. One replica serves 32 requests at once,
4 s each. A new replica takes about 320 s to serve its first request.
Target: mean queue wait under 250 ms at peak.

## Decision
We will run 6 replicas: 4 for today's peak and 25% growth, 1 for N+1,
and 1 of standing headroom for the cold start.
We will autoscale on vllm:num_requests_waiting, not GPU utilisation.

## Consequences
Positive: peak queue wait stays near 0 ms, and one replica can fail.
Negative: peak utilisation is 48%, so cost is $1.701 per million output
tokens at $3.49 per GPU hour, $15,286 per month.
Revisit if the cold start drops below 60 s: the plan then needs 5 replicas.
```

Every number in that record comes from `capacity_plan.py`. Record 4 is not deleted. It stays in the log, marked superseded by record 7.

The course ships a template that combines both formats, plus the part a generic template lacks:

```
code/phase06_design/design_doc_template.md
```

### The part a generic template does not have

Section 5 of that template is a table with one row for each concern this course taught. Each row names the phase that shows how to fill it in. It is the course, turned into a review checklist:

```
┌────────────────────────────────────────────┬───────┐
│ concern                                    │ phase │
├────────────────────────────────────────────┼───────┤
│ cost per request by token class            │ 3A    │
│ expected cache hit rate and prompt layout  │ 3A    │
│ routing, and the control group behind it   │ 3B    │
│ per-request budget and what happens past it│ 3B    │
│ self-host or API, against BOTH API prices  │ 4B    │
│ measured throughput, and how it was measured│ 4A   │
│ replicas, peak utilisation, redundancy     │ 6A    │
│ how tenants share capacity                 │ 6A    │
│ quantization and its eval gate             │ 4B    │
│ connect, first-chunk, stall, total timeouts│ 5A    │
│ which layer retries, and the stop signal   │ 5A    │
│ SLO indicators, including quality          │ 5B    │
│ failover or fallback, and is it exercised  │ 5B    │
│ fields recorded per request                │ 5B    │
│ rollback baseline and time to restore      │ 6B    │
└────────────────────────────────────────────┴───────┘
```

Every row needs a number and the source of that number. "Estimate" is acceptable if it is labelled. An unlabelled number is the first thing a reviewer will ask about.

### What reviewers actually ask

The Google SRE book publishes a launch checklist. It groups its questions into nine areas:

- architecture and dependencies, integration, and external dependencies
- capacity planning, failure modes, and client behaviour
- processes and automation, development process, and rollout planning

Its items are specific, for example:

- Make sure your client backs off exponentially on failure.
- Automate building and releasing a new version.
- Is this launch tied to a press release or other promotion?

That last one matters more than it looks. The same source reports launch traffic sometimes reaching **15 times** the initial estimate. A promotion is a capacity event.

Google's production readiness review covers six areas: architecture and dependencies, monitoring, emergency response, capacity planning, change management, and performance. It also reads **recent incidents and their follow-up items** as evidence.

Mercari publishes an open-source readiness checklist with pass-or-fail items. Three examples:

- "its rollback process is automated"
- "those alerts are actionable"
- "its design doc is up to date with the implementation"

Here is how those map onto an LLM system, and the answer each one should get:

```
┌─────────────────────────────┬───────────────────────────────────────────────┐
│ reviewer asks               │ your answer should contain                    │
├─────────────────────────────┼───────────────────────────────────────────────┤
│ what does it cost?          │ cost per request by token class, the cache    │
│                             │ hit rate it assumes, and what if it is 0%     │
│ why not just use the API?   │ break-even utilisation against BOTH a cheap   │
│                             │ and a frontier price, and the people cost     │
│ how many GPUs?              │ replicas from queueing math, peak             │
│                             │ utilisation, and N+k, not peak / capacity     │
│ what if traffic is 15x?     │ scale-up time, standing headroom, and what    │
│                             │ you shed first                                │
│ what if the provider fails? │ failover versus fallback, and whether the     │
│                             │ fallback runs continuously                    │
│ how do you know it is good? │ a quality indicator with a budget, the        │
│                             │ judge's agreement with humans, sample size    │
│ how do you undo it?         │ the known-good baseline and the measured time │
│                             │ to restore                                    │
└─────────────────────────────┴───────────────────────────────────────────────┘
```

### Run a pre-mortem before the review

A pre-mortem is a short exercise that asks the team to explain a failure that has not happened yet. The procedure, from the article that introduced it:

1. Brief the team on the plan.
2. Announce that the project has failed badly.
3. For a few minutes, everyone writes down, **alone**, every reason it failed.
4. Go round the room, one reason at a time, starting with the project lead, until every reason is recorded.
5. Afterwards, the lead reviews the list and strengthens the plan.

The article cites 1989 research on imagining that an outcome has already happened. That research reported a **30%** increase in the ability to identify reasons for the outcome. State that number carefully. One published summary of the underlying study notes it measured the **number** of reasons generated, not whether they were correct. The original paper was not read for this course. So treat the 30% as "more reasons", not "more correct reasons".

Step 3, writing alone, is the part that makes it work. Discussion first lets the most senior voice set the list.

The course template has a pre-mortem table. For an LLM system, start it with the failures this course showed you:

- the prefix cache stops hitting, from section 3.2
- a retry storm during a burst, from section 5.3
- a provider changes the answering model, from section 5.5
- a quantized model gets longer as well as worse, from section 4.4
- one tenant starves the rest, from section 6.2
- the fallback has never run, from section 5.6

### A worked defence, with numbers from the course

The scenario only sets realistic numbers. It is a support assistant with 22.8 requests per second at peak. It streams responses and serves several business customers on one deployment. The scripts produced every figure below.

```
concern                    answer                                  from
─────────────────────────────────────────────────────────────────────────────
naive fleet                3 replicas at 95%: 429ms mean queue     capacity_plan
                           wait. Rejected.
planned fleet              4 replicas for today, 4 after 25%       capacity_plan
                           growth, 5 with N+1, 6 with headroom
                           for a measured ~5-minute cold start
cost                       $15,286/month for 6 GPUs at $3.49/h;    capacity_plan
                           peak utilisation 48%                    + gpu_economics
the trade-off              that utilisation is what raises cost    4B section 4.6
                           per token. Latency and safety bought
                           it.
tenant isolation           token quotas plus token-fair            fair_queue_sim
                           admission. Round robin gave heavy
                           9.8x busy's work; token fairness
                           1.0x. Light tenant p99 wait 0.17s
retries                    one layer, a budget, a TTFT-based       health_signal
                           breaker. Blind retry dropped a burst
                           from 89% to 22.7% success
quality                    indicator on a judged sample; slice     incident_drill
                           tests on every new prompt version
```

Notice what that table does. Every row is a claim with a number, and every number names the tool that produced it. A reviewer can disagree with an assumption, such as the scale-up time. You can then rerun the tool with their number in front of them. That is the difference between defending a design and defending a preference.

**Say the trade-off out loud.** The fleet above runs at 48% utilisation at peak. That is a deliberate cost, paid for latency and for surviving a failure. Section 4.6 showed what low utilisation does to cost per token. A reviewer who spots it should hear that you spotted it first.

**The sentence to remember:** in a design review, every claim carries a number, and every number names its source. A disagreement then becomes a rerun, not an argument.

**The trap:** an alternatives section that lists options without their trade-offs. Reviewers read that section first, and "we considered X" without "and gave up Y" tells them nothing.

**Try this now:** copy `code/phase06_design/design_doc_template.md`, pick any LLM feature you know well, and fill in section 5. Count the rows where you have a measured number, and the rows where you only have a guess. The second count is your preparation list.

---

## 🧪 Hands-on lab — part B

E9 to E12 run offline. E13 and E14 are written exercises with no code.

- [ ] **E9 (offline).** Verify the incident drill.
  - Run: `python phase06_design/incident_drill.py --self-test`
  - Expected: 9 checks pass, including "the overall average alone would miss it".
  - Teaches: the triage itself is tested against seeded incidents before you trust it on a real one.

- [ ] **E10 (offline).** Attribute three different regressions.
  - Run: `python phase06_design/incident_drill.py --scenario prompt`, then `--scenario model`, then `--scenario corpus`.
  - Expected: each run names the axis that changed and suggests a next step.
  - For the model scenario, write down which two recorded fields made it detectable.
  - Teaches: every attribution field from Phase 5B exists so that this table can be filled in.

- [ ] **E11 (break-it, offline).** Hide a regression inside the average.
  - Run: `python phase06_design/incident_drill.py --scenario prompt --records 1000`
  - Expected: the overall z-score is about 0.6, which looks healthy. The drill still reports a regression, because it tests the changed slice on its own.
  - Teaches: the average is where a slice regression hides.

- [ ] **E12 (offline).** The two answers nobody likes.
  - Run: `python phase06_design/incident_drill.py --scenario infra`, then `--scenario noise`.
  - Expected: `infra` reports a real drop that no recorded field explains. `noise` declines to open an incident.
  - Teaches: "nothing we recorded changed" is evidence about the serving infrastructure, and "not significant" is a valid result.

- [ ] **E13 (written).** Fill in a design document.
  - Copy `code/phase06_design/design_doc_template.md` and complete section 5 for any LLM feature you know well.
  - Mark every number as measured or estimated, and name its source.
  - Expected: a count of measured rows and a count of estimated rows.
  - Teaches: the estimated rows are exactly the questions a reviewer will ask first.

- [ ] **E14 (written).** Run a pre-mortem alone.
  - Assume the design from E13 has failed badly six months from now. Spend five minutes writing, alone, every reason it failed.
  - Then compare your list with the failure modes this course showed:
    - a prefix cache that stops hitting
    - a retry storm
    - a silently swapped model
    - a quantized model that produces longer outputs
    - one tenant starving the others
    - a fallback that never ran
  - Teaches: the course is a list of failures you can now name in advance.

---

## 🔍 Check it yourself

This course has no anchor repository, so these questions point at the course's own code. Questions 3 and 4 work on any repository you own.

1. Open `code/phase06_design/incident_drill.py:99`. This is `triage`. It first asks two questions. Did a recorded field take a new value? Is that slice worse? Only then does it look at the overall pass rate.
   Read the docstring at lines 101 to 114. What did the first version do, and how often did it miss the regression?
   Then find the line that sets `out["hidden"]`. In words, what does `hidden` mean?

2. Open `code/phase06_design/incident_drill.py:49`. `AXES` lists four fields.
   Which one of them is a place and not a cause? Find the comment in `triage` that treats it differently, and say why that difference is correct.

3. In any LLM feature you own, search for the four attribution fields.
   Run: `grep -rn "response_model\|gen_ai.response.model\|prompt_version\|corpus_version" <your repo>/`
   For every field that returns no hit, write down which drill scenario from E10 you could not diagnose.

4. In the same repository, find where the prompt text is loaded.
   Is it a file in the deployed image, a registry lookup, or a string in code? Write down how long a rollback of that prompt would take, and how you know.

---

## ✅ Checkpoint 6B — answer in your own words

1. **The silent Tuesday.** On Tuesday, your support team says answers "feel worse". The overall eval pass rate is 86% this week and 88% last week. Your run record stores the requested model and the prompt version, but not the response model. Describe your first 30 minutes. Name which drill scenario you cannot rule out, and why.

2. **The declared incident nobody wanted.** A teammate says a two-point quality drop is "not an incident, nothing is down". Use the standard postmortem triggers to argue for or against declaring one. Then say what severity rule you apply when you are unsure.

3. **The rollback that did not roll back.** You moved the `production` label of a prompt back to v6 at 10:00. At 10:03 your slice test still shows v7 answers. Give the most likely cause, and how you would confirm it. Use the caching behaviour from section 6.3.

4. **Where versus why.** The drill says `corpus_version` changed and adds "It hurts most at: route=summarise". Your manager asks you to roll back the summarise route. Explain why that is the wrong action, and what you do instead.

5. **The alternatives section.** A reviewer reads your design document and says: "You considered a hosted API and rejected it. Why?" Your document says only "cost". Rewrite that row so it states what you gave up. Use the numbers from section 6.4's worked defence.

6. **The 48% question.** A reviewer says your planned fleet runs at 48% utilisation at peak. They call it waste. Defend or change the plan. Show the arithmetic that produced each replica. Then name one measured number that, if it improved, would let you remove a replica.

7. **The pre-mortem.** Run a pre-mortem on the design from question 6. List three failure reasons. For each, name the phase of this course that showed it, and the metric that would detect it first.

<details>
<summary>Answer sketches</summary>

1. First, test whether the drop is real. Two points on a weekly rate may be noise, so compute the z-score as the drill does. Then slice by every new value of every recorded field, whatever the average says. Test the prompt version first. You cannot rule out the **model** scenario. Without the response model, a provider-side model change looks like the **infra** scenario. You see a real drop that no recorded field explains. Add the field today, so the next incident is diagnosable.

2. Declare it. The standard triggers include user-visible degradation and a monitoring failure. A quality drop is user-visible degradation. When unsure between two severities, treat it as the higher one. Declaring early costs little. Declaring late loses the timeline.

3. The most likely cause is the label cache. The prompt client caches the label lookup. The Langfuse client's default is 60 seconds. Each process may refresh at a different time. Other clients may cache longer or be configured differently. Confirm it by checking the prompt version recorded on each run, grouped by host and time. The version should switch host by host. If some hosts still serve v7 after the cache time, check for a hard-coded fallback or a baked-in prompt file.

4. The route is a place. It is where the damage shows, and it is not the cause. The cause is the corpus change. Rolling back the route removes a feature and leaves the bad corpus in place for every other route. Instead, roll back the corpus version. Then compare retrieval results for the same queries on the two versions to find what changed.

5. Example: "Hosted API: rejected. It would cost about $X per month at our measured volume, against $15,286 for the fleet. By rejecting it, we give up two things: a service with no operations work, and the provider's scaling. We accept 6 GPUs to run and a cold start of about 5 minutes. We also own quality incidents on the serving axis." A row that says only "cost" gives a reviewer nothing to check.

6. Today's peak needs 4 replicas to meet the 250ms mean queue-wait target. 25% growth still fits in 4. N+1 makes it 5. A cold start takes about 5 minutes, and demand can rise 1.5 rps per minute. So demand can rise 8 rps before a new replica is ready. That needs 1 standing replica, which makes 6. Each replica has a named reason. The number that would remove a replica is the cold start. At 60 seconds, the tool gives 5 replicas and $12,739 per month.

7. Example answers. First, the prefix cache stops hitting after a prompt change. Phase 3A showed it, and the cached-token ratio detects it first. Second, a retry storm during a provider brownout. Phase 5A showed it, and the requests-per-call ratio detects it. Third, one tenant floods the queue. Section 6.2 showed it, and the per-tenant p99 wait detects it. Others are valid if they name a phase and a metric.

</details>

---

## References & Further Learning

Every URL below returned HTTP 200 when checked on 2026-09-17.

### Incident response

- **Google SRE book, "Managing Incidents"** — https://sre.google/sre-book/managing-incidents/
  Focus on: the incident command roles, and the section on when to declare an incident.
- **Google SRE book, "Postmortem Culture"** — https://sre.google/sre-book/postmortem-culture/
  Focus on: the list of postmortem triggers. Note that degradation counts, not only outages.
- **Google SRE workbook, "Incident Response"** — https://sre.google/workbook/incident-response/
  Focus on: the worked case studies. Read one and mark where the responders declared late.
- **PagerDuty incident response docs, severity levels** — https://response.pagerduty.com/before/severity_levels/
  Focus on: the rule for choosing between two severities when unsure.
- **PagerDuty incident response docs, roles** — https://response.pagerduty.com/before/different_roles/
  Focus on: the incident commander's duties, and what the commander must not do.
- **Langfuse docs, prompt caching** — https://langfuse.com/docs/prompt-management/features/caching
  Focus on: the client-side cache and its default time-to-live. This is why a label rollback is not instant.
- **AWS Well-Architected, Generative AI Lens, GENOPS03-BP01** — https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/genops03-bp01.html
  Focus on: versioning prompts and models so a rollback target exists.
- **AWS Well-Architected, Agentic AI Lens, AGENTOPS02-BP03** — https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentops02-bp03.html
  Focus on: the rollback targets. Under five minutes to restore, a quarterly rollback exercise, and a 5 to 10% start.
- **Coalition for Secure AI, AI Incident Response framework** — https://www.coalitionforsecureai.org/wp-content/uploads/2026/03/AI-Incident-Response-1.pdf
  Focus on: the list of AI incident types. Note that it names model drift but gives no step-by-step procedure.
- **NIST AI RMF Playbook, Manage function** — https://airc.nist.gov/airmf-resources/playbook/manage/
  Focus on: the guidance to disengage a system that exceeds its risk tolerance.
- **Google SRE workbook, "Canarying Releases"** — https://sre.google/workbook/canarying-releases/
  Focus on: comparing the canary against a control group running at the same time. The same rule applies to a prompt rollout.

### Design review

- **Malte Ubl, "Design Docs at Google"** — https://www.industrialempathy.com/posts/design-docs-at-google/
  Focus on: the section list, and the part on "alternatives considered". The template in `code/phase06_design/` follows it.
- **Michael Nygard, "Documenting Architecture Decisions"** — https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions
  Focus on: the five parts of a decision record, and why a superseded record is kept.
- **Oxide RFD 1, "Requests for Discussion"** — https://rfd.shared.oxide.computer/rfd/0001
  Focus on: the states a design document moves through. It is a second model to compare with Ubl's.
- **Gergely Orosz, "Software Engineering RFC and Design Doc Examples and Templates"** — https://blog.pragmaticengineer.com/rfcs-and-design-docs/
  Focus on: the list of real templates from several companies. Compare two of them with the course template.
- **Google SRE book, "Reliable Product Launches at Scale"** — https://sre.google/sre-book/reliable-product-launches/
  Focus on: the launch checklist questions on capacity and failure modes.
- **Google SRE book, "The Evolution of the SRE Engagement Model"** — https://sre.google/sre-book/evolving-sre-engagement-model/
  Focus on: the production readiness review, and the areas it covers.
- **Mercari production readiness checklist** — https://github.com/mercari/production-readiness-checklist
  Focus on: the design checklist. It is a real, public checklist from a company that uses it.
- **Gary Klein, "Performing a Project Premortem"**, Harvard Business Review, 2007 — https://hbr.org/2007/09/performing-a-project-premortem
  Focus on: the procedure. The article cites a 30% figure from earlier research. That study measured how many reasons people produced, not whether the reasons were correct.
- **Gary Klein's premortem page** — https://www.gary-klein.com/premortem
  Focus on: the short step list. Use it for E14.

---

## Cheatsheet — part B

```
QUALITY INCIDENT TRIAGE
  1. is it real?        two-proportion z on pass rate, baseline vs recent
  2. what is new?       for EVERY new value of every recorded field,
                        test that slice against baseline. ALWAYS, even
                        when the average looks healthy
  3. nothing new?       a real drop with no recorded cause points at
                        serving infrastructure: status page, second provider
  4. not significant?   do not declare. keep watching the burn rate
  place fields (route, tenant) say WHERE it hurts, never WHY

THE FOUR AXES AND THEIR FIELDS
  model     request model AND gen_ai.response.model   both, or no diagnosis
  prompt    prompt name + version
  data      corpus / index version                      you name it
  serving   no field exists                             found by elimination

DECLARE
  degradation is an incident trigger. unsure of severity -> the higher one
  roles: incident commander, operations, communications, scribe

ROLLBACK
  keep a known-good prompt, model and corpus version, always
  label moves are cached: know the TTL (Langfuse client default 60 s)
  compare against a control group running at the same time

DESIGN DOCUMENT (Ubl)
  context and scope | goals and non-goals | design |
  alternatives considered (with what you gave up) | cross-cutting concerns

DECISION RECORD (Nygard)
  title | context | decision "We will ..." | status | consequences
  numbered, never deleted, superseded records stay

DEFENDING A NUMBER
  every claim has a number; every number names the tool that made it
  a disagreement becomes a rerun, not an argument
  say the trade-off before the reviewer does

PRE-MORTEM
  "it failed badly in six months. why?"  write alone first, then share
```

---

This is the last phase of Module 1. You can now follow an LLM feature from a single call to a fleet plan. The path runs through the engine, caching, serving, and the client and its telemetry. You can defend the result in a design review.
