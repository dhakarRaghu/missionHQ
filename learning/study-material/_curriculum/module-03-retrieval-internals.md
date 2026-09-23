# Module 03 — Retrieval engineering internals

Research date: 2026-09-17. Status: research dossier, not course material.

## 1. What this module is for

This module teaches how the retrieval step of a RAG system works inside, and how to measure it. The learner already builds basic RAG. They have not yet looked inside the vector index, the quantized codes, the fusion step, or the metrics. Every knowledge-base answer in a support product depends on these parts. Without this module, a team cannot explain three common problems. A filtered query returns 4 rows instead of 10. Recall falls after a year of deletes. Nobody can say whether a new embedding model is better. Library defaults also differ widely. The same "HNSW" index has an `ef` search default of 10 in hnswlib, 16 in FAISS, and 40 in pgvector. Elasticsearch changed its default vector quantization twice between 9.0 and 9.4.

## 2. Scope

### In scope

- Approximate nearest-neighbour (ANN) index internals: HNSW, IVF, IVF-PQ, DiskANN or Vamana, ScaNN, and cluster indexes with in-place updates such as SPFresh.
- Recall, latency, and memory trade-offs, and how benchmarks measure them.
- What each vector library and database implements, with defaults read from source at a release tag.
- Embedding quantization: int8, binary, product quantization, RaBitQ and TurboQuant, Matryoshka truncation, and rescoring.
- Hybrid retrieval: BM25 with dense retrieval, reciprocal rank fusion, learned sparse retrieval, and rerankers.
- Query understanding: rewriting, HyDE, Query2doc, multi-query, and decomposition, with their measured effect.
- Chunking: fixed, recursive, semantic, late chunking, and contextual retrieval.
- Freshness: upserts, deletes, tombstones, unreachable nodes, and embedding model upgrades.
- Retrieval evals: recall@k, nDCG@10, MRR, BEIR, MTEB v2, and a labelled set built from real queries.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Agentic retrieval, GraphRAG, retrieval without vectors, routing | Module 4 |
| Multi-tenant index isolation and semantic caching | Module 4 |
| PDF parsing, OCR, ColPali page retrieval | Module 5 |
| Judges, golden sets, significance tests, CI gates | Module 11 |
| Faithfulness of the generated answer | Modules 11 and 17 |
| Right to erasure as a legal process | Module 18 |
| Serving the embedding model on a GPU cluster | Module 13 |

### Overlap with earlier modules

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Quantization of model weights | Module 1, 4.4 | Quantization of stored embeddings. It is a different operation with different error behaviour. |
| Prompt caching | Module 1, 3.2 and 3.3 | The cost of contextual retrieval depends on caching the whole document. Link, do not re-teach. |
| Small eval sets and paired tests | Module 1, 3.4 and 6.3. Module 11 dossier, phase 4. | Retrieval metrics and qrels. Module 11 lists recall@k and nDCG as belonging to "the retrieval modules". |
| Context length hurts even with perfect retrieval | Module 2 dossier, Du et al. | Why passing more chunks is not free. Link only. |
| Benchmark contamination | Module 11 dossier, phase 7 | MTEB and BEIR specific traps. |

## 3. What changed recently

| Change | Date | Source | Why it matters |
|---|---|---|---|
| Weaviate 1.33 adds `DEFAULT_QUANTIZATION` | 2025-09-25 | Weaviate compression docs, GitHub release | A server setting can quantize every new collection |
| MTEB 2.x line starts. Earliest 2.x on PyPI is 2.0.1. | 2025-10-20 | PyPI JSON | New `mteb.evaluate` API. v1 code breaks. |
| Weaviate 1.34 makes ACORN the default filter strategy | 2025-11-05 | Weaviate vector index docs, `config.go` at v1.39.5 | Filtered search behaviour changed without a schema change |
| Cohere Rerank 4.0, `pro` and `fast`, 32k context | 2025-12-11 | Cohere changelog source file | Context grew from 4k in v3.5 |
| Weaviate 1.36 adds HFresh, based on SPFresh | 2026-02-24 | Weaviate vector index docs | A cluster index with in-place updates |
| hnswlib 0.9.0 on GitHub only. PyPI still at 0.8.0 from 2023. | 2026-03-28 | GitHub releases, PyPI JSON | `pip install hnswlib` does not give the latest fixes |
| Elasticsearch 9.4 defaults float vectors to `bbq_disk` when licensed | 2026-05-05 | Elastic dense_vector docs, version badges | Same mapping, different index, by version and licence |
| Qdrant 1.18 adds TurboQuant | 2026-05-11 | Qdrant release notes and docs | Rotation-based quantization at 1 to 4 bits |
| pgvector 0.8.3 and 0.8.4 fix HNSW vacuum corruption | 2026-06-17, 2026-06-30 | pgvector CHANGELOG | Deletes plus vacuum had real bugs |
| "Ghost Vectors" paper on soft deletes | 2026-06-16 | arXiv 2606.18497 | Deleted vectors stay readable on disk |
| ANN-Benchmarks declared unmaintained. Points to VIBE. | 2026-07-10 commit | ann-benchmarks README | The most cited ANN chart is frozen. Its site was last modified 2024-12-09. |
| Milvus 3.0.0 | 2026-07-29 | GitHub release | Online schema backfill for model upgrades. FAISS index passthrough. |
| Qdrant 1.19: 4-bit TurboQuant as primary storage | 2026-08-05 | GitHub release | Originals no longer need to be kept |
| sentence-transformers 6.0 | 2026-08-18 | GitHub release | `MultiVectorEncoder` for ColBERT models. Fixes half-precision reranker scores. |
| "When Is Complex Chunking Worth It?" CIKM 2026 | 2026-08-17 | arXiv 2608.16586 | Contextual, semantic, and late chunking rarely win significantly |
| FAISS 1.15.1 | 2026-09-16 | PyPI, CHANGELOG | RaBitQ storage inside HNSW, deterministic HNSW build option |
| VIBE benchmark, DMLR 2026 | README current on 2026-09-14 | VIBE README, arXiv 2505.17810 | Modern embedding datasets and out-of-distribution queries |

## 4. Core concepts, with verified facts

### 4.1 HNSW: a layered proximity graph

HNSW stores each vector as a node with links to near neighbours. Upper layers hold few nodes and long links. Layer 0 holds every node. A search starts at the top, walks greedily down, and keeps a candidate list of size `ef` on layer 0. `M` sets links per node, so it sets memory. `efConstruction` sets build quality. `efSearch` sets the recall and latency point at query time.

- The level multiplier choice is `mL = 1/ln(M)`. Layer 0 allows `Mmax0 = 2·M` links. The authors write that 2·M "is a good choice for Mmax0". Source: Malkov and Yashunin, arXiv 1603.09320, section 4.1 and Fig. 6, measured on 5M SIFT vectors. Verified from raw text.
- Graph memory per element is "(Mmax0+mL ∙Mmax)∙bytes_per_link". Typical M from 6 to 48 gives "about 60-450 bytes per object", excluding the vector data. Source: same paper, section 4.2.3. Verified.
- hnswlib allocates layer 0 per element as `maxM0_ * sizeof(tableint) + sizeof(linklistsizeint)` plus the vector plus an 8-byte label. `maxM0_ = M_ * 2`. Source: hnswlib `hnswalg.h` lines 113 and 120 to 121, tag v0.9.0. Verified from source.
- Worked memory: M=16 and 768 dimensions gives 2·16·4 + 4 + 768·4 + 8 = 3,212 bytes per vector for layer 0. A saved hnswlib 0.8.0 index measured 3,220.7 bytes per vector for 100,000 random vectors. M=32 measured 3,348.3. Measured on the author's machine on 2026-09-17, Apple M4 Pro, Python 3.12. Verified by run. The vector itself is 3,072 of those bytes. So at 768 dimensions, quantizing the vector saves far more memory than lowering M.
- Defaults differ by library. Rows that name a file are verified from source at that tag. Rows marked "docs" are verified from docs only.

| Library, tag | M | build ef | search ef | File |
|---|---|---|---|---|
| hnswlib v0.9.0 | 16 | 200 | 10 | `hnswalg.h` lines 92, 93, 115 |
| FAISS v1.15.1 | 32 | 40 | 16 | `impl/HNSW.h` lines 141, 144, 197 |
| pgvector v0.8.6 | 16 | 64 | 40 | `src/hnsw.h` lines 54, 57, 60 |
| Qdrant docs, current | 16 | 100 | equals `ef_construct` | Qdrant indexing docs. Not checked in source. |
| Weaviate v1.39.5 | 32 | 128 | -1, dynamic between 100 and 500 | `entities/vectorindex/hnsw/config.go` lines 27 to 32 |
| OpenSearch k-NN 3.8.0.0 | 16 | 100 | 100 | `KNNSettings.java` lines 140 to 142 |
| Vespa v8.753.16 | 16 | 200 | set per query | `HnswIndexParams.java` lines 13 to 14 |
| Elasticsearch docs, current | 16 | 100 | `num_candidates` per query | dense_vector docs. Not checked in source. |

- hnswlib guidance: `M` from 12 to 48 "is ok for the most of the use cases". If recall at `ef = ef_construction` is below 0.9, build quality can improve. Source: hnswlib `ALGO_PARAMS.md` at v0.9.0. Verified.
- Laptop sweep: hnswlib 0.8.0, 100,000 synthetic 384-dimension vectors in 200 Gaussian clusters, `ef_construction` 200, one query thread. M=16 gave recall@10 of 0.728 at ef 10, 0.969 at ef 40, and 0.999 at ef 100. Latency was 0.072, 0.131, and 0.188 ms per query. Build took 5.9 s with 8 threads. Measured on Apple M4 Pro on 2026-09-17. Verified by run. The data is synthetic. Real embeddings will give other numbers.

### 4.2 IVF, IVF-PQ, and cluster indexes

IVF splits vectors into clusters with k-means. A query scans only the `nprobe` nearest clusters. Product quantization, or PQ, splits each vector into sub-vectors and stores a codebook index for each one. IVF-PQ combines both. SPFresh-style indexes keep clusters on disk and split or merge them as data changes.

- pgvector IVFFlat default `lists` is 100 and default `probes` is 1. Max lists is 32,768. Source: `src/ivfflat.h` lines 55 to 58 at v0.8.6. Verified. The README suggests `rows / 1000` lists up to 1M rows and `sqrt(rows)` above that, and `sqrt(lists)` probes. Verified.
- FAISS `IndexIVF` default `nprobe` is 1. Source: `faiss/IndexIVF.h` at v1.15.1, lines 69 and 105. Verified. So an untuned IVF index scans one cluster.
- LanceDB defaults `nprobes` to 20. IVF_PQ sub-vectors default to `dimension // 16`. LanceDB recommends IVF_RQ or IVF_PQ for filtered search, because IVF_HNSW variants "can show higher latency variance". Source: LanceDB vector index docs. Verified.
- SPFresh reports "only 1% of DRAM and less than 10% cores needed at the peak" compared with the state of the art, for a billion-scale disk index with updates. Source: Xu et al., arXiv 2410.14452, abstract. Verified from the abstract only. The workload tables were not read.
- turbopuffer states its vector indexes "are based on SPFresh". It auto-tunes for "90-100% recall". Cold queries read object storage, "p50=874ms for 1M documents". Warm queries show "p50=14ms". Source: turbopuffer architecture and vector docs. Verified. These are vendor numbers without hardware or dimension details.
- Weaviate HFresh "is a cluster-based vector index based on the SPFresh algorithm", added in v1.36. It supports only cosine and l2-squared. Source: Weaviate vector index docs. Verified.
- The laptop sweep also ran FAISS `IVF316,PQ48x8` on the synthetic set. Recall@10 stayed at 0.238 even at nprobe 32. PQ with 48 bytes lost most neighbours on this data. Verified by run. This is a teaching point: PQ without re-ranking can fail on tight clusters. It is not a general PQ result.
- The original PQ paper, Jégou, Douze, and Schmid, is hosted on HAL. The HAL page returned a bot-check page, not the PDF text. Not checked.

### 4.3 DiskANN, Vamana, and filtered search

DiskANN builds a Vamana graph with a pruning parameter alpha greater than 1. The graph lives on SSD. Compressed vectors live in RAM. FreshDiskANN adds real-time inserts and deletes. Filtered search is a separate hard problem, because a filter can remove most of a graph walk.

- DiskANN on SIFT1B serves "> 5000 queries a second with < 3ms mean latency and 95%+ 1-recall@1 on a 16 core machine" with "64GB RAM and an inexpensive solid-state drive". FAISS and IVFOADC+G+P at a similar memory footprint "plateau at around 50% 1-recall@1". Source: Subramanya et al., NeurIPS 2019 PDF, abstract. Verified from raw text.
- FreshDiskANN keeps "> 95% 5-recall@5" with "thousands of concurrent real-time inserts, deletes and searches per second". It claims a "5-10x reduction in the cost of maintaining freshness". Source: Singh et al., arXiv 2105.09613, abstract. Verified.
- ACORN reports "2–1,000× higher throughput at a fixed recall" than prior filtered methods. Source: Patel et al., arXiv 2403.04871, abstract. Verified from the abstract.
- pgvector applies filters after the index scan. With `hnsw.ef_search` 40 and a filter matching 10% of rows, "only 4 rows will match on average". Iterative scans since 0.8.0 continue up to `hnsw.max_scan_tuples`, default 20,000. Source: pgvector README at v0.8.6. Verified.
- Big-ANN NeurIPS'23 filtered track: the winner, ParlayANN, reached 37,671 QPS on the private queries at recall@10 of at least 0.9. The FAISS baseline reached 3,253. Machine: Azure D8lds_v5, 8 vCPUs, 16 GB RAM. Data: 10M YFCC vectors, 192 dimensions, uint8. Source: Simhadri et al., arXiv 2409.17424, Table 1 and Table 2, section 3. Verified.

### 4.4 What each system implements

| System | Current version | Index types relevant here | Source, label |
|---|---|---|---|
| FAISS | 1.15.1, 2026-09-16 | Flat, IVF, PQ, HNSW, RaBitQ, binary. `IndexHNSW` has no delete. | PyPI, CHANGELOG, `Index.cpp` line 57. Verified. |
| hnswlib | 0.9.0 on GitHub. 0.8.0 on PyPI. | HNSW with `markDelete` and optional slot reuse | GitHub releases, `hnswalg.h`. Verified. |
| pgvector | 0.8.6, 2026-07-29 | HNSW, IVFFlat. `vector` up to 2,000 dims indexed, `halfvec` 4,000, `bit` 64,000 | README and `hnsw.h`. Verified. |
| pgvectorscale | 0.9.1, 2026-09-04 | StreamingDiskANN index on pgvector types | GitHub release. Verified. |
| Qdrant | 1.19.1 | HNSW with payload-aware edges. Scalar, binary 1 to 2 bit, PQ, TurboQuant. | Docs, releases. Verified. |
| Weaviate | 1.39.5. 1.40.0-rc.0 on 2026-09-15. | HNSW, flat, dynamic, HFresh. PQ, SQ, BQ, RQ. | Docs, `config.go`. Verified. |
| Milvus | 3.0.1 and 2.6.24 | Many types. 3.0 adds a `FAISS` passthrough type. | GitHub release. Verified. Milvus docs site returned 302 and 502. Not checked. |
| LanceDB | lancedb 0.38.0 on PyPI | IVF_PQ, IVF_RQ, IVF_HNSW_SQ, IVF_HNSW_FLAT | Docs, PyPI. Verified. |
| Elasticsearch | 9.5.4 and 9.4.7 | HNSW with int8, int4, BBQ. `bbq_disk` needs an Enterprise subscription. | dense_vector docs. Verified. |
| OpenSearch | 3.8.0 | Default engine FAISS. NMSLIB deprecated since 2.19.0. | `KNNEngine.java` lines 34 to 46. Verified. |
| Vespa | 8.753.16 | HNSW per tensor field | Source. Verified. |
| turbopuffer | client 2.9.0 | SPFresh-based index on object storage | Docs. Verified. Server version not public. |

- Elasticsearch default quantization by version: 9.0 uses `int8_hnsw`. 9.1 uses `bbq_hnsw` for 384 or more dimensions and `int8_hnsw` below that. 9.4 uses `bbq_disk` "when available under the current license". Source: Elastic dense_vector docs, read from the version badges in raw HTML. Verified. Elastic keeps raw floats on disk too, which adds "~25% for int8, ~12.5% for int4, and ~3.1% for bbq". Verified.

### 4.5 Embedding quantization and rescoring

Quantization stores each embedding with fewer bits. Int8 keeps 8 bits per dimension. Binary keeps the sign bit. PQ keeps codebook indexes. RaBitQ and TurboQuant rotate vectors randomly before quantizing, which spreads information across dimensions. Rescoring retrieves extra candidates with the small codes, then re-scores them with fuller vectors.

- Hugging Face and Mixedbread, March 2024: on the 15 retrieval tasks of MTEB, `mxbai-embed-large-v1` kept 96.45% of float32 nDCG@10 with binary codes plus rescoring, and 92.53% without rescoring. `e5-base-v2` kept only 74.77% with binary codes. `all-MiniLM-L6-v2` kept 93.79% with binary and 90.79% with int8. Setup: top 100 with `rescore_multiplier` 4. Source: HF embedding quantization blog, results table and "Binary Rescoring". Verified from raw HTML.
- The same blog reports mean speedups of 3.66x for int8 and 24.76x for binary. Conditions: exact search on CPU, GCP a2-highgpu-4g, int8 with USearch 2.9.2, binary with FAISS 1.8.0. The two methods used different libraries. So the speedup ratio mixes library and method. Verified.
- The blog table lists 286.10 GB for 250M float32 embeddings at 768 dimensions. 250M × 768 × 4 bytes is 715.26 GiB. The 1024-dimension row, 953.67 GB, is correct. Inferred from arithmetic. Do not copy the 768-dimension row.
- Qdrant docs: binary quantization gave "0.98 recall@100 with 4x oversampling" on OpenAI `text-embedding-ada-002`, 1536 dimensions, dbpedia. They say binary "is only efficient for high-dimensional vectors". 2-bit gives 16x compression and 1.5-bit gives 24x. Source: Qdrant quantization docs. Verified. Vendor numbers.
- Qdrant says "4-bit TurboQuant, at twice the compression ratio of scalar quantization, delivers similar recall and speed", and that results vary by dataset. Source: Qdrant quantization docs. Verified as a vendor claim. No table on the page.
- TurboQuant proves distortion within "a small constant (≈ 2.7) factor" of the lower bound. Source: Zandieh et al., Google Research, arXiv 2504.19874, abstract. Verified.
- RaBitQ quantizes D-dimensional vectors into D-bit strings with a theoretical error bound. The authors say PQ variants "fail disastrously on some real-world datasets". Source: Gao and Long, SIGMOD 2024, arXiv 2405.12497, abstract. Verified.
- Matryoshka Representation Learning, or MRL, trains a model so that the first n dimensions work alone. Its "up to 14×" claims are for ImageNet classification and image retrieval. Source: Kusupati et al., arXiv 2205.13147, abstract and section 4. Verified. The headline is not a text-retrieval number.
- Laptop check, BEIR SciFact test set, 5,183 documents, 300 queries, exact search. Measured on Apple M4 Pro on 2026-09-17 with sentence-transformers 6.0.1, torch 2.14.0, FAISS 1.15.1. Verified by run.

| Model | float32 nDCG@10 | int8 | binary, no rescore | binary, 40 candidates, float rescore | first half of dims | first quarter of dims |
|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2, 22.7M params, 384 dims | 0.6451 | 0.6442 | 0.5881 | 0.6390 | 0.6143 | 0.5533 |
| bge-small-en-v1.5, 33.4M params, 384 dims | 0.7127 | 0.7128 | 0.6258 | 0.6917 | 0.6732 | 0.5805 |

  Neither model was trained with MRL. So the truncation columns show the loss without MRL training. One dataset and 300 queries give wide intervals. No significance test was run.

### 4.6 Hybrid retrieval and reciprocal rank fusion

Hybrid retrieval runs a lexical retriever such as BM25 and a dense retriever, then merges the lists. Reciprocal rank fusion, or RRF, scores each document by the sum of 1/(k + rank) over the lists. It uses ranks, not raw scores, so the two scales do not need calibration.

- The RRF formula uses "k = 60 was fixed during a pilot investigation". The pilot fused 30 Wumpus runs on TREC topics 351 to 400. MAP moved from 0.2123 at k=10 to 0.2147 at k=80. k=0 gave 0.2072 and k=500 gave 0.2098. The authors say the choice "was not critical". Source: Cormack, Clarke, and Büttcher, SIGIR 2009, section 2 and Table 1. Verified from the PDF. The paper fused lexical and learning-to-rank runs from 2009. It did not test dense retrievers.
- Elasticsearch `rank_constant` defaults to 60. `rank_window_size` defaults to the `size` parameter. Source: Elastic RRF docs. Verified.
- MTEB 2.16 added `HybridSearch` with `fusion_strategy="rrf"`. Source: MTEB "What's New". Verified.
- Laptop check on SciFact: BM25 with bm25s 0.3.11 gave nDCG@10 0.6617. MiniLM gave 0.6451. RRF with k=60 gave 0.6823. RRF with k=1 gave 0.7044. With bge-small, dense gave 0.7127, RRF k=60 gave 0.6985, and RRF k=1 gave 0.7246. Recall@100 rose from 0.9417 dense to 0.9650 fused. Verified by run, same conditions as 4.5. So RRF at k=60 lowered nDCG@10 below the stronger single retriever on this dataset. Recall@100 still improved.
- SPLADE v2 reports "more than 9% gains on NDCG@10 on TREC DL 2019" over the first SPLADE. Source: Formal et al., arXiv 2109.10086, abstract. Verified.
- Milvus 3.0 claims its compressed BM25 index is "roughly 3x smaller than the 2.6 sparse index at comparable recall". Source: Milvus v3.0.0 release notes, "internal benchmarks". Verified as a vendor claim without conditions.

### 4.7 Rerankers and late interaction

A cross-encoder reads the query and one document together and outputs a score. It is accurate and slow, so it only reranks a short list. ColBERT keeps one vector per token and scores with MaxSim, the sum over query tokens of the best-matching document token. That is cheaper than a cross-encoder and larger than a single vector.

- BEIR: BM25 plus a MiniLM-L6 cross-encoder reranking the top 100 scored 11% above BM25 on average over the zero-shot datasets. It took 450 ms on a V100 GPU and 6,100 ms on an 8-core Xeon Platinum 8168 per query. TAS-B dense retrieval took 14 ms on GPU with exact search. Corpus: 1M DBPedia documents. Source: Thakur et al., arXiv 2104.08663, Table 2 and Table 3. Verified.
- ColBERT as a reranker gives "over 170× speedup" and "14,000× fewer FLOPs" than BERT-based rerankers. Source: Khattab and Zaharia, arXiv 2004.12832, section 1. Verified. Hardware: Tesla V100, from section 4.
- ColBERTv2 stores MS MARCO in 16 GiB at 1 bit or 25 GiB at 2 bits per dimension. Vanilla ColBERT needed 154 GiB. Source: Santhanam et al., arXiv 2112.01488, section 5.3. Verified.
- Cohere Rerank 4.0 has `pro` and `fast` variants and a 32k context. Released 2025-12-11. v3.5 has 4,096 tokens. Source: Cohere changelog, models page, and GitHub source file. Verified. A request may hold at most 10,000 documents times `max_chunks_per_doc`. Source: Cohere reranking best practices. Verified. Cohere publishes no latency numbers on these pages. Not checked.
- Anthropic used the top 150 candidates, reranked with Cohere, and kept the top 20. Source: Anthropic contextual retrieval post. Verified.
- sentence-transformers 6.0 found that bfloat16 cross-encoders with a sigmoid had "essentially randomized" rankings before v6. On `cross-encoder/ettin-reranker-32m-v1` over three NanoBEIR datasets with 100 candidates, mean nDCG@10 was 0.1849 in v5.7.0 and 0.6795 in v6.0.0. Source: sentence-transformers v6.0.0 release notes. Verified.
- sentence-transformers 6.0 adds `MultiVectorEncoder`, which loads PyLate and Stanford ColBERT checkpoints. Source: same release notes. Verified.

### 4.8 Query understanding

Query rewriting changes the user text before retrieval. HyDE asks an LLM to write a fake answer and embeds that. Query2doc appends a generated passage to the query. Multi-query sends several rewrites and fuses the results. The measured gains are real but depend on the baseline and cost an LLM call.

- HyDE with InstructGPT `text-davinci-003` and unsupervised Contriever: nDCG@10 went from 44.5 to 61.3 on TREC DL19 and from 42.1 to 57.9 on DL20. Contriever fine-tuned on MS MARCO scored 62.1 and 63.2 without HyDE. Source: Gao et al., arXiv 2212.10496, Table 1. Verified. So HyDE helps a weak zero-shot retriever most. It does not beat a supervised one on DL20.
- Query2doc with `text-davinci-003`: BM25 nDCG@10 on DL19 went from 51.2 to 66.2. For the strong E5-base+KD retriever, MS MARCO dev MRR@10 went from 40.7 to 41.5. Source: Wang et al., arXiv 2303.07678, Table 1. Verified. Zero-shot, it lowered SciFact nDCG@10 by 2.9 for both SimLM and E5. Source: Table 2. Verified.
- Query2doc latency: BM25 search took 16 ms. With query2doc, the LLM call took more than 2,000 ms and search took 177 ms. Source: Table 6, single thread, top 100, MS MARCO dev. Verified.
- Rewrite-Retrieve-Read used ChatGPT as reader and a web search engine as retriever. On HotpotQA, plain retrieval lowered exact match from 32.36 to 30.47. An LLM rewriter gave 32.80. Source: Ma et al., arXiv 2305.14283, Table 2. Verified. Gains elsewhere were 0.6 to 2.8 exact match points.
- RAG-Fusion at Infineon used human grading of answers and reported no retrieval metric. It was "nearly 1.77 times as slow", 34.62 s against 19.52 s. Source: Rackauckas, arXiv 2402.03367. Verified. This is weak evidence for multi-query.
- The research found no controlled study of query decomposition for single-hop support questions. Not checked further.

### 4.9 Chunking

Chunking splits documents before embedding. Fixed chunking cuts every N tokens. Recursive chunking cuts at paragraph, then line, then sentence breaks. Semantic chunking cuts where sentence embeddings change. Late chunking embeds the whole document first and pools token vectors per chunk. Contextual retrieval prepends an LLM-written summary of where the chunk sits in its document.

- Anthropic, 2024-09-19: contextual embeddings cut top-20 retrieval failure from 5.7% to 3.7%, a 35% reduction. Adding contextual BM25 gave 2.9%, 49%. Adding reranking gave 1.9%, 67%. Metric: 1 minus recall@20. Embedding: Gemini Text 004. Domains: codebases, fiction, ArXiv papers, science papers. Source: Anthropic engineering post. Verified. The per-dataset appendix is in images and was not read.
- Anthropic's cost estimate is "$1.02 per million document tokens", assuming 800-token chunks, 8k-token documents, and Claude 3 Haiku with prompt caching. Verified. The price is from 2024 and the model is old. Recompute before quoting.
- Caspari et al., CIKM 2026, compared eight methods on CoRE and KILT at up to 6M documents with Qwen3-0.6B, embeddinggemma-300M, and Snowflake-L v2 embeddings. They used Fisher randomization tests with Bonferroni correction. "semantic chunking, summary-only indexing, contextual chunking, and late chunking rarely achieve significant wins over simpler baselines." Source: arXiv 2608.16586, section 4. Verified. Contextual chunking processed 0.26 documents per second at 100 generated tokens per second. Table 3. Verified.
- Late chunking averaged 1.8 nDCG@10 points absolute over naive fixed 256-token chunks, across three models and four BEIR datasets. Source: Günther et al., Jina AI, arXiv 2409.04701, Table 2. Verified. The same paper says late chunking "is not useful" on needle-style synthetic tasks. Verified.
- Vectara: on non-stitched document retrieval, fixed-size chunking beat both semantic chunkers on HotpotQA, MS MARCO, ConditionalQA, and Qasper. Semantic chunking won on artificially stitched documents. Embedding: `stella_en_1.5B_v5`. Source: Qu et al., arXiv 2410.13070, Table 1. Verified.
- Chroma, July 2024: LLM-based chunking had the highest token-level recall, 0.919. Standard deviations were near ±0.3. Setup: 5 retrieved chunks, `text-embedding-3-large`, a small generated dataset. Chroma changed LangChain's default separators to get fair results. Source: Chroma research report. Verified.

### 4.10 Freshness: updates, deletes, and model upgrades

Graph indexes do not delete well. Most systems mark a node as deleted, called a tombstone, and skip it at query time. Cleanup rebuilds links later. Replacing deleted slots can leave nodes with no incoming links. Changing the embedding model makes every stored vector incompatible.

- hnswlib uses `markDelete`. With `allow_replace_deleted`, new items reuse deleted slots. Source: `hnswalg.h` lines 68, 852, 954 at v0.9.0. Verified.
- Xiao et al. deleted and reinserted 5% of SIFT1M per iteration with hnswlib's replaced update. After about 3,000 iterations, 3% to 4% of points were unreachable, and recall fell by about 3%. Raising `ef` did not fix it. Source: arXiv 2407.07871, section III.B and Fig. 3. Verified.
- FAISS `IndexHNSW` does not override `remove_ids`. The base class throws "remove_ids not implemented for this type of index". Source: `faiss/Index.cpp` line 57 at v1.15.1, and no `remove_ids` in `IndexHNSW.cpp`. Verified from source, not run.
- Weaviate cleans tombstones every `cleanupIntervalSeconds`, default 300. Source: `config.go` line 26 at v1.39.5. Verified. Its docs suggest 1M minimum and 10M maximum deletions per cycle for 300M objects per shard. Verified.
- Qdrant's optimizer vacuums a segment when 20% of its records are deleted and it holds at least 1,000 vectors. Source: Qdrant optimizer docs. Verified.
- pgvector 0.8.3 "Fixed possible index corruption with HNSW vacuuming". 0.8.4 fixed a "hnsw graph not repaired" error. Source: CHANGELOG. Verified.
- Ghost Vectors: soft-deleted vectors stayed readable in ChromaDB, FAISS, and Weaviate files. Vec2Text recovered 25.5% of exact person names from deleted Wikipedia biography embeddings. Source: Chakraborttii et al., arXiv 2606.18497, abstract and section I. Verified. One preprint, not peer reviewed.
- Drift-Adapter maps new-model queries into the old embedding space. For MiniLM to MPNet on 1M AG-News items, an MLP adapter recovered 0.992 of the recall@10 of a full re-embed and added 8.0 µs per query. For GloVe to MPNet, it recovered only 0.715. Source: Vejendla, EMNLP 2025, arXiv 2509.23471, Tables 1, 3, 4. Verified. The downtime and GPU-hour figures in Table 3 are marked as estimates.
- Milvus 3.0 supports adding and backfilling a column while serving. The notes describe an embedding upgrade over "hundreds of millions of rows" as "a hot path with no downtime". Source: Milvus 3.0.0 release notes. Verified as a vendor claim.

### 4.11 Retrieval evals

Recall@k is the share of relevant documents found in the top k. nDCG@10 rewards relevant documents near the top, with a log discount. MRR is the mean of 1 over the rank of the first relevant document. For ANN tuning, "recall" means something else: overlap with the exact nearest neighbours, not with human labels.

- Big-ANN defines k-recall@k' as the overlap of the returned set with the true k nearest neighbours, divided by k. Source: arXiv 2409.17424, section 3.1. Verified. This is ANN recall, measured against exact search.
- BEIR has 18 datasets across 9 task types. Its finding: "BM25 is a robust baseline", and reranking and late interaction score best zero-shot "at high computational costs". Source: arXiv 2104.08663, abstract. Verified.
- MTEB v1 had 8 task types and 58 datasets. Source: arXiv 2210.07316, abstract. Verified. MMTEB covers "over 500" tasks in "250+ languages". Source: arXiv 2502.13595, abstract. Verified.
- In mteb 2.21.0, `MTEB(eng, v2)` has 41 tasks, 10 of them retrieval. `MTEB(eng, v1)` has 56 tasks with 15 retrieval. `MTEB(Multilingual, v2)` has 131 tasks with 18 retrieval. Verified by running `mteb.get_benchmark` on 2026-09-17.
- mteb 2.12 added int8 evaluation through `CompressionWrapper`. 2.11 added Matryoshka support. Source: MTEB "What's New". Verified.
- ANN-Benchmarks README now says it "is no longer actively maintained". The site's last-modified header is 2024-12-09. Source: GitHub README and HTTP headers. Verified.
- VIBE evaluates 22 implementations on 11 in-distribution and 8 out-of-distribution datasets. The best methods "use various forms of quantization". General methods "deteriorate significantly on OOD queries". Hardware: Xeon Gold 6230, one core. Source: arXiv 2505.17810 and VIBE README. Verified. A search result summary said 21 implementations and 12 plus 6 datasets. That matches an older version, not the current PDF.

## 5. Proposed phase outline

| Phase | Title | What it teaches | Labs it needs | Runs where, costs what |
|---|---|---|---|---|
| 1 | Measuring retrieval | qrels, recall@k, nDCG@10, MRR, ANN recall versus relevance recall, BEIR and MTEB v2, building a labelled set from real queries | L1, L2 | Laptop, offline. SciFact downloads 5,183 documents. |
| 2 | Inside HNSW and IVF | graph layers, M, ef, memory math, IVF lists and probes, PQ, defaults per library | L3, L4, L5 | Laptop, 1 to 5 minutes per sweep |
| 3 | Disk, filters, and databases | DiskANN and SPFresh ideas, filtered search failure, pgvector iterative scans, choosing a system | L6, L7 | Laptop. Postgres in Docker for L7. |
| 4 | Quantization and rescoring | int8, binary, 2-bit, PQ, RaBitQ and TurboQuant ideas, MRL truncation, oversampling | L8, L9 | Laptop, under 3 minutes with small models |
| 5 | Hybrid, fusion, and reranking | BM25, RRF and its k, SPLADE, cross-encoders, ColBERT, reranker latency, half-precision trap | L10, L11 | Laptop. Optional Cohere call under $0.10. |
| 6 | Queries and chunks | HyDE, Query2doc, multi-query cost, chunking methods and their evidence, contextual retrieval cost | L12, L13 | Laptop with a local LLM via Ollama, or an optional API run under $1 |
| 7 | Freshness and change | tombstones, unreachable nodes, vacuum, soft-delete leakage, model upgrades and adapters | L14, L15 | Laptop, offline |

Seven phases, because nearly all of this is new. Module 1 covers weight quantization and caching, and Module 11 covers significance tests. Neither covers index internals, retrieval metrics, fusion, or chunking. Phase 1 comes first so that every later phase measures with the same harness. Phases 6 and 7 could merge into one if the course needs to be shorter. The evidence for query rewriting is thin, so it does not need a full phase alone.

## 6. Lab ideas

All labs run offline after a one-time download, unless marked. Timings are from the author's Apple M4 Pro on 2026-09-17. They are not a promise for other laptops.

1. **L1 — Metric calculator with a known answer.** Compute recall@k, nDCG@10, and MRR for hand-made runs. Prints a table. Break it: use `min(k, relevant)` wrongly in IDCG. Self-test: a fixed run with known nDCG, for example relevant at ranks 1 and 3 with two relevant documents gives about 0.920.
2. **L2 — SciFact baseline harness.** Load `mteb/scifact`, run BM25 and one dense model, print nDCG@10 and recall@100. Measured: BM25 0.6617 and MiniLM 0.6451, 137 s total with two models. Break it: evaluate on the train qrels. Self-test: BM25 nDCG@10 within ±0.01 of 0.662 with bm25s 0.3.11.
3. **L3 — HNSW sweep.** hnswlib over M in {8, 16, 32} and ef in {10, 40, 100, 400}. Prints recall@10, ms per query, build time. Measured build 3.8 to 8.0 s for 100k × 384. Break it: leave ef at hnswlib's default of 10. Self-test: recall rises with ef for each M.
4. **L4 — Memory from code.** Predict hnswlib bytes per vector from the layer-0 formula, then save the index and compare. Measured 3,220.7 against 3,212 predicted. Self-test: within 1%.
5. **L5 — Default drift table.** A script prints the documented defaults per library and runs FAISS HNSW with `efSearch` 16 against hnswlib with ef 10 and 40. Self-test: the printed defaults match a pinned JSON file.
6. **L6 — Filter starvation.** Filter to 10% of rows after an HNSW top-40 search. Count results returned. Then widen the candidate list. Self-test: mean results near 4, as pgvector's README predicts.
7. **L7 — pgvector iterative scan.** Docker Postgres with pgvector 0.8.6. Compare row counts with `hnsw.iterative_scan` off and `strict_order`. Self-test: the iterative scan returns the full LIMIT.
8. **L8 — Quantization table.** int8, binary, and binary with rescore on SciFact for two small models. Measured values are in section 4.5. Break it: rescore the binary candidates with binary scores. Self-test: float rescoring of 40 candidates beats no rescoring.
9. **L9 — Truncation without MRL.** Truncate a non-MRL model to half and a quarter of its dimensions, then repeat with an MRL-trained model such as `nomic-embed-text-v1.5`. Self-test: the MRL model loses less at the same size. Not yet run for the MRL model.
10. **L10 — RRF k sweep.** Fuse BM25 and dense runs with k in {1, 10, 60, 200}. Measured: k=60 below the best single retriever on nDCG@10 for bge-small, but higher recall@100. Self-test: a paired randomization test across 300 queries, reusing Module 11 code.
11. **L11 — Reranker precision trap.** Rerank the top 100 with a small cross-encoder in float32 and bfloat16. Count distinct scores. Self-test: float32 gives more distinct scores than bfloat16. Run on the MPS device or CPU.
12. **L12 — HyDE on a weak retriever.** Use a local 1B to 3B model through Ollama to write fake answers. Compare against the plain query. Optional API run with a small model costs under $0.50 for 300 queries at current small-model prices. Not checked against current prices.
13. **L13 — Chunking bake-off.** Fixed, recursive, and semantic chunking on a small long-document set, with a paired test. Self-test: report "no significant difference" when the p-value is above 0.05.
14. **L14 — Tombstone churn.** Delete and reinsert 5% of vectors per round with `allow_replace_deleted`. Count nodes with no incoming links and track recall. Self-test: unreachable count is non-decreasing on the fixed seed.
15. **L15 — Model upgrade adapter.** Fit an orthogonal Procrustes map from MiniLM space to bge-small space on 2,000 pairs. Query the old index with mapped new queries. Self-test: adapted recall is above the unadapted baseline. The dimensions match at 384, which makes Procrustes simple.

## 7. Failure stories and case studies

- **Half-precision rerankers ranked almost at random.** Before sentence-transformers 6.0, a bfloat16 cross-encoder with a sigmoid collapsed top scores into ties. NanoMSMARCO nDCG@10 was 0.0965 before the fix and 0.7093 after. Source: sentence-transformers v6.0.0 release notes. Verified. Condition: `ettin-reranker-32m-v1`, 100 candidates.
- **HNSW vacuum corruption in pgvector.** Versions before 0.8.3 could corrupt an HNSW index during vacuum. Source: pgvector CHANGELOG. Verified. The research found no public postmortem with user impact.
- **pgvectorscale silent out-of-bounds reads.** DiskANN indexes built on columns without a `vector(N)` typmod "were silently reading out of bounds before" 0.9.1. They must be dropped and rebuilt. Source: pgvectorscale 0.9.1 release notes. Verified.
- **Filtered queries return too few rows.** pgvector documents that post-filtering at the default `ef_search` returns about 4 rows for a 10% filter. Source: README. Verified. This is a documented behaviour, not an incident.
- **Unreachable points after churn.** 3% to 4% of SIFT1M points became unreachable after 3,000 delete and reinsert rounds in hnswlib. Source: arXiv 2407.07871. Verified.
- **Deleted data still recoverable.** Soft deletes in three HNSW stores left embeddings that Vec2Text partly inverted. Source: arXiv 2606.18497. Verified. Preprint.
- **Retrieval that hurts.** On HotpotQA, adding web retrieval lowered ChatGPT exact match from 32.36 to 30.47. Source: arXiv 2305.14283, Table 2. Verified.
- **Missing public postmortems.** The research found no first-party postmortem of a production recall drop after an embedding model change. Blog posts describe such incidents without a named company or data. Those posts are not cited.

## 8. Primary sources

All fetched 2026-09-17. Status is the HTTP status of the final URL after redirects. PDFs were read by text extraction with pypdf 6.18.1.

### ANN algorithms and benchmarks

- **Efficient and robust approximate nearest neighbor search using HNSW graphs, Malkov and Yashunin, IEEE TPAMI 2018** — https://arxiv.org/abs/1603.09320, 200. Focus on: 4.1 parameter choice, Fig. 6, 4.2.3 memory. Why: the mechanism and the memory formula.
- **DiskANN, Subramanya et al., NeurIPS 2019** — https://proceedings.neurips.cc/paper_files/paper/2019/file/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Paper.pdf, 200. Focus on: abstract, Algorithm 2 RobustPrune. Why: SSD-based graph search.
- **FreshDiskANN, Singh et al., Microsoft Research, 2021** — https://arxiv.org/abs/2105.09613, 200. Focus on: abstract, delete policy. Why: streaming updates on a graph.
- **SPFresh, Xu et al., SOSP 2023** — https://arxiv.org/abs/2410.14452, 200. Focus on: LIRE protocol. Why: the base of turbopuffer and Weaviate HFresh.
- **ScaNN: Anisotropic Vector Quantization, Guo et al., Google, ICML 2020** — https://arxiv.org/abs/1908.10396, 200. Focus on: the loss function. Why: the ScaNN idea. No numbers taken.
- **ACORN, Patel et al., Stanford, SIGMOD 2024** — https://arxiv.org/abs/2403.04871, 200. Focus on: predicate subgraph traversal. Why: Weaviate's default filter strategy.
- **Results of the Big ANN NeurIPS'23 competition, Simhadri et al., 2024** — https://arxiv.org/abs/2409.17424, 200. Also https://big-ann-benchmarks.com/neurips23.html, 200. Focus on: 3.1 metrics, Tables 1 to 4. Why: filtered, OOD, sparse, and streaming results on fixed hardware.
- **VIBE, Jääsaari et al., DMLR 2026** — https://arxiv.org/abs/2505.17810, 200. Repo https://github.com/vector-index-bench/vibe, 200. Focus on: key findings, Figures 7 and 8. Why: the maintained successor to ANN-Benchmarks.
- **ANN-Benchmarks** — https://ann-benchmarks.com/, 200. Repo https://github.com/erikbern/ann-benchmarks, 200. Focus on: the README maintenance note. Why: learners will find these charts. They must know the charts are frozen.

### Quantization

- **Embedding Quantization, Hugging Face and Mixedbread, 2024** — https://huggingface.co/blog/embedding-quantization, 200. Focus on: results table, rescoring, speed table. Why: the only public multi-model table. Note the arithmetic error in one row.
- **RaBitQ, Gao and Long, SIGMOD 2024** — https://arxiv.org/abs/2405.12497, 200. Why: now in FAISS and LanceDB.
- **TurboQuant, Zandieh et al., Google Research, 2025** — https://arxiv.org/abs/2504.19874, 200. Why: now in Qdrant.
- **Matryoshka Representation Learning, Kusupati et al., NeurIPS 2022** — https://arxiv.org/abs/2205.13147, 200. Focus on: section 4. Why: the source of truncatable embeddings. Its numbers are image numbers.
- **Qdrant quantization docs** — https://qdrant.tech/documentation/manage-data/quantization/, 200.
- **Weaviate compression docs** — https://docs.weaviate.io/weaviate/configuration/compression, 200.

### Systems docs and source

- **pgvector README, CHANGELOG, hnsw.h at v0.8.6** — https://github.com/pgvector/pgvector/blob/v0.8.6/README.md, https://github.com/pgvector/pgvector/blob/v0.8.6/CHANGELOG.md, https://github.com/pgvector/pgvector/blob/v0.8.6/src/hnsw.h, all 200.
- **hnswlib ALGO_PARAMS.md and hnswalg.h at v0.9.0** — https://github.com/nmslib/hnswlib/blob/v0.9.0/ALGO_PARAMS.md, https://github.com/nmslib/hnswlib/blob/v0.9.0/hnswlib/hnswalg.h, both 200.
- **FAISS HNSW.h, Index.cpp, CHANGELOG at v1.15.1** — https://github.com/facebookresearch/faiss/blob/v1.15.1/faiss/impl/HNSW.h, https://github.com/facebookresearch/faiss/blob/v1.15.1/faiss/Index.cpp, https://github.com/facebookresearch/faiss/blob/v1.15.1/CHANGELOG.md, all 200.
- **Weaviate HNSW config at v1.39.5** — https://github.com/weaviate/weaviate/blob/v1.39.5/entities/vectorindex/hnsw/config.go, 200. **Weaviate vector index docs** — https://docs.weaviate.io/weaviate/config-refs/indexing/vector-index, 200.
- **OpenSearch k-NN source at 3.8.0.0** — https://github.com/opensearch-project/k-NN/blob/3.8.0.0/src/main/java/org/opensearch/knn/index/KNNSettings.java and https://github.com/opensearch-project/k-NN/blob/3.8.0.0/src/main/java/org/opensearch/knn/index/engine/KNNEngine.java, both 200. **OpenSearch knn_vector docs** — https://docs.opensearch.org/latest/mappings/supported-field-types/knn-vector/, 200.
- **Vespa HnswIndexParams.java at v8.753.16** — https://github.com/vespa-engine/vespa/blob/v8.753.16/config-model/src/main/java/com/yahoo/schema/document/HnswIndexParams.java, 200. **Vespa ANN docs** — https://docs.vespa.ai/en/querying/approximate-nn-hnsw.html, 200.
- **Qdrant indexing and optimizer docs** — https://qdrant.tech/documentation/manage-data/indexing/, https://qdrant.tech/documentation/ops-optimization/optimizer/, both 200. **Qdrant releases** — https://github.com/qdrant/qdrant/releases/tag/v1.18.0 and https://github.com/qdrant/qdrant/releases/tag/v1.19.0, both 200.
- **Elasticsearch dense_vector and RRF docs** — https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector and https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion, both 200.
- **LanceDB vector index docs** — https://docs.lancedb.com/indexing/vector-index, 200.
- **turbopuffer architecture and vector docs** — https://turbopuffer.com/docs/architecture and https://turbopuffer.com/docs/vector, both 200.
- **Milvus 3.0.0 release** — https://github.com/milvus-io/milvus/releases/tag/v3.0.0, 200. **Milvus index docs** — https://milvus.io/docs/index-explained.md, 302 then 403 or 502. Not read.
- **pgvectorscale 0.9.1 release** — https://github.com/timescale/pgvectorscale/releases/tag/0.9.1, 200.

### Hybrid, rerankers, queries

- **Reciprocal Rank Fusion, Cormack, Clarke, Büttcher, SIGIR 2009** — https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf, 200. The old `plg.uwaterloo.ca` URL redirects here. Focus on: Table 1.
- **SPLADE v2, Formal et al., Naver Labs, 2021** — https://arxiv.org/abs/2109.10086, 200.
- **ColBERT, Khattab and Zaharia, SIGIR 2020** — https://arxiv.org/abs/2004.12832, 200. **ColBERTv2, Santhanam et al., NAACL 2022** — https://arxiv.org/abs/2112.01488, 200. Focus on: 5.3.
- **Cohere rerank docs, models page, best practices, v4 changelog** — https://docs.cohere.com/docs/rerank, https://docs.cohere.com/docs/models, https://docs.cohere.com/docs/reranking-best-practices, https://docs.cohere.com/changelog/rerank-v4.0, all 200.
- **sentence-transformers v6.0.0 release** — https://github.com/huggingface/sentence-transformers/releases/tag/v6.0.0, 200. Focus on: "Higher-precision scoring".
- **HyDE, Gao, Ma, Lin, Callan, ACL 2023** — https://arxiv.org/abs/2212.10496, 200. Table 1.
- **Query2doc, Wang, Yang, Wei, Microsoft, EMNLP 2023** — https://arxiv.org/abs/2303.07678, 200. Tables 1, 2, 6.
- **Query Rewriting for Retrieval-Augmented LLMs, Ma et al., EMNLP 2023** — https://arxiv.org/abs/2305.14283, 200. Table 2.
- **RAG-Fusion, Rackauckas, Infineon, 2024** — https://arxiv.org/abs/2402.03367, 200.

### Chunking

- **Introducing Contextual Retrieval, Anthropic, 2024** — https://www.anthropic.com/engineering/contextual-retrieval, 200. The old `/news/` URL redirects here.
- **When Is Complex Chunking Worth It?, Caspari et al., CIKM 2026** — https://arxiv.org/abs/2608.16586, 200. Figure 1, Tables 2 and 3.
- **Late Chunking, Günther et al., Jina AI, 2024** — https://arxiv.org/abs/2409.04701, 200. Table 2.
- **Is Semantic Chunking Worth the Computational Cost?, Qu et al., Vectara, 2024** — https://arxiv.org/abs/2410.13070, 200. Tables 1 to 3.
- **Evaluating Chunking Strategies for Retrieval, Chroma, 2024** — https://www.trychroma.com/research/evaluating-chunking, 200.

### Freshness and evals

- **Enhancing HNSW Index for Real-Time Updates, Xiao et al., 2024** — https://arxiv.org/abs/2407.07871, 200. Section III, Fig. 3.
- **Ghost Vectors, Chakraborttii et al., 2026** — https://arxiv.org/abs/2606.18497, 200.
- **Drift-Adapter, Vejendla, EMNLP 2025** — https://arxiv.org/abs/2509.23471, 200. Tables 1 to 4.
- **BEIR, Thakur et al., NeurIPS 2021 Datasets** — https://arxiv.org/abs/2104.08663, 200. Tables 2 and 3.
- **MTEB, Muennighoff et al., EACL 2023** — https://arxiv.org/abs/2210.07316, 200. **MMTEB, Enevoldsen et al., ICLR 2025** — https://arxiv.org/abs/2502.13595, 200.
- **MTEB What's New** — https://docs.mteb.org/whats_new/, 200. **SciFact in MTEB format** — https://huggingface.co/datasets/mteb/scifact, 200.

## 9. Tools and versions to pin

Versions from PyPI JSON and the GitHub releases API on 2026-09-17.

| Tool | Current version | Release date | Source | Notes on breaking changes |
|---|---|---|---|---|
| faiss-cpu | 1.15.1 | 2026-09-16 | PyPI | RaBitQ in HNSW added. Defaults unchanged. |
| hnswlib | 0.8.0 on PyPI. 0.9.0 and 0.10.0-rc.2 on GitHub. | 2023-12-03. 2026-03-28. 2026-09-14. | PyPI, GitHub | 0.9.0 throws when fewer than k results exist. Pin from PyPI unless you build from source. |
| pgvector extension | 0.8.6 | 2026-07-29 | GitHub tag, CHANGELOG | Use 0.8.4 or later for HNSW vacuum fixes |
| pgvector Python | 0.5.0 | 2026-07-06 | PyPI | |
| pgvectorscale | 0.9.1 | 2026-09-04 | GitHub | Some old DiskANN indexes must be rebuilt |
| qdrant server and client | 1.19.1 and 1.19.1 | 2026-09-04 and 2026-09-16 | GitHub, PyPI | TurboQuant from 1.18. RocksDB removed in 1.18. |
| weaviate server and client | 1.39.5 and 4.23.1 | 2026-09-15 and 2026-09-07 | GitHub, PyPI | ACORN default from 1.34 |
| milvus and pymilvus | 3.0.1 and 3.0.1 | 2026-09-09 and 2026-07-29 | GitHub, PyPI | 2.6.24 is still maintained. New index versions are opt-in. |
| lancedb | 0.38.0 | 2026-08-31 | PyPI | 0.40.0 betas on GitHub |
| elasticsearch server and client | 9.5.4 and 9.5.1 | 2026-09-15 and 2026-09-09 | GitHub, PyPI | Default quantization changed in 9.1 and 9.4 |
| OpenSearch | 3.8.0 | 2026-08-05 | GitHub | NMSLIB engine deprecated |
| Vespa and pyvespa | 8.753.16 and 1.2.6 | 2026-09-16 and 2026-09-14 | GitHub, PyPI | |
| sentence-transformers | 6.0.1 | 2026-08-31 | PyPI | v6 needs transformers v5. Scoring now upcasts to float32. |
| bm25s | 0.3.11 | 2026-08-25 | PyPI | `rank-bm25` last released 2022 |
| mteb | 2.21.0 | 2026-09-14 | PyPI | v1 scripts break. Use `mteb.evaluate`. |
| beir | 2.2.0 | 2025-06-04 | PyPI | Slow-moving. MTEB now hosts the datasets. |
| pylate | 1.6.0 | 2026-06-11 | PyPI | ColBERT training and indexing |
| cohere | 7.1.1 | 2026-08-31 | PyPI | Rerank v4 model names |
| langchain-text-splitters | 1.1.2 | 2026-04-16 | PyPI | Default separators affect results, per Chroma |
| scann | 1.4.2 | 2025-08-29 | PyPI | Linux wheels. Mac support not checked. |

## 10. Open questions and disagreements

- **Is contextual retrieval worth its cost?** Anthropic reports a 35% drop in top-20 failures from contextual embeddings alone, on its own four domains with Gemini embeddings. Caspari et al. found contextual chunking rarely wins significantly, with local Qwen3-Next context, small open embedders, and corpora up to 6M documents. The conditions differ in the embedder, the metric, the generator, and the significance testing. Anthropic reports no significance test. Both can be true. A course should present both and let L13 decide on the learner's data.
- **Is semantic chunking better?** Chroma found LLM chunking best on token-level recall, but with standard deviations near 0.3 and a small dataset. Vectara and Caspari found no consistent gain. Vectara showed semantic chunking wins mainly on artificially stitched documents. The split is the document mix.
- **Does RRF k matter?** Cormack et al. found k barely mattered for lexical runs in 2009. The laptop SciFact run found k=1 above k=60 by 0.02 nDCG@10 for both models. That run is one dataset without a significance test. The disagreement may come from fusing two lists instead of 30. Not settled.
- **Binary quantization quality.** The HF blog shows 96.45% retention for mxbai and 74.77% for e5-base-v2. Qdrant says binary works well only for high-dimensional, centered vectors. Both point to the model, not the method, as the cause. The laptop run showed 0.6917 against 0.7127 for bge-small at 384 dimensions with rescoring.
- **HNSW or cluster indexes for changing data?** HNSW papers and vendor docs report tombstone and unreachable-node problems. SPFresh-based systems claim in-place updates. VIBE ranks both families near the top for static data. No public study compared them under the same churn workload. Not checked.
- **Qdrant TurboQuant versus scalar quantization.** The release notes say "without the recall tax". The docs say it "may outperform or slightly underperform scalar quantization". Treat the release note as marketing.

## 11. Things I could NOT verify

- **The original PQ paper text.** HAL returned a bot-check page. Check: open https://inria.hal.science/inria-00514462/document in a browser.
- **Milvus index documentation.** milvus.io returned 302, then 403 and 502 to curl. Check: open the page in a browser and record the index list and defaults.
- **Qdrant and Elasticsearch HNSW defaults in source.** Taken from docs only. Check: read `lib/segment/src/types.rs` in Qdrant v1.19.1 and the Lucene HNSW defaults used by Elasticsearch 9.5.4.
- **Cohere binary embedding numbers.** The Cohere blog body is rendered by JavaScript. The raw HTML holds only the title and date, 2024-03-18. Check: read it in a browser.
- **Cohere Rerank 4 latency and quality numbers.** The docs and changelog give none. The Cohere blog body is also rendered by JavaScript. Check: browser read of https://cohere.com/blog/rerank-4.
- **MTEB leaderboard rankings.** The Hugging Face space renders client-side. No model rankings are stated here. Check: run `mteb` leaderboard CLI and record the date.
- **Anthropic contextual retrieval per-dataset results.** The appendix is images. Check: read the images and note which baseline includes BM25.
- **SPFresh, ScaNN, RaBitQ, and ACORN detailed tables.** Only abstracts were read. Check: read the evaluation sections before quoting any table number.
- **Query decomposition evidence for single-hop questions.** No controlled study was found. Check: a targeted search of SIGIR and ACL 2025 to 2026 proceedings.
- **Public postmortems of recall loss after a model change.** None found from a named company. Check: search engineering blogs of large search teams.
- **Laptop timings on other machines.** All run times are from one Apple M4 Pro. The ANN sweep used synthetic data. The IVF-PQ result there does not transfer to real embeddings.
- **The MRL half of lab L9.** Not run. Check: repeat the truncation code with `nomic-ai/nomic-embed-text-v1.5`.
- **The L12 API cost estimate.** Not checked against current price sheets. Check: use Module 1 `code/prices.yaml`.
- **ScaNN on macOS.** Not checked. Check: `pip install scann` on the learner's Mac.

## 12. Notes for the course generator

- Say which recall you mean every time. ANN recall compares with exact search. Relevance recall compares with human labels. Big-ANN, VIBE, and ANN-Benchmarks use the first. BEIR and MTEB use the second.
- Never state "the default ef". Name the library and tag. The table in 4.1 is the reference.
- Elasticsearch default quantization depends on version and licence. State the version with every Elasticsearch claim.
- Do not copy the 768-dimension float32 storage figure from the HF quantization blog. It is wrong by arithmetic.
- Do not present MRL's "14×" as a text retrieval result. It is from ImageNet.
- Do not present ANN-Benchmarks charts as current. The project is unmaintained and the site dates from 2024-12-09. Use VIBE and Big-ANN.
- Do not install hnswlib from PyPI and call it the latest. PyPI holds 0.8.0 from 2023.
- The RRF paper did not test dense retrieval. Say so when teaching k=60.
- Contextual retrieval cost uses 2024 Claude 3 Haiku prices. Recompute with current prices and cache pricing from Module 1, section 3.3.
- Numbers that go stale fastest: tool versions, Qdrant and Weaviate quantization options, Elasticsearch defaults, Cohere model names and limits, MTEB task counts, and VIBE results.
- Before generating, re-run: the PyPI and GitHub version checks, the default table against source at the new tags, `mteb.get_benchmark` task counts, and the SciFact lab.
- Labs: the SciFact run takes about 137 s on an M4 Pro with two small models, including a one-time download. The ANN sweep takes about 51 s including the environment build. Use `uv run --with` so learners do not pollute a global Python.
- Reuse Module 11 paired-test code for every "method A beats method B" claim in L10 and L13.
