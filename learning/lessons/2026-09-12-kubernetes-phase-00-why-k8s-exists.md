# Kubernetes Phase 0 — Why K8s Exists (taught version)

**The claim.** Kubernetes is three things: one database (etcd), one gatekeeper in front of it (the API server), and many small loops that only read and write that database. No component ever calls another. Everything you rely on, self-healing, rolling deploys, service discovery, falls out of that single decision.

Two things make this non-obvious. First, the watch streams those loops use are lossy. Events get dropped. The system stays correct anyway, because each loop periodically re-reads the current state and re-derives what to do. Second, that exact property is why Reddit's whole fleet failed for 314 minutes in 2023 while every controller was working perfectly. Level-triggered loops are only as right as the state they reconcile against.

You wrote this module to study from. This version keeps its shape, goes to the mechanism underneath, adds the failure, and corrects three things that moved.

---

## The mental model

Hold Kubernetes as one versioned store plus many thermostats.

The store (etcd) keeps two columns for every object: what you asked for (spec) and what it observes (status). Each thermostat (a controller) reads both, decides one small correction, and writes it back. Then it sleeps until the store changes again.

The thermostat analogy is the project's own, and it earns its place. A thermostat does not remember a sequence of instructions. It reads the current temperature and the target, and acts on the difference. Time passing does not corrupt it. That is the whole design: no commands, only targets; no calls, only reads and writes on shared rows.

The harder shift is what you name. Before orchestration you name machines: "nginx lives on box 14". Kubernetes asks you to name applications: "3 replicas of web". The orchestrator owes you admission (will it fit), scheduling (where), healing (keep it there), and identity (how anyone finds it). Box 14 stops being an addressable concept.

---

## 0.1 The problem: what you would build without it

Your module asks: how many people does it take to run ~1400 services on raw EC2? Run the thought experiment properly, because the answer tells you what an orchestrator actually is.

### The registry you would write

Without Kubernetes you would write three things:

1. A registry table: `service, host, port, health`. Some Postgres table or a Consul cluster.
2. A health-checker cron that updates it.
3. Deploy scripts that read the registry, SSH to a host, swap the process, update the row.

This works. Real companies ran on exactly this for years. It breaks in three specific places:

- **A machine dies at 3am.** Who moves the service? Your scripts know how to deploy; they do not know how to *want*. Nothing in the system holds the sentence "web needs 3 replicas", so nothing notices the count dropped to 2.
- **Packing.** Two services need RAM on the same night. Human judgment picks boxes, and humans pack badly. This is where the money goes.
- **The row goes stale.** The move script crashed between killing the old process and updating the registry. Now service A connects to a dead IP. Nobody's deploy failed; the system's *memory of reality* is wrong. This is the network identity problem, and it is a failure class of its own (Checkpoint Q3 lives here).

### Why Google built Borg (the numbers)

The honest postmortem of this era is the Borg paper (Verma et al., EuroSys 2015). Your module points at it; here is the quantitative core it gestures at.

Borg runs hundreds of thousands of jobs across clusters of tens of thousands of machines. The paper's central claim is economic. The features that matter are admission control (refuse work that does not fit), task packing (fill machines), over-commitment (reclaim resources a job reserved but is not using), and machine sharing with process-level isolation (unrelated jobs on one box, safely).

Why "manage applications, not machines" wins: the moment the unit of accounting is the machine, utilization is a human discipline problem and humans lose. The moment the unit is the application, utilization is a packing algorithm and algorithms win. The declaration, "this job needs 2 CPU and 4GB, run 500 copies", becomes the versioned artifact, and the cluster becomes a function of the artifact.

Kubernetes is the third iteration of that lineage: Borg taught the model, Omega rebuilt the control-plane around a shared store, Kubernetes is the open version of the store design. That history matters because it explains Phase 0's whole architecture: the shared store came *first*, and the controllers came after as clients of it.

### Keep in your head

The orchestrator is not a deploy tool. It is the thing that answers three questions continuously: what should be running, where, and how does everyone find it. All three answers live in one database. That database is Phase 0.

---

## 0.2 Desired state: declarations do not decay

### Commands decay, declarations do not

A command's effect is tied to the moment it ran. `ssh box-14; start nginx` creates a fact in the world and remembers nothing. Tomorrow box 14 dies, and the universe no longer contains any trace that nginx was supposed to exist.

A declaration stores the intent itself in durable storage: "spec: 3 replicas of web, image X". The effect derived from it (3 running pods) is recomputed constantly. When a pod dies, the difference between spec (3) and observed (2) reappears, and a loop closes it. The system does not remember the command; it re-derives the consequence.

### What `kubectl apply` actually is

Your module's framing is exact, so keep it: `kubectl apply` is an UPDATE on a row in a database.

When you run it, the request goes through the API server's chain: authenticate (who are you), RBAC (may you write this kind of object), admission (mutating and validating webhooks, quotas, defaults), then store (write to etcd). The command returns after the etcd write succeeds, typically in tens of milliseconds.

What is true at that moment: the desired state is durably stored. Because etcd is raft-replicated, that fact survives API server restarts and even the loss of a minority of etcd members.

What is NOT yet true: anything about the real world. No pod exists. No image was pulled. The rollout happens later, as the side effect of controllers that were watching. This is why `apply` returning success guarantees nothing about your deploy, and why `kubectl rollout status` exists as a separate command: it watches the *status* side of the same row until observed matches desired.

### The claim your module leaves unproved

Section 0.2 of the module says missed events cannot cause drift. That is not true because watches are reliable. Watches are not. It is true because of a specific mechanism, and you should know it cold before Phase 1. It gets its own section below (0.4, depth).

---

## 0.3 The architecture: one database, one gatekeeper, only watchers

### The chain

The module's t=0 to t=60s choreography, with the mechanism filled in:

- **t=0.0s** — `kubectl apply -f deploy.yaml`. The request hits the API server: authN, RBAC, admission, then a transactional write to etcd. etcd bumps its cluster-wide revision counter and persists the object.
- **t=0.1s** — Every controller that watches Deployments gets an event. Not from etcd directly. The API server runs a watch cache: roughly one watch per resource *type* to etcd, a sliding window of recent events in memory, and fan-out to the thousands of client watches. This is why thousands of controllers do not melt etcd.
- **t=0.2s–1s** — The Deployment controller reads the new object, computes the diff, and writes a ReplicaSet. The ReplicaSet controller writes Pod objects (just rows; nothing runs yet). The scheduler sees Pods with no node assignment, picks nodes by resource fit and constraints, and writes `pod.spec.nodeName` back. Still nothing running. Only rows.
- **t=1s–10s** — The kubelet on each chosen node sees a Pod assigned to it. It pulls the image, asks the container runtime to start it, and writes status back: `pod.status.phase = Running`.
- **t=10s–60s** — The EndpointSlice controller sees ready Pods and writes EndpointSlice objects naming their IPs. kube-proxy, watching EndpointSlices on every node, programs DNAT rules so the Service's virtual IP reaches those pod IPs. Traffic flows.

Note what never happened: the API server never called the scheduler. The scheduler never called the kubelet. Every arrow is a read or a write on etcd, fanned out through the API server's watch cache. That is why the control plane degrades by restarting a component and catching up, not by corrupted half-conversations.

### Two updates, because this section has drifted since the module was written

**1. Endpoints are EndpointSlices now.** The module says "the endpoints controller adds the IP to the Service endpoints". The modern path: the endpointslice controller populates EndpointSlice objects (grouped, sharded slices of pod IPs per Service), and kube-proxy watches those. The legacy Endpoints API is deprecated and survives only as a compatibility mirror. Same mental model, different objects. If you run `kubectl get endpointslices` on any current cluster, that is what kube-proxy is actually consuming.

**2. kube-proxy's "programs iptables" needs a footnote.** Still the default: as of Kubernetes 1.37, the default Linux kube-proxy mode is iptables, installing per-Service, per-endpoint DNAT rules. But: nftables mode is GA since 1.33 (needs kernel >= 5.13), ipvs mode is deprecated since v1.35 and scheduled for removal in v1.43, and a future release flips the default to nftables. Also, since v1.28 iptables mode applies only changed rules per sync, so the old advice to raise `minSyncPeriod` is mostly outdated (defaults: `syncPeriod` 30s, `minSyncPeriod` 1s). The mental model (kube-proxy turns EndpointSlice changes into local forwarding rules) survives all three backends. The backend names are what your debugging commands will reference.

---

## 0.4 The control loop: level, not edge

### The loop

Every controller runs the same shape:

```
for {
    desired := observe(spec rows)
    actual  := observe(status rows and the world)
    if desired != actual { makeOneCorrection() }
    sleep until the store changes
}
```

Level-triggered means it acts on the *current level* of state, not on the history of events. Edge-triggered means it acts on each event as it arrives. Kubernetes chose level, and the official controllers doc says why in its own words: prefer many simple loops over one interlinked monolith, and design each loop to tolerate its own death and restart.

Edge-triggered systems have a fatal property: a missed event is lost forever. If your provisioning script crashed during the event, the state you missed never gets made. Level-triggered systems have a different fatal property: a wrong *level* is faithfully executed, forever, by every loop. You will meet both. Reddit met the second.

### Composability: the HPA stack

The module's HPA example is the composability proof. Horizontal Pod Autoscaler writes `replicas` on the Deployment row. Deployment controller writes ReplicaSet. ReplicaSet controller writes Pods. Scheduler writes node assignments. Kubelet writes status. Six loops, none aware of the others, coordinating only through the database. You can replace any one of them (your own operator instead of the Deployment controller) because the interface is rows, not APIs.

### Depth: how "it was WATCHING" actually works

This is the mechanism the module skips, and it is where interview answers and production debugging live.

**etcd is MVCC.** Every write increments a cluster-wide revision counter. Nothing is overwritten in place; a write appends a new revision of the key. Old revisions are deleted by a background job called compaction. After compaction, history before that revision is gone for good. The default auto-compaction retention is about 5 minutes of history.

**resourceVersion.** Every Kubernetes object carries a `resourceVersion`, which maps to etcd's revision. The official docs warn twice: treat it as an opaque string. Do not parse it as a number, do not compare two of them.

**List-then-watch.** The standard controller pattern is: LIST the current objects, which returns a consistent snapshot plus the resourceVersion of that snapshot, then open a WATCH starting at that resourceVersion. Together that yields "everything that happened after a known-consistent point". This is what a client-go informer does the moment you start it.

**410 Gone is the key failure mode.** Open a watch from a resourceVersion older than the compaction window and the API server answers `410 Gone`: "resourceVersion too old". The events between then and now were compacted; there is no stream to replay. The client must re-list current state and re-anchor. Informers do this automatically. Every watch gap is healed by re-reading the *current* state, which is exactly why drift cannot accumulate.

**Bookmarks.** During quiet periods a watch sends nothing. A long-idle watch could slide past the compaction window without ever receiving an event. Bookmarks are synthetic "nothing changed, latest revision is N" events (`AllowWatchBookmarks`) that re-anchor idle watches so they do not fall into 410 territory.

**Ops symptoms you will recognize later.** Watch storms after an API server restart (every informer re-lists at once), watch-cache memory pressure, informers stuck in repeated relist loops. Metrics: `apiserver_watch_cache_stale_total`, `apiserver_watch_cache_capacity`.

### Why "missed events cannot cause drift" is true

Put the pieces together. The watch stream is an edge-triggered, lossy hint. The correctness comes from the loop around it: on every gap (410, disconnect, restart), the informer throws away event history and re-reads the current state. The controller then reconciles against the level, not the log. A missed notification is not lost forever *because notifications were never the source of truth*. The rows are.

Keep both halves. The level model is what makes restarts safe. The level model is also what makes a wrong row catastrophic, executed perfectly at fleet scale.

---

## 0.5 The same picture in any Helm shop

Almost nobody types `kubectl apply` in production. You deploy through a pipeline, and every pipeline of this shape maps onto the vocabulary above:

- **A values file is the desired-state source.** It is the declaration; git is its durability story; the diff on it is the audit log.
- **The chart is the compiler.** It turns one service's intent into the full object set — Deployment, HPA, PodDisruptionBudget, ServiceAccount — the way a compiler expands one function call into many instructions.
- **`helm upgrade --install` is the write path**, standing in for `kubectl apply`. Helm adds one thing apply lacked: release state, its own record of what it installed. That is both a feature and a divergence risk (below).
- **A namespace is the tenancy and blast-radius boundary.** Which cluster it sits in is the network and account boundary.
- **A control plane is scoped to exactly one cluster.** That is a property of the design, not an oversight, and it is why a fleet of clusters has no global view for free. Anything cross-cluster — fleet dashboards, failover — is a layer you add on top (the Argo world of Phase 4).
- **Config deploys and code deploys are the same mechanism.** An env value renders into the pod template; the template hash changes; the Deployment controller sees a new spec and rolls. One mechanism — which is why "config-only deploy" and "code deploy" share a pipeline.

### Where the mapping breaks: drift between what Helm thinks and what is running

That leaves one question open: what breaks when Helm's release state diverges from git. Three real sources: someone runs a manual `kubectl edit` against a live object (now the cluster disagrees with the values file), a release is upgraded outside CI (now Helm disagrees with git), or the chart changes for a service that was never redeployed (now git disagrees with the cluster).

All three are the same disease: two stores of desired state, no loop reconciling them. That is precisely the gap GitOps closes (Argo, Phase 4): a controller whose job is "cluster spec must equal git", reconciling continuously. You do not need Phase 4 to respect the principle: **there must be exactly one writable source of desired state. Every other write path is an incident seeding itself.**

---

## Where it breaks in production: Reddit, Pi Day 2023

The canonical Phase 0 incident. Walk it in order.

**What broke, as it first appeared.** March 14, 2023. Reddit's team upgraded the control plane of the cluster running Old Reddit from 1.23 to 1.24. Within minutes: all inter-node routes dropped cluster-wide. Metrics went dark. Internal DNS failed. Image pulls failed. Calls from the API server to an OPA admission webhook failed, which wedged the control plane itself. The symptom looked like total cluster death during a routine, well-practiced upgrade.

**What they found.** Kubernetes 1.24 removed the node label `node-role.kubernetes.io/master`. Reddit's Calico route reflectors (the BGP speakers that distribute pod routes between nodes) selected their peers and nodes *by that label*. The upgrade was correct. Every controller reconciled perfectly against the new state, and correctly concluded there were no route reflector nodes. So the loops tore down every peering. Desired state said "no masters"; actual state agreed; the system stayed wrong for 314 minutes. This is Checkpoint Q3 in production costume: no controller was broken, and that was the problem.

**The fix, in two layers.** Stop the bleeding: with no supported downgrade path, recovery meant restoring the control plane from a pre-upgrade etcd backup. This is the module's "one database is the whole cluster" claim from the recovery side. And the restore nearly failed three ways: the restore procedure had rotted (it predated their Docker to CRI-O switch), restored nodes had TLS certs that did not match AWS-generated hostnames, and AWS had no spare capacity in the region for the control-plane instance type. Stop it recurring: Reddit's own root cause was knowledge lost through attrition plus a bespoke cluster configuration that existed nowhere in code. The fix they committed to is section 0.5's discipline: cluster config as versioned, declarative artifacts, redeployable by definition.

**The detail worth remembering.** Bringing traffic back, they ramped 1% to 5% to 10% to 100% to avoid a thundering-herd cache collapse. Recovery is a rollout too.

**What it costs you.** This failure was workload-side: a network controller reacting to a label change. It applies fully on managed EKS, where AWS owns etcd backup but not your Calico config. Your concrete exposures: anything in your clusters that selects nodes by labels you did not define yourself; anything that depends on a Kubernetes API or annotation that can be removed between minor versions; any admission webhook that can wedge the control plane when it is unreachable. One check this week: `kubectl get nodes --show-labels`, and grep your network-policy and CNI config for labels starting with `node-role.kubernetes.io`. If anything depends on `master`, you are one upgrade from Reddit's afternoon.

---

## Corrections to the module (it is mostly right; three things moved)

1. **EndpointSlice, not Endpoints.** Kube-proxy watches EndpointSlice objects written by the endpointslice controller; the legacy Endpoints API is deprecated, a compatibility mirror only.
2. **kube-proxy mode landscape.** iptables still the default (as of 1.37), but nftables is GA since 1.33, ipvs deprecated since 1.35 and removed in 1.43, and the iptables default will flip to nftables in a future release. Since 1.28, iptables mode syncs only changed rules.
3. **"Level-triggered" needs its footnote.** Watches are lossy edge streams. The level-triggered guarantee is built from list-then-watch plus relist-on-410, not from the watch itself. Same mental model; different confidence about where correctness lives.

Optional trivia, not a correction: since v1.32 the API can speak CBOR (alpha, feature-gated) alongside JSON, and `resourceVersion` is formally opaque.

---

## Labs

The phase has no labs, so here are three. You need [kind](https://kind.sigs.k8s.io/) or minikube. Total time: about 40 minutes.

### Lab 1 — Watch a deploy happen as object changes (15 min)

```bash
kind create cluster --name phase0

# Terminal A: watch the store change
kubectl get pods -w

# Terminal B
kubectl create deployment web --image=nginx:1.27 --replicas=2
kubectl rollout status deployment/web
```

Terminal A shows the *effect*: pods appearing with no deploy command ever touching a node. Now the level-trigger proof:

```bash
kubectl delete pod <one-of-the-two>
```

Terminal A shows the pod vanish and a replacement appear. You never asked for a replacement. The ReplicaSet controller read desired=2, observed=1, and closed the gap. That was your homegrown registry's 3am failure, deleted.

Cleanup: `kubectl delete deployment web`.

### Lab 2 — Do list-then-watch by hand (15 min)

See the actual mechanism rather than take 0.4 on faith.

```bash
kubectl proxy --port=8001 &

# LIST: get a snapshot and its resourceVersion
RV=$(curl -s "http://localhost:8001/api/v1/namespaces/default/pods" | jq -r '.metadata.resourceVersion')
echo $RV

# WATCH from that RV (this call hangs, streaming events)
curl -N "http://localhost:8001/api/v1/namespaces/default/pods?watch=true&resourceVersion=$RV"
```

In another terminal: `kubectl create deployment web --image=nginx:1.27 --replicas=2`. Watch the streamed JSON events arrive: ADDED, MODIFIED, MODIFIED again as status flips to Running. Each event carries a resourceVersion. That stream is what every controller in the cluster consumes. ctrl-C to stop.

### Lab 3 — Force 410 Gone (10 min)

Prove the watch is lossy and the relist is mandatory:

```bash
curl -s "http://localhost:8001/api/v1/namespaces/default/pods?watch=true&resourceVersion=1"
```

Response: a `Failure` event, status `410`, reason `Gone`, message "too old resource version". Revision 1 is older than anything the watch cache holds, so there is no stream to give you. A controller hitting this must re-list current state and start a fresh watch. That response, not the watch stream, is the foundation of the level-triggered guarantee. Try also `resourceVersion=0` and read the API-concepts doc on what "most recent" semantics that gets you; the differences matter in Phase 1 when you write your first operator.

Cleanup: `kind delete cluster --name phase0`.

---

## Checkpoint

Answer from the article. If any answer needs outside reading, that section failed you; tell me which.

1. `kubectl apply -f deploy.yaml` returned success in 200ms. State precisely what is true at that moment, and name three things that are NOT yet true.
2. A controller was down for 2 hours. Why can it come back and behave correctly without any event replay? Name the two mechanisms involved (what tells it to re-read, and what it re-reads). What is the failure boundary: what input would make it behave badly on restart?
3. Every controller in the cluster is healthy, every reconcile loop is running, and cluster networking is entirely down. Explain how, in one sentence, using the Reddit incident. Then name the property of level-triggered loops that made them unable to repair it.
4. Why does the architecture forbid components from calling each other directly? What do you give up for that property?
5. Overnight, your pods rescheduled to new nodes. Your homegrown EC2 scripts would have broken; Kubernetes did not. Name the two mechanisms that absorbed the change, and which module section each one comes from.

Answers, in brief: (1) desired state durably stored in etcd; no pod scheduled, no image pulled, no routing updated. (2) The watch gap (or startup) triggers a list of current state; reconciliation runs against the level. Boundary: the stored desired state itself is wrong, as with Reddit's label removal. (3) Controllers reconciled correctly against state that said "no route-reflector nodes", so they correctly tore the network down; loops fix differences, they do not judge intent. (4) Restart and failure isolation: any component can die and catch up from the store. You give up latency (coordination costs watch hops) and any notion of synchronous confirmation. (5) Service identity via virtual IP plus EndpointSlice, and the reconciliation loop re-placing pods by spec.

---

## Cheatsheet

- **One database**: etcd. MVCC, raft-replicated, revision counter, compaction (about 5 min default retention).
- **One gatekeeper**: API server. authN, RBAC, admission, store. Also hosts the watch cache (one etcd watch per resource type, fan-out to clients).
- **Many loops**: controllers. Level-triggered. Act on spec vs status, coordinate only through rows.
- **apply** = UPDATE a row. Returns on etcd write. Rollout is a side effect, later.
- **list-then-watch** = snapshot + resourceVersion, then stream. **410 Gone** = your RV aged out; relist. **Bookmarks** keep idle watches alive.
- **Missed events cannot drift** because relist re-reads current state. **Wrong state cannot self-heal** for the same reason.
- **Service identity**: VIP to DNAT by kube-proxy, fed by EndpointSlice objects. Default backend: iptables (1.37), moving to nftables (GA 1.33); ipvs deprecated (1.35) and removed (1.43).
- **GitOps rule**: one writable source of desired state. Manual `kubectl edit` in a track is drift seeding itself.
- **Reddit 2023**: removed label + Calico selectors = correct loops destroying the network; recovery = etcd restore + 1/5/10/100% traffic ramp.

---

## Two angles you could post

1. "Your Kubernetes controllers are not event-driven, they are level-driven, and the watch stream is a disposable hint." The claim, backed by the 410 Gone relist mechanism and one `curl` showing the failure, is the part nobody's intro tutorial says.
2. "Reddit's Pi Day outage: every controller was healthy and that was the problem." Level-triggered loops faithfully execute wrong state; a removed node label and a Calico selector cost 314 minutes. His angle: the same exposure exists in any managed-EKS cluster that selects on label names it does not own.

---

## Sources

- Your module: https://raghu-monitoring.vercel.app/study/kubernetes-phase-00-why-k8s-exists
- Borg paper: https://research.google/pubs/large-scale-cluster-management-at-google-with-borg/
- Controllers (official): https://kubernetes.io/docs/concepts/architecture/controller/
- API concepts, list/watch/resourceVersion (official): https://kubernetes.io/docs/reference/using-api/api-concepts/
- etcd-to-watch mechanism writeup (corroborating): https://svalle.ru/posts/kubernetes/etcd-to-watch/
- kube-proxy virtual IPs (official): https://kubernetes.io/docs/reference/networking/virtual-ips/
- nftables kube-proxy milestone: https://kubernetes.io/blog/2025/02/28/nftables-kube-proxy/
- Reddit Pi Day postmortem (repost of Reddit's r/RedditEng original): https://postmortem.io/incidents/reddit--2023-03-21--pi-day-outage/
- Study digest this lesson was built from: quarantine/2026-09-12-kubernetes-phase-00-why-k8s-exists-study.md