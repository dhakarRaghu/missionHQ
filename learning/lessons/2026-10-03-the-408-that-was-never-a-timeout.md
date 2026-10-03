Phase 3B left you able to ship a routing change behind a control group and to reserve spend before it happens. Both of those levers assume you can see the failure: the cascade mispredicts, the cache breaks, the cost climbs, and your dashboards tell you. This week your serving stack is live in production, and the first severity-2 incident lands in a shape none of those dashboards explains. The frontend starts timing out on long requests, and every engine metric stays green the whole time.

The natural reading is that the engine failed those requests, so the fix should be engine-side: a bigger timeout, more capacity, a faster model. This lesson shows what a study of real production incidents found instead, and why the failure that looks like a sick engine so often lives between two healthy components, in how the connection is held while the engine works.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- A non-streaming long request holds one silent connection, so the shortest idle timeout in the chain kills it no matter how healthy the engine is. Predict which of his request paths will fail as generation time grows, and fix it with streaming or a keepalive instead of debugging the engine.

## What does a real fleet actually fail on, and does the phase's alarm list cover it?

Your severity-2 alarms target assumed failure classes, and a measured fleet says which classes actually fire.

Suppose your team's first severity-2 incident, a user-visible outage that pages the on-call, is live. It shows frontend timeouts on long requests, and every engine metric green. Before you debug anything, a question decides where you look first. What does a production LLM fleet actually fail on, in measured proportions?

Sort 156 high-severity incidents from a hyperscale serving fleet by root cause, and four classes appear. Engine failures dominate at about 60 percent. Within engine failures, timeouts cause about 40 percent and resource exhaustion about 29 percent. Infrastructure follows at about 20 percent, model configuration at about 16 percent, and operations at about 4 percent.

  156 production incidents by root cause

Evidence
Microsoft-internal study of 156 incidents (129 severity 2, 27 severity 2.5) from a hyperscale LLM inference fleet. Two raters labeled a random 31 of them, with Cohen's kappa 0.89. One company, no public dataset, so every number above carries that condition (arXiv 2511.07424).

Now hold this mix against your alarm. Phase 3B built a cost guard on per-request cost and cache-hit rate: a detector. It prices each request and fires when cost or cache-hit rate crosses a floor. That detector assumes you know what breaks. Against the measured mix, it covers part of the engine class: resource exhaustion moves cost, and some timeouts do too. It covers nothing of the configuration class, and that class holds a surprise.

Of the configuration failures, 81 percent were header misconfiguration. It is a request header the serving stack rejects or mishandles, shipped with a deploy. That happens at deploy time, before any request runs. A per-request detector watches requests, so it sees this class only after users do. The fix is different in kind. Validate headers against a schema in the deploy pipeline before rollout, and the class mostly disappears.

The wrong belief this mix corrects is that incident response is engine debugging. Three of the four classes sit outside the engine. So the first question of an outage is which class you are in, not which engine knob to turn. One more number frames the whole lesson. 48 percent of these incidents closed monitor-only or self-healing, and only 28 percent needed a hotfix. Hold that; the last section asks what it means for your incident design.

Predict: your long non-streaming requests return HTTP 408 at the frontend, but backend logs show the same requests later returning HTTP 200 with correct outputs. Where is the failure?
Not in the engine. A 200 in the backend log means the engine finished the request correctly. So the failure sits between two healthy components. Something in the chain gave up waiting and closed the connection while the engine was still working. The next section walks exactly this incident.

Your incident fits this shape. The engine metrics are green because the engine is healthy. But the engine class is not the only class that produces a frontend timeout. The next section opens the incident itself: why did the frontend time out while the engine returned 200?

## Why did the frontend time out while the engine returned 200?

Long requests die at the shortest idle timer in the chain, however healthy the engine.

The mix above says failures are mostly engine, but it cannot show where damage lands. Case B lands it between two healthy components. Your cascade, the cheap-first router proved against a random control, is in production now. The first severity-2 incident opens as frontend 408s on long requests while every engine metric stays green.

A non-streaming answer sends nothing until it is complete, so one long request holds one connection open and silent. Every box on the path, client SDK, gateway, middleware, carries an idle timeout. That is the seconds of silence it tolerates before closing the connection. The shortest timer fires first, and the engine's correct answer then has nowhere to go.

  One non-streaming request: 40 s of generation, a 30 s idle timeout

  Step 1 (t = 0 s): one non-streaming request goes in and the engine starts generating.

  Step 2 (t = 0 to 30 s): the engine works while the connection carries no bytes.

  Step 3 (t = 30 s): the middleware's idle timeout fires, the frontend answers 408, and the engine keeps working.

  Step 4 (t = 40 s): the engine returns HTTP 200 into a connection nobody holds.

  The times are an illustration chosen to show Case B's shape, not measured values.

Predict: if the team adds engine capacity first, do the 408s stop?
No, because the failure never touched the engine. The backend logs showed the same requests returning HTTP 200, so more capacity would change nothing on the silent connection. That is where the 408 was born. The guess was reasonable because capacity is the lever you control. But a request that outlives the shortest idle timeout still dies.

The incident as the team lived it.

- Symptom. Long requests return HTTP 408 at the frontend while short requests pass and the dashboards stay normal.

- Wrong theory. The engine must be failing them, reasonable because everything measured, cost, health, token rate, watches the engine and nothing watches the connection.

- Decisive signal. Backend logs show the same request ids later returning HTTP 200 with correct outputs, so the engine finished them.

- Mechanism confirmed. The connection carried no bytes for the whole generation, the middleware's idle timer fired mid-generation, and the answer went nowhere.

The recorded fixes attack the connection, not the engine.

- Streaming on long requests, sending each token as generated, puts bytes on the wire, and a live wire resets every idle timer.

- Tuned batching and capped pending tokens bound the queue under load, so fewer requests outlast the timer.

- Per-endpoint isolation gives high-priority customers their own endpoint, so a neighbour's incident cannot become theirs.

- Hardened structured retries check what failed first, because a blind retry lands on a fresh silent connection and the same timer.

Isolation is justified by the fleet's shape. About 96 percent of the 156 incidents touched a single endpoint, so containment already works. Your agent loops and slow RAG calls hold this same silent connection.

After the liveness fixes rolled out, one anonymized customer's normalized HTTP 408 rate fell. The drop was from 2.72 percent in February 2025 to 0.47 percent in March 2025. The study itself labels this directional, one customer outside the main incident window, no counterfactual. So count it as inferred, not proof.

EvidenceCase B and Figure 7 of the Microsoft-internal study of 156 severity-2 and 2.5 incidents, arXiv 2511.07424, full HTML read 2026-10-03. The 408 rates paraphrase Figure 7 for one anonymized customer, and whether connection liveness alone caused the drop could not be verified. One company's fleet, no public dataset.

A silent connection dies at the chain's shortest idle timeout, however healthy the engine.

A 408 reads as engine failure, so the tempting first move is to scale the engine, the part that never broke.

Find the shortest idle timeout on your longest request path, because that is your deadline.

None of these fixes changed engine code. The next section asks what incident response should optimize when only 28 percent of incidents need a hotfix.

## If only 28 percent need a hotfix, what should your incident response optimize?

Case B failed between two healthy components, so only routing and liveness could reach it. The fleet's closure numbers show which lever does the real work. The running incident ended the same way: traffic moved, the engines kept serving, and no code shipped.

### Half the incidents close without a code change

Across the 156 incidents, 48 percent closed monitor-only or self-healing, and only 28 percent needed a hotfix.

The levers that restored service were rerouting traffic, restarting instances, rebalancing nodes and adding capacity. None of them touches engine code. The cost of reaching for code first shows up in the lifecycle numbers.

  32 hP75 time-to-mitigate, April 2025, internal view

  49 hP75 time-to-mitigate, May 2025, hotfix-heavy period

  ~1 hmedian recovery, ChatGPT and Claude status pages, outside view

Chu et al. measured public LLM services from their status pages: median recovery was 1.32 hours for ChatGPT and 0.93 hours for Claude. The internal study reports a P75 time-to-mitigate of 32 to 49 hours. The two numbers are not a fair race. One is a median and the other a 75th percentile, and an internal incident includes validation and hotfix cycles that a status page never shows. They still show where the hours go: into treating traffic problems as code problems.

Half of these incidents closed without code. The closures that worked were traffic moves, so routing away must be safe to automate. That safety depends on what the health check measures.

Predict: your health check pings the engine process and gets a reply, but the engine returns HTTP 500 on every real request. Does the load balancer drain it?
No. A process check asks whether the process is alive, and the process is alive, so the probe passes and the pool keeps the engine. Every request routed to it still fails, because the check measured liveness and the failure is in serving.

Kubernetes already separates the two questions: a liveness probe restarts a dead pod, and a readiness probe decides whether a live pod gets traffic. The fix here is a serving-ability probe, a readiness check that exercises the serving path with one short real generation and verifies the output. Case B is why the check must touch serving, because the engine was healthy and the connection still died, so process health said nothing about service. Per-endpoint isolation then keeps a wrong drain small enough that an automatic drain can be trusted.

Process health

GET /healthz returns 200 while the process runs. An engine failing every request stays in the pool and keeps taking traffic.

Serving ability

One short real generation through the serving path. A failure drains the endpoint within one probe interval, before users see the storm.

EvidenceClosure mix, fix types and P75 time-to-mitigate are from the Microsoft-internal study of 156 severity-2 and 2.5 incidents. It is arXiv 2511.07424, full HTML read 2026-10-03, one company's fleet, no public dataset. The study attributes the May rise to hotfix-heavy periods. Public recovery medians are from Chu et al., ICPE 2025, arXiv 2501.12469, status pages of 8 services, read 2026-10-03. The two measure different incident classes, so the gap is not a fair race.

### Pushback is the same bound, applied to load

The study's second case came from the opposite direction. Bursty traffic on vision models saturated the image encoders and the model containers together, and the service answered with 429s and 5xx. The first fix was pushback, the load balancer slowing or refusing new work once the queue fills: caps on pending tokens, caps on pending requests, and per-client throttling on expensive sampling parameters.

A cap bounds the queue before it grows, because without one each new request joins the queue, waits longer, times out and retries, and the retry joins the same queue. The cap turns that growth into a quick rejection at the edge, and the engine keeps serving at full rate behind it.

This is the bounded default a cost guard applies to money, moved to load. A pre-call reservation prices a call's worst case and holds that amount before the call runs, so spend cannot outrun the budget. A pending cap holds the queue to a fixed depth before requests arrive, so load cannot outrun the engine. In both, the bound is set ahead of time and the default absorbs the burst.

The three bounds line up one per resource:

- A session budget bounds cost, one reservation held for a whole agent loop.

- A pending-request cap bounds queue, shedding load at the edge before it pools inside.

- A serving-ability probe bounds misrouted traffic, draining a bad endpoint within one check.

Most incidents close on routing and monitoring, so make routing safe to automate.

A live process passes a liveness probe while failing every request you send it.

Change one health check from a process ping to one real generation.

You can now treat a 500 storm as a routing and probe question before an engine question. The lab, "Try it today", finds the shortest idle timeout on your own stack.

## Try it today

The shortest idle timeout in your chain decides which of your requests die silently. This lab finds it. Plan for fifteen minutes.

-  E1 15 min Map the chain. List every hop between your client and your model call. For each one, write down its idle or read timeout and where you found it.

- Client SDK: the HTTP client's read timeout, often named timeout or read_timeout in its config.

- Gateway or proxy: for nginx look at proxy_read_timeout; an API gateway document it under idle or route timeout.

- Load balancer: its idle timeout for the listener behind your service.

- Your own server: any read or write deadline set on the outbound call.

Write one line per hop: name, timeout, source. Circle the smallest number. That number, not your engine, sets the longest safe non-streaming request.

-  E2 5 min Cross the limit. Send one long non-streaming request whose generation time exceeds the number you circled. A large max_tokens on a slow prompt is enough. Watch two things.

- At the client: note the status code and when it arrives. A 408 or a connection error arriving at the circled timeout is Case B's symptom.

- In the backend logs: find the same request later. If it logged a 200 with a correct output, your engine was healthy and the connection died waiting.

No failure can also be the answer: your shortest timeout may be longer than your request. Raise max_tokens until you cross it.

-  E3 5 min Check the streaming path. If your path already streams, the silent connection is gone at the hops that forward chunks. Check each hop for buffering instead: a proxy that collects the whole stream before forwarding gives the idle timeout a silent connection again. For nginx, proxy_buffering left on is the usual cause.

The output of this lab is the circled number and one decision per request path. Any path whose requests can run longer than that number needs streaming, or a heartbeat below the timeout, before the next long task ships. This is Case B played on your own stack: the fix is at the connection, not the engine.

## Check yourself

Your team's p99 latency doubles and HTTP 500s climb on one endpoint right after a deploy. The token dashboard is flat, and the engine process is alive and answering health checks.

Using the phase's model and this lesson, answer two things aloud before opening the answer.

- Which three checks tell you whether this is an engine failure, a probe failure, or a configuration failure?

- Which fix do you apply first, and why is it not a code change?

Answer sketch
The three checks, in order:

- Probe serving ability, not process liveness. The process being alive says nothing, because 74 percent of incidents presented as 500s while engines could not serve. Send one real test request through the endpoint and see whether it completes.

- Check the deploy's headers against the previous configuration. 81 percent of configuration incidents were header misconfigurations, and a deploy just landed, so compare the request headers before and after.

- Check engine-side capacity signals. Only if the first two are clean: watch pending tokens, pending requests; resource exhaustion is 29 percent of engine incidents.

The first fix is to reroute traffic away from the failing endpoint and confirm the 500s stop. 96 percent of incidents touched a single endpoint, so containment works, and 48 percent of incidents closed monitor-only while only 28 percent needed a hotfix. Routing away restores service now; the investigation decides later whether the cause was configuration, probe, or engine.

The trap answer is restarting the engine first: it burns the mitigation window on a guess, and it cannot fix a header that the deploy broke.

## What you could write

- The 408 that was never a timeout. The claim: a frontend 408 with a backend 200 means the connection died, not the engine, so streaming on any long request is a reliability feature, not a UX feature. What makes it his: the "Try it today" output, one timeout per hop with the smallest circled, plus the measured 2.72 to 0.47 percent rate for one customer with its no-counterfactual condition.

- Most incidents never reach the codebase. The claim: 48 percent of 156 incidents closed monitor-only or self-healing and only 28 percent needed a hotfix, against the on-call assumption that an incident ends in a code change. What makes it his: the checkpoint decision he just made, rerouting before investigating, and what that mix would change about how his own on-call time is spent. The numbers are one company's internal study, so that condition travels with them.

## Sources

- https://arxiv.org/abs/2511.07424 — The Microsoft study of 156 production inference incidents. Full HTML read 2026-10-03. This gave the failure mix, Cases A and B, the fixing pattern and the time-to-mitigate numbers. Internal data from one company, no public dataset, so none of its numbers is independently checkable.

- https://arxiv.org/abs/2501.12469 — Chu et al., ICPE 2025. Public status pages for 8 LLM services. This gave the outside-in MTTR numbers (median 1.32 h for ChatGPT, 0.93 h for Claude) and the cross-provider isolation comparison.

- https://arxiv.org/abs/2410.21680 — Meta's training-cluster reliability study, 11 months and 4 million jobs. Cited only for contrast: training failures sit in a different regime, so its numbers do not transfer to serving.

- https://arxiv.org/abs/2608.13573 — Nixon et al., a one-year production serving trace. Abstract only at read time, so it confirmed the long-tailed workload premise and nothing more; the body is queued for a later read.