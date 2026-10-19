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
│  4.7  Multi-region & AZ    — cross-AZ cost, cross-region replication, and  │
│                             what a region failover loses                   │
│  4.8  Securing Redis       — protected mode, ACL users, TLS, the cluster   │
│                             bus, dangerous commands, and patching          │
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

**Verify:** on any Redis, run `redis-cli INFO cluster`. If `cluster_enabled:0`, you are on the one-primary topology, and every multi-key op works. If `cluster_enabled:1`, you are sharded, and multi-key ops need same-slot keys. Do not use `CLUSTER INFO` for this check. Without cluster mode it returns `ERR This instance has cluster support disabled` (local run, redis-server 8.10.1, 2026-10-19).

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

## 4.7 — Multi-region and AZ design (the cost of distance, and what a failover loses)

**Why this matters:** Section 4.6 showed that each region stands alone. This section says what that costs. Two numbers decide your bill and your risk. The first is cross-AZ transfer, which can cost more than the cluster itself. The second is the data your sessions, locks, rate limits and caches lose when a region fails over. If you keep state only in one region's Redis, a region failure loses it.

An **Availability Zone (AZ)** is one or more data centers inside one cloud Region. A **Region** has several AZs. Traffic inside one AZ is cheap. Traffic across two AZs in the same Region is billed. Traffic across two Regions is billed more.

Start with the money, because it is the part teams miss.

```
┌──────────────────────────────────────────────────────────────────────┐
│  AWS data transfer, us-east-1 price list, 2026-09-16                  │
│                                                                       │
│  same AZ            ──────────────────────────────►  $0.00 / GB      │
│  across AZs, same Region ─────────────────────────►  $0.01 / GB      │
│       (billed when it leaves AND when it enters: 1 GB costs $0.02)   │
│  across Regions (out of us-east-1, most targets) ──►  $0.02 / GB     │
│                                                                       │
│  Verified: AWS Price List, AWSDataTransfer, SKU PNUBVW4CPC8XA46W.    │
│  The "each direction" rule: Corey Quinn's 2019 test, 10 GB → 20c.    │
│  Not re-measured in 2026. The Valkey test below counts $0.01 once.   │
└──────────────────────────────────────────────────────────────────────┘
```

**Why a read from a replica in another AZ costs you.** Your client opens a connection to a replica to spread reads. If that replica sits in another AZ, every reply crosses an AZ boundary. The ElastiCache pricing page says there is no transfer charge for traffic in or out of the cache node itself. So replication between nodes in two AZs is free. That step is inferred from the page, not from a bill. The charge is on traffic between your application and the cache. So the fix is to read from a replica in the **same AZ** as the client.

The Valkey team measured both the latency and the bill of getting this wrong.

```
┌────────────────────────────┬──────────────┬──────────────────────────┐
│ Read from                  │ Latency      │ Monthly cost (their test)│
├────────────────────────────┼──────────────┼──────────────────────────┤
│ replica in the same AZ     │ ~300 µs      │  $1,088 (cluster only)   │
│ replica in another AZ      │ ~800 µs      │  $4,373 total            │
│   (cross-AZ transfer part) │              │  $3,285 of that is xAZ   │
├────────────────────────────┴──────────────┴──────────────────────────┤
│ AZ affinity cut the total from $4,373 to $1,088 (project blog, 2025).│
│ Test: 2 shards, each 1 primary + 2 replicas, m7g.xlarge.             │
│ Traffic: 250 MB/s of reads, half cross-AZ, at $0.01/GB counted ONCE. │
│ Billed in each direction, the transfer part would be about twice.    │
└───────────────────────────────────────────────────────────────────────┘
```

AZ-aware reads are a client feature, not a server one, and support differs by library. You must know which your client has.

- **go-redis v9.5.1** has `RouteByLatency` and `RouteRandomly`. It has no AZ option. (Verified: `osscluster.go`, no `zone` or `az` field.)
- **Lettuce** has `ReadFrom.subnet(...)`. You can approximate AZ-local reads with the CIDR of each AZ's subnet. (Verified: `ReadFrom.java`.)
- **Valkey GLIDE** has `AZ_AFFINITY`. It needs a client AZ setting that matches the AZ the server reports. (Verified: GLIDE read-strategy docs.)

For the server to report its AZ, Valkey 8.0 added the `availability-zone` config. The value shows in `INFO`, and since Valkey 8.1 in the `HELLO` reply. Redis 8.10.2 has no such setting. (Verified: `valkey.conf` at 9.1.2 line 541, `createSDSConfig("availability-zone", ...)` in Valkey `src/config.c:3357`.)

**Now cross-region.** Open-source Redis and Valkey have no built-in multi-primary across Regions. A cross-region replica is an ordinary `REPLICAOF` over a wide-area link, and you promote it and move clients yourself. This is inferred from the Redis replication docs, which describe only leader-follower replication. It was not checked against every Valkey page. Managed and commercial products add more:

- **ElastiCache Global Datastore.** One primary Region takes writes. Up to two secondary Regions take reads only. Replication is asynchronous. AWS does **not** fail over across Regions for you. You click **Promote to primary** on a secondary, and you move your application traffic. (Verified: AWS Global Datastore prerequisites page, "ElastiCache doesn't support autofailover from one AWS Region to another".) The AWS product page says a promotion takes less than 1 minute. That is a product page, not the docs. Writes not yet replicated at promotion are lost. That is inferred from the asynchronous replication, and was not tested on ElastiCache.
- **Redis Enterprise Active-Active.** Every Region has its own primary and takes writes. It merges concurrent writes with CRDTs, conflict-free replicated data types. A **CRDT** is a data type that merges writes from many sites and ends with the same value everywhere. It needs about double the memory. It is **not** in open-source Redis or Valkey. (Verified: redis.io Active-Active docs.)

Here is the part that decides your design. Replication across Regions is asynchronous, so a failover loses the writes that had not arrived yet. What that means is different for each kind of data.

```
┌─────────────────────────────────────────────────────────────────────┐
│  A region failover, and what each kind of data loses                 │
│                                                                       │
│  primary region ──async──► standby region                            │
│      │ writes W1..W100 replicated                                    │
│      │ writes W101..W125 NOT yet replicated when the region dies     │
│      ▼                                                               │
│   promote the standby: it has W1..W100 only                         │
│                                                                       │
│  sessions  → 25 users must log in again (their session was W101+)   │
│  locks     → a lock taken in W101+ is absent → two workers run it   │
│  counters  → rate-limit count falls back → users get extra quota    │
│  caches    → W101+ keys are misses → the standby's database is read │
└─────────────────────────────────────────────────────────────────────┘
```

Uber chose not to replicate its cache values across Regions. CacheFront serves over 40 million requests a second across Uber's Docstore instances. A cold cache in the other Region would add database load at a failover, and that would stop Uber from shrinking its database. Uber copies the **keys**, not the values, to the other Region. It tails the write stream, sends each key name across, and the other Region reads the row from its own database and fills its cache. (Verified: Uber engineering blog, 2024-02-15, a vendor source.)

Cloudflare shows the session case. In a 2020 incident its dashboard sessions lived "in a Redis cluster for the duration of that user's session". The post says the sessions "cannot currently be moved across the ocean without disruption". Moving API traffic to the second data center helped the API and hurt the dashboard, so Cloudflare moved authentication back. (Verified: Cloudflare blog, 2020-11-27.)

**WRONG** belief: a replica in another AZ or Region is free insurance, so add as many as you can.

```
# WRONG: read from any replica, wherever it is.
# Every cross-AZ reply is billed. The Valkey test, at $0.01 per GB
# counted once, paid $3,285 a month in cross-AZ transfer on a cluster
# that cost $1,088.
```

**RIGHT**: pin reads to the same AZ, and treat a region failover as data loss for anything kept only in one region's Redis.

```
# RIGHT (Valkey GLIDE): set the client's AZ and ask for same-AZ replicas.
#   client_az = "us-east-1a"; read_from = AZ_AFFINITY
# RIGHT for cross-region: copy keys, not values, to warm the standby
#   (Uber CacheFront), and accept that unreplicated writes are lost at
#   a failover. Size your "users log in again" count from the write rate.
```

**The sentence to remember:** cross-AZ reads are billed in each direction and can cost more than the cluster, so read from a same-AZ replica. A region failover keeps only what replicated, so sessions, locks, rate limits and caches lose the writes in the lag window.

**The trap:** keeping sessions or locks only in one region's Redis. At a region failover users log in again, and a lock taken just before the failure can be held by two workers in two regions at once.

**Try this now:**
```bash
# One region fails over to a standby. See each kind of data lose the
# writes that had not replicated, on two throwaway servers.
mkdir -p /tmp/p4a /tmp/p4b
redis-server --port 6583 --bind 127.0.0.1 -::1 --dir /tmp/p4a --save '' --appendonly no --daemonize yes
redis-server --port 0 --unixsocket /tmp/p4b/redis.sock --dir /tmp/p4b --save '' --appendonly no --daemonize yes
go run ./phase04_ha/region_failover   # 25 sessions lost, a lock a second worker can take
```

---

## 4.8 — Securing Redis (the trust model, ACL users, TLS, and the cluster bus)

**Why this matters:** Redis trusts the network. Both releases in this course's measurement window, 8.10.1 and 8.10.2, are security releases. Wiz counted about 60,000 internet-exposed Redis servers with no authentication in October 2025. That is a vendor count. This section gives the defaults that stop that, the per-service users that limit the damage of a stolen credential, and the two cluster-bus and TLS issues the 8.10 releases fixed.

Redis "is designed to be accessed by trusted clients inside trusted environments". So the first defence is the shipped defaults, and the second is one ACL user per service.

```
┌─────────────────────────────────────────────────────────────────────┐
│  The layers that stop an unauthorized command                        │
│                                                                       │
│   network   ──►  bind 127.0.0.1 -::1  (shipped config: loopback only)│
│   protected ──►  protected-mode yes, default user has no password    │
│      mode         → reject every non-loopback connection             │
│   auth      ──►  ACL user + password, or a TLS client certificate    │
│   ACL rules ──►  which commands, which keys, which channels          │
│   dangerous ──►  DEBUG, MODULE LOAD, CONFIG SET dir: off by default  │
└─────────────────────────────────────────────────────────────────────┘
```

**Protected mode** is the default that saves an exposed server. When `protected-mode yes` and the default user has no password, Redis rejects every connection that is not from loopback. It sends a `-DENIED` error that explains the fix. (Verified: `src/networking.c:1608-1637` at 8.10.2.) Two facts matter. First, protected mode turns **off** as soon as the default user gets a password, even a weak one. Second, since Redis 7.0 a non-default `bind` no longer turns it off. (Verified: `src/networking.c:1609`; Redis 7.0.0 release notes #9034.)

Protected mode is hard to show on loopback, because loopback is exactly what it allows. A remote client sees the `-DENIED` reply. On this course's build, a connection from the machine's LAN address was refused, and `rejected_connections` in `INFO stats` rose by one. (Local run, redis-server 8.10.1, 2026-10-19.)

**The real control is one ACL user per service.** An **ACL**, access control list, is a named user with a password. It has a set of allowed commands, and a set of allowed key and channel patterns. The default user ships as `+@all ~* &* on nopass`, which is every command on every key with no password. Any production deployment replaces it with per-service users and a locked-down default user.

A command belongs to one or more **categories**, such as `@read`, `@write`, `@dangerous`, `@admin` and `@scripting`. You grant and remove categories, and the rules apply left to right.

```
┌─────────────────────────────────────────────────────────────────────┐
│  A per-service user for the session service                          │
│                                                                       │
│  ACL SETUSER svc-sessions on >secret                                 │
│       resetkeys ~session:*        ← only keys that start session:    │
│       resetchannels               ← no pub/sub channels              │
│       -@all +@read +@write +@connection   ← a small command set      │
│       -@dangerous -@scripting     ← applied LAST, so they win         │
│                                                                       │
│  Result: GET/SET session:* work. FLUSHALL, KEYS, FUNCTION LOAD do    │
│  not. CONFIG and EVAL are in no plus category, so -@all removed them.│
└─────────────────────────────────────────────────────────────────────┘
```

Here is the trap that a key pattern alone does not cover. `FLUSHALL`, `FLUSHDB` and `SWAPDB` have no key, so the `~session:*` pattern never applies to them. A user with `~session:* +@read +@write` can still erase the whole server.

```
# WRONG: a key pattern, but no command limits.
#   ACL SETUSER svc on >pw resetkeys ~session:* -@all +@read +@write +@connection
#   ACL DRYRUN svc FLUSHALL  ->  OK      ← the service can wipe everything
```

```
# RIGHT: remove the dangerous and scripting categories AFTER the grants.
#   ACL SETUSER svc on >pw resetkeys ~session:* -@all +@read +@write \
#       +@connection -@dangerous -@scripting
#   ACL DRYRUN svc FLUSHALL  ->  no permissions to run the 'flushall' command
#   (verified on redis-server 8.10.1, 2026-10-19; FLUSHALL is in @dangerous)
```

Two more ACL facts you need. A key pattern limits **access**, not **visibility**: a `SCAN` as `svc-sessions` still lists key names outside the pattern, although a `GET` on them is refused. And `ACL LOG` records every refusal with its reason, which is `command`, `key`, `channel`, `auth` or `tls-cert`, plus the user and the command. (Verified: `src/acl.c:3167-3182`; local run.)

Removing `@scripting` from a user is worth its own line. This course's security research read 29 Redis CVEs from 2023 to 2026. 8 were Lua engine bugs. One is CVE-2025-49844, a use-after-free scored 10.0 that needs an authenticated user to send a Lua script. (Verified: GitHub advisories API, and the Wiz blog of 2025-10-06, a vendor source.) `EVAL` is only in `@scripting`, so `-@all +@read +@write` already refuses it. The gap is `FUNCTION LOAD` and `FUNCTION FLUSH`. They are in `@write` as well as `@scripting`, so `+@write` grants them. `FUNCTION LOAD` runs the library's Lua code when it loads it. Only `-@scripting` removes these commands. (Verified: `ACL DRYRUN` and a `FUNCTION LOAD` on redis-server 8.10.1, 2026-10-19.)

**TLS** encrypts the client connection and can authenticate the client with a certificate. It is off by default and needs a build with TLS. With `tls-auth-clients-user CN` (Redis 8.6 and later), the certificate's Common Name picks the ACL user. A Common Name with no matching user leaves the client on the **default** user, and `ACL LOG` gets a `tls-cert` entry. If the default user is `nopass`, that client has every permission. If the default user has a password, the client must still send `AUTH`. (Verified: `src/networking.c:102-108` and `:1641-1655` at 8.10.2; E17.) The 8.10.1 release fixed a bypass here: a NUL byte inside the Common Name was truncated, so `admin\0innocent` logged in as `admin`. (Verified: 8.10.2 release notes, 8.10.1 section; `src/tls.c:655-680`.)

**The cluster bus** is the second TCP port each cluster node opens, at the client port plus 10000. It has no authentication of its own unless `tls-cluster yes`. A `MEET` packet from any host that can reach the bus port adds that host as a node, and its gossip is trusted. Redis 8.10.2 fixed this with a startup warning and a new opt-in setting.

```
┌─────────────────────────────────────────────────────────────────────┐
│  cluster-bus-port-protected-mode, Redis 8.10.2, default: no          │
│                                                                       │
│   no  (default) ──► node starts, logs a warning if the bus is not TLS│
│   yes           ──► node refuses to start unless tls-cluster yes     │
│                                                                       │
│   The PR proposed default "yes" and called it a breaking change.     │
│   The shipped default is "no" (config.c:3434). Valkey 9.1.2 has no   │
│   such option, only bus packet length validation (#3972).            │
└─────────────────────────────────────────────────────────────────────┘
```

A local run showed the risk directly. A two-node cluster ran with no bus TLS. A third node sent `CLUSTER MEET` to it, and `cluster_known_nodes` rose from 2 to 3. After that rogue node replicated the data and ran `CLUSTER FAILOVER TAKEOVER`, it owned all 16384 slots, and the original primary became its replica. The one thing that stopped the rogue from reading data was a **client** password on the primary, which blocked its replication AUTH. (Local run, redis-server 8.10.1, loopback ports 6583 to 6588, 2026-10-19.) The cluster bus itself did the join with no credential at all. The password did not stop the takeover. In a second run with the password set, the rogue still took all 16384 slots, and the old primary became its replica. Clients that asked the old primary got `MOVED` to the rogue, which held no keys. (Reviewer rerun, redis-server 8.10.1, ports 6595 to 6597, 2026-10-19.)

**Dangerous commands** are off by default since Redis 7.0. `enable-debug-command`, `enable-module-command` and `enable-protected-configs` all default to `no`. So `DEBUG`, `MODULE LOAD` and `CONFIG SET dir` are refused even for the default user. (Verified: `src/config.c:3496-3498`; local run.) This blocks the two classic takeover paths: point the save directory at `/etc/cron.d`, or load a malicious module. The old `rename-command` is **deprecated**. Use ACLs instead, because they are per user, change at runtime, and log their denials. (Verified: `redis.conf:1160-1183`.)

**Patch on the security releases.** The upgrade note `SECURITY` means the release has security fixes. It does not rank them. ElastiCache applies critical security updates in the maintenance window and offers the rest as self-service. MemoryDB applies mandatory updates you cannot skip. (Verified: 8.10.2 release notes; AWS self-service and MemoryDB docs.)

**The sentence to remember:** Redis trusts the network, so a real deployment needs per-service ACL users with `-@dangerous -@scripting`. It also needs TLS on the client port, `tls-cluster` on the bus, and prompt patching of the security releases.

**The trap:** a key pattern with no command limits. The user still runs `FLUSHALL`, `FLUSHDB` and `SWAPDB`, because those commands have no key for the pattern to apply to.

**Try this now:**
```bash
# A per-service user that cannot FLUSHALL or CONFIG, and ACL LOG showing
# the denial. Needs a throwaway server on 6583.
redis-server --port 6583 --bind 127.0.0.1 -::1 --dir /tmp/p4acl --save '' --appendonly no --daemonize yes
go run ./phase04_ha/acl_service_user        # compares the WRONG and RIGHT rule sets
go run ./phase04_ha/acl_service_user -break # runs FLUSHALL as the WRONG user
```

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

The exercises below are for sections 4.7 and 4.8. They run against a throwaway server on port 6583 and a Unix socket, never on 6379. Every command below was executed on 2026-10-19, on redis-server 8.10.1, an x86_64 Homebrew build under Rosetta 2 on an Apple M4 Pro. E16 is a written exercise. Start a server with:
```bash
mkdir -p /tmp/p4lab
redis-server --port 6583 --bind 127.0.0.1 -::1 --dir /tmp/p4lab --save '' --appendonly no --daemonize yes
```

- [ ] **E13 (break-it, local). A per-service user that cannot wipe the server.**
  - Run: `go run ./phase04_ha/acl_service_user` then `go run ./phase04_ha/acl_service_user -break`
  - Expected: the WRONG user (`~session:*` with no `-@dangerous`) runs `FLUSHALL`, and `-break` shows `DBSIZE before 3 ... FLUSHALL as p4-naive -> OK. DBSIZE after 0`. The RIGHT user gets `no permissions to run the 'flushall' command`. The model agrees with `ACL DRYRUN` on all 32 checks.
  - If it fails: check the server is on 6583 and empty. `-break` refuses to run if the server holds more than 3 keys.
  - Teaches: a key pattern does not limit keyless commands, so you need `-@dangerous`.

- [ ] **E14 (offline). The ACL rule model self-test.**
  - Run: `go run ./phase04_ha/acl_service_user -self-test`
  - Expected: `all checks passed`. Remove `-@dangerous` from `rightRules` and re-run: 5 checks fail, because FLUSHALL, FLUSHDB, SWAPDB, KEYS and CLIENT KILL become allowed. Remove `-@scripting` instead: 2 checks fail, because FUNCTION LOAD and FUNCTION FLUSH become allowed.
  - Teaches: the rules apply left to right, and the order of the minus rules decides the result.

- [ ] **E15 (break-it, local). A region failover loses the unreplicated writes.**
  - Run: `go run ./phase04_ha/region_failover`, after starting a second server on a socket:
  ```bash
  mkdir -p /tmp/p4b
  redis-server --port 0 --unixsocket /tmp/p4b/redis.sock --dir /tmp/p4b --save '' --appendonly no --daemonize yes
  go run ./phase04_ha/region_failover
  ```
  - Expected: the standby holds 100 of the primary's 125 sessions, so 25 users log in again. The counter falls from 125 to 100. The lock taken after the cut is absent, so `SET ... NX` by worker-B returns `true`. The standby matches the model on every row.
  - If it fails: check that `/tmp/p4b/redis.sock` exists and the primary is on 6583. The run takes about 6 seconds, mostly the full sync after the 5-second diskless delay.
  - Teaches: asynchronous cross-region replication loses the lag window at a failover, differently for each kind of data.

- [ ] **E16 (written). The cross-AZ bill.**
  - Reason: your service makes 2 TB of cross-AZ reads a month at $0.01 per GB in each direction. Compute the monthly transfer cost, and the cost if you pin reads to a same-AZ replica. Compare with the Valkey test's $3,285 against $1,088.
  - Expected: 2 TB = 2,048 GB. Each GB is billed $0.01 when it leaves one AZ and $0.01 when it enters the other, so $0.02 a GB. 2,048 × $0.02 = about $41 a month. A same-AZ read costs $0. The Valkey test counted $0.01 once and got $3,285 against a $1,088 cluster. Billed in each direction, its transfer part would be about twice that.
  - Teaches: cross-AZ transfer can cost more than the cluster, and AZ affinity removes it.

- [ ] **E17 (live, TLS). A certificate mapped to an ACL user, and TLS replication.**
  - Run: `bash ./phase04_ha/tls_lab.sh`
  - Expected: a plain TCP client is reset. A client certificate with `CN=p4-sessions` becomes the default user until that ACL user exists, then becomes `p4-sessions`. `CONFIG SET tls-cert-file` serves a new certificate without a restart (the served serial changes). A replica reaches the TLS-only primary only after `CONFIG SET tls-replication yes`.
  - If it fails: this needs a redis-server built with TLS. Check `redis-cli --help | grep -i tls` lists `--tls`, and `otool -L $(which redis-server)` lists `libssl`. This course's build has TLS. A build without it cannot run this exercise.
  - Teaches: TLS client-certificate authentication, the CN-to-user mapping and its default-user fallback, certificate rotation, and `tls-replication`.

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

**Q8.** (4.7) Your agent platform keeps session state and a lock per run in one region's Redis, with an async read-only standby in a second region. The region fails. In the last second before it died the primary acknowledged 40 session writes and 1 run lock that had not replicated. (a) What do those 40 users see after you promote the standby? (b) The run lock was one of the 40. What can now happen to that run, and why? (c) Your cross-AZ read bill is $3,000 a month on a $1,000 cluster. Which client change removes most of it, and why does it work?

**Q9.** (4.8) A teammate creates one Redis user for the cache service: `ACL SETUSER cache on >pw resetkeys ~cache:* -@all +@read +@write +@connection`. (a) Show the exact command this user can still run that erases every key on the server, and explain why the `~cache:*` pattern does not stop it. (b) Give the one rule you add to fix it, and say where in the rule list it must go. (c) A separate cluster runs with no `tls-cluster`. An attacker can reach the bus port. What single `CLUSTER` command joins their host, and what Redis 8.10.2 setting would have refused to start the node?

<details>
<summary>Answer sketches</summary>

8. (a) The 40 sessions were not on the standby, so those users are logged out and must sign in again. (b) The lock was not replicated, so the standby does not have it. A second worker in the new region runs `SET lock NX`, gets it, and runs the same job the first worker still thinks it holds. Two workers run one run. (c) Pin reads to a replica in the same AZ. Cross-AZ transfer is billed in each direction, and same-AZ transfer is free, so a same-AZ read removes the cross-AZ part. The Valkey test cut $4,373 to $1,088 this way.
9. (a) `FLUSHALL` (also `FLUSHDB`, `SWAPDB`). These commands take no key, so the `~cache:*` key pattern never applies to them. The user has `+@write`, and FLUSHALL is a write command, so it is allowed. (b) Add `-@dangerous` after the plus rules. It removes FLUSHALL, FLUSHDB, SWAPDB, KEYS, SORT, MIGRATE, RESTORE and CLIENT KILL, which the plus rules had granted. Add `-@scripting` too, because `+@write` also grants FUNCTION LOAD. Rules apply left to right, so a minus rule placed before `+@write` would be undone. (c) `CLUSTER MEET <host> <port>` adds the attacker's host as a node, and its gossip is trusted. `cluster-bus-port-protected-mode yes` (Redis 8.10.2) makes the node refuse to start without `tls-cluster`.

</details>

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

**Multi-region and AZ (4.7):**
- 📄 [ElastiCache pricing](https://aws.amazon.com/elasticache/pricing/) — no charge for traffic in or out of the node itself, and application traffic across an AZ is billed. The Global Datastore example charges $0.02/GiB out of the primary Region.
- 📄 [Valkey blog: reducing latency and the cloud bill with AZ affinity](https://valkey.io/blog/az-affinity-strategy/) — the 300 µs vs 800 µs read, and the $4,373 → $1,088 cut. Read for the cost arithmetic. (Vendor source.)
- 📄 [ElastiCache Global Datastore — AWS docs](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Redis-Global-Datastore.html) — one writable primary Region, read-only secondaries, asynchronous replication, promotion for disaster recovery.
- 📄 [Global Datastore prerequisites and limitations — AWS docs](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Redis-Global-Datastores-Getting-Started.html) — up to two secondary Regions, and no autofailover across Regions. Read the promotion bullet.
- 📄 [Uber: serving 40M reads/s with an integrated cache](https://www.uber.com/en-GB/blog/how-uber-serves-over-40-million-reads-per-second-using-an-integrated-cache/) — why they copy keys, not values, across Regions. Read §"Cache warming". (Vendor source.)
- 📄 [Cloudflare: a Byzantine failure in the real world](https://blog.cloudflare.com/a-byzantine-failure-in-the-real-world/) — dashboard sessions in Redis that could not move Regions. The session-failover case.

**Securing Redis (4.8):**
- 📄 [Redis security — official docs](https://redis.io/docs/latest/operate/oss_and_stack/management/security/) — the trust model, protected mode, and the code-security notes on CONFIG and dir.
- 📄 [Redis ACL — official docs](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/) — users, categories, key and channel patterns, selectors, and ACL LOG. Read §"Command categories" and §"Key permissions".
- 📄 [Redis TLS — official docs](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/) — tls-auth-clients, tls-replication, tls-cluster, and certificate files.
- 📄 [Wiz: the CVE-2025-49844 Lua RCE](https://www.wiz.io/blog/wiz-research-redis-rce-cve-2025-49844) — why removing @scripting reduces risk, and the exposed-instance counts. (Vendor source.)

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

MULTI-REGION & AZ (4.7)
  cross-AZ transfer billed EACH direction: ~$0.01/GB per direction (us-east-1).
    same AZ = $0.00. cross-Region out of us-east-1 ≈ $0.02/GB.
  read from a SAME-AZ replica (AZ affinity): Valkey test 800µs→300µs, $4,373→$1,088.
    go-redis v9.5.1: RouteByLatency only (no AZ). Lettuce: ReadFrom.subnet().
    Valkey GLIDE: AZ_AFFINITY + client AZ. server AZ: Valkey availability-zone (8.0).
  cross-region: no multi-primary in open source. Global Datastore = 1 writable
    Region, manual promote, no autofailover. Active-Active (CRDT) = Redis Enterprise.
  region failover loses the unreplicated window:
    sessions → re-login. locks → two holders. counters → extra quota. caches → cold.
  Uber: copy KEYS not values to warm a standby Region.

SECURITY (4.8)
  trust model: Redis trusts the network. protected-mode yes + default nopass
    → reject non-loopback. A password on default turns protected mode OFF.
  one ACL user per service: -@all +@read +@write +@connection -@dangerous -@scripting
    key pattern ~x:* does NOT limit FLUSHALL/FLUSHDB/SWAPDB (no key) → need -@dangerous.
    +@write grants FUNCTION LOAD/FLUSH (Lua) → -@scripting removes them. EVAL is not in @write.
    SCAN still LISTS names outside the pattern (access ≠ visibility). ACL LOG logs denials.
  TLS: off by default. tls-auth-clients yes (mTLS). tls-auth-clients-user CN → ACL user
    (no match → stays DEFAULT user + ACL LOG tls-cert). tls-replication / tls-cluster separate, default no.
  cluster bus: no auth without tls-cluster. MEET from any host joins it.
    a client password stops the rogue's replication, NOT its slot takeover.
    cluster-bus-port-protected-mode (8.10.2, default NO) → refuse to start without tls-cluster.
  dangerous OFF by default (7.0+): DEBUG, MODULE LOAD, CONFIG SET dir. rename-command deprecated.
  8.10.1 and 8.10.2 are SECURITY releases. 8/29 recent CVEs are Lua → drop @scripting.

INVESTIGATE
  INFO replication  → role, connected_slaves, master_link_status, lag
  INFO persistence  → rdb_last_save_time, aof_enabled
  CLUSTER INFO / CLUSTER NODES / CLUSTER KEYSLOT <key>
  WAIT n timeout    → how many replicas have your writes
  ACL LIST / ACL DRYRUN <user> <cmd> / ACL LOG   → what each user may do, and denials
  CONFIG GET availability-zone (Valkey) / tls-* / cluster-bus-port-protected-mode
```

---

*Next: Phase 5 — Performance & Failures. Pipelining, hot keys + big keys, eviction policies (all 8), and the slow commands to avoid — anchored to the INCP-520 memory incident, the volatile-lru default, and real latency numbers. Say `next`.*
