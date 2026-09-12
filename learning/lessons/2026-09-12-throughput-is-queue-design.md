# Throughput is queue design

**Where this sits.** AI systems, your current subject, on the serving side.
It also feeds the phase 3 replica build. Neither article is on your exemplar
list: the vLLM post is newer and deeper than "How LLM Inference Works", and
your bar says the newer one wins.

## The one idea

A fast thing feeds a slow thing. That join is a **seam**.

In MySQL replication, the fast thing is the primary. It can commit thousands
of row changes a second. The slow thing is the replica, which by default
applies them one transaction at a time.

In vLLM, the fast thing is prefill. The GPU can read a huge prompt in one
pass. The slow thing is decode: one token per step, and each step reads the
whole model's weights from memory.

When work arrives faster than the slow side can take it, you have exactly
two options:

1. **Buffer it.** Accept the work, park it somewhere, fall behind.
2. **Refuse it.** Don't accept it yet. Make the caller wait at the door.

That's the whole lesson. Everything else is detail on those two options, and
on one question: **who pays for the choice?**

## MySQL buffers

Two threads run on the replica.

The **I/O thread** pulls events from the primary and writes them, unchanged,
into a local file called the **relay log**. That file is the buffer.

The **applier thread** reads the relay log and actually executes the changes.

When the primary runs hot, the I/O thread keeps up easily — it is just
copying bytes. The applier falls behind. The unapplied part of the relay log
grows. Nothing errors. Disk fills quietly.

**About `Seconds_Behind_Master`.** People treat this as "how big the backlog
is". It isn't. It compares the timestamp of the event the applier is working
on right now against the replica's clock. So it measures *applier* delay
only.

That has a nasty consequence: if the network dies and the I/O thread stops
pulling, the applier finishes what it has and `Seconds_Behind_Master` reports
**0** — while you are minutes behind. Zero can mean "healthy" or "not
receiving anything". You cannot tell them apart from that number alone.
Check that the I/O thread is actually running too.

## vLLM refuses

vLLM keeps two queues: **waiting** and **running**.

To generate tokens for a request, the GPU must store that request's
attention keys and values — the **KV cache**. vLLM allocates that memory in
fixed chunks of 16 tokens, called **blocks**.

The rule is simple: a request only moves from waiting to running if the KV
cache manager can guarantee it enough blocks for its next step. No blocks, no
admission. It waits at the door.

The point is what this protects. A request that is already generating never
stalls halfway through for want of memory. The cost lands on the new
request's **time to first token** instead.

Refusing is cheap here because of how the batch is laid out. All sequences
are concatenated into one long flat row of tokens, with no padding. So a
request can join or leave the batch at any token boundary. That is what
"continuous batching" means: the batch is re-formed every step, not held
until the slowest member finishes.

## Who pays

That's the real decision at every seam.

| | MySQL's answer | vLLM's answer |
|---|---|---|
| Excess work waits | in the relay log (on disk) | in the waiting queue |
| Who feels it | whoever reads the replica — they get stale data | the new request — slower first token |
| The number to watch | applier lag, plus "is the I/O thread alive?" | queue wait and time to first token |

Buffering hides the problem and costs you freshness. Refusing shows the
problem immediately and costs you admission latency. Neither is free, and a
system that appears to have no cost is usually hiding it somewhere you're not
measuring.

## The third move: chop the big job

Once you have buffer and refuse, one more lever appears: make the big item
smaller.

A 100,000-token prompt processed in a single step would hold the GPU for
seconds. Every request already generating gets nothing during that time. That
is **head-of-line blocking**: one big job at the front stalls everyone behind
it.

**Chunked prefill** caps how many prompt tokens are processed per step. The
long prompt is spread across several steps, and each step also carries the
ongoing decodes. The long request's first token arrives later. Everyone else
keeps a smooth stream.

The knob is `--max-num-batched-tokens`: the token budget per step, shared
between prefill chunks and decodes. Smaller budget, smoother decodes, slower
prefill. That is the trade, stated out loud.

Two more things vLLM does, same reasoning:

- **Prefix caching.** If two prompts start with the same 16-token block, the
  KV for that block is computed once and reused. The best way through a seam
  is not to send the work at all. Only *complete* blocks are cached, so a
  prompt ending mid-block re-computes its tail.
- **Speculative decoding.** Decode is limited by memory bandwidth, not by
  arithmetic — the GPU's math units sit idle waiting for weights. So a small
  cheap model guesses several tokens ahead, and the big model verifies them
  all in one pass. A rejection sampler keeps the output distribution
  identical to what the big model alone would have produced.

## One knob that lies

**Semi-synchronous replication** makes the primary wait for at least one
replica to confirm it received the transaction before reporting commit. It
sounds like durability.

The default timeout is **10 seconds**. On timeout, the primary silently
switches to plain asynchronous replication and keeps going.

So the guarantee holds while the network is fast, and disappears exactly when
the network is slow — which is the only time you needed it. It does not warn
you. If you need a real durability bound, you need consensus, not semi-sync.

## Fifteen minutes today

Watch a buffer fill. Two containers, `mysql:8.4`.

```yaml
# docker-compose.yml
services:
  primary:
    image: mysql:8.4
    command: --server-id=1 --log-bin=binlog --gtid-mode=ON
             --enforce-gtid-consistency=ON
    environment: { MYSQL_ROOT_PASSWORD: root }
    ports: ["3306:3306"]
  replica:
    image: mysql:8.4
    command: --server-id=2 --read-only=ON
    environment: { MYSQL_ROOT_PASSWORD: root }
    ports: ["3307:3306"]
```

Row-based binlog is already the default in 8.0+, so you don't need to set it.

```sql
-- on the primary
CREATE USER 'repl'@'%' IDENTIFIED BY 'repl';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';
CREATE DATABASE bench;
CREATE TABLE bench.t (id BIGINT PRIMARY KEY AUTO_INCREMENT, v INT);

-- on the replica
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='primary', SOURCE_PORT=3306,
  SOURCE_USER='repl', SOURCE_PASSWORD='repl',
  SOURCE_AUTO_POSITION=1;
START REPLICA;
```

Now freeze the slow side and keep the fast side running:

```sql
-- replica: stop applying, keep receiving
STOP REPLICA SQL_THREAD;

-- primary: insert in a loop for a minute
-- replica: watch it climb
SHOW REPLICA STATUS\G
```

Look at three fields together, not one:

- `Replica_IO_Running` — still Yes? Then you are receiving.
- `Seconds_Behind_Master` — climbing. That's applier delay.
- `Relay_Log_Space` — growing. That's the buffer, in bytes.

Then `START REPLICA;` and watch it drain. Time the drain. Now try again with
`SET GLOBAL replica_parallel_workers = 4;` on the replica and compare.

(In 8.4, transactions are already marked with WRITESET dependency information
by default, so non-conflicting transactions can apply in parallel. On 8.0 you
had to set `binlog_transaction_dependency_tracking = WRITESET` yourself; that
variable is deprecated now.)

You have just built the observable half of your phase 3 replica build — a lag
counter — before writing any Go.

**And the build itself?** If the Bitcask-style store from phase 2 isn't
running yet, there is nothing for a replica to attach to. Reading has outrun
building.

## Where it breaks

- **`Seconds_Behind_Master` = 0 can mean "disconnected".** Always check
  `Replica_IO_Running` alongside it.
- **Statement-based replication diverges silently.** `SYSDATE()`, `UUID()`,
  `RAND()`, `LIMIT` without `ORDER BY`, and user-defined functions all give
  different answers on the replica. No error, just wrong data found weeks
  later. (`NOW()` is safe — the statement's timestamp is replicated with it,
  which is exactly why `SYSDATE()` is not: it reads the clock at execution.)
- **Row-based apply needs primary keys.** The applier finds each row by
  primary key. Without one, every UPDATE and DELETE becomes a full table scan
  on the replica, one event at a time.
- **A weak replica cannot absorb, only fall behind.** If the replica has less
  CPU or slower disk than the primary, parallel workers won't save you. The
  drain rate is structurally below the fill rate.
- **Chunked prefill isn't free.** The long request's first token gets slower,
  and prefill runs a little less efficiently. Right trade with many
  concurrent users, wrong trade when one request owns the machine.
- **Prefix caching only shares complete blocks.** A prompt ending mid-block
  recomputes that tail every time.

## Two posts you could write

- **"Seconds_Behind_Master lies to you twice."** It measures applier delay,
  not backlog, and it reads 0 when you're disconnected. Yours because you can
  demo both states with two containers and a screenshot.
- **"A vLLM scheduler and a MySQL replica solve the same problem."** At every
  seam you either buffer or refuse, then choose who pays. Yours because you
  can put KV-block admission beside the relay log with real flags and real
  status fields — nobody puts those two side by side.

## Sources

- *Inside vLLM: Anatomy of a High-Throughput LLM Inference System*, Aleksa
  Gordic — https://blog.vllm.ai/2025/09/05/anatomy-of-vllm.html
  (digest: `quarantine/2026-09-12-vllm-anatomy-study.md`; the extraction was
  truncated inside distributed serving, so benchmarking is not covered here)
- *MySQL Replication Internals*, Arpit Bhayani —
  https://arpitbhayani.me/blogs/mysql-replication-internals/
  (digest: `quarantine/2026-09-12-mysql-replication-internals-study.md`)

*Corrections applied on review: `Seconds_Behind_Master` measures applier
delay rather than relay-log size and reads 0 when disconnected; `NOW()` is
safe under statement-based replication while `SYSDATE()` is not; WRITESET
dependency tracking is the default in MySQL 8.4 and its variable is
deprecated.*
