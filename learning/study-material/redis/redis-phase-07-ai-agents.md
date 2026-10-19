# Phase 7 — Redis for AI agents

An AI agent is a program that calls a model in a loop, calls tools, and keeps state. Agent platforms use Redis for six jobs: answer cache, embedding cache, memory, token streams, limits, and a tool-call queue. Each job looks like a pattern from Phases 1 to 3, but breaks in a new way: the data is probabilistic, long-running, and paid per token.

After this phase you can build and size each job. If you skip it, you meet the failures in production. Examples: one tenant's cached answer served to another, and a budget that admits 6 calls instead of 15.

**The running case.** A support agent platform serves two tenants, acme and globex. API pods take user questions, call a model provider, call paid tools, and stream answers to a web page. Every lab is a part of that platform.

## What we cover in Phase 7

```
┌──────────────────────────────────────────────────────────┐
│  7.1  Where Redis sits      — six jobs, what each loses  │
│  7.2  Answer caching        — semantic, threshold, scope │
│  7.3  Vector search         — vector sets, Query Engine  │
│  7.4  Agent memory          — field TTLs, history        │
│  7.5  Token streams         — one stream each, resume    │
│  7.6  Limits for LLM calls  — tokens, leases, 429s       │
│  7.7  Tool-call queues      — paid-call idempotency      │
└──────────────────────────────────────────────────────────┘
```

**Prerequisites.** Phase 1.2 hashes, 1.3 lists, 1.5 sorted sets and 1.6 Streams. Phase 2.3 stampedes and 2.5 invalidation. Phase 3.2 to 3.5 locks, leases and fencing. Phase 4.1 persistence and 4.2 replication. Phase 5.5 eviction.

**Where the labs run.** Go programs in `code/phase07_ai_agents/` run against a throwaway `redis-server` 8.10.1 on port 6571. That build has vector sets, hash field TTLs and `INCREX`. It has no Query Engine, so `FT.*` steps are written and marked "not run". Redis 8.10.2, of 2026-09-17, is a security release, and the labs ran on 8.10.1. Verified in its release notes. No lab calls a model. The embeddings are fake and deterministic. **Costs at most: $0.**

Time: 6 to 9 hours.

**Evidence labels.** Every claim is verified, inferred, or not checked. "Vendor" marks a source from the seller of the product. Sources were fetched and labs measured on 2026-10-19, on an Apple M4 Pro with the x86_64 Redis 8.10.1 build under Rosetta 2. Latencies are higher than on a native build. This build reports `mem_allocator:libc`, not jemalloc, so `MEMORY USAGE` bytes can differ on Linux.

---

## 7.1 — Where Redis sits in an agent system (six jobs, and what each may lose)

Why this matters: one Redis often holds data that is cheap to lose and data that is not. Know which before you set eviction, persistence and TTLs.

**The mental model.** Redis does six jobs for an agent. Four hold data that you can rebuild. Two hold data that someone paid for or that a user expects to see again.

```
┌──────────────┐  question   ┌──────────────┐  prompt   ┌──────────────────┐
│ Web page     ├────────────►│ API pod (x N)├──────────►│ Model provider   │
│              │◄────────────┤              │◄──────────┤ RPM, TPM, 429s   │
└──────────────┘ token SSE   └──────┬───────┘  tokens   └──────────────────┘
                                    │
       ┌────────────────────────────┼─────────────────────────────┐
       ▼                            ▼                             ▼
┌──────────────────────┐ ┌──────────────────────┐ ┌───────────────────────┐
│ Redis: may lose      │ │ Redis: must not be   │ │ Durable store         │
│ answer cache   7.2   │ │ the only copy        │ │ Postgres or similar   │
│ embedding cache 7.2  │ │ working memory  7.4  │ │ transcripts, runs,    │
│ token streams  7.5   │ │ tool-call queue 7.7  │ │ long-term memory,     │
│ limit counters 7.6   │ │                      │ │ tool results, billing │
└──────────────────────┘ └──────────────────────┘ └───────────────────────┘
```

| Job | If Redis loses it | Durable copy |
|---|---|---|
| Answer and embedding cache | more paid calls | no |
| Token stream | a viewer reloads the answer | the final answer |
| Limit counter | a short burst over the limit | no |
| Working memory | the agent forgets the session | yes, if a user can return |
| Tool-call queue | a paid call is lost or runs twice | the call and its result |

**What the defaults give you.** Verified in `redis.conf` at 8.10.2 and the Redis docs:

- AOF is off by default. With `appendfsync everysec`, a crash loses up to about 1 second of writes. With the default rules, `save 3600 1 300 100 60 10000`, RDB alone can lose up to an hour of writes. See Phase 4.1.
- `maxmemory-policy` defaults to `noeviction`. With `allkeys-lru`, Redis evicts memory keys that have no TTL. See Phase 5.5.
- Replication is asynchronous, so a failover can lose `XADD` writes. See Phase 4.2.

**Two published cases.**

1. LangSmith Agent Server, vendor docs. Redis carries the worker wake-up list, cancel signals, the pub/sub stream of output, and a retry counter. The docs say: "No user or run data is stored in Redis." Postgres holds runs, threads, state and long-term memory. Verified, LangSmith data-plane page, line 34.
2. Inngest, vendor blog of 2026-09-09. Its queue "has run on Valkey". The post says a hard failure of the in-memory store can lose data. Inngest is moving the queue to FoundationDB. Verified.

**The sentence to remember:** Redis may be the only home of data you can rebuild. Everything else also goes to a durable store.

**The trap:** one shared Redis with `allkeys-lru` for the cache and for working memory. Under memory pressure, Redis then evicts live sessions like stale cache entries. Put each class in its own instance, or give the memory keys TTLs and `volatile-lru`.

**Try this now:** on a Redis you own, run `redis-cli CONFIG GET maxmemory-policy appendonly`. For each of the six jobs it holds, check the "Durable copy" column.

---

## 7.2 — Exact and semantic caching of LLM answers (thresholds, scope, TTL)

Why this matters: a cache hit skips a model call that costs seconds and money. A wrong hit returns a confident wrong answer, and no log line marks it.

You might expect exact-match caching to work for prompts. The lab shows otherwise. An exact-match cache keys the answer by a hash of the normalised prompt. In the lab set of 26 user questions, it hit 2. Users rarely type a sentence twice.

**The mental model.** A semantic cache stores each answer with the embedding of its prompt. An embedding is a vector that a model makes to represent a text's meaning. For a new prompt, the cache finds the nearest stored prompt, and returns its answer if the similarity is above a threshold. Cosine similarity is the cosine of the angle between two vectors. It is 1 for the same direction.

```
┌──────────┐ prompt ┌──────────┐ vector ┌──────────────────────────┐
│ API pod  ├───────►│ embedder ├───────►│ Redis: nearest prompt in │
│          │        └──────────┘        │ scope tenant + model ver │
│          │◄───────────────────────────┤ returns answer, cos      │
└────┬─────┘  cos >= threshold: HIT     └──────────────────────────┘
     │        cos <  threshold: MISS
     ▼
┌──────────────────┐ answer ┌────────────────────────────────────┐
│ model provider   ├───────►│ store prompt vector + answer + TTL │
└──────────────────┘        └────────────────────────────────────┘
```

**How RedisVL does it.** RedisVL is Redis's Python AI library. `SemanticCache` defaults, verified in `semantic.py` at v0.28.0:

| Setting | Default | Note |
|---|---|---|
| `distance_threshold` | 0.1 cosine distance | distance = 1 minus similarity, so about 0.9 similarity |
| `ttl` | None | entries never expire |
| TTL on hit | refreshed on every matched key | a hot entry never expires |
| index | FLAT, COSINE | every check compares with every entry |
| entry ID | SHA-256 of prompt and filter values | the model version is not in the ID |

LangCache, Redis's managed semantic cache, defaults to a similarity threshold of 0.85 and no expiration. Verified, vendor.

**The threshold, measured.** The lab `semcache` stores 16 answers and asks 26 questions, each labelled with its right answer or "none". The embeddings are a hashed bag of words, so the numbers show the mechanism, not a real model. Measured, Q8 vectors, tenant filter on:

```
 threshold   hits        correct   wrong hits   right answers missed
 0.60  ████████████████████████████  22    15    7  ███████          1
 0.70  ███████████████████████       18    15    3  ███              1
 0.78  █████████████████████         16    14    2  ██               2
 0.85  ████████████████              12    11    1  █                5
 0.90  █████████████                 10    10    0                   6
 exact-match cache                    2     2    0                  14
```

Two wrong hits explain the problem:

```
 cosine to the nearest cached prompt
 0.70        0.75        0.80        0.85        0.90
 ├───────────┼───────────┼───────────┼───────────┼──────►
                  ▲         ▲            ▲
                  │         │            └─ 0.866 "price of the Pro Max plan?"
                  │         │               nearest: "Pro plan" -> WRONG
                  │         └─ 0.800 "refund within 30 days?"  -> WRONG
                  │            0.800 "refund possible after 30 days?" -> right
                  └─ 0.775 "price of the Pro plan per month" -> right
```

The wrong question "Pro Max" is closer than the right paraphrase "Pro plan per month". The self-test proves both values in closed form. Three shared words between texts of 4 and 3 words give 3/sqrt(12) = 0.866. Three shared words between texts of 5 and 3 words give 3/sqrt(15) = 0.775. Any threshold that accepts the right one also accepts the wrong one.

**Published rates for real models.** Each source judged "wrong" in its own way.

| Source | Setup | Threshold | Hit rate | Wrong share of hits |
|---|---|---|---|---|
| AWS blog, 2025-11-26 | 63,796 Chatbot Arena queries, Titan v2, ElastiCache for Valkey 8.2 | 0.99 | 23.5% | 7.9% |
| same | same | 0.90 | 74.5% | 7.7% |
| same | same | 0.75 | 90.3% | 8.8% |
| vCache paper, Table 3 | SemCacheLMArena, E5-large-v2 | 0.99 | 37% | 6.8% |

The AWS wrong share is 100% minus its reported "accuracy". The post does not say how it judged correctness. Verified on the AWS page. vCache counts wrong hits as a share of all prompts: 2.5% at 0.99. As a share of hits that is 2.5 / 37 = 6.8%. vCache also found that right and wrong hits had almost the same mean similarity, 0.84 and 0.85. It says one threshold "is not a reliable decision boundary". Verified on arxiv.org/html/2502.03771. vCache learns a threshold per cached entry instead.

In the AWS test, 0.99 instead of 0.75 cut the hit rate from 90.3% to 23.5%, but the wrong share only from 8.8% to 7.9%. A high threshold mostly removes right hits.

**Cost arithmetic.** The AWS run cost $49.5 a day without a cache. At threshold 0.75 it cost $6.8, a saving of 1 - 6.8/49.5 = 86.3%, with 8.8% of hits wrong. You trade money for wrong answers.

**Scope.** An entry is valid only for the context that produced it: the tenant, the locale, the model version and the prompt template version. Put each in the key name or a filter.

- With `-scope none`, the lab serves acme's CSV-export answer to a globex user at cosine 1.000, and globex's password answer to acme. With `-scope filter` or `-scope key`, both miss. Measured.
- langchain-redis `RedisSemanticCache` stores the model string in metadata and checks it after the vector search. It asks for one result, so if the nearest entry came from another model, the lookup misses even when the second is valid. Verified in `libs/redis/langchain_redis/cache.py`, lines 494 to 499. The effect on hit rate is inferred.

**TTL and invalidation.** Phase 2.5 covers delete-on-write, and Phase 2.3 covers TTL jitter. Three points are specific to LLM answers:

1. RedisVL refreshes the TTL on every hit, so a wrong answer that users hit often never expires. Inferred from the code. Delete it by ID when a user reports it.
2. AWS suggests a TTL of "around 23 hours" plus random jitter for data that changes daily. Verified, vendor.
3. Tag each entry with its source documents, and delete by tag when one changes. LangCache deletes entries by attributes. Verified, vendor.

**Provider prompt caching is different.** Anthropic and OpenAI cache the processed prompt prefix, and the model still generates a new answer. Anthropic's docs say prompt caching "has no effect on output token generation". Verified on platform.claude.com.

| | Semantic cache in Redis | Provider prompt caching |
|---|---|---|
| What is reused | the whole answer | the processed prompt prefix |
| Can return a wrong answer | yes | no |
| Saves output tokens | yes | no |
| Lifetime | your TTL | Anthropic 5 minutes by default, refreshed on use |

Use prompt caching for a long fixed system prompt, and a semantic cache for repeated questions.

**The sentence to remember:** a semantic cache trades wrong answers for saved calls, and in the AWS test no threshold removed them. Scope every entry by tenant, locale, model version and template version.

**The trap:** picking a threshold such as 0.95 because it "looks safe". In the AWS test, 0.99 still served 7.9% wrong hits. Label a sample of your prompts and measure both numbers.

**Try this now:**

    go run ./phase07_ai_agents/semcache -scope none

The `globex` line shows `HIT A05` and `WRONG answer served`.

---

## 7.3 — Vector search in Redis (vector sets, Query Engine indexes, memory)

Why this matters: the cache in 7.2, long-term memory in 7.4 and RAG retrieval all run a nearest-neighbour search. RAG, retrieval-augmented generation, adds found documents to the prompt. The index decides memory, recall and scaling.

**The mental model.** Redis 8 has two vector engines. Vector sets are a data type: one key holds the vectors and an HNSW graph. HNSW, Hierarchical Navigable Small World, is a layered graph that finds near neighbours by walking between nodes. The Query Engine indexes hashes or JSON documents with `FT.CREATE`, and adds filters, full text and automatic sharding. Recall is the share of the true nearest neighbours that the search returns.

```
┌───────────────────────────────────┬───────────────────────────────────────┐
│ Vector sets  VADD / VSIM          │ Query Engine  FT.CREATE / FT.SEARCH   │
├───────────────────────────────────┼───────────────────────────────────────┤
│ one key = vectors + HNSW graph    │ index over many hash or JSON keys     │
│ no schema                         │ schema: TYPE, DIM, DISTANCE_METRIC    │
│ Q8 int8 by default                │ TYPE is required, such as FLOAT32     │
│ filter on JSON attributes         │ TAG, NUMERIC, TEXT, GEO filters       │
│ one key = one shard: you split it │ shards across a cluster for you       │
│ ran on this build                 │ NOT on this build: FT.* unknown       │
└───────────────────────────────────┴───────────────────────────────────────┘
```

**Vector sets, one level down.** Verified in `modules/vector-sets` at 8.10.2:

- `VADD key FP32 <blob> <element> [Q8|NOQUANT|BIN] [M n] [EF n] [SETATTR json]` adds one vector. Q8 is the default.
- Q8 scales each vector to signed int8. BIN keeps one bit per dimension.
- `VSIM` returns (cos + 1) / 2. Convert it back before you compare it with a cosine threshold.
- Defaults: M 16, build EF 200, search EF 100, COUNT 10. EF is the size of the candidate list the search keeps.

**Memory and recall, measured.** The lab `vectorsets` loads 20,000 clustered synthetic vectors and runs 200 queries with k = 10. The truth comes from a brute-force search in Go on the float32 originals. Recall is the mean of three seeds:

```
 bytes per element, MEMORY USAGE / n, 128 dims, M 16
 NOQUANT  ████████████████████████████████████████  1,203   recall 1.000
 Q8       ███████████████████████████               819     recall 0.971
 BIN      ████████████████████████                  707     recall 0.15-0.18

 split: vector NOQUANT 512, Q8 128, BIN 16 bytes, + 691 bytes everything else
```

The "everything else" was 691 bytes at 128 and 384 dims, for every quantisation: the graph, the element name and the node. The README puts the links alone at 2.33 × M pointers of 8 bytes: 298 bytes at M 16. So at 128 dims Q8, the graph and node cost 5.4 times the vector, and quantisation saves less than you expect.

1 million vectors of 1,536 dims, plus 691 bytes each, take about 6.8 GB with NOQUANT and 2.2 GB with Q8. Inferred from the 128-dim and 384-dim runs. Check it at 1,536 dims before you size a node.

**EF trades latency for recall.** Q8, 128 dims, seed 1. Repeat runs gave 0.865 and 0.868 at EF 10:

| EF | recall@10 | p50 µs | p99 µs |
|---|---|---|---|
| 10 | 0.870 | 238 | 378 |
| 100, the default | 0.975 | 269 | 414 |
| 500 | 0.975 | 476 | 759 |

p50 and p99 are the median and the 99th percentile of the client round trip. Recall stopped at 0.975 for Q8, and NOQUANT reached 1.000. So the int8 rounding set the limit, not the search. Inferred from the NOQUANT row. The README's Word2Vec test measures search error only. Its int8 key found 95.98% of what a linear scan of the same key found. Its BIN key found 35.48%. Verified, vendor author.

BIN on sparse vectors is worse. With `semcache -quant BIN`, all 26 questions hit at every threshold, and 11 hits were wrong. Measured.

**Scaling a vector set.** A vector set is one key, so it lives on one shard. The README says to split it into N keys, query each, and merge by score. With 4 keys in the lab, recall stayed at 0.975. p50 rose from about 270 µs to 1,033 to 1,173 µs with 4 sequential calls, over five runs. Parallel calls would cut that. Inferred.

**The Query Engine.** Not run on this build. Verified from the redis.io vector docs:

```bash
# NOT RUN: this build has no Query Engine (FT.CREATE is an unknown command)
FT.CREATE idx:sem ON HASH PREFIX 1 sem: SCHEMA \
  tenant TAG  model TAG \
  vec VECTOR HNSW 6 TYPE FLOAT32 DIM 768 DISTANCE_METRIC COSINE
FT.SEARCH idx:sem "(@tenant:{acme} @model:{chat_v202609})=>[KNN 1 @vec $B]" \
  PARAMS 2 B <768 float32 bytes> LIMIT 0 1 DIALECT 2
```

- FLAT compares with every vector and suits under 1M vectors. HNSW defaults are M 16, EF_CONSTRUCTION 200, EF_RUNTIME 10. SVS-VAMANA arrived in Redis 8.2 and uses less memory.
- SVS compression with LVQ and LeanVec is not in Redis Open Source.
- A filter before `=>` makes a hybrid query. Redis filters batches of neighbours, or scores every document that passes.

**When Redis is the right vector store.** No neutral benchmark was found. Redis's and Qdrant's each put their own product first. Rules inferred from the sources and the lab:

| Situation | Choice |
|---|---|
| Redis is already in the stack, up to a few million vectors, simple filters | Redis |
| Similarity only, no full text, you can split keys yourself | vector sets |
| Filters with text, numbers or geo, or automatic sharding | Query Engine |
| Tens of millions of vectors | price the RAM first: 50M × 768 × 4 bytes = 153.6 GB before the graph |
| Valkey | valkey-search: `FT.*` with HNSW and FLAT, and `FT.HYBRID` in 1.3.0-rc1. No vector sets: issue 2569 is open. Verified |

**The sentence to remember:** at M 16 a vector set element costs about 691 bytes plus the vector. Q8 caps recall below NOQUANT, and one vector set is one shard.

**The trap:** sizing memory from the vector bytes alone. At 128 dims Q8, the vector is 128 bytes and the element is 819 bytes. A plan built on 128 bytes is 6.4 times too small.

**Try this now:**

    go run ./phase07_ai_agents/vectorsets -dim 384 -shards 1 -efs 10,100,500

Compare the `B/elem` and `vector B` columns. The gap is the same in every row.

---

## 7.4 — Agent memory (field TTLs, bounded history, and what must be durable)

Why this matters: memory decides what the model sees next. Without a bound, the prompt and the bill grow. If it disappears, the user repeats themselves.

**The mental model.** Agent memory has four tiers, each with its own lifetime and type.

```
┌───────────────────────────────────────────────────────────────────────┐
│ working memory   hash per session     goal, plan, tool results        │
│                  key TTL 30 min, field TTLs for stale tool results    │
├───────────────────────────────────────────────────────────────────────┤
│ history          list per session     last N messages, RPUSH + LTRIM  │
│                  trimmed again by tokens before each model call       │
├───────────────────────────────────────────────────────────────────────┤
│ long-term        vectors + text       facts about the user            │
│                  Redis index for recall, durable store for the truth  │
├───────────────────────────────────────────────────────────────────────┤
│ checkpoints      graph state per step  resume a run after a crash     │
│                  durable store, or Redis with AOF and a TTL           │
└───────────────────────────────────────────────────────────────────────┘
```

**Field TTLs, one level down.** `HEXPIRE` exists since Redis 7.4, and `HSETEX` and `HGETEX` since 8.0. A small hash with field TTLs uses the `listpack_ex` encoding: field, value and TTL triplets ordered by TTL. Each database indexes these hashes by next field expiry. Active expiry deletes up to 10000/hz fields per call. Verified in the Redis 8.10.2 source. Valkey added `HEXPIRE` in 9.0.0 and converts any hash with a field TTL to a hashtable. Verified in the Valkey 9.1.2 source. The extra memory per small hash is inferred, not measured.

The `HEXPIRE` page states the rule that causes the most bugs. Field expirations "will only be cleared by commands that delete or overwrite the contents of the hash fields." Verified.

```bash
# WRONG: refresh a tool result with a plain HSET
HSETEX p7:wm:{acme:s-42} EX 60 FIELDS 1 tool:prices v1   # HTTL -> 60
HSET   p7:wm:{acme:s-42} tool:prices v2                  # HTTL -> -1, never expires
# RIGHT: write the value and its TTL in one command
HSETEX p7:wm:{acme:s-42} EX 60 FIELDS 1 tool:prices v3   # HTTL -> 60
```

The lab printed these HTTL values. Measured.

**Bounded history.** The lab appends 500 messages of about 150 bytes. The bounded list keeps 50 with `RPUSH`, `LTRIM -50 -1` and `EXPIRE` in one `MULTI`. Measured:

| List | LLEN | MEMORY USAGE | TTL |
|---|---|---|---|
| bounded, 500 turns | 50 | 8,003 bytes | 30 min |
| unbounded, 500 turns | 500 | 80,025 bytes | none |
| unbounded, 2,000 turns | 2,000 | 321,175 bytes | none |

A count bound is not a prompt bound: 50 messages can differ by ten times in tokens. So the app trims again by tokens before each call, keeping the system prompt and the newest messages that fit. In the lab, 21 messages and a 2,000-token budget gave 9 messages and 1,950 tokens.

**What the libraries do.** In the write paths of five libraries, none uses `HEXPIRE`. Verified.

| Library | Storage | TTL default | A fact to know |
|---|---|---|---|
| Redis Agent Memory Server, `V0/` | one JSON document per session | none | `JSON.SET`, then `EXPIRE` in a second call |
| langgraph-checkpoint-redis 0.5.2 | JSON + Search indexes per checkpoint | none | `default_ttl` is in **minutes** |
| OpenAI Agents SDK `RedisSession` | hash + list + counter | none | `WATCH` and `MULTI`, no `LTRIM` |
| LlamaIndex Redis chat store | one list per chat | none | no `LTRIM`, `KEYS *`, and `delete_message` reverses the order |
| mem0 | Redis as a vector store | none | change history goes to SQLite |

The lab reproduces the two-call failure: `SET` without a TTL, then a crash before `EXPIRE`, leaves `TTL=-1`. `SET ... EX` in one command leaves `TTL=30m0s`. Measured.

**A failure from production.** In OpenAI's ChatGPT outage of 2023-03-20, a client cancelled a Redis request before it read the reply. The next request on that connection read the old reply, so some users saw other users' data. Payment data of 1.2% of active ChatGPT Plus users may have been visible. Verified in the archived postmortem and redis-py issue 2624. Agents cancel many requests, because users stop answers. The OpenAI Agents SDK discards a connection after a cancel. Verified in `redis_session.py`, lines 576 to 582.

**The sentence to remember:** working memory is a hash with key and field TTLs. History is bounded by count in Redis, and by tokens before the call.

**The trap:** a plain `HSET` on a field that had a TTL. The field becomes permanent, and the app sends the stale tool result to the model on every turn.

**Try this now:**

    go run ./phase07_ai_agents/agentmemory -turns 2000 -keep 50

Compare the two `MEMORY USAGE` lines. Section 3 shows the HSET trap.

---

## 7.5 — Streaming LLM tokens that a client can resume (Streams per response)

Why this matters: an answer takes seconds to stream. Phones change networks, tabs sleep and load balancers drop connections. Without resume, the user sees half an answer.

You might expect fast pub/sub to be enough. Alone, it loses tokens in two ways:

1. Delivery is at most once: a message reaches only the subscribers connected at that moment. After a network disconnect, the docs say the message is "forever lost". Verified on the pub/sub docs.
2. Redis drops a slow subscriber. Unsent output waits in a buffer per client. The default `client-output-buffer-limit pubsub 32mb 8mb 60` closes the client at 32 MB, or after 60 s above 8 MB. Verified in `redis.conf` at 8.10.2, line 2476.

On the lab server, with `pubsub 1mb 0 0`, a subscriber stopped reading, and Redis sent it 400 messages of 10 KB. `INFO stats` showed `client_output_buffer_limit_disconnections:1`. Measured.

**The mental model.** Write each chunk of the answer to a stream, one key per response. The entry ID is the reader's position. A reader that reconnects calls `XREAD` with the last ID it saw, and gets the rest. In a web page, send the entry ID as the SSE event ID. SSE, Server-Sent Events, is the HTTP streaming format that browsers resume with a `Last-Event-ID` header.

```
 time ──────────────────────────────────────────────────────────────►
 producer  XADD + PUBLISH per token, sleep 2 ms, 400 tokens         ► done
 viewer    ├─ 100 tokens ─┤◄─ away 150 ms ─►├─ reconnects ──────────►
 stream    ████████████████░░░░░░░░░░░░░░░░░████████████████████████
           XREAD from the last ID: 400 of 400 tokens, text identical
 pub/sub   ████████████████                 ████████████████████████
           343 to 351 of 400 tokens, 49 to 57 LOST
```

Measured in the `tokenstream` lab, eight runs. The pub/sub subscriber lost one token every 2.6 to 3.1 ms of its 150 ms gap, and the stream viewer none.

**The design.**

1. Key `resp:{response_id}`. One key per response spreads load over slots. Inferred.
2. `XADD resp:{id} MAXLEN ~ 10000 * seq <n> t <chunk>`. `MAXLEN` guards against a runaway answer. The TTL is the normal bound.
3. `EXPIRE` at the first chunk and again at the end.
4. A final entry `done 1`. A reader stops there.
5. Viewers use plain `XREAD` with their own last ID. A consumer group per viewer keeps a pending list for nothing. Inferred from the Streams docs.
6. `XRANGE` is inclusive. To resume with it, start at `(<last id>`. `XREAD` is already exclusive.

**Stream internals.** A stream is a radix tree of listpack nodes of up to 4,096 bytes or 100 entries. Each node stores field names once, and IDs as deltas. Verified in `src/t_stream.c` at 8.10.2. So batching tokens saves memory. Measured, 2,000 tokens written one call at a time:

| Tokens per entry | XADD calls | Time | MEMORY USAGE | Bytes per token |
|---|---|---|---|---|
| 1 | 2,000 | 192 to 209 ms | about 37,000 | 18 to 19 |
| 8 | 250 | 23 to 27 ms | about 14,200 | 7 |

Batch by size and time, such as 8 tokens or 50 ms, so a slow model still shows text.

**Two published designs.**

- Vercel `resumable-stream` 2.2.13 keeps chunks in the producer's memory, not Redis. It uses pub/sub plus one sentinel key with `EX 86400`, and a second reader asks the producer to replay. If the producer process dies, the answer cannot resume. Inferred from the in-memory buffer.
- Upstash AgentKit `EventLog` writes each event with `XADD` and an `EXPIRE` of 86,400 s in one Lua script. Readers resume with `XRANGE key (lastId + COUNT 500` and poll every 250 ms. It has no `MAXLEN`. Verified in source, vendor.

**Stopping an answer.** The AI SDK docs say `stop()` only closes the connection, and a separate endpoint must cancel the work. Verified. Publish a cancel signal that the producer checks between chunks.

**The sentence to remember:** use one stream per response and resume from the entry ID. Set a TTL after the last chunk. Use pub/sub only to wake readers.

**The trap:** pub/sub alone for token delivery. Every reconnect loses the tokens of the gap. The lab lost 49 to 57 of 400 in 150 ms.

**Try this now:**

    go run ./phase07_ai_agents/tokenstream -gap 300ms

The `pub/sub viewer` line shows about twice the loss of the default run. The stream viewer still shows `400 of 400`.

---

## 7.6 — Limits for LLM calls (tokens, INCREX, semaphores, shared 429s)

Why this matters: providers limit tokens per minute and calls in flight, not only requests. If a limiter counts requests, a few long prompts use the whole budget. Then every pod gets 429, the HTTP status for "too many requests".

**What providers count.** Anthropic limits requests, input and output tokens per minute with a token bucket. OpenAI counts the larger of `max_tokens` and an estimate from the characters, and failed requests also count. Verified on both rate-limit pages. So a shared limiter reserves an estimate before the call and corrects it after.

```
 pod            Redis counter tpm:{acme}:model-x:<w>  provider
  │ INCREX BYINT 1500 UBOUND 10000 PX 60000 ENX ──►  value 1500, applied 1500
  │ applied > 0: call ─────────────────────────────────────────────────►│
  │◄──────────────────────────────────────────── 600 tokens used ───────┤
  │ INCREX BYINT -900 PX 60000 ENX, same <w> ─►  value 600
  │ applied == 0: queue or return 429 to the caller
```

**INCREX, one level down.** `INCREX` arrived in Redis 8.8.0. It increments, checks a bound and sets a TTL in one O(1) command. Verified in `src/commands/increx.json` and `src/t_string.c` at 8.10.2:

- The reply is `[new value, applied increment]`. Without `SATURATE`, an out-of-bound result is rejected and the reply is `[current, 0]`.
- `ENX` sets the TTL only when the key has none. So a later call or correction never extends it.
- With no bound, every increment applies: the bounds default to the type limits, lines 1033 and 1034.
- The docs mark it not supported on Redis Software and Redis Cloud. Valkey 9.1.2 has no `INCREX`. On those, use a Lua script of `INCRBY` and `PEXPIRE`, or the sorted-set window of Phase 1.5.

**The budget, measured.** Limit 10,000 tokens per 60 s. Each call estimates 1,500 tokens and uses 600:

| Budget | Calls admitted of 30 | Counter | Real tokens |
|---|---|---|---|
| reserve only, no correction | 6 | 9,000 | 3,600 |
| reserve, then correction | 15 | 9,000 | 9,000 |

The self-test checks 15. Each corrected call leaves 600, and a call needs 1,500 free. 600 × 14 + 1,500 = 9,900 fits. 600 × 15 + 1,500 = 10,500 does not.

The correction must have no bound. With the counter at 9,900, a call that used 400 more than its estimate tried to add 400. `INCREX ... UBOUND 10000` rejected it with `applied=0`. The counter stayed at 9,900 while real use was 10,300. Measured.

**The late correction.** A long answer can end after its window. Measured: 1 s window, 1,500 reserved, 600 used, `-900` sent 1.2 s later. The right answer is 6 calls.

| Key and correction | After the correction | Next window |
|---|---|---|
| one key, `INCRBY`, no call between | -900, PTTL -1 | 7 calls |
| one key, `INCRBY`, a call opened the next window | 600 | 7 calls |
| key per window, `INCREX ... PX ENX` | old key -900, PTTL 999 ms | 6 calls |

A Lua guard that corrects only an existing key still gave 7 in row 2, because it found the next window's key. The fix: name the key `tpm:{acme}:model-x:<w>`, with w = unix ms / 60,000, rounded down. The correction reuses the reserve's w. Its `PX ... ENX` gives an expired old key a TTL again, as row 3 shows. Pod clock skew moves the edge a little. Inferred.

**The fixed-window edge.** A fixed window allows up to twice the limit across its edge. The lab admitted 999 tokens at a 2 s window's end and 1,000 at the next one's start. That is 1,999 tokens in 147 to 151 ms, against 1,000 per 2 s. Anthropic uses a token bucket, so it can refuse that burst. Use a window shorter than the provider's, or the sliding window of Phase 1.5.

**Calls in flight: a semaphore with leases.** A semaphore is a counter of free slots. Here it is a sorted set of holder IDs, scored by lease expiry from the Redis clock. The script removes expired leases before each acquire. From `llmlimits/main.go:310`:

```go
var acquireLua = redis.NewScript(`
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local lease = tonumber(ARGV[1])
for i, k in ipairs(KEYS) do
  redis.call('ZREMRANGEBYSCORE', k, '-inf', now)
  if redis.call('ZCARD', k) >= tonumber(ARGV[2 + i]) then return 0 end
end
for i, k in ipairs(KEYS) do
  redis.call('ZADD', k, now + lease, ARGV[2])
  redis.call('PEXPIRE', k, lease * 2)
end
return 1
`)
```

Measured with 4 slots, 12 workers and 300 ms calls: peak in flight was 4, and the total 907 to 932 ms, against a minimum of 900 ms. Then one holder crashed without a release. The lease semaphore had 3 of 4 slots free right after the crash and 4 of 4 at 1.1 s. An `INCR` and `DECR` counter had 3 of 4 free at 1.1 s and forever after. Make the lease longer than a normal call, and renew it during the call. Phase 3.4 shows work that outlives a lease.

LiteLLM's in-flight gauge is a similar sorted set, with Redis `TIME` and a 3,600 s slot TTL. Its file header says "not yet ready for production". Verified in source.

**One 429, shared across pods.** When one pod gets a 429 with `retry-after`, every pod should pause. Every pod checks `pause:{provider}:{model}` before a call, set with `SET ... 1 PX <retry_after_ms> NX`. In the lab, 5 pods sent a call every 100 ms while the provider refused calls for 1.5 s:

| Pause | 429 responses | Successful calls |
|---|---|---|
| none | 74 to 75 | 24 to 25 |
| per pod, local | 5 | 24 to 25 |
| shared key in Redis | 1 | 24 to 25 |

OpenAI counts failed requests toward the limit, so the 73 or 74 extra 429s also use budget. LiteLLM shares a cooldown through Redis. Its length is the deployment's `cooldown_time`, else `retry-after`, else 5 s. Verified in `litellm/router.py` at 9c958af, lines 9182 to 9203.

**Fairness between tenants.** A global semaphore alone lets a busy tenant take every slot. Check a per-tenant cap in the same script. Measured with 8 global slots, 40 calls from tenant big and 4 from tenant small, 200 ms each, seven runs:

| Per-tenant cap | small waits on average | big waits on average |
|---|---|---|
| 8, no cap | 233 to 640 ms | 442 to 487 ms |
| 6 | 92 to 102 ms | 579 to 589 ms |

The cap costs the big tenant about 100 to 150 ms of wait, and gives the small tenant 2 slots at all times.

**Fail open or fail closed.** If Redis fails, LiteLLM falls back to a window per instance, so N pods can each admit the full limit. Fail open for a provider limit, with a small local limit. Fail closed for a spend cap.

**The sentence to remember:** reserve and correct with `INCREX` on one key per window, with no bound on the correction. Cap calls in flight with a lease semaphore, and share each 429 through one pause key.

**The trap:** a reserve without a correction. With estimates of 1,500 and real use of 600, the budget admitted 6 calls instead of 15. Users see 429s while 64% of the budget is unused.

**Try this now:**

    go run ./phase07_ai_agents/llmlimits -part budget

In part 1, the counters are equal and the admitted calls differ by 9. In part 4, WRONG rows admit 7 and RIGHT rows 6.

---

## 7.7 — Tool-call queues and idempotency for paid calls (at-least-once, briefly)

Why this matters: a tool call can cost money or act on the world, such as a refund or an email. A queue that redelivers after a crash runs that call twice unless the worker checks first.

**The mental model.** Put tool calls on a stream with a consumer group, as in Phase 1.6. Each entry goes to one worker and stays in the PEL until `XACK`. The PEL, pending entries list, is the group's list of delivered but unacknowledged entries. Another worker claims a crashed worker's entries, so delivery is at least once. The worker must make the paid call idempotent: one call ID never pays twice. Phase 3.2 to 3.5 teach the `SET NX PX` and fencing parts.

```
 worker A                       Redis                         worker B
 XREADGROUP call-1 ◄────────── PEL: call-1 -> A
 SET idem:call-1 A NX PX ─────► OK
 paid call  $0.01
 SET result:call-1 ───────────► stored
 ✗ crash before XACK
                                 250 ms later
                                 XAUTOCLAIM min-idle 200 ms ────► call-1 -> B
                                 GET result:call-1 ◄────────────── found
                                                                  XACK, paid calls = 1
```

**Measured in the `toolqueue` lab:**

| Case | Paid calls | Outcome |
|---|---|---|
| no idempotency key, crash before `XACK` | 2, $0.02 | B pays again |
| key, crash after the result was stored | 1, $0.01 | B reuses the stored result |
| key, crash after the paid call, before the result | 1, $0.01 | B reports "unknown", entry stays pending |

In the third row the retry cannot know the result, and paying again can charge twice. Pass the call ID to the tool's API as its idempotency key, if it accepts one. Otherwise send the entry to a person before the claim key's 30 s lease ends, after which a retry pays again. Inferred from `toolqueue/main.go:107`.

**New commands that help.**

- `XADD ... IDMP <producer> <id>` since Redis 8.6 returns the first entry ID for a repeated pair, and adds nothing. In the lab, two plain `XADD` calls gave two entries, and two `IDMP` calls gave one. Defaults: 100 s and 100 IDs per producer. The docs report 2% to 5% lower throughput. Verified, vendor.
- `XNACK ... FAIL` since 8.8 releases an entry at once and keeps its delivery count. In the lab, `XAUTOCLAIM` with a min-idle of 60 s still claimed the released entry at once. After 3 deliveries the poison call went to a dead-letter stream, acknowledged. Measured.
- `IDMP` protects only the write into the stream, not the worker's paid call. Verified.

**On Valkey.** Valkey 9.1.2 has no `XNACK`, `XADD ... IDMP` or `DELEX`. Verified at tag 9.1.2: `xnack.json` and `delex.json` return 404, and `xadd.json` has no `IDMP`. Alternatives:

- For `XNACK ... FAIL`: `XCLAIM <key> <group> <self> 0 <id> IDLE <min-idle> JUSTID`. The next `XAUTOCLAIM` takes the entry at once. `JUSTID` keeps the delivery count.
- For `IDMP`: a Lua script that returns the ID stored in the pair key, or runs `XADD` and `SET <pair key> <id> EX 100`.
- For `DELEX key IFEQ owner`, Redis 8.4: `DELIFEQ key owner` since Valkey 9.0.0, or the Lua script of Phase 3.3.

The first two ran on Redis 8.10.1, not Valkey. The count stayed 1 after `XCLAIM`, and two script calls gave one entry. Valkey's `t_stream.c` skips the count for `JUSTID`, lines 3277 to 3281. Verified.

**The sentence to remember:** a stream delivers at least once. So every paid tool call needs an idempotency key and a stored result under the same ID.

**The trap:** acknowledging last and checking nothing first. A crash between the paid call and `XACK` doubles the charge, and the queue reports success.

**Try this now:**

    go run ./phase07_ai_agents/toolqueue

Read section 2. The `paid calls` column shows 2, 1 and 1.

---

## 🧪 Hands-on lab

Every command below ran on 2026-10-19, with Go 1.27.1 and go-redis v9.5.1, on port 6571 with no persistence. The "Expected" lines are real output, as ranges where runs differed.

Setup:

```bash
cd study-material/redis/code
mkdir -p /tmp/p7redis
redis-server --port 6571 --dir /tmp/p7redis --save '' --appendonly no --daemonize yes
redis-cli -p 6571 INFO server | grep redis_version     # redis_version:8.10.1
redis-cli -p 6571 VADD probe VALUES 3 1 0 0 a           # (integer) 1, so vector sets exist
redis-cli -p 6571 DEL probe
```

The labs refuse port 6379, which usually holds real data, unless you pass `-allow-6379`. They delete only `p7:` keys.

- [ ] **E1 (offline).** Run every self-test.
  - Run: `for d in semcache vectorsets agentmemory tokenstream llmlimits toolqueue; do go run ./phase07_ai_agents/$d -self-test | tail -1; done`
  - Expected: `all checks passed` six times.
  - If it fails: `no hash collisions` fails when `fakeembed.Dim` is not 2048.
  - Teaches: each rule in the text has a check.

- [ ] **E2 (local).** Measure exact and semantic caching.
  - Run: `go run ./phase07_ai_agents/semcache`
  - Expected: the exact-match row shows `2` hits. The 0.78 row shows `16` hits and `2` wrong. The 0.90 row shows `10` hits, `0` wrong and `6` missed.
  - Teaches: exact match misses paraphrases, and semantic hits can be wrong.

- [ ] **E3 (break-it, local).** Remove the tenant scope.
  - Run: `go run ./phase07_ai_agents/semcache -scope none`
  - Expected: `globex cos=1.000 HIT A05 ... <-- WRONG answer served`. The 0.90 row has `2` wrong hits, because acme also receives `G01`.
  - Teaches: the scope is part of correctness, not a tuning option.

- [ ] **E4 (local).** Measure vector set memory and recall.
  - Run: `go run ./phase07_ai_agents/vectorsets` and repeat with `-seed 2` and `-seed 3`.
  - Expected, seed 1: `NOQUANT ... 1203 ... 1.000`, `Q8 ... 819 ... 0.975`, `BIN ... 707 ... 0.17`. EF 10 gives recall near `0.87`.
  - Teaches: per-element overhead and the Q8 recall limit.

- [ ] **E5 (break-it, local).** Use BIN on sparse vectors.
  - Run: `go run ./phase07_ai_agents/semcache -quant BIN`
  - Expected: every threshold row shows `26` hits and `11` wrong. The gap line shows `0.9961 (BIN)`.
  - Teaches: binary quantisation destroys scores for sparse vectors.

- [ ] **E6 (break-it, local).** Watch a field expire, then lose a TTL two ways.
  - Run: `go run ./phase07_ai_agents/agentmemory`
  - Expected: `HTTL goal, plan, tool:weather:paris -> [-1 -1 2]`, then `after 2.5 s: fields=[goal plan], session key exists=1`. Sections 3 and 4 show `plain HSET -> HTTL [-1]` and `two calls, crash between: TTL=-1`.
  - Teaches: per-field lifetimes, and how a TTL disappears silently.

- [ ] **E7 (break-it, local).** Disconnect a viewer for twice as long.
  - Run: `go run ./phase07_ai_agents/tokenstream -gap 300ms`
  - Expected: the stream viewer shows `400 of 400 tokens, reconnects=1, text identical=true`. The pub/sub viewer loses 98 to 112 tokens, about twice the default run.
  - Teaches: pub/sub loses the gap, and a stream does not.

- [ ] **E8 (local).** Reserve and correct a token budget.
  - Run: `go run ./phase07_ai_agents/llmlimits -part budget`
  - Expected: `admitted  6 of 30` and `admitted 15 of 30`, then `INCREX +400 UBOUND 10000  applied=0 -> counter=9900`, then `1999 tokens admitted within` about 150 ms. Part 4 shows `admitted 7` in WRONG rows and `admitted 6` in RIGHT rows.
  - Teaches: the correction, the INCREX trap, the window edge and the late correction.

- [ ] **E9 (break-it, local).** Crash a semaphore holder.
  - Run: `go run ./phase07_ai_agents/llmlimits -part semaphore`
  - Expected: `lease semaphore  : free slots at t=0.0 s: 3 of 4, at t=1.1 s: 4 of 4` and `INCR/DECR counter: ... at t=1.1 s: 3 of 4, and forever after`.
  - Teaches: a lease returns a crashed holder's slot, and a counter does not.

- [ ] **E10 (local).** Share a 429 and cap a tenant.
  - Run: `go run ./phase07_ai_agents/llmlimits -part 429` and `go run ./phase07_ai_agents/llmlimits -part fairness`
  - Expected: `429 responses =` 74 or 75, then 5, then 1, for none, local and shared. `per-tenant cap 6: small waits` about 100 ms.
  - Teaches: one pause key for all pods, and a cap per tenant.

- [ ] **E11 (break-it, local).** Crash a worker after a paid call.
  - Run: `go run ./phase07_ai_agents/toolqueue`
  - Expected: `paid calls=2 ($0.02)` without a key, `paid calls=1 ($0.01)` with one, and `unknown: key taken, no result` for the crash before the result.
  - Teaches: at-least-once delivery plus an idempotency key.

Shut the server down when you finish:

```bash
redis-cli -p 6571 SHUTDOWN NOSAVE
```

**Where the labs stop matching reality.** The embeddings, vectors, provider, paid tool and token timing are fake. Real models give other hit and error rates. The Query Engine steps did not run.

---

## 🔍 Check it yourself

1. Open `code/phase07_ai_agents/semcache/main.go:154`. This is the scope rule inside `lookupMemory`. Delete the `continue` and run `-self-test`. Which check fails, and what does its detail show?

2. Open `code/phase07_ai_agents/llmlimits/main.go:315`. This is the `ZREMRANGEBYSCORE` step of `acquireLua`, modelled in Go at line 534. Why does the script read `TIME` from Redis instead of taking `now` from the client, as Redisson's `RPermitExpirableSemaphore` does?

3. Open `code/phase07_ai_agents/toolqueue/main.go:107`. `handle` returns "unknown" when the key is taken and no result exists. Name one tool where "unknown" must go to a person, and one where a second call is harmless.

4. In any agent service you own, run:
   `grep -rniE "hset|expire|publish" <your repo>/ | grep -iE "session|memory|stream|token"`
   Find each `HSET` on a field with a TTL, and each `EXPIRE` sent apart from its write. What does a crash between the two leave?

---

## ✅ Checkpoint 7 — answer in your own words

1. **Walk through what happens when** a user loses signal for 4 s during an answer at 40 tokens/s. Compare pub/sub with a stream per response. How many tokens does each viewer miss, and what does the browser send on reconnect?

2. **A colleague says** "set the threshold to 0.99, then wrong answers are impossible." Argue against it with the AWS numbers. What would you measure instead, and on what data?

3. **Given these constraints, design** working memory for an agent. Sessions last up to 2 hours. Tool results go stale after 5 minutes. Users can return tomorrow. The context is 32,000 tokens. Name each key, its type and TTL, and what also goes to the durable store.

4. **This is broken.** Memory on the agent cluster grows 3% a day. `SCAN` shows sessions with TTL -1 and tool fields with HTTL -1. No deploy changed the TTL settings. What is the cause, and how do you check it?

5. **Show the arithmetic.** You need 2 million vectors of 768 dims in vector sets, M 16. Use the lab's 691 bytes of overhead per element. Compute the memory for NOQUANT and Q8, and the Q8 recall you expect on the lab data.

6. **Given these constraints, design** a limiter for one model: 400,000 tokens per minute, 30 pods, 50 tenants. A tenant may use at most 25% of it, and have at most 10 calls in flight. A call estimates 3,000 tokens and uses 1,200 on average. Write the Redis commands for one call. How many calls per minute does it admit, with and without the correction?

<details>
<summary>Answer sketches</summary>

1. The gap is 4 s × 40 = 160 tokens, and pub/sub loses all of them. The browser sends `Last-Event-ID: <last entry ID>`, and the server calls `XREAD STREAMS resp:{id} <that ID>`. The stream viewer misses 0. If the TTL ran out, the server loads the answer from the durable store.

2. In the AWS test, 0.99 kept a 23.5% hit rate, and 7.9% of hits were still wrong, against 8.8% at 0.75. The threshold mostly removed right hits. vCache found that right and wrong hits had mean similarities of 0.84 and 0.85. Measure hit rate and wrong share on labelled prompts from your own traffic.

3. `wm:{t:s}`: hash, `EXPIRE` 2 h on each write, tool fields with `HSETEX EX 300`. `hist:{t:s}`: list, `RPUSH`, `LTRIM -50 -1` and `EXPIRE 7200` in one `MULTI`, then trimmed by tokens to 32,000 minus the answer budget. The transcript goes to the durable store every turn, since the Redis keys are gone by tomorrow.

4. Cause one: a write and its `EXPIRE` sent in two calls. Cause two: a plain `HSET` over a field with a TTL. Grep the write paths for both, and reproduce them with agentmemory sections 3 and 4. Fix with `SET ... EX`, `HSETEX` or `MULTI`, then remove orphans with `SCAN` and `UNLINK`.

5. NOQUANT: 768 × 4 = 3,072 + 691 = 3,763 bytes × 2 M = about 7.5 GB. Q8: 768 + 691 = 1,459 bytes × 2 M = about 2.9 GB. On the synthetic lab data, Q8 recall@10 was 0.966 to 0.975 at 128 and 384 dims. Measure it on your own vectors.

6. Per call, with w the minute index: `INCREX itpm:{model}:tenant:{t}:<w> BYINT 3000 UBOUND 100000 PX 60000 ENX` for the 25% cap. Then the same on `itpm:{model}:all:<w>` with `UBOUND 400000`. Then the lease semaphore with a limit of 10 on `inflight:{model}:{t}`. After the call, `INCREX ... BYINT -1800 PX 60000 ENX` both keys of the same w, even if that minute ended. If the global step rejects, return the tenant reservation the same way. Without the correction: 400,000 / 3,000 = 133 calls per minute. With it, a call passes while 1,200 × n + 3,000 ≤ 400,000. So n ≤ 330, and 331 calls pass.

</details>

---

## References & Further Learning

All URLs returned HTTP 200 on 2026-10-19.

**Redis commands and data types**

- **INCREX, Redis docs** — https://redis.io/docs/latest/commands/increx/
  Focus on: "Pattern: window counter rate limiter" and the compatibility table.
- **HEXPIRE, Redis docs** — https://redis.io/docs/latest/commands/hexpire/
  Focus on: what clears a field TTL, and the per-field reply codes.
- **Vector sets README at tag 8.10.2** — https://raw.githubusercontent.com/redis/redis/8.10.2/modules/vector-sets/README.md
  Focus on: "Optimizing memory usage", "Scaling vector sets", and the recall table near line 660.
- **Vector search, Query Engine docs** — https://redis.io/docs/latest/develop/ai/search-and-query/vectors/
  Focus on: the index parameter tables and the hybrid query modes.
- **Streams idempotency, Redis docs** — https://redis.io/docs/latest/develop/data-types/streams/idempotency/
  Focus on: "Parameters" and "Expiration behavior".
- **Pub/sub, Redis docs** — https://redis.io/docs/latest/develop/pubsub/
  Focus on: the at-most-once paragraph.

**Semantic caching**

- **vCache, arXiv 2502.03771** — https://arxiv.org/abs/2502.03771
  Focus on: Table 3 and Section F.9. A preprint, not peer reviewed.
- **AWS Database Blog, ElastiCache as a semantic cache, 2025-11-26** — https://aws.amazon.com/blogs/database/lower-cost-and-latency-for-ai-using-amazon-elasticache-as-a-semantic-cache-with-amazon-bedrock/
  Focus on: Table 1. Vendor.
- **Anthropic prompt caching** — https://platform.claude.com/docs/en/build-with-claude/prompt-caching
  Focus on: lifetime and pricing, which change.

**Agent memory, streams and limits in real code**

- **LangSmith data plane** — https://docs.langchain.com/langsmith/data-plane.md
  Focus on: lines 13 to 46, what Redis holds and what Postgres holds. Vendor.
- **langgraph-redis** — https://github.com/redis-developer/langgraph-redis
  Focus on: TTL in minutes, and the shallow saver.
- **OpenAI Agents SDK RedisSession** — https://raw.githubusercontent.com/openai/openai-agents-python/main/src/agents/extensions/memory/redis_session.py
  Focus on: the WATCH and MULTI write, and the cancel block near line 576.
- **Vercel resumable-stream** — https://github.com/vercel/resumable-stream
  Focus on: `src/runtime.ts`, where the chunks are buffered.
- **LiteLLM limiter v3** — https://raw.githubusercontent.com/BerriAI/litellm/main/litellm/proxy/hooks/parallel_request_limiter_v3.py
  Focus on: the sorted-set gauge and the fail-open fallback.
- **Anthropic rate limits** — https://platform.claude.com/docs/en/api/rate-limits
  Focus on: cache-aware input limits and `retry-after`.
- **OpenAI rate limits** — https://developers.openai.com/api/docs/guides/rate-limits
  Focus on: how `max_tokens` counts.

**Production reports and Valkey**

- **Inngest, the queue is the easy part, 2026-09-09** — https://www.inngest.com/blog/the-queue-is-the-easy-part
  Focus on: why the queue left Valkey. Vendor.
- **OpenAI, March 20 ChatGPT outage, archived** — https://web.archive.org/web/20250101055603/https://openai.com/index/march-20-chatgpt-outage/
  Focus on: the cancelled-request mechanism. The live page returns 403 to scripts. Read with redis-py issue 2624: https://github.com/redis/redis-py/issues/2624
- **Valkey issue 2569, vector sets** — https://github.com/valkey-io/valkey/issues/2569
  Focus on: its status, open on 2026-10-19.

---

## Cheatsheet

```
SIX JOBS, AND THE RULE
  only in Redis : answer cache, embedding cache, token buffers, limit counters
  also durable  : transcripts, runs, long-term memory, paid tool results

SEMANTIC CACHE
  scope key/tag : tenant + locale + model version + template version
  threshold     : measure on your labelled prompts; AWS 0.99 -> 23.5% hits, 7.9% wrong
  TTL           : RedisVL default none, refreshed on hit; daily data ~23 h + jitter

VECTOR SETS (Redis 8)
  VADD key FP32 <blob> <id> [Q8|NOQUANT|BIN]   default Q8, M 16, EF build 200
  VSIM key FP32 <blob> WITHSCORES COUNT k      score = (cos+1)/2, EF 100
  measured 128d : B/elem NOQUANT 1203, Q8 819, BIN 707; +691 B at M 16
  recall@10     : NOQUANT 1.000, Q8 0.971, BIN 0.15-0.18 (3 seeds, synthetic)
  scale         : one key = one shard; N keys, merge by score
QUERY ENGINE    : FLAT < 1M, HNSW M16 EFC200 EFR10, SVS-VAMANA 8.2+, LIMIT 0 k, DIALECT 2
VALKEY          : valkey-search FT.* HNSW/FLAT; no vector sets, INCREX, XNACK, IDMP, DELEX

MEMORY
  HSETEX key EX 300 FIELDS 1 f v    plain HSET clears the field TTL
  RPUSH + LTRIM -N -1 + EXPIRE      in one MULTI; then trim by tokens
  SET k v EX ttl                    never SET then EXPIRE in two calls

TOKEN STREAMS
  XADD resp:{id} MAXLEN ~ 10000 * seq n t chunk ; EXPIRE at first and last
  resume        : XREAD STREAMS resp:{id} <lastId>  (XRANGE needs "(lastId")
  batch 8 tok   : 250 XADD not 2000; 7 B/token not 18-19

LIMITS
  reserve       : INCREX k:<w> BYINT est UBOUND lim PX 60000 ENX; w = ms / 60000
  correct       : INCREX k:<same w> BYINT (actual - est) PX 60000 ENX, no bound
  window edge   : up to 2x limit (lab 1999 of 1000 in ~150 ms)
  in flight     : ZSET holder->lease expiry, Redis TIME, ZREMRANGEBYSCORE first
  shared 429    : SET pause:{prov}:{model} 1 PX retry_after NX  (lab 75 -> 1)

TOOL QUEUE
  delivery      : at least once; XAUTOCLAIM after min-idle; XNACK FAIL (8.8)
  producer      : XADD ... IDMP pid iid (8.6), default 100 s / 100 ids
  worker        : SET idem:{call} owner NX PX; store result:{call}; XACK last
  crash gap     : paid, no result -> "unknown"; to a person within the key lease
  Valkey 9.1.2  : XCLAIM ... IDLE <min-idle> JUSTID; Lua SET + XADD; DELIFEQ
```
