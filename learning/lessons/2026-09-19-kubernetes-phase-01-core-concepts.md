Everything you will ever debug in Kubernetes traces back to five primitives: Pods, Deployments, Services, ConfigMaps/Secrets, and the network layer underneath them. The 3am CrashLoopBackOff. The deploy that silently dropped 2% of requests. The service that works on one pod but not the other. Phase 0 gave you the control-loop model: desired state in etcd, controllers reconciling reality toward it. Phase 1 is where that model grows hands.

Here is the deal. By the end of this phase you will open the rendered chart for a production service (default-service-template rendering for im-service) and explain every line of the resulting Deployment. Probes, strategy, resources, service ports. Not "roughly what it does." Every line. That is the bar, because every service on a platform across 8 EKS clusters and two AWS accounts lives inside exactly this machinery.

Skip this phase and here is what production does to you. You will set a liveness probe that checks the database, and the first RDS blip will restart every pod in the fleet at the same moment. You will run kubectl apply on a ConfigMap and wonder why the running pods still hold the old value three days later. There is a real incident receipt for that one: April 2025, a doc-store service, and Phase 0's checkpoint already asked you about it. You will put a gRPC service behind a normal ClusterIP and watch 100% of traffic pin itself to one pod out of ten.

Time: 2 to 3 weeks. The exercises are non-negotiable. You need a laptop with Docker, kind, and kubectl.

The original anchored this course to internal code from the author's former job. This page keeps the concrete chart and service names he works from (default-service-template, im-service, healthCheck.sh) because the mechanism lives in them, and drops the company name. Hunter could not verify any of the internal specifics; the page marks each one in the text instead of presenting it as platform fact.

## 0.1 What this phase teaches, and what it does not

What gets introduced here for the first time: pods and the pause container, the Deployment→ReplicaSet→Pod chain with maxSurge/maxUnavailable math, liveness versus readiness probes, Services with kube-proxy and DNS, the gRPC per-connection load-balancing problem, ConfigMap env snapshots versus mounted files, PV/PVC/StorageClass, the AWS VPC CNI, Vault agent injection, and the kubectl command repertoire the checkpoints assume.

What is deliberately not taught here, because later phases own it: the HPA algorithm and its targets (Phase 2 §2.5), KEDA, PodDisruptionBudgets, resource requests and limits, CFS throttling, Karpenter, Argo Rollouts (Phase 4), and Istio outlier detection (Phase 5). You will see HPA name-dropped as "HPA 2→10 @70%" where it is a production fact, never as a taught mechanism.

## 0.2 What we cover in Phase 1

┌──────────────────────────────────────────────────────────────────────────┐
│  1.1  Pods                — the atom: why pods (not containers), pod IPs │
│  1.2  Deployments         — ReplicaSets, self-healing, rolling updates   │
│  1.3  Probes              — liveness vs readiness, the org's exec pattern│
│  1.4  Services & traffic  — ClusterIP, DNS, the gRPC LB problem, Istio   │
│  1.5  ConfigMaps/Secrets  — discovery-configs, Vault, the staleness trap │
│  1.6  Storage             — PV/PVC/EBS-CSI, why a SaaS fleet is stateless│
│  1.7  AWS VPC CNI         — where pod IPs really come from on EKS        │
└──────────────────────────────────────────────────────────────────────────┘

## 0.3 Lab setup: do this now

Everything below assumes a running local cluster. kind is Kubernetes-in-Docker: a 3-node cluster in about 90 seconds.

brew install kind kubectl
cd ~/Desktop/code/verly/study-material/kubernetes/code
kind create cluster --name study --config kind-cluster.yaml
kubectl get nodes        # → 1 control-plane + 2 workers, STATUS Ready

# Build + load the exercise image (kind has no registry; we side-load):
docker build -t hello-server:v1 -f phase01_core_concepts/hello-server/Dockerfile .
kind load docker-image hello-server:v1 --name study

Reading Phase 1 without the lab leaves you able to describe the machinery but not operate it. The exercises are where the probes and the staleness trap become real.

Run the setup above before you read another section. kubectl get nodes showing 3 nodes Ready is your gate.

## 1.1 Pods — the atom you never deploy directly

Every abstraction above the pod (Deployment, ReplicaSet, Job, HPA) exists only to manufacture and manage pods. When something breaks, kubectl describe pod is where you end up. If your mental model of a pod is "it's a container," half of what you see there will not make sense.

First pass, the mental model. A pod is a group of containers that share a network namespace and can share volumes. One IP, one localhost, scheduled as a unit onto one node. Most pods have exactly one app container, but the group is the primitive.

┌─ Node ip-10-81-x-x (EKS worker) ────────────────────────────────────┐
│                                                                     │
│  ┌─ Pod im-service-7d9f8b-x2k4j   IP: 10.81.42.17 ────────────────┐ │
│  │                                                                │ │
│  │  ┌───────────────┐  ┌──────────────────┐  ┌─────────────────┐ │ │
│  │  │ pause         │  │ im-service       │  │ (istio ztunnel  │ │ │
│  │  │ (infra        │  │ (your Go binary, │  │  intercepts at  │ │ │
│  │  │  container —  │  │  ports 80 gRPC)  │  │  node level in  │ │ │
│  │  │  holds the    │  │                  │  │  ambient mode — │ │ │
│  │  │  netns alive) │  │  localhost ◄─────┼──┤  NOT a sidecar) │ │ │
│  │  └───────────────┘  └──────────────────┘  └─────────────────┘ │ │
│  │   shared: network namespace (one IP), IPC, optional volumes   │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘

### The pause container owns the IP

Second pass, the details. The pause container answers a question that sounds like trivia and is not. Containers come and go: they crash, restart, get a new image. But the pod's IP must stay stable for the pod's lifetime. So the kubelet starts a do-nothing pause container first. It owns the network namespace, and your app containers join it. When your Go process crashes and restarts, the IP survives because pause never died. Run docker ps on any node and you will see one pause per pod.

The pause container is a real image, registry.k8s.io/pause, not a kubelet trick. And one lifetime limit the original leaves implicit: if the node dies, the pod IP dies with it. Pod-IP identity is only as durable as the node it sits on.

  Pod im-service-7d9f8b-x2k4j

  pause
  owns netns

  app container
  running
  IP: 10.81.42.17

    1. App container crashes

    2. Pod deleted / node drained

  Click a scenario.

What survives a container crash, and what survives nothing. Illustration of the mechanism, not a measurement.

### Every pod gets a real, routable IP

This is the part that surprises people coming from Docker's port-mapping world. There is no NAT between pods. Pod A at 10.81.42.17 dials pod B at 10.81.43.9 directly, across nodes. On EKS this is literally true at the VPC level: pod IPs are VPC IPs, which section 1.7 explains. Three consequences you will use constantly:

- kubectl get pod -o wide shows an IP you can curl from any other pod. That is your first debugging move.

- Port conflicts do not exist between pods. Every pod has its own :80.

- When a pod dies, its IP is gone forever. Nothing should ever hold a pod IP. That is what Services are for, in 1.4.

### Why more than one container per pod at all

The sidecar pattern: a log shipper reading a shared volume, an Envoy proxy intercepting localhost traffic. There is a nuance here from the author's platform. The old service-mesh world (Linkerd; you will still see linkerd.inject: disabled in values-prod-us.yaml files, and it is dead config) used per-pod sidecars. The current Istio ambient mode deliberately does not. Its proxy, ztunnel, runs per node, so pods stay single-container. Fewer containers per pod means less memory overhead per replica. Multiply that by roughly 1,400 services and it is real money. That service count is an internal figure from the original, not externally verified.

### A bare pod has no supervisor

Third pass, the gotcha. A bare pod, like manifests/01-pod.yaml, has nothing watching it. Delete it, or drain the node it is on, and it is simply gone. The kubelet restarts containers inside a pod; that is what restartPolicy: Always means. But nothing resurrects the pod object itself. This is why "we deploy pods" is technically false everywhere. You deploy Deployments, which is 1.2.

A pod is the unit of scheduling and the unit of IP identity. Containers share it, controllers manage it, and nothing about it is durable.

Treating pod names or pod IPs as stable identifiers in config, dashboards, or code. Both change on every reschedule. Anything that must find a pod goes through a Service or DNS.

kubectl apply -f phase01_core_concepts/manifests/01-pod.yaml, then kubectl get pod hello-pod -o wide and note the IP and node. Then kubectl delete pod hello-pod && kubectl get pods: gone, and nothing brings it back.

Verify: after the delete, kubectl get pods returns "No resources found". If a pod reappears, it was never bare; something above it owns it.

## 1.2 Deployments & ReplicaSets — the self-healing machine

The Deployment is the object you will helm upgrade hundreds of times in your career on a platform like this. Understanding the Deployment → ReplicaSet → Pod chain is what lets you read a half-finished rollout at a glance and know whether it is progressing or stuck.

First pass. You declare "3 replicas of image v2." The Deployment controller creates a ReplicaSet (a pod template plus a count). The ReplicaSet controller creates pods. The kubelet runs them. Kill a pod and the ReplicaSet notices actual(2) != desired(3) and makes another. That is the whole self-healing story: a level-triggered reconcile loop, nothing smarter.

Deployment "im-service"            (owns rollout strategy + history)
    │
    ├── ReplicaSet im-service-7d9f8b   (pod-template hash 7d9f8b, replicas: 2)  ◄ current
    │       ├── Pod im-service-7d9f8b-x2k4j
    │       └── Pod im-service-7d9f8b-m8t1q
    │
    └── ReplicaSet im-service-5c4a2e   (previous version, replicas: 0)          ◄ kept for rollback

That old ReplicaSet at 0 replicas is not garbage. It IS the rollback mechanism. kubectl rollout undo just scales the old ReplicaSet back up and the new one down.

### The rolling update, with real numbers

The org-wide default for the author's platform lives in default-service-template/values.yaml:193-197 and is rendered by the deploymentStrategy helper in _helpers.tpl:288-296. (Internal repo; hunter could not verify the line numbers. The values themselves are the point.)

strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: "50%"          # may run up to 150% of desired during rollout
    maxUnavailable: "0%"     # may NEVER dip below 100% of desired

Internalize what that pair means: capacity never decreases during a deploy. New pods must come up AND pass readiness before old ones are killed. Timeline for a 2-replica service, the production shape of im-service:

┌──────────────────────────────────────────────────────────────────────┐
│ Rolling update, replicas=2, maxSurge=50%→1 extra, maxUnavailable=0%  │
├──────────────────────────────────────────────────────────────────────┤
│ t=0s    [v1] [v1]              desired state changed to v2           │
│ t=1s    [v1] [v1] [v2•]        surge pod created (2+1 allowed)       │
│ t=61s   [v1] [v1] [v2✓]        v2 pod READY (initialDelaySeconds:60!)│
│ t=62s   [v1] [v2✓]             one v1 terminated (still ≥2 ready)    │
│ t=63s   [v1] [v2✓] [v2•]       second v2 created                     │
│ t=123s  [v2✓] [v2✓]            rollout complete                      │
│                                                                      │
│ • = starting/not-ready   ✓ = ready                                   │
│ Note: 60s initialDelaySeconds on the readiness probe means every     │
│ rollout step waits ≥60s. A 10-replica service deploys in ~5-10 min.  │
│ That's not "slow CI" — that's your probe config. Now you know.       │
└──────────────────────────────────────────────────────────────────────┘

One word on that 60 seconds: it is the readiness probe's initialDelaySeconds, not a liveness delay. The rollout cadence is set by how slowly a new pod becomes ready. Section 1.3 shows the fix.

Upstream defaults, verified in pkg/apis/apps/v1/defaults.go at Kubernetes v1.34.0: maxSurge: 25%, maxUnavailable: 25%, revisionHistoryLimit: 10, progressDeadlineSeconds: 600 (the source sets it literally: *obj.Spec.ProgressDeadlineSeconds = 600). Put next to the org's 50%/0%, this is the sharp statement: the platform paid surge capacity to buy the no-dip guarantee, where the upstream default would dip 25% mid-rollout. And revisionHistoryLimit: 10 caps the kept old ReplicaSets: past 10 revisions, rollout undo history is gone.

Source: kubernetes v1.34.0 defaults.go

  Ready pods over a 4-replica rollout

-
  desired = 4

  Platform: surge 50 / unavail 0

  Upstream default: 25 / 25

Minimum ready capacity during a rollout under two strategies. Illustration of the mechanism, with the verified upstream defaults from v1.34.0 — not a measured run.

Click a strategy: 4 replicas, watch whether ready capacity ever dips.

The contrast case inside the org's own fleet: maxUnavailable: 25%, which some older values files like content-management-workers use, tears down old pods before replacements are ready. Fine for async workers, unacceptable for request-serving paths. Check what your service uses.

Real production numbers to calibrate against, from the author's internal dashboard, checked against the internal charts repo. Both are internal sources; hunter could not verify them, so treat the numbers as calibration, not ground truth:

┌────────────────────────┬───────────┬──────────────────┬─────────────┐
│ Service (prod)         │ replicas  │ HPA min→max      │ HPA target  │
├────────────────────────┼───────────┼──────────────────┼─────────────┤
│ im-service             │ 2         │ 2 → 10           │ 70% cpu/mem │
│ content-center-service │ 2         │ 2 → 4            │ 80% cpu/mem │
│ im-service (staging)   │ 3         │ 3 → 4            │ 80%         │
└────────────────────────┴───────────┴──────────────────┴─────────────┘

Base replicas of 2 is not stinginess. It is the floor for surviving one node failure, with HPA (Phase 2) doing the real scaling.

### The gotchas

- The selector is immutable and is the contract. spec.selector.matchLabels must match spec.template.metadata.labels, and you cannot change it after creation. If two Deployments' selectors overlap, their ReplicaSets fight over the same pods. A genuinely miserable failure mode.

- A rollout can wedge silently. If the new pods never pass readiness (bad config, a missing ConfigMap key), you get old pods serving plus new pods crash-looping plus a rollout that waits forever. kubectl rollout status deploy/<name> is the check. progressDeadlineSeconds (default 600) is what eventually marks it failed. It does NOT auto-rollback.

- kind: Deployment is the rule across the org's fleet; StatefulSets exist only for stateful infra (InfluxDB2, Neo4j-backed docgen). And one correction worth engraving: missions-processors is not a K8s workload at all. projects/missions-processors/missions-processors.json declares "type": "AwsLambda"; the Go consumers run as Lambdas fed by MSK EventSourceMappings (CloudFormation: infra/team-missions/missions-processors-stack/cfn.yaml). When you want the canonical K8s Go service, look at im-service, not missions-processors.

The ReplicaSet suffix 7d9f8b is not random. It is a hash of the pod template's content (hash-pod-template), which is why changing the template spawns a new ReplicaSet and changing only the replica count does not. You can compute it yourself.

A Deployment is versioned desired state. ReplicaSets are the versions. Rolling update = scale new RS up and old RS down under maxSurge/maxUnavailable constraints.

Assuming a merged MR equals deployed code. With maxUnavailable: 0%, a readiness-failing v2 means v1 keeps serving indefinitely while the rollout silently waits. Always kubectl rollout status, or check the deploy job, before declaring victory.

kubectl apply -f phase01_core_concepts/manifests/02-deployment.yaml, then kubectl get deploy,rs,pods -l app=hello to see all three layers, then kubectl delete pod -l app=hello --wait=false && kubectl get pods -w to watch self-healing live.

Verify: after the pod delete, kubectl get deploy hello returns to READY 3/3 (or whatever the manifest declares) without any action from you. If it does not, the ReplicaSet is not reconciling, and kubectl describe rs will say why.

## 1.3 Probes — the config that causes more outages than it prevents

Probes are where a config mistake turns a partial failure into a total one. Colin Breck's line, that misconfigured probes cause more Kubernetes outages than the bugs they catch, matches this fleet: the probe defaults in the shared charts encode several hard-won lessons, and you should know which numbers are load-bearing. (The Breck post is cited in the references; hunter did not re-fetch its exact title or date.)

First pass, the two questions. The kubelet asks your container two different questions, and confusing them is the classic mistake:

┌────────────────┬──────────────────────────────┬───────────────────────────┐
│                │ LIVENESS                     │ READINESS                 │
├────────────────┼──────────────────────────────┼───────────────────────────┤
│ Question       │ "Are you fundamentally       │ "Can you take traffic     │
│                │  broken (deadlocked)?"       │  RIGHT NOW?"              │
│ On failure     │ RESTART the container        │ Remove pod from Service   │
│                │                              │ endpoints. No restart.    │
│ May check deps │ NEVER (DB down → restart     │ Yes — DB conn, warmup,    │
│ (DB, Redis)?   │  loop fixes nothing)         │ cache primed              │
│ Recovers by    │ Process restart              │ Passing again → back in   │
└────────────────┴──────────────────────────────┴───────────────────────────┘

### How the fleet actually probes a gRPC service

Two patterns exist in the fleet, selected by healthchecktype in the values file. The shared chart supports only http and exec. There is no native gRPC probe in default-service-template, and no startupProbe template at all. Read those as chart facts, not Kubernetes facts; the correction box below keeps them straight.

Pattern A, HTTP services. healthchecktype: http. For example ui-shell probing GET /status on port 80, or Go HTTP services probing /health/live and /health/ready on 8000.

Pattern B, Go gRPC services. healthchecktype: exec. The image ships a tiny gRPC client binary, and the probe shells into the container and runs it. From the interactive-missions service:

# healthCheck.sh — this IS the production probe command
cd /app/healthCheck
./healthCheck

// interactive-missions/healthCheck/healthCheck.go (abridged, real code)
conn, err := grpc.Dial(fmt.Sprintf(":%d", ServicePort), ...)   // ServicePort = 80
c := healthCheckService.NewHealthCheckClient(conn)
response, err := c.HealthCheck(ctx, &common.EmptyMsg{}, ...)
if response.Healthy != true {
    panic(nil)    // non-zero exit → kubelet counts a probe failure
}

From the kubelet's chair, that probe is an exec command and an exit code. 0 is pass, anything else is fail. The values-file shape (this exact block appears in content-center-service/values-prod-us.yaml, godam/values.yaml:17-32, picasso/values-prod.yaml:207-217, and the new-service boilerplate .tpl/project_level_values_for_service.tpl:21-38; file paths are internal and unverified):

livenessProbe:
  healthchecktype: exec
  exec:
    command: [sh, /healthCheck.sh]
  initialDelaySeconds: 60      # some JVM-ish services use 120
  periodSeconds: 10
  timeoutSeconds: 10
  successThreshold: 1
  failureThreshold: 3

The original says: "The kubelet doesn't know or care about gRPC." That is true of this org's chart, and false of the platform. Since Kubernetes v1.27 (beta in v1.24), the kubelet has a native gRPC probe, stable, that dials the pod's gRPC health endpoint with no exec and no helper binary. Verified from the Kubernetes probe docs. Two details worth knowing: gRPC probes do not support named ports, and they are plaintext by default. Likewise, "no startupProbe" is a chart gap, not a Kubernetes gap: startupProbes are GA since v1.20 and are the canonical fix for the initialDelaySeconds: 60 hack below. If you defend "Kubernetes can't probe gRPC" in a review, you will lose.

Source: Kubernetes docs: liveness, readiness and startup probes (fetched 2026-09-17). Also of note from the same docs, still alpha and not usable: HTTP probes over h2c, gated by H2CContainerProbe in v1.37, so .internal-grpc h2c services still need exec or gRPC probes for now.

Do the failure math, because you will need it during an incident. A pod goes bad. Worst case before the kubelet acts: periodSeconds × failureThreshold = 30s of failed probes, plus up to 10s of timeout per attempt. For readiness that is up to roughly 30 to 40 seconds of a dead pod still receiving traffic. That window is why clients need retries, and why Istio's outlier detection exists (Phase 5). One more timeout detail: a hung exec probe does not count as failed until it returns or the timeout fires, so with timeoutSeconds: 10 a stuck gRPC health client can eat 10 seconds per attempt. Upstream's default timeoutSeconds is 1 second; this chart deliberately sets 10.

And the initialDelaySeconds: 60 you keep seeing? That is the poor man's startupProbe. Because the chart does not template startupProbe, slow-booting services push the first check out 60 to 120 seconds. The cost: every rollout step waits that long even if the pod was ready in 5 seconds (the timeline in 1.2), and a pod that boots broken serves nothing for 60 seconds before anyone notices. A startupProbe fixes exactly this: the first probe gets a budget of failureThreshold × periodSeconds, and liveness takes over fast after the first pass.

### The cascade, step by step

Internalize this with your own stack; it is the one that eats fleets:

Anti-pattern: liveness probe checks Redis connectivity. Redis blips for 40s.
┌──────────────────────────────────────────────────────────────────────┐
│ t=0     Redis unavailable                                            │
│ t=0-30  ALL pods fail liveness ×3 (10s period × 3 failures)          │
│ t=30    kubelet restarts ALL pods SIMULTANEOUSLY                     │
│ t=30-90 fleet is booting (initialDelaySeconds:60) — capacity = ZERO  │
│ t=40    Redis is back. Nobody is up to notice.                       │
│ t=90    pods boot, cold caches, full retry-storm inbound             │
│         → CPU spike → probe timeouts → SOME PODS RESTART AGAIN       │
│ A 40-second Redis blip became a 10-minute total outage.              │
└──────────────────────────────────────────────────────────────────────┘
Correct: liveness = process-only check. Readiness = may check deps.
Redis blip → pods leave the Service, come back when Redis does. No restarts.

  Redis blips for 40 seconds. Where did the dependency check get wired?

  Liveness checks Redis (wrong)

  Readiness checks Redis (right)
  Click a wiring.

The same 40-second dependency blip, two outcomes. The mechanism behind the timeline above.

Liveness restarts, readiness removes, and only readiness may look at dependencies.

Copying a liveness block into a readiness block. It is identical in most of this fleet's values files, and that is fine only because the health endpoint checks nothing external. The moment your HealthCheck RPC starts pinging MySQL, that copy-paste becomes the cascade above.

Watch readiness pull a pod out of rotation without restarting it: kubectl apply -f phase01_core_concepts/manifests/02-deployment.yaml, then kubectl get endpoints hello -w & in the background, then POD=$(kubectl get pod -l app=hello -o name | head -1) and kubectl exec ${POD#pod/} -- wget -qO- localhost:8080/toggle-ready.

Verify: the endpoints list drops from 3 IPs to 2, and the RESTARTS column stays unchanged. If RESTARTS moved, you toggled liveness, not readiness.

## 1.4 Services, DNS, and the gRPC problem — how traffic actually finds your pods

If you ship gRPC services, this section explains why a service mesh exists at all.

First pass. A Service is a stable virtual IP (ClusterIP) plus a live list of ready pod IPs, selected by label. kube-proxy programs every node's iptables so connections to the VIP get DNAT'd to a random ready pod IP.

   client pod                                       ┌──────────────┐
       │  dial im-service.<ns>.svc.cluster.local:80 │ DNS (CoreDNS)│
       │ ────────────────────────────────────────►  │ → 172.20.x.y │
       │                                            └──────────────┘
       ▼
┌─ node iptables (programmed by kube-proxy) ────────────────────────┐
│  DNAT 172.20.x.y:80  →  one of:                                   │
│     10.81.42.17:80   (pod 1, READY)                               │
│     10.81.43.09:80   (pod 2, READY)                               │
│     ✗ 10.81.44.21    (pod 3 — readiness failing → NOT in list)    │
└───────────────────────────────────────────────────────────────────┘

Two facts hiding in that diagram do real work. Readiness controls Service membership: a not-ready pod is never DNAT'd to, which is the mechanics behind section 1.3. And the pod choice is made per connection, not per request. File that away; it detonates two paragraphs from now.

The original names the pod list "Endpoints" and leaves it there. The object kube-proxy actually reads is the EndpointSlice: stable since v1.21, up to 100 endpoints per slice (tunable with --max-endpoints-per-slice, capped at 1000), and described in the Kubernetes docs as "the source of truth for kube-proxy." The older Endpoints API is deprecated, and mirroring it is deprecated since v1.33. Your kubectl get endpoints commands still work; kubectl aggregates the slices for you. Fix the mental model, keep the commands. One operational detail from the same docs for later: endpoint conditions are serving, terminating, and ready (stable since v1.26), and kube-proxy will still route to a terminating endpoint when all endpoints are terminating, which is the documented reason trailing connections are not dropped mid-rollout. That matters for exercise E11.

Source: Kubernetes docs: EndpointSlices (fetched 2026-09-17).

DNS names you will type daily: <service>.<namespace>.svc.cluster.local, short form <service> within the same namespace. On the author's platform, service-to-service addresses are injected as env vars from generated *-discovery-config ConfigMaps (section 1.5): same-track callers get the short DNS name, cross-track callers the full form. Plain Kubernetes DNS. No Consul, no custom Route53 for east-west traffic.

### The gRPC problem

Second pass. Here is where your stack bites the platform. gRPC runs on HTTP/2, and HTTP/2 opens one long-lived TCP connection and multiplexes every request onto it. Now replay the per-connection fact:

 WRONG mental model (what people assume):        REALITY with ClusterIP + gRPC:
 ┌────────┐   req1 → pod1                        ┌────────┐  ONE connection,
 │ client │   req2 → pod2                        │ client │  chosen ONCE at dial
 │        │   req3 → pod3                        │        │ ═══════════► pod1
 └────────┘   (per-request balance)              └────────┘   pod2: idle
                                                              pod3: idle
                                                 10 replicas, 1 doing all work.
                                                 HPA scales up → new pods get
                                                 ZERO traffic. Forever.

The kube-proxy DNAT happened exactly once, at TCP connect. Every later gRPC call rides that connection. Scale from 2 pods to 10 under load and the 8 new pods sit idle while the original 2 melt. This is the single most-linked Kubernetes blog post for a reason: "gRPC Load Balancing on Kubernetes without Tears."

  Requests served per pod

  pod 1
  pod 2
  pod 3

  HTTP/1.1 style requests

  gRPC over ClusterIP

  gRPC named port → waypoint

Distribution across 3 pods for one busy client under each wiring. Illustration of the mechanism, not a measured run.

Three industry-standard fixes, and what the author's platform chose:

┌──────────────────────┬───────────────────────────┬────────────────────────┐
│ Fix                  │ How                       │ Trade-off              │
├──────────────────────┼───────────────────────────┼────────────────────────┤
│ Headless Service +   │ clusterIP: None → DNS     │ Client must re-resolve;│
│ client round_robin   │ returns ALL pod IPs;      │ every client language  │
│                      │ grpc-go balances per-call │ reimplements it        │
│ Proxy (Envoy/nginx)  │ L7 proxy per-request LB   │ Extra hop, ops burden  │
│ Service mesh         │ mesh data plane does L7   │ Platform complexity —  │
│                      │ LB transparently          │ someone else's problem │
└──────────────────────┴───────────────────────────┴────────────────────────┘

The platform picked the mesh: Istio in ambient mode. Ambient mode is not an experiment: it reached general availability with Istio 1.24 in November 2024 (verified from the Istio blog), so this is a GA data plane about two years old as you read this. Verified in the charts: application gRPC services are all plain ClusterIP (headless services exist only for stateful infra peer discovery: RabbitMQ, Loki, ClickHouse, Hazelcast). The shared Go gRPC client utils have no round_robin resolver config, so grpc.Dial targets a single host:port. And default-service-template/templates/service.yaml does the wiring, with this real template logic:

{{- range .Values.ports }}
  {{- if (hasPrefix "grpc" .name) }}
    istio.io/use-waypoint: waypoint      # ← gRPC-named ports get routed
  {{- end }}                             #   through an Istio waypoint proxy
{{- end }}

That is why the port-naming convention (http-0, grpc-1) in every values file is load-bearing. Naming a port grpc-* is what opts it into L7 per-request load balancing via the ambient waypoint. Name your gRPC port tcp-1 and you are back to the broken diagram above. DestinationRules add per-service policy on top. Real example: hub-analytics-engine uses consistentHash on a company_id header, sticky-by-tenant routing. (Template snippets verified in the internal charts by the author; hunter could not open them.)

### North-south: the ingress layer

Third pass. External traffic today: nginx-ingress is the dominant controller, rendered by default-service-template/templates/ingress.yaml. content-center-service declares ingressClass: nginx with hosts like content-center.internal.prod-us.example.com. (The real hostname uses the company domain; the page rewrites it, the shape is exact.) The *.internal-grpc.* hostnames are ingress-routed h2c (cleartext HTTP/2) to the same ClusterIP services, with TLS terminated at the ingress LB. ALB ingress (ingressClassName: alb) appears only for infra and ops tooling: PMM, Teleport. CoachingApiGateway, a repo you know, is itself another nginx-fronted service acting as the coaching domain's aggregation gateway. There is no Kong or AWS API Gateway in the picture.

The original says nginx-ingress "hits EOL March 2026" and a migration to Higress is in progress, so "expect the ingress layer to change." That deadline has passed. On 2025-11-11, SIG Network and the Security Response Committee announced best-effort maintenance until March 2026 and nothing after: no releases, no bugfixes, no security fixes for discovered CVEs. The announcement also says "existing deployments will continue to function," so nothing breaks on its own; it rots. As of today (2026-09-17), the platform's dominant ingress path is formally unmaintained. The cause is worth remembering: snippet annotations, "yesterday's flexibility" turned "insurmountable technical debt," maintained by 1 to 2 people after hours. The upstream migration pointer is the Gateway API. The Higress migration moved from "coming" to "late" on 2026-03-01.

Source: Kubernetes blog: Ingress NGINX retirement (verified, direct quotes).

A Service load-balances connections; gRPC reuses one connection; so gRPC needs L7 balancing, which in this stack is Istio ambient's waypoint, opted into by naming the port grpc-*.

Renaming or mis-naming Service ports. grpc-1 → internal-1 is a one-line diff that silently turns per-request load balancing into single-pod pinning. Reviewers rarely catch it. Now you will.

kubectl apply -f phase01_core_concepts/manifests/03-service.yaml, then kubectl run -it --rm dbg --image=busybox:1.36 -- sh and inside: nslookup hello (one ClusterIP), nslookup hello-headless (three pod IPs), for i in 1 2 3 4 5; do wget -qO- hello/ | grep hostname; done (hostname varies).

Verify: the headless lookup returns one A record per pod, and the loop prints different hostnames across iterations. Same hostname five times means you hit one connection being reused or a single backend.

## 1.5 ConfigMaps & Secrets — and the staleness trap that has real incident numbers

On this platform, config is not a sidebar: the entire service-discovery mechanism is built out of ConfigMaps. This section separates "I redeployed and prayed" from "I know why the pod has a stale value."

First pass. Two consumption modes, two very different behaviors.

┌─ ConfigMap "hello-config" ──────────────┐
│  GREETING: "namaste"                    │
│  app.properties: |                      │
│    llm.timeout.seconds=25               │
└───────────┬─────────────────┬───────────┘
            │                 │
   as ENV VAR                as MOUNTED FILE
            │                 │
   snapshot at container      kubelet syncs changes into the
   START. Edit the CM →       mounted file within ~60s. Edit
   running pod KEEPS the      the CM → file updates in place —
   old value until restart.   IF the app re-reads it (most don't).

  A running pod consumed the ConfigMap both ways. You edit it now.

  env var (snapshot at start)
  GREETING=namaste

  mounted file (kubelet-synced)
  GREETING=namaste

  kubectl patch cm → "changed!"

One ConfigMap edit, one running pod: the two consumption modes diverge. Mechanism illustration; the exact delay is discussed below.

### The platform pattern, end to end

Open projects/content-center-service/values-prod-us.yaml and you see the whole architecture in one file. Three kinds of entries under project.env:

custom:
- name: CNT_CNTR_SERVICE_ENV          # 1. literal value
  value: prod-us
- name: TDB_SVC_SQLSVC_HOST           # 2. cross-service discovery —
  valueFrom:                          #    THE dominant pattern
    configMapKeyRef:
      key: TDB_SVC_SQLSVC_HOST
      name: tdb-svc-sqlsvc-discovery-config
vault:                                # 3. secrets — from Vault, not git
- mount: vaultcloud/common/kv
  path: prod-us
  key: BACKEND_JWT_SECRET_KEY

The *-discovery-config ConfigMaps are generated at deploy time from CloudFormation stack outputs: RDS endpoints, ElastiCache hosts, SQS URLs, other services' addresses. Your service declares which discovery configs it needs (env.configMaps.services: lists about 16 of them for content-center-service), and Helm renders everything into literal env: entries in the pod spec.

That rendering detail is the crux of change propagation. There is no checksum annotation, no Reloader, no rollout restart in the CI deployer. The author had his internal tooling read the full 661-line deployment.yaml template to confirm. The mechanism is simpler. CI always runs helm upgrade --install (devops/asset-deployer/src/helpers/helm.py:61-76). If you changed your own values file, the rendered pod template changes, the template hash changes, and you get a normal rolling update. Config change = deploy. Clean. (All file paths here are internal; hunter could not verify them.)

### Where the model breaks, with incident receipts

The gap is entries of type 2: a configMapKeyRef into someone else's discovery ConfigMap. If that referenced ConfigMap's content changes, your pod spec did not change; the spec only names the reference. No hash change, no rollout, and your running pods keep the value they read at boot, silently, indefinitely. This is not hypothetical. The author surfaced four real hits from the internal incident tracker (unverified externally; the class of failure is what matters):

- doc-store, 11 Apr 2025 (integration): a DB node was evicted, the discovery ConfigMap still held the old primary IP, and doc-store kept dialing the dead instance until manually restarted. This is the same incident Phase 0's checkpoint planted.

- ruleautomaton, 16 Apr 2025: dependent services failed when discovery ConfigMaps were unavailable during a track blackout.

- ICP-1672 (Mar 2025): an env var wired to the wrong ConfigMap key sent auth callbacks to int-svc-external instead of the production host (the original names the company's production domain; rewritten here).

- STOR-6202 (Jun 2025, open): prod-eu RDS discovery ConfigMaps contain unresolved {{resolve:secretsmanager:rds/...}} placeholder strings; services reading MasterUsername from them get a literal template string as a password.

So the instinct to build: when a service misbehaves after infra changed underneath it, your first question is "when did these pods last restart, and what did the discovery ConfigMap say at that moment?" Compare kubectl get cm <dep>-discovery-config -o yaml against kubectl exec <pod> -- env | grep <KEY>.

Three platform rules the original omits, all verified from the ConfigMap docs. One: a ConfigMap mounted with subPath never receives updates at all. If you see a mounted file that never changes, check for subPath before you check anything else. Two: ConfigMap data is capped at 1 MiB, so large prompt files and config bundles do not belong there. Three: immutable: true ConfigMaps, GA since v1.21, close the whole staleness class by construction, at the cost of name-bump rollouts on every change. And on timing: the total mounted-file delay is the kubelet sync period (60s default) plus the cache propagation delay. The default cache mode is watch, so on any modern cluster, including your kind cluster, the update usually lands in seconds. "Up to 60s" is the ceiling, not the expectation.

Source: Kubernetes docs: ConfigMaps (fetched 2026-09-17).

### Secrets: what is real and what is theater

A Kubernetes Secret is base64-encoded, not encrypted. Anyone with get secret RBAC in the namespace reads everything: kubectl get secret X -o jsonpath='{.data.KEY}' | base64 -d. The platform's live mechanisms, in order:

- Vault via Agent Injector (primary): function-library/templates/_vault.tpl maps your team's 3-letter code to a vaultcloud-<namespace>-approle and emits vault.hashicorp.com/agent-inject pod annotations; secrets are pulled at pod startup. Declared in values as the vault: block above (another live example: prompt-hub/values.yaml:38-48). A secondary vaultConfig.injectionMode: helm mode renders the Secret at deploy time instead (templates/vault-secrets.yaml).

- AWS Secrets Manager + CSI driver (templates/secretproviderclass.yaml, guarded by .Values.iamsecret), specifically for IAM access keys; used by cubejs/analytics and livekit.

- Legacy ownSecret plain K8s Secrets, still visible in a few old charts; discouraged.

- External Secrets Operator and Sealed Secrets: not used. Anything you read about them online does not apply here.

One uncomfortable observation to carry as a lesson, not a list: several production values files contain third-party API tokens as plaintext literal env values committed to git. Pattern 1 exists precisely so that pattern never grows.

On this platform, config changes deploy pods (helm → new template hash → rollout), except referenced discovery ConfigMaps, which change underneath running pods and reach nothing until something restarts.

Debugging a "config not applied" issue by re-checking the ConfigMap object. The object is fine; the pod's env snapshot is stale. Compare kubectl exec <pod> -- env against the ConfigMap, not the ConfigMap against git.

kubectl apply -f phase01_core_concepts/manifests/04-configmap.yaml, then kubectl exec deploy/hello-configured -- env | grep GREETING (namaste), then kubectl patch cm hello-config -p '{"data":{"GREETING":"changed!"}}', then the env grep again (still namaste), then kubectl exec deploy/hello-configured -- cat /etc/config/app.properties; wait and cat again: the file updated, the env var never will.

Verify: on a modern cluster the file usually updates within seconds thanks to the watch cache; allow up to about 60 seconds before calling it broken. The env var stays namaste no matter how long you wait. That asymmetry is the whole lesson.

## 1.6 Storage: PV, PVC, and why a stateless fleet barely uses them

This section matters mostly so you know what NOT to reach for. The interesting content is an architecture decision you should be able to defend in a design review.

First pass. The PersistentVolumeClaim is a request ("1Gi, ReadWriteOnce"). The StorageClass is the how (provisioner plus parameters). The PersistentVolume is the fulfilled result, an actual EBS volume. Pods mount claims, never volumes directly; the claim abstracts where storage comes from.

 Pod ──mounts──► PVC "data-claim"          (request: 1Gi, RWO)
                     │ bound to
                     ▼
                 PV pvc-8f3a...            (the actual resource)
                     │ provisioned by
                     ▼
                 StorageClass "ebs-sc"     (ebs.csi.aws.com, gp3,
                                            allowVolumeExpansion: true)
                     ▼
                 AWS EBS volume in the same AZ as the node

The platform specifics, verified by the author in the charts: all current PVCs use the modern EBS CSI driver (ebs.csi.aws.com) through the org-standard ebs-sc StorageClass, gp3, expandable, installed as an EKS addon via Terraform. The legacy in-tree kubernetes.io/aws-ebs provisioner appears only in old migration artifacts. No EFS anywhere: block storage only, no shared-filesystem pattern.

### The decision that shapes everything

Second pass. Of roughly 1,400+ charts, the services with PVCs are a short, countable list: Loki, PMM/Percona monitoring, RabbitMQ-HA (persistence off by default), Cubestore, one embedded Neo4j. Every product service is stateless by design. State lives in RDS/Aurora, ElastiCache Redis (14 named clusters in infra/elasticache/DEPLOYMENT_CHECKLIST.md), S3, DynamoDB, MSK, Couchbase, OpenSearch. All outside the cluster.

Why that is the right call: the RWO trap makes the argument. An EBS volume attaches to one node in one AZ. Give a pod a PVC and suddenly it can only reschedule onto nodes in that AZ; volume detach and attach add 30 to 120 seconds to every reschedule; maxSurge-style rollouts fight over the single attachment; node drain gets blocked. Stateless pods have none of these constraints. Kill them, move them, scale them, 50%-surge them freely. Statelessness is what makes everything in sections 1.2 to 1.4 cheap. The day you are tempted to write files to a pod volume, the answer is almost always S3.

The 30-to-120-second EBS detach/attach figure is the author's number and a reasonable ballpark for EBS, but hunter did not source-check it this run. Treat it as an order of magnitude: attach is measured in tens of seconds, not milliseconds, which is all the argument needs.

PVC = request, StorageClass = how, PV = result. And on this platform the best PVC is the one you did not create.

emptyDir feels like free local storage, but it dies with the pod and, worse, counts against the node's ephemeral storage. Fill it and the node evicts pods, yours and others'. Scratch space beyond a few hundred MB goes to S3, or declare explicit ephemeral-storage requests.

kubectl apply -f phase01_core_concepts/manifests/06-pvc.yaml, then kubectl get pvc data-claim (Bound, kind's local-path StorageClass), then kubectl delete pod hello-stateful and re-apply, then kubectl logs hello-stateful: two "born" lines, the data survived the pod.

Verify: the second kubectl logs hello-stateful prints both boot lines, so the claim (and the data) outlived the pod that wrote it. If you see one line, the pod wrote into emptyDir or container storage instead of the claim.

## 1.7 AWS VPC CNI — where pod IPs actually come from on EKS

The failure mode this section arms you against, IP exhaustion, is famous for looking exactly like a scheduling bug. Knowing its shape will save you an afternoon someday.

First pass. The AWS VPC CNI plugin runs as the aws-node DaemonSet on every node. It attaches Elastic Network Interfaces (ENIs) to the instance and hands their secondary IPs to pods. Pod IPs are first-class VPC citizens: routable from anywhere in the VPC without overlay or encapsulation. That is why section 1.1's "no NAT between pods" is literally true on this platform.

┌─ EC2 node (e.g. m5.xlarge) ───────────────────────────────────────┐
│                                                                   │
│  ENI-0 (primary)          ENI-1                 ENI-2             │
│  ├ node IP 10.81.40.5     ├ 10.81.42.17 → pod   ├ 10.81.44.3 → pod│
│  ├ 10.81.41.2  → pod      ├ 10.81.42.18 → pod   ├ ...             │
│  ├ 10.81.41.3  → pod      ├ ...                 │                 │
│  └ (14 secondary IPs)     └ (15 IPs)            └ (15 IPs)        │
│                                                                   │
│  m5.xlarge: max 4 ENIs × 15 IPs = 58 usable pod IPs               │
│  → default max-pods for this instance type = 58                   │
└───────────────────────────────────────────────────────────────────┘

### The two ceilings

Second pass. The instance type caps ENIs × IPs-per-ENI, so pod density is a function of instance size, independent of CPU and memory. A huge node with a small ENI budget strands compute. And the subnet caps total IPs: every pod consumes a subnet IP, so a /24 subnet (251 usable) supports about 250 pods across all nodes in it, minus nodes, load balancers, and warm-pool overhead.

  Pod-IP capacity is an ENI property, not a CPU property

Assignable pod IPs per node by instance type, from eni-max-pods.txt at amazon-vpc-cni-k8s v1.20.1 (verified). Prefix delegation off.

The warm pool is the subtle multiplier. For fast pod startup the CNI pre-allocates spare IPs per node: WARM_ENI_TARGET=1 means keep one full spare ENI's worth. Comfort for latency, paid in subnet IPs. The tuning knobs are env vars on the aws-node DaemonSet: WARM_ENI_TARGET, WARM_IP_TARGET, MINIMUM_IP_TARGET, and the big one, ENABLE_PREFIX_DELEGATION. With prefix delegation, each ENI gets a /28 prefix (16 IPs) per slot instead of single IPs: the same m5.xlarge jumps from 58 to hundreds of assignable pod IPs, and allocation pressure on the subnet drops.

Pod-IP caps, verified against misc/eni-max-pods.txt at amazon-vpc-cni-k8s v1.20.1, whose in-file formula is ENI × (IPv4/ENI − 1) + 2: m5.xlarge 58, m5.4xlarge 234, and the NodePool families the platform's Phase 2 will discuss: c5.4xlarge 234, c5a.4xlarge 234, c6g.4xlarge 234, c6g.metal 737. The phase's own example ("16-vCPU m5.4xlarge: ENI limit 234") matches the file exactly.

Source: amazon-vpc-cni-k8s v1.20.1 eni-max-pods.txt

What exhaustion looks like when it hits, so you recognize it in 10 seconds instead of 3 hours: pods stuck Pending or ContainerCreating on a node with plenty of free CPU. kubectl describe pod shows FailedCreatePodSandBox. The CNI logs show InsufficientFreeAddressesInSubnet. It is a networking quota failure cosplaying as a scheduling failure.

### The platform's own CNI config, honestly labeled

Third pass. The author's internal tooling found the config split across two eras. The historical hand-authored manifest (devops-scripts/cluster-upgrades/aws-k8s-cni.yaml) sets ENABLE_PREFIX_DELEGATION=false, WARM_ENI_TARGET=1, MTU 9001. The current eksctl provisioning path (devops-eks-dr/nodegroups/*/cluster.yml) installs vpc-cni as a managed EKS addon with no configurationValues override, which means AWS defaults, not deliberate tuning. No ENIConfig CRs (no custom networking), no in-repo IP-exhaustion postmortems, though a cni-metrics-helper DaemonSet ships ENI/IP metrics to CloudWatch, so detection exists. Treat "have we ever hit exhaustion, and is prefix delegation on today?" as a genuinely open question. The honest check is live: kubectl describe ds aws-node -n kube-system | grep -E "PREFIX|WARM". These are internal-repo findings; hunter could not verify them.

Know the cluster map while we are at the infra layer. This is the world your kubeconfig switches between (source: devops-ci-cd-gl/devops/track_config.json):

┌──────────────────┬────────────────┬───────────────┬─────────────────────┐
│ Cluster          │ Region         │ AWS account   │ Purpose             │
├──────────────────┼────────────────┼───────────────┼─────────────────────┤
│ prod-eks         │ ap-southeast-1 │ 191195949309  │ Production APAC     │
│ prod-us          │ us-east-1      │ 191195949309  │ Production US       │
│ prod-eu          │ eu-west-1      │ 191195949309  │ Production EU       │
│ staging-eks      │ ap-south-1     │ 845925808232  │ Staging             │
│ integration-eks  │ ap-south-1     │ 845925808232  │ Integration         │
│ dev-eks          │ ap-southeast-1 │ (prod acct)   │ Shared dev tracks   │
│ automated-eks    │ ap-southeast-1 │ (prod acct)   │ QA automation       │
│ devops-eks       │ ap-southeast-1 │ 191195949309  │ Internal devops     │
└──────────────────┴────────────────┴───────────────┴─────────────────────┘

Note the real isolation boundary: production lives in account 191195949309, staging and integration in 845925808232. Account-level blast-radius separation, not just naming.

On EKS, pod IPs are VPC subnet IPs served through node ENIs, so pod capacity is bounded by instance type and subnet size, not just CPU.

Pending pods plus free CPU sends everyone to the scheduler. Check describe pod events for FailedCreatePodSandBox first. If it is there, the problem is IPs, and no amount of resource-request tuning will fix it.

Verify your understanding: an m5.xlarge (4×15) with prefix delegation off runs at most about 58 pods. Your pods request 100m CPU each. How much of the 4-vCPU node can pods actually reserve before IPs run out? (58 × 100m = 5.8 cores requested, fine. But flip to 50 pods of 20m sidecar-less microservices on a 16-vCPU m5.4xlarge: ENI limit 234 IPs versus a subnet with 200 free. Now the subnet is your scheduler.)

## 🧪 Hands-on lab — the exercises that teach Phase 1

Work in ~/Desktop/code/verly/study-material/kubernetes/code/. Cluster and image from the setup block at the top. Exercises build on each other; do them in order.

These exercises need a live kind cluster, so none of them can run in the automated sandbox that checks Go and Python labs. All 12 are verify-by-hand against the expected output given. One file detail: E9's manifest is named after the author's former company in your copy of the study material. It is written as 07-fleet-style.yaml here; same file, same content, substitute the real name when you run it.

-  E1. Bare pod mortality. live
Run: kubectl apply -f phase01_core_concepts/manifests/01-pod.yaml && kubectl get pod hello-pod -o wide
Then: kubectl delete pod hello-pod && sleep 2 && kubectl get pods
Expected: pod gone, nothing recreated it.
Teaches: pods have no supervisor; controllers do the healing.

-  E2. The ownership chain. live
Run: kubectl apply -f phase01_core_concepts/manifests/02-deployment.yaml && kubectl get deploy,rs,pods -l app=hello
Then: kubectl get pod <one-pod> -o jsonpath='{.metadata.ownerReferences[0].kind}{" "}{.metadata.ownerReferences[0].name}'
Expected: ReplicaSet hello-<hash> — the pod is owned by the ReplicaSet, not the Deployment.
Teaches: Deployment → ReplicaSet → Pod is a real object graph, not an abstraction.

-  E3. Self-healing race. live
Run: kubectl get pods -l app=hello -w in one terminal; kubectl delete pod -l app=hello in another.
Expected: replacements appear within ~1s, Running in a few seconds. Note the new random suffixes.
Teaches: reconcile loop reaction time; pod names are ephemeral.

-  E4. Rolling update with zero downtime — prove it. live
Run: while true; do wget -qO- --timeout=1 http://localhost:8080/ 2>/dev/null | grep -o '"hostname":"[^"]*"' ; sleep 0.3; done via kubectl port-forward svc/hello 8080:80 & (approximate — a request loop against the service)
Trigger: docker build -t hello-server:v2 -f phase01_core_concepts/hello-server/Dockerfile . && kind load docker-image hello-server:v2 --name study && kubectl set image deploy/hello hello-server=hello-server:v2
Watch: kubectl rollout status deploy/hello and kubectl get rs -l app=hello (two ReplicaSets, counts shifting).
Expected: request loop never errors; old ReplicaSet drains to 0.
Teaches: maxSurge/maxUnavailable in motion; the RS-pair mechanism.

-  E5. Wedge a rollout on purpose (break-it). live
Run: kubectl set image deploy/hello hello-server=hello-server:does-not-exist
Watch: kubectl get pods -l app=hello → new pods ErrImagePull/ImagePullBackOff; old pods still Running and serving.
Verify: kubectl rollout status deploy/hello hangs. Recover: kubectl rollout undo deploy/hello.
Expected: the service never dropped a request while the rollout was broken (maxUnavailable: 0% at work).
Teaches: failed deploys do not take you down, but they do not tell you loudly either. This is the "merged ≠ deployed" trap.

-  E6. Env snapshot vs file sync. live
Run: the sequence in section 1.5's "Try this now."
Expected: env var frozen; mounted file updates within ~60s (usually in seconds on kind, thanks to the watch cache).
Teaches: the exact mechanics behind the doc-store incident.

-  E7. Readiness ≠ restart. live
Run: kubectl get endpoints hello -w in one terminal. In another: POD=$(kubectl get pod -l app=hello -o name | head -1); kubectl exec ${POD#pod/} -- wget -qO- localhost:8080/toggle-ready
Expected: endpoint count drops by one; kubectl get pods shows 0 restarts, the pod Running but READY flips 1/1→0/1.
Recover: toggle again; the endpoint returns.
Teaches: readiness controls Service membership only.

-  E8. Liveness kills (break-it). live
Run: edit 02-deployment.yaml, change the livenessProbe path to /readyz, re-apply, then toggle-ready one pod (as in E7) and wait ~30s.
Expected: RESTARTS increments. The pod was "not ready" but you made liveness see it, so the kubelet killed it. Revert the manifest after.
Teaches: viscerally, why liveness must never check the things readiness checks.

-  E9. The fleet-style exec probe. live
Run: kubectl apply -f phase01_core_concepts/manifests/07-fleet-style.yaml && kubectl get deploy,svc,hpa,pdb -l app=mt-style
Then: kubectl describe pod -l app=mt-style | grep -A3 Liveness to see the exec command.
Kill gRPC from inside: not possible here without killing the process, so run the client manually: kubectl exec deploy/mt-style -- /healthcheck -addr=localhost:9090 && echo PROBE-PASSES
Expected: status=SERVING, exit 0.
Teaches: the exec→gRPC probe pattern the production services actually use. (HPA will show <unknown> targets on kind without metrics-server; that itself teaches where HPA metrics come from. Phase 2.)

-  E10. DNS: ClusterIP vs headless. live
Run: the debug-pod sequence from 1.4's "Try this now."
Expected: one IP versus three IPs.
Teaches: what clusterIP: None changes, and why gRPC client-side load balancing needs it.

-  E11. Graceful shutdown vs dropped requests (break-it, subtle). live
Run: kubectl port-forward svc/hello 8080:80 & then wget -qO- --timeout=15 localhost:8080/slow & (a 10s request) and immediately kubectl rollout restart deploy/hello.
Expected: the slow request COMPLETES. The SIGTERM handler in main.go fails readiness, sleeps 5s, drains. Then read the code: phase01_core_concepts/hello-server/main.go, the shutdown block, and map each step to what you observed.
Teaches: terminationGracePeriodSeconds plus SIGTERM handling equals zero-downtime deploys. Without the handler, every deploy 502s.

-  E12. Secret "encryption" theater. live
Run: kubectl apply -f phase01_core_concepts/manifests/05-secret.yaml && kubectl get secret hello-secret -o jsonpath='{.data.API_TOKEN}' | base64 -d
Expected: plaintext token, no privileges needed beyond namespace read.
Teaches: why Vault injection exists on this platform, and that base64 is not security.

Why E11's 5-second sleep pattern is right, from the EndpointSlice docs (verified): endpoints carry ready, serving, and terminating conditions (stable since v1.26), and kube-proxy keeps routing to a terminating endpoint when all endpoints are terminating, so trailing connections are not dropped mid-rollout. The sleep gives the readiness-fail and the iptables programming time to settle before the process stops accepting work, and terminationGracePeriodSeconds is the budget that makes the whole sequence possible.

Source: Kubernetes docs: EndpointSlices (fetched 2026-09-17).

## 🏢 Anchor — things to check in the codebase

The original anchored this section to the author's former employer's repositories, and that is where he still does these checks. The company name is dropped throughout; the repos, files and line numbers below are kept exactly, so he can run every one. None of it is verifiable from public sources, as hunter flags, and none of it needs to be: these are exercises on his own copies of code.

- Read what every service inherits. Open devops-helm-charts/default-service-template/templates/deployment.yaml (661 lines; skim structure, do not grind). Find: where probes are templated (around lines 264–311), where project.env.custom becomes env:, and confirm there is no checksum/config annotation anywhere. Then open templates/service.yaml and find the hasPrefix "grpc" → istio.io/use-waypoint block from section 1.4. This one chart is the deployment story for nearly every service you own.

- Decode a real prod values file end-to-end. Open devops-helm-charts/projects/content-center-service/values-prod-us.yaml. For each block, say out loud what it renders: replicaCount: 2 plus hpa: {min 2, max 4, 80%}; strategy: {maxSurge 50%, maxUnavailable 0%}; exec probes with initialDelaySeconds: 60; ports http-0/grpc-1 (why is that suffix load-bearing? Section 1.4); resources: requests {150m, 100Mi} / limits {6, 4096Mi} (a 40× CPU overcommit; Phase 2 will ask whether that is sane); the vault: block versus the plaintext ELEVENLABS_API_KEY above it (which pattern is the future, and why).

- Find your own service's probe binary. In interactive-missions: read healthCheck.sh, healthCheck/healthCheck.go, and healthCheckConstants.go (ServicePort = 80). Question: this client dials the gRPC port and calls the internal healthCheckService.HealthCheck RPC. What happens to probe results if the service's gRPC server is up but its Kafka consumers are wedged? Is that the right answer for liveness? For readiness?

- Verify the Lambda correction yourself. Open devops-helm-charts/projects/missions-processors/missions-processors.json and find "type": "AwsLambda", then infra/team-missions/missions-processors-stack/cfn.yaml for the MSK EventSourceMappings. Meanwhile devops-helm-charts/surveillance/missions-processors/values-prod-us.yaml deploys Datadog consumer-lag monitors for it (real alert queries on ai_review_events_consumer_group and others). Question: why might the team have chosen Lambda over a K8s Deployment for LLM-grading consumers? Think cost-per-idle-replica versus 25-second processing latencies versus scale-to-zero.

Anchor 3 has a sharp edge the phase leaves as an exercise: a gRPC server that answers HealthCheck while its Kafka consumers are wedged passes liveness forever. If you wire consumer lag into the probe, use readiness, never liveness. Section 1.3's cascade is the reason.

## ✅ Checkpoint 1 — answer in your own words

Seven questions, each answerable from this phase alone. Answer out loud or in writing before you open a sketch.

Q1. A teammate deploys im-service; CI is green. Ten minutes later, customers still see the old behavior. kubectl get pods -n <track> shows 2 pods 45 minutes old and 1 pod 10 minutes old in 0/1 Ready. Walk through exactly what happened, why zero customers saw an error, which two commands confirm your diagnosis, and what the fix path is.

Answer sketchThe new pod never passed readiness, so with maxUnavailable: 0% the rollout wedged and the two old pods kept serving. Zero errors because the old version never lost a pod. Confirm with kubectl rollout status deploy/im-service (still progressing or timed out) and kubectl describe pod on the 0/1 Ready pod (probe failures in events). Fix: fix the readiness cause, or kubectl rollout undo to return to the previous ReplicaSet.

Q2. Your Go service's readiness and liveness probes both run /healthCheck.sh, which calls the HealthCheck RPC. A new engineer "improves" the RPC to also verify the ElastiCache Redis connection. Two weeks later Redis fails over (40s blip). Describe the fleet's behavior minute-by-minute for the next 10 minutes, and the one-line design principle that was violated.

Answer sketchSection 1.3's cascade, verbatim: all pods fail liveness within about 30s (periodSeconds 10 × failureThreshold 3), the kubelet restarts the whole fleet at once, everything boots through initialDelaySeconds: 60, and cold caches plus a retry storm can knock some pods over again. A 40s blip becomes a ~10-minute outage. Violated principle: only readiness may check dependencies; liveness is process-only.

Q3. interactive-missions scales from 2 to 8 pods under load, but Datadog shows p99 latency unchanged-bad and 6 pods at ~0% CPU. The service is called via gRPC by CoachingApiGateway. Explain the mechanism (down to what kube-proxy did and when), why HPA can't fix it, and the two distinct layers on this platform that are supposed to prevent this, including the naming convention that activates one of them.

Answer sketchThe gateway opened long-lived HTTP/2 connections; kube-proxy's DNAT chose a pod once, at TCP connect, and every multiplexed request rides it. HPA adds pods, but no new connections are opened to them, so they idle. The two layers: the mesh data plane (Istio ambient waypoint doing per-request L7 balancing), activated by naming the port grpc-* so the chart template emits istio.io/use-waypoint: waypoint; and client-side balancing, which this stack deliberately does not use (no round_robin resolver in the shared client). So on this platform the answer is the port name.

Q4. During an integration-track infra migration, an RDS failover changed the writer endpoint. The tdb-svc-sqlsvc-discovery-config ConfigMap was regenerated correctly with the new host. Your service is still failing writes 2 hours later. A colleague says "impossible, the ConfigMap is correct, I checked it." Why are you both right? Show the math on why no rollout occurred, the command pair that proves staleness, and two fixes (one immediate, one structural).

Answer sketchThe ConfigMap object is correct and the pod's env snapshot is stale: both are right. Your pod spec only names the configMapKeyRef, so a content change in the referenced ConfigMap changes no template hash and triggers no rollout. Prove it: kubectl get cm tdb-svc-sqlsvc-discovery-config -o yaml versus kubectl exec <pod> -- env | grep TDB_SVC_SQLSVC_HOST. Immediate fix: kubectl rollout restart. Structural fix: checksum annotation on the referenced ConfigMap data, Reloader, or immutable ConfigMaps with name-bump rollouts.

Q5. Design question: you are building a new async LLM-grading worker (25s per message, bursty MSK topic, near-zero traffic at night). Argue Deployment-on-EKS versus Lambda-with-EventSourceMapping using what you learned from the missions-processors anchor. Name the probe, rollout and scaling machinery you would need on K8s that Lambda gives you free, and one thing K8s gives that Lambda cannot.

Answer sketchLambda wins on scale-to-zero: at near-zero night traffic it costs nothing, while a Deployment's idle replicas (minimum 2 for node-failure tolerance) burn money all night. On K8s you would build the whole path yourself: probes, maxSurge/maxUnavailable rollout config, HPA or KEDA on consumer lag, plus the deployment pipeline. Lambda with an EventSourceMapping gives polling, batching and concurrency scaling for free. K8s' edge: no per-invocation limits or cold starts, which matters when each message costs 25 seconds of compute; long-running, predictable work is cheaper and simpler on reserved pods.

Q6. Show the math: a nodegroup of m5.xlarge (4 ENIs × 15 IPs), prefix delegation off, in a /24 subnet shared by 3 such nodes. Each pod requests 200m CPU. (a) Max pods per node by IP? (b) By CPU (4 vCPU)? (c) Which ceiling binds first, and what event message do you see when the other ceiling binds, and (d) which single CNI setting changes the answer?

Answer sketch(a) 4 × (15 − 1) + 2 = 58 pods per node (matches eni-max-pods.txt at v1.20.1). (b) 4 vCPU ÷ 200m = 20 pods by CPU. (c) CPU binds first here, at 20 pods; when the IP ceiling binds instead, describe pod shows FailedCreatePodSandBox and the CNI logs show InsufficientFreeAddressesInSubnet. The /24 shared by 3 nodes (58 × 3 = 174 IPs of ~251 usable) is comfortable for now. (d) ENABLE_PREFIX_DELEGATION=true hands each ENI slot a /28 prefix and lifts the IP ceiling into the hundreds.

Q7. A colleague proposes mounting a PVC into your service to cache rendered content between requests, "so we don't refetch from S3." List three operational properties of the service that silently degrade the moment the PVC lands (think: 1.2's rollout math, node drains, AZ topology), and the design the platform actually uses for this problem (name the specific infra from the values file you decoded in anchor 2).

Answer sketchThree degradations: (1) rescheduling becomes AZ-pinned and 30-to-120s slower per move because RWO volumes attach to one node in one AZ; (2) rollouts with maxUnavailable: 0% wedge, because the surge pod cannot mount a volume the old pod still holds; (3) node drains block on detach/attach. The platform's actual design for caching rendered content: ElastiCache Redis (the named clusters declared in the discovery configs in the values file) in front of S3, keeping the service stateless.

## 📚 References & Further Learning

Must-do, in this order:

- 🎥 Kubernetes Deconstructed: Understanding Kubernetes by Breaking It Down — Carson Anderson, KubeCon 2017 (33 min). Still the single best "how do the pieces fit" talk; he peels ingress → Service → kube-proxy → CNI layer by layer, exactly the 1.4/1.7 stack. When: watch BEFORE the lab. Slides/source: kube-decon.

- 📄 gRPC Load Balancing on Kubernetes without Tears — kubernetes.io blog (10 min). The canonical statement of the 1.4 problem, by the Linkerd authors. When: read AFTER E10.

- 📄 Kubernetes Liveness and Readiness Probes: How to Avoid Shooting Yourself in the Foot — Colin Breck (15 min). THE probe war-story post; the cascading-failure section is 1.3's diagram in prose. When: read AFTER E8, it will click differently.

- 📄 Official probe docs. Bookmark; the successThreshold/failureThreshold semantics table is the part you will return to.

Production war story:

- 📄 How three lines of configuration solved our gRPC scaling issues in Kubernetes — Jamf Engineering (8 min). A real company hitting exactly the single-pod-pinning failure from 1.4, with graphs. Their fix (MAX_CONNECTION_AGE) is the server-side mitigation nobody mentions; contrast it with the mesh answer from 1.4.

EKS/CNI deep dives, for 1.7:

- 📄 Amazon EKS Best Practices: Optimizing IP Address Utilization. The official treatment of warm pools, prefix delegation, MINIMUM_IP_TARGET; the section on prefix mode is the one to read.

- 💻 aws/amazon-vpc-cni-k8s README. Every env var (WARM_ENI_TARGET, ENABLE_PREFIX_DELEGATION, ...) documented; skim the README table, keep it as reference.

- 📄 Automating custom networking to solve IPv4 exhaustion in EKS — AWS Containers Blog. For when a subnet genuinely runs dry; read only if and when you hit it.

Official docs to bookmark:

- Deployments — the rollout/rollback semantics reference.

- Services — service types and port semantics.

Internal, the real curriculum:

- 💻 devops-helm-charts/default-service-template/ — anchor 1. The chart is the doc.

- 💻 Your internal Istio design doc (ambient mode versus Linkerd/Consul; the original's title carries the company name) — pairs with 1.4.

Hunter additions fetched for this page (2026-09-17):

- Kubernetes v1.34.0 defaults.go — the verified upstream rollout defaults quoted in 1.2.

- amazon-vpc-cni-k8s v1.20.1 eni-max-pods.txt — the per-instance pod-IP caps used in 1.7.

- Kubernetes docs: EndpointSlices — the object kube-proxy actually reads, and terminating-endpoint semantics.

- Kubernetes blog: Ingress NGINX retirement (2025-11-11) — the announcement behind the 1.4 correction.

- Kubernetes docs: ConfigMaps — subPath never updates, the 1 MiB cap, watch-cache timing.

- Istio blog: ambient mode reaches GA — Istio 1.24, November 2024.

## 🗒 Cheatsheet — Phase 1

── OBJECTS ────────────────────────────────────────────────────────────────
pod            → unit of scheduling + IP; mortal; never deployed bare
deployment     → versioned desired state; owns ReplicaSets (one per version)
service        → stable VIP + ready-pod list (EndpointSlices); readiness gates membership
configmap      → env (snapshot at start) or file mount (synced; subPath = NEVER syncs; 1 MiB cap)
secret         → base64 ≠ encryption; real secrets here: Vault agent-inject
pvc/pv/sc      → request / result / how; here: ebs-sc (gp3, CSI); avoid if you can

── COMMANDS YOU'LL USE DAILY ─────────────────────────────────────────────
kubectl get pods -o wide                        # + pod IP and node
kubectl describe pod <p>                        # events = 90% of debugging
kubectl get endpoints <svc>                     # who's actually serving (aggregates slices)
kubectl rollout status|undo deploy/<d>          # is it really deployed / revert
kubectl exec <p> -- env | grep <KEY>            # what the POD thinks config is
kubectl get cm <x>-discovery-config -o yaml     # what config SHOULD be
kubectl logs <p> --previous                     # why did it restart
kubectl get pod <p> -o jsonpath='{.metadata.ownerReferences[0].kind}'

── PRODUCTION SHAPE (this fleet) ─────────────────────────────────────────
strategy         RollingUpdate maxSurge 50% / maxUnavailable 0%  (org default)
                 (upstream v1.34.0 default: 25%/25%; keep 10 RS revisions; deadline 600s)
replicas         2 base + HPA (im-service: 2→10 @70%; ccs: 2→4 @80%)
probes           exec [sh /healthCheck.sh] delay 60-120s period 10 timeout 10 fail 3
                 (gRPC client binary; chart templates no grpc:/startupProbe —
                  the PLATFORM has both: gRPC probes GA v1.27, startupProbes GA v1.20)
ports            http-0, grpc-1 — "grpc" prefix opts into Istio waypoint L7 LB
config           values-<track>.yaml → literal env; discovery via
                 <dep>-discovery-config CMs; helm upgrade = the reload mechanism
config TRAP      referenced discovery-CM content change ≠ rollout → stale pods
secrets          Vault (vaultcloud/<team>/kv, agent-inject) > SM CSI > legacy k8s
clusters         prod/prod-us/prod-eu in acct 191195949309;
                 staging/integration in 845925808232
mesh             Istio AMBIENT (GA Istio 1.24, Nov 2024; ztunnel per node) — no sidecars
ingress          nginx (dominant; UNMAINTAINED since 2026-03 → Higress migration),
                 ALB for infra, h2c for gRPC
storage          stateless everywhere; state → RDS/Redis/S3/DDB/MSK

## 🔍 Things I could not verify

- Every internal-specific claim: the chart file paths and line numbers, the probe snippets, the four incident receipts, the production replica/HPA table, the cluster map and account IDs, the Vault wiring, the Istio waypoint template, the CNI manifest history. Hunter could read none of the internal repos. All are presented as the author's codebase facts, not platform facts.

- WARM_IP_TARGET versus MINIMUM_IP_TARGET semantics: hunter distinguished them from memory of the CNI README, not from a fresh read. The CNI README in the references is the source to settle it.

- EBS detach/attach 30–120s: a standard ballpark, not source-checked this run.

- kubectl get endpoints truncation with "!" past 1000 entries: operator knowledge, not opened; the underlying slice cap is verified.

- The v1.37 probe feature gates (h2c HTTP probes, gRPC probe TLS): docs mark both alpha, so this page does not teach them as available.

- Colin Breck's post title and date: cited from the phase's references, not re-fetched.

- The 2026-01-29 re-affirmation of the ingress-nginx retirement by Steering/SRC: hunter saw the search result, not the body. The 2025-11-11 announcement itself is verified verbatim.

## ✍️ Two things you could post

1. "Everyone asks why my org runs Istio. The honest answer is one port name." The claim: gRPC on ClusterIP silently pins all traffic to one pod, and the fix on this platform is the grpc-* port-naming convention that opts into the mesh's L7 balancing. It is yours because you have the E10 experiment, the real template snippet, and the checkpoint Q3 debugging walk to show, not retell.

2. "My ConfigMap was right and my service was still broken for two hours." The claim: kubectl apply on a referenced ConfigMap changes nothing inside a running pod, because env vars snapshot at container start. It is yours because the diagnosis ritual is concrete (exec -- env versus get cm -o yaml) and the incident class has real receipts from your own fleet, told without naming anyone.

Phase 1 of 7 — next: Phase 2 — Scaling & Resources (requests vs limits, QoS classes, OOMKill autopsy, HPA + KEDA, PDB).