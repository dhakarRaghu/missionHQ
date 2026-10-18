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

Because Lua runs atomically on the single command thread (Phase 0.1), nothing can slip between the `GET` and the `DEL`. Now A's stale release at t=3 finds the value is B's token, not A's, and refuses — B's lock survives. This is exactly what `redsync` does internally, and it's why the `redsync`-based Mindtickle locks are structurally safer than the hand-rolled `SETNX` ones (3.7).

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
2. **Lock extension / watchdog:** a background goroutine renews the lease (re-`PEXPIRE` while you still own it) as long as work continues. `redsync` supports `Extend()`. This shrinks but never closes the window — the watchdog itself can be paused.
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

---

## 🏢 Mindtickle anchor — things to check in the codebase

1. **The safe end (redsync).** Open `content-center-service/src/infrastructure/dispatch/packet/redis_packet.go` — `AcquireLock` (`redsync.NewMutex(key, WithExpiry(180s))`) and `ReleaseLock` (checks `ok` bool + err). Then find the *caller* in `UploadedMediaAssetFacade.go`: it's `defer facade.redisClient.ReleaseLock(ctx, mutex)` — the returned error is discarded. Question: does discarding the unlock error create a *correctness* bug here, given `redsync`'s internal CAS-unlock? (No — CAS-unlock still can't delete another's lock; discarding the error just means you won't *notice* a failed unlock, a observability gap, not a safety one.)

2. **The unsafe end (SETNX + plain DEL).** Open `ai-tutor/src/usecase/invitation/lock.go`: `SetNX(ctx, key, "1", 60s)` in a retry-until-deadline loop, released with a `defer` plain `Delete`. Reproduce its bug with E3. Question: is this an incident? (No — efficiency lock for email dedup; the double-fire cost is a duplicate email. The implementation is *sloppy* but *appropriate* for the risk. That judgment is the whole skill.)

3. **The one to actually worry about.** `copilot-chat-agent/.../RedisClient.go` uses a **500ms** TTL (`REDIS_TTL_FOR_INIT_RESUME_SESSION_LOCK`) on a session-init lock. Question: what's the worst-case latency of session init (LLM warm-up? gRPC to another service?), and how often would it exceed 500ms? Run E9. If init routinely takes >500ms, the lock is providing *less* protection than its existence implies — a false sense of safety.

4. **The dead lock + the dangerous comment.** In `asset-hub-analytics`, the `RLock`/`RUnLock` call sites are commented out with "we do not need to take a lock here, since redis is always atomic." Find the code that runs *instead*. Question: is it a single atomic op (comment is right) or a read-modify-write across multiple ops (comment is dangerously wrong — Phase 0.1 says only *individual* commands are atomic)? This is the exact confusion E11 targets.

---

## ✅ Checkpoint 3 — answer in your own words

**Q1.** For each of these, say "efficiency" or "correctness" and justify, then state whether Mindtickle's actual implementation is adequate: (a) ai-tutor deduping invitation emails; (b) a hypothetical lock ensuring a customer's subscription is charged exactly once; (c) copilot-chat-agent preventing duplicate chat sessions; (d) a lock ensuring a ledger balance is decremented once. Which of (a)–(d) could safely use the existing `SETNX`+plain-`DEL` pattern, and which absolutely could not?

**Q2.** Walk through the plain-`DEL` bug with ai-tutor's exact lock (`SetNX(key,"1",60s)`, `defer Delete(key)`). Give a concrete timeline where worker A deletes worker B's lock. Then: why does switching the value from `"1"` to a random UUID + a Lua compare-and-delete fix *this specific* bug — and what deeper bug does it *not* fix?

**Q3.** copilot-chat-agent uses a 500ms lock TTL on session init. Session init makes a gRPC call that's normally 80ms but occasionally 1.2s under load. Show the timeline for the 1.2s case: what happens to the lock, and can two session-init flows run concurrently? Propose two fixes and state which you'd ship.

**Q4.** Explain the Redlock debate to a colleague in four sentences: what Kleppmann claims, what antirez replies, why they're *both* right, and what you should therefore do for (a) an efficiency lock and (b) a correctness lock. Then: Mindtickle runs `redsync` (the Redlock library) against a single ElastiCache cluster — what guarantee does that actually give, and what does it NOT?

**Q5.** Design a fencing-token scheme for a hypothetical "generate exactly one invoice PDF per order" flow, where the PDF is written to S3. Give: the acquire (with token), the write (with token), and exactly what the *resource* (S3 + your metadata) must do to reject a stale writer. Then explain why, per antirez, this scheme means you might not have needed the distributed lock at all.

**Q6.** The asset-hub-analytics comment says "we do not need a lock, since redis is always atomic." Give one operation where that comment is *correct* and one where it's *dangerously wrong*, using the trending-assets ZSet+List design from Phase 1.5 (record-a-view = LPOP oldest + ZIncrBy decrement + RPUSH new + ZIncrBy increment). Is that sequence safe without a lock? Why or why not, and what would make it safe?

**Q7.** You're reviewing an MR that adds a `SETNX`+plain-`DEL` lock (copied from ai-tutor) to guard a new flow that decrements a customer's "remaining AI credits" and calls a paid third-party API. Write the review comment: what's wrong, what's the risk in concrete terms, and what three changes would you require before approving (ordered by importance)?

---

## References & Further Learning

**Must-read (in order — this is a debate, read both sides):**
- 📄 [How to do distributed locking — Martin Kleppmann](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html) — THE critique. Efficiency vs correctness, the pause problem, and fencing tokens explained with diagrams. (25 min) Read BEFORE 3.4–3.5. Non-negotiable.
- 📄 [Is Redlock safe? — antirez's rebuttal](http://antirez.com/news/101) — the other side, by Redis's creator. The check-and-set-with-unique-token counterargument and the semi-synchronous timing model. (20 min) Read immediately after Kleppmann.
- 📄 [Redlock algorithm — official Redis docs](https://redis.io/docs/latest/develop/use-cases/patterns/distributed-locks/) — the canonical single-instance lock recipe (SET NX PX + Lua unlock) AND the multi-master Redlock spec. (15 min) The recipe in the first half is exactly `safe_lock`.

**Deep dives:**
- 📄 [redsync — the Go Redlock library](https://github.com/go-redsync/redsync) — read `mutex.go`: `Lock`, `Unlock` (the Lua CAS), `Extend` (the watchdog). This is what content-center-service/upload-management use. (20 min) Read the source after 3.3.
- 🎥 [Martin Kleppmann — "Distributed systems" lecture series](https://www.youtube.com/playlist?list=PLeKd45zvjcDFUEv_ohr_HdUFe97RItdiB) — the Cambridge course; the consistency & consensus lectures give the theory under the debate. (per-video ~50 min) For when you want the foundations.
- 📄 [Chubby / "The Chubby lock service" — Google (Burrows, OSDI'06)](https://research.google/pubs/pub27897/) — the paper that defined distributed lock services; where fencing (sequencers) comes from. (45 min) The canonical source.
- 📚 *Designing Data-Intensive Applications* (Kleppmann), Ch. 8 "The Trouble with Distributed Systems" & Ch. 9 "Consistency and Consensus" — the definitive treatment of process pauses, fencing tokens, and why locks are hard. Read Ch. 8 §"Process Pauses" alongside 3.4.

**Official docs (bookmark):**
- [SET command options](https://redis.io/commands/set/) — `NX`, `XX`, `PX`, `EX`, `GET`, `KEEPTTL`.
- [EVAL / Lua scripting](https://redis.io/docs/latest/develop/interact/programmability/eval-intro/) — for the atomic compare-and-delete and beyond.

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

INVESTIGATE
  PTTL <lockkey>   → ms left on the lease (who holds it, how long)
  MONITOR          → watch SET NX / DEL in real time
  GET <lockkey>    → whose token holds it right now
```

---

*Next: Phase 4 — Architecture & HA. RDB vs AOF persistence, async replication and the data-loss window, Sentinel vs Cluster mode, and AWS ElastiCache specifics — anchored to Mindtickle's cluster-mode split (prod-US enabled 5.0.6 / prod-EU disabled 6.x) and the Equip cluster-mode-upgrade incident. Say `next`.*
