## 1 Why you are here: the five primitives that own your 3am pages

Everything you will ever debug in Kubernetes — the CrashLoopBackOff at 3am, the deploy that silently dropped 2% of requests, the service that "works on one pod but not the other" — traces back to five primitives: Pods, Deployments, Services, ConfigMaps/Secrets, and the network layer underneath them. Phase 0 gave you the control-loop mental model: desired state in etcd, controllers reconciling reality toward it. Phase 1 is where that model grows hands.

Here is the deal this course makes with you. By the end of this phase you will open your platform's chart repo, read what default-service-template renders for a real service in prod, and explain every line of the resulting Deployment. Probes, strategy, resources, service ports, the works. Not "roughly what it does." Every line. That is the bar, because every service you own lives inside exactly this machinery, across 8 EKS clusters and two AWS accounts.

Skip this phase and production does three specific things to you:

- You set a liveness probe that checks the database. The first RDS blip restarts every pod in the fleet at the same time.

- You trust kubectl apply on a ConfigMap and wonder why the running pods still hold the old value three days later. There is a real incident for this on your platform, April 2025, a document-storage service. Section 1.5 covers it.

- You put a gRPC service behind a normal ClusterIP and watch 100% of traffic pin itself to one pod out of ten.

Time: 2–3 weeks. The exercises are not optional. You need a laptop with Docker, kind, and kubectl. One naming note before you start: the original material names the company this course was written against. This page strips that name out. Wherever it says "the platform" or "your chart repo", it means the codebase you actually work in.

## What this phase covers, in the order real incidents hit

    1.1Pods — the atom: why pods, not containers; pod IPs
    1.2Deployments — ReplicaSets, self-healing, rolling updates
    1.3Probes — liveness vs readiness, the exec-probe pattern
    1.4Services & traffic — ClusterIP, DNS, the gRPC LB problem
    1.5ConfigMaps/Secrets — discovery configs, Vault, staleness
    1.6Storage — PV/PVC/EBS-CSI, why the platform is stateless

  1.7
  AWS VPC CNI — where pod IPs really come from on EKS (the layer under everything)

The seven sections. 1.7 is the floor everything else stands on, which is why the platform's full cluster map moves there.

## Lab setup: do this now, everything below assumes it

- Install the tools, then create a 3-node cluster. kind is Kubernetes-in-Docker: the whole cluster runs as Docker containers on your laptop, which means nothing you break here costs anything. Named study, created from a checked-in config.
brew install kind kubectl
cd ~/Desktop/code/verly/study-material/kubernetes/code
kind create cluster --name study --config kind-cluster.yaml
kubectl get nodes        # → 1 control-plane + 2 workers, STATUS Ready

The cluster takes about 90 seconds to come up.

- Build the exercise image and side-load it into kind. kind has no image registry, so a plain docker build is not visible to the cluster. kind load docker-image pushes the image from your Docker daemon into the node containers directly.
docker build -t hello-server:v1 -f phase01_core_concepts/hello-server/Dockerfile .
kind load docker-image hello-server:v1 --name study

Why kind and not a real EKS cluster. Every exercise in this phase destroys things — pods, endpoints, rollouts. On kind that is free and instant. The one idea you cannot rehearse locally is the VPC CNI (section 1.7); there you will read the mechanism and check it against the real clusters instead.

The sentence to remember: every Kubernetes production failure you will ever page on is one of five primitives misbehaving, and this phase makes you able to name which one from the symptoms.

The trap to avoid: thinking Phase 0's control-loop model is enough. The model tells you why the system wants the desired state; Phase 1 teaches you the exact machinery that gets in the way of it reaching there.

Do right now: run the two lab-setup steps above. If kubectl get nodes shows three nodes Ready, you are done with this section and the rest of the phase is hands-on.

## 1.1 What actually owns a pod's IP? (the atom you never deploy directly)

Every abstraction above the pod — Deployment, ReplicaSet, Job, HPA — exists only to manufacture and manage pods. When something breaks, kubectl describe pod is where you end up. If your mental model of a pod is "it's a container", half of what you see in that output will not make sense.

### Pass 1: the mental model

A pod is a group of containers that share one network namespace and can share volumes. One IP, one localhost, scheduled as a unit onto one node. Most pods have exactly one app container, but the group is the primitive — Kubernetes never schedules a container alone.

  Node ip-10-81-x-x (EKS worker)

  Pod im-service-7d9f8b-x2k4j — IP: 10.81.42.17

  pause
  holds the netns
  alive

  im-service
  your Go binary,
  port 80 (gRPC)

  no sidecar here:
  ztunnel intercepts
  at node level

-
  shared: one network namespace (one IP), IPC, optional volumes — localhost connects them all

One pod on one node. In sidecar meshes a proxy would sit inside this pod; in Istio ambient mode it does not. Adapted from the original's node diagram.

### Pass 2: the details that matter

The pause container is the answer to a trivia question that is not trivia. Containers come and go — they crash, they restart, their image gets upgraded — but the pod's IP must stay stable for the pod's lifetime. So the kubelet starts a do-nothing "pause" container first. It owns the network namespace, and your app containers join it. When your Go process crashes and comes back, the IP survives because pause never died. Run docker ps on any node and you will see one pause per pod.

Every pod gets a real, routable IP. This is the part that surprises people coming from Docker's port-mapping world. There is no NAT between pods: pod A at 10.81.42.17 dials pod B at 10.81.43.9 directly, across nodes. On EKS this is literally true at the VPC level — pod IPs are VPC IPs. Section 1.7 shows where they come from. Three consequences you will use constantly:

- kubectl get pod -o wide shows an IP you can curl from any other pod. That is your first debugging move.

- Port conflicts do not exist between pods. Every pod has its own :80.

- When a pod dies, its IP is gone forever. Nothing should ever hold a pod IP. That is what Services are for, in 1.4.

Why put multiple containers in one pod at all? The sidecar pattern: a log shipper reading a shared volume, a proxy intercepting localhost traffic. Here is your platform's nuance, from the original's notes on its codebase. The old service-mesh world, Linkerd, ran a per-pod sidecar proxy. You will still see linkerd.inject: disabled in values-prod-us.yaml files — dead config from that era. The current Istio ambient mode deliberately does NOT use sidecars: the proxy, ztunnel, runs per node, so your pods stay single-container. Fewer containers per pod means less memory overhead per replica, times roughly 1400 services. That is real money.

### Pass 3: the gotcha

A bare pod, like manifests/01-pod.yaml, has no supervisor. Delete it, or drain the node it sits on, and it is simply gone. Nothing recreates it. The kubelet restarts containers inside a pod — that is what restartPolicy: Always means — but nothing resurrects the pod object itself. This is why "we deploy pods" is technically false everywhere. You deploy Deployments, which is 1.2.

The sentence to remember: a pod is the unit of scheduling and the unit of IP identity — containers share it, controllers manage it, and nothing about it is durable.

The trap: treating pod names or pod IPs as stable identifiers in config, dashboards, or code. Both change on every reschedule. Anything that must find a pod goes through a Service or DNS.

Try this now: watch nothing bring the pod back.

kubectl apply -f phase01_core_concepts/manifests/01-pod.yaml
kubectl get pod hello-pod -o wide          # note the IP and node
kubectl delete pod hello-pod && kubectl get pods   # gone. nothing brings it back.

Verify: the first -o wide shows a real IP on one of your kind nodes; after the delete, kubectl get pods returns nothing. The second pass of the try-block — a Deployment that re-creates it automatically — comes in the next section.

## 1.2 How does a rollout heal and never dip below capacity? (Deployments & ReplicaSets)

The Deployment is the object you will helm upgrade hundreds of times. Understanding the Deployment → ReplicaSet → Pod chain is what lets you look at a half-finished rollout and know, in one glance, whether it is progressing or wedged.

### Pass 1: the mental model

You declare "3 replicas of image v2." The Deployment controller creates a ReplicaSet, which is a pod template plus a count. The ReplicaSet controller creates pods. The kubelet runs them. Kill a pod and the ReplicaSet notices actual(2) != desired(3) and makes another. That is the whole self-healing story: a level-triggered reconcile loop, nothing smarter.

Deployment "im-service"            (owns rollout strategy + history)
    │
    ├── ReplicaSet im-service-7d9f8b   (pod-template hash 7d9f8b, replicas: 2)  ◄ current
    │       ├── Pod im-service-7d9f8b-x2k4j
    │       └── Pod im-service-7d9f8b-m8t1q
    │
    └── ReplicaSet im-service-5c4a2e   (previous version, replicas: 0)          ◄ kept for rollback

Two things to read in that tree. The suffix on the ReplicaSet name, like 7d9f8b, is a hash of the pod-template content — change the template, get a new hash, get a new ReplicaSet. And the old ReplicaSet sitting at 0 replicas is not garbage: it is the rollback mechanism. kubectl rollout undo scales the old RS back up and the new one down.

### Pass 2: the rolling update, with your platform's exact numbers

The org-wide default lives in default-service-template/values.yaml:193-197 and is rendered by the deploymentStrategy helper in _helpers.tpl:288-296. In the chart repo on your machine those files may be named slightly differently; the settings are what matter:

strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: "50%"          # may run up to 150% of desired during rollout
    maxUnavailable: "0%"     # may NEVER dip below 100% of desired

Internalize what that pair means: capacity never decreases during a deploy. New pods must come up and pass readiness before old ones are killed. Walk the timeline for a 2-replica service (the prod shape of im-service) — step through it:

  Rolling update with replicas=2, maxSurge=50% (1 extra pod allowed), maxUnavailable=0%.
  ▢ solid = ready · ▢ dashed = starting, not ready yet.
  The 60-second step cadence is a readiness delay (initialDelaySeconds: 60), not a liveness one.
  ◄ step back
  step forward ►

Read what the timing tells you. initialDelaySeconds: 60 on the readiness probe means every rollout step waits at least 60 seconds. A 10-replica service deploys in roughly 5–10 minutes. That is not "slow CI" — that is your probe config doing exactly what it was told. Contrast with maxUnavailable: 25%, which some older values files in the chart repo still use: it tears down old pods before replacements are ready. Fine for async workers, unacceptable on request-serving paths. Check what your service actually renders.

What the upstream defaults are (verified: kubernetes v1.34.0 source, pkg/apis/apps/v1/defaults.go). If you never set the strategy, Kubernetes defaults to maxSurge: 25% and maxUnavailable: 25% — capacity may dip a quarter below desired mid-rollout. The platform's 50%/0% override is a deliberate trade: it pays surge capacity to buy a no-dip guarantee. Two more defaults from the same file worth knowing: progressDeadlineSeconds: 600 and revisionHistoryLimit: 10. The second one caps how far back rollout undo can reach — past ten revisions, the old ReplicaSets are pruned and the history is gone.
Source: raw.githubusercontent.com/kubernetes/kubernetes/v1.34.0/pkg/apis/apps/v1/defaults.go

Real prod numbers to calibrate against, from the platform's internal Compass dashboard, cross-checked against the chart repo:

Service (prod)replicasHPA min→maxHPA target

im-service22 → 1070% cpu/mem

content-center-service22 → 480% cpu/mem

im-service (staging)33 → 480%

Base replicas of 2 is not stinginess. It is the floor for surviving one node failure, with the HPA doing the real scaling work — the HPA's algorithm is Phase 2's territory, here you only need the floor.

### Pass 3: the gotchas

- The selector is immutable and is the contract. spec.selector.matchLabels must match spec.template.metadata.labels, and you cannot change it after creation. If two Deployments' selectors overlap, their ReplicaSets fight over the same pods — a genuinely miserable failure mode.

- A rollout can wedge silently. If the new pods never pass readiness — bad config, a missing ConfigMap key — you get old pods serving, new pods crash-looping, and a rollout that waits forever. kubectl rollout status deploy/<name> is the check. progressDeadlineSeconds (600 by default) marks it failed after ten minutes, but it does NOT auto-rollback.

- Not every "worker" is a K8s workload. kind: Deployment is the rule on the platform; StatefulSets exist only for genuinely stateful infra like InfluxDB2 and the Neo4j-backed docgen service. And one correction from the original worth keeping: a service called missions-processors is not a Kubernetes workload at all — its manifest declares "type": "AwsLambda". The Go consumers run as Lambdas fed by MSK EventSourceMappings. When you want the canonical K8s Go service to learn from, look at im-service, not missions-processors.

The sentence to remember: a Deployment is versioned desired state; ReplicaSets are the versions; a rolling update is scale the new RS up and the old RS down, under maxSurge/maxUnavailable constraints.

The trap: assuming a merged MR equals deployed code. With maxUnavailable: 0%, a readiness-failing v2 means v1 keeps serving indefinitely while the rollout silently waits. Run kubectl rollout status before you declare victory.

Try this now: watch the three layers respond, then break one:

kubectl apply -f phase01_core_concepts/manifests/02-deployment.yaml
kubectl get deploy,rs,pods -l app=hello     # see all three layers
kubectl delete pod -l app=hello --wait=false && kubectl get pods -w   # self-healing, live

Verify: the deleted pod disappears and a new one with a fresh name appears in the -w stream within seconds — the ReplicaSet noticed actual != desired and reconciled. Then read the RS names: the Deployment's pod-template hash is in each one.

## 1.3 Which probe kills your pod, and which one takes its traffic? (Probes)

Probes are where a config mistake turns a partial failure into a total one. Colin Breck's line — misconfigured probes cause more Kubernetes outages than the bugs they catch — matches platform reality. The probe defaults in the chart repo encode several hard-won lessons, and you should know which numbers are load-bearing.

### Pass 1: the two questions

The kubelet asks your container two different questions. Confusing them is the classic mistake:

LIVENESSREADINESS

Question"Are you fundamentally broken (deadlocked)?""Can you take traffic RIGHT NOW?"

On failureRESTART the containerRemove pod from Service endpoints. No restart.

May check deps (DB, Redis)?NEVER — DB down → restart loop fixes nothingYes — DB conn, warmup, cache primed

Recovers byProcess restartPassing again → back in

### Pass 2: how the fleet actually does it

Two patterns exist, selected by healthchecktype in the values file. The shared chart supports only http and exec — there is no K8s-native gRPC probe templated in default-service-template, and no startupProbe template at all.

Pattern A — HTTP services: healthchecktype: http. For example, ui-shell probing GET /status on port 80, or Go HTTP services probing /health/live + /health/ready on 8000.

Pattern B — Go gRPC services (yours): healthchecktype: exec. The image ships a tiny gRPC client binary, and the probe shells into the container and runs it. The real production probe command is exactly this:

# healthCheck.sh — this IS the production probe command
cd /app/healthCheck
./healthCheck

// healthCheck/healthCheck.go (abridged, the real code)
conn, err := grpc.Dial(fmt.Sprintf(":%d", ServicePort), ...)   // ServicePort = 80
c := healthCheckService.NewHealthCheckClient(conn)
response, err := c.HealthCheck(ctx, &common.EmptyMsg{}, ...)
if response.Healthy != true {
    panic(nil)    // non-zero exit → kubelet counts a probe failure
}

The original said "the kubelet doesn't know or care about gRPC." That is a chart fact, not a platform fact. Verified against the Kubernetes probe docs: the kubelet supports native gRPC health-check probes, stable since v1.27 (beta in v1.24). A native probe points at the pod's IP or hostname, speaks the standard gRPC health protocol, and does not need any binary in the image. What is true is that your chart predates them and does not template them, which is why the fleet ships an exec binary instead. Same split for startup probes: they are GA since v1.20 and exist precisely to replace the initialDelaySeconds hack below — the chart just has no template for one. Defend "Kubernetes can't probe gRPC" in a review and you will lose. Two caveats on the native gRPC probe, also verified: it does not support named ports, and TLS on it is still alpha. Native h2c (plain HTTP/2) HTTP probes are alpha too, in the v1.37 docs — not something you can turn on today.
Source: kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes (fetched 2026-09-17)

How the mechanism sees it: the kubelet sees an exec command and an exit code. 0 means pass, anything else means fail. It is the binary, not the kubelet, that speaks gRPC. The values-file shape below is what the real services render:

livenessProbe:
  healthchecktype: exec
  exec:
    command: [sh, /healthCheck.sh]
  initialDelaySeconds: 60      # some JVM-ish services use 120
  periodSeconds: 10
  timeoutSeconds: 10
  successThreshold: 1
  failureThreshold: 3

Do the failure math, because you will need it during an incident. A pod goes bad; worst-case detection is periodSeconds × failureThreshold = 30s of failed probes, plus up to timeoutSeconds on the last attempt still running. The upstream default for timeoutSeconds is 1; the chart here sets 10, and a hung exec does not count as a failure at all until it returns or times out — so with this block you can sit inside a 10-second timeout plus 30 seconds of repeats. For a readiness probe that is up to ~30–40s of a dead pod still receiving traffic. That window is why clients need retries, and why Istio's outlier detection exists (Phase 5).

Worst-case detection window = periodSeconds × failureThreshold, plus one timeoutSeconds on the
in-flight attempt. Move the chart's real knobs and watch the window move.
periodSeconds
failureThreshold
timeoutSeconds

And the initialDelaySeconds: 60 you keep seeing in values files? That is the poor man's startupProbe. Because the chart does not template a startupProbe, slow-booting services push the first check out 60–120 seconds. The cost: every rollout step waits that long even if the pod was ready in 5 seconds — you watched that in the 1.2 timeline — and a pod that boots broken serves nothing for 60s before anyone notices. The platform-native fix is a real startupProbe: failureThreshold × periodSeconds becomes the startup budget, and liveness takes over immediately after.

### Pass 3: the cascading-failure trap, step by step

This is the scenario Colin Breck's post is famous for. Internalize it with your own stack: the liveness probe checks Redis connectivity, and Redis blips for 40 seconds.

- t=0 Redis becomes unavailable.

- t=0–30 ALL pods fail liveness three times over (10s period × 3 failures).

- t=30 The kubelet restarts ALL pods simultaneously.

- t=30–90 The whole fleet is booting (initialDelaySeconds: 60). Serving capacity is ZERO.

- t=40 Redis is back. Nobody is up to notice.

- t=90 Pods boot with cold caches into a full retry storm. CPU spikes, probes time out, and SOME PODS RESTART AGAIN.

Wrong: liveness probe checks a dependency. A 40-second Redis blip became a 10-minute total outage, because a dependency failure triggered pod restarts across the entire fleet at once.

Right: liveness is a process-only check; readiness is the probe that may look at dependencies. Redis blip → pods leave the Service's endpoints, come back when Redis does. No restarts, no bootstorm, no cold-cache stampede.

The sentence to remember: liveness restarts, readiness removes — and only readiness may look at dependencies.

The trap: copying a liveness block into a readiness block. It is fine only because the current health endpoint checks nothing external. The moment your HealthCheck RPC starts pinging MySQL, that copy-paste becomes the cascade above.

Three things to internalize: (1) liveness restart vs readiness removal; (2) the detection window is period × failureThreshold plus a timeout, and a hung exec hides inside it; (3) initialDelaySeconds: 60 is a missing startupProbe, not a safety margin.

Try this now — watch readiness pull a pod out of rotation WITHOUT restarting it:

kubectl apply -f phase01_core_concepts/manifests/02-deployment.yaml
kubectl get endpoints hello -w &        # leave watching
POD=$(kubectl get pod -l app=hello -o name | head -1)
kubectl exec ${POD#pod/} -- wget -qO- localhost:8080/toggle-ready
# endpoints list drops from 3 IPs to 2. RESTARTS column: unchanged.

Verify: the endpoints watch shows the IP leave the list, and kubectl get pods shows the pod still Running with an unchanged RESTARTS count. Readiness un-registered it; nothing killed it. Toggle again and the IP returns.

## 1.4 Why does gRPC pin all traffic to one pod? (Services, DNS, and the mesh)

Pods are mortal, and their IPs die with them. The Service is the stable name in front of that churn. And for you specifically, as someone who ships gRPC services, this section explains why the platform needed a service mesh at all.

### Pass 1: the mental model

A Service is a stable virtual IP (a ClusterIP) plus a live list of ready pod IPs, selected by label. kube-proxy programs every node's iptables so connections to the VIP get DNAT'd to one ready pod IP. The ready-pod list is served today by EndpointSlices — the object kube-proxy actually reads.

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

Two facts hiding in that diagram do real work. Readiness controls Service membership — that is the machinery behind 1.3: a not-ready pod is not DNAT'd to. And the choice is made per-CONNECTION, not per-request. File that away; it detonates two paragraphs from now.

The old mental model says "the endpoints controller"; the object has changed. Verified against the EndpointSlice docs: EndpointSlice is the source of truth for kube-proxy (stable since v1.21, up to 100 endpoints per slice, capped at 1000 by --max-endpoints-per-slice), and the classic Endpoints API is deprecated — its mirroring controller was deprecated in v1.33. Your muscle-memory command still works: kubectl get endpoints aggregates the slices for display. One caution flagged by hunter but not source-checked this run: operators report the command truncates with a ! when a service has over 1000 entries — read endpointslice objects directly for very large services.
Source: kubernetes.io/docs/concepts/services-networking/endpoint-slices/ (fetched 2026-09-17)

DNS names you will type daily: <service>.<namespace>.svc.cluster.local, short form <service> within one namespace. On the platform, service-to-service addresses are injected as env vars from generated *-discovery-config ConfigMaps (the recipe for those is 1.5): same-track callers get the short DNS name, cross-track callers get the full form. Plain Kubernetes DNS — no Consul, no custom Route53 for east-west traffic.

### Pass 2: the gRPC problem

Here is where your stack bites the platform. gRPC runs on HTTP/2, and HTTP/2 opens one long-lived TCP connection and multiplexes every request onto it. Now replay the per-connection fact:

Wrong mental model (what everyone assumes): req1 → pod1, req2 → pod2, req3 → pod3. Per-request balancing, spread evenly, forever.

Reality with ClusterIP + gRPC: ONE connection, chosen ONCE at dial time. Every request rides it to pod 1. Pod 2 and pod 3 sit idle. 10 replicas, 1 doing all the work — and when the HPA scales up, the new pods get ZERO traffic. Forever.

The kube-proxy DNAT happened exactly once, at TCP connect. Every gRPC call after that rides the connection. Scale from 2 pods to 10 under load and the 8 new pods idle while the original 2 melt. This is the single most-linked Kubernetes blog post for a reason: "gRPC Load Balancing on Kubernetes without Tears".

The three industry-standard fixes:

FixHowTrade-off

Headless Service + client round_robinclusterIP: None → DNS returns ALL pod IPs; grpc-go balances per callClient must re-resolve; every client language reimplements it

L7 proxy (Envoy/nginx)Proxy in the path balances per requestExtra hop, extra ops burden

Service meshMesh data plane does L7 LB transparentlyPlatform complexity — made someone else's problem

The platform picked the mesh: Istio in ambient mode. Verified in the charts, per the original's read of its repo: application gRPC services are plain ClusterIP (headless services exist only for stateful infra peer discovery — RabbitMQ, Loki, ClickHouse, Hazelcast); the shared Go gRPC client utilities carry no round_robin resolver config — grpc.Dial targets a single host:port; and default-service-template/templates/service.yaml does the wiring. This is the real template logic:

{{- range .Values.ports }}
  {{- if (hasPrefix "grpc" .name) }}
    istio.io/use-waypoint: waypoint      # ← gRPC-named ports get routed
  {{- end }}                             #   through an Istio waypoint proxy
{{- end }}

That is why the port-naming convention in every values file (http-0, grpc-1) is load-bearing. Naming a port grpc-* is what opts it into L7 per-request load balancing through the ambient waypoint proxy. Name your gRPC port tcp-1 and you are back to the broken diagram above. DestinationRules add per-service policy on top — a real example: hub-analytics-engine uses consistentHash on a company_id header for sticky-by-tenant routing.

Ambient mode is not experimental. Verified: Istio ambient mode reached GA with Istio 1.24, in November 2024 — ztunnel, waypoints, and their APIs are stable. When the original notes say the platform picked Istio in ambient mode, date-stamp it: this is a GA data plane roughly two years old, not a beta you should treat as temporary.
Source: istio.io/latest/blog/2024/ambient-reaches-ga/

Click to send 10 gRPC requests. The per-pod counters accumulate so you can see what a burst of 30 looks like in each mode.
ClusterIP only
grpc-* port → waypoint
reset
▮ bar = requests served by that pod

### Pass 3: north-south — how external traffic gets in

The external path today: nginx-ingress is the dominant controller, rendered by default-service-template/templates/ingress.yaml. Services declare ingressClass: nginx with internal hostnames, and the *.internal-grpc.* hostnames are ingress-routed h2c (cleartext HTTP/2) into the same ClusterIP services, with TLS terminating at the ingress LB. The ALB ingress class appears only for infra and ops tooling. And the aggregation gateway in the coaching domain is just another nginx-fronted service, not a product like Kong or AWS API Gateway — the original names a gateway repo; the mechanism is what matters: it is an app, fronted by nginx, like everything else.

The original said "nginx-ingress hits EOL March 2026 — expect the layer to change." That cliff has already passed. Verified from the 2025-11-11 retirement announcement: best-effort maintenance continued until March 2026, and after that, quoted directly, "there will be no further releases, no bugfixes, and no updates to resolve any security vulnerabilities. Existing deployments will continue to function." As of today, ingress-nginx — the dominant ingress path on the platform — is fully unmaintained: it works, but nothing discovered tomorrow gets patched. The cause named in the post is worth remembering: snippet annotations were called "yesterday's flexibility… today's insurmountable technical debt", with only 1–2 maintainers working after hours. The announced migration pointer is the Gateway API; the platform's in-flight migration to Higress, a Gateway-API-compatible controller, just moved from "coming" to "overdue". A Steering/SRC reaffirmation dated 2026-01-29 exists but hunter did not open the body — treat it as reported, not verified.
Source: kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/

The sentence to remember: a Service load-balances connections; gRPC reuses one connection — so gRPC needs L7 balancing, which on the platform is Istio ambient's waypoint, opted into by naming the port grpc-*.

The trap: renaming or mis-naming Service ports. grpc-1 → internal-1 is a one-line diff that silently turns per-request L7 load balancing into single-pod pinning. Reviewers rarely catch it. Now you will.

Try this now: make the difference visible in DNS:

kubectl apply -f phase01_core_concepts/manifests/03-service.yaml
kubectl run -it --rm dbg --image=busybox:1.36 -- sh
  nslookup hello              # → ONE ClusterIP
  nslookup hello-headless     # → THREE pod IPs (headless = no VIP)
  for i in 1 2 3 4 5; do wget -qO- hello/ | grep hostname; done   # hostname varies

Verify: the plain Service resolves to one ClusterIP while the headless one resolves straight to three pod IPs — that contrast is exactly the headless+client-side-balancing row of the fixes table. The varying hostnames in the loop show plain HTTP spreading across pods across connections; remember HTTP/1.1 re-opens connections, which is why HTTP looks balanced in a way gRPC never is.

## 1.5 When does a changed value reach a running pod? (ConfigMaps, Secrets, and the staleness trap)

On the platform, config is not a sidebar — the entire service-discovery mechanism is built out of ConfigMaps. Understanding exactly when a changed value does or does not reach a running service separates "I redeployed and prayed" from "I know why the pod has a stale value." This section has real incident numbers attached to it.

### Pass 1: two consumption modes, two very different behaviors

┌─ ConfigMap "hello-config" ──────────────┐
│  GREETING: "namaste"                    │
│  app.properties: |                      │
│    llm.timeout.seconds=25               │
└───────────┬─────────────────┬───────────┘
            │                 │
   as ENV VAR                as MOUNTED FILE
            │                 │
   snapshot at container      kubelet syncs changes into the
   START. Edit the CM →       mounted file. Edit the CM →
   running pod KEEPS the      file updates in place —
   old value until restart.   IF the app re-reads it (most don't).

Press the buttons below and watch the two modes diverge — this is the whole trap in one picture:

kubectl patch cm hello-config → GREETING: changed!
let the kubelet sync pass
restart the pod
reset

### Pass 2: the platform's pattern, end to end

Open a real service's values-prod-us.yaml in the chart repo and you see the whole architecture in one file. Three kinds of entries under project.env:

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

The *-discovery-config ConfigMaps are generated at deploy time from CloudFormation stack outputs: RDS endpoints, ElastiCache hosts, SQS URLs, other services' addresses. Your service declares which discovery configs it needs (a real service lists about 16 of them), and Helm renders everything into literal env: entries in the pod spec.

That rendering detail is the crux of change propagation. There is no checksum annotation, no Reloader, no rollout restart in the CI deployer — the original has Compass, the platform's inventory tool, read the full 661-line deployment.yaml template to confirm. The mechanism is simpler. CI always runs helm upgrade --install. If you changed your own values file, the rendered pod template changes, the template hash changes, and a normal rolling update follows. Config change = deploy. Clean.

### Pass 3: where that model breaks, with real incident receipts

The gap: entries of type 2 — configMapKeyRef into someone else's discovery ConfigMap. If that referenced ConfigMap's content changes, your pod spec did not change: the pod spec only names the reference. No hash change → no rollout → your running pods keep the value they read at boot, silently, indefinitely. Not hypothetical. Compass surfaced four real hits:

- doc-store, 11 Apr 2025 (integration): the one from Phase 0's checkpoint. A DB node was evicted; the discovery ConfigMap held the old primary IP; doc-store kept dialing the dead instance until someone restarted it manually.

- ruleautomaton, 16 Apr 2025: dependent services failed when discovery ConfigMaps were unavailable during a track blackout.

- ICP-1672 (Mar 2025): an env var wired to the wrong ConfigMap key sent auth callbacks to an external integration service instead of the prod-us public host.

- STOR-6202 (Jun 2025, open): prod-eu RDS discovery ConfigMaps contain unresolved {{resolve:secretsmanager:rds/…}} placeholder strings — services reading MasterUsername get a literal template string as a password.

So build this instinct: when a service misbehaves after infra changed underneath it, your first question is "when did these pods last restart, and what did the discovery ConfigMap say at that moment?" Compare kubectl get cm <dep>-discovery-config -o yaml against kubectl exec <pod> -- env | grep <KEY> — never the ConfigMap against git.

On the "~60s" sync you will see quoted everywhere, including in the original. Verified against the current ConfigMap docs: total propagation delay is the kubelet sync period (default 60s) plus the cache propagation delay, and the kubelet's default change-detection strategy is watch — on a modern cluster the file usually updates in seconds, so treat 60s as a ceiling, not the expected wait. Two hard rules the docs carry and the original omits: a ConfigMap mounted with subPath never receives updates at all, and ConfigMap data is capped at 1 MiB — worth knowing before anyone parks a large prompt file in one. The platform-native way to close the whole staleness class is immutable: true ConfigMaps (GA since v1.21): a config change forces a new ConfigMap name, which forces a pod-template change, which forces a rollout. The checksum-annotation widget or the Reloader controller achieves the same by convention.
Source: kubernetes.io/docs/concepts/configuration/configmap/ (fetched 2026-09-17)

### Secrets: what is real and what is theater

A K8s Secret is base64-encoded, not encrypted. Anyone with get secret RBAC in the namespace reads everything: kubectl get secret X -o jsonpath='{.data.KEY}' | base64 -d. The platform's live mechanisms, in order of use:

- Vault via Agent Injector (primary). Template helpers map your team's 3-letter code to a namespaced AppRole and emit vault.hashicorp.com/agent-inject pod annotations; secrets are pulled at pod startup. Declared in values as the vault: block above. A secondary vaultConfig.injectionMode: helm mode renders a plain Secret at deploy time instead.

- AWS Secrets Manager + the CSI driver, specifically for IAM access keys; used by the analytics and livekit workloads.

- Legacy ownSecret plain K8s Secrets — still visible in a few old charts; discouraged.

- External Secrets Operator / Sealed Secrets: not used. Anything you read about them online does not apply here.

One uncomfortable observation to carry as a lesson: several prod values files contain third-party API tokens as plaintext literal env values committed to git. Pattern 1 — the custom: literal — exists for harmless values precisely so that tokens never grow there.

The sentence to remember: config changes deploy pods (helm → new template hash → rollout) — except referenced discovery ConfigMaps, which change underneath running pods and reach nothing until something restarts.

The trap: debugging "config not applied" by re-checking the ConfigMap object. The object is fine; the pod's env snapshot is stale. Compare kubectl exec <pod> -- env against the ConfigMap, not the ConfigMap against git.

Try this now: reproduce the staleness in your kind cluster:

kubectl apply -f phase01_core_concepts/manifests/04-configmap.yaml
kubectl exec deploy/hello-configured -- env | grep GREETING     # namaste...
kubectl patch cm hello-config -p '{"data":{"GREETING":"changed!"}}'
kubectl exec deploy/hello-configured -- env | grep GREETING     # STILL namaste
kubectl exec deploy/hello-configured -- cat /etc/config/app.properties
# wait ~60s, cat again — the FILE updated. The env var never will.

Verify: the second env print still reads namaste after the patch, and the cat of the mounted file flips to the new value within the kubelet's sync window (usually seconds on a modern cluster; up to ~60s is the ceiling). One line changes and one does not — that asymmetry is the section.

## 1.6 Why is the best PVC the one you never create? (Storage: PV, PVC)

This section matters mostly so you know what NOT to reach for. The real content is an architecture decision you should be able to defend in a design review: why a platform of roughly 1400 services runs almost no persistent volumes.

### Pass 1: the chain, request to result

A PersistentVolumeClaim is a request: "1Gi, ReadWriteOnce". A StorageClass is the how: provisioner plus parameters. A PersistentVolume is the fulfilled result: an actual EBS volume. Pods mount claims, never volumes directly — the claim abstracts where storage comes from:

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

The platform specifics, from the original's verified read of the charts: all current PVCs use the modern EBS CSI driver (ebs.csi.aws.com) through the org-standard ebs-sc StorageClass — gp3, expandable, installed as an EKS addon via Terraform. The legacy in-tree kubernetes.io/aws-ebs provisioner appears only in old migration artifacts. No EFS anywhere — block storage only, no shared-filesystem pattern.

### Pass 2: the decision that shapes everything

Of ~1400+ charts, the services carrying PVCs are a short, countable list: Loki, the PMM/Percona monitoring stack, RabbitMQ-HA (with persistence off by default), Cubestore, and one embedded Neo4j. Every product service — including everything you own — is stateless by design. State lives in RDS/Aurora, ElastiCache Redis, S3, DynamoDB, MSK, Couchbase, OpenSearch. All outside the cluster.

Why is that the right call? The RWO trap makes the argument. An EBS volume attaches to one node in one AZ. Give a pod a PVC and suddenly:

- It can only reschedule onto nodes in that AZ.

- Volume detach/attach adds 30–120s to every reschedule — a standard EBS ballpark, flagged by hunter as commonly accepted but not source-checked this run.

- maxSurge-style rollouts fight over the single attachment.

- Node drains get blocked waiting on the volume.

Stateless pods have none of these constraints. Kill them, move them, scale them, surge them 50% — freely. Statelessness is what makes everything in sections 1.2–1.4 cheap. The rolling update that never dips capacity only works because the new pod has no attachment to wait on. The day you are tempted to write files to a pod volume, the answer is almost always S3.

The sentence to remember: PVC = request, StorageClass = how, PV = result — and on this platform the best PVC is the one you didn't create.

The trap: emptyDir feels like free local storage, but it dies with the pod and — worse — counts against the node's ephemeral storage. Fill it and the node evicts pods, yours and other people's. Scratch space beyond a few hundred MB goes to S3, or gets an explicit ephemeral-storage request (Phase 2 territory).

Three things to internalize: (1) the request/how/result chain; (2) RWO means one node in one AZ, with an attach-time tax on every move; (3) state outside the cluster is a choice paid for once, in convenience, instead of a tax paid on every reschedule.

Try this now — prove a volume outlives its pod, so you can feel both sides of the trade:

kubectl apply -f phase01_core_concepts/manifests/06-pvc.yaml
kubectl get pvc data-claim                      # Bound (kind's local-path SC)
kubectl delete pod hello-stateful && kubectl apply -f phase01_core_concepts/manifests/06-pvc.yaml
kubectl logs hello-stateful                     # TWO "born" lines — data survived the pod

Verify: after the delete and re-apply, the logs show two birth lines — the first container wrote, the second container read it back. That persistence is exactly what you are agreeing to manage, with a volume, on the platform's stateless-by-default fleet. Hold the feeling next to the RWO tax above and the "almost always S3" answer writes itself.

## 1.7 Where do pod IPs actually come from on EKS? (AWS VPC CNI)

On EKS, "the network" is not an abstraction. Every pod IP is a real VPC IP, allocated from your subnets, through an elastic network interface (ENI) attached to the node. The failure this creates — IP exhaustion — is famous for looking exactly like a scheduling bug. Knowing its shape will save you an afternoon someday.

### Pass 1: the mental model

The AWS VPC CNI plugin runs as the aws-node DaemonSet on every node. It attaches ENIs to the instance and hands their secondary IPs to pods. Pod IPs are therefore first-class VPC citizens, routable from anywhere in the VPC with no overlay or encapsulation. That is why 1.1's "no NAT between pods" is literally true on this platform.

┌─ EC2 node (e.g. m5.xlarge) ───────────────────────────────────────┐
│                                                                   │
│  ENI-0 (primary)          ENI-1                 ENI-2             │
│  ├ node IP 10.81.40.5     ├ 10.81.42.17 → pod   ├ 10.81.44.3 → pod│
│  ├ 10.81.41.2  → pod      ├ 10.81.42.18 → pod   ├ ...             │
│  ├ 10.81.41.3  → pod      ├ ...                 │                 │
│  └ (14 secondary IPs)     └ (15 IPs)            └ (15 IPs)        │
│                                                                   │
│  m5.xlarge: max 4 ENIs × 15 IPs per ENI                          │
│  → 4 × (15 − 1) + 2 = 58 assignable pod IPs                      │
│  → default max-pods for this instance type = 58                   │
└───────────────────────────────────────────────────────────────────┘

Why 58 and not 60: each ENI keeps its first IP for the node itself, and the formula AWS ships reserves two more. The exact file is the CNI's own eni-max-pods.txt, where the formula is ENIs × (IPv4 addresses per ENI − 1) + 2.

Pick an instance type. All numbers verified against the CNI's eni-max-pods.txt at v1.20.1. Click a chip:

### Pass 2: the two ceilings

Instance type caps ENIs × IPs-per-ENI. So pod density is a function of instance size, independent of CPU and memory. A huge node with a small ENI budget strands compute: plenty of free CPU, nowhere to put a pod. And the subnet caps total IPs: every pod consumes a subnet IP, so a /24 subnet (251 usable addresses) supports roughly 250 pods across all nodes in it, minus nodes, load balancers, and warm-pool overhead.

The warm pool is the subtle multiplier. For fast pod startup, the CNI pre-allocates spare IPs per node — WARM_ENI_TARGET=1 keeps one full spare ENI's worth of IPs ready on every node. Comfort for latency, paid in subnet IPs. The tuning knobs are env vars on the aws-node DaemonSet: WARM_ENI_TARGET, WARM_IP_TARGET and MINIMUM_IP_TARGET (the distinction between those two — minimum-floor-for-new-nodes vs spare-pool-cap — is something hunter flagged as from memory, not re-verified this run), and the big one: ENABLE_PREFIX_DELEGATION, which assigns each ENI slot a /28 prefix (16 IPs) instead of single IPs. The same m5.xlarge jumps from 58 to hundreds of assignable pod IPs, and per-IP allocation pressure on the subnet drops.

What exhaustion looks like when it hits — recognize this in ten seconds instead of three hours:

- Pods stuck Pending or ContainerCreating on a node with plenty of free CPU.

- kubectl describe pod shows FailedCreatePodSandBox.

- The CNI logs show InsufficientFreeAddressesInSubnet.

- Conclusion: this is a networking quota failure cosplaying as a scheduling failure.

### Pass 3: the platform's state, honestly labeled

The original's tooling found the config split across two eras. The historical hand-authored CNI manifest sets ENABLE_PREFIX_DELEGATION=false, WARM_ENI_TARGET=1, MTU 9001. The current eksctl provisioning path installs the vpc-cni as a managed EKS addon with no configurationValues override — AWS defaults, not deliberate tuning. No ENIConfig custom networking. No in-repo IP-exhaustion postmortems, though a metrics DaemonSet ships ENI/IP metrics to CloudWatch, so detection exists. Treat "have we ever hit exhaustion, and is prefix delegation on today?" as a genuinely open question. The honest check is live:

kubectl describe ds aws-node -n kube-system | grep -E "PREFIX|WARM"

The max-pods numbers are not folklore. Every figure in the calculator above is verified against misc/eni-max-pods.txt at amazon-vpc-cni-k8s v1.20.1: m5.xlarge 58, m5.4xlarge 234, and the node-pool families you will see in Phase 2 — c5.4xlarge 234, c5a.4xlarge 234, c6g.4xlarge 234, c6g.metal 737. The in-file formula is ENI × (IPv4 per ENI − 1) + 2: the phase's own diagram agrees (14 secondary IPs on the primary ENI, 15 on the rest).
Source: raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.20.1/misc/eni-max-pods.txt

While you are at the infra layer, know the cluster map — the world your kubeconfig switches between, as recorded in the platform's track config:

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

Note the real isolation boundary: production lives in account 191195949309, staging and integration in 845925808232. Account-level blast-radius separation, not just naming. These account IDs are internal platform facts from the original's notes — they are how you recognize which side of the boundary a kubeconfig context puts you on.

The sentence to remember: on EKS, pod IPs are VPC subnet IPs served through node ENIs — so pod capacity is bounded by instance type and subnet size, not just CPU.

The trap: Pending pods plus free CPU sends everyone staring at the scheduler. Check describe pod events for FailedCreatePodSandBox first; if it is there, the problem is IPs, and no amount of resource-request tuning will fix it.

Verify your understanding: an m5.xlarge (4 ENIs × 15 IPs) with prefix delegation off runs max ~58 pods. If each pod requests 100m CPU, 58 × 100m = 5.8 cores on a 4-vCPU node — the ENI budget never bound you. But flip it: 50 tiny pods of 20m each, sidecar-less microservices on a 16-vCPU m5.4xlarge (ENI limit 234 IPs) on a subnet with 200 free addresses — the subnet is now your scheduler.

## 🧪 The lab: twelve exercises that make Phase 1 muscle memory

Work in ~/Desktop/code/verly/study-material/kubernetes/code/ with the cluster and image from the setup at the top. The exercises build on each other — do them in order. Every one of these runs against your own kind cluster, so none can be machine-checked: they are all do it, look at the output, confirm it matches. (One renaming note: two files below are named differently in your copy of the code — the original named them after the company. Here they are 07-platform-style.yaml and the label app=platform-style.)

-  E1 — Bare pod mortality observe
Run: kubectl apply -f phase01_core_concepts/manifests/01-pod.yaml && kubectl get pod hello-pod -o wide
Then: kubectl delete pod hello-pod && sleep 2 && kubectl get pods
Expected: pod gone, nothing recreated it.
Teaches: pods have no supervisor; controllers do the healing.
Verified: manual — needs your kind cluster.

-  E2 — The ownership chain observe
Run: kubectl apply -f phase01_core_concepts/manifests/02-deployment.yaml && kubectl get deploy,rs,pods -l app=hello
Then: kubectl get pod <one-pod> -o jsonpath='{.metadata.ownerReferences[0].kind}{" "}{.metadata.ownerReferences[0].name}'
Expected: ReplicaSet hello-<hash> — the pod is owned by the RS, not the Deployment.
Teaches: Deployment → ReplicaSet → Pod is a real object graph, not an abstraction.
Verified: manual.

-  E3 — Self-healing race observe
Run: kubectl get pods -l app=hello -w in one terminal; kubectl delete pod -l app=hello in another.
Expected: replacements appear within ~1s, Running in a few seconds. Note the new random suffixes.
Teaches: reconcile-loop reaction time; pod names are ephemeral.
Verified: manual.

-  E4 — Rolling update with zero downtime: prove it build
Run: while true; do wget -qO- --timeout=1 http://localhost:8080/ 2>/dev/null | grep -o '"hostname":"[^"]*"' ; sleep 0.3; done via kubectl port-forward svc/hello 8080:80 & (approximate — a request loop against the service)
Trigger: docker build -t hello-server:v2 -f phase01_core_concepts/hello-server/Dockerfile . && kind load docker-image hello-server:v2 --name study && kubectl set image deploy/hello hello-server=hello-server:v2
Watch: kubectl rollout status deploy/hello and kubectl get rs -l app=hello (two RSs, counts shifting).
Expected: request loop never errors; old RS drains to 0.
Teaches: maxSurge/maxUnavailable in motion; the RS-pair mechanism.
Verified: manual.

-  E5 — Wedge a rollout on purpose break
Run: kubectl set image deploy/hello hello-server=hello-server:does-not-exist
Watch: kubectl get pods -l app=hello → new pods ErrImagePull/ImagePullBackOff; old pods still Running and serving.
Verify: kubectl rollout status deploy/hello hangs. Recover: kubectl rollout undo deploy/hello.
Expected: the service never dropped a request while the rollout was broken — maxUnavailable: 0% at work.
Teaches: failed deploys don't take you down; but they don't tell you loudly either. The "merged ≠ deployed" trap.
Verified: manual.

-  E6 — Env snapshot vs file sync observe
Run: the full sequence in section 1.5's "Try this now".
Expected: env var frozen; mounted file updates within ~60s (likely seconds on kind — 60s is the ceiling from the kubelet's default 60s sync period; the watch-based cache usually lands it fast).
Teaches: the exact mechanics behind the doc-store incident.
Verified: manual.

-  E7 — Readiness ≠ restart observe
Run: kubectl get endpoints hello -w in one terminal. In another: POD=$(kubectl get pod -l app=hello -o name | head -1); kubectl exec ${POD#pod/} -- wget -qO- localhost:8080/toggle-ready
Expected: endpoint count drops by one; kubectl get pods shows 0 restarts, the pod Running but READY flipping 1/1 → 0/1.
Recover: toggle again; the endpoint returns.
Teaches: readiness controls Service membership only.
Verified: manual.

-  E8 — Liveness kills break
Run: edit 02-deployment.yaml: change the livenessProbe path to /readyz, re-apply, then toggle-ready one pod (as in E7) and wait ~30s.
Expected: RESTARTS increments — the pod was "not ready" but you made liveness see it, so the kubelet killed it. Revert the manifest after.
Teaches: viscerally, why liveness must never check what readiness checks.
Verified: manual.

-  E9 — The exec probe, the platform's way observe
Run: kubectl apply -f phase01_core_concepts/manifests/07-platform-style.yaml && kubectl get deploy,svc,hpa,pdb -l app=platform-style
Then: kubectl describe pod -l app=platform-style | grep -A3 Liveness — see the exec command.
Then: run the probe client manually: kubectl exec deploy/platform-style -- /healthcheck -addr=localhost:9090 && echo PROBE-PASSES
Expected: status=SERVING, exit 0.
Teaches: the exec→gRPC probe pattern your prod services actually use. The HPA will show <unknown> targets on kind without metrics-server — that itself teaches where HPA metrics come from (Phase 2). PDB is named here so you have seen the word; PodDisruptionBudget mechanics belong to Phase 2.
Verified: manual.

-  E10 — DNS: ClusterIP vs headless observe
Run: the debug-pod sequence from 1.4's "Try this now".
Expected: one IP vs three IPs.
Teaches: what clusterIP: None changes, and why gRPC client-side LB needs it.
Verified: manual.

-  E11 — Graceful shutdown vs dropped requests break
Run: kubectl port-forward svc/hello 8080:80 & then wget -qO- --timeout=15 localhost:8080/slow & (a 10s request) and immediately kubectl rollout restart deploy/hello.
Expected: the slow request COMPLETES — SIGTERM handling in main.go fails readiness, sleeps 5s, drains. Then read the code: phase01_core_concepts/hello-server/main.go, the shutdown block, and map each step to what you observed.
Teaches: terminationGracePeriodSeconds + SIGTERM handling = zero-downtime deploys. Without the handler, every deploy 502s.
Verified: manual.

-  E12 — Secret "encryption" theater observe
Run: kubectl apply -f phase01_core_concepts/manifests/05-secret.yaml && kubectl get secret hello-secret -o jsonpath='{.data.API_TOKEN}' | base64 -d
Expected: plaintext token, no privileges needed beyond namespace read.
Teaches: why Vault injection exists on the platform, and why base64 ≠ security.
Verified: manual.

For E11, the flip side of the race you just watched. Verified in the EndpointSlice docs: each endpoint carries ready, serving and terminating conditions (stable since v1.26), and kube-proxy may keep routing to a terminating endpoint when ALL of a Service's endpoints are terminating — that is the documented reason trailing connections are not dropped mid-rollout, and exactly why the hello-server's pattern (fail readiness immediately, sleep 5s, then drain) is the right shape: the sleep covers the window where iptables has not caught up with the SIGTERM. It is also why terminationGracePeriodSeconds has to outlast your drain time.
Source: kubernetes.io/docs/concepts/services-networking/endpoint-slices/ (fetched 2026-09-17)

## 🏢 Your platform anchor: things to check in the codebase

This phase exists so these four checks stop being trivia and start being obvious. The original names the org's chart repo; here the names stand in generically — on your machine, substitute the real paths. Everything below is a fact the original verified in that repo, not a platform claim.

- Read what every service inherits. Open default-service-template/templates/deployment.yaml in the org chart repo (661 lines — skim structure, don't grind). Find where probes are templated (about lines 264–311), where project.env.custom becomes literal env:, and confirm there is no checksum/config annotation anywhere. Then open templates/service.yaml and find the hasPrefix "grpc" → istio.io/use-waypoint block from section 1.4. This one chart is the deployment story for nearly every service you own.

- Decode a real prod values file end to end. Open the prod-us values file of a service like content-center-service. For each block, say out loud what it renders: replicaCount: 2 with hpa: {min 2, max 4, 80%}; strategy: {maxSurge 50%, maxUnavailable 0%}; exec probes with initialDelaySeconds: 60; ports http-0 and grpc-1 — why is that suffix load-bearing? Section 1.4. The resources: requests {150m, 100Mi} / limits {6, 4096Mi} pair is a 40× CPU overcommit you will learn to judge in Phase 2. And the vault: block sitting next to a plaintext ELEVENLABS_API_KEY above it — which pattern is the future, and why?

- Find your own service's probe binary. In your team's service repo, read healthCheck.sh, healthCheck/healthCheck.go, and the constants file (ServicePort = 80). Question to answer from the code: this client dials the gRPC port and calls the internal healthCheckService.HealthCheck RPC. What happens to probe results if the service's gRPC server is up but its Kafka consumers are wedged? Is that the right answer for liveness? For readiness?

- Verify the Lambda correction yourself. Open projects/missions-processors/missions-processors.json in the chart repo — find "type": "AwsLambda" — then the team stack's CloudFormation template for the MSK EventSourceMappings. Meanwhile a surveillance chart deploys Datadog consumer-lag monitors for it (real alert queries on consumer group names). Question: why might the team have chosen Lambda over a K8s Deployment for LLM-grading consumers — think cost-per-idle-replica against 25s processing latencies and scale-to-zero.

## ✅ Checkpoint 1: answer in your own words

Seven scenario questions. Each is answerable from what this phase taught; each is the shape of a real incident. Attempt before you open the sketch.

Q1. A teammate deploys im-service; CI is green. Ten minutes later, customers still see the old behavior. kubectl get pods -n <track> shows 2 pods 45 minutes old and 1 pod 10 minutes old in 0/1 Ready. Walk through exactly what happened, why zero customers saw an error, which two commands confirm your diagnosis, and what the fix path is.

Answer sketchThe v2 ReplicaSet scaled up one surge pod that never passed readiness (bad config or missing key — check its events and logs). With maxUnavailable: 0% no old pod is killed until a new one is Ready, so the 2 old pods kept serving: merged ≠ deployed, no customer impact. Confirm with kubectl rollout status deploy/im-service (hung, past the 600s progressDeadlineSeconds it reports failure) and kubectl describe pod on the 0/1 pod for the readiness failure reason. Fix the v2 failure and redeploy; rollout undo if v2 should just die.

Q2. Your Go service's readiness and liveness probes both run /healthCheck.sh, which calls the HealthCheck RPC. A new engineer "improves" the RPC to also verify the ElastiCache Redis connection. Two weeks later Redis fails over — a 40s blip. Describe the fleet's behavior minute-by-minute for the next 10 minutes, and the one-line design principle that was violated.

Answer sketcht=0 Redis down; t=0–30 all pods fail liveness 3× (10s period × 3); t=30 the kubelet restarts every pod at once; t=30–90 the fleet reboots under initialDelaySeconds: 60 — capacity zero; t=40 Redis is back and nobody is up to notice; t=90+ pods boot cold into the accumulated retry storm, CPU spikes, probe timeouts, some pods restart again. A 40s blip became ~10 minutes of total outage. Violated: liveness may never check dependencies — liveness restarts, readiness removes, and only readiness may look at Redis.

Q3. A service scales from 2 to 8 pods under load, but p99 latency stays bad and 6 pods sit at ~0% CPU. The service consumes gRPC calls from an upstream gateway. Explain the mechanism (down to what kube-proxy did and when), why the HPA cannot fix it, and the two distinct layers on the platform meant to prevent this — including the naming convention that activates one of them.

Answer sketchkube-proxy's DNAT chose a pod IP once per TCP connection, at dial time. gRPC multiplexes every request over one long-lived HTTP/2 connection, so the original 2 pods hold every request; the 6 new pods get zero traffic because no new connections ever open. The HPA sees the hot pods' CPU and scales, which only makes the idle pool larger. Prevention layer one: platform convention — gRPC ports named grpc-* in values, which the chart turns into the istio.io/use-waypoint: waypoint annotation on the Service; the waypoint does L7 per-request balancing. Layer two: the mesh itself (Istio ambient) — the data plane that makes that annotation do anything. (Also available in theory: headless Service + client-side round_robin; the platform does not use it for app services.)

Q4. During an integration-track infra migration, an RDS failover changed the writer endpoint. The tdb-svc-sqlsvc-discovery-config ConfigMap was regenerated correctly with the new host. Your service still fails writes 2 hours later. A colleague says "impossible, the ConfigMap is correct, I checked it." Why are you both right? Show the math on why no rollout occurred, the command pair that proves staleness, and two fixes — one immediate, one structural.

Answer sketchBoth right: the ConfigMap object is correct, AND your pods env vars were snapshotted at container start, before the change. No rollout because the change is inside a referenced ConfigMap: the pod spec only names configMapKeyRef → spec bytes unchanged → template hash unchanged → no new ReplicaSet → no rollout. Prove it: kubectl get cm tdb-svc-sqlsvc-discovery-config -o yaml vs kubectl exec <pod> -- env | grep TDB_SVC_SQLSVC_HOST — the two disagree. Immediate fix: kubectl rollout restart deploy/<svc>. Structural: a checksum annotation on the pod template over referenced ConfigMaps (or the Reloader controller, or immutable: true ConfigMaps with name bumps) so a config change always forces a rollout.

Q5. Design: a new async LLM-grading worker — 25s per message, bursty MSK topic, near-zero traffic at night. Argue Deployment-on-EKS vs Lambda-with-EventSourceMapping using the missions-processors anchor. Name the probe/rollout/scaling machinery you would need on K8s that Lambda gives you free, and one thing K8s gives that Lambda cannot.

Answer sketchLambda wins the night: scale-to-zero means the bursty, mostly-idle profile costs nothing when the topic is empty, and the EventSourceMapping gives consumer-lag-driven scaling, retries, and poller management with no HPA object, no probe config, no rollout machinery, no maxSurge math. K8s wins on control: 25s-per-message processing with connection reuse, warm caches, and no per-invocation cold/limits constraints, plus placement where the rest of the stack lives. The missions-processors answer was Lambda; the anchor question is whether your profile matches it. One thing K8s gives that Lambda cannot: long-lived connections and process state across messages (warm pools, in-memory caches) — the things that make 25s latencies fast in aggregate.

Q6. Show the math: a nodegroup of m5.xlarge (4 ENIs × 15 IPs), prefix delegation off, in a /24 subnet shared by 3 such nodes. Each pod requests 200m CPU. (a) Max pods per node by IP? (b) By CPU (4 vCPU)? (c) Which ceiling binds first, and what event message do you see when the other ceiling binds — and (d) which single CNI setting changes the answer?

Answer sketch(a) 4 × (15 − 1) + 2 = 58 pods per node. (b) 4 vCPU ÷ 200m = 20 pods per node — CPU binds first at 20, well under 58. Subnet headroom: 3 nodes × 20 = 60 pod IPs, far under the /24's ~251 usable, so the subnet never binds here. (c) If configs changed so IPs bound first (small subnet or big warm pool), the event is FailedCreatePodSandBox with InsufficientFreeAddressesInSubnet in the CNI logs — on a node with free CPU, the classic cosplay. (d) ENABLE_PREFIX_DELEGATION=true: slots become /28 prefixes, so the same instance family jumps to hundreds of assignable IPs.

Q7. A colleague proposes mounting a PVC into your service to cache rendered content between requests, "so we don't refetch from S3." List three operational properties of the service that silently degrade the moment the PVC lands (think 1.2's rollout math, node drains, AZ topology), and the design the platform actually uses for this problem — name the specific infra from the values file you decoded in anchor 2.

Answer sketchDegradations: (1) rescheduling is pinned to one AZ — a node failure in another AZ cannot take the pod; (2) every move pays the ~30–120s EBS detach/attach (the ballpark hunter flagged as unverified this run), so rollouts and drains slow and can wedge on attachment; (3) maxSurge: 50%/maxUnavailable: 0% stops meaning "capacity never dips" because new pods fight over the single RWO attachment — and node drains block. The platform's design: a shared external cache instead of local volume — the ElastiCache Redis cluster named in the discovery ConfigMaps from anchor 2's values file, with S3 as the origin. Cache where everyone can reach it, not where only one pod can.

## ✖ Things I could not verify — read these as open, not true

- Everything platform-internal — chart line numbers, the healthCheck binary, the four incident receipts in 1.5, Compass numbers, the cluster and account map, Vault wiring, the waypoint annotation — was verified by the original's authors inside repos hunter cannot read. Treat each as your codebase's fact until you run the anchor checks yourself.

- The WARM_IP_TARGET / MINIMUM_IP_TARGET distinction in 1.7 is from memory of the CNI README, not re-read this run. The CNI README listed in the references is the intended source.

- The 30–120s EBS attach/detach figure in 1.6 is the phase's number — a standard ballpark, not source-checked this run.

- The kubectl get endpoints truncation at 1000+ entries is common operator knowledge, not opened this run; only the 1000-per-mirror cap under it is verified in the slice docs.

- The v1.37 gRPC-TLS and h2c probe feature gates are marked alpha in the docs — do not plan around them.

- Colin Breck's probe post title and date are cited from the original, not re-fetched.

- The 2026-01-29 Steering/SRC reaffirmation of the ingress-nginx retirement exists in search results; hunter never opened the body.

## ■ References & further learning

Must-do, in this order. Every link below is either from the original phase or was opened by hunter for this page.

- 🎥 Kubernetes Deconstructed: Understanding Kubernetes by Breaking It Down — Carson Anderson, KubeCon 2017 (33 min).Why: still the single best "how do the pieces fit" talk — peels ingress → Service → kube-proxy → CNI, exactly the 1.4/1.7 stack. Slides source: kube-decon.carson-anderson.com.When: BEFORE the lab.

- 📄 gRPC Load Balancing on Kubernetes without Tears — kubernetes.io blog (10 min).Why: the canonical statement of the 1.4 problem, by the Linkerd authors.When: read AFTER E10.

- 📄 Kubernetes Liveness and Readiness Probes: How to Avoid Shooting Yourself in the Foot — Colin Breck (15 min).Why: THE probe war-story post; the cascading-failure section is 1.3's timeline in prose. (Title and date as cited in the original; not re-fetched.)When: read AFTER E8 — it clicks differently.

- 📄 Official probe docs.Why: bookmark. The successThreshold/failureThreshold semantics table is the part you will return to.When: keep open during anchors 1–3.

- 📄 How three lines of configuration solved our gRPC scaling issues — Jamf Engineering (8 min).Why: a real company hitting exactly the single-pod-pinning failure from 1.4, with graphs. Their fix, MAX_CONNECTION_AGE, is the server-side mitigation nobody mentions — contrast with your platform's mesh answer.When: after E10, next to the Tears post.

- 📄 Amazon EKS Best Practices: Optimizing IP Address Utilization.Why: the official treatment of warm pools, prefix delegation, MINIMUM_IP_TARGET.Focus: the prefix-mode section.When: after 1.7.

- 💻 aws/amazon-vpc-cni-k8s README.Why: every env var — WARM_ENI_TARGET, ENABLE_PREFIX_DELEGATION, the lot — documented. Skim the table, keep as reference. (Also the re-verification source for the warm-target distinction flagged above.)

- 📄 Automating custom networking to solve IPv4 exhaustion in EKS — AWS Containers Blog.Why: for when a subnet genuinely runs dry.When: only if you hit it.

- 📄 Deployments and 📄 Services — the rollout/rollback and service-type references. Bookmark both.

- ⚙ Hunter's sources for this page's corrections: k8s v1.34.0 upstream strategy defaults; CNI max-pods table v1.20.1; probe docs (gRPC probes, startupProbe); ConfigMap docs (subPath, 1 MiB, watch cache); EndpointSlice docs; ingress-nginx retirement; Istio ambient GA (1.24, Nov 2024).

- Internal (the real curriculum): your org's default-service-template/ chart — the chart is the doc (anchor 1); and the internal Confluence post on why ambient mode was chosen over Linkerd/Consul, which pairs with 1.4.

## ▤ Cheatsheet — Phase 1

── OBJECTS ────────────────────────────────────────────────────────────────
pod            → unit of scheduling + IP; mortal; never deployed bare
deployment     → versioned desired state; owns ReplicaSets (one per version)
service        → stable VIP + ready-pod list; readiness gates membership
                 ready-pod list = EndpointSlices (Endpoints API deprecated)
configmap      → env (snapshot at start) or file mount (live sync, ≤ ~60s)
                 subPath mounts NEVER sync; data cap 1 MiB; immutable exists
secret         → base64 ≠ encryption; real secrets: Vault agent-inject
pvc/pv/sc      → request / result / how; ebs-sc (gp3, CSI); avoid if you can

── COMMANDS YOU'LL USE DAILY ─────────────────────────────────────────────
kubectl get pods -o wide                        # + pod IP and node
kubectl describe pod <p>                        # events = 90% of debugging
kubectl get endpoints <svc>                     # who's actually serving
kubectl rollout status|undo deploy/<d>          # is it really deployed / revert
kubectl exec <p> -- env | grep <KEY>            # what the POD thinks config is
kubectl get cm <x>-discovery-config -o yaml     # what config SHOULD be
kubectl logs <p> --previous                     # why did it restart
kubectl get pod <p> -o jsonpath='{.metadata.ownerReferences[0].kind}'

── PRODUCTION SHAPE (the platform's org defaults) ────────────────────────
strategy         RollingUpdate maxSurge 50% / maxUnavailable 0%
                 (upstream default: 25% / 25%; revisionHistoryLimit: 10)
replicas         2 base + HPA (im-service: 2→10 @70%; ccs: 2→4 @80%)
probes           exec [sh /healthCheck.sh] delay 60-120s period 10 timeout 10 fail 3
                 (chart has no native gRPC probe / startupProbe template —
                  K8s HAS both: gRPC probes stable v1.27, startupProbe GA v1.20)
ports            http-0, grpc-1 — "grpc" prefix opts into Istio waypoint L7 LB
config           values YAML → literal env; discovery via <dep>-discovery-config
                 CMs; helm upgrade = the reload mechanism
config TRAP      referenced discovery-CM content change ≠ rollout → stale pods
secrets          Vault (vaultcloud/<team>/kv, agent-inject) > SM CSI > legacy k8s
clusters         prod/prod-us/prod-eu in acct 191195949309;
                 staging/integration in 845925808232
mesh             Istio AMBIENT (GA 1.24, Nov 2024) — no sidecars, ztunnel per node
ingress          nginx — UNMAINTAINED since 2026-03 (retired); migration → Higress
storage          stateless everywhere; state → RDS/Redis/S3/DDB/MSK
CNI              pod IPs = VPC IPs; max-pods = ENI×(IP/ENI−1)+2 (m5.xlarge = 58)

── THE FIVE TRUTHS ───────────────────────────────────────────────────────
1. Liveness restarts, readiness removes — only readiness may check deps.
2. gRPC = one connection; ClusterIP balances connections → name ports grpc-*.
3. Env vars snapshot at start; helm upgrade IS the config-reload mechanism.
4. maxUnavailable 0% means broken deploys hide — always `rollout status`.
5. Pending + free CPU on EKS → check FailedCreatePodSandBox (IPs, not CPU).

## ✍ Two things you could post

- "The kubelet can probe gRPC natively since v1.27 — most org charts still ship an exec binary." Yours because you read your own chart and found the exec-probe legacy inside it; the claim lands against a real file, not a blog summary.

- "Ingress-nginx is unmaintained today, and 'existing deployments will continue to function' is the scariest sentence in the retirement post." Yours because your dominant ingress path sits on it and the migration became overdue on a specific date you can name: 2026-03-01.

Phase 1 of 7 — next: Phase 2, Scaling & Resources (requests vs limits, QoS classes, OOMKill autopsy, HPA + KEDA, PDB).