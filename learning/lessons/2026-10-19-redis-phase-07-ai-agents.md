Phase 6 reviewed how a shared Redis behaves when a client waits, a key is evicted or a server misses a message. This last phase builds the AI features on top of that knowledge. The running case is a support agent platform with two tenants, acme and globex. API pods take user questions, call a model provider, call paid tools, and stream answers to a web page. Every section and every lab is one part of that platform.

An AI agent is a program that calls a model in a loop, calls tools and keeps state between the calls. The platform uses Redis for six jobs: an answer cache, an embedding cache, memory, token streams, limits and a tool-call queue. Each job looks like a pattern from Phases 1 to 3, but it breaks in a new way here. The data is probabilistic, because a cache hit depends on a similarity score. It is long, because an answer streams for seconds. And it is paid per token or per call, so a mistake costs money that no log line shows.

Two failures show the size of the problem. With no tenant scope, the lab cache served acme's answer to a globex user at a similarity of 1.000. With a token budget that never corrects its estimates, the lab limiter admitted 6 calls where 15 fit.

### What you must know

- A semantic cache's threshold sets its hit rate, not its error rate, so correctness comes from scope and measurement.Pick a threshold from labelled traffic, and scope every entry by tenant and model.

- A vector costs its bytes plus a graph cost that grows with M, and quantisation sets the recall ceiling.Size a vector index from the graph, and tune EF only when the search is the limit.

- A TTL belongs to the value that was written, so an overwrite or a split write can make memory permanent.Write agent memory so every value and field keeps its TTL.

- Pub/sub delivers at most once and Streams at least once, so readers keep positions and workers keep idempotency records.Build a token stream a client can resume and a tool queue that never pays twice.

- A shared LLM limit must reserve an estimate before the call and correct it after, in the same window.Build a token budget, an in-flight cap and a shared 429 pause across pods.

## Which earlier ideas does this phase use, and where does Redis sit?

Six ideas from earlier phases come back here. Each card explains one again in a few sentences, so you do not need to reopen the earlier lesson.

Persistence and replication lose recent writes

Phase 4 showed that AOF is off by default. So a crash loses everything since the last RDB snapshot. Replication is asynchronous, so a failover can lose writes the old primary had acknowledged, including XADD entries.

Eviction removes keys under memory pressure

Phase 5 showed that the default maxmemory-policy is noeviction. With allkeys-lru, Redis may remove any key, including keys that have no TTL.

Hash fields can expire one by one

Phase 1 showed that HEXPIRE gives one hash field its own TTL. A small hash with field TTLs keeps a compact encoding. This phase uses field TTLs for agent memory.

A cache fill can return old or wrong data

Phase 2 taught cache-aside with its miss path and fill path. It added delete-on-write and TTL jitter. A semantic cache keeps all of that and adds a new way to be wrong.

Claims, leases and idempotent writes

Phase 3 claimed work with a lease, using SET key owner NX PX ms. It also showed that the resource must refuse a repeated effect. A paid tool call needs the same idea.

Pub/sub keeps no copy

Phase 6 showed that a pub/sub message reaches only the subscribers connected at that moment. A server that was away reads the gap from a log, never from pub/sub.

These ideas decide which of the six jobs can live only in Redis. Four jobs hold data you can rebuild. Two hold data that someone paid for, or that a user expects to see again.

Web page
API pod (x N)
Model providerRPM, TPM, 429s
question, tokens
prompt, tokens
Redis: may lose
answer cacheembedding cache
token streamslimit counters
Redis: never the only copy
working memorytool-call queue
Durable store
transcripts, runslong-term memory
tool resultsbilling

Where each of the six jobs keeps its data. The left box may live only in Redis.

JobIf Redis loses itDurable copy needed

Answer and embedding cachemore paid model callsno

Token streama viewer reloads the answerthe final answer

Limit countera short burst over the limitno

Working memorythe agent forgets the sessionyes, if a user can return

Tool-call queuea paid call is lost or runs twicethe call and its result

Two published designs follow this split. LangSmith Agent Server keeps a worker wake-up list, cancel signals, the pub/sub stream of output and a retry counter in Redis. Its docs state that no user or run data is stored in Redis, and Postgres holds runs, threads, state and long-term memory. Inngest ran its queue of customer jobs on Valkey. When a Valkey cluster ran out of memory, the whole cluster went down, not only the tenant that filled it. After about two years of patches, Inngest is moving the queue state to FoundationDB.

Correction. The phase cited the Inngest post "the queue is the easy part" for why the queue left Valkey. That URL is a post about fairness in a multi-tenant queue. The reasons for leaving Valkey are in "Our Migration to FoundationDB, Part 1".

The common mistake with this split is one shared Redis with allkeys-lru for the cache and for working memory. Under memory pressure, Redis then evicts live sessions in the same way as stale cache entries. Put each class of data in its own instance, or give the memory keys TTLs and use volatile-lru. To check a Redis you own, run redis-cli CONFIG GET maxmemory-policy appendonly, and mark each job it holds against the table above.

Go deeper: the durability defaults, and the two published designs in detail

- AOF is off by default. With appendfsync everysec, a crash loses up to about 1 second of writes. With the default rules save 3600 1 300 100 60 10000, RDB alone can lose up to an hour of writes. These are the redis.conf values at 8.10.2.

- maxmemory-policy defaults to noeviction. With allkeys-lru, Redis evicts memory keys that have no TTL.

- Replication is asynchronous, so a failover can lose XADD writes as well as plain keys.

- LangSmith limits retries to 3 per run, with the counter in a Redis string that expires. Its output streams over pub/sub, and the next sections show why that is safe only because a durable copy lives elsewhere.

- Inngest's queue ran on one execution thread per cluster, so the queue could only peek at and process a subset of accounts on each pick. Recovery also reloaded on one thread. Inngest splits queue shards by billing tier, and the second part of its migration series gives about 20,000 accounts per logical shard on FoundationDB. Its companion post gives "hundreds of millions of items in flight".

Evidence
redis.conf at tag 8.10.2, lines 506, 1266, 1491 and 1550. LangSmith data-plane page, line 34: "No user or run data is stored in Redis." Inngest, "Our Migration to FoundationDB, Part 1", 2026-08-24, and Part 2, 2026-10-14. Vendor sources. The title correction comes from fetching both Inngest pages on 2026-10-19.

The cheapest job to lose is the answer cache, and it is also the one that can return a wrong answer with no error. The next section starts there.

## Why does an exact cache miss most questions, and what does a semantic cache return instead?

A cache hit skips a paid model call, and a wrong hit returns a confident wrong answer.

The answer cache sits first in the platform's request path, because a hit there skips the model call, which costs seconds and money. The obvious design keys each answer by a hash of the normalised prompt. In the lab set of 26 user questions, that exact-match cache hit 2 times, because users rarely type the same sentence twice.

A semantic cache stores each answer with the embedding of its prompt. An embedding is a vector that a model computes to represent the meaning of a text. Two paraphrases get vectors that point in similar directions. For a new prompt, the cache finds the nearest stored prompt and returns its answer if the similarity is above a threshold. The similarity is usually cosine similarity, the cosine of the angle between two vectors, which is 1 when they point the same way.

- API podgets the prompt.

- embedderturns it into a vector.

- Redis searchfinds the nearest stored prompt in this tenant and model version.

- cos ≥ thresholdHIT: return the stored answer.

- cos < thresholdMISS: call the model, then store vector, answer and TTL.

Predict: you raise the threshold from 0.90 to 0.99. What happens to the hit rate, and to the share of hits that are wrong?
The hit rate falls by about two thirds, from 74.5% to 23.5% in the published AWS test below. The share of hits that are wrong barely moves, from 7.7% to 7.9%. Most people expect a stricter threshold to remove the wrong answers first. That is reasonable, because a higher score sounds like a safer match. But the score measures how close two texts are, not whether the two questions need the same answer, so right and wrong hits sit at about the same scores.

Libraries pick their threshold for you. RedisVL, Redis's Python library for AI work, defaults to a cosine distance of 0.1, which is about 0.9 similarity, and to entries that never expire. LangCache, Redis's managed semantic cache, defaults to a similarity of 0.85.

The lab semcache stores 16 answers and asks 26 questions, each labelled with its right answer or "none". Its embeddings are a hashed bag of words, so the numbers show the mechanism, not a real model. With Q8 vectors and the tenant filter on, it measured the sweep below.

Two of the questions show why one threshold cannot separate right from wrong. "Price of the Pro Max plan?" scored 0.866 against the cached "Pro plan" question, and that hit is wrong. "Price of the Pro plan per month" scored 0.775 against the same entry, and that hit is right. So the wrong question is closer than the right paraphrase. Two refund questions both scored 0.800. "Refund within 30 days?" was a wrong hit, and "refund possible after 30 days?" was a right one. No threshold can split two hits with the same score. Both values come from word counts, in closed form.

3 shared words, texts of 4 and 3 words:  3 / sqrt(4 x 3) = 3 / sqrt(12) = 0.866   WRONG
3 shared words, texts of 5 and 3 words:  3 / sqrt(5 x 3) = 3 / sqrt(15) = 0.775   right
any threshold <= 0.775 accepts both; any threshold > 0.866 rejects both

At 0.90 this small lab set happened to have no wrong hits, but it also missed 6 right answers. A real model gives other numbers, and the next section shows them.

Go deeper: the RedisVL and LangCache defaults in full
RedisVL, Redis's Python library for AI work, shows what a typical semantic cache does by default. Its SemanticCache is configured like this at v0.28.0.

SettingDefaultWhat it means

distance_threshold0.1 cosine distancedistance is 1 minus similarity, so about 0.9 similarity

num_results1only the single nearest entry is checked

ttlNoneentries never expire

TTL on a hitrefreshed on every matched keya hot entry never expires

indexFLAT, COSINEevery lookup compares with every entry

entry IDSHA-256 of prompt and filter valuesthe model version is not part of the ID

LangCache, Redis's managed semantic cache, defaults to a similarity threshold of 0.85 and no expiration. Its docs also say that no single value is correct for every use case.

Evidence
RedisVL semantic.py at v0.28.0: distance_threshold: float = 0.1 at line 64, num_results: int = 1 at line 436, TTL refresh on hit at lines 519 to 521. schema.py line 42 for the entry ID. LangCache concepts page, line 45. The sweep was measured by the phase lab on Redis 8.10.1, x86_64 under Rosetta 2, and the 0.866 and 0.775 values are checked by the lab's self-test.

A small fake model cannot tell you how often a real cache is wrong. The next section asks what published tests with real embedding models found.

## Why does a higher threshold not remove the wrong answers?

The lab showed one wrong question that scored higher than a right paraphrase. A published test with a real embedding model shows the same effect at scale. AWS ran 63,796 Chatbot Arena queries and their paraphrases through a semantic cache on ElastiCache for Valkey. Amazon Titan Text Embeddings V2 made the vectors, and Claude 3 Haiku wrote the answers. The cache started empty. For each threshold, the post reports an "accuracy", the share of hits whose stored answer fits the question. So the wrong share is 100% minus that accuracy.

The AWS test, one threshold at a time.

Threshold row
Threshold . Hit rate . Wrong share of hits . Cost per day . Wrong answers per 10,000 questions .

Real values from the AWS post. Row 5 is the run with no cache.

Move the slider from row 0 to row 3. The hit rate rises almost four times, from 23.5% to 90.3%, while the wrong share moves less than one point, from 7.9% to 8.8%. So in this test a strict threshold mostly removed right hits. The wrong share climbs clearly only below about 0.75, to 12.5% at 0.50.

A research group that built a cache called vCache measured why. On 45,000 entries, right and wrong hits had almost the same mean similarity, 0.84 and 0.85, with a large overlap. The best threshold for each cached entry ranged from 0.71 to 1.0. If the two groups overlap, moving one global threshold removes right and wrong hits in about the same proportion. vCache therefore learns a threshold for each cached entry. On one dataset it reached a 41% hit rate, with wrong answers for 0.5% of all prompts. That is about 1.2% of its hits.

86.3%daily cost saved at 0.75 in the AWS test.

8.8%of those hits wrong.

7.9%wrong at 0.99, with 23.5% hits.

The cost arithmetic makes the trade clear. Without a cache the AWS run cost $49.5 a day, and at threshold 0.75 it cost $6.8. That is a saving of 1 − 6.8 / 49.5 = 86.3%, with 8.8% of hits wrong and no error in any log. So you trade money for wrong answers. The only way to know the rate is to label a sample of your own prompts and count.

Go deeper: how each source counts "wrong", and where these numbers stop holding

- The AWS post does not say how it judged a correct hit. Its dataset was built from paraphrases, so its hit rates are likely higher than most real traffic. That is inferred from the dataset description.

- vCache counts errors as a share of all prompts, not of hits. A static threshold of 0.99 on SemCacheLMArena with E5-large-v2 and GPT-4o mini gave a 37% hit rate and 2.5% errors. As a share of hits that is 2.5 / 37 = 6.8%, close to the AWS figure.

- The 0.84 and 0.85 means come from the SemCacheClassification set, not from the LMArena row above. vCache is a preprint.

- No named company has published a wrong-hit rate from a production semantic cache. A search for one found vendor guides and stories with no company name.

Evidence
AWS Database Blog, 2025-11-26, Table 1, node cache.r7g.large. Vendor benchmark. vCache, arXiv 2502.03771 v5, Table 3 and Appendix F.9: correct and incorrect hits "are nearly indistinguishable in similarity space". The 6.8% value is arithmetic on the published numbers. The 86.3% value matches the table's savings column. The table also has a 0.80 row, with 87.6% hits, 91.8% accuracy and $7.6 a day.

The threshold cannot make a hit correct, but one part of correctness does not depend on similarity at all. The next section covers that part, the scope of each entry.

## What makes a cache hit wrong at any similarity?

The threshold decides how many hits you get, and labelled traffic tells you how many are wrong. One class of wrong hit has nothing to do with the score. An entry is valid only for the context that produced it. That context is the tenant, the locale, the model version, the prompt template version and the embedding model. A hit across any of these is wrong even at a similarity of 1.000.

semcache -scope none

The lab serves acme's CSV-export answer to a globex user at cos 1.000, and globex's password answer to acme. The 0.90 row now has 2 wrong hits instead of 0.

semcache -scope filter or -scope key

The tenant is a filter on the search, or part of the key name. Both cross-tenant lookups miss, and the sweep returns to the scoped numbers.

Put each part of the scope in the key name or in a search filter. The tenant and locale stop one customer's answer reaching another. The model version and template version stop an answer from an old prompt being served after a change. The embedding model needs its own place, in the index name or a tag, for a different reason. A new embedding model puts new query vectors in another vector space, so every stored vector becomes useless at once. RedisVL helps only in part. It refuses to open an existing index whose schema differs, such as another vector dimension, unless you pass overwrite=True. A new model with the same dimension passes that check, so old and new vectors mix in one index. When you pass no vectorizer, RedisVL also logs a warning that its default model changed in version 0.6.0.

Expiry has three rules that are special to LLM answers. Phase 2 already taught delete-on-write and TTL jitter, so only the new parts follow.

- RedisVL refreshes the TTL of every matched key on a hit, so a wrong answer that users hit often never expires. Delete it by ID when a user reports it.

- AWS suggests a TTL of around 23 hours plus random jitter for data that changes daily.

- Tag each entry with its source documents, and delete by tag when one of them changes. LangCache deletes entries by attributes in this way.

Provider prompt caching is a different mechanism, and it cannot return a wrong answer. Anthropic and OpenAI cache the processed prompt prefix, and the model still generates a new answer. Anthropic's docs say prompt caching has no effect on output token generation.

Semantic cache in RedisProvider prompt caching

What is reusedthe whole answerthe processed prompt prefix

Can return a wrong answeryesno

Saves output tokensyesno

Lifetimeyour TTLAnthropic: 5 minutes by default, refreshed on use

So use prompt caching for a long fixed system prompt, and a semantic cache for questions that repeat. In the running case, the platform's long support instructions belong in the provider cache. The repeated "how do I export to CSV" question belongs in Redis, scoped by tenant.

The threshold sets the hit rate, and scope and labelled samples decide correctness.

A threshold of 0.99 "looks safe", yet the AWS test still served 7.9% wrong hits.

Run go run ./phase07_ai_agents/semcache -scope none and find the WRONG answer served line.

Go deeper: where one library checks the model version
Libraries differ in where they check the scope, and the place matters. langchain-redis RedisSemanticCache stores the model string in metadata and checks it after the vector search. It asks for one result, so if the nearest entry came from another model, the lookup misses even when the second-nearest entry is valid. The effect on the hit rate is inferred from the code and was not measured.

Evidence
Scope runs measured by the phase lab, and the 2 wrong hits at 0.90 come from the review run. langchain-redis libs/redis/langchain_redis/cache.py, lines 494 to 499. RedisVL semantic.py at v0.28.0, lines 44 to 50 for the warning and 198 to 211 for the schema check, re-opened for this review. The schema compares the vector dimension and type, not the model name, in schema.py lines 116 to 135. AWS "around 23 hours", vendor. Anthropic prompt caching page, lines 212 and 769.

Every semantic cache lookup is a nearest-neighbour search over stored vectors. The next concept asks what that search costs in memory, and what limits its accuracy.

## How much memory does one stored vector really take?

A vector index costs more than its vectors, and the graph decides by how much.

The semantic cache, the platform's long-term memory and any RAG retrieval all run the same nearest-neighbour search. RAG, retrieval-augmented generation, adds documents found by that search to the prompt. Before the platform stores a million support articles as vectors, you have to size the Redis node, and the obvious sizing is wrong.

Redis 8 has two vector engines. Vector sets are a data type, and one key holds the vectors and an HNSW graph. HNSW, Hierarchical Navigable Small World, is a layered graph that finds near neighbours by walking from node to node along links. Each node keeps up to 2 × M links to its neighbours at the lowest layer, and up to M at each higher layer. So M sets the size of the graph. The Query Engine instead indexes many hash or JSON keys with FT.CREATE, and adds filters, full text and automatic sharding across a cluster.

- One key holds the vectors and the HNSW graph, with no schema.

- Q8 int8 quantisation by default.

- Filters on JSON attributes set with SETATTR.

- One key lives on one shard, so you split it yourself.

- Ran on the lab build.

- One index over many hash or JSON keys.

- A schema with TYPE, DIM and DISTANCE_METRIC. TYPE is required, such as FLOAT32.

- TAG, NUMERIC, TEXT and GEO filters.

- Shards across a cluster for you.

- Not on the lab's Homebrew build, so FT.* is an unknown command there.

Predict: you plan 2 million 128-dimension vectors in one vector set with Q8. Your sizing sheet says 2 M × 128 bytes = 256 MB. What is the real figure, and which setting changes it most?
About 2 M × 819 bytes, which is 1.6 GB, more than six times the sheet. M changes it most, at about 19 bytes per unit of M. The sheet counts only the vector, which is reasonable because the vector is the data you think of. But at 128 dimensions with Q8, the graph links, the node and the element name cost 5.4 times the vector itself.

The commands and defaults of vector sets below were read from the module at 8.10.2.

- VADD key FP32 <blob> <element> [Q8|NOQUANT|BIN] [M n] [EF n] [SETATTR json] adds one vector. Q8 is the default.

- Q8 scales each vector to signed int8, one byte per dimension. NOQUANT keeps 4-byte floats. BIN keeps one bit per dimension.

- Defaults are M 16, build EF 200, search EF 100 and COUNT 10. EF is the size of the candidate list the search keeps, and the search raises it to COUNT when COUNT is larger.

- VSIM returns (cos + 1) / 2, not the cosine. Convert it back before you compare it with a cosine threshold.

The lab vectorsets loaded 20,000 clustered synthetic vectors of 128 dimensions and divided MEMORY USAGE by the element count.

One Q8 element at 128 dimensions, M 16: 819 bytes.

The 691 bytes stayed the same at 128 and 384 dimensions, and for every quantisation. NOQUANT measured 1,203 bytes and BIN 707, which is 512 and 16 bytes of vector plus the same 691. The vector-sets README explains most of it. A node has on average 2.33 × M pointers of 8 bytes, which is 298 bytes at M 16. A sweep of M on 16-dimension vectors gave a straight line. So the overhead per element on this build is about 393 + 18.7 × M bytes.

Memory of one vector set.

Vectors, millions
Dimensions
M
Per element overhead . NOQUANT . Q8 . BIN .

The formula is a fit to five measured points, M 4 to 64, on one x86_64 libc build. Check it on your own build before you buy a node.

At real dimensions the measurement holds. At 1,536 dimensions with 10,000 elements and M 16, the lab gave 6,835 bytes for NOQUANT, 2,227 for Q8 and 883 for BIN. Each is the vector, 6,144, 1,536 or 192 bytes, plus the same 691. So 1 million vectors of 1,536 dimensions take about 6.8 GB with NOQUANT and 2.2 GB with Q8.

Correction. The phase gave 6.8 GB and 2.2 GB for 1 million 1,536-dimension vectors. It inferred them from 128 and 384 dimensions, and asked you to check. A run at 1,536 dimensions measured it: 6,835, 2,227 and 883 bytes per element, with the same 691-byte overhead.

The mistake is to size memory from the vector bytes alone. At 128 dimensions with Q8, the vector is 128 bytes and the element is 819 bytes. So a plan built on 128 bytes is 6.4 times too small.

Go deeper: the M sweep, and the status of vector sets

Mbytes per element, 16 dims NOQUANTminus the 64-byte vectorREADME links, 2.33 × M × 8

453146775

8605541149

16755691298

321,053989596

641,6511,5871,193

- Each extra unit of M costs 18.7 bytes, which is exactly 2.33 × 8. The fixed part, about 393 bytes, is the node and the element name. The element names were 6 bytes long, so longer names add to it.

- At 1,536 dimensions, recall@10 was 1.000 for NOQUANT, 0.983 for Q8 and 0.233 for BIN.

- The top-level README.md of Redis 8.10.2 still lists "Vector set (beta)". The docs page and the module README have no such label, so expect that the API may still change.

- This build reports mem_allocator:libc, not jemalloc. A native jemalloc build on Linux can give other byte counts.

Evidence
Defaults: vset.c lines 130, 133, 136, 600 and 832 to 836, and hnsw.h line 20, at 8.10.2. README lines 65 and 639 for the links. Measured with the phase lab and with a redis-cli M sweep, Redis 8.10.1 x86_64 under Rosetta 2. The 1,536-dimension command was vectorsets -dim 1536 -n 10000 -queries 100 -shards 1 -efs 100.

Memory is one half of the choice of quantisation. The next section shows the other half, what each choice does to recall.

## What limits recall: the search or the rounding?

The last section sized the graph, and showed that Q8 saves less memory than the vector bytes suggest. The other cost of quantisation is recall. Recall is the share of the true nearest neighbours that a search returns. A recall@10 of 0.97 means 9.7 of the true top 10 on average. The lab found the true neighbours by a brute-force search in Go on the float32 originals. It ran 200 queries with k = 10 and three seeds.

Quantisation, 128 dimsbytes per elementrecall@10

NOQUANT1,2031.000

Q8, the default8190.971

BIN7070.15 to 0.18

EF is the knob most people turn when recall is low. It trades latency for recall, but only up to a point. These runs used Q8 at 128 dimensions with seed 1. The p50 and p99 are the median and the 99th percentile of the client round trip.

search EFrecall@10p50 µsp99 µs

100.870238378

100, the default0.975269414

5000.975476759

Recall stopped at 0.975 for Q8, while NOQUANT reached 1.000 on the same data. So at the default EF the int8 rounding set the limit, not the search, and more EF only added latency. Check which limit you have before you tune EF. If NOQUANT on a sample also stays low, the search is the limit. If NOQUANT reaches 1.000, the rounding is the limit and EF cannot help.

BIN fails badly on sparse vectors, such as the lab's hashed bag of words. With semcache -quant BIN, all 26 questions hit at every threshold and 11 hits were wrong. One bit per dimension cannot tell most of these texts apart. BIN suits dense vectors only, and only where recall can be checked.

A vector set is one key, so it lives on one shard. The README says to split a large set into N keys, query each and merge the results by score on the client. Writes then scale with N, but reads do not, because every query goes to every key. In the lab, 4 keys kept recall at 0.975. The p50 rose from about 270 µs to between 1,033 and 1,173 µs with 4 sequential calls over five runs. Parallel calls would cut that, which is inferred and was not measured.

The Query Engine did not run on the lab build, because the Homebrew formula builds Redis without the bundled modules. Its index and query commands are in the Go deeper block below.

Correction. The phase said "That build has no Query Engine". That is true for the Homebrew build only. Redis 8.10.2 ships the Search and Query Engine as a bundled module, so say "this Homebrew build", not "Redis 8.10".

The two engines also use the same word with different defaults. The Query Engine's HNSW searches with EF_RUNTIME 10 by default, while vector sets search with EF 100. Code moved from VSIM to FT.SEARCH keeps the word "EF" and loses most of the search effort, so set EF_RUNTIME on purpose.

- Is Redis already in the stack, with up to a few million vectors and simple filters?

- yesRedis is a reasonable vector store. Price the RAM first.

- no, tens of millionsPrice the RAM first: 50M × 768 × 4 bytes is 153.6 GB before the graph.

- Do you need text, number or geo filters, or automatic sharding?

- yesUse the Query Engine.

- no, similarity only, and you can split keysUse vector sets.

An element costs 691 bytes plus its vector at M 16, and Q8 caps recall.

Sizing from vector bytes alone makes a Q8 128-dimension plan 6.4 times too small.

Run E4's vectorsets and compare the B/elem and vector B columns.

Go deeper: Query Engine commands and index types, Valkey, the README recall test, and the 8.10.2 fix

- FLAT compares with every vector and suits indexes under 1 million vectors or exact results. HNSW defaults are M 16, EF_CONSTRUCTION 200 and EF_RUNTIME 10. SVS-VAMANA arrived in Redis 8.2 and uses less memory. Its LVQ and LeanVec compression is not in Redis Open Source.

- A filter before => makes a hybrid query. Redis either filters batches of neighbours, or scores every document that passes the filter.

- Whether the Redis Query Engine stores each vector twice, once in the hash and once in the index, was not checked. Valkey's search module did this for HASH documents until 1.3.0-rc1, which stores them once. So check it before you size a Query Engine node.

- Whether the Query Engine raises EF_RUNTIME to K when K is larger was not checked.

- Valkey has valkey-search, with FT.*, HNSW and FLAT, and FT.HYBRID in 1.3.0-rc1. Valkey has no vector sets, and issue 2569 for them is open.

- The README's Word2Vec test found that an int8 key returned 95.98% of what a linear scan of the same int8 key returned, and a BIN key 35.48%. That measures search error only, because the ground truth used the same quantised key.

- No neutral benchmark of Redis against other vector stores was found. Redis and Qdrant each publish one that puts their own product first.

- Redis 8.10.2 is a security release. It fixes a crash from deeply nested JSON in vector set queries and a crash in RedisSearch KNN with very long vector field names. Upgrade before you pass user input to VSIM ... FILTER. The labs ran on 8.10.1.

A Query Engine index for the semantic cache, from the redis.io vector docs. It was not run.

# NOT RUN: this Homebrew build has no Query Engine (FT.CREATE is an unknown command)
FT.CREATE idx:sem ON HASH PREFIX 1 sem: SCHEMA \
  tenant TAG  model TAG \
  vec VECTOR HNSW 6 TYPE FLOAT32 DIM 768 DISTANCE_METRIC COSINE
FT.SEARCH idx:sem "(@tenant:{acme} @model:{chat_v202609})=>[KNN 1 @vec $B]" \
  PARAMS 2 B <768 float32 bytes> LIMIT 0 1 DIALECT 2

Evidence
Recall and latency measured by the phase lab, three seeds, Redis 8.10.1 x86_64 under Rosetta 2. EF repeat runs at 10 gave 0.865 and 0.868. Vectors docs lines 112 and 444 for EF_RUNTIME 10. vset.c line 133 for EF 100. README "Scaling vector sets", line 628, and the recall table near line 660. Homebrew Formula/r/redis.rb line 61 and Redis README.md lines 49 and 219 at 8.10.2. Google Memorystore limits page for the duplicated vectors. Redis 8.10.2 release notes via gh api.

Caches and vectors can be rebuilt if Redis loses them. Agent memory is the first job where a lost or a permanent value changes what the model sees, and the next concept starts there.

## Why does a session with a TTL still leak memory?

Memory decides what the model sees next, and a lost TTL makes stale data permanent.

The support agent keeps each session's goal, plan and recent tool results in Redis, and sends them to the model on every turn. A price lookup is fresh for a minute, a weather lookup for a few minutes, and the session itself lasts 30 minutes. If a value outlives its TTL, the model reads stale data on every turn. If it never expires, memory also grows without a bound.

Agent memory has four tiers, and each has its own lifetime and Redis type.

TierRedis shapeHoldsLifetime

Working memoryhash per sessiongoal, plan, tool resultskey TTL 30 min, field TTLs for tool results

Historylist per sessionlast N messagesRPUSH + LTRIM, then trimmed by tokens before each call

Long-termvectors and textfacts about the userRedis index for recall, durable store for the truth

Checkpointsgraph state per stepa run's progress, to resume after a crashdurable store, or Redis with AOF and a TTL

Phase 1 showed that a hash field can carry its own TTL. HEXPIRE sets it since Redis 7.4, and HSETEX writes it together with the value since 8.0. For agent memory, the key fact is that a TTL belongs to the value that was written. It does not belong to the field name or the key name. So the next write to that field decides whether the TTL survives.

Predict: a tool result was written with HSETEX ... EX 300. Later code refreshes it with a plain HSET. What is the field's TTL now, and what does the model see in an hour?
The TTL is gone: HTTL returns -1. The model sees the old tool result for the life of the session key, or forever if the key has no TTL. Most people expect the field to keep its TTL, because an update feels like a change to the same thing. But Redis treats an overwrite as a new value, and the new value was written with no TTL.

The HEXPIRE page states the rule: field expirations are cleared only by commands that delete or overwrite the contents of the field. A command that changes the value in place keeps it. Three measured cases show the rule.

HSETEX p7:wm:{acme:s-42} EX 60 FIELDS 1 tool:prices v1   # HTTL -> 60
HSET   p7:wm:{acme:s-42} tool:prices v2                  # HTTL -> -1, never expires

HSETEX p7:wm:{acme:s-42} EX 60 FIELDS 1 tool:prices v3   # HTTL -> 60
HEXPIRE k 60 FIELDS 1 n ; HINCRBY k n 1                  # change, not overwrite: TTL kept

Inside Redis, the field TTL is stored with the field.

- A small hash with field TTLs uses an encoding that OBJECT ENCODING reports as listpackex. It stores field, value and TTL together, ordered by TTL.

- Each database tracks such hashes by their next field expiry, so Redis can find due fields without scanning every hash.

- Active expiry removes up to 10,000 / hz fields per call, where hz is how many times per second Redis runs its background jobs. When expired fields pile up, that budget is multiplied by up to 32.

- The field TTL costs memory. On the lab build, a one-field hash took 37 bytes without a field TTL and 71 bytes with one. A ten-field hash took 153 and 277 bytes. So a field TTL costs about 24 bytes per hash plus about 10 bytes per field. That fit uses two points: 34 extra bytes for 1 field and 124 for 10 fields.

Correction. The phase named the encoding listpack_ex, gave the expiry budget as 10000/hz without the multiplier, and called the extra memory inferred. OBJECT ENCODING replies listpackex, and in Redis 8.10.2 the budget is multiplied by up to 32 under load. The measured cost fits about 24 bytes per hash plus about 10 per field.

The second way to lose a TTL is a write and its EXPIRE sent as two calls. If the process dies between them, the key stays with TTL=-1. The lab reproduced it: SET without a TTL, then a crash before EXPIRE, left TTL=-1, while SET ... EX in one command left TTL=30m0s. Nothing reports either failure, so memory on the agent cluster grows slowly and no error names the cause.

Popular agent-memory libraries do not protect you from this. In the write paths of five libraries, none uses HEXPIRE, and all five default to no TTL. The Go deeper block below lists what each one does.

Go deeper: five memory libraries, Valkey, source lines, and how to find orphans
The five agent-memory libraries whose write paths were read.

LibraryStorageTTL defaultA fact to know

Redis Agent Memory Server, V0/one JSON document per sessionnoneJSON.SET, then EXPIRE in a second call

langgraph-checkpoint-redis 0.5.2JSON + Search indexes per checkpointnonedefault_ttl is in minutes

OpenAI Agents SDK RedisSessionhash + list + counternoneWATCH and MULTI, no LTRIM

LlamaIndex Redis chat storeone list per chatnoneno LTRIM, uses KEYS *, and delete_message reverses the order

mem0Redis as a vector storenonechange history goes to SQLite

- Valkey has HEXPIRE, HSETEX and HGETEX since 9.0.0. It converts a listpack hash to a hashtable as soon as a field gets a TTL, so small hashes with field TTLs cost more there. The extra memory on Valkey was not measured.

- The internal name of the encoding is OBJ_ENCODING_LISTPACK_EX, at src/t_hash.c line 1224 in 8.10.2.

- To find orphans, scan with a pattern that matches the hash-tagged key, such as p7:wm:{acme:*, and check TTL and HTTL. A pattern like p7:wm:acme:* does not match p7:wm:{acme:s-42}. Remove orphans with UNLINK.

- The Redis Agent Memory Server two-call write is at working_memory.py lines 648 to 652, from the course research. It was not re-opened for this lesson.

Evidence
HEXPIRE docs, line 49 of the page source. src/expire.c lines 102 and 263 to 271 at 8.10.2. Field-TTL memory and encoding measured with redis-cli on Redis 8.10.1 x86_64, libc malloc. Valkey hexpire.json and t_hash.c lines 486 to 495 at 9.1.2. langgraph-redis README line 318. OpenAI Agents SDK redis_session.py line 369 for the default TTL.

A TTL keeps memory from living forever, but it does not keep a session's history small enough for the prompt. The next section bounds the history.

## How do you bound a session's history twice, by count and by tokens?

The last section kept each value's TTL attached to it. A list of messages can still grow until it no longer fits in the prompt. A session of the support agent can run to hundreds of turns. If the platform keeps every message, both Redis memory and the model bill grow with each turn.

The first bound is a count in Redis. The lab appends 500 messages of about 150 bytes. The bounded list keeps the newest 50 with RPUSH, LTRIM -50 -1 and EXPIRE, sent together in one MULTI. So a crash cannot leave a list without its trim or its TTL.

A count bound is not a prompt bound, because 50 messages can differ by many times in tokens. So the application trims again by tokens before each model call. It keeps the system prompt, then adds the newest messages that fit in the budget, and never splits a message. In the lab, 21 messages and a budget of 2,000 tokens gave 9 messages and 1,950 tokens.

- RPUSH + LTRIM -50 -1 + EXPIREone MULTI per turn keeps at most 50 messages, with a TTL.

- LRANGE 0 -1reads the 50 before the model call.

- trim by tokenskeeps the system prompt, then the newest messages that fit.

- model callgets a prompt that fits, with room for the answer.

- durable storekeeps the full transcript if the user can return.

The full transcript goes to the durable store on every turn when a user can return tomorrow. The Redis keys are gone by then. Redis holds the short, fast copy that the model reads.

Agents also cancel many Redis calls, because users press stop in the middle of an answer. Phase 6 told the ChatGPT outage. There, a cancelled call left its reply on a pooled connection, and the next request read another user's data. The OpenAI Agents SDK discards a connection after a cancelled command for that reason.

Write each value and its TTL in one command, and bound history twice.

A plain HSET over a field with a TTL makes the stale result permanent.

Run go run ./phase07_ai_agents/agentmemory -turns 2000 -keep 50 and compare the two MEMORY USAGE lines.

Go deeper: checkpoints, and the cancel rule in the SDK

- A checkpoint stores an agent graph's state after each step, so a crashed run can resume. langgraph-checkpoint-redis writes JSON documents with Search indexes per checkpoint and has no TTL by default. Its default_ttl is counted in minutes, so a value of 60 means one hour. Keep checkpoints in a durable store, or in Redis with AOF and a TTL.

- The cancel block of the OpenAI Agents SDK is near line 576 of redis_session.py. The phase cites the file on main, where line numbers move, so read the block by its content.

- In the ChatGPT case, payment data of 1.2% of active ChatGPT Plus users in a nine-hour window may have been visible.

Evidence
List sizes and the token trim measured by the phase lab agentmemory, Redis 8.10.1 x86_64. OpenAI postmortem, archived copy, and redis-py issue 2624. OpenAI Agents SDK redis_session.py lines 576 to 582 on main, from the course research.

Memory is read at the start of a turn. The answer is written at the end, token by token, while the user watches. The next concept asks what that user misses when the connection drops.

## What does a viewer miss when it reconnects in the middle of an answer?

Phones change networks mid-answer, and without resume the user sees half an answer.

An answer from the support agent streams for several seconds. In that time a phone changes networks, a browser tab sleeps, or a load balancer drops an idle connection. The API pod that runs the model is often not the pod that serves the viewer. So the tokens pass through Redis, and the question is which Redis feature carries them.

Phase 6 showed that pub/sub keeps no copy of a message, so a server that was away cannot read what it missed. For tokens this means at-most-once delivery: each viewer gets each token once or never. Redis Streams give the other guarantee, because a stream keeps its entries and each entry has an ID. The entry ID is the reader's position, and a reader that reconnects calls XREAD with the last ID it saw to get the rest.

Predict: a phone loses signal for 4 seconds during an answer at 40 tokens per second. Viewer A reads tokens from pub/sub. Viewer B reads with XREAD from its last entry ID. How many tokens does each miss?
Viewer A misses about 4 × 40 = 160 tokens, and its text has a hole. Viewer B misses none, as long as the stream key still exists. Many people expect pub/sub to be fine because it is fast and the gap is short. Speed is not the problem: during the gap there is no subscriber, so Redis delivers those messages to nobody and keeps no copy.

400 tokens, one every 2 ms, viewer away for 150 ms.

Step 1: both viewers read the first 100 tokens as they arrive.

Step 2: the viewer is away for 150 ms. The stream keeps every entry, and pub/sub sends each token to no subscriber.

Step 3: the stream viewer reads from its last ID and ends with identical text. The pub/sub viewer has a hole.

Lane widths follow the lab setting of 2 ms per token, as an illustration. The token counts were measured in the tokenstream lab.

In the tokenstream lab the stream viewer received 400 of 400 tokens with identical text. The pub/sub viewer lost about 50 to 60 tokens in its 150 ms gap, about one token every 2.5 to 3.1 ms. Pub/sub also loses tokens a second way, because Redis closes a subscriber that reads too slowly. Unsent output waits in a buffer per client. The default client-output-buffer-limit pubsub 32mb 8mb 60 closes the client at 32 MB, or after 60 seconds above 8 MB. With the limit set to pubsub 1mb 0 0, a subscriber that stopped reading got 400 messages of 10 KB, and INFO stats showed client_output_buffer_limit_disconnections:1.

Correction. The phase gives the pub/sub loss as 49 to 57 of 400 tokens, from eight runs. Three later runs on the same build lost 58, 59 and 60, so expect about 50 to 60.

The design that follows from this has six rules.

- Use one key per response, resp:{response_id}. One key per response spreads the load over cluster slots, which is inferred.

- Append each chunk with XADD resp:{id} MAXLEN ~ 10000 * seq <n> t <chunk>. MAXLEN guards against a runaway answer, and the TTL is the normal bound.

- Set EXPIRE at the first chunk and again at the end.

- Write a final entry done 1, and let readers stop there. Do not delete the stream as the "done" signal, because a slow reader may not have read the last chunk yet.

- Let each viewer use plain XREAD with its own last ID. A consumer group per viewer keeps a pending list that nobody needs.

- Send the entry ID as the SSE event ID. SSE, Server-Sent Events, is the HTTP streaming format that a browser resumes by sending a Last-Event-ID header. XREAD is already exclusive, but XRANGE is inclusive, so to resume with it start at (<last id>.

Stardrift shows why an answer needs its own stream, and why rule 4 exists. Its agent tasks ran for minutes, so users tabbed away and came back to an interrupted chat. The conversation appeared only after a refresh. The first version streamed each answer over one HTTP connection and saved it to a database at the same time. Its final design writes chunks to a Redis stream keyed by chat and message. A separate key maps the chat to its active message. Stardrift kept that status key because deleting the stream at the end would race the reader. The reader may not have read the final chunk when the stream is deleted. The post gives no latency or volume numbers.

Batch tokens into fewer entries, by size and by time, such as 8 tokens or 50 ms, whichever comes first. In the lab, 8 tokens per entry cut 2,000 XADD calls to 250, and memory from 18 or 19 bytes per token to 7. The time limit keeps text moving when the model is slow.

Pub/sub is still useful as the wake-up path, when a durable copy lives elsewhere. LangSmith streams run output over pub/sub and stores no events in Redis, but its thread streams still resume with Last-Event-ID from another store. So the rule is narrower than "never pub/sub": never pub/sub alone, with no stored copy.

Go deeper: stream internals, two published libraries, and stopping an answer

- Vercel resumable-stream 2.2.13 keeps chunks in the producer's memory, not in Redis. It uses pub/sub plus one sentinel key with EX 86400, and a second reader asks the producer to replay. If the producer process dies, the answer cannot resume. This is inferred from the in-memory buffer, const chunks: string[] = [] in runtime.ts.

- Upstash AgentKit's EventLog stores each event in a stream with a TTL of 24 hours, set in the same Lua script as the XADD. It has no MAXLEN. Readers resume with XRANGE key (lastId + COUNT 500 and poll every 250 ms.

- The AI SDK docs say stop() only closes the connection, and a separate endpoint must cancel the work. Publish a cancel signal that the producer checks between chunks. LangSmith also keeps cancel signals in Redis.

- Where LangSmith keeps the events it replays for Last-Event-ID was not checked. Its docs say they are not in Redis.

A stream is stored as a radix tree of listpack nodes, each of up to 4,096 bytes or 100 entries. Each node stores the field names once and the IDs as differences from the first ID. So batching tokens into fewer entries saves both calls and memory. In the lab, 2,000 tokens written one call at a time gave the numbers below.

Tokens per entryXADD callsTimeMEMORY USAGEBytes per token

12,000192 to 209 msabout 37,00018 to 19

825023 to 27 msabout 14,2007

Evidence
Pub/sub docs, lines 51 and 54: at-most-once, a message to a disconnected subscriber "is forever lost". redis.conf line 2476 at 8.10.2, and CONFIG GET on 8.10.1 gave pubsub 33554432 8388608 60. Stream node limits in src/t_stream.c at 8.10.2. Token loss: eight phase runs and three study-note runs, Redis 8.10.1 x86_64 under Rosetta 2. Stardrift, "Is resumable LLM streaming hard? No, it's just annoying.", 2025-12-15. LangSmith data-plane line 42 and streaming page line 1055. Upstash event-log.ts at commit 7022274, vendor.

A viewer that reads twice only sees text twice. A worker that runs a paid tool call twice spends money twice, and the next section asks how a queue causes that.

## How does a tool call run twice, and what stops a second payment?

A stream lets a token viewer resume, because the viewer keeps its own position. A queue of tool calls needs the opposite guarantee, that each call takes effect once, and Redis cannot give it alone. The support agent calls paid tools that issue a refund, send an email or query a paid API at $0.01 a call. The platform puts these calls on a stream with a consumer group, so any worker pod can run them.

A consumer group gives each stream entry to one consumer, and keeps it in the group's PEL. The PEL, the pending entries list, holds the entries that were delivered and not yet acknowledged with XACK. If a worker crashes before XACK, another worker claims the entry with XAUTOCLAIM after a minimum idle time. So delivery is at-least-once: every entry runs, and some run twice. The worker must make the paid call idempotent, so that one call ID never pays twice. Phase 3 built the two parts this needs, a claim key written with SET ... NX PX and an idempotent effect that the resource refuses to repeat.

- worker A: XREADGROUPcall-1 is pending for A.

- SET idem:call-1 A NX PX 30000OK, so A owns the call for 30 s.

- paid call, $0.01the tool acts once.

- SET result:call-1the result is stored under the same ID.

- A crashes before XACKcall-1 stays pending.

- worker B: XAUTOCLAIM min-idle 200 ms250 ms later, call-1 moves to B.

- GET result:call-1: foundB reuses it and sends XACK. Paid calls = 1.

The toolqueue lab crashes a worker at three points.

CasePaid callsOutcome

no idempotency key, crash before XACK2, $0.02B pays again

key, crash after the result was stored1, $0.01B reuses the stored result

key, crash after the paid call, before the result1, $0.01B reports "unknown", and the entry stays pending

The third row is the gap that no Redis feature closes. The retry cannot know whether the tool acted, so paying again can charge twice and not paying can lose the call. Pass the call ID to the tool's own API as its idempotency key, if the tool accepts one. Only the tool can say whether it already acted. Otherwise send the entry to a person before the claim key's 30-second lease ends. After that, a retry claims the key and pays again, which is inferred from the lab code.

Redis 8 adds three commands that help with the queue. None of them protects the paid call itself.

- XADD ... IDMP <producer> <id>, since Redis 8.6, returns the first entry ID for a repeated producer and ID pair, and adds nothing. In the lab, two plain XADD calls gave two entries and two IDMP calls gave one. It keeps 100 IDs per producer for 100 seconds by default, and the docs report 2% to 5% lower throughput. It stops duplicate entries, not duplicate work.

- XNACK ... FAIL, since 8.8, releases an entry at once and keeps its delivery count. In the lab, XAUTOCLAIM with a min-idle of 60 seconds still claimed the released entry at once. After 3 deliveries the poison call went to a dead-letter stream and was acknowledged.

- DELEX key IFEQ owner, since 8.4, deletes the claim key only if it still holds your owner value, in one command.

Valkey 9.1.2 has none of these three commands, so the tool-queue pattern needs other commands there. The Go deeper block below gives one alternative for each.

Readers keep their own position, and workers keep an idempotency key with a stored result.

Acknowledging last and checking nothing first doubles the charge after a crash.

Run go run ./phase07_ai_agents/toolqueue and read the paid calls column: 2, 1, 1.

Go deeper: the Valkey alternatives, and queues of work that lived only in Redis
On Valkey 9.1.2, each Redis 8 command has an alternative.

Redis 8 commandOn Valkey 9.1.2

XNACK ... FAILXCLAIM <key> <group> <self> 0 <id> IDLE <min-idle> JUSTID. The next XAUTOCLAIM takes the entry at once, and JUSTID keeps the delivery count.

XADD ... IDMPa Lua script that returns the ID stored in the pair key, or runs XADD and SET <pair key> <id> EX 100

DELEX key IFEQ ownerDELIFEQ key owner since Valkey 9.0.0, or the Lua compare-and-delete of Phase 3

The first two alternatives ran on Redis 8.10.1, not on Valkey. The delivery count stayed at 1 after XCLAIM ... JUSTID, and two script calls with the same pair gave one entry.

- Discord fed new messages to its search indexing workers through a Redis queue. When Elasticsearch nodes failed, the queue backed up, Redis CPU hit its limit and Redis dropped messages. Discord moved that queue to Google Cloud Pub/Sub, which guarantees delivery.

- Slack kept its job queue in Redis, with over 1.4 billion jobs on busy days and a peak of 33,000 jobs per second. When database contention slowed the workers, jobs piled up until Redis reached maxmemory. Dequeue also needs free memory, because it moves a job into an in-flight list, so the queue stayed stuck after the database recovered. Slack put Kafka in front of Redis, with a relay that moves jobs at a controlled rate.

- Inngest, from the first section, shows the same lesson for tenants: one tenant that filled memory stopped the queue for every tenant.

- Valkey's t_stream.c skips the delivery-count increment for JUSTID, at lines 3277 to 3281 of tag 9.1.2. At Redis 8.10.2, xnack.json says since 8.8.0 and delex.json since 8.4.0.

Evidence
Measured by the phase lab toolqueue on Redis 8.10.1, and the "unknown" path is toolqueue/main.go:107. Streams idempotency docs, lines 17, 100 and 101. XNACK docs, lines 26 and 49. Valkey command files at tag 9.1.2: xnack.json and delex.json return 404, and xadd.json has no IDMP. Discord, "How Discord Indexes Trillions of Messages", 2025-04-24. Slack, "Scaling Slack's Job Queue", 2017-12-06.

The queue decides how often a paid call runs. The provider decides how many calls it accepts per minute, and the last concept asks how all pods share that limit.

## What should a shared limiter count for LLM calls?

Providers limit tokens per minute, so a request counter admits the wrong amount of work.

The platform's pods share one provider account, and the provider limits each model. If the pods count requests, a few long prompts use the whole budget. Then every pod gets a 429, the HTTP status for "too many requests". If the pods count too much per call, they refuse work the provider would accept.

Providers count tokens, not requests. Anthropic limits requests, input tokens and output tokens per minute with a token bucket. A token bucket is a counter that refills at a steady rate, so capacity returns continuously. OpenAI counts the larger of max_tokens and an estimate from the character count of the request, and failed requests also count against the limit. The real use of a call is known only after the answer ends. So a shared limiter has to reserve an estimate before the call and correct it to the real use after the call.

Airbnb met the same problem in its key-value store. Its first rate limiter was a Redis counter per caller that returned 429 over quota, and every request cost the same. A one-row read counted the same as a scan of 100,000 rows, so the limit did not follow the real load on the backend. The new system gives each request a cost, which is the same move as counting tokens instead of calls.

Predict: each call reserves 3,000 tokens and really uses 1,200. The limit is 400,000 tokens per minute. How many calls per minute pass with and without the correction?
Without the correction, 400,000 / 3,000 = 133 calls pass. With it, a call passes while 1,200 × n + 3,000 ≤ 400,000, so n ≤ 330 and 331 calls pass, about 2.5 times more. Many people think counting the estimate is close enough, because it is safe. It is safe, but with estimates 2.5 times the real use, the limiter admits only 40% of what fits, and users see 429s from your own code.

Redis 8.8.0 added INCREX, which increments a counter, checks a bound and sets a TTL in one O(1) command. So the reserve needs no Lua script.

pod                        Redis counter tpm:{acme}:model-x:<w>
INCREX BYINT 1500 UBOUND 10000 PX 60000 ENX   -> [1500, 1500]   applied > 0: call the provider
... the call uses 600 tokens ...
INCREX BYINT -900 PX 60000 ENX  (same <w>)    -> [600, -900]    the correction always applies
if a reserve returns applied == 0             -> queue the call, or return 429 to the caller

- The reply is [new value, applied increment]. Without SATURATE, a result past the bound is rejected, nothing is written, and the reply is [current, 0].

- ENX sets the TTL only when the key has none. So a later call or a correction never extends the window.

- With no bound given, every increment applies, because the bounds default to the limits of a 64-bit integer.

- The docs mark INCREX as not supported on Redis Software and Redis Cloud, and Valkey 9.1.2 has no INCREX. On those, use a Lua script of INCRBY and PEXPIRE, or the sorted-set window of Phase 1.

Calls admitted per window.

Limit, tokens per window
Estimate per call
Real use per call
Reserve only:  calls. Reserve, then correct:  calls. Budget left unused without the correction: .

The formula from this section. The lab's case is a limit of 10,000, an estimate of 1,500 and a real use of 600, which gives 6 and 15.

The lab measured that case with 30 calls in one 60-second window.

BudgetCalls admitted of 30CounterReal tokens

reserve only, no correction69,0003,600

reserve, then correction159,0009,000

Both counters end at 9,000, but the first budget turned away 9 calls that fit, while 64% of the limit was unused. Each corrected call leaves 600, and a new call needs 1,500 free. So 600 × 14 + 1,500 = 9,900 fits, and 600 × 15 + 1,500 = 10,500 does not.

The correction itself must have no bound. With the counter at 9,900, a call that used 400 more than its estimate tried to add 400. INCREX ... UBOUND 10000 rejected it with applied=0, so the counter stayed at 9,900 while real use was 10,300. The bound is for admission, and a correction records what already happened.

Evidence
OpenAI rate-limits guide: the maximum of max_tokens and the character estimate, and unsuccessful requests count. Anthropic rate-limits page, lines 26 and 129: "the token bucket algorithm", and max_tokens does not count toward OTPM. src/commands/increx.json and src/t_string.c lines 1033, 1034 and 1265 to 1275 at 8.10.2. INCREX docs, compatibility table at line 212. Airbnb, "From Static Rate Limiting to Adaptive Traffic Management in Airbnb's Key-Value Store", no date on the page. Budget runs measured by the phase lab llmlimits.

The correction works while its window is open. A long answer can end after its window has closed, and the next section shows where that correction then goes.

## Where does a correction go when the answer ends after its window?

Reserve and correct admits the right number of calls while each call ends inside its window. A long generation or a slow tool loop can outlive a 60-second window. Then the correction arrives when its key has expired, or when the key belongs to the next window.

The lab tested this with a 1-second window and a reserve of 1,500. The call used 600, and the -900 correction came 1.2 seconds later. The right answer is that the next window admits 6 calls, the same as a fresh window.

- t=0 s The reserve runs INCREX ... BYINT 1500 PX 1000 ENX, and the window key now holds 1,500.

- t=1.0 s The window key expires with the window.

- t=1.0 s+ In case B, a new call reserves first, and creates the key for the next window.

- t=1.2 s The late -900 correction arrives.

Key and correctionAfter the correctionNext window admits

one key, INCRBY, no call between (case A)-900, PTTL -17 calls

one key, INCRBY, a call opened the next window (case B)6007 calls

key per window, INCREX ... PX ENXold key -900, PTTL 999 ms6 calls

Both wrong rows give the next window 900 free tokens it should not have. In case A, the INCRBY creates a new key at -900 with no TTL, so it never expires if no call comes. In case B, the correction lands on the next window's key. A Lua guard that corrects only an existing key does not help in case B. The key it finds is the next window's key, so the window still admitted 7.

The fix has two parts.

- Put the window index in the key name: tpm:{acme}:model-x:<w>, with w = unix ms / 60,000, rounded down. The reserve picks the name, and the correction reuses it. So a late correction goes to the old window's key and never reaches the next one.

- Correct with INCREX key BYINT d PX <window> ENX, with no bound. It keeps the reserve's TTL, and if the old key has expired, it creates the key again with a TTL, never without one. No reserve reads that old name again.

Each pod computes w from its own clock, so clock skew moves the window edge a little for each pod. That trade-off is inferred and was not measured.

A fixed window has a second edge problem. It allows up to twice the limit across the boundary between two windows. The lab admitted 999 tokens at the end of a 2-second window and 1,000 at the start of the next. So 1,999 tokens passed in 147 to 152 ms, against a limit of 1,000 per 2 seconds. Anthropic's token bucket can refuse that burst even though your counter allowed it. So use a window shorter than the provider's, or the sliding window of Phase 1.

Go deeper: the source lines behind ENX, and a fixed-window limiter at Lyft

- src/t_string.c at 8.10.2, lines 1186 and 1187: if no expiration option is given, the key's existing TTL is kept, and ENX limits expiration updates to keys that have no TTL. Line 1300 implements it.

- Lyft's rate limit service for Envoy builds a key from a domain and descriptors and counts in Redis. Per-second limits can go to a separate Redis, and a pipeline window of 150 to 500 µs is suggested. An optional local cache keeps keys that are already over their limit, so those requests skip Redis. That it uses fixed-window counters with a TTL is inferred from its README.

Evidence
Late-correction cases measured by the phase lab llmlimits -part budget part 4, six runs with the same counts, PTTL 996 to 999 ms. The Lua guard run was made with redis-cli. Window edge, eight phase runs and one study-note run. Lyft: the envoyproxy/ratelimit README.

A token budget limits how much work starts each minute. The provider also limits how many calls run at the same time. The last section adds that limit and a shared response to a 429.

## How do pods cap calls in flight and share one 429?

The window budget now admits the right number of tokens each minute, even when corrections arrive late. Two more limits act on calls that are already running. A cap on calls in flight stops the pods from opening more calls than the provider allows at once. A shared pause stops every pod when one of them gets a 429.

A semaphore is a counter of free slots. Here it is a sorted set of holder IDs, each scored by the time its lease ends, read from the Redis clock. The script removes expired leases before each acquire, so a holder that crashed without a release loses its slot when its lease ends. This is the lease idea of Phase 3, applied to N slots instead of one lock. The code is from llmlimits/main.go:310.

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

With 4 slots, 12 workers and calls of 300 ms, the peak in flight was 4. All calls finished in 907 to 932 ms, against a minimum of 900 ms. Then one holder crashed without a release.

INCR and DECR counter

3 of 4 slots free at t = 1.1 s, and forever after. The crashed holder's slot never comes back.

Lease semaphore

3 of 4 slots free right after the crash, and 4 of 4 at t = 1.1 s, when the lease ended.

Make the lease longer than a normal call, and renew it during the call. Phase 3 showed what happens to work that outlives its lease.

When one pod gets a 429 with a retry-after header, every pod should pause, not only that one. Every pod checks a key pause:{provider}:{model} before a call. The pod that got the 429 sets it with SET pause:{provider}:{model} 1 PX <retry_after_ms> NX. In the lab, 5 pods sent a call every 100 ms while the provider refused calls for 1.5 seconds.

Pause429 responsesSuccessful calls

none74 to 7524 to 25

per pod, local524 to 25

shared key in Redis124 to 25

The successful calls are the same in every row, so the extra 429s bought nothing. They also cost budget, because OpenAI counts failed requests toward the limit.

A global semaphore alone lets a busy tenant take every slot. So the same script also checks a cap per tenant, which is why it loops over several keys. With 8 global slots and a cap of 6, the small tenant's average wait fell from as much as 640 ms to about 100 ms. In the running case, acme's batch job can no longer make globex's users wait.

Decide what happens when Redis itself fails. For a provider limit, fail open with a small local limit per pod, because the provider still enforces its own limit. For a spend cap, fail closed, because nothing else stops the spending.

Reserve and correct per window key, lease the slots, and share each 429.

A reserve with no correction admitted 6 calls of 15 and left 64% unused.

Run go run ./phase07_ai_agents/llmlimits -part budget and compare part 4's WRONG and RIGHT rows.

Go deeper: the fairness runs, LiteLLM's limiter, and why the script reads the Redis clock
The fairness run used 8 global slots, 40 calls from tenant big and 4 from tenant small, 200 ms each, over seven runs.

Per-tenant capsmall waits on averagebig waits on average

8, no cap233 to 640 ms442 to 487 ms

692 to 102 ms579 to 589 ms

The cap costs the big tenant about 100 to 150 ms of wait, and keeps 2 slots for the small tenant at all times.

- LiteLLM's in-flight gauge is a similar sorted set, scored by acquire time instead of lease expiry, with Redis TIME and a slot TTL of 3,600 s. Its file header says it is "not yet ready for production".

- LiteLLM shares a cooldown through Redis. The length is the deployment's cooldown_time, else the provider's retry-after header, else 5 seconds.

- If Redis fails, LiteLLM falls back to a window per instance, so N pods can each admit the full limit.

- The script reads TIME from Redis instead of taking now from the client, so every pod compares leases against one clock. A client clock that runs fast could remove other holders' leases early, which is inferred from the script.

- The Lua scripts and the shared pause key are tested by the live runs, not by the offline self-test.

Evidence
Semaphore, 429 and fairness numbers measured by the phase lab llmlimits, Redis 8.10.1 x86_64 under Rosetta 2. LiteLLM litellm/router.py at commit 9c958af, lines 9182 to 9203, and parallel_request_limiter_v3.py lines 1 to 5.

That completes the five concepts. The recall section below puts them side by side.

## What you can do now, and what comes next

You can now design each of the platform's six Redis jobs. You can also say what each one loses when something fails. Each question below comes from one concept.

- How often is this semantic cache wrong? The threshold sets the hit rate, and in the AWS test 0.99 still served 7.9% wrong hits. Scope every entry by tenant, locale, model version, template version and embedding model, and measure the wrong share on labelled prompts. Concept c1, the first three teaching sections.

- How much memory will this vector index take, and what limits its recall? At M 16 an element costs about 691 bytes plus its vector, and Q8 stopped recall at 0.975 where NOQUANT reached 1.000. Concept c2.

- Can any write in this memory path lose its TTL? A plain HSET over a field with a TTL, or a write and its EXPIRE in two calls, leaves memory that never expires. Bound history by count in Redis and by tokens before the call. Concept c3.

- What does a reader or a worker miss after a disconnect or a crash? A stream per response lets the viewer resume from its last ID. An idempotency key with a stored result keeps a paid tool call from running twice. Concept c4.

- Does this limiter admit what the provider would accept? Reserve an estimate and correct it on the same window key. Cap calls in flight with leases, and share each 429 through one pause key. Concept c5.

This is the last phase of the Redis course, so no later phase follows it. As a next step, take one agent service you work on and run lab E1 to check each rule. Then trace each Redis call of that service against the five questions above.

## Lab: eleven Go exercises on a throwaway Redis

Open the lab: setup, exercises E1 to E11, and the code questions

This lab is copied exactly from the phase. Its programs ran on a local Redis 8.10.1, x86_64 under Rosetta 2, on ports 6571 to 6574, and the "Expected" lines are their real output. The Query Engine steps did not run, because this Homebrew build has no Query Engine. No lab calls a model, and the embeddings are fake and deterministic. Never point the labs at a shared or production Redis.

Every command below ran on 2026-10-19, with Go 1.27.1 and go-redis v9.5.1, on port 6571 with no persistence. The "Expected" lines are real output, as ranges where runs differed.

Setup:

cd study-material/redis/code
mkdir -p /tmp/p7redis
redis-server --port 6571 --dir /tmp/p7redis --save '' --appendonly no --daemonize yes
redis-cli -p 6571 INFO server | grep redis_version     # redis_version:8.10.1
redis-cli -p 6571 VADD probe VALUES 3 1 0 0 a           # (integer) 1, so vector sets exist
redis-cli -p 6571 DEL probe

The labs refuse port 6379, which usually holds real data, unless you pass -allow-6379. They delete only p7: keys.

-  E1 (offline). all concepts Run every self-test.

- Run: for d in semcache vectorsets agentmemory tokenstream llmlimits toolqueue; do go run ./phase07_ai_agents/$d -self-test | tail -1; done

- Expected: all checks passed six times.

- If it fails: no hash collisions fails when fakeembed.Dim is not 2048.

- Teaches: each rule in the text has a check.

-  E2 (local). c1 Measure exact and semantic caching.

- Run: go run ./phase07_ai_agents/semcache

- Expected: the exact-match row shows 2 hits. The 0.78 row shows 16 hits and 2 wrong. The 0.90 row shows 10 hits, 0 wrong and 6 missed.

- Teaches: exact match misses paraphrases, and semantic hits can be wrong.

-  E3 (break-it, local). c1 Remove the tenant scope.

- Run: go run ./phase07_ai_agents/semcache -scope none

- Expected: globex cos=1.000 HIT A05 ... <-- WRONG answer served. The 0.90 row has 2 wrong hits, because acme also receives G01.

- Teaches: the scope is part of correctness, not a tuning option.

-  E4 (local). c2 Measure vector set memory and recall.

- Run: go run ./phase07_ai_agents/vectorsets and repeat with -seed 2 and -seed 3.

- Expected, seed 1: NOQUANT ... 1203 ... 1.000, Q8 ... 819 ... 0.975, BIN ... 707 ... 0.17. EF 10 gives recall near 0.87.

- Teaches: per-element overhead and the Q8 recall limit.

An extra run at real dimensions shows the same 691-byte overhead: the study note ran vectorsets with -dim 1536 -n 10000 -queries 100 -shards 1 -efs 100 and got 6,835, 2,227 and 883 bytes per element. BIN recall varies between runs, even with the same seed, because the HNSW build is not deterministic. Seed 1 gave 0.167 and 0.173 in two runs, and seeds 1 to 3 gave 0.150 to 0.176.

-  E5 (break-it, local). c2 Use BIN on sparse vectors.

- Run: go run ./phase07_ai_agents/semcache -quant BIN

- Expected: every threshold row shows 26 hits and 11 wrong. The gap line shows 0.9961 (BIN).

- Teaches: binary quantisation destroys scores for sparse vectors.

-  E6 (break-it, local). c3 Watch a field expire, then lose a TTL two ways.

- Run: go run ./phase07_ai_agents/agentmemory

- Expected: HTTL goal, plan, tool:weather:paris -> [-1 -1 2], then after 2.5 s: fields=[goal plan], session key exists=1. Sections 3 and 4 show plain HSET -> HTTL [-1] and two calls, crash between: TTL=-1.

- Teaches: per-field lifetimes, and how a TTL disappears silently.

-  E7 (break-it, local). c4 Disconnect a viewer for twice as long.

- Run: go run ./phase07_ai_agents/tokenstream -gap 300ms

- Expected: the stream viewer shows 400 of 400 tokens, reconnects=1, text identical=true. The pub/sub viewer loses 98 to 112 tokens, about twice the default run.

- Teaches: pub/sub loses the gap, and a stream does not.

-  E8 (local). c5 Reserve and correct a token budget.

- Run: go run ./phase07_ai_agents/llmlimits -part budget

- Expected: admitted  6 of 30 and admitted 15 of 30, then INCREX +400 UBOUND 10000  applied=0 -> counter=9900, then 1999 tokens admitted within about 150 ms. Part 4 shows admitted 7 in WRONG rows and admitted 6 in RIGHT rows.

- Teaches: the correction, the INCREX trap, the window edge and the late correction.

-  E9 (break-it, local). c5 Crash a semaphore holder.

- Run: go run ./phase07_ai_agents/llmlimits -part semaphore

- Expected: lease semaphore  : free slots at t=0.0 s: 3 of 4, at t=1.1 s: 4 of 4 and INCR/DECR counter: ... at t=1.1 s: 3 of 4, and forever after.

- Teaches: a lease returns a crashed holder's slot, and a counter does not.

-  E10 (local). c5 Share a 429 and cap a tenant.

- Run: go run ./phase07_ai_agents/llmlimits -part 429 and go run ./phase07_ai_agents/llmlimits -part fairness

- Expected: 429 responses = 74 or 75, then 5, then 1, for none, local and shared. per-tenant cap 6: small waits about 100 ms.

- Teaches: one pause key for all pods, and a cap per tenant.

-  E11 (break-it, local). c4 Crash a worker after a paid call.

- Run: go run ./phase07_ai_agents/toolqueue

- Expected: paid calls=2 ($0.02) without a key, paid calls=1 ($0.01) with one, and unknown: key taken, no result for the crash before the result.

- Teaches: at-least-once delivery plus an idempotency key.

Shut the server down when you finish:

redis-cli -p 6571 SHUTDOWN NOSAVE

Where the labs stop matching reality. The embeddings, vectors, provider, paid tool and token timing are fake. Real models give other hit and error rates. The Query Engine steps did not run.

### Check it yourself

- Open code/phase07_ai_agents/semcache/main.go:154. This is the scope rule inside lookupMemory. Delete the continue and run -self-test. Which check fails, and what does its detail show?

- Open code/phase07_ai_agents/llmlimits/main.go:315. This is the ZREMRANGEBYSCORE step of acquireLua, modelled in Go at line 534. Why does the script read TIME from Redis instead of taking now from the client, as Redisson's RPermitExpirableSemaphore does?

- Open code/phase07_ai_agents/toolqueue/main.go:107. handle returns "unknown" when the key is taken and no result exists. Name one tool where "unknown" must go to a person, and one where a second call is harmless.

- In any agent service you own, run:
grep -rniE "hset|expire|publish" <your repo>/ | grep -iE "session|memory|stream|token"

Find each HSET on a field with a TTL, and each EXPIRE sent apart from its write. What does a crash between the two leave?

## Checkpoint questions

Open the questions: seven scenarios, each with an answer sketch

Q1. Walk through what happens when a user loses signal for 4 s during an answer at 40 tokens/s. Compare pub/sub with a stream per response. How many tokens does each viewer miss, and what does the browser send on reconnect?

Answer sketchThe gap is 4 s × 40 = 160 tokens, and pub/sub loses all of them. The browser sends Last-Event-ID: <last entry ID>, and the server calls XREAD STREAMS resp:{id} <that ID>. The stream viewer misses 0. If the TTL ran out, the server loads the answer from the durable store. Concept c4.

Q2. A colleague says "set the threshold to 0.99, then wrong answers are impossible." Argue against it with the AWS numbers. What would you measure instead, and on what data?

Answer sketchIn the AWS test, 0.99 kept a 23.5% hit rate, and 7.9% of hits were still wrong, against 8.8% at 0.75. The threshold mostly removed right hits. vCache found that right and wrong hits had mean similarities of 0.84 and 0.85. Measure hit rate and wrong share on labelled prompts from your own traffic. Concept c1.

Q3. Given these constraints, design working memory for an agent. Sessions last up to 2 hours. Tool results go stale after 5 minutes. Users can return tomorrow. The context is 32,000 tokens. Name each key, its type and TTL, and what also goes to the durable store.

Answer sketchwm:{t:s}: hash, EXPIRE 2 h on each write, tool fields with HSETEX EX 300. hist:{t:s}: list, RPUSH, LTRIM -50 -1 and EXPIRE 7200 in one MULTI, then trimmed by tokens to 32,000 minus the answer budget. The transcript goes to the durable store every turn, since the Redis keys are gone by tomorrow. Concept c3.

Q4. This is broken. Memory on the agent cluster grows 3% a day. SCAN shows sessions with TTL -1 and tool fields with HTTL -1. No deploy changed the TTL settings. What is the cause, and how do you check it?

Answer sketchCause one: a write and its EXPIRE sent in two calls. Cause two: a plain HSET over a field with a TTL. Grep the write paths for both, and reproduce them with agentmemory sections 3 and 4. Fix with SET ... EX, HSETEX or MULTI, then remove orphans with SCAN and UNLINK. Concept c3.

Q5. Show the arithmetic. You need 2 million vectors of 768 dims in vector sets, M 16. Use the lab's 691 bytes of overhead per element. Compute the memory for NOQUANT and Q8, and the Q8 recall you expect on the lab data.

Answer sketchNOQUANT: 768 × 4 = 3,072 + 691 = 3,763 bytes × 2 M = about 7.5 GB. Q8: 768 + 691 = 1,459 bytes × 2 M = about 2.9 GB. On the synthetic lab data, Q8 recall@10 was 0.966 to 0.975 at 128 and 384 dims, and 0.983 at 1,536 dims. Measure it on your own vectors. Concept c2.

Q6. Given these constraints, design a limiter for one model: 400,000 tokens per minute, 30 pods, 50 tenants. A tenant may use at most 25% of it, and have at most 10 calls in flight. A call estimates 3,000 tokens and uses 1,200 on average. Write the Redis commands for one call. How many calls per minute does it admit, with and without the correction?

Answer sketchPer call, with w the minute index: INCREX itpm:{model}:tenant:{t}:<w> BYINT 3000 UBOUND 100000 PX 60000 ENX for the 25% cap. Then the same on itpm:{model}:all:<w> with UBOUND 400000. Then the lease semaphore with a limit of 10 on inflight:{model}:{t}. After the call, INCREX ... BYINT -1800 PX 60000 ENX both keys of the same w, even if that minute ended. If the global step rejects, return the tenant reservation the same way. Without the correction: 400,000 / 3,000 = 133 calls per minute. With it, a call passes while 1,200 × n + 3,000 ≤ 400,000. So n ≤ 330, and 331 calls pass. Concept c5.

Q7. Plan a change. The platform moves its semantic cache to a new embedding model on Monday. The cache holds 2 million entries for acme and globex, keyed by a hash of prompt and tenant. What breaks, and what do you change in the keys or the index?

Answer sketchEvery stored vector is in the old model's vector space, so new query vectors no longer match them in a meaningful way. Hits stop meaning anything, and with RedisVL's default of no TTL the old entries never expire on their own. Put the embedding model and its version in the index name or a tag, build the new index next to the old one, and switch reads to it. RedisVL refuses a schema change, such as a new vector dimension, unless you pass overwrite=True. A new model with the same dimension passes that check, so the index name or tag is the real guard. Concept c1.

## Cheatsheet

Open the cheatsheet
SIX JOBS, AND THE RULE
  only in Redis : answer cache, embedding cache, token buffers, limit counters
  also durable  : transcripts, runs, long-term memory, paid tool results
  shared Redis  : not allkeys-lru for cache + memory; separate, or TTLs + volatile-lru

c1 SEMANTIC CACHE
  scope key/tag : tenant + locale + model version + template version + embedding model
  threshold     : sets hit rate, not error rate; measure on your labelled prompts
  AWS test      : 0.99 -> 23.5% hits, 7.9% wrong; 0.75 -> 90.3% hits, 8.8% wrong, cost -86.3%
  RedisVL       : distance 0.1 (~0.9 sim), 1 result, TTL none, TTL refreshed on hit
  LangCache     : similarity 0.85, no expiration
  TTL           : daily data ~23 h + jitter; delete by tag when a source doc changes
  prompt cache  : provider reuses the prefix, never the answer; Anthropic 5 min default

c2 VECTOR SETS (Redis 8)
  VADD key FP32 <blob> <id> [Q8|NOQUANT|BIN]   default Q8, M 16, EF build 200
  VSIM key FP32 <blob> WITHSCORES COUNT k      score = (cos+1)/2, EF 100, COUNT 10
  bytes/elem    : vector + ~393 + 18.7 x M  (691 B at M 16; x86_64 libc build)
  measured 128d : NOQUANT 1203, Q8 819, BIN 707;   1536d: 6835 / 2227 / 883
  recall@10     : NOQUANT 1.000, Q8 0.971, BIN 0.15-0.18 (3 seeds, synthetic)
  EF            : 10 -> 0.870, 100 -> 0.975, 500 -> 0.975 at +77% p50
  scale         : one key = one shard; N keys, query all, merge by score
QUERY ENGINE    : FLAT < 1M, HNSW M16 EFC200 EF_RUNTIME 10 (not 100), SVS-VAMANA 8.2+
                  not in the Homebrew build; bundled in Redis 8.10.2
VALKEY 9.1.2    : valkey-search FT.* HNSW/FLAT; no vector sets, INCREX, XNACK, IDMP, DELEX
SECURITY        : 8.10.2 fixes a VSIM FILTER nested-JSON crash; upgrade before user input

c3 MEMORY
  HSETEX key EX 300 FIELDS 1 f v    plain HSET clears the field TTL; HINCRBY keeps it
  encoding      : listpackex; field TTL ~ +24 B per hash, +10 B per field
  active expiry : 10000/hz fields per call, up to x32 under backlog
  RPUSH + LTRIM -N -1 + EXPIRE      in one MULTI; then trim by tokens
  SET k v EX ttl                    never SET then EXPIRE in two calls
  langgraph     : default_ttl is in MINUTES

c4 TOKEN STREAMS
  XADD resp:{id} MAXLEN ~ 10000 * seq n t chunk ; EXPIRE at first and last
  end           : final entry done 1; never delete the stream as the signal
  resume        : XREAD STREAMS resp:{id} <lastId>  (XRANGE needs "(lastId")
  pub/sub       : at-most-once; lab lost ~50-60 of 400 in 150 ms; pubsub 32mb 8mb 60
  batch 8 tok   : 250 XADD not 2000; 7 B/token not 18-19

c4 TOOL QUEUE
  delivery      : at least once; XAUTOCLAIM after min-idle; XNACK FAIL (8.8)
  producer      : XADD ... IDMP pid iid (8.6), default 100 s / 100 ids, 2-5% slower
  worker        : SET idem:{call} owner NX PX; store result:{call}; XACK last
  crash gap     : paid, no result -> "unknown"; to a person within the key lease
  Valkey 9.1.2  : XCLAIM ... IDLE <min-idle> JUSTID; Lua SET + XADD; DELIFEQ

c5 LIMITS
  reserve       : INCREX k:<w> BYINT est UBOUND lim PX 60000 ENX; w = ms / 60000
  correct       : INCREX k:<same w> BYINT (actual - est) PX 60000 ENX, no bound
  admitted      : no correction floor(L/e); with floor((L-e)/r)+1  (lab 6 vs 15)
  window edge   : up to 2x limit (lab 1999 of 1000 in ~150 ms)
  in flight     : ZSET holder->lease expiry, Redis TIME, ZREMRANGEBYSCORE first
  shared 429    : SET pause:{prov}:{model} 1 PX retry_after NX  (lab 75 -> 1)
  per tenant    : cap 6 of 8: small waits ~100 ms, big +100-150 ms
  Redis down    : provider limit fail open (small local limit); spend cap fail closed

## Sources

Open the sources
The phase's URLs returned HTTP 200 on 2026-10-19. Sources from the seller of a product are marked vendor.

- INCREX, Redis docs: the window counter pattern, O(1), ENX, and the compatibility table.

- HEXPIRE, Redis docs: what clears a field TTL, and the per-field reply codes.

- Vector sets README at tag 8.10.2: memory per node, scaling by splitting keys, and the recall table near line 660.

- Vector search, Query Engine docs: FLAT, HNSW and SVS-VAMANA parameters, EF_RUNTIME 10, and hybrid query modes.

- Streams idempotency, Redis docs: IDMP parameters, 100 s and 100 IDs, and expiration.

- Pub/sub, Redis docs: at-most-once delivery, and lost messages for a disconnected subscriber.

- LangCache concepts: similarity 0.85 by default, no expiration, deletion by attributes. Vendor.

- vCache, arXiv 2502.03771: right and wrong hits at 0.84 and 0.85, and per-entry thresholds. A preprint.

- AWS, ElastiCache as a semantic cache: hit rate, accuracy and cost per threshold over 63,796 queries. Vendor.

- Anthropic prompt caching: the answer is not cached, and the default lifetime is 5 minutes.

- LangSmith data plane: what Redis holds and what Postgres holds. Vendor.

- LangSmith streaming: thread streams resume with Last-Event-ID. Vendor.

- langgraph-redis: default_ttl in minutes, and the shallow saver.

- OpenAI Agents SDK RedisSession: the WATCH and MULTI write, and the cancel block. Cited on main, so line numbers move.

- Vercel resumable-stream: chunks buffered in the producer's memory, in src/runtime.ts.

- Stardrift, resumable LLM streaming: chunks in a Redis stream, and the race when the stream is deleted at the end.

- LiteLLM limiter v3: the sorted-set gauge and the fail-open fallback. Cited on main. The cooldown order comes from router.py at commit 9c958af.

- Anthropic rate limits: the token bucket, and retry-after.

- OpenAI rate limits: the larger of max_tokens and the estimate counts, and failed requests count.

- Airbnb, from static rate limiting to adaptive traffic management: a Redis counter per caller where every request cost the same.

- envoyproxy/ratelimit: Lyft's rate limit service with counters in Redis.

- Inngest, Our Migration to FoundationDB, Part 1: why the queue left Valkey. Vendor.

- Inngest, Part 2: about 20,000 accounts per logical shard. Vendor.

- Inngest, fairness in a multi-tenant queue: the post the phase cited under another title. Vendor.

- Discord, How Discord Indexes Trillions of Messages: a Redis queue that dropped messages under backlog.

- Slack, Scaling Slack's Job Queue: a full Redis that could not dequeue.

- OpenAI, March 20 ChatGPT outage, archived: the cancelled-request mechanism. Read with redis-py issue 2624.

- Valkey issue 2569, vector sets: open on 2026-10-19.

- Google Memorystore vector search limits: vectors duplicated in Valkey's search module before 1.3.