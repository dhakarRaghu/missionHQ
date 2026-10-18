# Phase 4 — Architecture & HA (the phase about what happens when a node dies)

Everything so far assumed Redis was *there* — a single box answering `GET`s. This phase is about the day it isn't: the primary crashes, an availability zone goes dark, a version upgrade reshuffles your keys, or a network partition splits the cluster. Redis in production is never one box; it's a replication topology with a failover story and a durability story, and both stories have a **data-loss window** you need to be able to quantify.

Here's the thing that catches people: Redis's own persistence and Redis's high-availability are *different problems with different answers*, and on AWS ElastiCache — which is what Mindtickle runs — the answers are not the ones you'd pick for self-hosted Redis. ElastiCache doesn't lean on AOF for durability the way a textbook would; it leans on **replication + Multi-AZ failover**, with RDB snapshots only as a backup. Get this wrong in your mental model and you'll reason about the wrong failure modes.

And the failure modes are real and recent at Mindtickle: the Equip cluster hit a **cluster-mode upgrade** that reshuffled keys across shards while a client held a stale slot map (Jan 2026); UPI-3658 broke pub/sub because cluster mode needs cluster-aware routing; and an AI-Completion path hardcoded `WAIT(2, 2s)` assuming two replicas that didn't exist in staging, adding 2 seconds to every call. Every one of those is an *architecture* bug — the code was fine in isolation and wrong about the topology.

By the end of this phase you'll be able to quantify the data-loss window of any Redis setup, explain exactly what happens in the 2–5 seconds after a primary dies, choose between Sentinel and Cluster mode, and read Mindtickle's real ElastiCache configs (which you'll see are *not* uniform) and predict how each behaves under failure.

Time: 5–7 days. The replication and cluster exercises need multiple containers — that's the point; HA can't be learned on one node.

## What we cover in Phase 4:
```
┌──────────────────────────────────────────────────────────────────────────┐
│  4.1  Persistence         — RDB vs AOF, the data-loss window, and what    │
│                             ElastiCache ACTUALLY does (not what you think) │
│  4.2  Replication         — async replication, read replicas, WAIT, and   │
│                             the failover data-loss window                  │
│  4.3  Failover            — what happens in the 2-5s after a primary dies  │
│  4.4  Sentinel vs Cluster — the two HA topologies, and when each fits      │
│  4.5  Cluster mode        — 16384 slots, MOVED/ASK, hash tags, resharding  │
│  4.6  ElastiCache at MT    — the prod-US/prod-EU split, Multi-AZ, backups  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4.1 — Persistence (the data-loss window you're signing up for)

**Why this matters:** "Redis is in-memory" makes people think a restart loses everything. It doesn't have to — but *how much* it loses on a crash is a config choice with a precise, quantifiable window, and most engineers can't state their own. On ElastiCache the answer is different from self-hosted, and knowing which one you're on determines what a crash costs you.

Redis has two persistence mechanisms, and they answer different questions:

**RDB (Redis Database) — point-in-time snapshots.** Periodically, Redis forks and writes the entire dataset to a compact binary file (`dump.rdb`). Configured as `save <seconds> <changes>` (e.g. `save 60 1000` = snapshot if ≥1000 keys changed in 60s). On restart, it loads the last snapshot.

```
┌─────────────────────────────────────────────────────────────────────┐
│  RDB data-loss window                                                │
│                                                                      │
│  t=0   BGSAVE → snapshot taken (dump.rdb has everything up to here)  │
│  t=0-60 ...writes happen, NOT yet in any snapshot...                 │
│  t=45  CRASH (SIGKILL / OOM / power loss)                            │
│  t=45  restart → loads t=0 snapshot                                  │
│                                                                      │
│  LOST: every write from t=0 to t=45 (up to a full snapshot interval) │
│  → RDB trades durability for speed: tiny files, fast restart, but    │
│    a crash loses everything since the last snapshot.                 │
└─────────────────────────────────────────────────────────────────────┘
```

**AOF (Append-Only File) — a log of every write.** Every write command is appended to a log; on restart, Redis replays the log. The durability depends on `appendfsync`:
- `always` — fsync every write. Loss ≈ 0, but slow (a disk sync per command).
- `everysec` — fsync once per second. Loss ≤ ~1 second of writes. **The standard choice.**
- `no` — let the OS decide (up to ~30s). Fast, weak.

```
┌────────────────┬──────────────────────┬───────────────────────────────┐
│                │  RDB                 │  AOF (everysec)               │
├────────────────┼──────────────────────┼───────────────────────────────┤
│ What it is     │ periodic snapshot    │ log of every write            │
│ Crash loss     │ since last snapshot  │ ≤ ~1 second                   │
│                │ (seconds to minutes) │                               │
│ File size      │ small (compressed)   │ large (grows; needs rewrite)  │
│ Restart speed  │ fast (load one file) │ slower (replay the log)       │
│ Write overhead │ ~none (fork+snapshot)│ fsync cost per interval       │
│ Best for       │ backups, fast restart│ minimal-loss durability       │
└────────────────┴──────────────────────┴───────────────────────────────┘
```

You can run both (AOF for durability + RDB for fast backups) — that's the belt-and-suspenders default for self-hosted.

**Now the ElastiCache reality, which is the part that matters for you.** Mindtickle runs ElastiCache, and ElastiCache's durability model is *not* "turn on AOF." ElastiCache for Redis doesn't expose AOF as a parameter at all (Compass confirmed: zero `appendonly` config on any ElastiCache resource). Instead, durability comes from:
1. **RDB snapshots for backup** — configured via `SnapshotRetentionLimit` (days to keep) and `SnapshotWindow` (when) — *and it's not uniform.* The real configs: `equip-redis` (prod-US) keeps `SnapshotRetentionLimit: 3` (daily, 04:00–05:00); `redis-cache-data-cluster` (prod-EU) keeps `SnapshotRetentionLimit: 1` (02:00–03:00); and — critically — **`common-redis-elasticcache` (prod-US/integration) configures NO snapshots at all** (the fields are absent from its CFN → default snapshotting effectively unmanaged). So the "backup" durability floor ranges from 3 days to *nothing* depending on which cluster you're on.
2. **Replication + Multi-AZ failover** for *availability* (4.2–4.3) — which is a different property than persistence. (And even this varies: `equip-redis` and `redis-cache-data-cluster` set `MultiAZEnabled: true`; `common-redis` sets only `AutomaticFailoverEnabled` and leaves MultiAZ absent.) There is **no Global Datastore / cross-region replication** anywhere — each region stands alone.

The consequence, and the sentence to internalize: **on ElastiCache, a single node's durability is a daily RDB snapshot — your real protection against data loss is the replica, not the disk.** If the primary dies, you don't restore from `dump.rdb` (that's hours stale); you fail over to the replica (seconds behind). This is why 4.2's replication story matters more than persistence for ElastiCache — and it also means the cache is genuinely a *cache*: treat anything in it as reconstructible, because your durability floor is "yesterday's snapshot + whatever the replica had."

**The sentence to remember:** RDB loses since-the-last-snapshot, AOF-everysec loses ≤1s — but on ElastiCache you get neither as your primary durability; you get daily RDB backups plus replica failover, so treat cached data as reconstructible, not durable.

**The trap:** assuming your ElastiCache has AOF because "we enabled persistence." Cluster-mode ElastiCache doesn't. Your data-loss window on a total failure is the replication lag (small) on failover, or the last daily snapshot (large) on a true disaster.

**Try this now:**
```bash
bash ./phase04_ha/persistence_demo.sh
# RDB-only: the key written after BGSAVE is LOST on crash.
# AOF-everysec: all keys survive (replayed from the log).
```

---

## 4.2 — Replication (the copy that saves you, and its lag)

**Why this matters:** replication is what makes Redis highly available and what gives you read scaling — but it's **asynchronous**, which means there's a window where the primary has acknowledged a write that the replica doesn't have yet. If the primary dies in that window, that write is gone. Quantifying and controlling that window is the core HA skill, and it's where the `WAIT` incident lives.

The topology: one **primary** takes writes; one or more **replicas** continuously copy the primary's write stream and can serve reads.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ┌──────────┐   async stream   ┌──────────┐        │
│   writes ─────────►│ PRIMARY  ├─────────────────►│ REPLICA 1│        │
│                    │ (master) ├─────────────────►│ REPLICA 2│◄─reads │
│                    └──────────┘                  └──────────┘        │
│                         ▲                                            │
│                         └── reads (or offload reads to replicas)     │
│                                                                      │
│  Key fact: SET returns to the client as soon as the PRIMARY has it.  │
│  Replication happens AFTER the ack → the replica is always slightly  │
│  behind (replication lag: usually <1ms same-AZ, more cross-AZ).      │
└─────────────────────────────────────────────────────────────────────┘
```

Two things fall out of "replication is async":

**1. The failover data-loss window.** If the primary acks a write, then dies before the replica received it, and the replica is promoted — that write is lost. The window is the replication lag. Usually tiny (sub-millisecond same-AZ), but a slow/overloaded primary or a cross-AZ replica widens it. **This is why Redis is not a system of record**: even with replication, a failover can drop the last few writes.

**2. `WAIT` — trading latency for durability.** `WAIT numreplicas timeout_ms` blocks until `numreplicas` have acknowledged all your writes so far (or the timeout fires), returning how many actually acked. It lets you say "don't proceed until this write is on 2 replicas" — shrinking the loss window to near-zero for that write, at the cost of the round-trip to the replicas.

And this is exactly where Mindtickle got bitten (Compass confirmed the code *and* the RCA). Two COE/ML services do it: `coe-ml/tool-auth-service` (`infrastructure/redis/redis.go:106`, `r.client.Wait(2, 2*time.Second)`, gated on `config.Track == "prod"`) and `coe-ml/ai-completion` (`src/infrastructure/redis/redisClient.go:98`, `Wait(2, REDIS_SET_WAIT_TIME)`). The RCA ("Redis Wait Operation Performance Issue", COE Confluence, Atul Verma, Sep 2025): production *had* 2 replicas so `WAIT` returned in <100ms, but integration/staging had only **1** replica, so `WAIT 2` could never be satisfied → it blocked the **full 2 seconds on every `Set`**, inflating Set latency to 2000ms+ vs <100ms in prod. The bug wasn't `WAIT`; it was hardcoding the replica count instead of reading the actual topology (`connected_slaves` from `INFO replication`). The fix: make the `WAIT` call environment-aware (disable it where there's only 1 replica) — which dropped staging latency to ~15ms.

```
   Correct WAIT (prod, 2 replicas):        Incident (staging, 1 replica):
   SET k v                                 SET k v
   WAIT 2 2000 → 2, in ~1ms                WAIT 2 2000 → 1, in 2000ms  ← full timeout
   (both replicas acked fast)              (2nd replica never exists → blocks, every call)
```

**The sentence to remember:** replication is asynchronous, so a failover can lose the last few acked writes (the replication-lag window); `WAIT` shrinks that window but only works if the replica count you demand actually exists — hardcode it and you'll block the full timeout, like the AI-Completion incident.

**The trap:** `WAIT <n> <timeout>` with a hardcoded `n` that doesn't match every environment. Read `connected_slaves` or make `n` config-driven; otherwise a smaller environment eats the full timeout.

**Try this now:**
```bash
# Single instance (0 replicas): WAIT 2 blocks the full timeout — the incident.
go run ./phase04_ha/wait_command -replicas 2 -timeout 2s
# Real replication (2 replicas): WAIT 2 returns 2 fast.
docker compose -f docker-compose.replication.yml up -d && sleep 5
docker exec redis-primary redis-cli SET k v && docker exec redis-primary redis-cli WAIT 2 1000  # → 2
docker compose -f docker-compose.replication.yml down
```

---

## 4.3 — Failover (the 2–5 seconds after a primary dies)

**Why this matters:** failover is the moment HA either works or doesn't, and it's a *specific sequence* with a *specific unavailability window*. If you can't narrate it, you can't reason about what your app sees (errors? stale reads? a gap?) or tune the timeouts that control it.

Here's the timeline when a primary dies, with the two coordination models Redis uses (Sentinel for non-cluster, the cluster bus for cluster-mode; ElastiCache manages both for you):

```
┌───────────────────────────────────────────────────────────────────────┐
│ Timeline: primary failure + automatic failover                        │
│                                                                        │
│  t=0.0s   primary serving writes; replicas following                  │
│  t=0.0s   primary dies (crash / AZ outage / kill)                     │
│  t=0-Xs   the monitor (Sentinel quorum / cluster nodes) MISSES        │
│           heartbeats. Detection takes `down-after-milliseconds`        │
│           (Sentinel default 30s! ElastiCache tunes this much lower)   │
│  t=X      a replica is elected new primary (most up-to-date replica    │
│           wins; needs a majority to avoid split-brain)                │
│  t=X+     new primary announced; clients' next write to the OLD        │
│           primary fails → client refreshes topology → finds new one   │
│  t=X+ε    writes resume against the new primary                       │
│                                                                        │
│  App sees: a burst of errors/timeouts for the detection+election      │
│  window, then recovery. Writes in the replication-lag window at t=0   │
│  are LOST (4.2). On ElastiCache Multi-AZ this is typically seconds.   │
└───────────────────────────────────────────────────────────────────────┘
```

The three things that determine your experience:

1. **Detection time** — how fast the death is noticed. Sentinel's `down-after-milliseconds` (default 30s, way too high; ElastiCache uses much lower internal values). This dominates the unavailability window.
2. **Quorum / majority** — a replica can only be promoted if a majority of monitors agree, which is what prevents *split-brain* (two primaries). This is why you want an **odd** number of nodes/AZs.
3. **Client behavior** — the client must detect the failed connection and re-discover the new primary. A good client (go-redis, redsync) does this on the next error; a client with a stale topology cache stalls (the Equip incident, 4.5).

The subtle danger: **`unclean` promotion and lost writes.** The promoted replica is the most up-to-date one available, but "most up-to-date" ≠ "fully caught up" — the writes the dead primary acked but hadn't replicated are gone. There's no way around this with async replication; it's the price of not blocking every write on `WAIT`.

**The sentence to remember:** failover = detection (the slow part — tune `down-after-milliseconds`) + majority-elected promotion (prevents split-brain, needs odd quorum) + client topology refresh — and the writes in the replication-lag window at the moment of death are lost.

**The trap:** an even number of nodes/AZs (split-brain risk) or a client that caches topology and doesn't refresh on error (stalls through the whole window). Both turn a 3-second blip into an outage.

**Verify your understanding:** ElastiCache equip-redis runs `AutomaticFailoverEnabled: true` + `MultiAZEnabled: true` + `ReplicasPerShard: 2`. Why does 2 replicas (3 nodes/shard total) give clean failover where 1 replica (2 nodes) is riskier? (Majority: with 3 nodes a promotion can get a 2-of-3 majority; with 2 nodes there's no majority if one dies — split-brain risk.)

---

## 4.4 — Sentinel vs Cluster (the two HA topologies)

**Why this matters:** these are the two ways to make Redis highly available, they solve *different* problems, and confusing them leads to picking the wrong one. Mindtickle runs the managed-ElastiCache equivalents of both (cluster-mode-enabled in some regions, disabled in others — 4.6), so you need to know what each buys.

```
┌──────────────────────────────┬──────────────────────────────────────────┐
│  SENTINEL (a.k.a. cluster-    │  CLUSTER MODE                             │
│  mode DISABLED on ElastiCache)│  (cluster-mode ENABLED)                   │
├──────────────────────────────┼──────────────────────────────────────────┤
│ Solves: AVAILABILITY          │ Solves: AVAILABILITY + horizontal SCALE   │
│ One primary + N replicas.     │ Data SHARDED across N primaries (16384    │
│ ALL data on every node.       │ slots split across shards), each with     │
│                               │ its own replicas.                         │
│ Sentinel processes monitor    │ Nodes gossip over the cluster bus; they   │
│ the primary and orchestrate   │ detect failure + elect among themselves.  │
│ failover + tell clients the   │                                           │
│ new primary.                  │                                           │
│                               │                                           │
│ Scales: reads (add replicas). │ Scales: reads AND writes AND memory       │
│ Writes + memory capped at ONE │ (add shards). The only way past one       │
│ node's capacity.              │ node's RAM/write throughput.              │
│                               │                                           │
│ Multi-key ops: always work    │ Multi-key ops: only if keys share a slot  │
│ (all data on one primary).    │ (need hash tags) → CROSSSLOT errors else. │
│                               │                                           │
│ Complexity: LOW               │ Complexity: HIGH (slots, MOVED, resharding)│
│ Use when: data fits one node, │ Use when: data/throughput exceeds one     │
│ you just need failover.       │ node. Accept the complexity for scale.    │
└──────────────────────────────┴──────────────────────────────────────────┘
```

The decision is really one question: **does your data and write throughput fit on one (big) node?** If yes → cluster-mode-disabled (Sentinel-style): simpler, multi-key ops always work, just add replicas for HA and read scaling. If no → cluster mode: shard across primaries, accept the slot/hash-tag/resharding complexity as the price of horizontal scale.

This is *exactly* the tradeoff Mindtickle made differently by region (4.6): prod-US ran cluster-mode-enabled (5.0.6), but prod-EU deliberately **migrated to cluster-mode-disabled** (the `CLUSTER_MODE_SIMPLIFICATION.md` doc) — trading horizontal scale for the operational simplicity of no slots, no CROSSSLOT errors, no resharding hazards. That's a team looking at "our data fits one node" and choosing simplicity. It's a defensible, senior call.

**The sentence to remember:** Sentinel/cluster-mode-disabled = one primary's worth of data with failover (simple, multi-key ops always work); cluster mode = data sharded across primaries for horizontal scale (complex, multi-key ops need hash tags) — choose by whether your data fits one node.

**The trap:** using cluster mode when your data fits one node. You take on slots, CROSSSLOT errors, hash-tag discipline, and resharding risk (the Equip incident) for scale you don't need. prod-EU's migration *away* from cluster mode is the lesson.

---

## 4.5 — Cluster mode internals (slots, MOVED, and why Equip broke)

**Why this matters:** if you're on cluster mode, the 16384-slot model isn't a detail — it dictates which operations are even *legal*, and its resharding behavior caused two real Mindtickle incidents. This is the section that turns "cluster mode is complicated" into "I know exactly what it does."

Cluster mode splits the keyspace into **16384 hash slots**. A key's slot is `CRC16(key) % 16384`, and each slot is owned by exactly one shard (primary). Clients keep a slot→shard map and route each command to the right shard.

```
┌─────────────────────────────────────────────────────────────────────┐
│  16384 slots, split across 3 shards:                                │
│    shard 0: slots 0-5460     shard 1: 5461-10922   shard 2: 10923+   │
│                                                                      │
│  SET company:c7:profile   → CRC16 → slot 15713 → shard 2            │
│  SET company:c7:settings  → CRC16 → slot 11829 → shard 2            │
│  SET company:c7:sessions  → CRC16 → slot 3080  → shard 0  ← different!│
│                                                                      │
│  MGET across profile+sessions → CROSSSLOT error (different shards).  │
└─────────────────────────────────────────────────────────────────────┘
```

Three consequences you must know:

**1. Multi-key ops need same-slot keys.** `MGET`, `MULTI/EXEC`, a Lua script touching 2 keys — all fail with `CROSSSLOT` if the keys are on different slots. The fix is **hash tags**: only the part in `{braces}` is hashed, so `{company:c7}:profile` and `{company:c7}:settings` hash to the *same* slot and land on the same shard. Mindtickle's `external-sharing-service` uses `{companyName}key` exactly so a company's keys co-locate for bulk `MGET`.

**2. MOVED/ASK redirects.** If a client sends a command to the wrong shard (its slot map is stale), the shard replies `MOVED <slot> <host:port>` — "not mine, go there." A correct client follows the redirect *and* refreshes its slot map. `ASK` is the transient version during a live slot migration.

**3. Resharding moves slots — and that's where Equip broke.** When you add/remove shards or upgrade cluster mode, slots **migrate** to new shards. A client caching the old slot map queries the old shard and gets nil — the key looks *missing* even though it's just on a different shard now.

```
┌─────────────────────────────────────────────────────────────────────┐
│  The Equip cluster-mode upgrade incident (Jan 2026)                  │
│                                                                      │
│  before: key equip:notif:count:u42 → slot 10876 → shard 1 (3 shards)│
│  upgrade/reshard → slot 10876 now owned by shard 2 (4 shards)        │
│  client with STALE slot map → queries shard 1 → key not there → nil │
│  → high error rate on equip-gql-graphql (keys look "missing")       │
│  fix: client restart / topology re-discovery so it honors the new   │
│       slot map (and MOVED redirects)                                 │
└─────────────────────────────────────────────────────────────────────┘
```

And **UPI-3658**: pub/sub in cluster mode needs *cluster-aware* routing — a plain `SUBSCRIBE`/`PUBLISH` isn't automatically routed to the right shard the way keyed commands are (sharded pub/sub, `SSUBSCRIBE`, exists precisely for this). When a cluster was switched to cluster mode, the unseen-notification-count pub/sub broke because the publisher and subscriber weren't on the same shard's channel. The lesson: **turning on cluster mode changes the semantics of pub/sub and multi-key ops — code that worked in cluster-mode-disabled can silently break.**

**The sentence to remember:** cluster mode = 16384 slots, `slot = CRC16(key) % 16384`, one shard per slot — so multi-key ops need `{hash tags}` to co-locate, resharding *moves* slots (stale client maps → "missing" keys = the Equip incident), and pub/sub needs cluster-aware routing (UPI-3658).

**The trap:** assuming a client "just works" across a topology change. It works only if it honors MOVED and re-discovers slots. A client that caches the slot map and doesn't refresh turns a reshard into an outage.

**Try this now:**
```bash
go run ./phase04_ha/cluster_hashslots
# See CRC16 slots, hash-tag co-location (all → slot 8819), and the Equip
# slot-migration mechanism (slot 10876 moves shard 1 → shard 2 on reshard).
```

---

## 4.6 — ElastiCache at Mindtickle (the non-uniform reality)

**Why this matters:** you'll operate *these* clusters, and the single most important fact is that **there is no one "Mindtickle Redis."** Config varies by cluster, region, and migration wave. Reasoning about "our Redis" as if it's uniform is how you get surprised.

The verified topology (from `devops-helm-charts` CFN templates):

```
┌──────────────────────────────┬──────────────┬────────┬──────────┬──────────────┬──────────┐
│ Cluster / region             │ cluster mode │ engine │ replicas │ HA           │ snapshots│
├──────────────────────────────┼──────────────┼────────┼──────────┼──────────────┼──────────┤
│ common-redis (prod-US)       │ ENABLED      │ 5.0.6  │ 2        │ failover;    │ NONE     │
│                              │              │        │          │ MultiAZ unset│          │
│ equip-redis (prod-US)        │ ENABLED      │ 6.2    │ 2        │ MultiAZ+     │ 3 days   │
│                              │ (.cluster.on)│        │          │ failover     │ 04-05h   │
│ redis-cache-data (prod-EU)   │ DISABLED     │ 6.x    │ 1        │ MultiAZ+     │ 1 day    │
│                              │              │        │          │ failover     │ 02-03h   │
│ common-redis (integration)   │ ENABLED      │ 5.0.6  │ 1        │ failover     │ NONE     │
└──────────────────────────────┴──────────────┴────────┴──────────┴──────────────┴──────────┘
  No AOF anywhere. No Global Datastore / cross-region replication.
  Eviction: volatile-lru (default param group). Persistence floor ranges 3 days → NONE.
```

The three things this table tells you:

**1. Cluster mode is a per-cluster/per-region choice, and it changed over time.** prod-US common and equip run cluster-mode-*enabled*; the prod-EU "simplified" set was deliberately migrated to cluster-mode-*disabled* (`CLUSTER_MODE_SIMPLIFICATION.md`) — trading horizontal scale for operational simplicity (no slots, no CROSSSLOT, no reshard hazard). Same company, opposite calls, both defensible (4.4).

**2. Replica count varies by environment — which is the root of the `WAIT` incident.** prod has 2 replicas per shard; staging/integration often has 1 (or on t3.micro). Any code that assumes a fixed replica count (`WAIT 2`, or "reads always hit a replica") is correct in prod and wrong in staging. **Never hardcode topology.**

**3. Durability is replication + (sometimes) an RDB backup, never AOF — and the backup floor varies.** `equip-redis` keeps 3-day snapshots, `redis-cache-data` 1-day, and `common-redis` keeps **none**. `AutomaticFailoverEnabled` (+`MultiAZEnabled` where set) gives failover to a replica in another AZ. So the data-loss story is: on a node failure, fail over to the replica (lose the replication-lag window, ~ms); on a catastrophic cluster loss, restore from a snapshot if the cluster *has* one (equip: ≤24h; common-redis: **nothing to restore**). Treat cache data as reconstructible — on common-redis you have no choice.

The operational rule that falls out: **before you reason about a Redis behavior, check *which* cluster and *which* environment.** Is it cluster mode? How many replicas here? What's the engine version (5.0.6 vs 6.2 vs 6.x — pub/sub, sharded-pubsub, and some commands differ)? The Equip, UPI-3658, and WAIT incidents were all "correct code, wrong assumption about this specific topology."

**The sentence to remember:** there is no uniform "Mindtickle Redis" — cluster mode, engine version, node size, and replica count vary by cluster/region/environment, durability is replication + daily RDB (no AOF), and every HA incident so far was code that assumed a topology it didn't verify.

**The trap:** testing against staging (1 replica, maybe cluster-mode-disabled) and assuming prod (2 replicas, cluster-mode-enabled) behaves identically. The `WAIT` incident is exactly this. Check the topology per environment.

**In your codebase:** open `devops-helm-charts/infra/team-equip/equip-redis-elasticache-cluster/values-prod-us.yaml`. Confirm: `AutomaticFailoverEnabled: true`, `MultiAZEnabled: true`, `ReplicasPerShard: 2`, `RedisEngineVersion: 6.2`, `CacheParameterGroupName: default.redis6.x.cluster.on`, `SnapshotRetentionLimit: 3`. Then find the staging/integration values file and diff the replica count. That diff is the `WAIT` incident.

---

## 🧪 Hands-on lab — the exercises that teach Phase 4

Setup (single node for some, multi-node compose for others):
```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d                                    # single study node
docker-compose -f docker-compose.replication.yml up -d  # primary + 2 replicas (for E5-E8)
```

- [ ] **E1. RDB loses since-last-snapshot.**
  - Run: `bash ./phase04_ha/persistence_demo.sh`
  - Expected: the key written *after* BGSAVE is gone after the crash+restart; AOF keeps all.
  - Teaches: the RDB data-loss window vs AOF-everysec.

- [ ] **E2. See the persistence config.**
  - Run: `docker exec redis-study redis-cli CONFIG GET save; docker exec redis-study redis-cli CONFIG GET appendonly`
  - Expected: the study node's save rules and `appendonly no` (our sandbox).
  - Teaches: how to check what durability you actually have.

- [ ] **E3. Force a snapshot and find it.**
  - Run: `docker exec redis-study redis-cli BGSAVE; docker exec redis-study redis-cli LASTSAVE; docker exec redis-study redis-cli --rdb /tmp/dump.rdb` (or check `INFO persistence | grep rdb_last_save_time`).
  - Teaches: `BGSAVE`/`LASTSAVE`/`INFO persistence` — the snapshot toolkit.

- [ ] **E4. The WAIT incident (single node = 0 replicas).**
  - Run: `go run ./phase04_ha/wait_command -replicas 2 -timeout 2s`
  - Expected: `WAIT 2` blocks the full 2s and returns 0 → the AI-Completion staging failure.
  - Teaches: hardcoded replica counts block the full timeout when replicas are missing.

- [ ] **E5. Real replication.**
  - Run: `docker exec redis-primary redis-cli INFO replication` (→ role:master, connected_slaves:2).
  - Then: `docker exec redis-primary redis-cli SET foo bar; docker exec redis-replica-1 redis-cli GET foo` (→ bar, replicated).
  - Teaches: primary→replica async replication, and replicas serve reads.

- [ ] **E6. WAIT works when replicas exist.**
  - Run: `docker exec redis-primary redis-cli SET k v; docker exec redis-primary redis-cli WAIT 2 1000`
  - Expected: `2` (both replicas acked), fast — contrast with E4.
  - Teaches: WAIT's contract, and why the replica count must match.

- [ ] **E7. Replicas are read-only.**
  - Run: `docker exec redis-replica-1 redis-cli SET x 1`
  - Expected: `READONLY You can't write against a read only replica.`
  - Teaches: writes go to the primary only; replicas reject writes by design.

- [ ] **E8. (Break it) Simulate failover / replication lag.**
  - Run: pause the primary mid-writes: `docker pause redis-primary`, write attempts fail; `docker exec redis-replica-1 redis-cli INFO replication | grep master_link_status` (→ down). `docker unpause redis-primary` to recover.
  - Teaches: what clients see when the primary is unreachable; the link-status signal.

- [ ] **E9. CRC16 slots + hash tags.**
  - Run: `go run ./phase04_ha/cluster_hashslots`
  - Expected: untagged keys scatter across shards; `{company:c7}` tags co-locate to one slot (8819).
  - Teaches: slot computation, CROSSSLOT, and hash-tag co-location.

- [ ] **E10. Verify a slot against Redis's own value.**
  - Reason/verify: the demo prints `slot("foo")=12182`; Redis documents `CLUSTER KEYSLOT foo` = 12182. (Our study node isn't cluster mode, but the CRC16 is identical.)
  - Teaches: the slot math is deterministic and matches Redis exactly.

- [ ] **E11. Read the real ElastiCache config.**
  - Run: open `devops-helm-charts/infra/team-equip/equip-redis-elasticache-cluster/values-prod-us.yaml` and the staging one.
  - Expected: prod-us = 2 replicas, MultiAZ, failover, redis 6.2, cluster.on, snapshot retention 3.
  - Teaches: the real topology, and the prod-vs-staging replica diff behind the WAIT incident.

- [ ] **E12. (Break it) CROSSSLOT in your head, then confirm the fix.**
  - Reason: given the demo's output, why does `MGET company:c7:profile company:c7:sessions` fail on a real cluster but `MGET {company:c7}:profile {company:c7}:sessions` succeed?
  - Teaches: the exact rule for when multi-key ops are legal in cluster mode.

---

## 🏢 Mindtickle anchor — things to check in the codebase

1. **The real HA config.** Open `devops-helm-charts/infra/team-equip/equip-redis-elasticache-cluster/values-prod-us.yaml`: `AutomaticFailoverEnabled: true`, `MultiAZEnabled: true`, `ReplicasPerShard: 2`, `NumOfShards: 1`, `RedisEngineVersion: 6.2`, `CacheParameterGroupName: default.redis6.x.cluster.on`, `SnapshotRetentionLimit: 3`, `SnapshotWindow: 04:00-05:00`. Questions: what's the data-loss window on a primary failure here (replica lag)? On a total cluster loss (up to the last daily snapshot)? Is there AOF? (No — RDB backup only.)

2. **The prod-EU simplification.** Find `CLUSTER_MODE_SIMPLIFICATION.md` (or the prod-EU values with `.cluster.off`/cluster-mode-disabled). Question: why would a team migrate *away* from cluster mode? (Data fits one node → trade horizontal scale for no slots/CROSSSLOT/reshard hazard — 4.4. It's a simplicity win, not a regression.)

3. **The topology-assumption bug.** Open `coe-ml/tool-auth-service/infrastructure/redis/redis.go:106` (`r.client.Wait(2, 2*time.Second)`, gated on `config.Track == "prod"`) and `coe-ml/ai-completion/src/infrastructure/redis/redisClient.go:98`. Question: is the `2` hardcoded or read from `connected_slaves`? Then diff replica count between `common-redis` prod-US (2) and integration (1) values. That diff is the incident (RCA "Redis Wait Operation Performance Issue", COE Confluence) — a hardcoded `WAIT 2` in a 1-replica env blocked the full 2s; the fix made it env-aware and staging dropped from 2000ms to ~15ms.

4. **The hash-tag co-location.** In `external-sharing-service`, find the `{hashTag}key` construction (e.g. `{companyName}contactEmail`). Question: what multi-key operation does this enable (bulk `MGET` of a company's keys), and what would break without the braces on a cluster-mode cluster? (CROSSSLOT — the keys would scatter across shards.)

---

## ✅ Checkpoint 4 — answer in your own words

**Q1.** State the data-loss window for each, precisely: (a) self-hosted Redis with RDB `save 60 1000` only; (b) self-hosted with AOF `appendfsync everysec`; (c) Mindtickle's equip-redis ElastiCache on a *primary node failure*; (d) equip-redis on a *total cluster loss*. Which of these is Mindtickle actually running, and what does that imply about treating Redis as a system of record?

**Q2.** Walk the AI-Completion `WAIT(2, 2s)` incident end to end. Why did it work in prod and add 2s/call in staging? Show the exact `INFO replication` field the code should have read instead of hardcoding `2`, and give two fixes (one code, one config).

**Q3.** A primary dies at t=0. Narrate the next 5 seconds for a cluster-mode-enabled ElastiCache with `AutomaticFailoverEnabled: true` and 2 replicas: detection, election (why does 2 replicas + primary = clean majority?), client recovery, and what data (if any) is lost. Then: why would an *even* node count risk split-brain?

**Q4.** A colleague wants to "upgrade us to cluster mode for scale." Given prod-EU deliberately went the *other* way (`CLUSTER_MODE_SIMPLIFICATION.md`), argue both sides: when is cluster mode the right call, and what four specific complexities (name them) does it impose that cluster-mode-disabled avoids? What single question decides it?

**Q5.** The Equip Jan-2026 incident: a cluster-mode upgrade reshuffled slots and `equip-gql-graphql` started getting nil for keys that existed. Explain the mechanism using CRC16 slots, and explain precisely what a *correct* client does (MOVED handling + slot-map refresh) that the failing one didn't. Why did a restart fix it?

**Q6.** Design task: you need `MGET` of a company's profile, settings, and 5 session keys in *one* round-trip on a cluster-mode cluster. Show the key design that makes this legal, name the mechanism, and explain the risk you're accepting (hint: what if one company has 90% of the data — hot slot/shard?).

**Q7.** UPI-3658: pub/sub broke when a cluster switched to cluster mode. Explain why plain `PUBLISH`/`SUBSCRIBE` isn't automatically cluster-routed the way `GET`/`SET` are, and what the cluster-aware alternative is. What's the general lesson about "turning on cluster mode" for code that already works?

---

## References & Further Learning

**Must-read (in order):**
- 📄 [Redis persistence — official docs](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/) — RDB, AOF, `appendfsync` modes, and the exact durability guarantees. (20 min) Read BEFORE 4.1.
- 📄 [Redis replication — official docs](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/) — async replication, the WAIT command, replica read-only. (20 min) Read with 4.2.
- 📄 [Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/) — the 16384-slot model, hash tags, MOVED/ASK, resharding. (40 min) The canonical source for 4.5; read §"Keys distribution model" and §"Redirection".
- 📄 [ElastiCache: Replication & Multi-AZ — AWS docs](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/AutoFailover.html) — how AWS does automatic failover, snapshots, and Multi-AZ. (20 min) This is what Mindtickle actually runs.

**Deep dives:**
- 📄 [ElastiCache: cluster-mode enabled vs disabled — AWS](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/Replication.Redis-RedisCluster.html) — the exact prod-US/prod-EU distinction from 4.6. (15 min)
- 📄 [Redis Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/) — hands-on resharding; watch what happens to slots when you add a node (the Equip incident, controlled). (30 min)
- 🎥 [Redis University RU301 — Running Redis at Scale](https://redis.io/university/) — the HA/scaling course; the replication and failover modules are the relevant ones.
- 📚 *Designing Data-Intensive Applications* (Kleppmann), Ch. 5 "Replication" — the definitive treatment of leader-based replication, replication lag, and failover. Read §"Problems with Replication Lag" alongside 4.2.

**Official docs (bookmark):**
- [WAIT command](https://redis.io/commands/wait/) — the semantics behind the AI-Completion incident.
- [CLUSTER KEYSLOT / hash tags](https://redis.io/commands/cluster-keyslot/) — verify your slot math; the hash-tag rule.
- [INFO replication / persistence](https://redis.io/commands/info/) — the fields you read to know your real topology.

---

## Cheatsheet — Phase 4

```
PERSISTENCE (the data-loss window)
  RDB  = periodic snapshot (save N M). Crash loses SINCE LAST SNAPSHOT.
  AOF  = write log. appendfsync everysec → lose ≤1s; always → ~0 (slow); no → ~30s.
  ElastiCache: RDB snapshots for BACKUP only (equip: retention 3d, window 04:00-05:00).
               NO AOF. Real durability = REPLICATION + Multi-AZ failover.
  → treat cache data as RECONSTRUCTIBLE, not durable.

REPLICATION (async → there's a loss window)
  SET returns when PRIMARY has it; replicas follow AFTER (lag: <1ms same-AZ).
  failover loses the replication-lag window of acked-but-unreplicated writes.
  WAIT numreplicas timeout_ms → block until N replicas ack (returns actual count).
  ⚠ AI-Completion incident: WAIT(2,2s) hardcoded → staging had 1 replica →
    blocked full 2s every call. Read connected_slaves from INFO; don't hardcode.
  replicas are READ-ONLY. Offload reads to them; writes to primary only.

FAILOVER (2-5s window)
  detection (down-after-ms, tune it) + majority-elected promotion (odd nodes!
  prevents split-brain) + client topology refresh.
  ElastiCache equip-redis: AutomaticFailoverEnabled + MultiAZ + 2 replicas/shard.

SENTINEL (cluster-mode DISABLED)   vs   CLUSTER MODE (enabled)
  one primary, all data, +replicas       data SHARDED across N primaries (16384 slots)
  scales reads only                      scales reads+writes+memory
  multi-key ops always work              multi-key ops need same slot (hash tags)
  simple                                 complex (slots, MOVED, reshard)
  choose by: does data fit ONE node?  yes→disabled  no→enabled

CLUSTER MODE INTERNALS
  slot = CRC16(key) % 16384, one shard per slot.  CLUSTER KEYSLOT <key> to check.
  multi-key op across slots → CROSSSLOT error. Fix: {hashTag} → hash only the braces.
    {company:c7}:profile & {company:c7}:settings → same slot → MGET works.
  MOVED <slot> <host> = "wrong shard, go there" → client MUST follow + refresh map.
  resharding MOVES slots → stale client map = "missing" keys (Equip Jan-2026 incident).
  pub/sub needs cluster-aware routing (sharded pub/sub) → UPI-3658 broke without it.

MINDTICKLE ELASTICACHE (NOT uniform — check per cluster/env)
  prod-US common: cluster ENABLED, redis 5.0.6, 2 replicas, failover (MultiAZ unset), NO snapshots
  prod-US equip:  cluster ENABLED, redis 6.2, 2 replicas, MultiAZ+failover, snapshots 3d
  prod-EU redis-cache-data: cluster DISABLED, 6.x, 1 replica, MultiAZ+failover, snapshots 1d
  integration:    1 replica  ← the WAIT-incident environment
  NO AOF. NO Global Datastore (each region standalone). eviction: volatile-lru.
  WAIT incident: coe-ml/tool-auth-service + ai-completion Wait(2,2s); staging had 1
    replica → full-2s stall; fix = env-aware WAIT → staging 2000ms → ~15ms.

INVESTIGATE
  INFO replication  → role, connected_slaves, master_link_status, lag
  INFO persistence  → rdb_last_save_time, aof_enabled
  CLUSTER INFO / CLUSTER NODES / CLUSTER KEYSLOT <key>
  WAIT n timeout    → how many replicas have your writes
```

---

*Next: Phase 5 — Performance & Failures. Pipelining, hot keys + big keys, eviction policies (all 8), and the slow commands to avoid — anchored to the INCP-520 memory incident, the volatile-lru default, and real latency numbers. Say `next`.*
