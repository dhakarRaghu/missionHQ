A uniform hash spreads sessions evenly on average, but the average hides the spread, and scaling out does not shrink it.

In Phase 3B you learned to route a session back to the replica that already holds its KV cache, so the request skips a second full prefill. Stickiness solved the recomputation problem, but it left a question your rollout plan cannot dodge: if a uniform hash decides which replica each session lands on, how uneven is the load across your replicas? On Modal's Kimi K2.6 coding-agent service, 50 replicas and 250 sticky sessions aimed at 5 per replica, yet about 4% of replicas sat at 1 session or fewer while others reached 12.

The reasonable guess is that this is a small-scale problem, and that adding more replicas lets the law of large numbers smooth it out. This phase measures what actually happens: why the spread between your idlest and busiest replica has a floor set by the hashing itself, why doubling replicas and sessions together changes nothing about it, and the one load-aware fix worth adding to your own router.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- Uniform session hashing over S servers is a Poisson process whose variance equals its mean, so the relative load spread across replicas never shrinks as you add replicas. Predict idle-replica and overloaded-replica percentages for his own router before he builds autoscaling, and decide when load-aware placement is worth the complexity.

## What does a request actually cost when it lands on the wrong replica?

A request on the wrong replica replays a 100,000-token prefill it could have skipped. Here is why.

You run several GPU replicas behind a router, and a user's turn can land on any of them. This section shows what that landing costs, and the cost is lopsided: the same request is nearly free on one replica and ruinously expensive on another. The reason is the shape of one coding-agent request, so start there.

A coding agent works in turns, and each turn resends the whole conversation. The article calls this session history replay: turn T's input is the full history of turns 1 to T-1 plus something new. On Modal's Kimi K2.6 service, one request carried roughly 100,000 input tokens and produced roughly 500 output tokens. That is 200 input tokens per output token.

  One coding-agent request, by tokens

llm-d, a separate team on different hardware, reports agentic ratios above 100:1. So this shape belongs to the workload class, including your own support agents. It is not a Modal peculiarity.

The GPU does not have to recompute the shared history every turn. It keeps the KV cache, the attention keys and values computed for tokens it has already seen. When the history is cached, the prefill (the single pass that processes input tokens before the first output token) only handles the new tokens. When it is not cached, prefill replays all 100,000.

Predict: turn 15 lands on a replica without the KV cache. The new turn adds about 500 tokens. How much more input does prefill process on a miss than on a hit: about 2x, 20x, or 200x?
About 200x. A cache hit prefills only the roughly 500 new tokens. A miss replays the near-100,000-token history. The user feels this as time to first token, the wait before the first word of the reply. llm-d measured the consequence: P90 time to first token of 0.542s with cache-aware routing against ~93s cache-blind, on 8 vLLM pods and 16 H100s.

There is one catch: a KV cache lives in one replica's GPU memory. A session's history is cheap only on the replica that processed it. So the router needs session affinity, the rule that keeps a session on the replica holding its KV cache. Affinity converts one expensive decision, where a session first lands, into a permanent commitment.

- turn arriveshistory plus ~500 new tokens

- router picks a replicathis choice decides the cost

- holds the cacheprefill ~500 tokens

- no cacheprefill ~100,000 tokens

Notice what this does to load. A replica holding one extra session is not holding one extra request. It may be repaying a 100,000-token prefill on every turn. An overloaded replica's slowest users are slow by a factor of hundreds, not percent. That amplification is why an uneven spread of sessions across replicas, however small it looks as a count, is a latency problem.

Evidence
The 100k input, 500 output and 200:1 figures are quoted from Modal's engineering post on their production Kimi K2.6 coding-agent service, a single team and a single workload. The >100:1 agentic ratio and the 0.542s versus ~93s P90 TTFT comparison are llm-d's own measurements on 8 vLLM pods and 16 H100s. Both urls are in the sources list.

A cache hit prefills 500 tokens; a miss prefills 100,000, so routing decides the cost.

Treating one session as one unit of load, when a session is 200 input tokens per output token.

Log input and output token counts per request on your own agent and compute their ratio.

So the router must be sticky. But stickiness raises a question this section left open: once sessions are pinned by a hash, how uneven does the fleet get, and does adding replicas even it out?

## Why does a uniform hash stay uneven at any scale?

Knowing why scale cannot fix a sticky router saves you building autoscaling to fix it.

The section above showed why the router must be sticky: a session on the wrong replica repays a 100,000-token prefill. It left open how uneven that constraint makes the fleet, which is what this section measures.

Here is the mechanism, one level below "the router hashes sessions". Most routers use consistent hashing. It assigns each session to a replica by hashing its session id. So adding one replica remaps only some sessions instead of all of them. Two facts follow.

- Each session id hashes to a replica uniformly and independently. Put N sessions over S replicas and each replica's count is a binomial draw, which at these sizes behaves as a Poisson distribution with rate N/S, the average sessions per replica.

- A Poisson distribution's variance equals its mean. So when the target is 5 sessions per replica, the spread around 5 has the same shape whether you run 50 replicas or 500. This is the Poisson variance floor: the relative unevenness of uniform hashing does not shrink when you add replicas, because adding replicas adds sessions in the same ratio.

Predict: how many replicas sit near idle, and does doubling the fleet help?
You run 50 replicas and 250 sticky sessions, hashed uniformly, aiming at 5 sessions per replica. What share of replicas sit at 1 session or fewer? Does that share fall if you double everything to 100 replicas and 500 sessions?

About 4% at 1 session or fewer, and no, doubling changes nothing. The Poisson rate stays 5, so the shape of the spread stays the same. The reasonable belief that the law of large numbers smooths this out fails. That is because the mean scales with the fleet, and the variance scales with the mean.

Move the sliders and watch both tails. See the share of replicas at 1 session or fewer. Also see the share at 12 or more, under a Poisson at your chosen rate.

Sessions per replica under uniform hashing

Replicas

Target sessions per replica

At 1 session or fewer

At 12 sessions or more

At 50 replicas, 250 sessions and a target of 5, Modal measured about 4% of replicas at 1 session or fewer and about 0.5% at 12 or more, matching the Poisson shape and invariant to total scale. Their production spread was worse than the theory, with variance several times the mean. The cause is the session burst: clients control session ids, and tree-structured agent flows with sub-agents and branches fire many concurrent requests under one session id, so all of that load pins one replica while the hash still counts it as one session.

Modal's production fleet, 50 replicas, target 5 sessions per replica.

Evidence
The 4% and 0.5% dispersion figures are Modal's own measurements. So is "variance several times the mean". They were measured on their Kimi K2.6 coding-agent service, one team and one workload. A second team measured the failure this math predicts. llm-d reports P90 time to first token of 0.542s with cache-aware scheduling. That is against ~31s approximate and ~93s cache-blind, on 8 vLLM pods and 16 H100s. Both urls are in the sources list.

Uniform sticky hashing is Poisson, so the load spread never shrinks as you add replicas.

Expecting the law of large numbers to even out the fleet; the variance grows with the mean.

Set the calculator to your replica count and read the idle share before planning autoscaling.

So the spread is mathematical, not bad luck. What a router can do about it without breaking stickiness is the next section's subject. It covers what Modal changed, and which fix applies to your stack.

## What did Modal change in the router, and which fix applies to his stack?

The section above showed the load spread is mathematical, not bad luck. What it left open is what your router can do about it without breaking stickiness. Modal changed their router in three ways, and each one maps to one cause from the spread.

### Three fixes, one per cause

- Split heavy sessions past a threshold. A session burst, the many concurrent requests a tree-shaped agent fires under one session id, pins all of them on one replica. Past a load threshold the router deliberately places one session on two replicas. Some KV is recomputed, because a shared prefill is cheaper than one overloaded replica running while others idle.

- Place new sessions by live load, not by hash. Sessions differ by orders of magnitude in tokens, so counting sessions miscounts work. The router reads fine-grained signals from each replica, such as running requests and KV utilization, and puts a new session on the least loaded one. This is load-aware placement, choosing a replica from measured load instead of from a hash over session counts. Session affinity still holds after placement, so the session stays put and keeps its cache.

- On scale-up, send new sessions to the new replicas. Consistent hashing reroutes about 1/N of sessions whenever the replica count changes, and each rerouted session recomputes its full KV. New replicas are empty by definition, so they are the best placement and no existing session has to move.

The result was strongly sub-Poisson dispersion, meaning a variance under half the mean. The uniform hash from the section above has a variance equal to its mean. So Modal's router beats the floor rather than sitting on it.

Evidence
The three fixes and "variance under half the mean" are Modal's own report on their Kimi K2.6 coding-agent router. It is one team and one workload. llm-d measured the same fix class paying off on different hardware. P90 time to first token of 0.542s with cache-aware scheduling against ~93s cache-blind, on 8 vLLM pods and 16 H100s. Both urls are in the sources list.

### What transfers to your router

Predict: your stack is small, a handful of replicas. Of Modal's three fixes, splitting heavy sessions, load-aware placement, and placing new sessions on new replicas, which is least worth building first?
The session split. It is more machinery than a small router needs. The hotspot it fixes comes from client-controlled bursts, which you may not have. The other two matter at any scale, because the Poisson floor never improves with scale.

At four replicas a trivial sticky router with load-aware placement is a real improvement, not a premature optimization. The maths makes this clear: the floor does not fall as the fleet grows. So a small fleet does not escape it either. Placing new sessions on the least loaded replica is a few lines in any router. It removes the left tail of idle replicas before you ever autoscale.

One check fits this week. Log sessions per replica and its variance next to cache hit rate, as a first-class metric. When variance climbs past the mean, placement has drifted back toward the hash. Time to first token will show it first.

Fix the hash's spread by placing new sessions on measured load, then keep each session where it landed.

Treating routing as a small-scale concern and waiting for autoscaling; the Poisson floor is identical at 4 and 50 replicas.

Add one log line per placement. Then plot sessions per replica next to cache hit rate and look for the left tail.

You can now read this phase's sticky-session rule with one condition on it. Stickiness sets where a session can go, but the hash still decides the spread. A uniform hash leaves about 4% of replicas nearly idle and a tail overloaded at any replica count. The recall section collects the claims.

## Lab: watch the Poisson floor in fifteen minutes

The section above gave you the claim and its fix. This lab lets you produce the Poisson floor yourself in fifteen minutes. It uses the same 50-replica, 250-session setup from Modal's service. So the 4% number becomes something you measured rather than something you read.

-  E1 offline
The floor at 5 sessions per replica. Hash 250 random session ids onto 50 buckets, the way a sticky router hashes sessions onto replicas.

import hashlib, random

def spread(sessions, replicas):
    counts = [0] * replicas
    for i in range(sessions):
        h = hashlib.sha256(f"session-{i}-{random.random()}".encode()).digest()
        counts[int.from_bytes(h[:8]) % replicas] += 1
    idle = sum(1 for c in counts if c <= 1) / replicas
    hot = sum(1 for c in counts if c >= 12) / replicas
    return idle, hot

print("50 x 250:", spread(250, 50))
# Expected (Poisson with mean 5, illustration, not measured):
# ~4% of buckets at 1 session or fewer
# ~0.5% of buckets at 12 sessions or more

Compare your shares against Modal's measured numbers from section 2. They should land close, because the math is the mechanism.

-  E2 offline
Scale changes nothing. The first exercise showed the shape at 50 replicas. Now double everything and confirm the shares barely move.

print("100 x 500:", spread(100, 500))
# Expected: the same ~4% idle and ~0.5% hot shares.
# If your numbers move, run each size a few dozen times
# and average; a single run has noise.

This is the result the law of large numbers said should not happen. The mean load doubled and the relative spread did not shrink.

-  E3 offline
The session burst makes it worse. The two exercises above count sessions as equal. In the running case, sessions with sub-agents fire many concurrent requests under one session id, so a session's true weight is skewed. Weight each bucket by a skewed session size instead of counting.

import random
def weighted_spread(sessions, replicas):
    load = [0] * replicas
    for i in range(sessions):
        h = hashlib.sha256(f"session-{i}-{random.random()}".encode()).digest()
        r = int.from_bytes(h[:8]) % replicas
        load[r] += random.paretovariate(1.2)  # heavy-tailed session sizes
    mean = sum(load) / replicas
    var = sum((x - mean) ** 2 for x in load) / replicas
    return var / mean  # ratio of variance to mean

print(weighted_spread(250, 50))
# Expected: a ratio of several, not 1.0. Load-aware
# placement would push it under 0.5.

The uniform hash promised variance equal to the mean. A skewed workload pays several times that, which matches Modal's production observation.

Keep these three scripts. When you add the sessions-per-replica metric from section 3 to your router, E1 gives you the baseline its variance should beat.

You have now measured the floor, confirmed it does not move with scale, and watched the session burst widen it. The checkpoint next gives you a user's complaint and asks you to explain it from these numbers.

## Checkpoint

The lab showed the floor in scripts you ran yourself. Now use the concept on a live complaint.

The complaint

Your multi-agent system runs 4 replicas, each holding its own KV cache, with 40 sticky sessions hashed uniformly across them. You log sessions per replica and see 7, 9, 10, and 14.

A user on the replica with 14 sessions reports a time to first token twice the others. You scale out to 8 replicas. After the scale-out, the counts read 3, 4, 4, 5, 5, 5, 6, 8, and the same class of complaint comes back two days later.

Answer these from Concept 1 before opening the sketch:

- Why did scaling from 4 to 8 replicas not remove the slowest replica?

- Which two router changes would remove it?

Answer sketch
1. Scaling cannot fix it. Uniform hashing of N sessions over S replicas is Poisson with rate N/S, and Poisson variance equals the mean, so the relative spread stays the same at any replica count. At 5 target sessions per replica, about 0.5% of replicas still sit at 12 or more sessions. Autoscaling halves the absolute load on every replica, but the share of replicas sitting far above the mean does not move, so some replica always accumulates the tail and its prefill queue doubles its time to first token.

2. The two fixes. First, place new sessions by measured load, such as running requests and KV utilization, instead of by hash alone, which is load-aware placement over a sticky session. Second, past a load threshold, split a hot session across two replicas, because a session whose sub-agents fire concurrent requests can pin one replica on its own, and duplicating some KV is cheaper than one hotspot. Both fixes keep session affinity after placement, so cache hit rate is preserved.

The Poisson floor was Modal's measurement on a 200:1 coding-agent workload; your exercise E1 reproduced the same shape with a hash and a for loop.

## Things he could post

Two posts this lesson supports:

The counterintuitive number

Random sticky routing leaves about 4% of replicas at one session or fewer at five sessions per replica. That is true at any scale. Doubling the fleet does not shrink the share. What makes it his is the figure: his own simulation from the lab above. It shows two overlaid histograms at 50 and 100 replicas showing the same shape.

Two teams, one failure

A short note comparing Modal's Poisson floor with llm-d's P90 time to first token of 0.542s cache-aware. That is against about 93s cache-blind on 8 vLLM pods and 16 H100s. The claim is that two independent teams hit the same routing failure on different stacks. So it is a property of cache-aware serving, not of one vendor.

The first post works because the number contradicts the reasonable belief that scale smooths random hashing. The second works because two measurements of one mechanism are stronger evidence than either alone.

## Sources

- Modal Engineering, "Serving trillions of tokens for trillion-parameter coding agents" (2026-09-23): the primary trace for this lesson. Gave the routing math, the Poisson dispersion numbers at 50 replicas and 250 sessions, the session burst effect, and the three router fixes.

- llm-d, "KV-Cache Wins You Can See": the independent measurement of the same failure class on different hardware. Gave the P90 time to first token of 0.542s cache-aware against about 31s approximate and about 93s cache-blind, and the agentic input to output ratios above 100:1.

Read the numbers with their strength. Every headline dispersion figure (about 4% near idle, about 0.5% overloaded) is Modal's own, from one team and one workload, so treat it as one production observation on top of the math. llm-d measured the same mechanism differently, through latency percentiles rather than per-replica spread, and their result confirms the failure is real without confirming Modal's exact percentages.