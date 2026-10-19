# Phase 3 — Distributed Locking (the phase where "it works" and "it's correct" diverge)

This is the phase that separates engineers who *use* Redis from engineers who can be trusted to protect money, or a customer's data, with it. Because a distributed lock is the one Redis pattern where "it worked in testing" tells you almost nothing — the failure modes only appear under a GC pause, a network blip, or a worker that runs 50ms too long, and when they appear they're silent: two workers both "hold" the lock, both act, and nobody sees an error. Just a duplicate email, a double-generated share link, or a corrupted counter.

Here's the uncomfortable truth this phase builds to, and it comes straight from a famous argument between Redis's creator and one of the field's most respected distributed-systems researchers: **a Redis lock cannot, by itself, provide correctness.** It can provide *efficiency* — "probably don't do this expensive thing twice" — which is genuinely useful and covers most real needs. But if a lock failing would corrupt data or double-charge a customer, Redis alone is not enough, and no amount of `SET NX EX` cleverness changes that. You need something at the *resource* — a fencing token — and Compass confirms **zero Mindtickle services have it.**

That's not a reason to panic; it's a reason to *know which of your locks are efficiency locks (fine) and which are pretending to be correctness locks (a latent incident)*. By the end of this phase you'll be able to look at any of Mindtickle's eight real Redis locks and say exactly what it protects against, what it doesn't, and whether that gap matters. You'll have reproduced the plain-`DEL`-deletes-someone-else's-lock bug, watched two workers hold the "same" lock because work outran the lease, and seen a fencing token reject the stale writer.

Time: 5–7 days. Do not rush this one. The exercises are where the danger becomes visceral.

## What we cover in Phase 3:
```
┌──────────────────────────────────────────────────────────────────────────┐
│  3.1  Efficiency vs correctness — the ONE question to ask before locking  │
│  3.2  The minimum viable lock   — SET key <token> NX PX <ttl>, flag by flag│
│  3.3  The unlock problem        — plain DEL vs random-value + Lua CAS      │
│  3.4  The lease problem         — work > TTL = two holders (watchdogs)     │
│  3.5  Fencing tokens            — the fix a lock ALONE cannot give         │
│  3.6  The Redlock debate        — Kleppmann vs antirez, and your takeaway  │
│  3.7  Mindtickle's 8 locks      — the audit: redsync vs SETNX, safe vs not │
│  3.8  Lua scripts, Functions    — script cache, NOSCRIPT, BUSY, FCALL      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3.1 — Efficiency vs correctness (the question to ask before you write a single line)

**Why this matters:** almost every distributed-locking mistake starts by skipping this question. Martin Kleppmann's framing (from the essay that started the Redlock debate) is the sharpest tool you have here, and it should be the first thing you reach for whenever someone says "let's add a lock."

There are exactly two reasons to take a lock:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  EFFICIENCY LOCK                     │  CORRECTNESS LOCK                  │
│  "don't do the same work twice"      │  "two actors must NEVER both act"  │
│                                      │                                    │
│  cost of failure: minor              │  cost of failure: severe           │
│   - a duplicate email                │   - data corruption                │
│   - a wasted LLM call ($0.02)        │   - double-charged customer        │
│   - a recomputed cache entry         │   - two conflicting writes to      │
│                                      │     the same record                │
│                                      │                                    │
│  Redis SET NX EX is PERFECT here.    │  Redis alone is NOT enough.        │
│  A rare double-run is acceptable.    │  You need fencing at the resource, │
│                                      │  or a consensus system (ZooKeeper/  │
│                                      │  etcd), or an idempotent write.    │
└─────────────────────────────────────────────────────────────────────────┘
```

Kleppmann's verdict on Redlock — the multi-master Redis locking algorithm — is that it's "neither fish nor fowl": too heavyweight for the efficiency case (a single Redis `SET NX EX` already does that job), and *not safe enough* for the correctness case (it can't prevent a paused client from acting after its lease expired — 3.4). The practical consequence for you: **decide which kind of lock you're writing before you write it**, because the answer changes everything downstream.

If it's an efficiency lock: a single-instance `SET NX EX` is the right, cheap, simple answer. Ship it, document that a rare double-execution is possible, move on. This is *most* locks, and it's exactly what most of Mindtickle's locks are (3.7) — deduping invitation emails, share-link generation, session init. A duplicate invite email is annoying, not catastrophic. Redis is the correct tool.

If it's a correctness lock: stop. A Redis lock will *reduce* the probability of a double-act but cannot eliminate it, and "reduced probability" is not "correctness." You need one of: (a) a **fencing token** the resource checks (3.5), (b) an **idempotent** write so a double-act is harmless, or (c) a real consensus system. Most of the time the pragmatic answer is (b) — make the operation idempotent — because it's robust to *all* the failure modes, not just the ones your lock anticipated.

**The sentence to remember:** before writing a lock, ask "efficiency or correctness?" — efficiency locks are a job Redis `SET NX EX` does perfectly; correctness locks need a fencing token or an idempotent write, because a lock alone can't guarantee two actors never both act.

**The trap:** writing an efficiency lock and *believing* it's a correctness guarantee. The code looks identical; the difference is only visible during a GC pause or a lease overrun — i.e., in production, at 3am.

**Verify your understanding:** ai-tutor's `invite_email_lock` dedups invitation emails. Efficiency or correctness? (Efficiency — a duplicate email is a paper cut. So its plain-`DEL` unlock and 60s TTL, while technically racy, are an *acceptable* engineering choice. Contrast with a lock guarding a payment.)

---

## 3.2 — The minimum viable lock (SET NX EX, flag by flag)

**Why this matters:** the single-instance Redis lock is three flags, and every one of them is load-bearing. Get any one wrong and you have a lock that either doesn't exclude, holds forever, or can't be released safely. This is the primitive under `redsync`, under every hand-rolled Mindtickle lock, and under your future ones.

The acquire is one command:

```
   SET  lock:resource   <random-token>   NX   PX 30000
        └──────┬──────┘  └──────┬──────┘  │    └───┬────┘
          the key        the OWNER token   │    auto-expire
       (what you lock)  (unique to THIS    │    after 30s
                         holder — 3.3)      │
                                      only set if
                                      ABSENT (mutual
                                      exclusion)
```

Take the three ideas one at a time, because each defends against a specific failure:

**`NX` — only set if absent.** This is the mutual exclusion itself. Because Redis is single-threaded (Phase 0.1), `SET ... NX` is atomic: of N concurrent callers, exactly one succeeds and gets `OK`; the rest get nil. No locking, no race — the single thread *is* the critical section. This is why `SETNX` is a valid lock primitive at all.

**`PX <ttl>` (or `EX`) — auto-expiry.** Without a TTL, a holder that crashes (pod OOM-killed, `kill -9`, network partition) holds the lock **forever** — a permanent deadlock that needs manual intervention. The TTL is the crash safety net: worst case, the lock frees itself after `ttl`. **A lock without a TTL is a latent outage.** (Note the failure mode this trades *into*, though: if the TTL is shorter than the work, the lock frees while you're still using it — 3.4. TTL choice is a real tension, not a formality.)

**`<random-token>` — the owner fingerprint.** This is the one people skip, and it's what makes *release* safe (3.3). The value must be unique to this specific acquisition — 16+ bytes from a CSPRNG, or a UUID. Not `"1"`, not `"locked"`, not a constant. Without it you cannot tell "my lock" from "someone else's lock that happens to be here now."

Putting acquire + safe release together (this is the whole correct single-instance lock):

```go
// ACQUIRE
token := random16Bytes()
ok, _ := rdb.SetNX(ctx, key, token, ttl).Result()   // SET key token NX PX ttl
if !ok { /* someone else holds it */ }

// ... do the protected work (must finish well within ttl) ...

// RELEASE — atomic compare-and-delete (3.3)
releaseScript.Run(ctx, rdb, []string{key}, token)    // DEL only if value == my token
```

**The sentence to remember:** the minimum viable lock is `SET key <random-token> NX PX <ttl>` — `NX` excludes, `PX` prevents deadlock-on-crash, and the random token makes release safe; drop any one and the lock is broken in a specific way.

**The trap:** a lock value of `"1"` or `"locked"`. It works in the demo and is a release bug in production (3.3). ai-tutor uses `"1"`, external-sharing-service uses `"locked"`, asset-hub-analytics uses `"100"` — all three are vulnerable.

**Try this now:**
```bash
go run ./phase03_locking/safe_lock
# A acquires, B denied, A releases; A's stale token can't release B's later lock.
```

---

## 3.3 — The unlock problem (why plain DEL is a bug)

**Why this matters:** this is the most common distributed-locking bug in the wild, it's in *four* of Mindtickle's eight locks, and it's completely invisible until a lock overruns its TTL. The fix is five lines of Lua. Understanding *exactly* how plain `DEL` corrupts is the thing to internalize.

Here's the race, step by step. Worker A uses a plain `DEL` to unlock (no ownership check):

```
┌────────────────────────────────────────────────────────────────────────┐
│  t=0.0  A: SET lock "1" NX PX 2000   → OK. A starts work (will take 3s)  │
│  t=2.0  lock AUTO-EXPIRES (A's work isn't done; A doesn't know)          │
│  t=2.0  B: SET lock "1" NX PX 2000   → OK! (key was free). B starts work │
│  t=3.0  A finishes, calls DEL lock   → deletes B's lock!! (A never       │
│         checked whose lock it was — the value "1" is identical)          │
│  t=3.0  C: SET lock "1" NX PX 2000   → OK. Now B AND C both "hold" it.   │
│                                                                          │
│  The lock guaranteed NOTHING. Three "holders" touched it; two overlap.  │
└────────────────────────────────────────────────────────────────────────┘
```

The root cause: with a constant value, `DEL` cannot answer "is this still *my* lock?" A's `DEL` at t=3 deletes whatever is there — which is now B's lock. The fix is the random token from 3.2 plus an **atomic compare-and-delete** on release. It must be atomic (one Lua script), because a naive "GET; if mine, DEL" has the same race *between* the GET and the DEL:

```lua
-- release: delete the key ONLY IF it still holds my token. Atomically.
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0    -- not my lock anymore — someone else holds it, do NOT delete
end
```

Because Lua runs atomically on the single command thread (Phase 0.1), nothing can slip between the `GET` and the `DEL`. Now A's stale release at t=3 finds the value is B's token, not A's, and refuses — B's lock survives. This is exactly what `redsync` does internally, and it's why the `redsync`-based Mindtickle locks are structurally safer than the hand-rolled `SETNX` ones (3.7). Section 3.8 shows what happens to this script when a restart or a failover empties the script cache.

**Note this does *not* fix everything.** Compare-and-delete stops A from deleting B's lock. It does *not* stop the deeper problem that A and B both did work at overlapping times (A's work ran past its lease). That's the lease problem, and no unlock cleverness fixes it — 3.4.

**The sentence to remember:** unlock must be an atomic compare-and-delete (random token + Lua `GET==mine then DEL`) — a plain `DEL` deletes whatever's there, so after your lease expires you'll delete the *next* holder's lock and shatter mutual exclusion.

**The trap:** "GET then DEL" in application code instead of one Lua script. The gap between the two commands is the exact race you were trying to fix.

**Try this now:**
```bash
go run ./phase03_locking/unsafe_unlock
# Watch A delete B's lock at t=3, then C acquire → B and C both hold it.
```

---

## 3.4 — The lease problem (work that outlives the TTL)

**Why this matters:** this is the failure that survives a *perfectly* implemented lock — random token, atomic compare-and-delete, all of it — and it's the crux of the Redlock debate. If your protected work can ever take longer than the lock's TTL, two workers can hold the lock at the same time, and there is nothing the lock can do about it.

The mechanism is brutally simple:

```
┌────────────────────────────────────────────────────────────────────────┐
│  ttl = 5s. Worker A's work normally takes 2s. One day A hits a          │
│  stop-the-world GC pause / CPU steal / slow downstream for 4s:          │
│                                                                          │
│  t=0   A acquires (ttl=5s), starts work                                 │
│  t=1   A is 1s into work... then a GC pause freezes A for 6s            │
│  t=5   A's lease EXPIRES (A is frozen, has no idea)                     │
│  t=5   B acquires the free lock, starts ITS work                        │
│  t=7   A un-freezes, resumes as if nothing happened, WRITES             │
│  t=7   B is also working → BOTH act on the resource. Invariant broken.  │
│                                                                          │
│  A did everything right. The lock was correct. The ASSUMPTION           │
│  "work always finishes within ttl" is what failed.                      │
└────────────────────────────────────────────────────────────────────────┘
```

You cannot fully solve this with the lock, only mitigate it:

1. **Size the TTL generously** relative to worst-case work — but too long means a crashed holder blocks everyone for that long. It's a genuine tension: short TTL → lease-overrun risk; long TTL → slow crash recovery.
2. **Lock extension / watchdog:** a background goroutine renews the lease (re-`PEXPIRE` while you still own it) as long as work continues. `redsync` supports `Extend()`. This shrinks but never closes the window — the watchdog itself can be paused. The renewal is a Lua script too, so it needs the `NOSCRIPT` fallback from 3.8.
3. **Make the protected write idempotent** — then a double-act is harmless. Often the best real answer.
4. **Fencing tokens (3.5)** — the only thing that actually *prevents* the late writer from corrupting the resource.

The reason this matters so much: it means **a lock with a TTL is not a correctness guarantee**, full stop. Mindtickle's locks all rely on exactly this assumption (work < TTL), with TTLs from **500ms** (copilot-chat-agent session init — alarmingly short) to **180s** (content-center-service content sync). Every one is a bet that work finishes before the lease. For efficiency locks that bet is fine. For anything that must be correct, it isn't.

**The sentence to remember:** a correct lock with a TTL is still unsafe if work can exceed the lease — a GC pause past the TTL gives you two live holders, and only a generous TTL + watchdog + idempotency + fencing narrows or closes that gap.

**The trap:** a short TTL "to recover fast from crashes" on work with variable latency (an LLM call, a slow gRPC). copilot-chat-agent's 500ms session-init lock is one slow dependency away from routine lease overruns.

**Try this now:**
```bash
go run ./phase03_locking/lease_expiry_race -ttl 500ms -work 900ms
# Invariant expected: counter==1. Actual: counter==2. The lock was correct; work outran it.
```

---

## 3.5 — Fencing tokens (the fix a lock alone cannot give)

**Why this matters:** this is Kleppmann's central prescription and the thing that turns "probably safe" into "actually safe." It's also the thing almost nobody implements — Compass confirms **zero Mindtickle services use it** — because it requires cooperation from the *resource*, not just the lock. Understanding it is what lets you reason correctly about which locks are truly safe.

The idea: every time the lock is acquired, issue a **monotonically increasing number** — a fencing token. In Redis that's trivial: `INCR` a counter on acquire. The holder passes that token to the resource on every write, and **the resource rejects any write whose token is lower than the highest it has already accepted.**

```
┌────────────────────────────────────────────────────────────────────────┐
│  fencing counter (Redis INCR)                                          │
│                                                                          │
│  A acquires → token 33 → then STALLS (GC pause), lease expires          │
│  B acquires → token 34 → writes to resource with token 34               │
│       resource: "highest seen = 34, accept" ✓                          │
│  A wakes → writes to resource with its OLD token 33                     │
│       resource: "33 < 34, REJECT" ✗   ← the stale writer is fenced off  │
│                                                                          │
│  The RESOURCE, not the lock, enforces safety. This is the ONLY thing    │
│  that stops the 3.4 lease-overrun from corrupting data.                 │
└────────────────────────────────────────────────────────────────────────┘
```

The catch — and why it's rare — is in the last line: **the resource must actively check the token.** Your database, your S3 write, your API call has to understand fencing tokens and reject stale ones. That's easy if the resource is a row you control (`UPDATE ... WHERE fence_token < :token`), hard if it's a third-party API or a physical action, and impossible if the resource can't do a conditional write. This is exactly antirez's counterargument (3.6): if your resource can already reject out-of-order writes, you arguably didn't need a strong lock in the first place — you could use a check-and-set on the resource's own version.

For your purposes at Mindtickle: none of the eight locks fence. That's *acceptable* for the efficiency locks (a rare duplicate is tolerable). It would *not* be acceptable if any of them were guarding a correctness-critical, non-idempotent write — and the audit in 3.7 is where you check that none secretly are.

**The sentence to remember:** a fencing token (monotonic `INCR` on acquire, checked and enforced by the resource) is the only mechanism that actually prevents a lease-overrun double-act — but it only works if the *resource* rejects stale tokens, which is why almost no one, including Mindtickle, implements it.

**The trap:** generating a fencing token and then not checking it at the resource. That's theater — the token does nothing unless the write path enforces monotonicity.

**Try this now:**
```bash
go run ./phase03_locking/fencing_tokens
# token 34 accepted, stale token 33 rejected → B's write wins, A's is fenced off.
```

---

## 3.6 — The Redlock debate (Kleppmann vs antirez — and what you should actually do)

**Why this matters:** this is the most famous argument in the practical distributed-systems world, both participants are right about different things, and the *synthesis* is a genuinely useful decision procedure. You'll be asked about it in senior interviews and, more importantly, you'll use its conclusion every time you reach for a lock.

The setup: **Redlock** is antirez's algorithm for locking across N *independent* Redis masters (acquire on a majority, so no single node's failure loses the lock). Kleppmann published a critique; antirez rebutted. The disagreement, distilled:

```
┌───────────────────────────────────────────────────────────────────────────┐
│  KLEPPMANN says                          │  ANTIREZ replies                 │
│                                          │                                  │
│  Redlock can't provide correctness:      │  Redlock isn't meant for         │
│  a GC pause past the lease → two         │  problems that need a linearizable│
│  holders. Needs FENCING TOKENS           │  store anyway. Its RANDOM token   │
│  (monotonic) — Redlock's random          │  + check-and-set on the resource  │
│  token can't be ordered.                 │  achieves the same, more          │
│                                          │  practically than a monotone int. │
│                                          │                                  │
│  Its safety leans on timing/clock         │  It assumes only a semi-synchronous│
│  assumptions (bounded pause, no clock    │  model (relative time, ~10% error),│
│  jump) that don't hold in real systems.  │  not bounded absolute time; use    │
│                                          │  monotonic clock API (conceded).   │
│                                          │                                  │
│  For correctness use ZooKeeper/etcd      │  Redlock moves people OFF unsafe   │
│  + fencing. For efficiency, single-node  │  single-instance/master-slave     │
│  Redis is fine (just say it's approximate)│  locking, cheaply. That's the goal.│
└───────────────────────────────────────────────────────────────────────────┘
```

Both are correct on their own terms. Kleppmann is right that *no* timeout-based lock — Redlock included — can guarantee correctness against unbounded pauses without fencing. antirez is right that (a) the fencing requirement often implies you didn't need the heavyweight lock anyway, and (b) Redlock is a real improvement over the naive single-instance-with-failover locking it replaced.

**The synthesis — your actual decision procedure:**

1. **Efficiency lock?** → single-instance `SET NX EX` with random token + Lua CAS unlock. Don't use Redlock; it's needless complexity. Document that a rare double-run is possible. *(This is the right call for almost every Mindtickle lock.)*
2. **Correctness lock?** → do NOT rely on any Redis lock as the guarantee. Make the write **idempotent** (best), or add **fencing tokens** the resource enforces, or use a **consensus system** (ZooKeeper/etcd) if you truly need distributed mutual exclusion. The Redis lock, if present, is now just an optimization on top.
3. **The Mindtickle-specific twist:** Mindtickle runs *one* ElastiCache cluster, not N independent masters. So `redsync` here — even though it *is* the Redlock library — degenerates to a **single-instance** lock (there's one primary per shard; a key lives on one primary). You get single-instance `SET NX EX` semantics with a nice API and safe CAS-unlock, but *not* Redlock's multi-master fault tolerance. Which is fine — because per the synthesis, single-instance is the right tool for efficiency locks anyway. Just don't believe you have Redlock's guarantees; you have `SET NX EX`'s.

**The sentence to remember:** Kleppmann and antirez are both right — no timeout lock is correct without fencing, *and* if you need fencing you probably didn't need the heavy lock — so: single-instance `SET NX EX` for efficiency, idempotency/fencing/consensus for correctness, and know that Mindtickle's `redsync` is really single-instance because there's one ElastiCache cluster.

**The trap:** reaching for Redlock (multiple clusters) to make a lock "more correct." It adds operational complexity and still doesn't give correctness without fencing. If you need correctness, fix the resource, not the lock.

**In your codebase:** `content-center-service` uses `redsync` against the single `gen-redis` ElastiCache endpoint. Ask: is this Redlock or single-instance? (Single-instance — one cluster. The `redsync` API gives safe CAS-unlock, not multi-master tolerance.)

---

## 3.7 — Mindtickle's eight locks (the audit you can now read)

**Why this matters:** you now have every concept needed to audit a real lock. Compass pulled all eight of Mindtickle's Redis locks; here they are with the exact facts, so you can practice the judgment. Read each row as: *what kind of lock is it, and does its implementation match?*

```
┌──────────────────────┬──────────────┬────────┬───────────────┬──────────────┐
│ Service              │ lock key     │ TTL    │ unlock        │ owner check? │
├──────────────────────┼──────────────┼────────┼───────────────┼──────────────┤
│ content-center-svc   │ {ContentSync │ 180s   │ redsync       │ yes (random  │
│ (redsync)            │ Id}_{Ingest} │        │ Unlock, but   │ token) — but │
│                      │              │        │ err DISCARDED │ bool discard │
│                      │              │        │ by defer      │ by caller    │
│ content_search_svc   │ raw          │ 2 min  │ redsync,      │ yes; but     │
│ (redsync)            │ ResourceId   │ Tries=1│ logged only   │ latent nil-  │
│                      │              │        │               │ ptr on log   │
│ upload-mgmt (folder) │ UPLOADER_    │ 2s     │ redsync,      │ yes; logged  │
│ (redsync)            │ <workflowId> │ Tries=1│ logged only   │ not enforced │
│ upload-mgmt (TUS)    │ TUS_         │ 20s    │ redsync, err  │ yes —        │
│ (redsync) ★CLEANEST  │ <uploadId>   │ Tries=1│ RETURNED      │ enforced     │
│ ai-tutor             │ invite_email_│ 60s    │ plain DEL     │ NONE         │
│ (SETNX)              │ lock:<co>:<tu>│       │ (value "1")   │              │
│ copilot-chat-agent   │ <feat>_<user>│ 500ms  │ plain DEL     │ NONE         │
│ (SETNX)  ⚠SHORT TTL  │ _init_sess   │  (!)   │               │              │
│ external-sharing-svc │ lock_asset_  │ 10s    │ plain DEL     │ NONE (value  │
│ (SETNX)              │ public_link_ │        │               │ ="locked")   │
│ asset-hub-analytics  │ <TRENDING>:  │ 20s    │ plain DEL     │ NONE (value  │
│ (SETNX) ✗DEAD CODE   │ <companyID>  │        │ (commented    │ ="100")      │
│                      │              │        │ out now)      │              │
└──────────────────────┴──────────────┴────────┴───────────────┴──────────────┘
  Fencing tokens: NONE, anywhere. Every lock is an EFFICIENCY lock.
```

What to *read* from this table — the senior judgment:

- **The `redsync` four are structurally safer** because `redsync` uses a per-mutex random value and a CAS-unlock internally (3.3) — even the ones that discard the unlock error still can't delete someone else's lock, because `redsync`'s own `DEL` is conditional. The `upload-management` TUS lock is the cleanest: it actually returns and checks the unlock error.
- **The four hand-rolled `SETNX` locks all have the plain-`DEL` bug from 3.3** — constant values (`"1"`, `"locked"`, `"100"`), unconditional `DEL`. They can delete a lock they no longer own once the TTL has passed. Whether that *matters* is the efficiency-vs-correctness question: for invitation-email dedup, a rare double email is fine. None guard a correctness-critical write, so the bug is a latent paper-cut, not an incident — *today*. Two per-service wrinkles Compass surfaced: **ai-tutor has no unlock function at all** — its doc comment tells callers to do a raw `Delete(lockKey)` themselves; and **asset-hub-analytics is one line from correct** — its `RLock` actually threads a `value` token through at acquire, but `RUnLock` never reads it back before deleting. The fix (compare-then-delete) is right there, unused.
- **copilot-chat-agent has two problems.** Its 500ms TTL is the one to watch: session init can involve slow dependencies, and 500ms is easy to overrun (3.4), producing routine lease overlaps. Worse, its TTL is *caller-supplied with no default* — **a caller passing `0` gets a lock that never expires**, i.e. the "no TTL → deadlock-on-crash" failure from 3.2 is one bad call away. It's still "just" a duplicate session (efficiency), but it's the closest to biting.
- **asset-hub-analytics' lock is dead code** — the call sites are commented out with "we do not need to take a lock here, since redis is always atomic." That comment is *half right* (individual Redis ops are atomic — Phase 0.1) and *half dangerous* (a read-modify-write across multiple ops is NOT atomic without a lock or a Lua script). Worth flagging.
- **content_search_service's unlock has a latent nil-pointer panic**: if `isUnlocked` is false but the error is nil, the log line dereferences the nil error. A real bug hiding in error-handling code.

Two more facts that complete the picture. First, **the single-cluster SPOF**: all three `redsync` managers wrap *one* ElastiCache endpoint, so a failover of that one primary momentarily affects every lock built on it — single-instance semantics means single point of failure (3.6). Second, **Redisson (the Java lock library) is NOT used for locking in production anywhere** — it appears in ~12 Java repos but only as a cache (`RBucket`/`RMap`/`RAtomicLong`); the only real `RLock`/`tryLock` usage is in the QA automation suite (`mindtickle-api-automation/LockUtils.java`) to serialize shared test environments. So the Go `redsync` + hand-rolled `SETNX` locks above are the *entire* production distributed-locking surface. (Incident history for these locks couldn't be confirmed — Atlassian was unavailable during the Compass run — but a duplicate-email/duplicate-share-link incident is architecturally plausible given the unlock bugs; there's also an open TODO in the code: "concurrency race conditions on same event require Redis locking implementation.")

The meta-lesson: **every Mindtickle Redis lock is an efficiency lock, and that's the correct choice for what they protect.** The implementation gaps (plain DEL, discarded errors, short TTLs, a no-default-TTL) are real but tolerable *because* none of these locks is load-bearing for correctness. The day someone reaches for one of these patterns to guard a payment or a non-idempotent state transition, the audit changes from "paper cuts" to "incident."

**The sentence to remember:** all eight Mindtickle locks are efficiency locks — the `redsync` four are safe-by-library, the four hand-rolled `SETNX` locks have the plain-`DEL` bug but tolerably so, and the danger is the day one of these patterns is copied to guard something that actually needs correctness.

**The trap:** copy-pasting ai-tutor's or external-sharing's `SETNX` + plain-`DEL` lock into a correctness-critical path because "we already do it this way." The existing uses are fine *because* they're efficiency locks; the pattern is not safe for correctness.

**In your codebase:** open `ai-tutor/src/usecase/invitation/lock.go` and `external-sharing-service/.../RedisLockServiceClientImpl.go`. Confirm: constant value, plain `DEL`. Then ask the only question that matters: what breaks if this lock double-fires? (A duplicate email / a duplicate share link — annoying, recoverable. Efficiency lock. The implementation matches the need.)

---

## 3.8 — Lua scripts and Functions in production (what happens to your unlock script at failover)

**Why this matters:** every lock in this phase runs a Lua script on the server. The release in 3.3 is a script. The watchdog extend in 3.4 is a script. redsync runs three scripts. Two facts about scripts decide whether these locks keep working in production. First, a restart or a failover empties the cache that holds the scripts. Second, a slow script stops every other client on that primary. This section teaches both, and the tool that removes the first problem: Functions.

**The mental model.** Redis keeps two kinds of server-side code. A *script* is Lua source that the client sends with `EVAL`. Redis keeps it in the *script cache*, a table in memory keyed by the SHA1 hash of the source. A *function* is Lua code in a named library that you load once with `FUNCTION LOAD`. Functions belong to the data set, like keys. So a function survives a restart and a failover, and a cached script does not.

```
                 ┌──────────────────────┐              ┌──────────────────────┐
                 │ primary              │              │ replica, promoted    │
                 ├──────────────────────┤              ├──────────────────────┤
EVAL src ──────► │ script cache         │  ─ ─ ✗ ─ ─►  │ script cache         │
EVALSHA h ─────► │   sha1 -> source     │  not copied  │   empty              │
                 │   memory only        │              │                      │
                 ├──────────────────────┤              ├──────────────────────┤
FCALL name ────► │ data set             │  ──────────► │ data set             │
                 │   keys + libraries   │  replicated  │   keys + libraries   │
                 │   saved in RDB, AOF  │              │   same as primary    │
                 └──────────────────────┘              └──────────────────────┘
```

### EVAL, EVALSHA and the script cache

Three commands put a script in the cache or run it:

1. `EVAL <source> <numkeys> <key>... <arg>...` sends the full source. Redis hashes it, caches it and runs it.
2. `EVALSHA <sha1> <numkeys> <key>... <arg>...` sends only the 40-character hash. A long script then costs fewer bytes on every call.
3. `SCRIPT LOAD <source>` caches a script without running it, and returns its hash.

If the hash is not in the cache, `EVALSHA` gets this reply. The text is in `src/server.c:2232` at Redis 8.10.2, and E13 printed it:

```
NOSCRIPT No matching script. Please use EVAL.
```

The cache is memory only, so several events empty it. The table gives each event and its evidence.

| Event | Script cache after it | Evidence |
|---|---|---|
| Restart of the process | Empty | E15 restart run: `SCRIPT EXISTS` false, uptime 1 s |
| Failover to a replica | Empty. Since Redis 7.0, `SCRIPT LOAD` is not sent to replicas | 7.0.0 release notes, PR #9812 |
| `SCRIPT FLUSH` | Empty | E13 |
| `DEBUG RELOAD` | Unchanged. It reloads the data set only | E15 |
| 500 newer `EVAL` scripts, since Redis 7.4 | The least recently used `EVAL` script is evicted | E13: `evicted_scripts` went up by 1 |
| 500 newer `EVAL` scripts, script came from `SCRIPT LOAD` | Kept. These are never evicted | E13 |

The eviction rule surprises most people. Since Redis 7.4, Redis caps the scripts that arrived through `EVAL` or `EVAL_RO` at 500. A new one evicts the least recently used one, and INFO stats counts it as `evicted_scripts`. The constant is `LRU_LIST_LENGTH 500` in `src/eval.c:534` at 8.10.2. The source comment gives the reason. Some apps build a new script for each call, and those scripts would fill memory.

Important: on Redis 8.10, `SCRIPT LOAD` does not protect a script that `EVAL` cached first. Redis sees the script is already cached and returns early, so the script stays evictable. The code is `src/eval.c:445-447` at 8.10.2. E13 measured it: `EVAL`, then `SCRIPT LOAD`, then 500 other `EVAL` scripts, and the script was gone.

### What the client does when it gets NOSCRIPT

A lock library must handle `NOSCRIPT`, because the cache can empty at any time. The common clients do it in two different ways.

| Client | On `NOSCRIPT` it sends | What that means for the cache |
|---|---|---|
| go-redis v9.5.1 `Script.Run`, `script.go:68-74` | `EVAL` with the full source | The script now came through `EVAL`, so 500 newer `EVAL` scripts can evict it again |
| redsync v4.18.0 go-redis adapter, `goredis.go:62-64` | `EVAL` with the full source | The same as go-redis |
| redis-py 8.1.0 `Script.__call__`, `commands/core.py:10937` | `SCRIPT LOAD`, then `EVALSHA` again | Never evicted |
| redis-py 8.1.0 pipeline, `client.py:2149` | `SCRIPT EXISTS` and `SCRIPT LOAD` before the pipeline is sent | Never evicted |
| Your own code that calls only `EVALSHA` | Nothing. The error reaches the caller | The unlock fails |

E13 checked both ways on Redis 8.10.1. After `SCRIPT FLUSH`, go-redis `Script.Run` released the lock and returned 1. Then 500 other `EVAL` scripts evicted the unlock script. The redis-py way, `SCRIPT LOAD` and `EVALSHA`, also returned 1, and the script was still cached after 500 other `EVAL` scripts.

The wrong way and the right way in Go. The WRONG lines follow the pattern of the case below. The RIGHT lines use the go-redis method that E13 ran.

```go
// WRONG: load once at start, then call EVALSHA forever.
sha := rdb.ScriptLoad(ctx, unlockSrc).Val()
// ... a failover empties the script cache ...
err := rdb.EvalSha(ctx, sha, []string{key}, token).Err()
// err: NOSCRIPT No matching script. Please use EVAL.

// RIGHT: Script.Run sends EVALSHA, and EVAL with the source on NOSCRIPT.
var unlock = redis.NewScript(unlockSrc)
n, err := unlock.Run(ctx, rdb, []string{key}, token).Int()
// n == 1: released, n == 0: another holder has the lock
```

Here is the same sequence in time, across a failover:

```
┌──────────────────────────────────────────────────────────────────────┐
│ Timeline: the unlock script across a failover. Example times.        │
├──────────────────────────────────────────────────────────────────────┤
│ t=0s   pod A: SCRIPT LOAD unlock -> e04ea135... on the primary       │
│ t=1s   pod A: SET lock:summary:42 tokA NX PX 10000 -> OK             │
│ t=2s   the primary dies. Sentinel promotes the replica               │
│ t=4s   the new primary has the lock key, if the write reached it,    │
│        and an empty script cache                                     │
│ t=5s   pod A: EVALSHA e04ea135... 1 lock:summary:42 tokA             │
│        -> NOSCRIPT No matching script. Please use EVAL.              │
│                                                                      │
│        EVALSHA only    -> unlock fails, the lock stays until t=11s   │
│        go-redis Run    -> EVAL with the source -> 1, released        │
│        redis-py call   -> SCRIPT LOAD, EVALSHA -> 1, released        │
└──────────────────────────────────────────────────────────────────────┘
```

An open issue report shows the cost. async-job-processor-redis is an open-source Ruby job library. The report was filed on 2026-10-14, and the maintainers had not replied by 2026-10-19. Its version 0.3.1 runs `SCRIPT LOAD` once at start and then only calls `EVALSHA`. The code at that tag shows this, and its two background loops have no `rescue`. The report says that after a restart or `SCRIPT FLUSH`, the first `NOSCRIPT` ends its heartbeat and delayed-job loops. The loops do not start again while the process lives. Workers still take jobs, because that path uses no script, so the server looks healthy. The issue suggests one retry after a fresh `SCRIPT LOAD`, and no retry for other errors.

One more rule applies to pipelines. The Redis page "Scripting with Lua" says a pipelined `EVALSHA` can get a `NOSCRIPT` that the client cannot handle. Use `EVAL` inside a pipeline, or load the scripts before you send it, as redis-py does.

### Keys go in KEYS

Pass every key that a script touches as a key argument, never as an `ARGV` value. The client reads the key arguments to pick the cluster node. The server checks each `redis.call` in cluster mode. A key on another node fails with "Script attempted to access a non local key in a cluster node". The check is in `src/script.c:496-539` at 8.10.2. A script that starts with a `#!lua` line also refuses undeclared keys in another slot. It needs the flag `allow-cross-slot-keys` to allow them. So a lock key and its fence counter need one hash tag, such as `{summary:42}:lock` and `{summary:42}:fence`. These cluster rules come from the source. The lab did not run them, because its server is not a cluster.

### Effects replication

Since Redis 7.0, a replica never runs your script. The primary sends the script's writes to the replicas and to the AOF. When the script made more than one write, the primary wraps them in `MULTI` and `EXEC`, in `src/server.c:3861` at 8.10.2. Release notes 7.0.0 list the removal of verbatim script replication as PR #9812. This has two results for a lock:

- A replica applies your unlock without the script. So its empty cache does not matter while it stays a replica.
- The empty cache matters on the day that replica becomes the primary. That is the failover in the timeline above.

A script may also call `TIME` or a random command now, because the replica copies the result, not the call.

### The busy limit, BUSY, SCRIPT KILL and SHUTDOWN NOSAVE

A script blocks every other client while it runs, as 3.3 used for atomicity. The config `busy-reply-threshold`, old name `lua-time-limit`, is 5000 ms by default. On the lab server, `CONFIG GET` returned 5000 for both names. Past that time Redis does not stop the script. It logs "Slow script detected" and answers other clients with this error:

```
BUSY Redis is busy running a script. You can only call SCRIPT KILL or SHUTDOWN NOSAVE.
```

Before the threshold, other clients only wait. After it, they get `BUSY`. `SCRIPT KILL` stops the script only if it has not written yet. After its first write, Redis replies `UNKILLABLE`. The reason is atomicity: stopping the script after a write would leave half of its writes in the data set. E14 measured both cases with the threshold lowered to 200 ms on the lab server:

```
┌──────────────────────────────────────────────────────────────────────┐
│ E14 on Redis 8.10.1, busy-reply-threshold 200 ms. Measured.          │
├──────────────────────────────────────────────────────────────────────┤
│ A script that only reads, spinning for 1.5 s                         │
│ t=0 ms     client 1: EVAL spin. Nobody else is served now            │
│ t=50 ms    client 2: PING. No reply, the server is in the script     │
│ t=200 ms   the threshold passes. PING gets BUSY after 150 ms         │
│ t=200 ms   client 2: SCRIPT KILL -> OK                               │
│ t=200 ms   client 1: ERR Script killed by user with SCRIPT KILL...   │
├──────────────────────────────────────────────────────────────────────┤
│ A script that writes one key first, then spins for 1.5 s             │
│ t=0 ms     client 1: EVAL SET p3sc:written, then spin                │
│ t=310 ms   client 2: SCRIPT KILL -> UNKILLABLE Sorry the script ...  │
│ t=310 ms   client 2: PING -> BUSY                                    │
│ t=1.51 s   client 1: write-spin done. The script ended by itself     │
│ t=1.51 s   client 2: PING -> PONG                                    │
└──────────────────────────────────────────────────────────────────────┘
```

The full `UNKILLABLE` reply from E14 names the last way out:

```
UNKILLABLE Sorry the script already executed write commands against the dataset. You can either wait the script termination or kill the server in a hard way using the SHUTDOWN NOSAVE command.
```

`SHUTDOWN NOSAVE` stops the server without saving. Every write since the last save on that server is lost. On a primary that is a decision to lose data, so most teams wait instead.

Three more details matter in production:

1. The check runs from a Lua hook every 100,000 Lua instructions, in `src/script_lua.c:1669-1671` at 8.10.2. One long `redis.call`, such as `KEYS *` on a large database, cannot be stopped while it runs. This is inferred from the hook design and was not measured.
2. A threshold of 0 removes the limit, and the script can never be killed. On the lab server, `CONFIG SET busy-reply-threshold -1` was refused: "argument must be between 0 and 9223372036854775807 inclusive".
3. Sentinel does not count `BUSY` as a valid reply to its `PING`. When it already sees the primary as down and the reply is `BUSY`, it sends `SCRIPT KILL` once. The code is `src/sentinel.c:2813-2831` at 8.10.2. If the script has written, the kill fails, and the primary stays down for Sentinel.

ScaleGrid, a Redis hosting vendor, showed what happens next in a demo. They used two Redis servers, three Sentinels, `lua-time-limit` 500 ms and `down-after-milliseconds` 5 s. An endless script that wrote keys made Sentinel promote the replica. When the old primary was brought back online, Sentinel made it a replica. It then synced from the new primary, so the script's writes were lost. The post does not say how the endless script was stopped. This is a vendor demo, not an incident report.

Rails hit the `BUSY` error in its cache store. `RedisCacheStore#delete_matched` deleted keys by pattern inside one Lua script. With enough keys, other clients got `BUSY` errors. The fix replaced the script with a `SCAN` and `DEL` loop. A lock script is two commands on one key, so it is far below 5,000 ms. The danger is a long script that someone else runs on the same primary.

### Read-only scripts: EVAL_RO, EVALSHA_RO and FCALL_RO

Since Redis 7.0, `EVAL_RO`, `EVALSHA_RO` and `FCALL_RO` run a script that must not write. The server refuses a write inside them. This lab's server replied: "ERR Write commands are not allowed from read-only scripts." A read-only call can run on a read-only replica. An ACL rule can also allow it for a user who may not write. A lock's owner check, `GET` of the lock key, fits a read-only call. E15 ran the owner check with `FCALL_RO` and got `tokA`. It ran the unlock with `FCALL_RO` and got "ERR Can not execute a script with write flag using *_ro command."

### Functions: FUNCTION LOAD and FCALL

A function library starts with a line that names its engine and the library. Each `redis.register_function` call adds one named function. This is the lock library from `script_cache/main.go:90-107`:

```lua
#!lua name=p3sc_lockkit
redis.register_function('p3sc_unlock', function(keys, args)
  if redis.call('GET', keys[1]) == args[1] then
    return redis.call('DEL', keys[1])
  end
  return 0
end)
redis.register_function('p3sc_extend', function(keys, args)
  if redis.call('GET', keys[1]) == args[1] then
    return redis.call('PEXPIRE', keys[1], args[2])
  end
  return 0
end)
redis.register_function{
  function_name = 'p3sc_owner',
  callback = function(keys) return redis.call('GET', keys[1]) end,
  flags = {'no-writes'},
}
```

The client then calls a function by name: `FCALL p3sc_unlock 1 lock:summary:42 tokA`. The rules below come from the Redis 8.10.2 source and the functions documentation:

1. `FUNCTION LOAD` loads a whole library at once. A library is replaced as a whole, with `FUNCTION LOAD REPLACE`. Without `REPLACE`, loading a name that exists fails. This lab's server replied "ERR Library 'lockkit' already exists".
2. A function gets its keys as the first argument of its callback and its other arguments as the second. The `KEYS` and `ARGV` globals do not exist in functions.
3. `FUNCTION LOAD` is a write command. So the library goes to the replicas and to the AOF, and `SAVE` writes it into the RDB file. E15 deleted the library from memory and ran `DEBUG RELOAD NOSAVE`, and the library came back from the file. After a real restart, the library was loaded and the script cache was empty.
4. In a cluster, Redis does not copy libraries between shards. You load the library on every primary yourself. The documentation gives `redis-cli --cluster-only-masters --cluster call host:port FUNCTION LOAD ...` for this. `redis-cli --cluster add-node` copies the libraries to a new node.
5. `FUNCTION DUMP` returns every library in the RDB format, with a version and a checksum. `FUNCTION RESTORE <payload>` takes a policy. `APPEND` is the default and fails when a library exists. `REPLACE` replaces it. `FLUSH` deletes all libraries first. E15 got "ERR Library p3sc_lockkit already exists" with the default and `OK` with `REPLACE`.
6. Library code runs once, at load time, with a limit of 500 ms. `FUNCTION KILL` stops a long function, and `SCRIPT KILL` cannot stop one.

Flags change where a script or function may run. You set them in the table form of `register_function`, or on the `#!lua` line of a script.

| Flag | Effect |
|---|---|
| no flags, on a `#!lua` script or a function | May write. Refused on a stale replica and when memory is over `maxmemory`. Keys must be in one slot |
| `no-writes` | Allowed under `FCALL_RO` and `EVAL_RO`, and on read-only replicas |
| `allow-oom` | Allowed when used memory is over `maxmemory` |
| `allow-stale` | Allowed on a stale replica with `replica-serve-stale-data no` |
| `no-cluster` | Refused in cluster mode |
| `allow-cross-slot-keys` | May touch undeclared keys in other slots |

### When to choose Functions over EVAL

Recommendation: keep `EVAL` with a `NOSCRIPT` fallback for a short lock script that one app owns. Move to Functions when several services share the code. Also move when the code must survive a failover without help from each client. The table gives the trade-offs.

| Question | `EVAL` and `EVALSHA` | Functions |
|---|---|---|
| Survives restart and failover | No. Each client must handle `NOSCRIPT` | Yes. Saved in RDB and AOF, and replicated |
| Deploy step | None. The app carries the source | Load on every primary, and again on a new cluster |
| Name in `SLOWLOG` and `MONITOR` | `EVALSHA` shows a SHA1 hash. `EVAL` shows the whole source | A function name |
| Changing the code | New source means a new hash. Old and new run side by side | `FUNCTION LOAD REPLACE` changes it for every caller at once |
| Inside a pipeline | `EVALSHA` can fail with `NOSCRIPT` | No cache to miss |
| Who owns it | The app team | The team that runs Redis, or one shared library |

The Redis design issue that proposed Functions, #8693, lists the same problems with scripts. Scripts can disappear, `EVALSHA` in a transaction is risky, and SHA names are hard to debug. No first-hand report of a production move from `EVAL` to Functions was found.

### Valkey 9.1 differences

Valkey 9.1.2 runs the same commands with these differences:

- Lua is a module in `src/modules/lua` since Valkey 9.1.0, PR #2858. The build option `BUILD_LUA` has three values in `src/Makefile:261-293`. `static` is the default since PR #3392, `module` builds `libvalkeylua.so`, and `no` builds a server without Lua.
- A server built with `BUILD_LUA=no` has no Lua engine, so `EVAL` and `FCALL` with Lua code fail. This is inferred from the engine lookup and was not built. Ask your managed Valkey service which build it runs.
- The global table is `server`, and `redis` is an alias for it, in `src/modules/lua/script_lua.c:1842-1848`. Code that calls `redis.call` runs on both servers.
- `SCRIPT SHOW <sha1>` returns the source of a cached script, since Valkey 8.0.0. Redis 8.10.2 has no `SCRIPT SHOW`.
- `SCRIPT LOAD` of a script that `EVAL` cached first takes it off the eviction list, in `src/eval.c:366-388`. So on Valkey, `SCRIPT LOAD` protects the script. On Redis 8.10 it does not.
- `busy-reply-threshold` has the same names and the same default of 5000 ms.

**The sentence to remember:** the script cache is memory only and is not replicated. So every `EVALSHA` needs a `NOSCRIPT` fallback, and code that must survive a failover belongs in a Function.

**The trap:** a lock helper that runs `SCRIPT LOAD` once at start. After the first failover, every unlock fails with `NOSCRIPT`. Each lock stays until its TTL ends, and the server looks healthy.

**Try this now:**
```bash
go run ./phase03_locking/script_cache -addr localhost:6582 -part noscript
# Look for NOSCRIPT after SCRIPT FLUSH, then "released ... got 1" from the go-redis fallback.
```

---

## 🧪 Hands-on lab — the exercises that teach Phase 3

Setup:
```bash
cd /Users/raghvendradhakar/Desktop/code/verly/study-material/redis/code
docker-compose up -d && docker exec redis-study redis-cli PING   # → PONG
```

- [ ] **E1. The correct lock.**
  - Run: `go run ./phase03_locking/safe_lock`
  - Expected: A acquires, B denied while A holds, A releases, A's stale token can't release B's later lock.
  - Teaches: `SET NX PX` + random token + Lua CAS unlock, end to end.

- [ ] **E2. Watch the acquire on the wire.**
  - Run: `docker exec -it redis-study redis-cli MONITOR` in one terminal; in another `docker exec redis-study redis-cli SET lock:x tokenA NX PX 30000` then again with `tokenB`.
  - Expected: first returns OK, second returns nil (key exists).
  - Teaches: `NX` is the mutual exclusion; the single thread makes it atomic.

- [ ] **E3. (Break it) The plain-DEL unlock bug.**
  - Run: `go run ./phase03_locking/unsafe_unlock`
  - Expected: A's lock expires mid-work, B acquires, A's `DEL` deletes B's lock, C acquires → B+C both hold.
  - Teaches: the exact ai-tutor/external-sharing failure mode. This is why value must be random + CAS unlock.

- [ ] **E4. Prove the Lua CAS unlock refuses a stale release.**
  - Run: `docker exec redis-study redis-cli SET lock:y realowner PX 30000`, then run the release script with the WRONG token: `docker exec redis-study redis-cli EVAL 'if redis.call("GET",KEYS[1])==ARGV[1] then return redis.call("DEL",KEYS[1]) else return 0 end' 1 lock:y wrongtoken` (→ 0, not deleted), then with `realowner` (→ 1).
  - Teaches: compare-and-delete only deletes when you still own it.

- [ ] **E5. (Break it) Lease overrun → two holders.**
  - Run: `go run ./phase03_locking/lease_expiry_race -ttl 500ms -work 900ms`
  - Expected: counter==2, invariant broken, "❌ BROKEN".
  - Teaches: a perfect lock still fails if work > TTL. The Redlock-debate crux.

- [ ] **E6. Tune the lease to fix (and then break) it.**
  - Run: `-ttl 2s -work 900ms` (safe: counter==1), then `-ttl 2s -work 3s` (broken again).
  - Teaches: TTL sizing is a bet on worst-case work; there's no value that's safe against an unbounded pause.

- [ ] **E7. Fencing tokens save the day.**
  - Run: `go run ./phase03_locking/fencing_tokens`
  - Expected: token 34 accepted, stale token 33 rejected.
  - Teaches: only the resource-enforced token prevents the lease-overrun double-act.

- [ ] **E8. Fencing without enforcement is theater.**
  - Reason about it: modify `fencing_tokens` so the resource does NOT check the token (accept all writes). What's the final value? (A's stale "A's STALE data" wins — the token did nothing.)
  - Teaches: the token is worthless unless the resource rejects stale ones.

- [ ] **E9. Simulate copilot-chat-agent's 500ms TTL.**
  - Run: `go run ./phase03_locking/lease_expiry_race -ttl 500ms -work 700ms`
  - Expected: broken (counter==2) — a 700ms init (one slow gRPC) overruns a 500ms lease.
  - Teaches: why a sub-second TTL on variable-latency work is fragile.

- [ ] **E10. Build the redsync-equivalent by hand.**
  - Write a tiny Go loop that acquires with `SetNX(key, uuid, ttl)`, retries with backoff on failure (like asset-hub-analytics' `[1,2,5,10]s` jittered backoff), and releases with the Lua CAS. Compare your version to `safe_lock`.
  - Teaches: what `redsync` does for you, and the retry/backoff dimension.

- [ ] **E11. (Break it) Read-modify-write without a lock.**
  - Run: 50 concurrent `GET counter; increment in your shell; SET counter` (the WRONG way) vs 50 `INCR counter` (right). 
  - Expected: the GET/SET version loses updates; `INCR` is exact.
  - Teaches: the asset-hub-analytics "redis is always atomic" comment is only true for single ops, not read-modify-write — sometimes you DO need the lock (or a Lua script).

- [ ] **E12. Inspect a live lock's TTL.**
  - Run: `docker exec redis-study redis-cli SET lock:demo tok PX 30000; docker exec redis-study redis-cli PTTL lock:demo` repeatedly.
  - Expected: PTTL counts down; at 0 the key vanishes (auto-expiry).
  - Teaches: the lease is real and observable; `PTTL` is your debugging tool for "who holds it and for how long."

E13 to E15 were run on 2026-10-19 against a throwaway server. It was an x86_64 Homebrew Redis 8.10.1 under Rosetta 2 on an Apple M4 Pro. It was started with `redis-server --port 6582 --dir <tmpdir> --save '' --appendonly no --enable-debug-command local --daemonize yes`. The program flushes the script cache and changes a config value. So it refuses to run when the server holds a key that is not its own, in any database. A small model of the server rules runs next to the server and gives the expected value of each step. Its offline check is `go run ./phase03_locking/script_cache -self-test`.

- [ ] **E13 (live).** EVALSHA after the script cache is emptied, and how each client recovers.
  - Run: `go run ./phase03_locking/script_cache -addr localhost:6582 -part noscript`
  - Expected: `after SCRIPT FLUSH, EVALSHA -> NOSCRIPT No matching script. Please use EVAL.` Then `go-redis Script.Run falls back to EVAL, released` with `got 1`. After 500 other `EVAL` scripts the unlock script is gone, and `evicted_scripts went up by` shows `got 1`. The `SCRIPT LOAD` way keeps the script. Every line ends with `matches the model`.
  - If it fails: `refusing to run` means the server holds keys that are not the lab's. Start a throwaway server on its own port.
  - Teaches: the script cache is memory only, and every `EVALSHA` needs a `NOSCRIPT` fallback.

- [ ] **E14 (break-it, live).** A slow script gives other clients BUSY, and SCRIPT KILL fails after a write.
  - Run: `go run ./phase03_locking/script_cache -addr localhost:6582 -part busy`
  - Expected: `PING sent at 50ms waited 150ms -> BUSY Redis is busy running a script. You can only call SCRIPT KILL or SHUTDOWN NOSAVE.` Then `SCRIPT KILL before any write` gets `OK`. For the script that wrote: `SCRIPT KILL at 310ms -> UNKILLABLE Sorry the script already executed write commands against the dataset.` and later `script reply after 1.51s: write-spin done`. The times move by about 10 ms between runs: a second run printed `300ms` and `1.5s`.
  - If it fails: the program lowers `busy-reply-threshold` to 200 ms with `CONFIG SET`. It puts the old value back at the end. On a slow machine, raise `-spin` so the scripts run past the threshold.
  - Teaches: the busy limit does not stop a script. After the first write, only waiting or `SHUTDOWN NOSAVE` ends it.

- [ ] **E15 (break-it, live).** A Function survives a reload and a restart. The script cache survives only DEBUG RELOAD.
  - Run: `go run ./phase03_locking/script_cache -addr localhost:6582 -part reload`
  - Expected: `library p3sc_lockkit loaded after DEBUG RELOAD` and `unlock script cached after DEBUG RELOAD` both match. After `FUNCTION DELETE`, `DEBUG RELOAD NOSAVE` loads the library back from the file. `FCALL_RO p3sc_unlock -> ERR Can not execute a script with write flag using *_ro command.` `FUNCTION RESTORE (APPEND) -> ERR Library p3sc_lockkit already exists`, and `REPLACE` gets `OK`.
  - Then run: `go run ./phase03_locking/script_cache -addr localhost:6582 -part restart-prep`, then `redis-cli -p 6582 SHUTDOWN NOSAVE`, start the server again with the same `--dir`, and run `go run ./phase03_locking/script_cache -addr localhost:6582 -part restart-check`.
  - Expected: `uptime_in_seconds:1`, `unlock script cached after the restart` with `got false`, and `library p3sc_lockkit loaded after the restart` with `got 1`.
  - If it fails: if `DEBUG RELOAD` returns an error that DEBUG is not allowed, start the server with `--enable-debug-command local`.
  - Teaches: a library is part of the data set and comes back from the RDB file. The script cache is part of the process.

My first version of E15 was wrong, and the mistake teaches something. It expected `DEBUG RELOAD` to empty the script cache. The run showed the script still cached. `DEBUG RELOAD` calls `emptyData` and `rdbLoad` in `src/debug.c:648-651` at 8.10.2. `emptyData` clears the keys and the function libraries in `src/db.c:1079-1081`. `rdbLoad` skips the old `lua` field of the file, in `src/rdb.c:4822-4823`. Neither call touches the script cache. So the restart step is the real test of a cache that a new process loses.

---

## 🏢 Codebase anchor — things to check in the codebase

1. **The safe end (redsync).** Open `content-center-service/src/infrastructure/dispatch/packet/redis_packet.go` — `AcquireLock` (`redsync.NewMutex(key, WithExpiry(180s))`) and `ReleaseLock` (checks `ok` bool + err). Then find the *caller* in `UploadedMediaAssetFacade.go`: it's `defer facade.redisClient.ReleaseLock(ctx, mutex)` — the returned error is discarded. Question: does discarding the unlock error create a *correctness* bug here, given `redsync`'s internal CAS-unlock? (No — CAS-unlock still can't delete another's lock; discarding the error just means you won't *notice* a failed unlock, a observability gap, not a safety one.)

2. **The unsafe end (SETNX + plain DEL).** Open `ai-tutor/src/usecase/invitation/lock.go`: `SetNX(ctx, key, "1", 60s)` in a retry-until-deadline loop, released with a `defer` plain `Delete`. Reproduce its bug with E3. Question: is this an incident? (No — efficiency lock for email dedup; the double-fire cost is a duplicate email. The implementation is *sloppy* but *appropriate* for the risk. That judgment is the whole skill.)

3. **The one to actually worry about.** `copilot-chat-agent/.../RedisClient.go` uses a **500ms** TTL (`REDIS_TTL_FOR_INIT_RESUME_SESSION_LOCK`) on a session-init lock. Question: what's the worst-case latency of session init (LLM warm-up? gRPC to another service?), and how often would it exceed 500ms? Run E9. If init routinely takes >500ms, the lock is providing *less* protection than its existence implies — a false sense of safety.

4. **The dead lock + the dangerous comment.** In `asset-hub-analytics`, the `RLock`/`RUnLock` call sites are commented out with "we do not need to take a lock here, since redis is always atomic." Find the code that runs *instead*. Question: is it a single atomic op (comment is right) or a read-modify-write across multiple ops (comment is dangerously wrong — Phase 0.1 says only *individual* commands are atomic)? This is the exact confusion E11 targets.

---

## ✅ Checkpoint 3 — answer in your own words

1. **Q1.** For each of these, say "efficiency" or "correctness" and justify, then state whether Mindtickle's actual implementation is adequate: (a) ai-tutor deduping invitation emails; (b) a hypothetical lock ensuring a customer's subscription is charged exactly once; (c) copilot-chat-agent preventing duplicate chat sessions; (d) a lock ensuring a ledger balance is decremented once. Which of (a)–(d) could safely use the existing `SETNX`+plain-`DEL` pattern, and which absolutely could not?

2. **Q2.** Walk through the plain-`DEL` bug with ai-tutor's exact lock (`SetNX(key,"1",60s)`, `defer Delete(key)`). Give a concrete timeline where worker A deletes worker B's lock. Then: why does switching the value from `"1"` to a random UUID + a Lua compare-and-delete fix *this specific* bug — and what deeper bug does it *not* fix?

3. **Q3.** copilot-chat-agent uses a 500ms lock TTL on session init. Session init makes a gRPC call that's normally 80ms but occasionally 1.2s under load. Show the timeline for the 1.2s case: what happens to the lock, and can two session-init flows run concurrently? Propose two fixes and state which you'd ship.

4. **Q4.** Explain the Redlock debate to a colleague in four sentences: what Kleppmann claims, what antirez replies, why they're *both* right, and what you should therefore do for (a) an efficiency lock and (b) a correctness lock. Then: Mindtickle runs `redsync` (the Redlock library) against a single ElastiCache cluster — what guarantee does that actually give, and what does it NOT?

5. **Q5.** Design a fencing-token scheme for a hypothetical "generate exactly one invoice PDF per order" flow, where the PDF is written to S3. Give: the acquire (with token), the write (with token), and exactly what the *resource* (S3 + your metadata) must do to reject a stale writer. Then explain why, per antirez, this scheme means you might not have needed the distributed lock at all.

6. **Q6.** The asset-hub-analytics comment says "we do not need a lock, since redis is always atomic." Give one operation where that comment is *correct* and one where it's *dangerously wrong*, using the trending-assets ZSet+List design from Phase 1.5 (record-a-view = LPOP oldest + ZIncrBy decrement + RPUSH new + ZIncrBy increment). Is that sequence safe without a lock? Why or why not, and what would make it safe?

7. **Q7.** You're reviewing an MR that adds a `SETNX`+plain-`DEL` lock (copied from ai-tutor) to guard a new flow that decrements a customer's "remaining AI credits" and calls a paid third-party API. Write the review comment: what's wrong, what's the risk in concrete terms, and what three changes would you require before approving (ordered by importance)?

8. **Q8.** Your summary service calls the unlock script of 3.3 with `EVALSHA` only. Each pod runs `SCRIPT LOAD` once at start. The lock TTL is 10 s, and Sentinel's `down-after-milliseconds` is 30,000. (a) Sentinel fails over the primary at 02:00. Walk through what each pod sees on its next unlock and extend, and how long each lock stays. (b) A teammate adds a reporting script with `EVAL` on the same primary. It writes a key first and then runs for about 7 s. With the default `busy-reply-threshold`, what do the lock clients see, for how long, and can `SCRIPT KILL` help? (c) What would you move into a Function, and what deploy step does that add on a cluster with 3 primaries?

<details>
<summary>Answer sketches</summary>

1. (a) Efficiency, since a double email is a nuisance. The pattern is tolerable, though a random token and a compare-and-delete cost nothing. (b) Correctness. No Redis lock is the guarantee. Use an idempotency key with the payment provider and a unique charge row in your database. (c) Efficiency, but watch for a TTL shorter than the session start. (d) Correctness. Use a conditional UPDATE or a version check in the ledger's own database. Only (a) and (c) could use the existing pattern, and (b) and (d) must not.
2. A acquires at t=0 s, and its work stalls until t=70 s. The key expires at t=60 s, and B acquires at t=61 s. A finishes at t=70 s, and its deferred Delete removes B's key. C acquires at t=71 s, so B and C overlap. With a random token, A's release finds B's token and deletes nothing. A and B still both worked between t=61 s and t=70 s, which is the lease problem, and only an idempotent write or a fence fixes it.
3. Flow 1 acquires at 0 ms, and the lock expires at 500 ms. Flow 2 acquires at, say, 600 ms, so the two flows run at once from 600 ms to 1,200 ms. If the release is a plain DEL, flow 1 then deletes flow 2's lock at 1,200 ms. Fix one: a TTL well above the p99 of the call, such as 5 s, with a watchdog. Fix two: make session creation idempotent with a unique key on user and feature. Ship both, and treat the unique key as the guarantee and the lock as a saving.
4. Kleppmann says no lease-based lock is correct against long pauses without fencing, and that Redlock leans on timing assumptions. antirez says a random token with check-and-set at the resource is enough, and that a resource able to resolve races needs no strong lock. Both are right, so you use one Redis node for efficiency and a check at the resource for correctness. On one endpoint the library's quorum is 1, so you get single-node SET NX PX with a safe release. You do not get tolerance of node failures, and the lock can still vanish at failover.
5. Take the token from the order's database row, for example by adding one to an invoice_fence column and reading it back, because that source does not go backwards. Optionally take a Redis lock to save work. Upload the PDF under a key that includes the token, such as invoices/42/7.pdf. Then run UPDATE invoices SET object_key = :k, fence = :t WHERE order_id = :o AND fence < :t, and treat 0 rows as "a newer writer won". S3 cannot do the check, so the metadata row is the resource. The row already refuses stale writers with its own version, so the lock only saves duplicate rendering work.
6. Correct: one ZINCRBY or one INCR is atomic. Wrong: the four-command view update, because another client's commands can run between any two of them. Two views can then pop and decrement in an order that leaves the counts wrong. Make the four commands one Lua script, because the decrement needs the value that LPOP returned, which MULTI cannot pass along. WATCH with a retry also works. A distributed lock is the wrong tool, because Redis is the resource.
7. What is wrong: an efficiency-lock pattern now guards a correctness job, with a constant value, a plain DEL and no check at the resource. The risk: one stall past the TTL deducts the customer's credits twice and bills the provider twice, and no error is logged. Required changes, in order. First, make the credit decrement conditional and idempotent in the database, with a unique key per request. Second, record the paid call in a row before sending, and send the provider an idempotency key if it accepts one. Third, fix the lock itself, with a random token, a DELEX or Lua release, a TTL above the call's p99, and a count of ErrLockAlreadyExpired.
8. (a) The promoted replica has an empty script cache, because `SCRIPT LOAD` is not replicated since Redis 7.0. Every pod's next `EVALSHA` gets `NOSCRIPT`, so no unlock and no extend succeeds. A lock whose key reached the replica stays until its TTL ends. That is at most 10 s after its last acquire or extend. A watchdog's extend also fails, so long jobs lose their lease and overrun. The fix is go-redis `Script.Run`, which sends `EVAL` on `NOSCRIPT`. (b) For the first 5,000 ms every lock command waits, and at 5,000 ms the waiting commands get `BUSY`. For the last 7,000 - 5,000 = 2,000 ms every new command gets `BUSY` at once. The script wrote first, so `SCRIPT KILL` gets `UNKILLABLE`. Sentinel sends one `SCRIPT KILL` only when it already sees the primary as down. That takes 30,000 ms here, so no failover happens. Rewrite the report as a `SCAN` loop, as Rails did. (c) Move the unlock and extend into one library, such as `p3sc_lockkit`. It then survives restarts and failovers. The new step is `FUNCTION LOAD REPLACE` on all 3 primaries, for example with `redis-cli --cluster-only-masters --cluster call host:port FUNCTION LOAD REPLACE ...`, on every release of the library. The reporting job stays a client-side loop, because a function blocks the server exactly as a script does.

</details>

---

## References & Further Learning

**Must-read (in order — this is a debate, read both sides):**
- 📄 [How to do distributed locking — Martin Kleppmann](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html) — THE critique. Efficiency vs correctness, the pause problem, and fencing tokens explained with diagrams. (25 min) Read BEFORE 3.4–3.5. Non-negotiable.
- 📄 [Is Redlock safe? — antirez's rebuttal](https://antirez.com/news/101) — the other side, by Redis's creator. The check-and-set-with-unique-token counterargument and the semi-synchronous timing model. (20 min) Read immediately after Kleppmann.
- 📄 [Redlock algorithm — official Redis docs](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/) — the canonical single-instance lock recipe (SET NX PX + Lua unlock) AND the multi-master Redlock spec. (15 min) The recipe in the first half is exactly `safe_lock`.

**Deep dives:**
- 📄 [redsync — the Go Redlock library](https://github.com/go-redsync/redsync) — read `mutex.go`: `Lock`, `Unlock` (the Lua CAS), `Extend` (the watchdog). This is what content-center-service/upload-management use. (20 min) Read the source after 3.3.
- 🎥 [Martin Kleppmann — "Distributed systems" lecture series](https://www.youtube.com/playlist?list=PLeKd45zvjcDFUEv_ohr_HdUFe97RItdiB) — the Cambridge course; the consistency & consensus lectures give the theory under the debate. (per-video ~50 min) For when you want the foundations.
- 📄 [Chubby / "The Chubby lock service" — Google (Burrows, OSDI'06)](https://research.google/pubs/the-chubby-lock-service-for-loosely-coupled-distributed-systems/) — the paper that defined distributed lock services; where fencing (sequencers) comes from. (45 min) The canonical source.
- 📚 *Designing Data-Intensive Applications* (Kleppmann), Ch. 8 "The Trouble with Distributed Systems" & Ch. 9 "Consistency and Consensus" — the definitive treatment of process pauses, fencing tokens, and why locks are hard. Read Ch. 8 §"Process Pauses" alongside 3.4.

**Official docs (bookmark):**
- [SET command options](https://redis.io/docs/latest/commands/set/) — `NX`, `XX`, `PX`, `EX`, `GET`, `KEEPTTL`.
- [EVAL / Lua scripting](https://redis.io/docs/latest/develop/interact/programmability/eval-intro/) — for the atomic compare-and-delete and beyond.

**Lua scripts and Functions in production, for 3.8. Every URL below was fetched on 2026-10-19 and returned HTTP 200:**
- **Scripting with Lua, Redis docs** — https://redis.io/docs/latest/develop/programmability/eval-intro/
  Focus on: "Script cache", "Cache volatility", "EVALSHA in the context of pipelining" and "Script replication". Read it with E13.
- **EVAL command page, Redis docs** — https://redis.io/docs/latest/commands/eval/
  Focus on: the note that since Redis 7.4 scripts loaded with EVAL or EVAL_RO are evicted. The docs give no number. The source below gives 500.
- **Redis programmability, Redis docs** — https://redis.io/docs/latest/develop/programmability/
  Focus on: "Maximum execution time" for SCRIPT KILL and SHUTDOWN NOSAVE, and "Read-only scripts". Read it with E14.
- **Redis functions, Redis docs** — https://redis.io/docs/latest/develop/programmability/functions-intro/
  Focus on: "Prologue", which lists what is wrong with EVAL scripts, "Functions in cluster" and "Function flags". Read it with E15.
- **Redis 8.10.2 source, src/eval.c** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/eval.c
  Focus on: lines 520 to 550, the 500-entry LRU for EVAL scripts, and lines 445 to 447, where SCRIPT LOAD returns early.
- **Redis 8.10.2 source, src/script.c** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/script.c
  Focus on: lines 141 to 170 for the slow-script log, 366 to 389 for when SCRIPT KILL refuses, and 496 to 552 for the cluster key checks.
- **Redis 8.10.2 source, src/script_lua.c** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/script_lua.c
  Focus on: lines 1669 to 1671, the hook every 100,000 instructions that checks the busy limit.
- **Redis 8.10.2 source, src/server.c and src/config.c** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/server.c
  Focus on: server.c lines 2231 to 2238 for the NOSCRIPT and BUSY texts. config.c line 3573 at https://raw.githubusercontent.com/redis/redis/8.10.2/src/config.c gives busy-reply-threshold, alias lua-time-limit, default 5000.
- **Redis 8.10.2 source, src/sentinel.c** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/sentinel.c
  Focus on: lines 2813 to 2831, where Sentinel sends SCRIPT KILL to a busy primary, and line 69, the 30,000 ms down-after default.
- **Redis 8.10.2 source, src/debug.c** — https://raw.githubusercontent.com/redis/redis/8.10.2/src/debug.c
  Focus on: lines 611 to 659, DEBUG RELOAD. It explains why the E15 script stayed cached.
- **Redis 7.0.0 release notes** — https://raw.githubusercontent.com/redis/redis/7.0.0/00-RELEASENOTES
  Focus on: #9812, the end of verbatim script replication and of SCRIPT LOAD propagation, and #8693, Functions.
- **Redis issue #8693, the Functions design** — https://github.com/redis/redis/issues/8693
  Focus on: the list of problems with EVAL scripts that Functions were built to fix.
- **go-redis v9.5.1, script.go** — https://raw.githubusercontent.com/redis/go-redis/v9.5.1/script.go
  Focus on: lines 68 to 74, Script.Run and its EVAL fallback. This is the version the lab pins.
- **redsync v4.18.0, go-redis v9 adapter** — https://raw.githubusercontent.com/go-redsync/redsync/v4.18.0/redis/goredis/v9/goredis.go
  Focus on: lines 51 to 64, the same EVAL fallback inside redsync.
- **redis-py v8.1.0, commands/core.py and client.py** — https://raw.githubusercontent.com/redis/redis-py/v8.1.0/redis/commands/core.py
  Focus on: core.py line 10937, SCRIPT LOAD and EVALSHA on NoScriptError, and client.py lines 2149 to 2160 at https://raw.githubusercontent.com/redis/redis-py/v8.1.0/redis/client.py for pipelines.
- **Valkey 9.1.2, src/Makefile** — https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/Makefile
  Focus on: lines 261 to 293, the three BUILD_LUA values.
- **Valkey 9.1.2, the Lua module README and source** — https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/modules/lua/README.md
  Focus on: why Lua became a module. The `server` global is in https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/modules/lua/script_lua.c lines 1842 to 1848.
- **Valkey 9.1.2, src/eval.c** — https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/eval.c
  Focus on: lines 366 to 388, where SCRIPT LOAD takes an EVAL script off the eviction list.
- **Valkey 9.1.2 release notes** — https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/00-RELEASENOTES
  Focus on: #2858, Lua moved into a module, and #3392, static by default. SCRIPT SHOW is "since 8.0.0" in https://raw.githubusercontent.com/valkey-io/valkey/9.1.2/src/commands/script-show.json.
- **async-job-processor-redis issue #15, an open-source Ruby job library** — https://github.com/socketry/async-job-processor-redis/issues/15
  Focus on: how one NOSCRIPT after a restart stopped two background loops for good while the server looked healthy.
- **Rails issue #32610, RedisCacheStore#delete_matched** — https://github.com/rails/rails/issues/32610
  Focus on: a Lua delete-by-pattern that caused BUSY errors, replaced with a SCAN and DEL loop.
- **ScaleGrid, "Redis Transactions & Long-Running Lua Scripts", vendor blog, 2020** — https://dev.to/scalegrid/redis-transactions-long-running-lua-scripts-5a6e
  Focus on: the demo with lua-time-limit 500 ms and down-after-milliseconds 5 s, where Sentinel failed over and the script's writes were lost. A vendor demo, not an incident report.

---

## Cheatsheet — Phase 3

```
THE FIRST QUESTION (always ask before locking)
  EFFICIENCY lock  → "don't do it twice", failure = minor (dup email, wasted $)
                   → single-instance SET NX PX + random token + Lua CAS. Ship it.
  CORRECTNESS lock → "two must never both act", failure = corruption/double-charge
                   → a Redis lock is NOT enough. Use idempotency / fencing / consensus.

THE CORRECT SINGLE-INSTANCE LOCK
  acquire:  SET lock:res <randomToken> NX PX <ttl>
              NX = mutual exclusion (atomic via single thread)
              PX = auto-expire → no deadlock if holder crashes
              randomToken = owner fingerprint (NOT "1"/"locked"/const)
  release:  EVAL 'if GET(k)==ARGV[1] then DEL(k) else 0 end'  (atomic compare-and-delete)

THE THREE FAILURE MODES (and fixes)
  1. no TTL         → crashed holder locks forever      → always set PX/EX
  2. plain DEL      → delete someone else's lock after   → random token + Lua CAS unlock
     unlock           your TTL expired
  3. work > TTL     → lease expires mid-work → 2 holders → TTL >> work + watchdog(Extend)
     (lease overrun)   (a CORRECT lock still fails here)   + idempotent write + FENCING

FENCING TOKEN (the only real correctness fix)
  acquire: token = INCR fence:res      (monotonic)
  write:   resource.write(token, data)
  resource: reject if token < highest_seen   ← REQUIRED. token is theater without this.

THE REDLOCK DEBATE (synthesis)
  Kleppmann: no timeout lock is correct without fencing. (right)
  antirez:   if you can fence/CAS the resource you didn't need the heavy lock. (also right)
  → efficiency: single-instance SET NX EX.  correctness: fix the RESOURCE, not the lock.
  → MT runs redsync on ONE ElastiCache cluster = single-instance semantics, NOT true Redlock.

MINDTICKLE'S 8 LOCKS (all efficiency locks; NONE fence)
  redsync (safer, internal CAS-unlock): content-center-svc(180s), content_search(2m),
    upload-mgmt folder(2s) + TUS(20s, cleanest — checks unlock err)
  SETNX + plain DEL (has the 3.3 bug, but tolerable — efficiency only):
    ai-tutor invite_email(60s,"1") | copilot-chat session-init(500ms ⚠) |
    external-sharing share-link(10s,"locked") | asset-hub trending(20s,"100", dead code)

LUA SCRIPTS AND FUNCTIONS (3.8)
  EVAL src n k.. a..      -> cache by SHA1, then run     EVALSHA sha n k.. a.. -> hash only
  NOSCRIPT No matching script. Please use EVAL.        -> the cache was emptied
  emptied by: restart | failover (SCRIPT LOAD not replicated since 7.0) | SCRIPT FLUSH
  evicted:    500 EVAL scripts, LRU, since 7.4. SCRIPT LOAD ones never. INFO evicted_scripts
  kept by:    DEBUG RELOAD (it reloads the data set only)
  fallback:   go-redis Script.Run, redsync -> EVAL   | redis-py -> SCRIPT LOAD + EVALSHA
  pipelines:  EVAL, or load the scripts before sending
  keys:       every key in KEYS. One hash tag: {summary:42}:lock {summary:42}:fence
  replication since 7.0: the script's writes, in MULTI/EXEC if more than one, never the script
  busy-reply-threshold (alias lua-time-limit) 5000 ms -> then BUSY for everyone else
    SCRIPT KILL: OK before the first write | UNKILLABLE after -> wait, or SHUTDOWN NOSAVE (loses data)
    Sentinel: BUSY to PING while down -> one SCRIPT KILL -> failover -> the script's writes lost
  read-only: EVAL_RO EVALSHA_RO FCALL_RO, flag no-writes
  FUNCTIONS: FUNCTION LOAD [REPLACE] "#!lua name=lib ..."    FCALL fn n k.. a..
    in RDB + AOF + replicated | cluster: load on EVERY primary yourself
    FUNCTION DUMP -> FUNCTION RESTORE payload APPEND (default) | REPLACE | FLUSH
    flags: no-writes allow-oom allow-stale no-cluster allow-cross-slot-keys
  VALKEY 9.1: Lua is a module, BUILD_LUA=static (default) | module | no
              global "server", alias "redis" | SCRIPT SHOW sha | SCRIPT LOAD protects from eviction

INVESTIGATE
  PTTL <lockkey>   → ms left on the lease (who holds it, how long)
  MONITOR          → watch SET NX / DEL in real time
  GET <lockkey>    → whose token holds it right now
```

---

*Next: Phase 4 — Architecture & HA. RDB vs AOF persistence, async replication and the data-loss window, Sentinel vs Cluster mode, and AWS ElastiCache specifics — anchored to Mindtickle's cluster-mode split (prod-US enabled 5.0.6 / prod-EU disabled 6.x) and the Equip cluster-mode-upgrade incident. Say `next`.*
