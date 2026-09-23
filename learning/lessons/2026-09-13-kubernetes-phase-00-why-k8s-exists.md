# Kubernetes Phase 0 — Why K8s Exists

_A course lesson. Phase 0 of the Kubernetes course, rewritten. No lab in this phase, by design: this one is the mental model everything else stands on._

## Why you are here: the machine that dies at 3am

It is 3am and one of your VMs is gone. Not slow, gone. The load balancer health check has been red for four minutes. The service that lived on that box ran three of your processes: an API, a worker, and a cron runner you forgot was co-located there. You SSH into a second box, pull the repo, start the API by hand. The worker needs a queue URL from a config file that only exists on the dead machine. Twenty minutes in, the API is back but timed-out requests have already stacked up, and the load balancer keeps sending traffic to the dead IP because nobody updated its target list. By sunrise you have fixed the incident and written nothing down. Next month a different box dies and the whole evening happens again, slightly differently.

That night is the real cost of running services without an orchestrator. Nothing you did was wrong. Every step was reasonable. The problem is that the system kept no picture of what "running correctly" looks like, so every recovery was a person reconstructing that picture from memory under pressure. This phase exists so that, by the end of it, you can look at Kubernetes and see the answer to one question: what would a system have to do so that the 3am recovery is not a person at all?

## What this phase will teach you

Phase 0 has no lab and no code, and that is deliberate. It teaches four ideas, in order. First, what you would have to build yourself if Kubernetes did not exist, so the tool reads as an answer rather than a pile of nouns. Second, the desired-state paradigm: you declare what should run, you never say how. Third, the architecture, five components and one database. Fourth, the control loop, the single pattern every component implements. Later phases assume this one completely. Pods, Deployments, Services and networking are all Phase 1; where one of them appears here, it appears as a cameo with a one-line definition.

## What you would have to build yourself

Take Kubernetes away and look at what is left to write. Say you run a few dozen services across a few dozen VMs.

You need **placement**: deciding which service runs on which box, tracking which box has spare memory, and not putting two heavy JVMs on the same 4GB machine. That is a database and an allocation algorithm. You need **restart on failure**: something that notices a process died and starts it again, and notices a *machine* died and moves the work. That is health checking plus a failover path. You need **scaling**: when traffic doubles, someone or something starts more copies, and puts them on boxes that have room. You need **rollouts**: shipping version two without taking version one down first, so you write the blue-green bash everyone writes, with its hand-maintained list of which port is live. You need **service discovery**: when a new copy starts, everything that calls it needs its new IP, so you end up with a registrar, or a config file, or DNS entries that go stale. And you need some **isolation**, so one service's memory leak does not kill its neighbour.

None of these is exotic. Each one is a few hundred lines of bash and a cron job. Together they are an orchestrator, written badly, in production, by you, forever. An **orchestrator** is just the name for the system that owns all six: it decides where things run, keeps them running, scales them, rolls them out, and tells callers where they are.

## Why Google built this three times

Google hit every item on that list at a scale where bash stops being a joke and starts being a headcount. Their internal answer was **Borg**, a cluster manager that ran most of Google's workloads for a decade. The 2015 Borg paper is public and worth reading later. Then they built **Omega**, a rethink of Borg's architecture. Then they open-sourced the lessons as **Kubernetes**. The lineage matters because of what each stage contributed.

Borg contributed the core shift: manage **applications, not machines**. Borg's authors describe containerization as the thing that "transformed the data center from being machine oriented to being application oriented." Monitoring, health checks and load balancing key on the application. The machine becomes furniture. Omega contributed the architecture Kubernetes uses today: a centralized, consistent store of the whole cluster's state, with components using optimistic concurrency over it. Strip the names off and that is "one database, many readers and writers agreeing through it." Kubernetes took both, fixed Borg's rigid job model with labels and selectors, and shipped it as Borg's lessons learnable by the rest of us. The point to hold: self-healing in this design is not a feature bolted on. It is what falls out of the architecture once the state lives in a store and the components just react to it.

## What goes wrong when you tell machines what to do

Before the paradigm has a name, watch it fail. Your blue-green deploy script says: start v2 on port 9001, health check it, flip the load balancer, stop v1. Monday it works. Wednesday the health check times out mid-run because the box was loaded, and the script exits after starting v2 but before flipping traffic. Now you are running both versions, nobody knows which one the load balancer points at without checking, and the script's own log is the only record. Re-running the script is not obviously safe because some steps may have already happened. You wrote a sequence of commands, and reality disagreed with the sequence partway through. That disagreement is now yours to find and fix by hand.

This failure has a name and a shape. The name is **imperative**: you told the system what to do, step by step. The shape is decay. Every imperative program about infrastructure makes an implicit bet that the world is still in the state the previous step left. Steps fail halfway, machines die between steps, and two runs overlap. Each time, the gap between what the script assumes and what is true gets wider, and a human closes it. Commands say *do this*. Nothing checks whether *this* survived.

## What desired state looks like in practice

The alternative is to stop issuing commands and start stating facts. This is the **declarative** model: you write down the state you want ("three copies of the API, this image version, these environment variables") and hand it to the system. The system's job is to make reality match the statement, and to keep making it match, forever. The statement is the **desired state**.

A useful way to feel the difference: `kubectl apply` is an UPDATE statement against a database row. You are not launching processes. You are writing "this row should exist with this content" into the cluster's database of desired state. The same reframing works backwards. `kubectl delete pod web-7` does not reduce your running count for long. Deleting the pod removes an object from the database, but the desired state you wrote earlier still says three copies. Something is watching, the replacement appears, and within moments there are three again. I said "pod": the **pod** is Kubernetes' smallest deployable unit, one or more containers scheduled together. Phase 1 opens with it; here you only need to know it is the thing that gets created and deleted.

One honesty note, because your original module deserves it: its diagram shows a deleted pod "replaced in ~1s." Treat that as a cartoon of the control loop's *reaction*, not a service guarantee. The replacement pod *object* is written to the database almost immediately. The pod actually serving traffic takes as long as pulling the image, starting the container and passing readiness checks, which your own Phase 1 material prices at a minute or more on a cold node. The loop is fast. Physics is not.

## The five components and the one database

Here is the whole machine, in one pass. Kubernetes splits into a **control plane** (the brain, run per cluster) and **nodes** (the machines that run your work).

**etcd** is the one database. The official docs describe it as a consistent, highly available key-value store used as the backing store for all cluster data. Every fact about the cluster lives here: your desired state, and the observed state of everything. It is the only stateful component in the control plane.

**kube-apiserver** is the front door. Every read and write of cluster state goes through it: your `kubectl`, the internal components, everything. It is stateless and can run many copies behind a balancer.

**kube-scheduler** watches for pods that have no node assigned, picks a node (the placement problem from section 3), and writes the assignment back.

**kube-controller-manager** is many small, independent controllers compiled into one binary. There is one that keeps replica counts matching, one that reacts to nodes dying, and dozens more. Each is a small loop doing one job.

**kubelet** is the agent on every node. It watches for pods assigned to *its* node and asks the container runtime (the thing that actually starts containers, such as containerd) to run them. Also on each node live **kube-proxy**, which handles per-node networking, and the container runtime itself. Both are Phase 1 territory.

Two precision fixes on the module's count. First, the official architecture lists a sixth control-plane component, **cloud-controller-manager**, which embeds cloud-provider logic and is exactly the thing that wires up an AWS load balancer when you ask for one. On a managed service like Amazon EKS, where Amazon runs the whole control plane, you never see any of these machines, so "five invisible boxes" is operationally true and structurally incomplete. Second, the API server being the single door to etcd is not a convention. It is a stated design rule of the project, and the next section is about what it buys you.

## Why only the API server talks to etcd

The project's own design principles say it in one sentence: only the API server communicates with etcd, not the scheduler, not the kubelet, nothing else. Traffic between nodes and the control plane all terminates at the API server; the docs note that other control-plane components do not even expose remote services. One door means one place for authentication, authorization, validation and audit. It also means the blast radius of a broken client is bounded: a misbehaving controller can write nonsense desired state, but it cannot corrupt the store directly.

One carve-out, because quoting the rule too flatly will get you corrected in a design review. No component *instructs* another, but the API server does initiate connections in one direction: `kubectl logs`, `exec`, `attach` and port-forward all ride an apiserver-to-kubelet connection. The docs warn that, by default, the API server does not verify the kubelet's serving certificate, and apiserver-to-node proxy traffic defaults to plain HTTP. On EKS this is handled for you, but you should know the exception exists. The honest phrasing: components never push work to each other. Your debugging traffic, and the API server's stream fetching, are the exceptions.

## The behaviour you just saw has a name: the control loop

Go back to the deleted pod. You deleted `web-7`. Desired state said three copies, observed state dropped to two, and a third appeared. Each step of that was one component doing the same four things: read the desired state, read the observed state, compare, act on the difference. That is the **control loop** (or reconcile loop), and it is the only pattern in this architecture. The scheduler's loop: is there a pod with no node? Bind one. The replica controller's loop: do the running copies match the count? Create or delete. The kubelet's loop: does this node run everything assigned to it? Start what is missing, stop what is extra.

Two vocabulary words the loop needs, and they are on every Kubernetes object. The **spec** is the desired state you wrote. The **status** is the observed state the system reports back. Every loop in the cluster is a function from (spec, status) to action. And the loop never exits. There is no "done." A controller that has nothing to do is not finished; it is waiting for the next disagreement. This is also why declaring rather than commanding works at all: the record of what you asked for outlives any attempt to fulfil it, so a failed attempt is just input to the next pass.

The page version of this lesson carries an interactive diagram of exactly this: step through a pod deletion and watch the change travel from your command, into etcd, out to the scheduler and kubelet, and back as status. It has a second mode showing what happens when a watching client's connection stalls, which is the preview of the incident at the end of this phase.

## Why the loop reads the world instead of remembering events

There are two ways to drive a loop like this. **Edge-triggered** means the loop reacts to events: "a pod was deleted, wake up." This is fast and cheap, and it has a fatal property: miss the event and you never know. A controller that was down, or a message that was dropped, and desired and observed drift apart permanently. **Level-triggered** means the loop reacts to the full current state on every pass: not "something changed" but "here is what I can see, all of it, right now." A level-triggered loop cannot miss anything. Even if it was asleep through seventeen changes, the eighteenth pass sees the mismatch and acts.

The project's design principles make this a law, verbatim: functionality must be level-based, meaning the system must operate correctly given the desired state and the current observed state, regardless of how many intermediate updates may have been missed. Edge-triggered behaviour is allowed only as an optimization on top. The same document contains a remark the module had no room for, and it is the deep reason: "there should be a CAP-like theorem regarding the tradeoffs between driving control loops via polling or events about simultaneously achieving high performance, reliability, and simplicity. Pick any 2." Kubernetes picks reliability and simplicity, and pays in performance: level-triggered loops re-read state they mostly already agree with. That trade is obviously right when your state is a few thousand rows of desired configuration. It would be obviously wrong for a ten-million-event-per-second log, where the cost term dominates. This is a design choice, not a law of physics, and knowing which side of it a system sits on tells you how to operate it.

## Why Kubernetes expects you to kill its pods

Two more lines from the same principles document, because they explain behaviour that looks insane the first time you see it. First: "Assume an open world. Example: we allow users to kill pods under control of a replication controller; it just replaces them." An **open-world assumption** means no component believes it has the whole picture. Anything can change state it did not create, so every component tolerates it. Second: "Don't assume a component's decisions will not be overridden or rejected. Retry, but back off and/or make alternative decisions."

This is why the standard maintenance move, "just delete the pod," is safe, and why *fighting* a controller is not. If you try to hold a pod alive by patching around the controller, you have made yourself a competing control loop, and the controller will never stop disagreeing with you. The whole system is built on the bet that reconciling beats preventing. Chaos engineering, deleting things on purpose in production to prove recovery works, is not a stunt layered on top of Kubernetes. It is using the architecture the way it was assumed to be used.

## How independent loops compose without ever talking

Notice what did not happen when your pod came back. The replica controller did not call the scheduler. The scheduler did not call the kubelet. No component instructed any other. Each read the database, saw work that was its, did it, and wrote the result back. The *composition* happens in the shared store: controller A's output is controller B's input, and neither knows the other exists.

A second example shows why this matters for features added later. The Horizontal Pod Autoscaler (a controller that changes replica counts based on load; Phase 1 covers it properly) does not create pods, delete pods, or talk to the scheduler. When load rises, it edits one number: the replica count on your **Deployment**, the object that states how many copies should run. The Deployment's own controller notices the desired count changed and creates pods. The scheduler notices unbound pods and places them. Kubelets notice assignments and start containers. Three loops, one written years after the others, cooperating with zero new integration code, because the integration surface was always the database. This is the payoff of section 8's one-door rule: the database is not just storage. It is the only API between components.

## What your deploy pipeline is really doing

Your original module mapped this model onto an internal deploy pipeline at your previous employer, with repo paths and account IDs you cannot reuse or show anyone. This is the public equivalent, and the mapping itself survives intact.

Take **Helm**, the most widely used packaging tool for Kubernetes, and the deploy tool thousands of public pipelines are built on. In Helm vocabulary, a **chart** is a templated bundle of Kubernetes object definitions, and a **values file** is the concrete parameters for one release: image tag, replica count, resource limits. A typical CI pipeline does this: render the chart with the values file into plain YAML manifests, then POST those manifests to the API server. That is the entire deploy. The pipeline never starts a container, never SSHes anywhere, never touches a load balancer. It writes desired state into the database through the one door, and every loop you have met does the rest: scheduler places, kubelet starts, the old version's objects are wound down. Once you see your deploy tool as "a program whose whole job is to keep the database's desired-state rows matching the git repository," every piece of later-phase machinery, GitOps tools like Argo CD included, reads as a variation on the same sentence.

## Where this design breaks: Monzo, 27 October 2017

This architecture's price is that its correctness is *eventual*, and its clients cache what they last saw. Monzo, a UK bank running on Kubernetes, paid the full price in public. What follows is cross-corroborated by The Register and InfoQ, both quoting the engineering lead's postmortem, and catalogued in the community kubernetes-failure-stories list; the original postmortem thread itself was identified but not re-read for this lesson, so treat fine detail as reported, not primary.

**What broke, as it first appeared.** Around 14:10 UK time, after a routine change to a payment-processing service, payments began failing. Inbound payments were delayed, outbound ones failed outright.

**The wrong theory, and why it was reasonable.** The natural move in a Kubernetes incident is to restart the sick processes. Monzo restarted their routing layer, built on linkerd, at scale. This made it catastrophically worse: freshly restarted routers had no cached view of the world, asked the API server for their service lists, got an empty response shape they could not parse, and crashed with null-pointer errors. A service-specific outage became a platform-wide one. Everything you have read in this phase tells you restarting is safe. The caveat is that a restarted component recovers *through the watch path*, and that path was the broken part.

**The signal that located it.** Two weeks earlier, Monzo had grown its etcd cluster from three nodes to nine, and a bug, in Kubernetes or the etcd client per the engineering lead's account, silently broke request handling after that reconfiguration. Desired state in etcd stayed correct. Loops kept reconciling correctly. But the *watch stream*, the channel the routing layer used to learn where pods were, had stalled. The routers served from a two-week-old cache and sent traffic to pod addresses that no longer existed. Desired state fine, every loop running, every dashboard component "healthy," production down. That coexistence is not a paradox; it is section 6's model with one silent failure in the one layer nobody alarmed on.

**The fix.** Two desired-state edits, no imperative orchestration: deploy a newer router version compatible with the API server's responses, and delete Kubernetes services with zero replicas so the empty responses that crashed the parser stopped occurring. Follow-up work rebuilt the etcd fleet across three zones so quorum survives multiple member failures, attacking the root in the store layer, which is where section 7 said the blast radius lives.

**What it costs you.** The stall was silent for two weeks because nothing monitored the watchers. Your own stack has watching clients too: anything caching service endpoints, anything caching config, any mesh or proxy. The one check worth adding this week is a freshness alarm on what your watchers last saw, not a health check on whether they are running. A live process with a stale view is the least detectable failure this architecture can produce.

## Checkpoint 0

Answer each in your own words, from this article alone.

1. In one sentence each: what does the scheduler decide, and what does the kubelet do with that decision? Who carries the message between them?
2. You deleted a pod and your user-visible copy count did not drop for more than seconds. Explain, using spec, status and the control loop.
3. Your routing layer learns pod addresses by watching the API server, and that watch stalls silently overnight. Every row in etcd is correct. What do your users experience, and why? What alarm would have caught it?
4. You kill a pod that a controller manages, and the documentation calls this safe and expected. Which design assumption of the project makes it safe?
5. `kubectl apply` and a bash deploy script can carry the same change to the cluster. Which one decays, and why?

The page's cheat sheet section below is the compressed version of this whole phase; use it after you have answered, not before.

## Cheatsheet — Phase 0

- **The shift**: manage applications, not machines. The machine is furniture.
- **Declarative model**: `kubectl apply` is an UPDATE on desired-state rows. You never say how.
- **One database**: etcd holds all cluster state. Consistent, highly available key-value store.
- **One door**: only the API server talks to etcd. Every component, and you, go through it.
- **The loops**: scheduler places, controller manager keeps counts true, kubelet runs what is assigned to its node. Each reads spec, reads status, acts on the difference, forever.
- **Level-triggered**: loops read full state each pass; missed events are recoverable by construction. Reliability and simplicity, paid for with performance.
- **Open world**: killing managed pods is expected and safe. Fighting a controller is never safe, because it reconciles forever and you sleep.
- **Self-healing** is a consequence of state-in-a-store plus loops, not a feature.
- **The failure to fear**: a watching client with a silently stalled stream. Desired state correct, loops healthy, users down. Alarm on freshness, not liveness.

## Two things you could post

- "kubectl delete pod deletes nothing. It edits a row in a database and waits for a loop to disagree." Your angle: you are learning this as a course and can walk the mechanism end to end, not just repost the aphorism.
- "A bank lost payments for over an hour while every Kubernetes component worked exactly as designed." Your angle: the Monzo 2017 outage retold as the price of watch-based eventual consistency, with the monitor-the-watchers lesson operators still miss.

## Sources

- The module itself: https://raghu-monitoring.vercel.app/study/kubernetes-phase-00-why-k8s-exists (digest: quarantine/2026-09-13-kubernetes-phase-00-why-k8s-exists-study.md)
- Kubernetes Cluster Architecture: https://kubernetes.io/docs/concepts/architecture/
- Control-plane to node communication: https://kubernetes.io/docs/concepts/architecture/control-plane-node-communication/
- Borg paper: https://research.google/pubs/large-scale-cluster-management-at-google-with-borg/ (Verma et al., EuroSys 2015)
- Borg, Omega, and Kubernetes (ACM Queue retrospective by the three systems' authors): https://queue.acm.org/detail.cfm?id=2898444
- Kubernetes design principles (archived): https://raw.githubusercontent.com/kubernetes/design-proposals-archive/main/architecture/principles.md
- Monzo coverage: https://www.theregister.com/software/2017/10/31/kubernetes-bug-ate-my-banking-app-how-code-flaw-crashed-brit-upstart/428731 and https://www.infoq.com/news/2017/11/Monzo-Outage-Post-Mortem/
- Failure catalogue: https://codeberg.org/hjacobs/kubernetes-failure-stories
