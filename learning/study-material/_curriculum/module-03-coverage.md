# Module 3 — Retrieval Engineering Internals

Status: COMPLETE. Course folder: `study-material/retrieval-internals/`. Code: `study-material/retrieval-internals/code/`. This file was written on 2026-09-23.

This file lists what Module 3 teaches, section by section. Later modules link to it and do not teach the same thing again. Link in the form `Module 3, 4.2`.

## How this file was checked

- **Source of truth.** The seven phase documents, `course.json`, `code/` and `code/common/HARNESS.md`. The old dossier, `_curriculum/module-03-retrieval-internals.md`, was read only to confirm which of its claims the course corrected.
- **Headings.** Copied from the phase documents with `grep -n '^#'`. Verified.
- **Lab numbers.** 66 lab commands were run again on 2026-09-23. The machine was an Apple M4 Pro with 14 cores and 24 GiB of memory, on macOS 26.6. The runs used uv 0.12.8 and Python 3.12.14. Each ran as `RI_OFFLINE=1 uv run --offline python ...` from `code/`. The 1-minute load average was 3 to 11. Every quality number marked "lab, re-run" matched the phase text. Times did not always match. The tables say where. Verified.
- **Self-tests.** All 58 scripts passed in the same session, with the check counts the lab sections state. The counts are in "Shared code". Verified.
- **Paper, source-code and documentation numbers.** Copied from the phase text, which names the table, file and line, or page. The sources were not opened again for this file. They are marked "cited".
- **Code line references,** such as `metrics.py:117`. Checked with `sed -n`. Five references in the phase text have moved. They are listed under "Corrections". Verified.

The "Checked" column in each table uses four values:

- **lab, re-run**: the command was run on 2026-09-23 and printed this number.
- **lab, not re-run**: the phase text states a lab result and names the script. It was not run again for this file. Most of these runs take 3 to 60 minutes.
- **cited**: the phase text states it and names its source. The source was not re-read here.
- **formula**: a definition or a hand calculation from the phase text.

## Documents

| Phase | File | Sections | Scripts |
|---|---|---|---|
| 1 | `retrieval-internals-phase-01-measure.md` | 1.1 to 1.5 | `code/phase01_measure/` |
| 2 | `retrieval-internals-phase-02-indexes.md` | 2.1 to 2.5 | `code/phase02_indexes/` |
| 3 | `retrieval-internals-phase-03-filters-disk.md` | 3.1 to 3.6 | `code/phase03_filters/` |
| 4 | `retrieval-internals-phase-04-quantization.md` | 4.1 to 4.5 | `code/phase04_quant/` |
| 5 | `retrieval-internals-phase-05-hybrid-rerank.md` | 5.1 to 5.5 | `code/phase05_hybrid/` |
| 6 | `retrieval-internals-phase-06-queries-chunks.md` | 6.1 to 6.5 | `code/phase06_queries_chunks/` |
| 7 | `retrieval-internals-phase-07-freshness.md` | 7.1 to 7.5, and "The module question, answered" | `code/phase07_freshness/` |

Exact phase titles:

- `# Phase 1 — Measure retrieval before you tune it`
- `# Phase 2 — Inside graph and cluster indexes`
- `# Phase 3 — Filters, disk, and choosing a system`
- `# Phase 4 — Quantization and rescoring`
- `# Phase 5 — Hybrid search, fusion and reranking`
- `# Phase 6 — Queries and chunks`
- `# Phase 7 — Freshness, deletes and model upgrades`

Each document ends with the same parts: `## 🧪 Hands-on lab`, `## 🔍 Check it yourself`, a checkpoint, `## References & Further Learning` and `## Cheatsheet`. Phase 4 has E1 to E11. Every other phase has E1 to E12.

The module question, from `_curriculum/README.md`: "Your retrieval scores well on average and fails for one customer. Which stage is responsible?" Phase 7 answers it in `## The module question, answered`.

Module 3 builds on these sections and does not repeat them. Source: `course.json` `buildsOn`.

- Module 1, `inference-internals` 3.2 and 3.3: prompt caching and the break-even of a cache write. Used in 6.5.
- Module 1, 4.4: weight quantization. Phase 4 says it is a different operation from embedding quantization.
- Module 2, `context-engineering` 1.1 to 1.3: more chunks in the context is not free. Used in 1.2 and 6.2.
- Module 2, 2.4: handles, not payloads. Linked from 6.2.
- Module 2, `code/common/stats.py`: trial sizing for a share. Section 1.5 uses a different formula for paired queries.

---

## Symbols

Module 3 names every constant before it uses it. Many letters change meaning between phases. The last column says what a later module should do.

| Symbol | Meaning | Unit | Defined in | Note for later modules |
|---|---|---|---|---|
| `N` | vectors or documents in the corpus. In 6.1 only: pseudo-documents per query in HyDE | count | 1.1, 2.x, 6.1 | Two meanings. Say which |
| `d` | dimensions per vector. In 5.3 only: the reranker's input depth | count | 2.x, 4.x, 5.3 | Two meanings |
| `k` | results returned per query. In 3.4: mean layer-0 degree, 17.14. In 5.2: the RRF constant | count | 1.1, 3.4, 5.2 | Three meanings. Say which |
| `k₂` | distinct nodes within two hops, 305 | count | 3.4 | Stable |
| `R` | relevant documents per query. In 3.5: DiskANN maximum degree, 64. In 7.4: the Procrustes rotation matrix | count, count, matrix | 1.2, 3.5, 7.4 | Three meanings |
| `g_i`, DCG, IDCG | grade at rank i, discounted cumulative gain, ideal DCG from every judged grade | none | 1.2 | Stable |
| `δ`, `sd`, `n` | mean difference to detect, sd of per-query differences, labelled queries | nDCG points, count | 1.5 | `n` also means chunks per document in 6.5, updates per batch in 7.3, and Query2doc's 5 query repeats in 6.1 |
| `1.960`, `0.842`, `2.802` | z for 95% two-sided, z for 80% power, their sum | none | 1.5 | Used in `queries_needed()` |
| `M` | links per node on upper layers. Layer 0 allows 2M | count | 2.1 | Stable. Weaviate calls it `maxConnections` |
| `ef`, `efConstruction` | query candidate list on layer 0, build candidate list | count | 2.1 | Never write "the default ef". Name library and version |
| `mL`, mean level | 1/ln(M), and the true mean level 1/(M − 1) | none | 2.2 | Use 1/(M − 1) for memory |
| `nlist`, `nprobe` | IVF clusters, clusters scanned per query | count | 2.3 | pgvector calls them `lists`, `probes` |
| `m` | PQ sub-vectors in 2.3. Dimensions kept in 4.3. Elasticsearch's HNSW m in 4.4 | count | 2.3, 4.3, 4.4 | Three meanings |
| `k_factor`, oversampling factor | candidates divided by k | ratio | 2.3, 4.2 | Stable |
| `s` | filter share in Phase 3. Shared direction, the squared length of the mean document vector, in 4.5. Probe sample size in 7.2 | share, share, count | 3.1, 4.5, 7.2 | Three meanings |
| `LIMIT` | rows a filtered query asks for, 10 | count | 3.1 | Stable |
| `a`, `b` | exact cost per allowed row, 158.7 ns. Index cost per unit of LIMIT / s, 5.372 µs | ns, µs | 3.3 | `b` also means TurboQuant bits per coordinate in 4.5 |
| `W` | DiskANN beam width, 2, 4 or 8 | count | 3.5 | Stable |
| `p` | p-value everywhere. In 4.1 only: θ_1 / π | share | 1.4, 4.1 | Two meanings |
| `θ_1`, `θ_10`, gap, noise | angle to rank 1 and rank 10. gap = (θ_10 − θ_1)/π. noise = √(p(1 − p)/d) | radians, share | 4.1 | gap/noise is a heuristic, not a law |
| `c`, `ō`, `<ō, o>` | RaBitQ centroid, 1-bit code as a unit vector, their inner product, about 0.8 | vector, share | 4.5 | Stable |
| `w`, alpha | RRF list weight, convex score-fusion weight | none | 5.2 | Elasticsearch multiplies by `w`, Qdrant divides the position by it |
| df, idf | documents containing a word, Lucene inverse document frequency | count, none | 5.1 | Stable |
| `D`, `C`, `I`, `O` | document tokens, chunk tokens, instruction tokens 50, output tokens 100 | tokens | 6.5 | Stable |
| `u` | unreachable nodes | count | 7.2 | Stable |
| `A`, `B` | old and new vectors of the training documents | matrix | 7.4 | Stable |
| margin | the largest mean loss the gate accepts, 0.01 nDCG@10 | nDCG points | 7.5 | Stable |

## Terms

| Term | Meaning in Module 3 | Section |
|---|---|---|
| ANN recall@k | share of exact search's top k that an index returns. Big-ANN's k-recall@k | 1.1 |
| relevance recall@k | share of labelled relevant documents in the top k | 1.1 |
| filtered ANN recall@10 | ANN recall against exact search over the allowed rows only | Phase 3 terms |
| ceiling | the relevance score of exact search, which no index setting can pass. In 5.3: nDCG@10 of a perfect reranker over the d candidates | 1.1, 5.3 |
| qrel, labelled set | one human label, query, document and grade, and the set of them. Grade 0 means judged not relevant | Phase 1 terms |
| capped recall@k | relevant found divided by min(k, R). BEIR's R_cap. `rcap@k` in the harness | 1.2 |
| judged@k, pool, holes | share of a top k with any label. The documents labellers saw. Unjudged documents counted as not relevant | 1.3 |
| slice | a subset of queries that share a property, such as overlap or length | 1.4 |
| paired randomization test | sign-flip test on per-query differences. `common/stats.py` | 1.4 |
| Holm family | the set of tests Holm corrects together. Choose it before you look | 1.4 |
| bootstrap interval | 95% percentile interval of the mean difference, 10,000 resamples | 1.5 |
| operating point | one setting of an index's query knob, with its recall and latency | Phase 2 terms |
| Pareto frontier | the points no other point beats on both recall and time | 2.4 |
| scanned share | vectors scored per query divided by N | 2.3 |
| share | fraction of rows a filter lets through. The phase avoids "selectivity" | Phase 3 terms |
| post-filtering, pre-filtering, filtered walk | filter after the index, exact search over allowed rows, filter checked during the walk | Phase 3 terms |
| tuple | pgvector's word for an index entry whose distance it computes | Phase 3 terms |
| iterative scan, discarded heap | pgvector 0.8.0 and later resumes the walk from candidates it pushed out | 3.2 |
| crossover | the share or row count below which exact search over allowed rows is faster | 3.3 |
| gather, packed | exact search that fetches scattered vectors, or vectors stored together | 3.3 |
| record, sector | DiskANN's vector plus neighbour list on SSD, and the 4,096-byte read unit | 3.5 |
| code, calibration set | the stored compressed vector, and the vectors that set int8 ranges | Phase 4 terms |
| rescoring, candidate recall | reorder candidates with a fuller copy, and the share of the float32 top k inside the candidates | 4.2 |
| shared direction | squared length of the mean document vector. Equals the mean cosine of two random documents | 4.1, 4.5 |
| MRL | Matryoshka Representation Learning, training nested prefixes | 4.3 |
| truncation | Phase 4: cutting vector dimensions. Phase 6: the encoder ignoring input tokens past its limit | 4.3, Phase 6 terms |
| code, extras, shared tables, kept copy, graph | the five parts of a vector's bytes | 4.4 |
| majority share | share of documents whose bit equals the most common bit for a coordinate | 4.5 |
| window | results each list contributes to fusion. Elasticsearch `rank_window_size` | Phase 5 terms |
| TM2C2 | theoretical min-max normalisation before convex score fusion | 5.2 |
| cross-encoder, input depth | a model that reads query and document together, and how many candidates it reads | 5.3 |
| late interaction, MaxSim | one vector per token, and the sum over query tokens of the best document-token match | 5.4 |
| bfloat16, logit | 16-bit format with 7 fraction bits, and the raw model output before an activation | 5.5 |
| pseudo-document, PRF | text written for the query, and the lab's stand-in: the retriever's own top documents | 6.1 |
| coverage, boundaries | whether any vector sees the matching text, and where the cuts fall | 6.3 |
| late chunking, wide | pool chunk tokens encoded with context, and its control: wider plain windows | 6.3 |
| titled | the document title in front of every fixed window, the no-LLM context baseline | 6.5 |
| churn, tombstone, slot reuse | deletes and inserts after build, a delete mark, and writing a new vector into a deleted slot | Phase 7 terms |
| unreachable, `zero_in_all`, `not_reached` | no chain of links from the entry point. Xiao et al.'s zero in-degree count, and the lab's wider count | 7.1 |
| self-miss | a vector that does not find itself at ef 400. An upper bound on unreachable nodes | 7.1 |
| probe A, probe B | ANN recall at the serving ef on fixed queries, and self-search of sampled live vectors | 7.2 |
| soft delete, hard delete | hide from the API, or remove the bytes | 7.3 |
| adapter, agree@10 | a map from new-model vectors to the old space, and overlap with the new model's exact top 10 | 7.4 |
| shadow query, dual write, alias flip | log a candidate's results without showing them, write changes to both indexes, switch by pointer | 7.5 |
| non-inferiority gate | pass when the interval rules out a loss beyond the margin and no slice loses | 7.5 |

A note for Module 11. The gate in 7.5 is one paired test with a pass rule. It is not a CI gate with judges or a golden set.

---

## Phase 1 — Measure retrieval before you tune it

Phase 1 builds the shared harness and teaches which number answers which question. Every later phase measures with it.

### 1.1 — Two recalls, and which one tuning can move

**Claim.** ANN recall compares an index with exact search. Relevance recall compares results with labels. Index tuning moves only the first. The model and the chunks set the ceiling of the second. Relevance recall falls more slowly than ANN recall, because most relevant documents sit at exact rank 1.

| Key number | Source | Checked |
|---|---|---|
| bge-small, SciFact, IVF 64 clusters: ANN recall@10 0.992 to 1.000 moves relevance recall@10 only 0.8318 to 0.8362 | `two_recalls.py`, seeds 0 to 2 | lab, re-run |
| nprobe 1: ANN recall@10 0.441, relevance recall@10 0.4591. MiniLM stops at 0.7833 | `two_recalls.py` | lab, re-run |
| nprobe 8 keeps 93.9% of exact rank 1 and 83.4% of rank 10. 182 of 283 relevant documents sit at rank 1. It keeps 92.6% of relevant documents and 87.5% of the rest | `two_recalls.py --by-rank 8` | lab, re-run |
| No nprobe reaches relevance recall@10 0.95 with either model | `two_recalls.py --target 0.95` | lab, re-run |
| MiniLM reads 256 tokens and cuts 71.0% of SciFact documents. bge-small reads 512 and cuts 8.8% | `bakeoff.py --dataset scifact` prints both | lab, re-run |
| 128-token windows every 96 tokens: MiniLM relevance recall@10 0.7833 to 0.8133, p = 0.055. nDCG@10 0.6451 to 0.6740, p = 0.038, borderline, 0.035 to 0.045 over five test seeds. bge-small +0.0033, p = 0.854 | `two_recalls.py --chunks 128 96` | lab, re-run |
| nprobe 32 keeps 99.5% of the ceiling at 0.056 ms. The full scan costs 0.105 ms. Batch times | `two_recalls.py` | lab, re-run. Times read 0.061 and 0.115 ms at load 3 |

**Labs.** E5: `uv run python phase01_measure/two_recalls.py`, then `--by-rank 8`. E6 break-it: `--target 0.95`. E7: `--chunks 128 96`.

**Reusable code.** `ann_recall()` at `common/metrics.py:208`. The cached SciFact windows are `chunks-128-96-*.npy`. `chunked_ids` in `two_recalls.py` rebuilds their texts.

**Terms and symbols.** ANN recall@k, relevance recall@k, exact top k, ceiling, share of ceiling, `k`.

**Deferred.** IVF is explained in 2.3. Chunking methods are compared in 6.3.

### 1.2 — Pick the metric by what reads the results

**Claim.** Each metric answers one question. Pick the metric by what reads the results, at the depth it reads. The same two systems can swap places between metrics. A labelled query with no results must score 0.

| Key number | Source | Checked |
|---|---|---|
| SciFact, BM25 minus MiniLM: nDCG@10 +0.0412, p = 0.018. MRR@10 +0.0445, p = 0.025. recall@100 −0.0123, p = 0.496. recall@5 −0.0017, p = 0.935 | `pick_metric.py` | lab, re-run |
| NFCorpus: MiniLM beats BM25 on recall@100 by 0.0648, p < 0.001, and loses nDCG@10 by 0.0048, p = 0.68 | `pick_metric.py --dataset nfcorpus` | lab, re-run |
| NFCorpus has 38.19 relevant per query. A perfect retriever scores recall@5 0.462 | same | lab, re-run |
| Known answers: relevant at ranks 1 and 3 of 2 gives 0.9197. One of two at rank 1 gives 0.6131 | `common/metrics.py` | lab, re-run |
| IDCG from the retrieved list only, NFCorpus: BM25 0.3214 to 0.5557, bge-small 0.3438 to 0.5546. The winner flips | `baseline.py --dataset nfcorpus --idcg retrieved` | lab, re-run |
| bge-small leads BM25 on NFCorpus at p = 0.034 | `benchmark_gap.py` | lab, re-run |
| The harness matches MTEB for MiniLM on SciFact: nDCG@10 0.64508, recall@100 0.925, MRR@10 0.60472 | `baseline.py` | lab, re-run |
| Per-query values equal pytrec_eval 0.5.7 on nine runs, largest difference 3.3e-16 | Phase 1 review | cited |
| pytrec_eval and BEIR average only over queries in the run. The harness scores a labelled empty query 0, as `trec_eval -c` | trec_eval.c `-c`, BEIR `evaluation.py` | cited |

**Labs.** E1: `uv run python common/metrics.py`. E2 break-it: `common/metrics.py --self-test --mutate idcg-retrieved`. E3: `phase01_measure/baseline.py`. E4 break-it: `baseline.py --dataset nfcorpus --idcg retrieved`. E8: `phase01_measure/pick_metric.py`, then `--dataset nfcorpus`.

**Reusable code.** `ndcg_at_k()` at `common/metrics.py:117`. `_IDCG_DEFAULT` at line 62. `evaluate()` at line 174.

**Reusable method.** Six steps. List every consumer and its depth. Pick one metric per consumer. Use capped recall when R is often above k. Choose k for an LLM from the prompt budget first. Check nDCG code with three cases: perfect list 1.0, one of two at rank 1 0.6131, empty labelled query 0. Report a paired p-value per metric.

**Terms and symbols.** rank i, `g_i`, `R`, DCG, IDCG, capped recall, MRR, `trec_eval -c`.

**Deferred.** None stated. The cost of more chunks in a prompt is Module 2, 1.2.

### 1.3 — A benchmark does not predict your corpus

**Claim.** A public benchmark average does not predict your corpus. BM25 is a strong baseline. Model rankings change by dataset. A test that looks like a model's training data favours it. Labels have holes that favour the systems that built them. Build your labelled set from your own queries.

| Key number | Source | Checked |
|---|---|---|
| 14 BEIR datasets, nDCG@10 averages: BM25 0.430, MiniLM 0.423, bge-small 0.525. BM25 and MiniLM win 7 each. Gaps −0.187 to +0.234 | `benchmark_gap.py`, `published_beir.json` | lab, re-run |
| SciDocs, 1,000 queries: MiniLM beats bge-small by 0.0112, interval [+0.0025, +0.0198], p = 0.0129 | `benchmark_gap.py` | lab, re-run |
| BM25 on SciFact: 0.6863 with the English stemmer, 0.6617 without, 0.6762 at BEIR's k1 0.9 and b 0.4. BEIR prints 0.665 from Anserini with separate title and body fields | `common/HARNESS.md`, BEIR section 4 | cited |
| judged@10 on SciFact: 0.091 BM25, 0.094 bge-small. A perfect list reaches at most 0.113 | `benchmark_gap.py` | lab, re-run |
| BEIR hole study, TREC-COVID: ANCE 0.654 to 0.735, BM25 0.656 to 0.668 after labelling. Unjudged in top 10: BM25 6.4%, TAS-B 31.8% | BEIR, Table 4 | cited |
| MiniLM's card lists 52.6M S2ORC title citation pairs and 684,100 SPECTER triplets. The SciDocs win is inferred from this | model card at revision 1110a243 | cited |

**Labs.** E9: `uv run python phase01_measure/benchmark_gap.py`, and `--published-only`.

**Reusable method.** Six steps to build a labelled set. Sample real queries over two weeks or more. Stratify by slice. Pool the top 10 from several retrievers. Grade 0, 1 and 2 with written rules. Freeze a test split and tune on a development split. Watch `judged@10` for every new system.

**Terms and symbols.** pool, holes, judged@k, stemmer as a BM25 parameter.

**Deferred.** Judges, labeller agreement and CI gates go to Module 11. Stated in the text and in `course.json` `keptOut`.

### 1.4 — Averages hide the slice that fails

**Claim.** An average hides the slice that fails. Break every metric down by slice. Test a change with a paired test on the same queries. Fix the Holm family before you look.

| Key number | Source | Checked |
|---|---|---|
| SciFact BM25 minus MiniLM: +0.0412 overall, −0.0659 on the 101 low-overlap queries, Holm p = 0.049 over three overlap slices | `slices.py` | lab, re-run |
| The same slice: p 0.0445 to 0.0500 over seeds 0 to 9, 0.046 with 1,000,000 sign patterns, Holm 0.147 over all six slices. Borderline | Phase 1 review, `HARNESS.md` | cited |
| Unpaired test, bge-small minus MiniLM: p = 0.037 overall, one slice of six at Holm 0.046. Paired: p < 0.001 overall and in all six slices | `slices.py --a bge-small --b minilm`, with and without `--unpaired` | lab, re-run |
| bge-small minus BM25: p = 0.090 overall. Low-overlap +0.1195, Holm p = 0.001. 13 or more words +0.0541, Holm p = 0.037 | `slices.py --a bge-small --b bm25` | lab, re-run |
| Per-query nDCG@10 sd 0.380 and 0.384. sd of differences 0.271. 60% of differences are exactly 0 | `label_budget.py` prints 0.271 and 60% | lab, re-run for the last two |
| A Monte Carlo p-value from 10,000 sign patterns has a standard error of about 0.002 near 0.05 | `HARNESS.md` | cited |

**Labs.** E10: `uv run python phase01_measure/slices.py`, then `--a bge-small --b bm25`. E11 break-it: `--a bge-small --b minilm --unpaired`.

**Reusable code.** `paired_test()` at `common/stats.py:77`. `_flip_means()` at line 59 flips signs on sorted absolute differences, so p does not depend on query order. `compare()` at line 125. `holm()` at line 151. Scripts print p below 0.001 as `<0.001`.

**Reusable method.** Five steps. Fix slices and cut points first. Report every metric per slice with its size. Use the paired test and Holm across a named family. Block a release when a slice that matters loses significantly. Slice by what you can act on: query length is known at query time, overlap needs labels.

**Terms and symbols.** slice, overlap, length, paired randomization test, Holm, family.

**Deferred.** Phase 5, 5.2 fuses BM25 and dense on the low-overlap slice, quoted as borderline.

### 1.5 — Size the label set before you trust a result

**Claim.** The spread of per-query differences sets how many labelled queries a comparison needs. Corpus size does not. On SciFact, 300 queries see only differences of about 0.04 to 0.05 nDCG@10. Report a bootstrap interval with every p-value.

| Key number | Source | Checked |
|---|---|---|
| `n = ((1.960 + 0.842) × sd / δ)²` | Phase 1 | formula |
| bge-small minus BM25, sd 0.271, δ 0.0264: 828 queries for 80% power. 300 queries give 39% | `label_budget.py`, `common/stats.py --sd 0.271 --deltas 0.0264 0.01` | lab, re-run |
| 300 queries detect 0.0378 to 0.0499. To see 0.01 needs 4,290 to 7,459 queries | `label_budget.py` | lab, re-run |
| At 30 queries: found 8% of the time, wrong sign 28% of the time | `label_budget.py --n 30` | lab, re-run |
| The formula matches resampling within 3 points at n 30 to 600, 400 sets per seed, 3 seeds | `label_budget.py` | lab, not re-run. Only n 30 was re-run |
| BM25 minus bge-small, SciFact: 95% interval [−0.0566, +0.0039] | `benchmark_gap.py` | lab, re-run |
| Paired t p = 0.0928 against 0.0932 from 1,000,000 sign patterns | Phase 1 text | cited |

A note on the two sizing prints. `common/stats.py --sd 0.271` uses the rounded sd and prints 5,765 queries for 0.010. `label_budget.py` uses the unrounded sd and prints 5,774. Both were re-run.

**Labs.** E12 break-it: `uv run python phase01_measure/label_budget.py --n 30`, then without `--n`. Try this: `uv run python common/stats.py --sd 0.271 --deltas 0.0264 0.01`.

**Reusable code.** `queries_needed()` at `common/stats.py:141`. `detectable_diff()` at line 146. `bootstrap_ci()` at line 112.

**Terms and symbols.** `δ`, `sd`, `n`, `1.960`, `0.842`, power, bootstrap interval.

**Deferred.** "Stopping early raises the false alarm rate" is stated as a standard result and not measured. Module 11 owns eval statistics beyond this one paired test.

---

## Phase 2 — Inside graph and cluster indexes

Phase 2 opens HNSW and IVF, weighs an index byte by byte, and compares indexes the way benchmark authors do. It uses SciFact and yahoo-200k, the first 200,000 vectors of VIBE's `yahoo-minilm-384-normalized`.

### 2.1 — HNSW is a greedy walk, ef sets how wide

**Claim.** HNSW search is a greedy walk that keeps ef candidates on layer 0. ef sets recall and work per query with no rebuild. M sets links per node, so memory, build time and the whole recall curve. Tune ef at the corpus size you serve.

| Key number | Source | Checked |
|---|---|---|
| SciFact, bge-small, M 16, efConstruction 200, one build thread: ef 10 computes 235 distances, 4.5% of N, ANN recall@10 0.876. ef 320: 2,290, 44.2%, 1.000. The Python walk agrees with hnswlib on all 300 queries | `hnsw_walk.py` | lab, re-run |
| Greedy mutant, list of 1 on layer 0: top 1 found 0.480 against 0.940, 93 distances | `hnsw_walk.py --mutate greedy --ef 10` | lab, re-run |
| No stopping rule: 619 distances at ef 10, ANN recall@10 0.959 | `hnsw_walk.py --mutate no-stop --ef 10 40` | lab, re-run |
| yahoo-200k: ef 10 computes 357 distances, 0.2% of N, ANN recall@10 0.781 | `hnsw_walk.py --corpus yahoo-200k` | lab, not re-run |
| SciFact sweep: M 16 at ef 10 gives 0.8753. First ef at 0.95 is 40. Relevance recall@10 loss at ef 10 per seed: 0.0400, 0.0500, 0.0400, p ≤ 0.003. At ef 40: 0.0033, p = 1.000 | `hnsw_sweep.py` | lab, not re-run |
| yahoo-200k sweep: M 16 at ef 10 gives 0.7878. ef reaching 0.95: 40 for M 16 and M 32, 100 for M 8. M 32 costs 1.7 times the CPU of M 16 there | `hnsw_sweep.py --corpus yahoo-200k` | lab, not re-run |
| efConstruction 40 to 200 at ef 40, yahoo-200k: 0.9220 to 0.9541, 4.2 times the build time. 400 gains nothing | `hnsw_sweep.py --efc-sweep` | lab, not re-run |
| hnswlib searches layer 0 with max(ef, k) | `hnswalg.h:1309` at v0.8.0 | cited |

**Labs.** E1: `uv run python phase02_indexes/hnsw_walk.py`. E2 break-it: `--mutate greedy --ef 10`. E3 break-it: `--mutate no-stop --ef 10 40`. E4: `--corpus yahoo-200k`, 190 s. E5: `phase02_indexes/hnsw_sweep.py`, then `--corpus yahoo-200k`, about 15 minutes.

**Reusable code.** `search_layer()` at `hnsw_walk.py:139` is Algorithm 2 of the HNSW paper. `read_hnswlib()` at `hnsw_walk.py:91` parses a saved hnswlib 0.8.0 file and checks it consumed every byte. In `bench.py`: `hnswlib_build()` at line 153, `faiss_hnsw()` at 193, `faiss_ivf()` at 222, `timed_search()` at 126.

**Reusable method.** Tune ef first. Pick the smallest ef that reaches the ANN recall target. Then check relevance recall with the paired test. Set ef at least as large as the k you fetch. hnswlib, FAISS and Qdrant raise the list to k. pgvector does not. Change M only when no ef reaches the target. Check build quality as hnswlib's `ALGO_PARAMS.md` says. Search for the M nearest neighbours at ef equal to efConstruction. Recall below 0.9 means efConstruction can still help.

**Terms and symbols.** `M`, `efConstruction`, `ef`, layer, entry point, SEARCH-LAYER, lists C and W.

**Deferred.** Filtered walks go to Phase 3. Deletes go to Phase 7.

### 2.2 — The vector, not the graph, is the memory

**Claim.** At common embedding sizes the stored vector is most of an HNSW index. Lowering M saves a few percent and costs recall. Change the stored vector first.

| Key number | Source | Checked |
|---|---|---|
| Saved bytes per vector, hnswlib 0.8.0, d 384: `(4 + 8M) + 4d + 8 + 4 + (4 + 4M)/(M − 1)` | `graph_memory.py:78` | formula |
| M 16: 1,684.7 saved against 1,684.5 predicted. The vector is 91.2%. M 32: 1,812.2. M 32 to 16 saves 127.5 bytes, 7.0% | `graph_memory.py --faiss` | lab, re-run |
| Mean level is 1/(M − 1) = 0.0667 at M 16, not the paper's mL = 0.361. Seed 0 measures 0.0687 | same | lab, re-run |
| Graph bytes: the paper's formula gives 151.1, the file 140.7 | same | lab, re-run |
| FAISS 1.15.1 `IndexHNSWFlat` M 32: 1,808.1 predicted, 1,808.6 serialized | same | lab, re-run |
| Vector share at M 16: 95.4% at d 768, 96.5% at 1024, 97.6% at 1536, 98.8% at 3072 | same | lab, re-run |
| RAM adds 157 to 170 bytes per vector above the file, M 16 and 32, yahoo-200k, peak footprint from `/usr/bin/time -l` | `graph_memory.py --ram` | lab, not re-run |

**Labs.** E6: `uv run python phase02_indexes/graph_memory.py --faiss`, then `--ram --corpus yahoo-200k --M 16 32`. `--ram` works on macOS only.

**Reusable code.** `hnswlib_bytes_per_vector()` at `graph_memory.py:78`. `mean_level()` at line 73. `faiss_bytes_per_vector()` at line 89.

**Reusable method.** Size an index in five steps. Vector bytes. Graph bytes from the formula. Library overhead, 157 to 170 bytes for hnswlib 0.8.0. Replicas, kept copies and build headroom. If it does not fit, change the vector, then lower M last.

**Terms and symbols.** `mL`, mean level, link, label, layer-0 block.

**Deferred.** Memory per stored format goes to 4.4.

### 2.3 — IVF scans nprobe clusters, and PQ can collapse

**Claim.** IVF scans only nprobe clusters, and FAISS and pgvector default to one. PQ ranks by distances to centroids, so it loses true neighbours inside the scanned clusters until you re-rank with full vectors. How much it loses depends on the data.

| Key number | Source | Checked |
|---|---|---|
| FAISS 1.15.1 and pgvector 0.8.6 default nprobe and probes to 1. pgvector lists default 100 | `IndexIVF.h:105`, `ivfflat.h:55, 58` | cited |
| SciFact, nlist 64: nprobe 1 gives ANN recall@10 0.4409 and scans 1.83%. nprobe 16 gives 0.9556 and scans 26.81% | `ivf_pq.py --nprobe 1 4 16` | lab, re-run |
| nlist guidance: FAISS wiki 4√N to 16√N below 1M. pgvector rows / 1000 up to 1M, √rows above | FAISS wiki, pgvector README | cited |
| yahoo-200k, nlist 2048: nprobe 1 gives 0.4333 at 0.06% scanned. nprobe 64 gives 0.9674 at 3.15%. nlist 200: nprobe 16 reaches 0.9519 at 8.16% | `ivf_pq.py --corpus yahoo-200k --nlist 2048` and `200` | lab, not re-run |
| Distances per query at 0.95: 8,348 with 2,048 clusters, 16,520 with 200 | same | lab, not re-run |
| yahoo-200k, nprobe 128: PQ 96 bytes 0.8208 without re-ranking, 0.9846 with k_factor 10. PQ 48 bytes 0.6320 | `ivf_pq.py ... --pq` | lab, not re-run |
| SciFact PQ 96 without re-ranking loses relevance recall@10 on one seed of three: p = 0.003, 0.504, 0.177 | `ivf_pq.py` | lab, not re-run |
| Tight synthetic clusters, PQ 48: 0.1280 at every nprobe, 0.5675 with 100 re-ranked | `ivf_pq.py --corpus clustered` | lab, not re-run |
| FAISS `IndexRefine` `k_factor` defaults to 1. IVF-PQ encodes residuals. 256 centroids ask for 9,984 training points | `IndexRefine.h:15`, `IndexIVFPQ.cpp:64` | cited |

**Labs.** E7: `uv run python phase02_indexes/ivf_pq.py --corpus yahoo-200k --nlist 2048`, then `--nlist 200`. E8 break-it: `--pq`, then `P02_MUTATE=no-refine ... --self-test`. E9 break-it: `--corpus clustered --nlist 2048 --pq`.

**Reusable method.** Never ship IVF at the default nprobe. Pick nlist from N, then sweep nprobe. Keep full vectors when you use PQ. Re-rank PQ candidates, and size the depth with 4.2.

**Terms and symbols.** `nlist`, `nprobe`, scanned share, PQ, `m`, `k_factor`, residual.

**Deferred.** Full vectors on disk: 3.5. Oversampling factor: 4.2. Retraining centroids on drift: 7.2 item 7, inferred and not measured.

### 2.4 — Compare indexes at equal recall

**Claim.** An index is a curve, not a point. Compare indexes by time at the same ANN recall. Use one machine and thread count, time the indexes in alternation, and put exact search on the chart.

| Key number | Source | Checked |
|---|---|---|
| yahoo-200k at ANN recall@10 0.95, one query per call, one thread, load near 5: FAISS HNSW16 0.1277 ms, FAISS HNSW32 0.1286, IVF-Flat 0.1671, IVF-PQ96 with re-ranking 0.1857, hnswlib M16 0.1978, exact 4.3106 | `compare_curves.py --corpus yahoo-200k` | lab, not re-run. 22 minutes |
| hnswlib is 1.5 times slower than FAISS with the same M 16 and efConstruction 200 on 200,000 vectors, 3.5 times on 5,183 | same | lab, not re-run |
| At default knobs, IVF-Flat is the fastest point at 0.0477 ms with ANN recall@10 0.4333 | `compare_curves.py --points` | lab, not re-run |
| Pure scan per distance: hnswlib 132 ns, FAISS 21.5 ns. hnswlib 0.8.0 has SIMD distance code for x86 only | `hnswlib.h` lines 11 to 20, Phase 2 review | cited |
| Batch against single query, exact search on yahoo-200k: 0.11 ms against 4.2 ms per query | Phase 2 text | lab, not re-run |
| VIBE, yahoo-minilm-384 at ANN recall@100 0.95, one core: ngt-qg 4,932 QPS, Glass 4,715, hnswlib 1,710 | `vibe_results.py` | lab, not re-run. The table is live |
| Big-ANN NeurIPS'23 ranks by the highest batch throughput at 0.9 10-recall@10 or more, all threads, Azure D8lds_v5. VIBE runs one core, k = 100, fastest of 5 runs | Big-ANN section 3.1, VIBE section 5.1 | cited |

**Labs.** E11 break-it: `uv run python phase02_indexes/compare_curves.py --corpus yahoo-200k --points`. E12: `uv run --with pyarrow==25.0.1 python phase02_indexes/vibe_results.py`.

**Reusable code.** `at_recall()` at `bench.py:261` reads time at a target recall from the frontier and never extrapolates. `pareto()` at line 250. `compare_curves.py` times indexes in alternation. `P02_MUTATE=sequential` and `no-frontier` fail its self-test.

**Reusable method.** Four fairness rules. Same work, machine and thread count. Time indexes in alternation. Read from the frontier and do not extrapolate. Put exact search on the chart. Also ask for build time and memory, and name the load.

**Terms and symbols.** operating point, Pareto frontier, QPS, batch time, one query per call.

**Deferred.** None stated. ANN-Benchmarks is unmaintained. Use VIBE and Big-ANN.

### 2.5 — "HNSW" at defaults is not one operating point

**Claim.** "HNSW" names an algorithm, not an operating point. At k = 10 the default search list runs from 10 to 100 across eight systems, and recall follows it. Implementations also keep different link counts from the same settings.

| Key number | Source | Checked |
|---|---|---|
| Search list at k = 10: hnswlib 0.8.0 10, Vespa 8.753.16 10, Elasticsearch 9.5.4 15, FAISS 1.15.1 16, pgvector 0.8.6 40, Qdrant 1.19.1 100, OpenSearch 3.8.0.0 100, Weaviate 1.39.6 100 | `default_drift.py --table`, source file and line per row | lab, re-run |
| Rules: Weaviate clamp(8k, 100, 500), at least k. Elasticsearch round(min(10,000, 1.5k)) with Java rounding, so k = 7 gives 11. pgvector never raises the list to k | same | formula |
| yahoo-200k at defaults: ANN recall@10 0.7896 with hnswlib settings to 0.9948 with Weaviate settings. FAISS's own index at its defaults 0.9101, hnswlib with the same settings 0.8441 | `default_drift.py --corpus yahoo-200k` | lab, not re-run |
| Layer-0 links per node at M 32 and efConstruction 40: FAISS 43.1, hnswlib 20.1. The recall gap cause is inferred | Phase 2 review | lab, not re-run |
| SciFact: hnswlib defaults lose 0.04 to 0.05 relevance recall@10 on each seed, p ≤ 0.003. Weaviate defaults lose nothing | `default_drift.py` | lab, not re-run |
| Weaviate switches to flat search below 40,000 allowed vectors. Qdrant below `full_scan_threshold` 10,000 KB | `config.go:34`, Qdrant `config.yaml` | cited |

**Labs.** E10 break-it: `uv run python phase02_indexes/default_drift.py --table`, then `--corpus yahoo-200k`, about 11 minutes. `P02_MUTATE=no-max-k` fails its self-test.

**Reusable code.** The defaults table as data at `default_drift.py:90` onward.

**Reusable method.** Never write "HNSW, defaults". Write library, version, M, efConstruction, search list and k. Read defaults in source at your version. Recompute the list when k changes. Re-read defaults after every upgrade.

**Deferred.** Elasticsearch's quantized default index types go to 3.6. Filters go to Phase 3.

---

## Phase 3 — Filters, disk, and choosing a system

Phase 3 runs on BEIR SciDocs with bge-small and one hnswlib 0.8.0 graph with pgvector's M 16 and efConstruction 64, seed 100. Most pgvector numbers come from a Python emulation of pgvector 0.8.6's scan. E12 checks them on real pgvector 0.8.1.

### 3.1 — Post-filtering keeps ef × s rows, not LIMIT

**Claim.** A filter applied after the index keeps about ef × s rows. LIMIT is not in the formula. A filter that works against the query keeps none.

| Key number | Source | Checked |
|---|---|---|
| ef 40, 10% random filter: 3.95 rows, 0.7% of queries full. Prediction 4.00 and 0.5%, hypergeometric | `post_filter.py` | lab, re-run |
| 20% filter: 7.65 rows, 25.4% full against 26.8% predicted | same | lab, re-run |
| Tenant filter at 1%: 2.14 rows. Relevance recall@10 0.358 post-filtered against 0.699 exact filtered, p = 0.0001. At 0.1%: 0.358 against 0.943 | `post_filter.py --filter tenant` | lab, re-run |
| Far filter: 0.00 rows at every share from 50% to 0.1% | `post_filter.py --filter far` | lab, re-run |
| ef 400 gives full answers down to 5%. 2% gives 7.69 rows, 1% gives 3.99 | `post_filter.py --ef 400` | lab, not re-run |
| pgvector README at 0.8.6: "filtering is applied *after* the index is scanned" | README | cited |

**Labs.** E2: `uv run python phase03_filters/post_filter.py`, then `--ef 400`. E3 break-it: `--filter far`. E4: `--filter tenant`.

**Reusable code.** `post_filter()` at `post_filter.py:76`. In `filters.py`: `make_masks()` at line 54 builds random, tenant and far filters. `exact_filtered()` at line 84. `filtered_ann_recall()` at line 96.

**Reusable method.** Find every filtered vector query and where its filter runs. Count each common filter's share and compute ef × s. Alert on rows returned divided by LIMIT, per customer, at low percentiles. Treat tenant filters as the worst case.

**Caution.** The tenant filter adds each query's relevant documents to the allowed set. So exact filtered search looks better than it would for a real tenant. The text says the row count is the robust signal.

**Terms and symbols.** `s`, `LIMIT`, post-filtering, pre-filtering, filtered walk, tuple, filtered ANN recall@10.

**Deferred.** Tenant isolation as a boundary goes to Module 4 per `course.json` and to Module 16 per `_curriculum/README.md` line 150. Section 3.1 treats a tenant filter only as a recall problem.

### 3.2 — Iterative scans fill the LIMIT, at a price

**Claim.** An iterative scan fills the LIMIT by walking further. The walk grows roughly as LIMIT / s. A capped walk returns wrong rows before it returns short ones.

| Key number | Source | Checked |
|---|---|---|
| Tuples per query, LIMIT 10: 481 with iterative scans off. `relaxed_order` 1,131 at 10%, 5,270 at 1%, 19,356 at 0.1%. Filtered ANN recall@10 0.967, 0.990, 0.994 | `iterative_scan.py`, emulation of pgvector 0.8.6 | lab, re-run |
| `hnsw.ef_search` 1000 at 1%: 8.88 rows, 56.3% full, 5,295 tuples. At 0.1%: 0.81 rows | same | lab, re-run |
| `strict_order` drops 39 rows per query at 1% and 177 at 0.1%. Filtered ANN recall@10 0.948 against 0.990 at 1% | same | lab, re-run |
| Tenant filter at 0.1%: relaxed minus strict +0.0128 relevance recall@10, largest p 0.025. Not significant at 1% and 10% | `iterative_scan.py --filter tenant` | lab, not re-run |
| Cap of 2,000 tuples: at 1%, 10.00 rows, 99.8% full, filtered ANN recall@10 0.822. At 0.1%, 1.92 rows | `iterative_scan.py --max-scan-tuples 2000` | lab, not re-run |
| Default cap 20,000: 339 of 600 scans at 0.1% hit it and still scored 0.989 | Phase 3 review | cited |
| Real pgvector 0.8.1 on PostgreSQL 14.24: off 4.00, 0.41, 0.06 rows. `relaxed_order` 0.985, 0.996, 1.000. Cap 2,000 at 1%: 0.863. Postgres's own graph scored 0.001 to 0.078 higher in every row | `pgvector_iterative.sql`, `pgvector_iterative_RESULTS.txt` | lab, not re-run |
| Tuples per needed candidate: 5.3 at 1%, 1.9 at 0.1% | Phase 3 | formula |

**Labs.** E5: `uv run python phase03_filters/iterative_scan.py`, about 1 minute. E6 break-it: `--max-scan-tuples 2000`. E7: `--filter tenant`. E12: `filters.py --export-csv /tmp/p03`, then the four steps in the header of `pgvector_iterative.sql`. It runs a throwaway cluster on port 55439, 64 s.

**Reusable code.** In `phase03_filters/hnsw_graph.py`: `PgScan` at line 223 re-implements `HnswSearchLayer`, `ResumeScanItems` and `hnswgettuple` at v0.8.6. `pg_query()` at line 354. `build_index()` at line 77 and `cached_index()` at line 369. Constants `PG_EF_SEARCH = 40` and `PG_MAX_SCAN_TUPLES = 20_000`.

**Reusable method.** Set `hnsw.iterative_scan = relaxed_order` on pgvector 0.8.0 or later. Size `hnsw.max_scan_tuples` from the smallest share, several times LIMIT / s. Raise `hnsw.scan_mem_multiplier` if the cap does not help. Measure filtered ANN recall, not only rows.

**Warnings.** pgvector 0.6.0 to 0.8.1 have CVE-2026-3172, fixed in 0.8.2. Use 0.8.1 only in a throwaway cluster, and 0.8.4 or later in a real database. The emulation does not model the `work_mem × hnsw.scan_mem_multiplier` cap.

**Terms and symbols.** iterative scan, `strict_order`, `relaxed_order`, discarded heap, `hnsw.max_scan_tuples`.

**Deferred.** None stated.

### 3.3 — For rare filters, exact search wins

**Claim.** Below a crossover, exact search over the allowed rows is faster than the index and exact. The crossover in allowed rows grows as √N, so the crossover share shrinks as the table grows. Route by allowed rows, not by share.

| Key number | Source | Checked |
|---|---|---|
| 1% share, 257 rows: index with widening 6,460 µs, exact 34.7 µs, about 190 times. Four runs gave 186 to 272 times | `exact_crossover.py`, run D | lab, not re-run |
| Gather crossover 11.7%, 3,013 rows. 11.7% to 12.5% over four runs at loads 5 to 256. Packed 41.7% to 43.1% | same | lab, not re-run |
| Model `s* = √(b × LIMIT / (a × N))`, a = 158.7 ns, b = 5.372 µs: 11.5% at 25,657 rows, 1.84% and 18,400 rows at 1M, 0.58% and 58,200 rows at 10M. A model, not a measurement | same | formula |
| Quick version at load 3.7: model lines 11.53%, 1.85%, 0.58%. Fitted a = 101.7 ns, b = 3.467 µs. Measured gather crossover 15.3%, where the text's quick run gave 11.2% | `exact_crossover.py --queries 50 --seeds 0 --repeats 2` | lab, re-run. The measured crossover differs |
| pgvector 0.8.1 planner chose a B-tree and an exact sort at 1% and 0.1%, and HNSW at 10% | E12 | lab, not re-run |
| Qdrant `full_scan_threshold` 10,000 KB is 6,667 vectors of 384 float32. Weaviate `flatSearchCutoff` 40,000 objects | Qdrant `types.rs`, Weaviate `config.go` | cited |

**Labs.** E8: `uv run python phase03_filters/exact_crossover.py`, 5 to 10 minutes, or the quick version above.

**Reusable code.** `index_widen()` at `exact_crossover.py:75`. `exact_crossover_rows()` at `choose_system.py:102`, with `EXACT_US_PER_ROW` and `INDEX_US_PER_CAND` at lines 58 and 59. Re-fit with `exact_crossover.py --corpus-sizes <N>`.

**Reusable method.** Count the rows a filter allows. Below the crossover, run exact search over them. Store small tenants together with partitions, partial indexes or namespaces. Re-fit the crossover on your hardware.

**Terms and symbols.** `a`, `b`, crossover, gather, packed.

**Deferred.** None stated.

### 3.4 — Filter-aware walks, and where the graph breaks

**Claim.** A walk that steps only on allowed nodes breaks apart near a share of 1 / degree. A second hop moves that point down by about the degree again.

| Key number | Source | Checked |
|---|---|---|
| Mean layer-0 degree, both directions, 17.14. 1/k = 5.8%. Within two hops 305. 1/k₂ = 0.33% | `filter_walk.py` | lab, re-run |
| One-hop filtered ANN recall@10: 0.644 at 20%, 0.263 at 10%, 0.070 at 5%. Two-hop: 0.963 at 5%, 0.664 at 1%, 0.236 at 0.5% | same | lab, re-run |
| Largest connected piece, one hop: 65.1% at 10%, 3.8% at 5% | same | lab, re-run |
| The sweep scores 1.000 at every share but computes 25,657 distances at 0.1%. Exact search computes 26 | same | lab, re-run |
| At 50%, two-hop 0.878 falls below one-hop 0.912 | same | lab, re-run |
| Weaviate `acorn` default from 1.34. Qdrant 1.19.1 ACORN option off by default, `max_selectivity` 0.4. `HNSW_DEFAULT_FILTER_STRATEGY=sweeping` changes Weaviate's default | docs, `config.go:123` | cited |
| ACORN: 2 to 1,000 times higher throughput at fixed recall. PACMMOD 2(3), 2024, the SIGMOD 2024 journal | arXiv 2403.04871, Crossref | cited |

**Labs.** E9: `uv run python phase03_filters/filter_walk.py`, about 1 minute. E10 break-it: `filter_walk.py --self-test --mutate no-second-hop`, then `hnsw_graph.py --self-test --mutate no-discarded`.

**Reusable code.** The two-hop rule at `filter_walk.py:86`.

**Reusable method.** Compute 1 / degree for your graph. Below it, use a second hop, filter edges or exact search. On Qdrant, create payload indexes before loading data. Test with a filter that works against the query. Count distances, not only recall.

**Terms and symbols.** `k` as mean degree, `k₂`, percolation, one hop, two hop, sweep.

**Deferred.** None stated.

### 3.5 — Disk and object storage trade latency for memory

**Claim.** A disk index keeps short codes in RAM and full vectors on SSD or object storage. Memory drops by two orders of magnitude. Latency becomes round trips times the cost of one trip. Plan from the p99, not the warm p50.

| Key number | Source | Checked |
|---|---|---|
| 10M vectors of 1024 float32: RAM graph 42.4 GB. SSD graph 0.3 GB of RAM and 81.9 GB of SSD. Object store 41.0 GB | `budget.py` | lab, re-run |
| Record `d × bytes + 4 + R × 4` = 4,356 bytes, 2 sectors. With 2-byte values: 2,308 bytes, 1 sector, 41.0 GB | `budget.py --bytes-per-dim 2` | lab, re-run |
| Model latency: SSD 5 round trips × 0.2 ms = 1 ms. Cold object store 4 × 100 ms = 400 ms | Phase 3 | formula |
| DiskANN on SIFT1B: under 3 ms mean, 95% or more 1-recall@1, over 5,000 QPS, 64 GB RAM, 16 cores | DiskANN, NeurIPS 2019 | cited |
| turbopuffer, 10M × 1024: warm p50 14 ms, p99 27 ms. Cold p50 874 ms, p99 1,686 ms. Vendor numbers, hardware not stated. Its two pages disagree on 1M or 10M documents | turbopuffer home and architecture pages | cited |
| FreshDiskANN: 1,800 inserts and 1,800 deletes per second with 1,000 searches per second at 95% 5-recall@5 | arXiv 2105.09613 | cited |
| SPFresh: P99.9 near 4 ms against more than 20 ms for DiskANN during rebuilds, 2.41 times lower on average | SOSP 2023, arXiv 2410.14452 | cited |

**Labs.** E11: `uv run python phase03_filters/budget.py`, then `--bytes-per-dim 2`.

**Reusable code.** `diskann_record()` at `budget.py:82`. `plan()` at line 93. The record rule comes from DiskANN's code at tag 0.7.0, `src/disk_utils.cpp` lines 923 to 939.

**Terms and symbols.** record, sector, round trip, `R` as maximum degree, `W`.

**Deferred.** Churn in graphs goes to Phase 7.

### 3.6 — Choose a system by workload, at a version

**Claim.** Choose the layout from four numbers: RAM needed, the smallest filter share, the update rate and the cold share. Then read the defaults at the exact version. The version that created an Elasticsearch index picks its default type.

| Key number | Source | Checked |
|---|---|---|
| Elasticsearch float `dense_vector` with no `index_options`: 9.0 `int8_hnsw`. 9.1 `bbq_hnsw` at 384 dims or more, else `int8_hnsw`. 9.4 `bbq_disk` with an Enterprise licence, else the 9.1 rule. byte and bit vectors: `hnsw` | `choose_system.py --es 9.4.7 --dims 768`, `--no-license`, `--es 9.0.8`. `DenseVectorFieldMapper.java` lines 417 to 458 at v9.4.7 | lab, re-run |
| Elasticsearch keeps raw floats on disk: about 25% more for int8, 12.5% for int4, 3.1% for BBQ | Elasticsearch 9.x docs | cited |
| Agent-memory scenario: 20,000 allowed rows is below the model crossover of 367,928, so exact search | `choose_system.py --scenarios` | lab, re-run |
| Versions on 2026-09-23: pgvector 0.8.6, pgvectorscale 0.9.1, Qdrant 1.19.1, Weaviate 1.39.6, Elasticsearch 9.5.4 and 9.4.7, LanceDB 0.39.0, turbopuffer client 2.10.1, Milvus 3.0.2, FAISS 1.15.1, hnswlib 0.8.0 on PyPI and 0.9.0 on GitHub | git tags, PyPI JSON | cited |
| Milvus is not in the decision table, because its index documentation did not load | Phase 3 | cited |

**Labs.** E11: `uv run python phase03_filters/choose_system.py --scenarios`. `--check-versions` needs the network.

**Reusable code.** `es_default()` at `choose_system.py:67`. `decide()` at line 126. `systems.json` holds the pins.

**Reusable method.** Run `choose_system.py` with your N, dims, RAM, filter share, updates per day and p99. Pin versions and write down each inherited default. Set `index_options.type` explicitly in Elasticsearch 9.x. Diff release notes for default, filter and quantization before an upgrade. Re-fit the 3.3 crossover.

**Terms and symbols.** the four numbers, index creation version, licence.

**Deferred.** Rebuild budgets for more than about 1% change per day go to Phase 7.

---

## Phase 4 — Quantization and rescoring

Phase 4 uses five models: MiniLM, bge-small, nomic-embed-text-v1.5, mxbai-embed-xsmall-v1 and all-mpnet-base-v2. mpnet is the control without MRL. Data: SciFact, NFCorpus and SciDocs.

### 4.1 — The model decides how much quantization costs

**Claim.** At 1 bit the model decides the loss. Sign bits estimate angles with noise set by d. The model sets how close the top-10 angles are. gap/noise, a label-free heuristic, ranked held-out models by binary loss. Decoded int8 is near lossless.

| Key number | Source | Checked |
|---|---|---|
| Binary kept: bge-small 87.8% on SciFact, 79.7% on SciDocs. MiniLM 91.2% and 85.8%. 79.7% to 93.6% over 15 runs | `quant_table.py` | lab, re-run for SciFact. The rest not re-run |
| Decoded int8 kept 99.6% to 100.2% in all 15 runs. SciFact: 100.1% MiniLM, 100.0% bge-small | same | lab, re-run for SciFact |
| gap/noise on SciFact: bge-small 2.15, MiniLM 3.01. Shared direction 0.628 and 0.131 | same | lab, re-run |
| Raw sign bits against θ/π at rank 1: bge-small 0.2536 against 0.2056. MiniLM 0.2857 against 0.2850 | same | lab, re-run |
| Spearman with binary kept, gap/noise: fitted 10 runs +0.93, held-out 5 runs +0.90, all 15 +0.92. Shared direction: −0.27, −0.70, −0.35 | `quant_table.py` over all datasets | lab, not re-run |
| Raw int8 dot product: bge-small 0.6575, 92.3% | `quant_table.py --int8-raw` | lab, not re-run |
| int8 ranges from 100 documents kept 99.5% to 100.5%, none significant | `--int8-calib` | lab, not re-run |
| PQ 48 bytes kept 92.4% for bge-small on SciFact, binary 87.8% in the same bytes | `quant_table.py` | lab, re-run |
| HF blog: mxbai-embed-large-v1 binary 92.53% without rescoring. Its int8 rows 90.79% to 97% "directly used the dot-product". The link to raw-code scoring is inferred | HF embedding-quantization blog | cited |

**Labs.** E1: `uv run python phase04_quant/quant_table.py --datasets scifact --models minilm bge-small`. E2 break-it: add `--int8-raw`. E3: `quant_table.py` over all runs, 107 to 180 s.

**Reusable code.** In `codes.py`: `int8_fit()` at line 80, `int8_decode()` at 95, `int8_raw_scores()` at 102 is the wrong way, `sign_pm1()`, `pack_bits()`, `hamming()`. In `quant_table.py`: `angle_stats()` at line 103 and `shared_direction()` at 97 need no labels.

**Reusable method.** Compute gap/noise on 200 queries before choosing a code. Rank candidate models by it, then measure. Use decoded int8 as the safe default. Use binary only with rescoring. Never score int8 codes with a raw dot product.

**Terms and symbols.** code, int8, calibration set, binary, Hamming, kept, `θ_1`, `θ_10`, gap, noise, `p` as θ_1/π, shared direction.

**Deferred.** Weight quantization stays in Module 1, 4.4.

### 4.2 — Oversample, then rescore

**Claim.** Codes pick the candidates and fuller vectors order them. float32 rescoring returns exactly the float32 top k found among the candidates. So the factor you need follows the model's candidate recall. int8 rescoring equals float32.

| Key number | Source | Checked |
|---|---|---|
| bge-small on SciFact, k = 10: binary 0.6258. Factor 1 rescored 0.6669. Factor 20 gives 0.7056, p = 0.075, the smallest factor at 99% without a significant loss. Factor 10 gives p = 0.046, borderline | `rescore.py` | lab, re-run |
| MiniLM: factor 5 gives 0.6400, p = 0.245 | same | lab, re-run |
| Labelled rule by model: mpnet 2, MiniLM 5, nomic 5, mxbai-xs 10, bge-small 20. Candidate recall 0.94 rule: 5, 10, 20, 10, 20 | `rescore.py --models nomic mxbai-xs mpnet` | lab, re-run for MiniLM and bge-small |
| float32 rescoring ANN recall@10 equals candidate recall at every factor. An identity, printed as a code check | `rescore.py` | lab, re-run |
| int8 rescoring within 0.0013 nDCG@10 of float32 | same | lab, re-run |
| Float query against binary codes plateaus at 0.6593, 92.5% of float32 | same | lab, re-run |
| At k = 100, factor 1 cannot raise recall@100: bge-small stays at 94.5%. Factor 4 gives 0.9293, 98.7%, p = 0.206 | `quant_table.py` | lab, re-run |
| Batch times, bge-small: binary search 0.025 ms, rescoring 100 candidates 0.046 ms, float32 exact 0.414 ms | `rescore.py` | lab, re-run. Times read 0.011, 0.017 and 0.105 ms at load 4 |
| Qdrant `oversampling` 2.4 with limit 100 pre-selects 240. Elasticsearch `rescore_vector.oversample` above 1.0 and below 10.0, 3.0 by default for `bbq_disk`. The HF blog's multiplier counts from top_k 100 | docs | cited |

**Labs.** E4: `uv run python phase04_quant/rescore.py`, then `--models nomic mxbai-xs mpnet`. E5 break-it: `rescore.py --break-it`.

**Reusable code.** `rescore()` at `codes.py:145`. `candidate_recall()` at `codes.py:161`.

**Reusable method.** Measure candidate recall on 200 queries at factors 1, 2, 5, 10 and 20. Pick the smallest factor at your target. Confirm with labels. Rescore with int8 if the copy must live in RAM. Time stage 2 if the copy is on disk. Re-run after a model change.

**Terms and symbols.** oversampling factor, candidates, candidate recall, stage 1, stage 2.

**Deferred.** None stated.

### 4.3 — Truncation loss follows the dimensions you keep

**Claim.** In these runs, truncation loss followed the dimensions left, not the MRL claim. Re-normalise after truncation. At equal bytes, int8 beat truncation.

| Key number | Source | Checked |
|---|---|---|
| 384 dimensions left: nomic, MRL, 99.1%, 96.4%, 94.0%. mpnet, no MRL, 96.2%, 97.6%, 97.5% | `truncate.py` | lab, not re-run |
| By dimensions left: 384 keep about 94% to 99%, 192 keep 87% to 96%, 96 keep 75% to 87% | same | lab, not re-run |
| mxbai-xs card, 96.2% at a 33% cut: it kept 96.7% to 98.2%. MiniLM without MRL kept 95.5% to 98.4% | same | lab, not re-run |
| No re-normalising, SciFact: bge-small at 96 dims 0.4847, 68.0%. nomic at 192 dims 0.6191, 88.1% | `truncate.py --no-renorm --datasets scifact --models bge-small nomic` | lab, re-run |
| With re-normalising: 0.5805, 81.5%, and 0.6621, 94.2% | `truncate.py` | lab, not re-run |
| Equal bytes: nomic int8 at 768 bytes 100.0% against 192 float32 dims 94.2%. bge-small int8 at 384 bytes 100.0% against 96 dims 81.5% | Phase 4 | lab, not re-run |
| MRL's "up to 14×" results are ImageNet results, not text retrieval | MRL paper | cited |

**Caution for later modules.** The summary lines of `truncate.py` compare models by share of d, not by dimensions left. The re-run above, with only bge-small and nomic, printed "above every model without MRL" for nomic. That is the confounded comparison the section corrects. Verified in the re-run output.

**Labs.** E6: `uv run python phase04_quant/truncate.py`. E7 break-it: `--no-renorm --datasets scifact --models bge-small nomic`.

**Reusable code.** `truncate()` at `codes.py:169`, with re-normalising and nomic's optional layer-norm step.

**Terms and symbols.** MRL, `m` as dimensions kept, variance up front, re-normalise.

**Deferred.** MRL at deeper cuts, such as 64 of 768, was not checked.

### 4.4 — Memory per vector, with everything counted

**Claim.** A vector costs its code, extras, shared tables, kept copy and graph. Quantization shrinks the first and often adds the fourth.

| Key number | Source | Checked |
|---|---|---|
| Elasticsearch 9.2+ `bbq_hnsw`, d 1024: 206 bytes of RAM, 128 code plus 14 extras plus 64 graph. 4,302 bytes of disk. 20.2 times less RAM, 3.4% more disk than plain `hnsw` | `memory.py --d 1024 --n 10000000 --graph-bytes 64` | lab, re-run |
| Elasticsearch 9.2+ `int8_hnsw`: 1,092 bytes of RAM, 5,188 of disk | same | lab, re-run |
| Code sizes: float32 4d, float16 2d, int8 d, int4 d/2, binary d/8, PQ m, RaBitQ 1 bit d/8 + 8. RaBitQ 4 bits 212 bytes at d 384, where the header comment implies 208 | `memory.py`, FAISS `RaBitQuantizer.cpp` | lab, re-run |
| SciFact, N = 5,183: PQ codebooks 393,216 bytes, rotation 591,360 bytes. RR + RaBitQ 1 bit 170.1 bytes per vector, predicted and measured | `memory.py --measure scifact --model minilm` | lab, re-run |
| Qdrant 1.19 default tier caches the originals. Only `turbo4` originals shrink disk | `memory.py`, Qdrant docs | lab, re-run. Qdrant behaviour cited |
| Elasticsearch before 9.2 also keeps each vector in `_source` | Elastic blog, docs | cited |
| Elasticsearch's "3.87GB" is 3.87 GiB, 4.16 GB | Phase 4 | formula |

**Labs.** E8: `uv run python phase04_quant/memory.py --d 1024 --n 10000000 --graph-bytes 64`. E9: `memory.py --measure scifact --model minilm`.

**Reusable code.** `code_bytes()` at `memory.py:74`. `shared_bytes()` at line 98. `layouts()` at line 109. Take `--graph-bytes` from 2.2.

**Reusable method.** Write the five parts for each layout. Split them into RAM and disk. Check which copy your system keeps at your version. Verify one layout on a real index with the system's disk-usage tool.

**Terms and symbols.** code, extras, shared tables, kept copy, graph, GiB against GB.

**Deferred.** None stated. The Elasticsearch default by version is owned by 3.6.

### 4.5 — Rotation codes need centering to pay off

**Claim.** A random rotation lets one quantizer fit every coordinate, but it keeps any shared direction. Centering removes it. For bge-small, rotation alone lowered nDCG@10 on three datasets, significantly on two.

| Key number | Source | Checked |
|---|---|---|
| bge-small, SciFact, float query: binary 0.6593. Plus rotation 0.6390, p = 0.084. Plus centering 0.6736. Lab RaBitQLite 0.6796. FAISS `IndexRaBitQ` 0.6754 | `rotate.py --part ablation` | lab, not re-run. FAISS RaBitQ 0.6754 re-run in `quant_table.py` |
| Rotation effect: NFCorpus −0.0251, p < 0.001. SciDocs −0.0086, p = 0.003. Centering plus correction: +0.0233 p = 0.047 borderline, +0.0047 p = 0.461, +0.0087 p = 0.005 | same, three datasets | lab, not re-run |
| Majority share `1/2 + arctan(√(s/(1 − s)))/π`. bge-small predicted 0.791, measured 0.787 | `rotate.py --part stats` | lab, not re-run |
| 4-bit TurboQuant_mse against int8: MiniLM +0.0024, p = 0.353. bge-small −0.0077, p = 0.023. Centered, not in the paper: 0.7118 | `rotate.py --part turbo` | lab, re-run |
| `--drop-center-term`: RaBitQ row falls to 0.6100 | `rotate.py --part ablation --drop-center-term` | lab, not re-run |
| `<ō, o>` is about √(2/π) = 0.798. TurboQuant MSE for b = 1 to 4: 0.36, 0.117, 0.03, 0.009 | papers, self-test | formula |

**Labs.** E10 break-it: `uv run python phase04_quant/rotate.py --part ablation --datasets scifact nfcorpus scidocs`, then `--drop-center-term`. E11: `rotate.py --part turbo`.

**Reusable code.** In `codes.py`: `random_rotation()` at line 183, `RaBitQLite` at 190, `lloyd_max_centroids()` at 231, `TurboQuantMSE` at 255. `RaBitQLite` keeps the query in float32 and uses one global center. It is not the paper's full method.

**Reusable method.** Compute s and gap/noise. If s is large, prefer a code that centers. Never add a rotation to a plain sign code by hand. Test 4-bit TurboQuant against int8 on your labels. Keep rescoring on for 1-bit and 2-bit codes.

**Terms and symbols.** `c`, `ō`, `<ō, o>`, `s` as shared direction, majority share, `b` as bits.

**Deferred.** Qdrant's own TurboQuant code, which may center, was not tested.

---

## Phase 5 — Hybrid search, fusion and reranking

Phase 5 uses BM25 from bm25s 0.3.11, MiniLM and bge-small on SciFact, NFCorpus and SciDocs. The cross-encoder is `cross-encoder/ettin-reranker-32m-v1` at revision `b33e5ceb5110`.

### 5.1 — Lexical and dense fail on different queries

**Claim.** BM25 wins when the query and the answer share a rare word. A dense model wins when they share only common words. So each finds relevant documents the other misses. Identifiers need an exact keyword field.

| Key number | Source | Checked |
|---|---|---|
| SciFact, BM25 against bge-small, by the rarest stemmed word shared with the answer: df ≤ 5, 100 queries, BM25 +0.0730, Holm p = 0.004. df 6 to 100, 160 queries, bge-small +0.0597, Holm p = 0.006. df > 100, 40 queries, bge-small +0.1419, Holm p = 0.001 | `wins_losses.py` | lab, re-run |
| Against MiniLM: +0.1275 and −0.1465, both Holm p = 0.001 | same | lab, re-run |
| 339 relevant documents: BM25 top 100 only 10, bge-small only 20, both 301, neither 8. Union 0.9764 | same | lab, re-run |
| idf = ln(1 + (N − df + 0.5)/(df + 0.5)): df 1 gives 8.15, df 500 gives 2.34 on SciFact | Phase 5 | formula |
| Identifier probe, 300 single-document tokens × 3 seeds: BM25 token only hit@10 1.000. bge-small 0.307, MiniLM 0.254. BM25 in a sentence 0.738 | `wins_losses.py --probe` | lab, not re-run |
| NFCorpus, MiniLM: common-only −0.0634. BM25 rare +0.0859, Holm p = 0.010. Against bge-small the rare lead is +0.0404, Holm p = 0.301 | `--dataset nfcorpus` | lab, not re-run |
| SPLADE v2: more than 9% higher nDCG@10 than SPLADE on TREC DL 2019 | arXiv 2109.10086 | cited |

**Labs.** E1: `uv run python phase05_hybrid/wins_losses.py`, and `--self-test --mutate raw-tokens`. E2: `--dataset nfcorpus`, `--dataset scidocs`. E3 break-it: `--probe`, then `--probe-why 230c sin3a tcid50`.

**Reusable code.** `rarest_shared_df()` at `wins_losses.py:83`. It must use BM25's own tokenizer, stop list and stemmer.

**Reusable method.** Count per-query wins and losses. Slice losses by the rarest shared df. Count relevant documents found by only one retriever. Route identifiers to an exact keyword field.

**Terms and symbols.** df, idf, dense retriever, bi-encoder, learned sparse retrieval.

**Deferred.** None stated.

### 5.2 — RRF: k decides how much the top ranks count

**Claim.** RRF adds w / (k + rank) over lists, with ranks from 1. k sets how much the top ranks count. Between two retrievers, the gap in their quality decides more than k. Fusion helps when they are close and can hurt when one is weak. Score fusion needs normalisation, and normalisation fixes the scale, not the spread.

| Key number | Source | Checked |
|---|---|---|
| Rank-1 vote over rank-10 vote: 5.50 at k = 1, 1.15 at k = 60 | `fusion.py --weights` | lab, re-run |
| RRF k = 60 minus the better single list, nDCG@10: SciFact bge-small +0.0151, MiniLM +0.0298. NFCorpus +0.0169, +0.0301. SciDocs −0.0092, −0.0150 | `rrf_sweep.py --summary` | lab, re-run |
| Holm over six rows with 1,000,000 sign patterns: 0.043 for three rows, 0.001 for the two MiniLM rows on NFCorpus and SciDocs. 0.097 in a family of 12 | `--summary --resamples 1000000` | lab, not re-run at 1,000,000. The default 10,000-pattern run printed 0.034 and 0.040 for the three rows |
| SciDocs recall@100: MiniLM 0.5101 to 0.4814 fused. bge-small 0.4591 to 0.4468 | `--summary` | lab, re-run |
| k from 1 to 1,000 on SciFact with bge-small: no k beyond +0.0044 from k = 60, none significant after Holm. RRF k = 60 is 0.7278 | `rrf_sweep.py --dense bge-small` | lab, re-run |
| k tuned on 809 train queries: k = 2. On test +0.0031 against k = 60, p = 0.618 | same | lab, re-run |
| Dense weight 2: SciDocs MiniLM +0.0065, Holm p < 0.001. SciDocs bge-small +0.0034, Holm 0.131. SciFact MiniLM −0.0108 | `--summary` | lab, re-run. Default run printed Holm 0.129 |
| TM2C2 with alpha 0.9 on bge-small: 0.7322 against RRF 0.7278, +0.0045, p = 0.507 | `rrf_sweep.py --dense bge-small` | lab, re-run |
| Raw-score sum at alpha 0.8: 0.7012, BM25's first result on top for 94.3% of queries. Normalised: 0.7212, 84.3%. Spread rank 1 to 10: bge-small 0.047, BM25 0.488 | `rrf_sweep.py --raw-sum --dense bge-small` | lab, not re-run |
| Low-overlap slice, MiniLM: fused +0.0501 over MiniLM, Holm p = 0.173 | `rrf_sweep.py --dense minilm --slices` | lab, not re-run |
| Elasticsearch 9.5.4: `rank_constant` 60, window defaults to `size`, weight multiplies the vote. Qdrant 1.19.1: `DEFAULT_RRF_K = 2` with positions from 0, which is Cormack's k = 1, weight divides the position. Weaviate from 1.24: `relativeScoreFusion`, alpha 0.75 | source files, docs | cited |
| Cormack et al., SIGIR 2009: k = 60 from four pilots, each fusing 30 configurations of one lexical engine. Table 1 MAP 0.2123 at k 10, 0.2145 at 60, 0.2147 at 80. No dense retriever | RRF paper | cited |
| Bruch, Gai and Ingber: TM2C2 beat RRF k = 60 on every dataset they tested. SciFact NDCG@100 0.753 against 0.730 | their paper | cited |

**Labs.** E4 break-it: `uv run python phase05_hybrid/fusion.py --weights`, then `--self-test --mutate zero-based`. E5: `rrf_sweep.py --dense bge-small`. E6: `--summary --resamples 1000000`. E7 break-it: `--raw-sum --dense bge-small`. E8: `--dense minilm --slices`.

**Reusable code.** In `fusion.py`: `rrf_query()` at line 61, `rrf()` at 79, `convex_query()` at 100, `convex()` at 112. `_RANK_BASE = 1`. The TM2C2 version gives a missing document the lowest possible score. Bruch et al. compute it instead.

**Reusable method.** Measure each retriever alone first. Set the window to at least the depth the next stage reads. Write down the rule and its constant. Tune k, weights or alpha on a development split. Report fusion per slice.

**Terms and symbols.** RRF, `k` as the RRF constant, `w`, alpha, window, TM2C2, convex combination.

**Deferred.** None stated. Phase 6 multi-query links here.

### 5.3 — A reranker is capped by the recall it receives

**Claim.** A reranker can only reorder what it receives. Recall at its input depth is its ceiling. Past a point, a deeper list adds more wrong candidates than right ones. Pick the depth on a development split.

| Key number | Source | Checked |
|---|---|---|
| bge-small first stage 0.7127. Ceiling 0.8388 at depth 10 to 0.9767 at 200. Reranked peaks at 0.7366 at depth 30. Depth 200 gives 0.7262 | `rerank_depth.py`, cached scores | lab, re-run |
| Depth 200 minus depth 30: −0.0104, p = 0.229 | `--resamples 1000000` | lab, re-run. Default run p = 0.228 |
| Depth 30 to 200: 9 labelled relevant and 1,169 unlabelled arrivals. 247 queries same, 44 worse, 9 better. 130 arrivals above a relevant document | `rerank_depth.py` | lab, re-run |
| Best depth: BM25 30, +0.0526, p < 0.001. RRF k = 60 depth 10, 0.7488 | same | lab, re-run |
| Depth picked on 809 train queries: 10, 20 and 10. RRF plus reranking at 10 beats bge-small by 0.0361, p = 0.009. Train, bge-small: depth 200 is 0.0227 below depth 10, p < 0.001 | `rerank_depth.py --heldout` | lab, not re-run |
| Latency median grows with depth on MPS and CPU. Depth 100 on MPS: 1,709 ms in one run, 7,942 ms in another, under heavy load | `rerank_depth.py --latency` | lab, not re-run |
| BEIR: BM25 plus a MiniLM-L6 cross-encoder over the top 100 of 1M DBPedia documents, estimated average 450 ms on one V100, 6,100 ms on CPU | BEIR, Table 3 | cited |
| Voyage billing rule, 300 SciFact queries: depth 100 bills 11,504,458 tokens, $0.575 at $0.05 per million | `hosted_rerank.py --estimate --depth 100` | lab, re-run |

**Labs.** E9: `uv run python phase05_hybrid/rerank_depth.py --resamples 1000000`, then `--heldout`, then `--self-test --mutate read-past-depth`. The first run scores 101,230 pairs, about 1,011 s on MPS. E10: `--latency --devices mps cpu --threads 4`, and `hosted_rerank.py --estimate`. The live call is UNVERIFIED with a $1.00 cap.

**Reusable code.** In `rerank_depth.py`: `rerank()` at line 141, `ceiling()` at 152, `newcomers()` at 163, `depth_effect()` at 183, `pick_depth()` at 223, `heldout()` at 230. Cached logits sit in `.cache/rerank/ettin-32m@b33e5ceb5110/`.

**Reusable method.** Print recall@d for d from 10 to 200. Sweep the reranker on a development split and pick where it stops rising. Confirm once on test. Time it on the serving host with the load stated. Re-run when the first stage changes. If the ceiling is low, fix the first stage.

**Terms and symbols.** `d` as input depth, recall@d, ceiling, cross-encoder, arrivals.

**Deferred.** None stated.

### 5.4 — Late interaction pays for speed with storage

**Claim.** Late interaction moves document encoding to index time, so queries are fast. It pays with one stored vector per token.

| Key number | Source | Checked |
|---|---|---|
| SciFact, 267.5 tokens per document, cut at 300, 55.2% cut. ColBERT 128 × 2 bytes: 68,472 bytes per document, 44.6 times one 384 float32 vector. ColBERTv2 2-bit: 9,629 bytes, 6.3 times. 1-bit: 5,349, 3.5 times | `late_interaction.py` | lab, re-run |
| MS MARCO: vanilla ColBERT 154 GiB, ColBERTv2 16 and 25 GiB, one 768 float32 vector a little over 25 GiB. So about 6 times, about 69 tokens per passage | ColBERTv2 section 5.3, arithmetic in the script | cited, arithmetic re-run |
| mxbai-edge-colbert-v0-17m, 48 dims: 33.7 times. Reranking bge-small's top 100: 0.7127 to 0.7320, p = 0.170 | `late_interaction.py --measure` | lab, not re-run |
| ColBERT over 170 times faster than a BERT-base cross-encoder, 14,000 times fewer FLOPs, one V100 | ColBERT paper | cited |

**Labs.** E11: `uv run python phase05_hybrid/late_interaction.py`, then `--measure`. Try `--max-len 512`: 326.7 tokens, 54.4 times.

**Terms and symbols.** late interaction, MaxSim, token vector, residual compression.

**Deferred.** Page-image retrieval with multi-vector models goes to Module 5.

### 5.5 — Precision can silently scramble a reranker

**Claim.** A bfloat16 sigmoid has only 128 values between 0.5 and 1.0. Strong matches tie, and the tie rule sets the order. Check distinct scores, ties and shuffled-tie nDCG@10 after any change in precision or library version.

| Key number | Source | Checked |
|---|---|---|
| bfloat16 values in [0.5, 1.0): 128, step 2⁻⁸. Every logit from 6.25 up gives exactly 1.0 | `precision_trap.py` | lab, re-run |
| Pre-v6 path, bfloat16 sigmoid: 561 distinct scores of 30,000. 251 of 300 queries tie in the top 10. Shuffled ties 0.6594, −0.0666 against float32's 0.7260. Stable sort 0.7340 | same | lab, re-run |
| v6 path, logits upcast: 2,243 distinct, 71 queries, −0.0021, p = 0.335 | same | lab, re-run |
| float32 scores stored in bfloat16: 980 distinct, 249 queries, −0.0663 | same | lab, re-run |
| 537 of 30,000 pairs score 1.0. 122 queries have two or more tied at 1.0 | same | lab, re-run |
| Real sentence-transformers 5.7.0 scores equal the rebuilt pre-v6 path. 6.1.0: 83.6% bit-identical to the rebuilt v6 path, the rest within 1.2e-7 | `old_st_scores.py` | lab, not re-run |
| NanoBEIR in both versions: 0.1956 with 5.7.0, 0.6224 with 6.1.0. The notes say 0.1849 and 0.6795. 39% of NanoBEIR pairs saturate against 1.8% on SciFact | `old_st_scores.py --nanobeir` | lab, not re-run |
| sentence-transformers v6.0.0, 2026-08-18, upcasts logits before the activation, `model.py` lines 720 to 722 in v6.1.0 | release notes, source | cited |

**Labs.** E12 break-it: `uv run python phase05_hybrid/precision_trap.py`, then `--self-test --mutate no-upcast`. Optional runs build a second environment with sentence-transformers 5.7.0.

**Reusable code.** `sigmoid_path()` at `precision_trap.py:78`. `split_apply()` at line 90 applies a function to one long tensor, because `torch.sigmoid` rounds the last bit differently by tensor length.

**Reusable method.** After a change of dtype, library, device or export format, print distinct scores and top-10 ties. Score nDCG@10 with ties shuffled over 3 seeds. Sort on logits or apply the sigmoid in float32. Keep stored scores in float32.

**Terms and symbols.** bfloat16, logit, sigmoid, tie, stable sort.

**Deferred.** None stated.

---

## Phase 6 — Queries and chunks

Phase 6 adds two LongEmbed sets, QMSum meeting transcripts and 2WikiMultihopQA, 22.9 MB. One exercise downloads Qwen2.5-0.5B-Instruct, 988 MB.

### 6.1 — A rewrite helps only a retriever that knows less

**Claim.** A rewrite helps only when the text it adds knows more than your retriever. So HyDE and Query2doc help weak retrievers and can lower strong ones.

| Key number | Source | Checked |
|---|---|---|
| HyDE Table 4, DL19: Contriever 44.5 to 61.3 with InstructGPT. Fine-tuned Contriever 62.1 to 60.2 with FLAN-T5-xxl, 67.4 with InstructGPT | HyDE, arXiv 2212.10496 | cited |
| Query2doc zero-shot SciFact: BM25 66.5 to 68.6. SimLM 62.4 to 59.5. E5-base 70.4 to 67.5 | Query2doc, Table 2 | cited |
| Rewrite-Retrieve-Read, MMLU social sciences: 78.2 to 76.4 with an LLM rewriter | arXiv 2305.14283 | cited |
| Stand-in, 18 runs: 2 gains and 3 losses before correction. Holm over 18: 0 gains, 2 losses, SciFact MiniLM and bge-small at N = 3 | `expand.py --dataset scifact nfcorpus scidocs` | lab, not re-run |
| SciFact bge-small: N = 1 −0.0053, p = 0.445. N = 3 −0.0324. 46 queries with no hit gained +0.0592, the rest lost −0.0170 | `expand.py --dataset scifact --retrievers bge-small --depths 1 3` | lab, re-run |
| Qwen2.5-0.5B HyDE passages on NFCorpus: BM25 +0.0205, Holm p = 0.0006. MiniLM +0.0119, Holm p = 0.059. bge-small no difference. SciFact: nothing moved | `generate.py`, `expand.py --passages` | lab, not re-run |

**Labs.** E1: `uv run python phase06_queries_chunks/expand.py --dataset scifact nfcorpus scidocs`. E2 break-it: `expand.py --self-test --mutate no-query`. E3: `generate.py --dataset nfcorpus`, then `expand.py --passages <path>`. E5 live, UNVERIFIED, at most $0.25.

**Reusable code.** `hyde_vector()` at `expand.py:67` is HyDE equation 8. Query2doc's sparse form repeats the query 5 times before the passage.

**Reusable method.** Measure the baseline and the share of queries with no hit. Run the stand-in. Run a real generator on 300 queries with the paired test. Check the size against 1.5. Keep a rewrite only for a significant gain worth 6.2's cost.

**Terms and symbols.** query rewriting, HyDE, Query2doc, pseudo-document, PRF, `N` as pseudo-documents, `n = 5`.

**Deferred.** Deciding per query whether to rewrite is routing, Module 4. Stated in 6.2 and `course.json`.

### 6.2 — A rewrite puts an LLM call before every search

**Claim.** A rewrite adds the time to first token plus the output time to every query, before the search starts. For a search under a millisecond, that is thousands of times the search.

| Key number | Source | Checked |
|---|---|---|
| Added time = time to first token + output tokens / decode speed. With 400 ms and 150 tokens per second, examples only: 128 tokens add 1,253 ms, 20 tokens add 533 ms | `rewrite_cost.py:59` | formula |
| Claude Haiku 4.5 at $1 and $5 per million: HyDE costs $0.70 per 1,000 queries, $70 a day at 100,000. Five more 200-token chunks in the answer prompt add $1.00 per 1,000 | `rewrite_cost.py --ttft-ms 400 --tps 150 --extra-chunks 5` | lab, re-run |
| BM25 on SciFact, one query per call, load near 9: plain 0.143 to 0.159 ms, expanded 188 words 0.381 to 0.420 ms | `expand.py` | lab, not re-run |
| Query2doc Table 6: BM25 16 ms, expanded search 177 ms, the LLM call more than 2,000 ms | Query2doc | cited |
| Qwen2.5-0.5B on MPS, 128 tokens: median 6.35 s, 23.7 tokens per second, at load 6 to 15. 10.97 s and 16.35 s under heavier load | `generate.py --latency 20` | lab, not re-run |
| RAG-Fusion: 34.62 s against 19.52 s, 1.77 times, mostly the second LLM call | arXiv 2402.03367 | cited |

**Labs.** E4: `uv run python phase06_queries_chunks/generate.py --dataset scifact --latency 20`, then `rewrite_cost.py --ttft-ms 400 --tps 150 --extra-chunks 5`. Try `--serial --search-ms 30`.

**Reusable method.** Measure your provider's time to first token and decode speed with 20 calls. Cap the output. Run multi-query searches in parallel. Time the whole path, not only the retrieval service.

**Terms and symbols.** time to first token, decode speed, multi-query.

**Deferred.** Routing, Module 4. Tool results kept across agent steps: Module 2, 2.4.

### 6.3 — Chunk or not matters more than where you cut

**Claim.** Whether the model reads every part of every document matters far more than where the cuts go. Chunking long documents moved nDCG@10 by 0.36 to 0.51. The choice of chunker moved it by 0.035 at most. Only 5 of 15 chunker comparisons survive one Holm family.

| Key number | Source | Checked |
|---|---|---|
| 2WikiMultihopQA, MiniLM: whole documents 0.4644, fixed chunks 0.9160, +0.4516. Semantic +0.0185, p = 0.150 | `bakeoff.py --dataset 2wikimqa` | lab, not re-run |
| SciFact, MiniLM: none −0.0289, p = 0.0378, borderline. No chunker differs from fixed with either model | `bakeoff.py --dataset scifact` | lab, re-run |
| One Holm family of 15 comparisons: 5 significant, 7 before correction. 2Wiki late +0.0318, recursive +0.0341, semantic +0.0335 with bge-small. QMSum late +0.0348. QMSum bge-small semantic −0.0234 | `bakeoff.py --dataset scifact 2wikimqa qmsum --one-family` | lab, re-run |
| The `wide` control matches late chunking: +0.0035, p = 0.440 on QMSum. The gain came from more text behind each vector | `bakeoff.py --dataset qmsum --models minilm --methods late wide --base late` | lab, not re-run |
| 254-token windows beat 128-token windows: +0.0383 on QMSum, +0.0311 on 2Wiki, both p < 0.002 | Phase 6 review | lab, not re-run |
| Caspari et al., CIKM 2026: semantic, late and contextual chunking beat token chunking significantly in 0% of settings on nDCG@10. Token beat semantic in 62% | arXiv 2608.16586, Figure 1a | cited |

**Labs.** E6: `uv run python phase06_queries_chunks/bakeoff.py --dataset scifact`. E7: `--dataset 2wikimqa`, `--dataset qmsum`, the overlap tests, and `--one-family`. E8: `--methods late wide --base late`.

**Reusable code.** In `chunkers.py`: `fixed_windows()` at line 101, `fixed_chunks()` at 111, `recursive_spans()` at 134 and `sentence_spans()` at 184. Also `breakpoints()` at 201, `semantic_spans()` at 211, and `late_window()` and `late_pool()` at 249 and 254. `bakeoff.py` methods: none, fixed, recursive, semantic, late, wide, nooverlap, titled. `CHUNK_TOKENIZER = "minilm"` at `bakeoff.py:95` cuts every chunk. `longdocs.py` loads the two LongEmbed sets at a pinned revision.

**Reusable method.** Measure truncation first. Chunk if much of the corpus is cut off. Size the test before comparing chunkers. Use the paired test with Holm, and choose the family first. Weigh index cost. Tune chunk size before the method.

**Terms and symbols.** chunk, chunker, coverage, boundaries, late chunking, wide, truncation as input tokens.

**Deferred.** Parsing documents into text goes to Module 5.

### 6.4 — Smart cuts pay only when the topic changes

**Claim.** A chunker that looks for boundaries helps only where a document changes topic. Semantic chunking needs a size cap.

| Key number | Source | Checked |
|---|---|---|
| bge-small, 2Wiki: recursive +0.0341, p = 0.0016. Semantic +0.0335, p = 0.0010. QMSum: recursive −0.0166, p = 0.0251, Holm 0.251 in the family of 15. Semantic −0.0234, p = 0.0032 | `bakeoff.py` | lab, re-run in the one-family run |
| Chunks that mix two passages: fixed 12.5%, recursive 7.7%, semantic 8.9%. Only 4,040 of 25,588 semantic cuts come from the percentile rule | `chunkers.py --mixing 2wikimqa` | lab, not re-run |
| QMSum: no overlap 0.5487 against 0.5762 with overlap, p = 0.0002. Against windows without overlap: recursive +0.0109, semantic +0.0041, no difference | `bakeoff.py --methods fixed nooverlap`, `--base nooverlap` | lab, not re-run |
| LangChain `SemanticChunker` with no cap: 58% of chunks over 254 tokens, −0.0642, p = 0.0002 | `bakeoff.py ... --semantic-cap 0` | lab, not re-run |
| Newlines removed: recursive −0.0497, p = 0.0004. Semantic still +0.0335 | `bakeoff.py ... --flatten` | lab, not re-run |
| Vectara, Qu et al.: breakpoint chunking won on stitched documents, fixed won on real ones. No significance test | arXiv 2410.13070 | cited |

**Labs.** E9 break-it: `--semantic-cap 0`, then `chunkers.py --self-test --mutate no-cap`. E10 break-it: `--flatten`.

**Reusable method.** Look at your documents first. Joined pieces with structure markers: recursive. Joined pieces without markers: capped semantic. One topic per document: fixed windows with overlap. Test with the paired test.

**Terms and symbols.** percentile rule, cap, overlap, flatten.

**Deferred.** Extractors that drop newlines belong to Module 5. This section shows only the effect on chunking.

### 6.5 — Price contextual retrieval with today's cache rules

**Claim.** Contextual retrieval re-reads each document once per chunk, so its cost per token grows with document length. Caching helps only above the model's minimum, and only for calls that start after the first response.

| Key number | Source | Checked |
|---|---|---|
| `cost = D × write + (n − 1) × D × read + n × (C + I) × input + n × O × output` | `contextual_cost.py:78` | formula |
| Claude Haiku 4.5, D 8,000, C 800: $3.84 per million document tokens. 64,000-token documents $10.84. 128,000 tokens $18.84. Cheapest at 4,096 tokens, $3.73 | `contextual_cost.py`, `--sweep` | lab, re-run |
| 2024 Claude 3 Haiku prices: $0.99 with n − 1 reads, $1.02 with n reads. The model and the formula are inferred from arithmetic | `contextual_cost.py` | lab, re-run |
| Below the 4,096-token minimum, 3,000 tokens: $5.80, never cached, no error | `--doc-tokens 3000` | lab, re-run |
| All chunk calls of a document sent at once: $14.19, above $11.69 with no caching | `--parallel` | lab, re-run |
| Batch at a 30% hit rate: $5.54 with 5-minute writes, $8.28 with 1-hour writes. At 98%: $2.02 and $2.46 | `--batch --hit-rate 0.3`, `--ttl 1h` | lab, re-run for 30% |
| One 100-token summary per document instead: $1.07 | `contextual_cost.py` | lab, re-run |
| Title in front of each fixed window, no LLM: SciFact MiniLM +0.0123, p = 0.238. All four runs positive and not significant | `bakeoff.py --dataset scifact nfcorpus --methods fixed titled` | lab, not re-run |
| Anthropic: failure rate 5.7% to 3.7% with contextual embeddings, 2.9% with contextual BM25, 1.9% with reranking. 1 minus recall@20. No significance test | Anthropic post | cited |
| Haiku 4.5: $1 input, $1.25 5-minute write, $2 1-hour write, $0.10 read, $5 output, minimum 4,096 tokens. claude-3-haiku-20240307 retired on 2026-04-20 | Anthropic pricing, caching and deprecation pages, fetched 2026-09-23 | cited |

**Labs.** E11: `uv run python phase06_queries_chunks/contextual_cost.py`, then `--sweep`, then the titled bake-off. E12 break-it: `--doc-tokens 3000`, `--parallel`, `--batch --hit-rate 0.3`, and `--self-test --mutate no-min-cache`.

**Reusable code.** `per_document()` at `contextual_cost.py:78`. `summary_per_document()` at line 107. `prices.py` holds `Price` and `BATCH_DISCOUNT = 0.5`.

**Reusable method.** Sum cost per document from your length distribution. Check each document against the minimum. Send call 1, wait for its first token, then send the rest. Log `cache_read_input_tokens` on call 2. Price batches with a hit rate. Test the free titled baseline before the paid version.

**Terms and symbols.** `D`, `C`, `I`, `O`, `n` as chunks per document, cache write, cache read, minimum.

**Deferred.** Prompt caching rules stay in Module 1, 3.2 and 3.3. LLM-written contextual retrieval quality was not measured.

---

## Phase 7 — Freshness, deletes and model upgrades

Phase 7 uses SciFact, bge-small and MiniLM, hnswlib 0.8.0 with M 16 and efConstruction 200. All hnswlib builds pass `SEED_OFFSET + seed`, with `SEED_OFFSET = 100`.

### 7.1 — Churn leaves nodes nobody can reach

**Claim.** A graph index under churn loses recall in two ways. A worse graph costs recall that a larger ef buys back. Unreachable nodes cost recall that only a rebuild restores.

| Key number | Source | Checked |
|---|---|---|
| 5% delete and reinsert per round with slot reuse, mean of seeds 0 to 2. Fresh: ANN recall@10 0.8759 at ef 10, 0.9888 at 50, 1.0000 at 400. Round 200: 0.8396, 0.9794, 0.9991. 3.3 nodes not reached. Self-miss at ef 400 0.0008 | `churn.py` | lab, not re-run. About 155 s per seed |
| Seed 0, 50 rounds: 3 nodes not reached, self-miss at ef 400 0.0006, which is 3 vectors. Rebuild restores 0 | `churn.py --seeds 0 --rounds 50 --every 25` | lab, re-run |
| Xiao et al.'s rule, unreachable nodes never updated: 20.0 not reached after 200 rounds, while ANN recall@10 at ef 400 reads 0.9976 | `churn.py --protect-unreachable` | lab, not re-run |
| Under random updates the count stays between 1.7 and 4.0 | `churn.py` | lab, not re-run |
| The seed offset moved every number by at most 1.3 nodes or 0.0063 ANN recall@10 | coherence report | cited |
| Xiao et al.: SIFT1M, 3,000 rounds of 5%, 3% to 4% unreachable, recall down about 3%. GIST1M random updates, about 3% to 4% | arXiv 2407.07871 | cited |
| A fresh build of 2,000 random vectors has 1 unreachable node | `hnsw_graph.py --demo` | lab, re-run |

**Labs.** E1: `uv run python phase07_freshness/hnsw_graph.py --demo`. E2: `churn.py`. E3: `--protect-unreachable`.

**Reusable code.** In `phase07_freshness/hnsw_graph.py`: `read_file()` at line 123 and `read_index()` at 147 parse hnswlib 0.8.0 links. `edges()` at 166 reads only the first `count` slots. `counts()` at 182 returns `zero_in_l0`, `zero_in_all` and `not_reached`. `SEED_OFFSET` at line 80, `DELETE_MARK = 0x01` at line 67. `churn.py` holds `Churner`, with `round()` at line 122.

**Reusable method.** Know which delete your store does. Raise ef first for the graph loss. Measure reachability separately by self-search at a large ef. Count nodes with no incoming link if the library exposes the graph.

**Terms and symbols.** churn, tombstone, slot reuse, unreachable, `zero_in_all`, `not_reached`, self-miss.

**Deferred.** When to rebuild: 7.2.

### 7.2 — Rebuild on a probe, not on a count or a clock

**Claim.** Vector stores clean up on a count of deletes or on a timer. Neither measures recall. Trigger rebuilds from probes that measure what queries can find.

| Key number | Source | Checked |
|---|---|---|
| 100 rounds, slot reuse, serving ef 50: the 20% deleted-share rule never fires, deleted share 0.0%. A timer rebuilt 4 times and bought nothing: mean ANN recall@10 0.9806 either way. Probe policy: 1 rebuild, self-miss 0.0005 against 0.0008 | `rebuild_policy.py` | lab, not re-run. 18 minutes |
| One round after a fresh build: 0.9888 to 0.9834, two rounds 0.9821 | Phase 7 | lab, not re-run |
| Tombstones, 40 rounds: records 5,183 to 15,543. ANN recall@10 at ef 50 0.9888 to 0.9862. Batch time 0.108 to 0.274 ms, 1.3 to 2.9 times across runs | `churn.py --mode tombstone --rounds 40 --every 10` | lab, not re-run |
| Under tombstones the 20% rule fires at round 6: 1,554 / 6,737 = 0.231 | Phase 7 | formula |
| A 500-vector probe misses 3 unreachable nodes of 5,183 with chance 0.7376 | Phase 7 | formula |
| Qdrant 1.19.1 `deleted_threshold` 0.2 and `vacuum_min_vector_number` 1,000. Weaviate 1.39.6 `cleanupIntervalSeconds` 300. pgvector on `VACUUM`. hnswlib: the application decides | `config.yaml`, `config.go`, Postgres docs | cited |

**Labs.** E5: `churn.py --mode tombstone --rounds 40 --every 10`. E6: `rebuild_policy.py`. A faster first run: `--policies none probe --seeds 0`.

**Reusable method.** Probe A: ANN recall@10 at the serving ef on 300 fixed queries. Probe B: 500 sampled live vectors query themselves at ef 400. Run both after each batch of updates. Treat any probe B miss as a rebuild ticket. Track records per live vector under tombstones. Rebuild beside the serving index.

**Terms and symbols.** probe A, probe B, `u`, `s` as sample size, deleted share, records per live vector.

**Deferred.** Drift in an IVF index: item 7, inferred and not measured.

### 7.3 — Deleted is not gone

**Claim.** A soft delete removes a vector from answers, not from disk. Only an overwrite or a rebuild from the source rows removes the bytes, in every copy.

| Key number | Source | Checked |
|---|---|---|
| 50 soft-deleted SciFact vectors: file 8,731,744 bytes before and after. 50 of 50 found byte for byte. `get_items` raises `Label not found` | `soft_delete.py --faiss` | lab, re-run |
| 50 slot-reuse inserts erase 50. A rebuild from 5,133 live rows keeps 0. A rebuild from the old file keeps 50 | `soft_delete.py --faiss`, `--rebuild-from-file` | lab, re-run |
| FAISS `IndexHNSWFlat.remove_ids` raises "not implemented". `IndexIDMap2` removes 50 | `soft_delete.py --faiss` | lab, re-run |
| One leaked vector's nearest live neighbour has cosine 0.863 and names the same topic | same | lab, re-run |
| hnswlib: `mark_deleted(L)` then `add_items(v, L, replace_deleted=True)` loses 138 of 5,183 labels in one batch of 259. Model: (n − 1)/2 = 129 | `churn.py --reuse-labels --rounds 3 --seeds 0` | lab, re-run |
| 20 seeds on random vectors lost 124 to 142, mean 132.6 | Phase 7 review | cited |
| Vec2Text recovered 92% of 32-token inputs for GTR-base. Ghost Vectors: 25.5% of names and 46.4% of locations from soft-deleted vectors, preprint | arXiv 2310.06816, 2606.18497 | cited |
| pgvector 0.8.6 `VACUUM` zeroes the deleted vector, `hnswvacuum.c:688`. Read, not run | pgvector source | cited |

**Labs.** E4 break-it: `churn.py --reuse-labels --rounds 3 --seeds 0`, then `--update-paths`. E7: `soft_delete.py --faiss`, then `--reuse 20`. E8 break-it: `--rebuild-from-file`.

**Reusable code.** `bytes_present()` at `soft_delete.py:73` searches raw file bytes for each vector.

**Reusable method.** An erasure checklist for vectors. List every copy. Name the operation that removes the bytes in each. Rebuild from source rows, never from the old index file. Verify with a byte search. In hnswlib, update with `add_items` on the live label and `replace_deleted=False`, or give every version a new label.

**Terms and symbols.** soft delete, hard delete, label table, `n` as updates per batch.

**Deferred.** Right to erasure as a legal process goes to Module 18. Stated in 7.3 and `course.json`.

### 7.4 — A new model invalidates every vector

**Claim.** Vectors from two models are never comparable, even when shapes match. An adapter imitates the old model's query, so a perfect adapter gives the old system. Only a re-embed gives the new model's gain.

| Key number | Source | Checked |
|---|---|---|
| SciFact, old index MiniLM 0.6451. bge-small queries on it with no map 0.1367. Full re-embed 0.7127. Adapters from 2,000 pairs, seeds 0 to 2: rotation 0.4488, centered rotation 0.5897, least squares 0.5870. All below the old system, p < 0.001 | `model_upgrade.py --protocol` | lab, re-run |
| Mean cosine of two random documents: MiniLM 0.131, bge-small 0.629, mpnet 0.128 | same | lab, re-run for MiniLM and bge-small |
| 100 pairs: rotation 0.1051, below no map. Least squares 0.2327 | `model_upgrade.py --pairs 100` | lab, re-run |
| Centered rotation on all 5,183 documents: 0.6158, p = 0.023. Plus 809 train queries: 0.6173, p = 0.027 | `--pairs 5183`, `--fit-on both` | lab, not re-run |
| MiniLM to mpnet: re-embed 0.6557, +0.0106, p = 0.437. Rotation adapter 0.5757. agree@10 0.652 against 0.595 for the old model. Drift-Adapter reports 0.974 | `model_upgrade.py --new mpnet --protocol` | lab, not re-run |
| Drift-Adapter protocol on AG-News, 50,000 items, 20,000 pairs: rotation 0.514 against 0.532 for the old model, p < 0.001 | `agnews_protocol.py --encode` | lab, not re-run |
| AG-News has 120,000 training items. The paper's 1 million-item database cannot be built as written | Hugging Face API | cited |

**Labs.** E9: `uv run python phase07_freshness/model_upgrade.py --protocol`, then `--fit-on both`. E10 break-it: `--pairs 100`. E11: `--new mpnet --encode --protocol`, then `uv run --with pyarrow==25.0.1 python phase07_freshness/agnews_protocol.py --encode`.

**Reusable code.** `fit()` at `model_upgrade.py:80` with methods `op`, `op-centered` and `lstsq`. `geometry()` at line 97. `paper_protocol()` at line 146. The mpnet spec at line 69.

**Reusable method.** Keep the old query model while it can run. Use an adapter only as a bridge when it cannot. Measure the mean cosine of each space, agreement with the new model, and the label score against the old system. Decide on the label score. Plan the re-embed anyway.

**Terms and symbols.** adapter, agree@10, ARR, orthogonal Procrustes, `A`, `B`, `R` as rotation.

**Deferred.** Serving embedding models on GPUs goes to Module 13.

### 7.5 — Switch behind a dual index and an eval gate

**Claim.** Never mix two embedding spaces in one index. Build the new index beside the old one and shadow real queries. Flip the alias only when the interval on your labels rules out a loss beyond the margin and no slice loses significantly.

| Key number | Source | Checked |
|---|---|---|
| In-place migration at 50%: 0.3739 with MiniLM queries, 0.3789 with bge-small queries. At 25% bge-small queries see only new documents | `switch_gate.py` | lab, re-run |
| Gate, margin 0.01: bge-small PASS, +0.0676, interval [+0.0414, +0.0942]. mpnet FAIL, +0.0106, [−0.0157, +0.0364], p = 0.437, and recall@10 reaches −0.0283. Adapter FAIL, seed 0 0.5820 | same | lab, re-run |
| An average-only gate passes mpnet | `switch_gate.py --candidates mpnet --average-only` | lab, re-run |
| To show +0.0106 with 80% power: 3,714 labelled queries | same | lab, re-run |
| Slice power at about 100 queries: 0.041 to 0.123 across the three candidates. A ±0.01 slice interval needs (1.96 × 0.231 / 0.01)² = 2,050 queries per slice | same, Phase 7 | lab, re-run for the range. formula for 2,050 |
| Shadow overlap@10 of bge-small with MiniLM on 809 train queries: 0.469. Low overlap did not mark the queries where quality moved most | same | lab, re-run |
| The lower end of a two-sided 95% interval is a one-sided 2.5% bound | Phase 7 | formula |
| bge-small encoded 213 documents per second on MPS, so 10M documents take about 13 hours | Phase 7 | formula |

**Labs.** E12 break-it: `uv run python phase07_freshness/switch_gate.py --average-only`, then without it. Setup needs `switch_gate.py --encode --candidates bge-small` once.

**Reusable code.** `gate()` at `switch_gate.py:89` with `MARGIN = 0.01` at line 66. `mixed_index()` at 69. `shadow()` at 114. `candidate_vectors()` at 122. The gate uses `compare()` and Phase 1's `slice_table`.

**Reusable method.** A seven-step runbook. Build and size the new index beside the old. Estimate the re-embed. Dual-write and shadow. Store model name and revision with every vector and refuse a mismatch. Pool labels from both systems. Run the gate. Flip the alias and keep the old index for rollback, then apply 7.3 to its files.

**Terms and symbols.** margin, non-inferiority, shadow query, dual write, alias flip.

**Deferred.** Judges, golden sets and CI gates go to Module 11.

### The module question, answered

**Claim.** Swap one stage at a time for its exact or ideal version, and test each swap with the paired test. The first swap that fixes the slice names the stage.

**The chain.** Nine steps, cheapest first. The last column is where each measurement is taught.

| Step | Stage | Measurement on the failing slice | Sections |
|---|---|---|---|
| 1 | Metric and slice | The metric at the consumer's depth, per slice, paired test and Holm. Check the slice can see the loss | 1.2, 1.4, 1.5, 7.5 |
| 2 | Model ceiling | Exact search on the slice. Count documents past the encoder's limit | 1.1, 6.3 |
| 3 | Index recall | ANN recall@10 and relevance with the index against exact search. The real search list | 2.1, 2.5 |
| 4 | Filters | Rows returned under the customer's filter, then filtered ANN recall@10 | 3.1, 3.2, 3.3 |
| 5 | Quantization | The metric with float32 exact search or rescoring on | 4.1, 4.2 |
| 6 | Retriever and fusion | Losses by rarest shared df. Identifiers in an exact field. Fusion on the slice | 5.1, 5.2 |
| 7 | Reranker | Recall at input depth. Distinct scores and top-10 ties | 5.3, 5.5 |
| 8 | Queries and chunks | Chunked against whole documents, each rewrite, newlines kept | 6.1, 6.3, 6.4 |
| 9 | Freshness | Probe B on the customer's vectors. Model and revision on every vector | 7.1, 7.2, 7.4, 7.5 |

Four checks need no labels: rows under the filter, probe B, documents over the encoder's limit, and score ties. Run them early on any customer. The chain stops working when two stages fail at once. After each fix, run it again from step 1.

**Key numbers.** None new. The section quotes numbers from the sections above.

---

## Shared code other modules can reuse

Run everything from `study-material/retrieval-internals/code/` with `uv run python <path>`. Later retrieval modules should import the harness in `code/common/` instead of writing their own metrics or tests. `code/common/HARNESS.md` is the full reference.

### How to import it

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.data import load
```

Do not edit files in `common/`. Register another model at run time with `embed.register`.

### The harness API

| Module | Functions, with line numbers | What it gives you | Self-test |
|---|---|---|---|
| `common/data.py` | `load(name, split="test")` :205, `download(name)` :161, `synthetic(n_topics=20, docs_per_topic=10, seed=0)` :236, `Dataset` :105, `DATASETS` | pinned BEIR sets with hash checks. `scifact` at `cf10ab6856b1`, 5,183 documents, 300 test and 809 train queries. `nfcorpus` at `52ac3f19d344`. `scidocs` at `490848228d0a`. `Dataset.doc_texts` joins title and body | 13 checks |
| `common/embed.py` | `embed_corpus(ds, model)` :187, `embed_queries(ds, model)` :192, `embed_texts(texts, model, kind=, ds_name=, ds_rev=, part=, fp=)` :137, `fingerprint(texts, ids=None)` :116, `exact_search(queries, docs, k)` :203, `get_model()` :95, `register(name, ModelSpec(...))` :109, `cache_meta()` :197, `device_name()` :84 | cached float32 L2-normalised embeddings. Pinned `minilm` at `1110a243fdf4` and `bge-small` at `5c38ec7c405e`. Exact search breaks ties by lower row id | 12 checks |
| `common/lexical.py` | `BM25Config(k1=1.5, b=0.75, method="lucene", stopwords="en", stemmer="english")` :60, `build_bm25()` :90, `bm25_search()` :103, `bm25_score_by_hand()` :118 | BM25 with bm25s 0.3.11 defaults and the English stemmer. -1 where no term matches | 10 checks |
| `common/metrics.py` | `evaluate(run, qrels, metrics)` :174, `ndcg_at_k()` :117, `recall_at_k()` :70, `capped_recall_at_k()` :77, `precision_at_k()` :85, `hit_at_k()` :90, `reciprocal_rank()` :95, `judged_at_k()` :103, `run_from_ids()` :203, `ann_recall()` :208 | metric names `ndcg@K`, `recall@K`, `rcap@K`, `precision@K`, `hit@K`, `mrr@K`, `judged@K`. `EvalResult` has `.mean`, `.per_query`, `.qids`, `.values(metric, qids)` | 27 checks |
| `common/stats.py` | `paired_test(a, b, n_resamples=10_000, seed=0)` :77, `compare(a, b)` :125, `bootstrap_ci(values)` :112, `queries_needed(sd_diff, delta)` :141, `detectable_diff(sd_diff, n)` :146, `holm(pvalues)` :151, `unpaired_test()` :96 | paired randomization test, exact below 17 queries. `compare` adds means, interval, wins, losses, ties and sd of differences. `unpaired_test` is the wrong test, kept for break-it | 18 checks |
| `common/runs.py` | `dense_ids(ds, model, k=100)` :43, `bm25_ids(ds, k=100, cfg)` :48, `score(ds, ids, metrics)` :53, `baseline(ds, k=100)` :59 | one-line runs and scoring, rows in `ds.query_ids` order | 2 checks |

Baseline nDCG@10 from `common/runs.py`, exact search. Verified by `baseline.py` and `benchmark_gap.py` re-runs:

| Dataset | BM25 | MiniLM | bge-small |
|---|---|---|---|
| SciFact | 0.6863 | 0.6451 | 0.7127 |
| NFCorpus | 0.3214 | 0.3167 | 0.3438 |
| SciDocs | 0.1578 | 0.2164 | 0.2052 |

### Rules for every later module that uses this code

1. **Never load torch and FAISS in one process.** torch 2.14.0 and faiss-cpu 1.15.1 each ship `libomp.dylib`. One process stops with `OMP: Error #15`, in either import order. Encode in one run, then run FAISS in a later run that reads the cached `.npy` files. `embed.py` imports torch only on a cache miss. `KMP_DUPLICATE_LIB_OK=TRUE` hides the error and is unsafe. hnswlib 0.8.0 does not use OpenMP and is safe next to torch. scikit-learn was not checked. Source: `HARNESS.md`.
2. **Offset hnswlib seeds on macOS.** hnswlib 0.8.0 seeds `std::default_random_engine`. In libc++ that is `minstd_rand`, which keeps the seed modulo 2^31 − 1 and turns 0 into 1. So seeds 0 and 1 build the same node levels. Pass `random_seed = 100 + seed`. See `bench.py:161` and `SEED_OFFSET = 100` at `phase07_freshness/hnsw_graph.py:80`. Linux libstdc++ was not checked. Source: Phase 2 Check it yourself item 1, Phase 2 review item 11.
3. **Name the pinned versions.** `code/pyproject.toml` pins them. They were read from PyPI on 2026-09-23.
   - Python 3.12.14, numpy 2.5.3, scipy 1.18.1.
   - torch 2.14.0, transformers 5.17.0, sentence-transformers 6.1.0, huggingface_hub 1.32.0.
   - faiss-cpu 1.15.1, hnswlib 0.8.0, bm25s 0.3.11, PyStemmer 3.1.0.

   Write "hnswlib 0.8.0 from PyPI" in every claim. GitHub has 0.9.0 and 0.10.0-rc.2. Extra packages come in only through `uv run --with`, such as h5py 3.16.0, pyarrow 25.0.1, datasets 5.0.1 and scikit-learn 1.9.1.
4. **A new model needs a new key.** The embedding cache path is `<model>@<revision[:12]>/<dataset>@<revision[:12]>/<part>-<fingerprint>.npy`, from `_paths()` at `embed.py:131`. It does not include `max_seq_length` or the prefixes. Registering the same key with other settings reads stale vectors. Phase 4 and Phase 7 share the `mpnet` key, so their specs must match exactly. Verified in code. Source for the risk: Phase 4 review.
5. **Pair scores by query id.** `EvalResult.per_query[m]` follows `EvalResult.qids`, sorted by id. Use `res.values(m, ds.query_ids)` for dataset order.
6. **A labelled query with no results scores 0.** The harness behaves as `trec_eval -c`. Queries whose labels are all grade 0 are skipped and counted.
7. **Every "A beats B" goes through `compare` and says whether p < 0.05.** Re-run any p between 0.03 and 0.07 with `n_resamples=1_000_000`. `bootstrap_ci` does not sort, so its interval moves in the third decimal with query order. Quote the interval from the script that printed it.
8. **State which time you report.** Batch time and one-query-per-call time do not compare. Name the thread count, device and load.
9. **Offline mode.** `RI_OFFLINE=1` forbids downloads. `RI_CACHE` moves the cache. Every self-test also runs with an empty cache and skips checks that need data.

### Cache

Everything sits under `code/.cache/`. On 2026-09-23 it held 6.4 GB: data 1.1 GB, embeddings 2.6 GB, models 2.6 GB, reranker scores 54 MB, Phase 3 graphs 41 MB. Measured with `du -sh`. The VIBE download alone is 1,043.5 MB.

### Phase scripts worth importing

| File | What it provides |
|---|---|
| `phase02_indexes/bench.py` | `Corpus`, `corpus(name)` for SciFact, yahoo-200k and a clustered set. `hnswlib_build()`, `faiss_hnsw()`, `faiss_ivf()`, `timed_search()`, `pareto()`, `at_recall()` |
| `phase02_indexes/graph_memory.py` | bytes per vector for hnswlib and FAISS HNSW |
| `phase03_filters/hnsw_graph.py` | parse an hnswlib graph and run pgvector 0.8.6's scan in Python |
| `phase03_filters/filters.py` | random, tenant and far filters, exact filtered search, filtered ANN recall |
| `phase03_filters/choose_system.py` and `systems.json` | Elasticsearch default by version, crossover model, decision rules, version check |
| `phase03_filters/budget.py` | RAM, SSD and object-store bytes and round-trip latency |
| `phase04_quant/codes.py` | int8, binary, rescoring, truncation, random rotation, `RaBitQLite`, `TurboQuantMSE` |
| `phase04_quant/memory.py` | bytes per vector per format and system |
| `phase04_quant/models.py` | registers nomic, mxbai-xs and mpnet at pinned revisions |
| `phase05_hybrid/fusion.py` | RRF with weights, TM2C2 convex fusion |
| `phase05_hybrid/rerank_depth.py` | cross-encoder scoring with a chunked cache, depth sweep, held-out depth choice |
| `phase06_queries_chunks/chunkers.py` | fixed, recursive, semantic with a cap, late chunking |
| `phase06_queries_chunks/longdocs.py` | QMSum and 2WikiMultihopQA as `Dataset` objects |
| `phase06_queries_chunks/contextual_cost.py` and `prices.py` | contextual retrieval cost with cache minimum, parallel, batch and TTL rules |
| `phase07_freshness/hnsw_graph.py` | hnswlib link parser and reachability counts |
| `phase07_freshness/switch_gate.py` | the non-inferiority gate |

### Self-test counts

All 58 scripts passed on 2026-09-23 with `uv run --offline python <script> --self-test`.

| Phase | Script and checks |
|---|---|
| common | data 13, embed 12, lexical 10, metrics 27, runs 2, stats 18 |
| 1 | baseline 8, benchmark_gap 5, label_budget 4, pick_metric 5, slices 6, two_recalls 7 |
| 2 | bench 8, compare_curves 6, default_drift 5, graph_memory 7, hnsw_sweep 5, hnsw_walk 10, ivf_pq 7, vibe_data 5, vibe_results 2 |
| 3 | budget 7, choose_system 8, exact_crossover 5, filter_walk 5, filters 6, hnsw_graph 9, iterative_scan 6, post_filter 5 |
| 4 | codes 14, memory 6, models 4, quant_table 7, rescore 4, rotate 3, truncate 4 |
| 5 | fusion 12, hosted_rerank 3, late_interaction 6, old_st_scores 3, precision_trap 8, rerank_depth 10, rrf_sweep 5, wins_losses 6 |
| 6 | bakeoff 9, chunkers 13, contextual_cost 10, expand 7, generate 5, longdocs 9, prices 4, rewrite_cost 5 |
| 7 | agnews_protocol 4, churn 16, hnsw_graph 10, model_upgrade 9, rebuild_policy 6, soft_delete 9, switch_gate 8 |

**Live exercises.** Three exist, and none was run. Phase 5 E10 calls a hosted reranker, capped at $1.00. Phase 6 E5 writes HyDE passages with a hosted model, at most $0.25. Phase 3 E12 runs locally on PostgreSQL and costs nothing.

---

## If a later module needs X, link to section Y

| If a later module needs | Link to | What is already there |
|---|---|---|
| Retrieval metrics and the two recalls | `Module 3, 1.1` and `1.2` | ANN recall against relevance recall, the ceiling, metric by consumer, nDCG with the correct IDCG, capped recall, empty labelled queries score 0, `common/metrics.py` |
| The paired test, slices and Holm | `Module 3, 1.4` | sign-flip test, per-slice reports, the family as a choice, Monte Carlo noise, `common/stats.py` |
| Sizing a labelled set, and intervals | `Module 3, 1.5` | `n = ((1.960 + 0.842) × sd / δ)²`, detectable difference, bootstrap interval |
| Building a labelled set from real queries | `Module 3, 1.3` | six steps, pooling, judged@10, BEIR hole study |
| Reading public benchmarks | `Module 3, 1.3` and `2.4` | BEIR and MTEB averages, VIBE and Big-ANN method, ANN-Benchmarks is unmaintained |
| HNSW parameters and defaults | `Module 3, 2.1` and `2.5` | the greedy walk, ef first, M last, search list at k = 10 across eight systems with source lines |
| Memory per vector | `Module 3, 2.2` and `4.4` | hnswlib formula, mean level 1/(M − 1), RAM overhead, five parts of a vector's bytes, Elasticsearch and Qdrant tiers |
| IVF and PQ | `Module 3, 2.3` | nprobe default 1, nlist rules, scanned share, PQ loss inside scanned clusters, re-ranking, collapse on tight clusters |
| Comparing indexes fairly | `Module 3, 2.4` | curves at equal ANN recall, alternation, frontier, exact search on the chart |
| Filtered search and pgvector | `Module 3, 3.1`, `3.2`, `3.3` and `3.4` | ef × s, iterative scans and the tuple cap, the √N crossover, 1 / degree, a Python pgvector 0.8.6 scan and a real 0.8.1 run |
| Disk indexes | `Module 3, 3.5` | codes in RAM, records per 4 KB sector, round trips, DiskANN, FreshDiskANN, SPFresh, cold object-store latency |
| Choosing a vector system | `Module 3, 3.6` | four numbers, a decision tree, Elasticsearch default by creation version and licence, versions on 2026-09-23 |
| Quantization and rescoring | `Module 3, 4.1` and `4.2` | gap/noise, decoded int8, binary loss by model, candidate recall, oversampling factor by model |
| Truncation and MRL claims | `Module 3, 4.3` | dimensions left decide the loss, re-normalise, int8 beats truncation at equal bytes |
| Rotation codes, RaBitQ and TurboQuant | `Module 3, 4.5` | centering against rotation, majority share formula, 4-bit TurboQuant against int8 |
| BM25 and hybrid fusion | `Module 3, 5.1` and `5.2` | rare against common words, identifiers need an exact field, RRF k and weights per system, when fusion hurts, TM2C2 |
| Rerankers and depth | `Module 3, 5.3` | ceiling at input depth, depth picked on a development split, latency and hosted cost grow with depth |
| Late interaction | `Module 3, 5.4` | storage per token, 44.6 times on SciFact, about 6 times on MS MARCO |
| Reranker precision and score ties | `Module 3, 5.5` | bfloat16 sigmoid ties, shuffled-tie nDCG, sentence-transformers 6.0 fix |
| Query rewriting | `Module 3, 6.1` and `6.2` | when HyDE and Query2doc help, the latency and money of a rewrite, multi-query cost |
| Chunking | `Module 3, 6.3` and `6.4` | coverage before boundaries, one Holm family, when smart cuts pay, the semantic cap, lost newlines |
| Contextual retrieval cost | `Module 3, 6.5` | per-document formula, cache minimum, parallel and batch traps, the titled baseline. Cache rules are `Module 1, 3.2` and `3.3` |
| Deletes and churn | `Module 3, 7.1`, `7.2` and `7.3` | unreachable nodes, probes instead of counts or timers, soft delete bytes, the hnswlib label trap, an erasure checklist |
| Model upgrades and eval-gated switches | `Module 3, 7.4` and `7.5` | adapters aim at the old system, dual index, shadow queries, the non-inferiority gate |
| Finding which stage fails for one customer | `Module 3, The module question, answered` | the nine-step chain and four label-free checks |

---

## What Module 3 explicitly leaves to later modules

| Topic | Owner | Where it is stated |
|---|---|---|
| Agentic retrieval, GraphRAG, retrieval without vectors, routing | Module 4 | `course.json` `keptOut`. Routing also in 6.2 and checkpoint 6 |
| Multi-tenant index isolation and semantic caching | Module 4 | `course.json` `keptOut`. No phase text names Module 4 for this |
| PDF parsing, OCR, page-image retrieval | Module 5 | `course.json` `keptOut`. No phase text names Module 5 |
| Judges, golden sets, CI gates | Module 11 | `course.json` `keptOut`, and 1.3 |
| Faithfulness of the generated answer | Modules 11 and 17 | `course.json` `keptOut` |
| Right to erasure as a legal process | Module 18 | `course.json` `keptOut`, and 7.3 |
| Serving embedding models on GPUs | Module 13 | `course.json` `keptOut` |
| Tenant isolation as a security boundary | Module 16 | `_curriculum/README.md` line 150 only. Not in `keptOut` and not in any phase text. Verified by `grep "Module 16"` |

Gaps between `course.json` and the text, verified by grep:

- `keptOut` says Module 3 "uses one paired test". The phases also use Holm, a bootstrap interval and a non-inferiority gate. They are all built on the same `common/stats.py`.
- Section 3.1 uses a tenant filter only as a recall and row-count problem. Section 7.3 covers where deleted bytes stay and what a leaked vector reveals. Neither treats isolation or inversion as a security control. Module 16 should not assume they do.

## Open questions Module 3 left unchecked

A later module can settle these. Each one is marked inferred or not checked in the phase text.

1. pgvector 0.8.6 itself never ran. The SQL lab ran on 0.8.1. The `work_mem × hnsw.scan_mem_multiplier` cap is not modelled. Section 3.2.
2. Drift in an IVF index, and when to retrain centroids and codebooks. Section 7.2 item 7.
3. The quality of LLM-written contextual retrieval. Section 6.5.
4. Hosted reranker latency and cost, Phase 5 E10, and hosted HyDE, Phase 6 E5. Both live exercises were never run.
5. Why Drift-Adapter reports 0.974. A 1M database, HNSW search and the paper's MLP adapter were not tested. Section 7.4.
6. Whether ChromaDB's own hnswlib build returns soft-deleted vectors through `get_items`, and whether pgvector's `VACUUM` zeroing happens as read. Section 7.3.
7. Whether Qdrant's TurboQuant centers, and its per-vector extras. Sections 4.4 and 4.5.
8. Whether MRL pays at deeper cuts, such as 64 of 768. Section 4.3.
9. hnswlib seed behaviour on Linux libstdc++. Phase 2.
10. That Lucene uses Elasticsearch's `num_candidates` as its candidate list, and OpenSearch's 2M layer-0 links. Section 2.5.
11. The Elasticsearch licence check in its plugin, `GET <index>/_settings` on a live cluster, and 8.x defaults. Section 3.6.
12. Weaviate's default filter strategy before 1.34. Section 3.6.
13. How hnswlib's per-element RAM overhead splits among its members. Section 2.2.
14. Whether bge-small's training data overlaps SciDocs. Section 1.3.
15. Whether real updates, which change the vector, strand more nodes than same-vector updates. Section 7.1.
16. Every timing on a quiet machine. All timings in the course came from a shared machine under load.

---

## Corrections Module 3 made

Later dossiers must not repeat these errors. The sources are `course.json` `notesForGeneration` and `reviewLog`, dated 2026-09-23. They also include the seven phase review reports and the coherence report in the study session's `scratchpad/reports/retrieval-internals_*`. `reviewLog` itself holds only three summary lines. The details are in the reports. Where the old dossier held the error, the dossier line is given.

### Rules the course kept from `notesForGeneration`

1. Say which recall you mean every time: ANN recall against exact search, or relevance recall against labels.
2. Never say "the default ef". Name the library and version.
3. State the Elasticsearch version with every Elasticsearch claim.
4. Do not copy the HF quantization blog's 768-dimension float32 storage rows. Section 4.4 says both print the size of 100 million vectors under a 250M heading.
5. MRL's "up to 14×" is an ImageNet result, not text retrieval.
6. ANN-Benchmarks is unmaintained. Use VIBE and Big-ANN.
7. PyPI hnswlib is 0.8.0 from 2023. Say which version a lab uses.
8. The RRF paper did not test dense retrieval.
9. Recompute contextual retrieval cost with current prices.
10. Every lab "A beats B" uses the paired test and says whether it is significant.
11. Re-read defaults in source at the current tag before quoting them.

### Errors that were in the old dossier

| Wrong claim | Correct claim | Where fixed | Evidence |
|---|---|---|---|
| RRF k = 60 lowered nDCG@10 below bge-small on SciFact, 0.6985. k = 1 beat k = 60 by 0.02 | That run used BM25 without a stemmer. With the harness's stemmed BM25, RRF k = 60 gives 0.7278, above bge-small, p = 0.156. k = 1 is only +0.0014, and no k differs significantly | 5.2 | dossier lines 163, 254 and 372. Re-run `rrf_sweep.py --dense bge-small`. Phase 5 generate report item 8 |
| BM25 nDCG@10 on SciFact is 0.6617 with bm25s 0.3.11 | 0.6617 is bm25s without the stemmer. The harness uses the English stemmer and gets 0.6863. BEIR's 0.665 came from Anserini with k1 0.9, b 0.4 and separate fields | 1.3 | dossier lines 163 and 246. Re-run `baseline.py`. `HARNESS.md` |
| Qdrant and Elasticsearch HNSW defaults, from docs only. Elasticsearch search list "per query" | Read in source: Qdrant's search list equals `ef_construct` 100, at least k. Elasticsearch `num_candidates` defaults to round(min(10,000, 1.5k)), 15 at k = 10 | 2.5 | dossier lines 84 and 88. Re-run `default_drift.py --table` |
| hnswlib memory from the layer-0 formula: 3,212 predicted against 3,220.7 measured | The layer-0 formula is incomplete. Add the upper lists with mean level 1/(M − 1), not the paper's mL. The full formula matches the saved file within 0.05% | 2.2 | dossier lines 76 and 248. Re-run `graph_memory.py --faiss` |
| all-MiniLM-L6-v2 kept 90.79% with int8 | Decoded int8 kept 99.6% to 100.2% in all 15 runs. The blog's int8 rows used a plain dot product. That link is inferred | 4.1 | dossier line 139. Re-run `quant_table.py` on SciFact |
| An MRL-trained model loses less when truncated to the same size | Loss followed dimensions left. mpnet without MRL kept 96.2% to 97.6% at 384 dims. MiniLM without MRL met mxbai-xs's card number | 4.3 | dossier lines 154 and 253. Phase 4 review item 1 |
| Drift-Adapter recovered 0.992 of the recall@10 of a full re-embed on 1M AG-News items | The ratio is agreement with the new model's exhaustive top 10, not labels. AG-News has 120,000 training items, so the stated 1M database is impossible as written. The Procrustes 0.974 did not reproduce: 0.652 on SciFact, 0.514 on AG-News. Every adapter scored below the old system on labels | 7.4 | dossier line 212. Re-run `model_upgrade.py --protocol` for SciFact |
| The unreachable count is non-decreasing on a fixed seed | Under random updates it moves up and down, 1.7 to 4.0. It grows only when unreachable nodes are never updated, Xiao et al.'s rule | 7.1 | dossier line 258. Phase 7 churn tables |
| The pgvector lab runs in Docker with pgvector 0.8.6 | No Docker. The course emulates 0.8.6 in Python and ran the SQL lab on PostgreSQL 14.24 with pgvector 0.8.1. 0.6.0 to 0.8.1 have CVE-2026-3172 | 3.2, E12 | dossier lines 233 and 251. Coherence report item 9 |
| Weaviate 1.39.5, LanceDB 0.38.0, turbopuffer client 2.9.0, Milvus 3.0.1 | On 2026-09-23: 1.39.6, 0.39.0, 2.10.1 and 3.0.2 | 3.6 | dossier lines 125 to 131 and 353 to 355. Phase 3 generate report |
| turbopuffer "p50=874ms for 1M documents" | The home page gives the same numbers for 10M documents. The two pages disagree. Treat them as an order of magnitude | 3.5 | dossier line 101. Phase 3 text |
| Anthropic's $1.02 assumes Claude 3 Haiku | The post names Claude 3 Haiku only for its prompt. The price model and the n-reads formula are inferred from arithmetic. Today the same workload costs $3.84 on Claude Haiku 4.5. Claude 3 Haiku was retired on 2026-04-20 | 6.5 | dossier line 195. Re-run `contextual_cost.py` |
| sentence-transformers notes: 0.1849 before and 0.6795 after the fix | The collapse reproduced, not the exact means: 0.1956 on 5.7.0 and 0.6224 on 6.1.0. The evaluator scored 17,165 pairs, not 15,040 | 5.5 | dossier lines 176 and 263. Phase 5 review item 11 |
| "The pilot" fused 30 Wumpus runs | Four pilots, each fusing 30 configurations on a different TREC collection. Table 1 is the first | 5.2 | dossier line 160. Phase 5 review item 9 |
| BEIR's cross-encoder "took 450 ms" | BEIR Table 3 calls it an estimated average latency | 5.3 | dossier line 171. Phase 5 review item 16 |

The Phase 1 generate report also says the dossier named Elasticsearch as the source of BEIR's BM25 row. `grep` finds no such line in the dossier. Not checked further.

### Errors in drafts or labs that a later module could repeat

| Wrong claim | Correct claim | Where fixed |
|---|---|---|
| The unpaired test found no significant slice | It found one slice of six, Holm p = 0.046 | Phase 1, 1.4 |
| The low-overlap slice at Holm p = 0.049 is 0.001 below 0.05 | Monte Carlo noise is about ±0.002. It is 0.046 with 1,000,000 patterns and 0.147 in a six-slice family. Borderline | Phase 1, 1.4 |
| The SciFact chunking gain is real at p = 0.038 | Borderline. p runs 0.035 to 0.045 over five test seeds | Phase 1, 1.1, coherence pass |
| hnswlib is 2.4 times slower than FAISS, and 4.4 times on SciFact | Timed in alternation: 1.5 times at 200,000 vectors and 3.5 times on SciFact. The first run timed indexes one after another under changing load | Phase 2, 2.4 |
| The hnswlib link-list header is a 4-byte count | A 2-byte count, a flag byte with 0x01 for deleted, one unused byte | Phase 2, 2.2 |
| Seeds 0, 1 and 2 give three graphs | On macOS seeds 0 and 1 give the same levels. Offset by 100 | Phases 2 and 7 |
| PQ 96 without re-ranking loses relevance significantly | Only one seed of three is significant | Phase 2, 2.3 |
| Resident set size measures an index's RAM | It went negative, −848 bytes per vector. Use peak memory footprint | Phase 2, 2.2 |
| Graph and cluster indexes gain little from batching | Not verified. Removed | Phase 2, 2.4 |
| The lab runs pgvector's scan line for line | A Python re-implementation, checked against the C source. Every pgvector number except E12 comes from it | Phase 3 intro |
| Crossover constants a = 178.4 ns and b = 7.365 µs | Those came from a fit whose intercepts were dropped. The log-space proportional fit gives 158.7 ns and 5.372 µs. The model is rough, within a factor of 3.45 | Phase 3, 3.3 |
| The default 20,000-tuple cap rarely ends a scan | At a 0.1% share, 56.5% of scans hit it | Phase 3, 3.2 |
| Elasticsearch's default follows the running version, and new segments switch | The version that created the index picks the default | Phase 3, 3.6 |
| DiskANN's +4 bytes and multi-sector rule are in the paper | They are in DiskANN's code at tag 0.7.0 | Phase 3, 3.5 |
| Truncation needs a model trained for it | Dimensions left decide the loss. The mpnet control shows it | Phase 4, 4.3 |
| gap/noise was tested on the runs it was chosen on | Five held-out runs, Spearman +0.90 | Phase 4, 4.1 |
| Sign bits on coordinate axes follow θ/π | True for four of five models. bge-small: 0.2536 against 0.2056 | Phase 4, 4.1 |
| Rotation alone lowered bge-small on SciFact | Not significant on SciFact, p = 0.084. Significant on NFCorpus and SciDocs | Phase 4, 4.5 |
| The lab's estimator is RaBitQ | It is `RaBitQLite`, a simpler version | Phase 4, 4.5 |
| A centered estimator that centers documents only | It must keep c · (x − c) exactly. The first version scored 0.6422, not 0.6796 | Phase 4, 4.5 |
| FAISS 1.14 and 1.15 added FastScan and multi-bit RaBitQ | FastScan came in 1.13.0 and multi-bit in 1.13.1 | Phase 4 references |
| The best reranker depth, picked on the test queries | Pick on the 809 train queries. The RRF claim held at +0.0361, p = 0.009 | Phase 5, 5.3 |
| Reranking falls from 0.7366 to 0.7262 with depth | Not significant on test, p = 0.229. Significant on the train queries | Phase 5, 5.3 |
| List weights matter more than k | Only one of six pairs gained significantly after Holm | Phase 5, 5.2 |
| ColBERT's 44.6 times holds at scale | About 6 times on MS MARCO. The ratio depends on document length and vector width | Phase 5, 5.4 |
| A per-query sigmoid gives 2,272 distinct scores | More than the 2,243 distinct logits. `torch.sigmoid` rounds by tensor length. Use `split_apply` | Phase 5, 5.5 |
| Chunk text is the same whatever `--models` lists first | The tokenizers decode differently. `CHUNK_TOKENIZER = "minilm"` now cuts every chunk | Phase 6, `bakeoff.py` |
| Two significant stand-in gains | After Holm over 18 runs: 0 gains and 2 losses | Phase 6, 6.1 |
| The two weaker retrievers gained from Qwen HyDE | Only BM25, after Holm across three retrievers | Phase 6, 6.1 |
| Four significant chunker results in 6.4 | Three in one family of 15 comparisons | Phase 6, 6.3 and 6.4 |
| A cache read is a tenth of the input price | True for Claude Haiku 4.5. Other models differ | Phase 6, 6.5 |
| Batch cost with 5-minute writes while advising the 1-hour tier | With 1-hour writes: $2.46 at 98% hits and $8.28 at 30% | Phase 6, 6.5 |
| Use an adapter when the models are close enough | No adapter beat the old system on labels. A perfect adapter gives the old system | Phase 7, 7.4. Phase 7 generate report |
| A timer rebuild bought 0.0001 ANN recall | After the seed fix it bought nothing: 0.9806 with and without | Phase 7, 7.2, coherence pass |

The reviews also fixed items that a later module is unlikely to repeat. They include anchor lines, self-test counts, download sizes, one wrong multiplier and some citation wording.

### Code line references that moved

Fixed on 2026-09-23: the phase text now cites the new lines below, and the three documents were republished. Before that fix, the phase text cited the old lines. The code had moved since. Verified with `sed -n` on 2026-09-23. The likely cause is the seed-offset and `titled` edits in the coherence pass. That cause is inferred.

| Cited in | Text says | Now |
|---|---|---|
| Phase 4, Check it yourself item 2 | `quant_table.py:101`, `angle_stats` | line 103 |
| Phase 6, 6.3 code block | `bakeoff.py:95`, `verdict` | line 99. Line 95 is `CHUNK_TOKENIZER` |
| Phase 6, Check it yourself item 2 | `bakeoff.py:252`, the Holm correction | line 266 |
| Phase 7, 7.3 code block and Check it yourself item 2 | `churn.py:118`, `Churner.round` | line 122 |
| Phase 7, 7.1 and Check it yourself item 1 | `hnsw_graph.py:174` `counts`, `:158` `edges` | lines 182 and 166 |

No phase states a correction to Module 1 or Module 2. Verified by `grep` for "inference-internals" and "context-engineering" next to "wrong", "correct", "error" and "mistake".

---

## Overlap guidance for later modules

- **Module 4, advanced retrieval.** Link to 5.1 and 5.2 for hybrid retrieval and 6.1 and 6.2 for rewrites. Link to 3.1 to 3.4 for filtered search. Module 4 owns routing, GraphRAG, retrieval without vectors, semantic caching and tenant isolation. Reuse `common/` and the module-question chain.
- **Module 5, ingestion.** 6.3 and 6.4 cover chunking and the effect of lost newlines. Module 5 owns parsing, OCR and page images, and stops where text becomes chunks.
- **Module 11, evals.** 1.2 to 1.5 and 7.5 give metrics, the paired test, Holm, sizing, intervals and one gate. Module 11 owns judges, golden sets, agreement between labellers and CI gates. Do not derive these numbers again.
- **Module 13, serving.** Module 3 encodes on one laptop GPU. Serving embedding models and rerankers at scale belongs to Module 13.
- **Module 14, cost.** 6.2, 6.5 and 5.3 price rewrites, contextual retrieval and hosted reranking per query or per token. Module 14 adds forecasting and ownership.
- **Module 15, observability.** Link to 3.1 for rows returned per LIMIT and 7.2 for probes A and B. Link to 5.5 for distinct scores and ties.
- **Module 16, security.** 7.3 shows where deleted bytes remain and cites inversion results. 3.1 shows tenant filters only as recall. Module 16 owns isolation and attacks.
- **Modules 17 and 18.** Faithfulness belongs to Modules 11 and 17. Right to erasure as a process belongs to Module 18, which can link to the 7.3 checklist.

The `_curriculum/README.md` status table lists Module 3 as "complete". Its Module 3 section still says "Status: ready." This file does not change either.

Summary: Module 3 shows how to find which retrieval stage fails for one customer, and how to measure and fix each stage. Link to its sections and import its harness instead of teaching them again.
