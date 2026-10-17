# Module 05: Document and multimodal ingestion

Research date: 2026-09-23. Status: research dossier, not course material. Reviewed by an independent reviewer on 2026-09-23. The corrections and spot checks are in the Review log at the end.

Module question: **A customer uploads a 300-page scanned PDF with tables. What does each parsing path cost, and where does each one lose information?**

## How this dossier was built

- **Inputs.** Four research reports written today in `scratchpad/reports/`: `research_document-ingestion_parsers.md`, `_benchmarks-vlm.md`, `_vision-retrieval.md` and `_hosted-cost.md`. Their saved sources, run files and labs are in `scratchpad/research_document-ingestion/<topic>/`. Below, `DI/` means `scratchpad/research_document-ingestion/`.
- **Gap work for this dossier.** Files are in `DI/gaps/`. The dossier author fetched four things. They are the MinerU licence at tag `mineru-4.0.6-released`, the Hugging Face licence tags of three MinerU models, the Mistral OCR docs page, and four Gemini 3 Pro pages. The author also counted output tokens of saved parser outputs with `out_tokens.py`. The author recomputed the cost table with `cost_recompute.py`.
- **Lab runs stopped by request.** A scanned-page retrieval run for gap 1 started at 19:53. The learner then asked for no new lab runs. The author killed it at 19:57 by PID. Its partial output is reported in section 8 and labelled partial. Nothing was deleted.
- **Labels.** Every claim is **verified**, **inferred** or **not checked**. A verified claim names its source and the table, section or line. "Verified by run" means a script ran on this laptop on 2026-09-23 and its output file is named. The dossier author or a research agent ran it. An inferred claim names its basis and the check that would confirm it.
- **Vendor numbers.** A number a vendor measured on documents the vendor chose is labelled "vendor-run, vendor-chosen documents".
- **Sample size.** Several parser table results rest on one page. Each such line says "n = 1 page". Treat them as warnings, not rankings.
- **Machine for every run.** Apple M4 Pro, 14 cores, 24 GiB, `sysctl hw.memsize` 25769803776, macOS 26.6, Python 3.12.14 arm64, uv 0.12.8. Parser timings are one timed run per file after one warm-up, so n = 1 and no variance. Some runs shared the machine with other jobs. Section 6 gives the load where it was recorded.
- **Anchor numbers re-checked.** Section 12 lists the result of a grep of every anchor number in section 4 against its saved source or run file.
- **Terms used in the whole dossier.**
  - **Text layer**: the invisible text stored in a PDF. A born-digital PDF has one. A scanned PDF may have one written by an old OCR run.
  - **OCR**: optical character recognition. It turns pixels into lines of text.
  - **Layout pipeline**: a set of small models that find regions, reading order and table cells, then run OCR per region.
  - **VLM parser**: a vision-language model that reads a page image and writes Markdown or HTML.
  - **Page-image retrieval**: a model that turns a page image into vectors for search, with no text step.
  - **TEDS**: tree edit distance similarity, the standard table score, 0 to 1.
  - **nDCG@10**: ranking quality of the top 10 results, 0 to 1. Module 3, 1.2 defines it.
  - **Paired test**: the harness function `common/stats.compare`, a sign-flip test on per-query differences, 10,000 flips.

---

## 1. What this module is for

Module 3 starts when text already exists. This module covers the step before it: how a page becomes text, or vectors, and what that step loses.

The short answer to the module question, for 300 scanned pages:

| Path | Time or price for 300 pages | Main loss |
|---|---|---|
| Text layer read | under 1 s on this laptop | Nothing new is read. On a scan it returns nothing or the old OCR layer's errors. |
| Plain OCR, Tesseract | about 13 min on this laptop. 17 to 60 min from single no-layer pages | Table rows and columns. Digits such as "2.1" become "21". |
| Layout pipeline, docling | about 30 min on this laptop. 35 to 88 min from single no-layer pages | Dense numeric tables on scans. Some values on born-digital tables. |
| Local VLM parser, MinerU standard | about 46 min on this laptop. 56 to 158 min from single no-layer pages | Plausible digit changes, such as ".3865" to ".3885". |
| Local VLM parser, marker fast, surya on CPU | about 175 min from the 16-page rate. 902 to 1,077 min from single no-layer pages | Plausible digit changes. The 16-page rate is low, inferred because marker read the old text layer: NACA page 23 took 1.47 s with the layer and 187.65 s without, `marker_default_ngl0.json`. |
| Hosted OCR | $0.45 at $1.50 per 1,000 pages | Table structure. Tables come back as lines. |
| Hosted layout or table API | $1.20 to $4.50. $1.20 is Textract Layout, which returns no table cells | Not measured on scans under a shared scorer. |
| Hosted VLM page parsing | $0.30 to $12.49, set by output tokens | Omission, repetition, plausible changes. Not measured here. |
| Page-image retrieval | about 4 min to encode at 0.81 s per page on an idle machine. About 9 min at the 1.73 s per page measured under load | No text for exact numbers. The answer step still needs text or a VLM. |

The first laptop time in each row comes from a 16-page real scan that still has an old OCR layer. The second comes from three single pages with no text layer. Both are n = 1 timings. Section 5 gives the conditions.

Every path lost information on at least one test page. No public benchmark measures all these paths on one scanned document set with one scorer. So the module lab must produce that number. Section 5 has the full table with conditions.

## 2. Scope

### In scope

- Reading PDFs: text layer, OCR, layout pipelines, local VLM parsers, hosted parsing APIs.
- Tables: what each path keeps and loses, and how table accuracy is scored.
- Parser benchmarks, their scorers, and who ran each number.
- VLM parser failures: omission, repetition, plausible substitution, and how to detect them.
- Page-image retrieval against parse-then-embed: what images change in cost and quality.
- Cost per 1,000 pages at today's prices, and laptop time per page.
- Re-parsing when a document changes: page fingerprints.
- Page and file limits, and parser licences for a hosted service.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Chunking after text exists, lost newlines and chunking | Module 3, 6.3 and 6.4 |
| Late interaction, MaxSim and its storage cost per token | Module 3, 5.4 |
| Quantization, binary vectors and rescoring | Module 3, 4.1 and 4.2 |
| Metric choice, nDCG, label set size, paired test | Module 3, 1.2 and 1.5 |
| Freshness, rebuild triggers, deleted vectors | Module 3, 7.1 to 7.3 |
| Hidden instructions inside uploaded files | Module 16 |
| LLM judges, judge bias, broken benchmarks in general | Module 11, 4.2 to 4.5 and 4.9 |
| Self-hosting a model on a GPU and its cost | Module 1, 4.1 and 4.6 |
| Model quantization for serving | Module 1, 4.4 |
| Image input tokens and prompt caching rules | Module 1, 3.1 to 3.3 |

### Overlap with built modules

Headings were read with `grep '^## '` on the phase documents of `inference-internals`, `context-engineering`, `retrieval-internals` and `advanced-retrieval` on 2026-09-23. The coverage files `_curriculum/module-01-coverage.md` to `module-03-coverage.md` were read too.

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Late interaction pays for speed with storage | Module 3, "5.4 — Late interaction pays for speed with storage" | Where page vectors come from and how many a page gets, 4.10. Link 5.4 for MaxSim. |
| Oversample then rescore, binary codes | Module 3, "4.1 — The model decides how much quantization costs", "4.2 — Oversample, then rescore" | Only the page-image result, 4.12. Link 4.1 and 4.2. |
| Memory per vector | Module 3, "4.4 — Memory per vector, with everything counted" | Bytes per page for image vectors and PNG pages, 4.10. Link 4.4 for the method. |
| Lexical and dense fail on different queries | Module 3, "5.1 — Lexical and dense fail on different queries" | BM25 on OCR text against page images, 4.11. Link 5.1. |
| Chunk or not, smart cuts | Module 3, "6.3 — Chunk or not matters more than where you cut", "6.4 — Smart cuts pay only when the topic changes". Coverage file line 867: "Parsing documents into text goes to Module 5." Line 888: "Extractors that drop newlines belong to Module 5." | The parser side only. The bge-small 512-token cut in 4.11 is a chunking effect: link 6.3. |
| A benchmark does not predict your corpus | Module 3, "1.3 — A benchmark does not predict your corpus" | Parser benchmarks, 4.5. Link 1.3 for the general rule. |
| Averages hide the slice that fails | Module 3, "1.4 — Averages hide the slice that fails" | Median against mean CER on OCR, 4.6. Link 1.4. |
| A new model invalidates every vector | Module 3, "7.4 — A new model invalidates every vector" | A new parser version changes the text, so it also forces re-embedding. Link 7.4. |
| Switching behind a gate | Module 3, "7.5 — Switch behind a dual index and an eval gate" | A parser upgrade can use the same dual-index switch. Link 7.5. Added by the reviewer. |
| What to record per run | Module 1, "5.5 — The run record (what to store, under which names)" | The parser version, mode, OCR engine and device from 4.2 belong in that record. Link 5.5. Added by the reviewer. |
| Rebuild on a probe | Module 3, "7.2 — Rebuild on a probe, not on a count or a clock" | Page fingerprints decide what to re-parse, 4.14. |
| Page-image retrieval deferred | Module 3 coverage line 769: "Page-image retrieval with multi-vector models goes to Module 5." | Taught here in 4.10 to 4.12. |
| Tokens and their uneven exchange rate | Module 1, "1.1 — Tokens" | Image tokens per page for hosted VLM parsing, 4.9. |
| The self-host decision | Module 1, "4.6 — The self-host decision (arithmetic, not preference)" | Laptop seconds per page as the input to that arithmetic, section 5. |
| Quantization for serving | Module 1, "4.4 — Quantization" | Not repeated. The VLM runtime result in 4.7 is about a Metal kernel, not quantization. |
| Text-to-SQL gold labels are wrong | Module 4, "1.3 — A text-to-SQL score also measures the gold labels" | Parser benchmark ground truth is wrong too, 4.5. Link Module 4, 1.3 for the method. |
| A citation proves a pointer, not support | Module 4, "6.5 — A citation proves a pointer, not support" | Evidence-box grounding on page images, 4.10. Link. |

---

## 3. What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-05-20 | PaddleOCR 3.0.0 | PyPI JSON | The 3.x API differs from 2.x tutorials. |
| 2025-09-25 | OmniDocBench v1.5 | README, commit f133a71 | New Overall formula. Older scores are on another scale. |
| 2025-10-21 | DeepSeek-OCR | arXiv 2510.18234 | Measured accuracy loss as text per vision token rises. |
| 2025-11-05 | pymupdf-layout 1.26.6, first release | PyPI JSON | Default layout step in pymupdf4llm 1.28.2. |
| 2026-01-13 | ViDoRe V3 on arXiv, ACL 2026 long paper | arXiv 2601.08620 | End-to-end benchmark. A text reranker beat a visual reranker. |
| 2026-01-13 | Google Layout Parser v1.6 preview on Gemini 3.0 Flash | Google layout parser docs | A layout meter now calls an LLM that writes descriptions. |
| 2026-02-13 | Last `llama-parse` and `llama-cloud-services` release, deprecated | PyPI JSON | Use `llama-cloud` 2.16.0. Old tutorials break. |
| 2026-04-10 | OmniDocBench v1.6 | README | New matching, 296 harder pages. v1.5 and v1.6 scores do not compare. |
| 2026-04-17 | MinerU 3.1.0: AGPL-3.0 replaced by the "MinerU Open Source License" | LICENSE.md at tags 3.0.9 and 3.1.0 | Licence review must be redone. Section 7 settles today's terms. |
| 2026-05-08 | PureDocBench audit | arXiv 2605.07492 | 12.08% of evaluator-scored OmniDocBench v1.5 blocks had errors. |
| 2026-06-11 | PP-OCRv6 "hallucination" table | arXiv 2606.13108 | First vendor table of VLM hallucination accuracy. Vendor data. |
| 2026-06-23, 2026-07-16 | Mistral OCR 4.0, then 4.1, $4 per 1,000 pages | Mistral docs and post | Cheap hosted OCR with structure and confidence scores. |
| 2026-07-20 | marker 2.0.0: code GPL-3.0 to Apache-2.0, OCR through the surya VLM, mode set by device | LICENSE and README at tags | Old marker benchmarks and licence notes are stale. |
| 2026-08-22 | colpali-engine 0.3.18 pins `torch<2.14.0` | PyPI | It cannot share the Module 3 environment. Use sentence-transformers 6.1.0. |
| 2026-09-01 | Reducto per-product pricing, r-1 at $10 per 1,000 pages | Reducto docs | Old Reducto estimates are 3 to 6 times too high. |
| 2026-09-10 | TeleOCR v3 tops OmniDocBench with non-default scorer timeouts | arXiv 2608.12898 | The paper and the leaderboard print different Overall scores for the same model. Quote the scorer settings with the number. |
| 2026-09-16 to 09-22 | MinerU 4.0.0 to 4.0.6: tiers, SHA-256 cache, CLI reads first 10 pages by default | PyPI, README, source | Seven releases in seven days. Pin exactly. |
| 2026-09-22 | docling 2.130.0 and unstructured 0.27.8 | PyPI | Near-weekly releases. |
| 2026-09-22 | gpt-6-luna at $0.10 and $0.50 per million tokens | OpenAI pricing page | Cheapest hosted VLM path. Its image token rule is not documented. |
| Until 2026-12-31 | Gemini 3.8 Flash promo price, doubles on 2027-01-01 | Gemini pricing page | Every VLM cost estimate needs a date. |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept has one best piece of evidence first, with its full conditions. Supporting evidence follows.

### 4.1 A scanned PDF often already has a text layer, and a parser that reads the layer first inherits its errors

A scan from an archive often carries an old OCR layer behind the image. A parser that trusts the text layer never runs OCR on that page.

- **Best evidence, verified by run, n = 1 page.** NACA Report 1135, page 23, a dense numeric table, from NASA NTRS. Every page is a 300 dpi CCITT scan with a hidden OCR layer. Producer field: "Pdf.Capture version 5.2". Gold: 10 rows × 16 columns typed by hand. 149 of 150 cells were confirmed against isentropic and shock formulas for γ = 1.4.
  - With the old layer, `cells_found` was 0.55 for docling 2.130.0 default, and 0.544 for marker 2.0.0 fast mode. PyMuPDF text, pymupdf4llm and unstructured `auto` took the same layer.
  - With the layer removed, in `naca_p23_notext.pdf`, marker reached 0.944 and MinerU 4.0.6 standard reached 0.994.
  - Source: `DI/parsers/runs/scores_all.txt`, rows `docling_default naca_p23`, `marker_default_ngl0 naca_p23` and `naca_p23_notext`, `mineru_standard naca_p23_notext`. Scorer: `DI/parsers/scripts/score.py`, written by the parsers research agent.
- **Why docling does this, verified in source at tag v2.130.0.** The default is `OcrMode.DEFAULT`, `docling/datamodel/pipeline_options.py` line 225. A comment at line 118 says DEFAULT "is wired to run PDF_AWARE_LAYOUT_REGIONS". Line 115 says that mode skips clusters "that contain exclusively text PDF cells".
- **A partial exception, verified by run.** MinerU standard ignored the old layer and scored 10 of 10 rows on the page with the layer. Source: `scores_all.txt`, `mineru_standard naca_p23`.
- **Not explained.** Docling with `OcrMode.FULL_PAGE` still found 0.55 of cells on the page with the layer. Inferred cause: TableFormer cell matching may still use the PDF text cells. Check: read the TableFormer cell-matching code path at v2.130.0.
- **Detection.** Compare the text layer with a fresh OCR of the same page. Large disagreement means the layer is stale. This check was not run.

### 4.2 The default, not the parser name, decides which pipeline runs, and the default changes with the device, the tier and the entry point

Two teams that "use marker" or "use MinerU" can run different pipelines.

- **Best evidence, verified in source at tag.** Marker 2.0.0, `marker/converters/pdf.py` lines 131 to 133: the mode is `"balanced" if settings.TORCH_DEVICE_MODEL == "cuda" else "fast"`. A Mac runs fast mode. An NVIDIA box runs balanced mode. The marker README's own olmOCR-Bench scores for the two modes are 76.0 and 66.6, vendor-run on one B200.
- **Unstructured 0.27.8, verified in source.** Strategy `auto` returns `FAST` when the PDF has extractable text. That path is pdfminer, with no OCR and no table model. `HI_RES` runs only when you ask for tables or images. A scan with no text layer gets `OCR_ONLY`, which runs OCR with no table model. Source: `partition/strategies.py` lines 94 to 109, function `_determine_pdf_auto_strategy`, read by the reviewer in the research install.
- **MinerU 4.0.6, verified in source and README.** The Python `parse()` uses `tier="standard"`, `parser/__init__.py` line 31. The CLI says "default: first 10 pages", `cli/commands/parse.py` line 89. A 300-page file sent through the CLI with defaults is parsed only to page 10.
- **Docling 2.130.0, verified in source.** On darwin the automatic OCR engine tries ocrmac, then RapidOCR with onnxruntime, then EasyOCR, then RapidOCR with torch. Source: `models/stages/ocr/auto_ocr_model.py` lines 67 to 200. The `OcrAutoOptions` docstring says something else: "EasyOCR if GPU is present, Tesseract otherwise", `datamodel/pipeline_options.py` line 315. In the research install, the log said "Auto OCR model selected rapidocr with torch".
- **pymupdf4llm 1.28.2, verified by run.** It returned an empty string for scanned pages, with no error, until `TESSDATA_PREFIX` was set. Source: `DI/parsers/runs/scores_all.txt`, `pymupdf_4llm` rows marked empty.
- **Teaching consequence, inferred.** Record the parser version, the mode or tier, the OCR engine chosen and the device with every parse. Without them a parse cannot be reproduced.

### 4.3 Layout-aware parsing recovers table cells that plain OCR loses, but no path kept every table on the test set

This is the worked page the module brief asked for.

- **Best evidence, verified by run, n = 1 page.** U.S. Census Bureau P60-282, page 21, Table A-1, rasterised at 200 dpi, grey, JPEG q85, no text layer. Gold: 37 table rows and 25 significance stars.
  - Tesseract 5.5.3, 300 dpi, `--psm 3`: 12 of 37 rows intact, 15 of 25 stars. The row "Female householder, no spouse present" came out with "21" where the page says "2.1". Nearby rows show "#70" for "*7.0" and "$57" for "*5.7".
  - docling 2.130.0 default: 37 of 37 rows, 25 of 25 stars. The same row keeps 2.1 in the right column.
  - Source: `DI/parsers/runs/scores_all.txt`, rows `tesseract_300dpi census_p21_scan200` and `docling_default census_p21_scan200`. Output files: `DI/parsers/out/tesseract_300dpi/census_p21_scan200.md` and `DI/parsers/out/docling_default/census_p21_scan200.md`.
- **What layout parsing recovers here.** Cell boundaries, the column of each value, and the star next to each value.
- **What no parser recovered, verified by reading outputs, not scored.** The row indentation that makes "Married-couple" a child of "Family households".
- **Where layout loses, verified by run, n = 1 page each.**
  - NACA page 23 without its layer: row digit edit distance was 0.037 for Tesseract, 0.700 for docling, 0.692 for unstructured `hi_res`, 0.722 for MinerU basic. Docling found 0.081 of the cells. TableFormer's own paper warns that "large tables (e.g. tables that occupy half of the page or more) yield poor predictions", arXiv 2203.01017.
  - Born-digital Census page: MinerU flash, basic and standard put all 37 row labels into one cell, 0 of 37 rows. The scanned copy gave 37 of 37 with standard.
  - Born-digital Census page: docling dropped 4 of 8 values from the row "No high school diploma".
  - Born-digital Census page: unstructured `hi_res` dropped the "2022" and "2023" headers, and kept 2 of 25 stars.
- **Why born-digital tables broke more often.** Not checked.

### 4.4 A table score near 1.0 does not mean the numbers in the table are right

TEDS charges a wrong cell only the normalized edit distance of that cell's text, then divides by the node count of the whole table.

- **Best evidence. TEDS 0.9921: measured by the research agent, output not saved. The phase writer must re-run the command before quoting the number.** granite-docling-258M read the cell "1.2" as "12" on a synthetic scanned page. The table had 1 header row, 7 data rows and 4 columns. Every other cell was correct. TEDS 0.9921, TEDS-S 1.0. Scorer: OmniDocBench's copy of the PubTabNet TEDS code, commit f133a71, run by `DI/benchmarks-vlm/lab/teds_p001.py`. Command to re-run: `uv run teds_p001.py` in `DI/benchmarks-vlm/lab/`, a few seconds.
  - The wrong cell is verified in the saved output: `DI/benchmarks-vlm/lab/out_set/p001_150_scan.md` line 7 has the row `| Inland | 43.4 | 75.7 | 12 |`.
  - **Hand check by the reviewer, inferred from the scorer code.** The scorer returns 1 − distance ÷ n_nodes, `DI/benchmarks-vlm/lab/omnidoc_teds_f133a71.py` lines 126 to 132. A `td` rename costs the Levenshtein distance divided by the longer string, line 51: "12" against "1.2" is 1 ÷ 3. The table builder in `scorers.py` lines 65 to 72 writes `thead`, `tbody`, 8 `tr` and 32 `td`, so n_nodes is 42. 1 − (1/3) ÷ 42 = 0.99206, which rounds to 0.9921. This agrees with the printed value, if the tree edit finds only that one rename.
- **Self-test cases, measured by the same agent, output not saved. `scorers.py --self-test` printed "0 failed".** On a hand-made 11 × 5 table: one changed digit gave TEDS 0.9971. Two values swapped between rows gave TEDS 0.9824 and TEDS-S 1.0. An invented extra row gave 0.9189. A header written as `th` with wrong text scored 1.0, because the reference code compares text only for `td`. The self-test code asserts "one wrong digit keeps TEDS > 0.99", `scorers.py` line 130.
- **Published, verified.** Horn and Keuper, Offenburg University, arXiv 2603.18652 v2, preprint. Pearson r against averaged human scores, 518 table pairs, 3 raters each: TEDS 0.684, GriTS-Avg 0.698, Claude Opus 4.6 as judge 0.939. Table 1. Data: 100 synthetic PDFs with 451 arXiv tables and 21 parsers. Module 11 owns judge bias: link it.
- **Teaching consequence.** Score tables with a row-integrity check and a digit check next to TEDS. The parsers agent's `score.py` has both: `rows_ok` and `row_digit_ned`.

### 4.5 A parser accuracy number compares only when it names the benchmark version, the scorer settings and who ran it

- **Best evidence, verified.** TeleOCR on OmniDocBench v1.6. The TeleOCR paper reports Overall 96.87, arXiv 2608.12898 v3, Table 1. The OmniDocBench leaderboard lists 96.91, README at commit f133a71, table "v1.6_full". The paper, appendix D, set both match timeouts to 1200 s. It set the fallback span to 200 and the order penalty to 0.05. The defaults are 300 s, 420 s, 10 and 0.10, `configs/end2end.yaml` lines 30 to 33 at f133a71.
- **Who ran it, verified.** The OmniDocBench README does not say who ran each leaderboard row. A grep for "reported by", "submitted" and "self-report" found no match.
- **Vendor-run, vendor-chosen documents, verified.** Mistral OCR 4 post, 2026-06-23: olmOCR-Bench 85.20 and OmniDocBench 93.07, with no OmniDocBench version. The post says "All competitor scores reflect internal reproductions." It says Mistral strips headers and footers before scoring on olmOCR-Bench. The human-preference win rate "averaging 72%" is on 600+ documents that Mistral assembled, "sourced from third-party vendors", with independent annotators, line 203. Source: `DI/hosted-cost/mistral_ocr4_news.txt`.
- **Unusable number, verified.** Reducto's r-1 post claims "20% reduction in error rate" with no benchmark, documents or metric. Source: `DI/hosted-cost/reducto_r1.txt`.
- **The ground truth is wrong too, verified.** PureDocBench, CASIA and others, arXiv 2605.07492, preprint. The audit of OmniDocBench v1.5 "screens its 21,353 evaluator-scored blocks and confirms 2,580 errors (12.08%)". Arithmetic checked: 2580 / 21353 = 0.1208.
- **Two benchmark families rank the same model differently, verified.** PaddleOCR-VL-1.6: TEDS 94.76 on OmniDocBench v1.6. Tables 67.77 on ParseBench, `leaderboard.csv`. The metrics and documents differ, and LlamaIndex, whose product ranks first, runs ParseBench.
- **Dropped claim.** A Gemini 3 Pro OmniDocBench 1.5 score of "0.115" appeared only in search results. The dossier author fetched the Google DeepMind evaluation PDF and three Gemini pages today. None contains 0.115 or any OmniDocBench number. The PDF gives only the method: "the average Edit Distance across the Text, Formula, Table, and ReadingOrder sub-metrics". That is not OmniDocBench's own Overall. Source: `DI/gaps/gem_b52ef7.txt`. The leaderboard row "Gemini 3 Pro 92.91" stays, with "who ran it: not stated".

### 4.6 VLM parsers fail silently by omission, repetition and plausible digit changes, and olmOCR-Bench cannot see inserted text

- **Best evidence, verified by run, n = 1 page.** marker 2.0.0 fast mode, surya VLM on CPU, NACA page 23 without its layer. It changed digits into other plausible digits: .3809 became .3909, .3759 became .8759, .8071 became .6071, .7532 became .7592. It changed header symbols: ρ₂/ρ₁ became p₂/ρ₁. MinerU standard changed .3865 to .3885. Source: `DI/parsers/out/marker_default_ngl0/naca_p23_notext.md`, found by the physics check used for the gold.
- **Synthetic pages, verified by run.** granite-docling-258M at revision 982fe3b, bf16, greedy, `use_cache=True`, on MPS. 20 synthetic A4 pages from `make_set.py`, each in 3 renderings. Reference: the PDF text layer. Scorer: `not_on_page.py`.
  - Clean 150 dpi: the table was dropped on 6 of 20 pages. The model emitted an empty table tag, and nothing errored.
  - Scan, 150 dpi, 0.8° rotation, blur 0.6, noise σ 12: one number not on the page, "12" for "1.2", on 1 of 20 pages.
  - Badscan, 100 dpi: most outputs repeated the title in place of the content. One page looped to the 2,048-token limit.
  - No output contained an invented sentence. Limits: 1 small model, synthetic pages, not real scans.
  - Source: `DI/benchmarks-vlm/lab/vlm_set.log` and `out_set/`.
- **olmOCR-Bench, verified.** The dataset jsonl files hold 7,019 tests over 1,403 PDFs: math 3,385, order 1,061, table 1,020, absent 823, present 721, baseline 9. Counted by the benchmarks agent at dataset revision 54a96a6. Presence, order, table and math tests search for a target, so extra text cannot fail them. This is inferred from `olmocr/bench/tests.py`. The absent tests check headers and footers only. The maintainers' comment on the repetition check: "Honestly, this test doesn't seem to catch anything at the moment", `tests.py` line 518, commit f7cfe4c. A changed digit can fail a presence or table test only when a test targets that exact value.
- **OmniDocBench is different, inferred from code, not run.** Unmatched predicted text gets `'edit': 1` in the text edit distance, `src/core/matching/match.py` lines 440 to 454, per the benchmarks report section C3. So OmniDocBench does charge inserted paragraphs. Text inside a table is scored by TEDS, and TEDS charged an invented row only 0.08, 4.4. Check: run the end2end scorer on the demo data with one added paragraph.
- **Vendor data, verified.** PP-OCRv6, Baidu, arXiv 2606.13108 v1, Table 7: "accuracy measures the rate of correct outputs without hallucinated content". Qwen3-VL-235B 80.56, GPT-5.5 78.00, Kimi-K2.6 85.00, the best VLM in the table, and PP-OCRv6_medium 93.20. The set is Baidu's own, its size is not stated, and the examples are VLMs "correcting" misspelled text.
- **The mean hides the failures, verified.** Gardella et al., arXiv 2607.24077 v3, preprint. 175 Spanish microfilm pages of the Berrutti dataset. Berrutti is the dataset name, not an author. Qwen 3.6 in reasoning mode: median CER 1.72%, mean CER 11.17%, section 4.3 and Table 1. Link Module 3, 1.4 for the method.
- **Detection, verified by self-test.** `not_on_page.py --self-test` passes 8 of 8. It compares the output with the text layer: unexpected words, numbers not on the page, digit bag, length ratio and tail repeats. It cannot see a correct value placed in the wrong cell. On a true scan there is no text layer, so the reference must come from a second OCR engine. That variant was not run.

### 4.7 On a laptop, the runtime and the shipped config decide VLM parser cost more than the model size

- **Best evidence, verified by run, log saved.** granite-docling-258M with transformers 5.17.0. The model repository's `generation_config.json` sets `"use_cache": false` at revision 982fe3b. With that default, one page took 189.3 s. With `use_cache=True` the same page took 2.5 s at 66.57 tokens per second, with identical text. Source: `DI/benchmarks-vlm/lab/vlm_run1.log` line 5 and `vlm_bf16c.log` line 6.
  - **Corrected by the Phase 3 re-run.** Back to back, at a similar load average, the pair took 94.9 s and 3.5 s, 27 times, with the same text. Source: `scratchpad/runs/document-ingestion_p03_granite_cache.txt`. The 189.3 s run overlapped a page-image encode on the same GPU, inferred from file times. Quote 27 times, not 75.7 times. See section 14.
- **Metal against CPU: measured by the research agent, output not saved. The phase writer must re-run the command before quoting the numbers.** `llama-bench` from llama.cpp build b11125 on `surya-2.gguf`, "qwen35 0.8B F16", 64 tokens, 2 repetitions. Metal `-ngl 99`: 6.58 ± 0.25 tokens per second. CPU `-ngl 0`: 70.42 ± 7.21. The reviewer searched `DI/benchmarks-vlm/` and `DI/parsers/` for "70.42" and "llama-bench" and found no log. Command to re-run: `llama-bench` with `-ngl 99` and with `-ngl 0`, under a minute.
  - **Overturned by the Phase 3 re-run.** Same build, same model, output saved: Metal 138.48 ± 0.54 tokens per second, CPU 72.36 ± 1.38. Source: `scratchpad/runs/document-ingestion_p03_llama_bench.txt`. See section 14.
- **Effect on marker, CPU side verified by run.** With `LLAMA_CPP_NGL=0`, scanned pages took 148.52 to 215.45 s. Source: `DI/parsers/runs/run_marker_default_ngl0.log` and `marker_default_ngl0.json`.
- **Effect on marker, Metal side: measured by the research agent, duration not saved.** The parsers report, section 1.4 line 72, says one scanned page had not finished after more than 4.5 minutes, with 1,731 tokens at about 7 tokens per second. The saved log `DI/parsers/runs/run_marker_default.log` agrees only in part. It ends after the born-digital `bert_p6` page at 17:48:49 and has no line for the scanned page.
  - **Overturned by the Phase 3 re-run.** On `bert_p6_scan200`, back to back, marker took 199.16 s on CPU and 68.88 s on Metal, with identical output bytes. One page, llama.cpp build b11125. A page-image encode shared the GPU during the whole CPU run and the first 28 s of the Metal run. A Metal-only run before that encode took 64.26 s. Sources: `scratchpad/runs/document-ingestion_p03_marker_cpu_vs_metal.txt` and `document-ingestion_p03_marker_metal.txt`. So the rule "set `LLAMA_CPP_NGL=0` on this Mac" is withdrawn. The CPU rates in section 5 stay, labelled CPU. See section 14.
- **Model size is not the only driver, inferred.** MinerU standard runs a 1.2B VLM through its bundled llama.cpp. It took 11.28 to 31.52 s per scanned page, faster than marker's 0.8B surya model on CPU. Source: `DI/parsers/runs/mineru_standard.json`. The two runs also differ in pipeline and output length, so this does not isolate model size.
- **Whether a newer llama.cpp build fixes the Metal slowdown.** Not checked.

### 4.8 A hosted "OCR" meter and a hosted "table" meter are different products, 7 to 10 times apart in price

A cheap per-page price usually buys text lines. Table cells cost a separate, higher meter.

- **Best evidence, verified.** AWS Price List API for Textract, us-east-1, publication date 2026-09-11. `DetectDocumentText` $1.50 per 1,000 pages for the first 1M pages. `AnalyzeDocument Tables` $15 per 1,000 pages. Quote: "0-1M pages of AnalyzeDocument Tables, $15 USD per 1000 pages". Source: `DI/hosted-cost/aws_textract_priceapi_useast1.json`.
- **The same split elsewhere, verified.** Azure Read $1.50, Azure Layout $10 per 1,000 pages, from the Azure Retail Prices API. Google Enterprise Document OCR $1.50 after 1,000 free, Layout Parser $10. The Google unit "per 1,000 pages" is inferred from the page's Form Parser example.
- **Consequence, inferred.** A scanned PDF with tables sent to a $1.50 meter comes back as lines. The table structure is lost and nothing fails. No hosted service was run on the test pages, so the loss on scans is not measured.
- **Model-written text inside a layout meter, verified in docs.** Google Layout Parser versions on Gemini "annotate" figures, charts and tables "with rich, textual descriptions". Reducto's `embedding_optimized: true` turns tables into "natural language summaries". Inferred risk: these can add text that is not on the page.

### 4.9 VLM page parsing is priced by the output tokens, and a table page writes more output than the usual assumption

- **Best evidence, verified prices and doc token count, measured output length.** Gemini 3.1 Flash-Lite: $0.25 per million input tokens and $1.50 per million output tokens, standard paid tier, `DI/hosted-cost/gemini_pricing.txt`. A PDF page costs 560 input tokens at the default media resolution on Gemini 3 models, `gemini_media-resolution.txt`. With 100 prompt tokens and 1,500 output tokens, one page costs $0.000165 in input and $0.00225 in output. Output is 93% of the cost.
- **Output length measured on real parser outputs, verified by run.** The dossier author counted the Markdown that local parsers wrote for four scanned pages. Tokenizer: granite-docling-258M's SmolLM2 BPE, not a Gemini, Claude or OpenAI tokenizer. MinerU standard wrote 1,682 tokens for BERT page 6, 3,820 for the Census table, 3,296 for NACA page 10 and 3,590 for NACA page 23. Marker wrote 8,236 tokens for NACA page 23. Source: `DI/gaps/out_tokens.txt`.
- **Consequence, inferred.** 1,500 output tokens per page is the low end for table pages. At 3,600 output tokens, Gemini 3.1 Flash-Lite costs $5.565 per 1,000 pages instead of $2.415. The scripts print these as 5.57 and 2.41. Section 5 gives both rows for every model. Check: the `usage` field of one real API call per page type.
- **Thinking tokens, verified in docs, not measured.** Google bills "Output price (including thinking tokens)". A model that thinks by default multiplies the output bill.
- **Image tokens per page.** Gemini 3 models: 560 at the default, verified. A second Gemini page says 258 tokens per page. Two first-party pages disagree. Claude: ⌈width/28⌉ × ⌈height/28⌉, capped at 1,568 on the standard tier and 4,784 on the high-resolution tier, verified in `claude_vision.md` lines 1258 to 1265. The tier table lists the high-resolution tier as "Claude 4.7 and later models". So Claude Sonnet 5 is in the high-resolution tier, inferred from that row. Check: count tokens on one 1275 × 1650 image. Claude Haiku 4.5 is on the standard tier. OpenAI gpt-6 models are missing from the sizing table: not checked.

### 4.10 Page-image retrieval removes the parser from the index, not from the system

The retriever needs no text. The answer step still needs text or a VLM that reads the page images.

- **Best evidence, verified.** ViDoRe V3, Illuin Technology with NVIDIA, ACL 2026 long paper, arXiv 2601.08620, section 4.2 and Table 3. 8 public datasets, Gemini 3 Pro as the generator, an LLM judge, hard queries only. Text context from the best text pipeline: 52.1% correct. Image context from ColEmbed-3B-v2: 54.5%. Top 5 images plus top 5 texts: 54.7%. Quote: "The hybrid pipeline achieves 54.7 % accuracy on hard queries".
- **So a production system stores up to three things, inferred from the result above.** The multi-vector index, the page images for the generator, and often a text index.
- **Storage per page, verified by run.** ColModernVBERT on ViDoRe V3 HR pages of 1654 × 2339 pixels: 884.95 vectors of 128 dimensions per page, 226,548 bytes in fp16. That is 147 times one bge-small float32 vector of 1,536 bytes. The PNG page as shipped is 401,318 bytes on average. Source: `DI/vision-retrieval/lab/emb/score_cmvb.json` and the vision report section 5.2.
- **Where vector counts come from.** ColPali: 1,024 image patches plus the prompt tokens "Describe the image", verified in the ColPali paper section 5.2 and footnote 10. The paper gives 257.5 KB per page. 1,030 vectors × 128 × 2 bytes = 257.5 KiB, so 1,030 per page is inferred from that memory figure. The paper does not print "1,030". ColModernVBERT cuts pages into 512 × 512 tiles and compresses each to 64 tokens, ModernVBERT paper section 3. So the count depends on page shape. Measure it on your pages.
- **Answer-step cost, inferred from the documented formula.** An HR page as an image costs about 1,568 tokens on a Claude standard-tier model and about 4,784 on a high-resolution model. The same page as Markdown is 773 bge-small tokens on average. Claude's own count was not measured.
- **Grounding is weak, verified.** ViDoRe V3 section 4.3: humans agree on evidence boxes at F1 0.602. Gemini 3 Pro scores 0.065. Link Module 4, 6.5.
- **Indexing speed on a GPU, verified.** ColPali paper, Table 5, one NVIDIA L4: ColPali 0.39 s per page. Unstructured with layout, OCR and Claude-3 Sonnet captions, then BGE-M3: 7.22 s per page, of which 3.71 s is captioning.
- **Indexing speed on this laptop, verified by run.** ColModernVBERT on MPS: 0.81 s per page for 8 pages at load average 3.4. 1.73 s per page over 1,110 pages at load average 15 to 21. Sources: `DI/vision-retrieval/lab/probe_cmvb_mps.log` line 23, "per page s 0.811", and `DI/vision-retrieval/lab/emb/cmvb_meta.json`, `s_per_page` 1.734. The load average 3.4 for the 8-page probe is in the vision report only.
- **Apple Vision OCR speed, measured by the research agent, output not saved.** ocrmac 1.0.1: 1.08 s per page on 10 pages at load about 17. The number is in the vision report section 5.2 only.

### 4.11 "Visual beats text" depends on the parse quality, the model size and the query language

- **Best evidence, verified by run.** ViDoRe V3 HR at revision 0cdf0979f2c5, 1,110 born-digital pages, 318 English queries, graded qrels. BM25 with the Module 3 harness defaults, bm25s 0.3.11 and the Snowball English stemmer, on the dataset's own NeMo Retriever Markdown: nDCG@10 0.4957. ColModernVBERT on page images: 0.4941. Difference −0.0016, p = 0.93, 95% CI −0.0390 to +0.0362. Source: `DI/vision-retrieval/lab/score_cmvb.log`.
  - The BM25 row reproduces ViDoRe V3 Table 9, HR 49.6. ColModernVBERT is 2.4 points above the paper's 47.0. The cause is not checked.
- **The text path's own weak point, verified by run.** bge-small with one 512-token vector per page scored 0.4241, 0.0715 below BM25. 71.7% of HR pages exceed 512 tokens. 256-token windows raised it to 0.4637. This is a chunking effect: link Module 3, 6.3.
- **Published, verified.** ViDoRe V3 Table 9, English queries: BM25S on Markdown 53.0, ColPali 53.0, ColModernVBERT 50.7. In Table 1, which mixes six query languages, BM25S drops to 20.3. The V3 abstract's "visual retrievers outperform textual ones" does not rest on the cross-language setting alone. English-only Table 9 also shows visual ahead for larger models: Jina-v4 on page images 63.9 against Jina-v4 on text 56.7, and ColEmbed-1B 64.3 against BM25S 53.0. The gap is far larger across languages. Corrected in the coherence pass, see section 14.
- **Reranking reverses it, verified.** ViDoRe V3 Table 2: the text reranker zerank-2 lifts the Jina-v4 text pipeline from 50.4 to 63.6. The visual reranker jina-reranker-m0 moves the visual pipeline from 57.6 to 57.8.
- **On real degraded scans, verified, preprint.** Lost in OCR, Los Alamos National Laboratory, arXiv 2505.05666. DocDeg, 4,196 documents with degradation levels 0 to 3. Llama 3.2 90B as the OCR engine plus a Qwen2 7B embedder beat ColQwen2 at every level. Level 0: nDCG@5 0.5468 against 0.3242. Level 0 holds born-digital pages with no degradation. At level 0 Nougat OCR lost to ColQwen2, 0.2721 against 0.3242. At levels 1 to 3, the degraded scans, Nougat also beat ColQwen2, per the paper's section 4.1. ColQwen2 was not fine-tuned on these documents.
- **On this module's scanned condition.** No completed run compares the two paths on scans of the same pages. Section 8, gap 1, gives the design and the partial output.

### 4.12 Light pooling holds for page vectors, and sign bits need an fp16 rescore

Module 3, 4.1 and 4.2 teach binary codes and rescoring for text vectors. Teach only the page-image result here.

- **Best evidence, verified by run.** Same HR run as 4.11. ColModernVBERT fp16 0.4941. Hierarchical token pooling, factor 3: −0.0044, p = 0.44. Factor 9: −0.0434, p = 0.0001. Sign bits for documents with a float query: −0.0268, p = 0.0014. Sign bits on both sides: −0.0482, p = 0.0001. Source: `DI/vision-retrieval/lab/score_cmvb.log`.
- **Published, verified.** ColPali paper section 5.2: pool factor 3 keeps 97.8% of nDCG@5 and "the Shift dataset—composed of the most text-dense documents—is a clear outlier". Light-ColPali, Findings of ACL 2025: 98.2% of nDCG@5 at 11.8% memory, after about 72 A100 GPU hours of fine-tuning. The printed 11.8% does not equal 1/9 = 11.1%: not explained.
- **Text-dense pages, published only.** The ColPali paper's Shift result is the only evidence that pooling costs most on text-dense pages. The HR run above did not split results by text density. Not checked on this module's pages.
  - **Measured in Phase 4 section 4.3.** Split at the median Markdown length, 3,331 characters, 159 queries per half. Pool factor 3 and float-query sign bits lost more on the dense half. Pool factor 9 and two-sided sign bits lost the same on both halves. Sign bits, then an fp16 rescore of the top 100, tied fp16 on 317 of 318 queries. Source: `scratchpad/runs/document-ingestion_p04_hr_score.txt`.

### 4.13 A parse error shows up later as a retrieval miss, not as an error

- **Best evidence, verified, peer reviewed.** OHRBench, "OCR Hinders RAG", Shanghai AI Laboratory and others, arXiv 2412.02592 v4, "Accepted by ICCV 2025". Section 4.2: "Even the best solutions experience a 14% (5 F1-score) drop in the overall stage evaluation". Conditions: 8,561 document images, 8,498 Q&A pairs, 7 domains. OCR tools MinerU, Marker, GOT, Nougat, Qwen2.5-VL-72B, InternVL2.5-78B, in 2024 and early 2025 versions. Retrievers BGE-M3 and BM25, top 2 chunks of 1,024. Generators Llama-3.1-8B-Instruct and Qwen2-7B-Instruct.
- **Mechanism: measured by the research agent, output not saved. The phase writer must re-run the command before quoting the numbers.** `DI/hosted-cost/noise_probe.py` with the Module 3 harness. One more reason to re-run: the 2% row, 0.6617, equals the harness's no-stemmer SciFact baseline to four decimals, `retrieval-internals/code/common/HARNESS.md` line 159. The hosted-cost report calls this a coincidence. The reviewer read `noise_probe.py` and found no stemmer switch in it. The equality is not explained. The numbers below are in the hosted-cost report, section 2.9, only. BEIR SciFact test, 5,183 documents, 300 clean queries, BM25 harness defaults with the English stemmer. Each document character changes with probability r, seed 0. nDCG@10: 0.6863 clean, 0.6617 at 2%, −0.0246, p = 0.0024. 0.5822 at 10%, −0.1041, p = 0.0001. No step raised an error. Real OCR errors cluster in tables and numbers, so this probe shows the mechanism only.
- **Real parser errors that would hit BM25, verified by run.** Text layer and Tesseract kept all 13 line-end splits on BERT page 6, such as "sys- tems". Every de-hyphenating parser also joined real hyphens on the born-digital page: "single-model" became "singlemodel" in 9 of 9 outputs. On the 200 dpi scan of the same page, marker and MinerU standard kept "single-model". Reviewer count with `grep` over `DI/parsers/out/*/bert_p6*.md`. Docling wrote "ResultsarepresentedinTable1." Source: `DI/parsers/runs/scores_all.txt`, `splits_left`, and `DI/parsers/out/`.
- **A hosted setting that hides failed pages, verified in docs.** LlamaParse `allowed_page_failure_ratio`, `lp_configuring.md` line 455, with the example value 0.05 at line 461. Its default is not checked.

### 4.14 A whole-file hash cannot drive re-parsing, and each per-page fingerprint fails on some edit

- **Best evidence, measured by the research agent, output not saved.** `DI/parsers/scripts/page_hash.py` on the 16-page BERT paper, 0.37 s for 3 × 16 pages. The table below is in the parsers report, section 1.5, only. The script printed it. The inputs `DI/parsers/docs/bert_v2_edit_p6.pdf` and `bert_v3_resaved.pdf` are saved, so the phase writer must re-run the script before quoting the table. It takes under 1 s.

  | Fingerprint | One number edited on page 6 | Same content, re-saved with `garbage=4, deflate=True, clean=True` |
  |---|---|---|
  | Whole-file SHA-256 | changed | changed |
  | Content-stream hash | page 6 only | all 16 pages |
  | Text hash | page 6 only | no pages |
  | Raster hash at 72 dpi | page 6 only | page 15 |

- **Position keys, measured by the research agent, output not saved.** The numbers are in the hosted-cost report, section 2.11, lines 256 and 257, only. `DI/hosted-cost/page_hash_sim.py`, a 300-page PDF, raster SHA-256 at 72 dpi, 2.0 s wall. Insert one page at the front: position keys re-parse 301 of 301 pages, content keys 1 of 301. A footer date change on every page re-parses 300 of 300 under both keys.
- **What the tools do, verified in source at tag.** MinerU 4.0.6 caches by whole-file SHA-256 plus tier plus page range, `doclib/migrations/001_init.sql` lines 26 to 60. LlamaParse says "Re-parsing the same file within 48 hours costs zero credits", `lp_tiers.md`. So a one-page edit re-parses the whole file. The MinerU cache behaviour was read from source, not run.
- **Scans, inferred.** A re-scan changes every pixel, so a raster hash changes on every page. A text hash after OCR is more stable, but OCR must run first. Not checked.

### 4.15 Page limits and licence terms decide the architecture before the price does

- **Best evidence, verified in first-party docs.** A 300-page scan does not fit several synchronous APIs:
  - Textract synchronous: "limit of 1 page". Asynchronous: 3,000 pages and 500 MB. Source: `aws_limits.txt`.
  - Google Enterprise OCR and Layout Parser: 15 pages online, 500 in batch. Source: `gcp_limits.txt`.
  - Claude PDF input: the limits table row "Maximum pages per request" says "600 (100 when the request's context window is under 1M tokens)". Request size 32 MB. Source: `claude_pdf.md` line 34.
  - Mistral OCR: "Uploaded document files must be 50 MB or less and contain 1,000 pages or fewer." Fetched by the dossier author today from docs.mistral.ai, Basic OCR FAQ, `DI/gaps/mistral_capabilities_document_ai_basic_ocr.txt`.
  - Unstructured Transform: "50 MB per document". Source: `unstr_limits.md`.
  - Gemini: "PDF files up to 50MB or 1000 pages".
- **File size depends on how the scan was compressed.** Two data points, both from saved files:
  - A real bilevel scan. NACA Report 1135, the 300 dpi CCITT scan from 4.1, has 70 pages and 6,771,826 bytes, verified by the reviewer with `ls` and PyMuPDF `page_count`, `DI/parsers/docs/naca1135.pdf`. That is about 97 KB per page, so 300 such pages would be about 29 MB. That fits the 50 MB limits.
  - A synthetic grey scan, verified by run. The gap run's 150 dpi grey JPEG pages at quality 50 averaged 243,679 bytes, `DI/gaps/scan_out/degrade_meta.json`. 300 such pages would be about 73 MB before PDF overhead, over every 50 MB limit above.
  - Consequence, inferred. Check the file size and the colour mode before you pick a synchronous API. A grey or colour scan of 300 pages may need splitting or an asynchronous API. Base64 encoding adds one third to a request body, so a 29 MB file may still exceed Claude's 32 MB request limit. Not checked.
- **Licences, verified at tags.**
  - PyMuPDF 1.28.2: AGPL-3.0 or Artifex commercial. AGPL section 13 requires offering source to network users of a modified version.
  - marker 2.0.0: code Apache-2.0. Weights: "modified AI Pubs Open Rail-M license (free for research, personal use, and startups under $5M funding/revenue)".
  - MinerU 4.0.6: Apache-2.0 plus added terms. Section 7, conflict a, settles it.
  - This is not legal advice.

---

## 5. Cost and loss per path, the answer to the module question

Conditions for laptop times: Apple M4 Pro, one parser at a time, one timed run after a warm-up, n = 1. "NACA 16" is pages 1 to 16 of NACA Report 1135, a real 300 dpi scan that still has its old OCR layer. "Single scans" are three pages with no text layer: Census page 21 at 200 dpi, NACA pages 10 and 23 without the layer. Source: `DI/parsers/runs/<parser>.json`, recomputed in `DI/gaps/cost_recompute.txt`. Prices: list prices fetched 2026-09-23 by the hosted-cost agent. VLM rows assume 100 prompt tokens, no thinking tokens, and 1,500 or 3,600 output tokens per page, as 4.9 explains.

| Path | Time per page on this laptop | $ per 1,000 pages today | What it loses | How you detect the loss |
|---|---|---|---|---|
| Text layer, PyMuPDF 1.28.2 `get_text()` | 0.001 s on NACA 16. 0.002 s on BERT 16 | $0 local | On a scan: nothing, or the old OCR layer with its errors (4.1). Default `get_text()` on the born-digital Census table: one cell per line, 0 of 37 rows. `sort=True` kept 37 of 37 Census rows, but interleaved the two BERT columns: 8 of 13 gold blocks lost, all 8 body paragraphs | Empty-text check per page. Compare the layer with a fresh OCR. Row-integrity check against a few hand-typed rows |
| Plain OCR, Tesseract 5.5.3, 300 dpi, `--psm 3` | 2.57 s on NACA 16. 3.37 to 11.98 s on single scans | $0 local. Cloud stand-in about $0.41, inferred below | Table rows and columns: 12 of 37 rows on the Census scan. Digits: "2.1" became "21". Rotated page: NED 0.777, fixed by `--psm 1` | `rows_ok`, digit edit distance, numbers-not-on-page against a second engine. Orientation detection |
| Plain OCR, Apple Vision through ocrmac 1.0.1 | 1.08 s on 10 HR pages at load about 17. 0.58 s on 300 synthetic scans at load about 4, partial gap run | $0 local, macOS only | Table structure not tested. 95.9% of Markdown words of 3+ letters found on 10 clean HR pages | Word recall against a text layer where one exists |
| Layout pipeline, docling 2.130.0 default | 6.01 s on NACA 16. 6.97 to 17.65 s on single scans | $0 local. Cloud stand-in about $0.97 | Dense numeric scan table: 0.081 of cells on NACA 23. 4 values dropped on the born-digital Census row. Merged words such as "ResultsarepresentedinTable1." Equations become placeholders | `rows_ok`, digit edit distance, cell count against the page. Formula placeholder count |
| Layout pipeline, other measured | unstructured `hi_res` 2.93 s. MinerU flash 1.46 s. MinerU basic 4.98 s. PP-StructureV3 42.8 to 149.4 s on single pages | $0 local | unstructured `hi_res`: dropped year headers, 2 of 25 stars. MinerU flash and basic: 0 of 37 born-digital rows, rotated page lost | As above |
| Local VLM parser, MinerU 4.0.6 standard | 9.15 s on NACA 16. 11.28 to 31.52 s on single scans | $0 local. Cloud stand-in about $1.47 | Best on NACA 23: 10 of 10 rows with the old layer, 9 of 10 without. Still changed ".3865" to ".3885". Born-digital Census: 0 of 37 rows | Physics or sum checks on numeric tables. Numbers-not-on-page. Length ratio |
| Local VLM parser, marker 2.0.0 fast, surya on CPU | 34.9 s on NACA 16. 180.4 to 215.5 s on the three single scans. 148.5 s on the BERT 200 dpi scan. Default Metal: did not finish one page in 4.5 min, report only (4.7) | $0 local | Plausible digit changes on NACA 23 (4.6). Dropped the Census "Source" line. Header sub-cells empty | As above |
| Local VLM parser, granite-docling-258M | 2.6 s median per synthetic page, `use_cache=True`. 189.3 s with the shipped config | $0 local | Table dropped on 6 of 20 clean pages. Title loops on bad scans | Length ratio, empty-table tag, tail repeats |
| Hosted OCR | not a laptop path | Textract DetectDocumentText $1.50. Azure Read $1.50. Google Enterprise OCR $1.50 after 1,000 free. LlamaParse Fast $1.25. Mistral OCR 4.1 $4, $2 in batch | Tables flattened to lines on the $1.50 meters, from vendor docs. Not measured on the test pages. Textract reads six languages | Run the gold pages through it and score `rows_ok` and digits |
| Hosted layout or table API | not a laptop path | Textract Layout $4, Tables $15. Azure Layout $10. Google Layout Parser $10. Reducto r-1 $10, $8 in batch. LlamaParse Agentic $12.50. Unstructured Transform $15 | Not measured on scans under a shared scorer. Gemini-based Layout Parser versions and Reducto's embedding mode write model text | Same gold-page run. Numbers-not-on-page for model-written text |
| Hosted VLM page parsing | not a laptop path | gpt-6-luna $1.01 to $2.06, inferred image tokens. Gemini 3.1 Flash-Lite $2.415 to $5.565. Gemini 3.8 Flash $6.12 to $13.995. Claude Haiku 4.5 $9.10 to $19.60, from 1,496 image tokens computed by `shared/cost_calc.py`. Claude Sonnet 5 $20.63 to $41.63. Ranges are 1,500 to 3,600 output tokens | Not measured here. Local VLM failures in 4.6 are the expected kinds | Numbers-not-on-page against a second engine, length ratio, repeats. Read the `usage` field for true output tokens |
| Page-image retrieval, ColModernVBERT | 0.81 s per page for 8 HR pages at load 3.4. 1.73 s over 1,110 pages at load 15 to 21 | $0 local. Storage 226,548 bytes per page fp16. Answer step: about 1,568 to 4,784 image tokens per page per query on Claude, inferred | No text for BM25 or exact numbers. The answer step needs a VLM or a text index. Evidence boxes are weak (4.10) | nDCG@10 on labelled queries against a text path, as in 4.11 |

**300 pages on this laptop, from the NACA 16 rate.** Inferred: rate × 300. Tesseract 12.8 min. MinerU flash 7.3 min. unstructured `hi_res` 14.7 min. MinerU basic 24.9 min. docling 30.1 min. MinerU standard 45.8 min. PaddleOCR OCR 142.5 min. marker on CPU 174.5 min. From the single no-layer scans, marker needs 902 to 1,077 min. The clean 16-page no-layer throughput run was cancelled by the parsers agent, so true-scan totals rest on single pages.

**Cloud stand-in for a local path.** Inferred. An AWS `c7g.4xlarge` costs $0.58 per hour in us-east-1, from the AWS price file published 2026-09-21. Assume it runs one job as fast as this laptop. Then $ per 1,000 pages = $0.58 × seconds per page ÷ 3.6. Tesseract $0.41, docling $0.97, MinerU standard $1.47, marker on CPU $5.62. Machines for 1M pages a month = seconds per page × 1,000,000 ÷ 2,592,000: Tesseract 0.99, docling 2.32, MinerU standard 3.53, marker 13.46. The speed on that instance is not measured. This replaces the hosted-cost report's 1, 3 and 10 s scenarios. See section 7, conflict b.

**Two warnings for every row.**

1. A $1.50 row and a $15 row are not the same product. The $1.50 row returns lines. The $15 row returns cells.
2. At 1M pages a month, contract prices replace list prices at Reducto, LlamaParse, Unstructured and Google. List prices are an upper bound.

Summary: local paths cost 0.001 to 215 s per page and lose table structure or digits in path-specific ways. Hosted paths cost $1.01 to $41.63 per 1,000 pages at list prices and have no shared accuracy number on scans. The $1.01 is gpt-6-luna with inferred image tokens. The lowest fully documented hosted price is LlamaParse Fast at $1.25.

---

## 6. Lab inventory

Every lab below already ran on 2026-09-23 on the M4 Pro, unless the row says otherwise.

| Lab | Script | Saved output | Run time | Download | Proves |
|---|---|---|---|---|---|
| Parser bake-off, 16 configurations on 9 pages plus two 16-page sets | `DI/parsers/scripts/make_set.py`, `run_<parser>.py`, `score.py`, `summary.py`, `queue*.sh` | `DI/parsers/out/<parser>/`, `runs/<parser>.json`, `runs/scores_all.txt`, `runs/queue.log` | About 2.5 h for all. Base plus Tesseract about 3 min | About 6.5 GB of venvs and 6.5 GB of models. Tesseract env 548 MB | 4.1, 4.2, 4.3, 4.6, 4.7, section 5 times |
| Old-OCR-layer trap | same scripts, `naca_p23.pdf` and `naca_p23_notext.pdf` | `runs/scores_all.txt`, rows `naca_p23*` | seconds to minutes per parser | as above | 4.1 |
| Page fingerprints | `DI/parsers/scripts/page_hash.py` | printed. table in the parsers report 1.5 | 0.37 s | none beyond PyMuPDF | 4.14 |
| `llama-bench` Metal against CPU | llama.cpp b11125 binary | not saved to a file | under 1 min | 11.2 MB tarball plus 1.18 GiB model | 4.7 |
| TEDS blind spots | `DI/benchmarks-vlm/lab/scorers.py --self-test`, `teds_p001.py` | printed only. Code asserts at `scorers.py` line 130 | 4.4 s | PyPI wheels only | 4.4 |
| Text-not-on-page detector | `DI/benchmarks-vlm/lab/not_on_page.py --self-test` | printed, 8 of 8 PASS | seconds | none | 4.6 |
| Small VLM parser failures | `make_set.py 20`, `run_vlm.py`, `eval_set.py` in `DI/benchmarks-vlm/lab/` | `vlm_set.log`, `out_set/`, `vlm_run1.log`, `vlm_bf16c.log`, `probe.log` | 60 pages in 178.2 s of generation, 2.97 s mean per page | 0.52 GB weights | 4.6, 4.7 |
| Page images against Markdown, HR | `DI/vision-retrieval/lab/run_hr.py` stages `text`, `images`, `score`, and `chunks_hr.py` | `score_cmvb.log`, `emb/score_cmvb.json`, `emb/cmvb_meta.json`, `emb/bge_meta.json` | Image encode 15 to 32 min by load. Score 4 min | 442 MB data plus 1.0 GB model | 4.10, 4.11, 4.12 |
| Apple Vision OCR probe | `DI/vision-retrieval/lab/ocr_probe.py` | printed. numbers in the vision report 5.2 | 10 pages, about 11 s | ocrmac wheel | section 5 |
| Cost calculator | `DI/hosted-cost/cost_calc.py` | printed. self-test passes | under 1 s | none | 4.8, 4.9 |
| Page-hash re-parse simulator | `DI/hosted-cost/page_hash_sim.py` | printed. hosted report 2.11 | 2.0 s | PyMuPDF | 4.14 |
| Character noise to retrieval loss | `DI/hosted-cost/noise_probe.py` | printed. hosted report 2.9 | under 1.5 s per noise level | SciFact already cached | 4.13 |
| Output tokens per parsed page | `DI/gaps/out_tokens.py` | `DI/gaps/out_tokens.txt` | seconds | none | 4.9 |
| Cost recompute with measured times | `DI/gaps/cost_recompute.py` | `DI/gaps/cost_recompute.txt` | under 1 s | none | section 5 |
| Scanned-page retrieval, partial, stopped | `DI/gaps/scan_lab.py`, `run_scan_lab.sh` | `DI/gaps/scan_lab_run.log`, `scan_out/degrade_meta.json`, `scan_out/ocrmac_scan.json`, `scan_out/tesseract_scan.json`, `scan_out/pages/` | Degrade 18.0 s. ocrmac on scans 174.7 s. Tesseract 38.7 s wall, 6 workers. Image stage failed. Killed at 19:57 | none new | nothing yet. See gap 1 |

**Self-tests that exist.** `score.py` gold against itself gives NED 0.002 to 0.004 and digit NED 0. `scorers.py --self-test` prints "0 failed". `not_on_page.py --self-test` 8 of 8. `cost_calc.py` reproduces AWS Example 2, $2,100, and Google Example 2, $130,000. `noise_probe.py` at 0% must equal the harness baseline 0.6863.

---

## 7. Conflicts resolved

| Conflict | Reports | Evidence used | Resolution |
|---|---|---|---|
| a. MinerU licence | Parsers: "MinerU Open Source License", Apache-2.0 plus terms, from tags 3.0.9 and 3.1.0. Benchmarks: unclear, PyPI says custom and the HF tag says AGPL-3.0 | The dossier author fetched `LICENSE.md` at tag `mineru-4.0.6-released`, HTTP 200, 3,301 bytes, `DI/gaps/mineru_LICENSE_4.0.6.md`. Line 3: "MinerU is licensed under Apache License 2.0 and is subject to the additional terms below". Lines 9 and 10: MAU over 100 million or monthly revenue over USD 20 million needs a commercial licence. Line 14: online services must "clearly and prominently indicate" that MinerU is used. Line 18: rights terminate automatically if either term is broken. HF API today: `opendatalab/MinerU2.5-2509-1.2B` has `license:agpl-3.0`. `opendatalab/MinerU2.5-Pro-2605-1.2B` has `license:apache-2.0`. `jinzhenj/MinerU2.5-Pro-2605-1.2B-GGUF`, the repo that MinerU 4.0.6 downloads by default, has no licence tag. Files `DI/gaps/hfapi_*.json` | The code at 4.0.6 is Apache-2.0 with added terms, not AGPL. The AGPL tag belongs to the older 2509 model weights, not to the 4.0.6 code. The default weights come from a personal repo with no licence tag. Treat the weights as unlicensed until the MinerU team confirms that repo. Verified for all strings. Legal meaning not checked |
| b. Local time per page | Hosted-cost used 1, 3 and 10 s scenarios | Parsers report measured times, re-read by the author from `DI/parsers/runs/<parser>.json`: Tesseract `tp_naca_16p` 41.12 s, docling 96.18 s, MinerU standard 146.43 s, marker 558.14 s, each for 16 pages | Section 5 uses the measured rates and gives the cloud stand-in cost. `DI/gaps/cost_recompute.txt` |
| c1. Marker time per scanned page | Parsers text says "150 to 215 s" in one place and "148 to 215 s" in another | `run_marker_default_ngl0.log` line 7: `bert_p6_scan200 148.52`. `marker_default_ngl0.json`: 180.37, 187.65, 215.45 | 148.5 to 215.5 s. Both statements were rounding of the same data |
| c2. Marker "fast, no OCR" throughput | Parsers: "(CPU)" in a table whose note says one B200. Hosted-cost: "on CPU" | marker README v2.0.0 line 468: throughput is "concurrent pages/sec on one B200 host", and "marker fast-no-OCR and liteparse ... are CPU-only by design" | 23.7 pages per second on the CPU of a B200 host, vendor-run. Both reports were right in part |
| c3. olmOCR-Bench size | Paper: 7,010 tests over 1,402 or 1,403 PDFs. marker README: "~8,400 pass/fail unit tests". Benchmarks agent: 7,019 by count | Benchmarks agent's count over the 7 jsonl files at revision 54a96a6 | Use 7,019 tests over 1,403 PDFs, counted today. The "~8,400" is not supported by the data counted |
| c4. OHRBench venue | Vision report: "2024, preprint". Hosted-cost: ICCV 2025 | `DI/hosted-cost/ohrbench_abs.html` comments field: "Accepted by ICCV 2025" | ICCV 2025, arXiv v4 |
| c5. TeleOCR and PaddleOCR-VL-1.6 on OmniDocBench v1.6 | 96.87 against 96.91. 96.33 against 96.34 | Paper Table 1, leaderboard README, model card | Both values are real. They come from different runs and scorer settings. Quote each with its source (4.5) |
| c6. Gemini 3 Pro on OmniDocBench | Benchmarks report: 0.115 from search results, not in the PDF | Author fetched the evaluation PDF and three Gemini pages: no 0.115, no OmniDocBench number | Dropped. Only the method line is quoted (4.5) |
| c7. Gemini tokens per PDF page | 258 on the document page, 560 on the media resolution page | Both first-party pages, saved by the hosted-cost agent | Not settled without a `countTokens` call. The cost table uses 560, the Gemini 3 figure |
| c8. LlamaParse base timeout | Limitations page: "up to 2 hours". Troubleshooting page: "30 min base" | Both first-party pages | Not settled. Check the API reference for `processing_control.timeouts` |
| c9. VLM output tokens per page | Hosted-cost assumed 1,500 | `DI/gaps/out_tokens.txt`: 1,682 to 3,820 tokens for MinerU standard on four scanned pages, SmolLM2 BPE | 1,500 is the low end for table pages. Section 5 gives 1,500 and 3,600 |
| c10. ColPali size in ViDoRe V3 | V3 Tables 1 and 9 print "7" | ModernVBERT Table 3 gives 2.92B. NanoVDR gives 2,964M | Treat "7" as a typo. Not checked in the camera-ready version |

---

## 8. Gap list, ranked by how much the module question needs it

The learner stopped new lab runs at about 19:57. Gaps 1 and 2 are now labs for the phase writer.

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | Page-image retrieval against OCR text plus BM25 on scanned pages | The question is about scans. Every retrieval comparison in section 4 is on born-digital pages | Lab for the phase writer. Partial output below |
| 2 | Parse errors show up as retrieval misses, with real parser outputs | 4.13 rests on synthetic noise and on OHRBench with 2024 parsers | Lab for the phase writer. Design below |
| 3 | Accuracy of hosted meters on scanned tables under one scorer | Section 5 has prices without quality for every hosted row | Not done. Needs API keys. Optional and UNVERIFIED for the course |
| 4 | Clean 16-page no-layer throughput per parser | 300-page totals on true scans rest on single pages | Not done. `DI/parsers/scripts/run_tp_notext.py` exists |
| 5 | Mistral OCR file limits | 4.15 needed a first-party limit | Done. Fetched: 50 MB and 1,000 pages |
| 6 | MinerU licence | 4.15 and section 7 | Done. Fetched at tag 4.0.6 and HF tags |
| 7 | Gemini 3 Pro OmniDocBench number | 4.5 | Done. Primary sources lack it, so it was dropped |
| 8 | Output tokens per page | 4.9 cost ranking depends on it | Partly done with a proxy tokenizer. A real `usage` field needs a key |
| 9 | Tables that continue across pages | A 300-page report often splits one table over two pages. No test page does this | Not done. Found by the reviewer: marker's `--use_llm` flag "will do things like merge tables across pages" and uses `gemini-3.5-flash` by default, `DI/hosted-cost/marker_readme_v2.0.0.md` line 53. So the merge sends pages to a hosted model. LlamaParse has `merge_continued_tables`, `lp_migration.md` line 81. Neither was run |
| 10 | Per-page routing in a mixed PDF | Some pages of a real upload have a good text layer and some do not. 4.1 shows that a per-file choice goes wrong | Not done. 4.1 gives the detection idea, not run |

### Gap 1: lab for the phase writer, scanned-page retrieval

- **Design.** Take a seeded random subset of 300 of the 1,110 ViDoRe V3 HR pages. Degrade each page into a scan: grey, resize by 0.75 to about 150 dpi, rotate 0.8°, Gaussian blur 0.6, Gaussian noise σ 12, JPEG quality 50. These match `DI/benchmarks-vlm/lab/make_pages.py` condition "scan", plus JPEG. Keep English queries with at least one relevant page in the subset, and restrict qrels to the subset. Arms:
  1. BM25 on the dataset's NeMo Markdown, the clean-parse reference.
  2. BM25 on ocrmac OCR of the clean page.
  3. BM25 on ocrmac OCR of the scan.
  4. BM25 on Tesseract 5.5.3 `--psm 3` OCR of the scan.
  5. ColModernVBERT on the clean page, reusing `DI/vision-retrieval/lab/emb/cmvb_docs.npz`.
  6. ColModernVBERT on the scan.
  Report nDCG@10 and recall@10, and paired tests: scan image minus scan OCR, scan minus clean for each path.
- **Scripts to reuse.** `DI/gaps/scan_lab.py`, stages `degrade`, `ocr`, `images`, `score`. It imports `run_hr.py` and the Module 3 harness `common.metrics`, `common.stats` and `common.lexical`. Run from `DI/vision-retrieval/lab/` with `uv run`, adding `--with ocrmac==1.0.1` for the ocrmac stages. Do not set `HF_HUB_OFFLINE=1`: the image stage failed with `LocalEntryNotFoundError` under it, and the line is now commented out.
- **Expected run time, inferred from the partial run.** Degrade 18 s. ocrmac 175 s per 300 pages. Tesseract 39 s with 6 workers. Image encode about 4 min at 0.81 s per page. Score under 1 min. About 12 minutes in total. No new download.
- **What it would prove.** Whether page images or OCR text lose more retrieval quality when a born-digital page becomes a scan, on the same queries. It tests the claim in 4.11 under the module's own condition.
- **Partial output, labelled partial.** Conditions: 300 pages, seed 0, degraded as above. ocrmac 1.0.1 accurate mode on the scans: 0.582 s mean per page, 174.7 s total, load average about 4. Tesseract 5.5.3 psm 3, `OMP_THREAD_LIMIT=1`, 6 workers: 0.763 s mean per page per worker, 38.7 s wall. 3 ocrmac pages and 4 Tesseract pages had under 20 characters. Scan JPEGs average 243,679 bytes. The image stage failed. The clean-page OCR was killed. Nothing was scored. Source: `DI/gaps/scan_lab_run.log` and `DI/gaps/scan_out/`.

### Gap 2: lab for the phase writer, parse errors as retrieval misses

- **Design.** Use the saved outputs of PyMuPDF text, docling default and Tesseract for the 16-page BERT paper, `DI/parsers/out/<parser>/tp_bert_16p.md`. Split each into 256-token windows. Write queries from the gold paragraphs of BERT page 6 in `DI/parsers/gold/`, including words that parsers split or merged: "systems", "single-model", "results are presented in Table 1". Relevance: windows that overlap the gold paragraph. Run harness BM25 with and without the stemmer. Report hit@5 per parser and the paired test.
- **Scripts to reuse.** Module 3 harness `common/lexical.py` and `common/stats.py`. The parsers agent's `score.py` for paragraph alignment.
- **Expected run time, inferred.** Under 1 minute. The outputs already exist, and BM25 on 16 pages is instant.
- **What it would prove.** Whether hyphen splits and merged words from real parsers change which chunk BM25 returns. Module 3, 6.3 and 6.4 own chunking, so the lab should show only the parser effect.

---

## 9. Primary sources

All were fetched on 2026-09-23 by a research agent or the dossier author, and returned HTTP 200 unless noted. Each report's source table has the full list.

- **Docling Technical Report and toolkit paper, IBM Research** — https://arxiv.org/abs/2408.09869 and https://arxiv.org/abs/2501.17887. Section 3 pipeline. Section 5 speeds on vendor-chosen documents, with superseded versions.
- **TableFormer, IBM Research** — https://arxiv.org/abs/2203.01017. Table 2 and the large-table caveat.
- **MinerU2.5 technical report** — https://arxiv.org/abs/2509.22186.
- **MinerU LICENSE at tag mineru-4.0.6-released** — https://raw.githubusercontent.com/opendatalab/MinerU/mineru-4.0.6-released/LICENSE.md. Fetched by the dossier author.
- **marker README at v2.0.0, Datalab** — https://raw.githubusercontent.com/datalab-to/marker/v2.0.0/README.md. Vendor benchmark and licence.
- **OmniDocBench, OpenDataLab, CVPR 2025** — https://github.com/opendatalab/OmniDocBench at commit f133a71, and https://arxiv.org/abs/2412.07626.
- **olmOCR and olmOCR-Bench, Allen Institute for AI** — https://arxiv.org/abs/2502.18443 and https://github.com/allenai/olmocr at commit f7cfe4c.
- **TEDS, IBM Research Australia** — https://arxiv.org/abs/1911.10683. Reference code https://github.com/ibm-aur-nlp/PubTabNet.
- **GriTS, Microsoft** — https://arxiv.org/abs/2203.12555.
- **Horn and Keuper, table metric agreement** — https://arxiv.org/abs/2603.18652.
- **PureDocBench** — https://arxiv.org/abs/2605.07492.
- **TeleOCR** — https://arxiv.org/abs/2608.12898.
- **PP-OCRv6, Baidu** — https://arxiv.org/abs/2606.13108. Vendor data.
- **When Low CER is Not Enough, Gardella et al.** — https://arxiv.org/abs/2607.24077. Data: the Berrutti dataset.
- **DeepSeek-OCR** — https://arxiv.org/abs/2510.18234.
- **ColPali, ICLR 2025** — https://arxiv.org/abs/2407.01449. Tables 2, 4, 5 and section 5.2.
- **ViDoRe V3, ACL 2026** — https://arxiv.org/abs/2601.08620. Tables 1, 2, 3, 9, 11 and section 4.3.
- **Lost in OCR Translation, LANL** — https://arxiv.org/abs/2505.05666. Table 1 only. Its Table 4 latency contradicts its text.
- **Light-ColPali, Findings of ACL 2025** — https://arxiv.org/abs/2506.04997.
- **ModernVBERT** — https://arxiv.org/abs/2510.01149.
- **OHRBench, ICCV 2025** — https://arxiv.org/abs/2412.02592. Section 4.2.
- **ViDoRe V3 HR dataset** — https://huggingface.co/datasets/vidore/vidore_v3_hr at revision 0cdf0979f2c5, CC-BY-4.0.
- **Price and limit pages** — URLs in the hosted-cost report, section 7. They cover AWS Textract, Azure Document Intelligence, Google Document AI, LlamaParse, Reducto, Mistral, Unstructured, Gemini, Claude and OpenAI.
- **Gemini 3 Pro evaluation methodology PDF, Google DeepMind** — https://storage.googleapis.com/deepmind-media/gemini/gemini_3_pro_model_evaluation.pdf. Method line only.

## 10. Tools and versions to pin

Checked on PyPI, GitHub or the Hugging Face API on 2026-09-23 by the research agents.

| Tool | Version | Note |
|---|---|---|
| docling | 2.130.0 | MIT. Near-weekly releases |
| marker-pdf, surya-ocr | 2.0.0, 0.22.1 | Needs llama.cpp `llama-server`, build b11125 used. Record `LLAMA_CPP_NGL`. The earlier rule `LLAMA_CPP_NGL=0` on this Mac is withdrawn, section 14 |
| unstructured, unstructured-inference | 0.27.8, 1.6.13 | Needs a Tesseract binary |
| mineru | 4.0.6 | Seven releases in seven days. CLI reads 10 pages by default |
| paddleocr, paddlepaddle, paddlex | 3.7.0, 3.3.1, 3.7.2 | `paddleocr[doc-parser]` for PP-StructureV3 |
| pymupdf, pymupdf4llm, pymupdf-layout | 1.28.2 | AGPL or commercial. `import fitz` is deprecated |
| Tesseract | 5.5.3, conda-forge | tessdata_fast eng |
| sentence-transformers | 6.1.0 | Loads ColModernVBERT with `MultiVectorEncoder` on MPS |
| colpali-engine | 0.3.18 | Pins `torch<2.14.0`. Needs its own environment |
| transformers, torch | 5.17.0, 2.14.0 | |
| ocrmac | 1.0.1 | macOS only |
| table-recognition-metric, apted, Levenshtein, rapidfuzz | 0.0.6, 1.0.3, 0.27.5, 3.14.6 | PyPI `teds` 0.8.1 is an unrelated tool. Do not install it |
| llama-cloud | 2.16.0 | Replaces deprecated `llama-parse` |
| granite-docling-258M | revision 982fe3b | Ships `use_cache: false` |
| ModernVBERT/colmodernvbert | revision 4c604428a6e1 | MIT |

---

## 11. Things not verified

Each item names the check that would settle it.

**From the parsers report.**

1. Clean 16-page no-layer throughput per parser. Check: `DI/parsers/scripts/run_tp_notext.py`.
2. PP-StructureV3 on 16 pages, killed at 19:45. Check: run `run_paddle.py structurev3` with no time limit.
3. Marker with default Metal on one full scanned page. Check: rerun without `LLAMA_CPP_NGL`.
4. Marker balanced mode, MinerU advanced tier, docling VLM pipelines, PaddleOCR-VL. Not run.
5. Peak memory for all parsers except PaddleOCR. Check: `/usr/bin/time -l`.
6. Variance of every timing, n = 1. Check: 3 repeats in the foreground.
7. MinerU cache behaviour at runtime. Read from source only. Check: `mineru server start`, parse, edit, parse again.
8. Why docling full-page OCR still found 0.55 of cells on NACA page 23. Check: TableFormer cell-matching code at v2.130.0.
9. Public-domain status of the NTRS scan. Inferred from 17 USC 105. Check: NTRS terms page.
10. TableFormer venue. Check: the publisher page.
11. Whether `jinzhenj/MinerU2.5-Pro-2605-1.2B-GGUF` is an official MinerU account. It has no licence tag today. Check: ask the MinerU maintainers or read the repo's commit history.
12. `llama-bench` Metal 6.58 and CPU 70.42 tokens per second. Measured by the research agent, output not saved. The reviewer found no log. The phase writer must re-run both settings before quoting them.
13. Why born-digital tables broke more parsers than scans of the same table. Check: inspect MinerU's layout boxes on `census_p21.pdf`.

**From the benchmarks report.**

14. TEDS 0.9921 on the p001 table. Measured by the research agent, output not saved. The reviewer's hand arithmetic from the scorer code agrees, 4.4. The phase writer must re-run `uv run teds_p001.py` before quoting it.
15. TEDS and GriTS venues, ECCV 2020 and ICDAR 2023. Check: publisher pages.
16. OmniDocBench penalizes inserted text in its main match path. Inferred from code. Check: run the end2end scorer on demo data with one added paragraph.
17. olmOCR-Bench cannot be failed by inserted text outside absent and baseline tests. Inferred from code. Check: append a paragraph to a passing output and re-score.
18. Who ran each OmniDocBench leaderboard row. Check: repository issues and PRs.
19. GLM-OCR 94.62 on v1.5. Check: the GLM-OCR technical report.
20. LightOnOCR-2 olmOCR-Bench numbers, image only. Check: arXiv 2601.14251.
21. dots.ocr size and licence. Check: the HF page in a browser.
22. RD-TableBench post date and results. Check: the blog page in a browser.
23. Dr.DocBench and MORE bodies. Keyword search only.
24. ParseBench GTRM and T-LAG metric code. Not read.
25. OCR-agreement detection on true scans. Check: run `not_on_page.py` with a second engine as the reference. The gap run's Tesseract and ocrmac scan outputs could serve as the two engines.
26. The clean-page table drop at other resolutions or models. Check: render the clean set at 200 dpi and re-run.
27. Horn and Keuper judge costs at today's prices. Not extracted.

**From the vision-retrieval report.**

28. The CPU behind NanoVDR's latency table. Check: its appendix or repo.
29. Why Light-ColPali's memory shares exceed 1/9 and 1/49. Check: its appendix B.
30. ColPali size "7" in ViDoRe V3. Check: the camera-ready ACL version.
31. The SIGIR 2025 paper's BGE-M3 size. Check: the BGE-M3 model card.
32. Per-page token counts in SIGIR 2025 Figure 3. Check: the figure image.
33. Claude token count of an HR Markdown page and of an HR page image. Check: the token counting endpoint. Needs a key.
34. ColParse, HPC-ColPali, jina-embeddings-v4 bodies. Abstracts only.
35. Vendor numbers: Vespa DocVQA, NVIDIA pipeline rows, IRPAPERS. Not reproduced.
36. MTEB leaderboard state today. Not fetched.
37. ColQwen2.5-base licence, Apache-2.0 tag against a Qwen Research card. Check: the LICENSE files.
38. ColModernVBERT 0.4941 here against 47.0 in V3 Table 9. Check: score an older adapter revision with colpali-engine 0.3.18 in a torch 2.13 environment.
39. Mxbai Edge 32M on HR, 52.7 against 0.5261. Rounding or run difference.
40. Per-page indexing time for the V3 pipelines. The JSON files have no timing fields.
41. Laptop timings under load. Check: re-measure page encode and OCR at load average under 4.
42. A completed scanned-page comparison. Gap 1 in section 8.

**From the hosted-cost report.**

43. Google Document AI price units. Check: the SKU in the Cloud Billing catalog.
44. gpt-6-luna and gpt-6-sol image tokens. Check: one call's `usage` field.
45. Whether Claude Sonnet 5 is in the high-resolution image tier. Inferred yes from the tier row "Claude 4.7 and later models". Check: token counting on one 1275 × 1650 image.
46. The resolution at which Claude and OpenAI render PDF pages. Check: token counting on a one-page PDF against the same page as an image.
47. LlamaParse default `allowed_page_failure_ratio`. Check: the API reference.
48. Whether failed pages are billed at LlamaParse, Reducto, Azure and AWS. Only Google states it.
49. Accuracy of every hosted service on scanned table pages under a shared scorer. None found. Gap 3.
50. B200 and other GPU hourly prices behind marker's throughput. Not fetched.
51. File size of a real 300-page scanned PDF. 4.15 now has one real bilevel scan, about 97 KB per page, and one synthetic grey scan, about 244 KB per page. Grey and colour 300 dpi scans are not measured.
52. A production write-up with parse failure rates or re-index savings. None found.
53. Model weight licences for docling, surya and PaddleOCR models.
54. Greshake et al. venue. Module 16 owns the topic.
55. Reducto r-1's "20% reduction in error rate": no documents or metric.
56. The OmniDocBench version behind Mistral's 93.07.
57. Gemini tokens per PDF page, 258 or 560. Check: `countTokens` on one page.
58. LlamaParse base timeout, 2 hours or 30 minutes. Check: the API reference.
59. The speed of any parser on a cloud instance. The section 5 stand-in assumes laptop speed.

**From this dossier's own work.**

60. Output tokens per page from a real hosted VLM. The SmolLM2 BPE count is a proxy. Check: one call per page type.

---

## 12. Anchor number re-check

The dossier author grepped 84 anchor strings from section 4 and section 7, conflict a, on 2026-09-23. Each search ran over the saved source text or run output named in the concept. Script: `DI/gaps/anchor_check.py`. Output: `DI/gaps/anchor_check.txt`.

- **82 of 84 anchors were found.**
- Two were found only after fixing the search pattern. The Textract text "limit of 1 page" is split across a line break in the saved page. The Claude PDF limit is a table row, so the first quote in 4.15 was reworded to match the source.
- One value is rounded in the dossier. The stored bytes per page are 226,547.5, printed as 226,548.
- **Two anchors have no saved file.** Both were printed to a terminal by a research agent and never written to disk:
  1. TEDS 0.9921 for the p001 table, 4.4. The wrong cell itself is verified in the saved output. Check: `uv run teds_p001.py`.
  2. `llama-bench` 6.58 and 70.42 tokens per second, 4.7. The marker timings that follow from it are verified in saved logs. Check: re-run `llama-bench` with `-ngl 99` and `-ngl 0`.
- **One more anchor rests on a report, not a run file.** The noise-probe numbers in 4.13, 0.6617 and 0.5822, were found only in the hosted-cost report. The probe printed to a terminal. Check: `noise_probe.py`, under 2 s per noise level.
- The learner stopped new runs, so none of these was re-run. The reviewer relabelled them "measured by the research agent, output not saved" in section 4. The phase writer must re-run each command before quoting its number.

---

## 13. Review log

Independent review on 2026-09-23. The reviewer did not write the dossier. All checks were read-only: `grep`, `sed`, `python3 -c` over saved files, and one PyMuPDF `page_count` read of a saved PDF. No lab ran. No URL was fetched, because every anchor had a saved copy. `DI/` means `scratchpad/research_document-ingestion/` of the research session.

Section 14 lists the corrections found later, while the phases were built.

### 13.1 Corrections

Counts: 6 wrong facts or wrong arithmetic, 9 labels changed, 4 source locations fixed, 2 headings rewritten, 4 additions with evidence, 2 overlap rows added, 2 gaps added.

**Wrong facts or arithmetic.**

1. Section 5 summary said hosted paths start at $1.25 per 1,000 pages. The cost table's own gpt-6-luna row is $1.01. Evidence: `DI/gaps/cost_recompute.txt`, "gpt-6-luna out=1500: 1.01". Fixed to $1.01, with the $1.25 LlamaParse Fast price named as the lowest fully documented one.
2. Section 1, MinerU row, said "Pages at 150 to 215 s each with marker on CPU". That is a marker number in a MinerU row. Moved to a new marker row.
3. Section 5, marker row, said "148.5 to 215.5 s on single scans". Section 5 defines single scans as Census 21, NACA 10 and NACA 23 with no layer. Those three are 180.37, 215.45 and 187.65 s. 148.52 s is `bert_p6_scan200`. Evidence: `DI/parsers/runs/marker_default_ngl0.json`. Fixed.
4. Section 5, text layer row, said "8 of 14 paragraphs lost". The gold file has 13 blocks, and 8 were lost. Evidence: `DI/parsers/gold/bert_p6.json` has 13 `paragraphs`. `scores_all.txt` row `pymupdf_text_sort bert_p6` lists P1 to P8 lost. Fixed.
5. The same row implied `sort=True` also broke the Census table. `pymupdf_text_sort census_p21` has `rows_ok=37/37`. Only default `get_text()` gives 0 of 37. Fixed.
6. 4.13 said "single-model" became "singlemodel" in 9 of 9 outputs, without the page. That holds on the born-digital page only. On `bert_p6_scan200`, marker and MinerU standard kept the hyphen. Evidence: reviewer `grep -c` over `DI/parsers/out/*/bert_p6*.md`. Fixed.

**Labels changed.**

7. 4.4, TEDS 0.9921: now "measured by the research agent, output not saved", and the phase writer must re-run it. The reviewer searched `DI/benchmarks-vlm/` and `DI/parsers/` for "0.9921". The only hits were an OmniDocBench demo JSON and poppler font maps, both unrelated.
8. 4.4, `scorers.py` self-test values 0.9971, 0.9824 and 0.9189: same label. They were printed only.
9. 4.7, `llama-bench` 6.58 and 70.42 tokens per second: same label. No file under `DI/benchmarks-vlm/` or `DI/parsers/` contains "70.42" or "llama-bench". The llama.cpp folder holds only the binary and its tarball.
10. 4.7, marker with default Metal not finishing in 4.5 min: the dossier cited the `ngl0` files, which hold CPU runs. The duration is in the parsers report line 72 only. `run_marker_default.log` ends after `bert_p6` at 17:48:49. Relabelled.
11. 4.7, "Model size is not the driver, verified by run": relabelled inferred. MinerU and marker differ in pipeline and output length as well as model size.
12. 4.13, noise probe: relabelled "output not saved". Added that the 2% row, 0.6617, equals the harness's no-stemmer baseline to four decimals, `HARNESS.md` line 159. The reviewer read `noise_probe.py` and found no stemmer switch. Not explained.
13. 4.14, page fingerprint table: was "verified by run". The output was printed only, per section 6. Relabelled, with the saved input PDFs named.
14. 4.14, `page_hash_sim.py` numbers: same. They are in the hosted-cost report, section 2.11, lines 256 and 257, only.
15. 4.10, Apple Vision 1.08 s per page: printed only, in the vision report. Relabelled. The 0.81 s ColModernVBERT figure is saved: `probe_cmvb_mps.log` line 23.

**Source locations fixed.**

16. 4.2, docling docstring: the quote "EasyOCR if GPU is present, Tesseract otherwise" is in `datamodel/pipeline_options.py` line 315, class `OcrAutoOptions`. It is not in `auto_ocr_model.py`.
17. 4.10, ColPali "1,030 vectors": the paper does not print 1,030. It gives 1,024 patches, footnote 10, plus the prompt "Describe the image", and 257.5 KB per page, line 616 of the saved text. 1,030 × 128 × 2 = 263,680 bytes = 257.5 KiB. Relabelled inferred.
18. 4.13, LlamaParse: `allowed_page_failure_ratio` is named at `lp_configuring.md` line 455. The value 0.05 is at line 461.
19. 4.5, Mistral: the 600+ documents were "sourced from third-party vendors" and assembled by Mistral, line 203. The vendor-chosen label stays.

**Headings rewritten.**

20. 4.6 said the two main benchmarks "barely see extra or changed text". The benchmarks report, section C3, infers from code that OmniDocBench does charge unmatched inserted text, `match.py` lines 440 to 454. Changed text fails an olmOCR-Bench test when a test targets that value. New heading names only olmOCR-Bench and inserted text. An OmniDocBench line was added.
21. 4.12 said compression "costs most on text-dense pages". Its best evidence, the HR run, did not split by text density. Only the ColPali paper's Shift remark says so. New heading states what the run measured. The Shift remark is kept as published-only evidence.

**Additions with evidence.**

22. 4.2: unstructured `auto` on a scan with no text layer returns `OCR_ONLY`, with no table model. Source: `partition/strategies.py` lines 94 to 109 in the research install, unstructured 0.27.8 per `envs/freeze_unstructured.txt`.
23. 4.4: hand arithmetic that reproduces TEDS 0.9921 from the scorer code: 1 − (1/3) ÷ 42 = 0.99206. See 4.4 for the lines.
24. 4.15: a real scan's file size. `DI/parsers/docs/naca1135.pdf` is 6,771,826 bytes for 70 pages, about 97 KB per page. 300 pages would be about 29 MB, under the 50 MB limits. The earlier text said a 300-page scan exceeds every 50 MB limit. That rested on the synthetic grey JPEG set only.
25. Section 1: each local row now also gives the 300-page time from the single no-layer pages. The 16-page set still has its old OCR layer. Marker took 1.47 s on NACA 23 with the layer and 187.65 s without, so its 16-page rate mostly measures the layer path.

**Other edits.** 4.6 now names Kimi-K2.6 at 85.00 as the best VLM in PP-OCRv6 Table 7. 4.9 now states the inferred Claude tier from the row "Claude 4.7 and later models", `claude_vision.md` line 1264. Section 3, TeleOCR row, no longer says scorer settings move numbers. The paper and the leaderboard differ by 0.04, and no run isolates the settings. Overlap table: two rows added, Module 1 5.5 and Module 3 7.5. Gap list: rank 9, tables across pages, and rank 10, per-page routing.

### 13.2 Spot checks

Each check opened the saved file named and matched the number and its conditions. Result "match" means the number, the unit and the condition all agree.

| # | Anchor | File checked | Result |
|---|---|---|---|
| 1 | 4.1 docling `naca_p23` cells 0.55, marker 0.544 | `parsers/runs/scores_all.txt` lines 7, 25 | match |
| 2 | 4.1 no layer: marker 0.944, MinerU standard 0.994, with layer 10/10 | same, lines 26, 52, 53 | match |
| 3 | 4.1 PyMuPDF, pymupdf4llm, unstructured `auto` take the layer | same, lines 79, 97, 126: 0.55 each | match |
| 4 | 4.3 Tesseract Census scan 12/37 rows, 15/25 stars | same, line 112 | match |
| 5 | 4.3 "21" for "2.1", "#70", "$57" | `out/tesseract_300dpi/census_p21_scan200.md` lines 20, 21, 30. Gold `census_p21.json` has "2.1" and "*7.0" | match |
| 6 | 4.3 docling scan 37/37, 25/25 | `scores_all.txt` line 4 | match |
| 7 | 4.3 NACA no-layer digit NED 0.037, 0.700, 0.692, 0.722, docling cells 0.081 | same, lines 116, 8, 136, 35 | match |
| 8 | 4.3 docling drops 4 of 8 values in "No high school diploma" | `out/docling_default/census_p21.md` line 50: 4 values, 4 empty cells | match |
| 9 | 4.6 marker digit changes .3809→.3909, .3759→.8759, .8071→.6071, .7532→.7592 | `out/marker_default_ngl0/naca_p23_notext.md` lines 8 to 10 against `gold/naca_p23_typed.txt` lines 2 to 4 | match |
| 10 | 4.2 docling `OcrMode.DEFAULT` and comments | `envs/docling/.../pipeline_options.py` lines 115, 118, 225 | match |
| 11 | 4.2 marker mode by device | `envs/marker/.../converters/pdf.py` lines 131 to 133 | match |
| 12 | 4.2 MinerU `tier="standard"`, CLI "first 10 pages" | `mineru/parser/__init__.py` line 31, `cli/commands/parse.py` line 89 | match |
| 13 | 4.2 docling log "rapidocr with torch" | `parsers/runs/docling_default.log` line 35 | match |
| 14 | 4.7 granite `use_cache: false`, 189.3 s, 2.5 s at 66.57 tokens/s | `hf_cache/.../generation_config.json` line 7, `vlm_run1.log` line 5, `vlm_bf16c.log` line 6 | match |
| 15 | 4.6 table dropped on 6 of 20 clean pages, 178.2 s for 60 pages, one loop | `vlm_set.log`, reviewer recount: clean output 50+ tokens shorter than its scan pair on p003, p005, p007, p010, p015, p019 | match, by token proxy |
| 16 | 4.4 TEDS 0.9921 | no saved output. Hand arithmetic from `omnidoc_teds_f133a71.py` and `scorers.py` | agrees, output not saved |
| 17 | 4.4 Horn and Keuper r 0.684, 0.698, 0.939, 518 pairs, 1,554 ratings | `arx_2603.18652.txt` lines 276, 696, 849, 1074, 1086 | match |
| 18 | 4.5 TeleOCR 96.87, timeouts 1200 s, span 200, penalty 0.05 | `arx_2608.12898.txt` lines 19, 1883 to 1886 | match |
| 19 | 4.5 leaderboard 96.91, defaults 300, 420, 10, 0.10 | `omnidoc_readme.md` line 543, `configs/end2end.yaml` lines 30 to 33 | match |
| 20 | 4.5 Mistral 85.20, 93.07, "internal reproductions", 72%, 600+ | `mistral_ocr4_news.txt` lines 166, 203, 216, 234 | match, sourcing reworded |
| 21 | 4.5 PureDocBench 21,353 and 2,580, 12.08% | `arx_2605.07492.txt` lines 36, 37 | match |
| 22 | 4.5 PaddleOCR-VL-1.6 TEDS 94.76, ParseBench Tables 67.77 | `omnidoc_readme.md` line 568, `parsebench_repo/leaderboard.csv` | match |
| 23 | 4.6 olmOCR-Bench 7,019 tests, 1,403 PDFs, type counts | reviewer recount over `olmbench/*.jsonl`: 7019, 1403, math 3385, order 1061, table 1020, absent 823, present 721, baseline 9 | match |
| 24 | 4.6 `tests.py` line 518 quote | `olmocr_repo/olmocr/bench/tests.py` line 518 | match |
| 25 | 4.6 PP-OCRv6 Table 7 | `arx_2606.13108.txt` lines 1001 to 1022 | match. Kimi-K2.6 85.00 added |
| 26 | 4.6 Gardella et al., Berrutti dataset, 175 pages, median 1.72%, mean 11.17% | `arx_2607.24077.txt` lines 206, 399, 400 | match |
| 27 | 4.8 Textract $1.50 and $15, Layout $4, publication 2026-09-11 | `aws_textract_priceapi_useast1.json` | match |
| 28 | 4.8 Azure Read $1.50, Layout $10. Google OCR $1.50 after 1,000 free, Layout $10 | `azure_retail_eastus.json` S0 meters, `gcp_docai_pricing.txt` lines 35 to 40, 110 to 111 | match |
| 29 | 4.9 Gemini 3.1 Flash-Lite $0.25 and $1.50, 560 PDF tokens, 258 on the other page, 3.8 Flash promo | `gemini_pricing.txt` lines 890 to 905, 243 to 250, `gemini_media-resolution.txt` line 597, `gemini_document-processing.txt` line 4160 | match |
| 30 | 4.9 Claude tiers, Haiku 4.5 $1 and $5, Sonnet 5 $2 and $10 | `claude_vision.md` lines 1258 to 1265, `claude_pricing.md` lines 29, 33 | match |
| 31 | 4.10 ViDoRe V3 54.7, 52.1, 54.5, F1 0.602 and 0.065 | `2601.08620.txt` lines 1094 to 1096, 1412 to 1415, Table 3 rows | match. The best model scored 0.089 |
| 32 | 4.11 Table 9 HR BM25S 49.6, ColModernVBERT 47.0, English averages 53.0, 53.0, 50.7. Table 1 BM25S 20.3 | same file, Table 9 rows and Table 1 BM25S row | match |
| 33 | 4.11 and 4.12 run numbers, p-values and CIs | `vision-retrieval/lab/score_cmvb.log` | match |
| 34 | 4.10 884.95 vectors, 226,547.5 bytes, 773 bge tokens, 71.7% over 512 | `score_cmvb.log` JSON block, `emb/bge_meta.json` | match |
| 35 | 4.10 ColPali 1,030 vectors | `2407.01449.txt` | not in the paper. Corrected |
| 36 | 4.12 pool 3 keeps 97.8%, Shift outlier. Table 5 0.39, 7.22, 3.71 s | `2407.01449.txt` lines 625, 627, 1239 to 1249 | match |
| 37 | 4.12 Light-ColPali 98.2%, 11.8%, about 72 A100 hours | `2506.04997.txt` lines 30, 31, 154 | match |
| 38 | 4.11 Lost in OCR nDCG@5 0.5468 against 0.3242 at level 0 | `2505.05666.txt` lines 691, 693 | match |
| 39 | 4.13 OHRBench quote, top 2 chunks of 1,024, generators | `2412.02592.txt` lines 637 to 645, 853, 888 | match |
| 40 | 4.15 limits: Textract 1 page, 3,000 pages, 500 MB. Google 15 pages. Claude 600 and 100 pages, 32 MB. Mistral, Unstructured, Gemini 50 MB | `aws_limits.txt` lines 20 to 24, `gcp_limits.txt`, `claude_pdf.md` lines 32 to 34, `gaps/mistral_capabilities_document_ai_basic_ocr.txt`, `unstr_limits.md` line 18, `gemini_document-processing.txt` | match |
| 41 | Section 7a MinerU licence lines, HF tags, default weights repo | `gaps/mineru_LICENSE_4.0.6.md`, `gaps/hfapi_*.json`, `envs/mineru/.../model/registry.py` line 70 | match |
| 42 | 4.2 marker README 76.0 and 66.6 on one B200 | `hosted-cost/marker_readme_v2.0.0.md` lines 458, 460, 468 | match |
| 43 | 4.9 output tokens 1,682, 3,820, 3,296, 3,590, marker 8,236 | `gaps/out_tokens.txt` | match |
| 44 | Section 3 dates: marker 2.0.0 2026-07-20, MinerU 3.1.0 2026-04-17, 4.0.0 2026-09-16, docling 2.130.0 and unstructured 0.27.8 2026-09-22, PaddleOCR 3.0.0 2025-05-20 | `hosted-cost/pypi_*.json` upload times | match |
| 45 | Section 5 PP-StructureV3 42.8 to 149.4 s | `run_paddle_structurev3*.log` | match |
| 46 | Gap 1 partial output: 0.582 s, 174.7 s, 0.763 s, 38.7 s, 243,679 bytes | `gaps/scan_lab_run.log`, `gaps/scan_out/degrade_meta.json` | match |

### 13.3 Arithmetic recomputed

- **Per-page laptop rates.** The reviewer divided each `tp_naca_16p` time in `DI/parsers/runs/<parser>.json` by 16. Tesseract 41.12 → 2.57 s. docling 96.18 → 6.01 s. MinerU standard 146.43 → 9.15 s. marker 558.14 → 34.88 s. MinerU flash 23.28 → 1.46 s. MinerU basic 79.62 → 4.98 s. unstructured `hi_res` 46.91 → 2.93 s. PaddleOCR 455.83 → 28.49 s. PyMuPDF 0.02 → 0.001 s. All match.
- **300-page times.** rate × 300 ÷ 60. Tesseract 12.85, printed 12.8. docling 30.05, printed 30.1. MinerU standard 45.75, printed 45.8. marker 174.5. flash 7.3. basic 24.9. unstructured 14.65, printed 14.7. PaddleOCR 142.5. The Tesseract value rounds to 12.9 by hand. Python printed 12.8 from binary floating point. The difference does not change "about 13 min". Single-scan ranges: marker 180.37 × 5 = 902 and 215.45 × 5 = 1,077. Match.
- **Cloud stand-in.** $0.58 × s ÷ 3.6: Tesseract 0.41, docling 0.97, MinerU standard 1.47, marker 5.62. Machines for 1M pages: s × 10⁶ ÷ 2,592,000: 0.99, 2.32, 3.53, 13.46. All match. The c7g.4xlarge price 0.58 is in `aws_ec2_useast1_linux.json`, publication 2026-09-21.
- **VLM rows.** ($in × (image + 100) + $out × output) × 1,000 ÷ 10⁶. Flash-Lite 2.415 and 5.565. 3.8 Flash 6.12 and 13.995. gpt-6-luna 1.0096 and 2.0596. Haiku 4.5 9.16 and 19.66, corrected in section 14 to 9.10 and 19.60. Sonnet 5 20.628 and 41.628. All match the table. 300 pages at 3,600 tokens for Sonnet 5: 12.49. Match.
- **Section 1 hosted rows.** $1.50 × 0.3 = $0.45. $4 × 0.3 = $1.20. $15 × 0.3 = $4.50. gpt-6-luna 1.01 × 0.3 = $0.30. Match.
- **4.9 share.** 2.25 ÷ (0.165 + 2.25) = 93.2%. Match.
- **4.10 ratio.** 226,547.5 ÷ 1,536 = 147.5. Printed "147 times". Acceptable.
- **4.15 synthetic size.** 300 × 243,679 = 73.1 MB. Match.

### 13.4 Overlap check

The reviewer ran `grep '^## '` on all phase files of the four built modules. Every heading quoted in the overlap table exists with the quoted number and text. The Module 1 headings "1.1 — Tokens" and "4.4 — Quantization" are shortened forms of the full headings. The coverage-file quotes at `module-03-coverage.md` lines 769, 867 and 888 match. Two missing links were added: Module 1 5.5 and Module 3 7.5.

### 13.5 History in concept sections

No history of the field was found in 4.1 to 4.15. The "Dropped claim" paragraph in 4.5 is research process, not history. It repeats section 7, conflict c6, and the phase writer can drop it.

### 13.6 What the reviewer could not check

- The four outputs that were only printed: TEDS 0.9921 and the self-test values, `llama-bench` 6.58 and 70.42, the page-fingerprint table, and the noise-probe rows. No lab runs were allowed.
- Whether the noise-probe 2% row equal to the no-stemmer baseline is a coincidence.
- The OmniDocBench leaderboard rows' authorship, the ViDoRe V3 "six query languages" remark, and the DocDeg size of 4,196 documents. These were not opened.
- The granite-docling "identical text" claim in 4.7. The logs show the same token count and character count, 169 and 388, but the texts were not compared.
- Whether the 1,731-token Metal observation in the parsers report came from the same run as `run_marker_default.log`.

### 13.7 Concepts whose evidence is weak for teaching

- **4.14 page fingerprints.** The best evidence is a printed table with no saved output. The inputs exist and the script runs in under 1 s. Re-run before teaching.
- **4.13 mechanism.** The noise-probe numbers are not saved, and one row has an unexplained match with another baseline. OHRBench uses 2024 parsers. Gap 2 is the fix.
- **4.7 Metal slowdown.** Both numbers that show it, `llama-bench` and the 4.5-minute page, are unsaved. The CPU timings are saved.
- **4.8 table meters.** Prices are verified, but no hosted service ran on any test page. The loss on scans is inferred from product names only.
- **4.3 and 4.6.** Every parser table result is n = 1 page, and the VLM failure set is one 258M model on synthetic pages. They can teach the kinds of failure, not rates or rankings.

## 14. Corrections found while building the course

The five phases re-ran the unsaved anchors and several labs on 2026-09-23. The list below names what they overturned or refined, and the saved run for each. Run files are in `scratchpad/runs/` of the session scratchpad.

| # | Dossier claim | What the course found | Evidence |
|---|---|---|---|
| 1 | 4.7: `llama-bench` Metal 6.58, CPU 70.42 tokens per second | Overturned. Metal 138.48 ± 0.54, CPU 72.36 ± 1.38, same build b11125 and model | `document-ingestion_p03_llama_bench.txt`, `_llama_bench_pp.txt` |
| 2 | 4.7 and section 5: marker on default Metal did not finish one scan in 4.5 min, so set `LLAMA_CPP_NGL=0` | Overturned. One page, back to back: CPU 199.16 s, Metal 68.88 s, identical bytes. A GPU encode overlapped the CPU run. Metal alone earlier: 64.26 s. The rule is withdrawn. Section 5 CPU rates stay, labelled CPU | `document-ingestion_p03_marker_cpu_vs_metal.txt`, `document-ingestion_p03_marker_metal.txt` |
| 3 | 4.7: granite-docling 189.3 s against 2.5 s | Refined. Back to back at a similar load average: 94.9 s against 3.5 s, 27 times. The 189.3 s run overlapped a GPU encode, inferred from file times | `document-ingestion_p03_granite_cache.txt` |
| 4 | 4.9 and section 5: Claude Haiku 4.5 $9.16 to $19.66 per 1,000 pages | Corrected to $9.10 to $19.60. `cost_calc.py` computes 1,496 image tokens for a Letter page at 150 dpi and reproduces Claude's resize table | `document-ingestion_p03_cost_calc.txt` |
| 5 | 4.9 and section 5: Gemini 3.1 Flash-Lite $2.42 to $5.57 | Exact values $2.415 to $5.565. The scripts print 2.41 and 5.57 | `document-ingestion_p03_cost_calc.txt` |
| 6 | 4.10: an HR page image costs about 1,568 and 4,784 Claude tokens | Those are the tier caps. The documented rule gives about 1,551 and 4,756. Inferred from the rule, not a measured count | `document-ingestion_p04_page_bytes.txt` |
| 7 | 4.10 and section 5: ColModernVBERT 0.81 s per page at load 3.4 | The probe log records no load. Phase 4 measured 0.925 s per page on 300 scans at load 10.3 | `document-ingestion_p04_scan_lab.txt` |
| 8 | Section 5: Apple Vision OCR 1.08 s per page at load about 17 | Phase 4 measured 0.607 s per page on 300 clean pages at load 7.9 | `document-ingestion_p04_scan_lab.txt` |
| 9 | 4.11: the V3 abstract's claim is a cross-language average | Wrong. English-only Table 9 also shows larger visual models ahead, such as Jina-v4 63.9 on images against 56.7 on text | ViDoRe V3 Table 9, saved paper text |
| 10 | 4.11 and gap 1: no completed scan comparison | Completed. On 300 synthetic scans with 219 English queries, no paired difference was significant | `document-ingestion_p04_scan_score.txt` |
| 11 | 4.12: the HR run did not split by text density | Measured. The loss followed the compression level more than text density. An fp16 rescore of the top 100 recovered the sign-bit loss | `document-ingestion_p04_hr_score.txt` |
| 12 | 4.6: MinerU standard changed .3865 to .3885 | Refined. Tesseract and marker wrote the same .3885, so MinerU made none of its own in the 10 gold rows. MinerU left out 46 of the 90 rows the page prints | `document-ingestion_p03_shared_misread.txt`, `document-ingestion_p03_physics_check.txt` |
| 13 | 4.6: most bad-scan outputs repeated the title | Refined. 9 of 20 outputs were too long and 11 almost empty, so bad scans give omission as well as repetition | `document-ingestion_p03_eval_set.txt` |
| 14 | 4.6: "Berrutti et al." | Wrong author. The paper is by Gardella et al. Berrutti is the dataset | arXiv 2607.24077, saved paper text |
| 15 | 4.13: the noise-probe 2% row equals the no-stemmer baseline, not explained | Explained. The means agree by chance. 89 of 300 queries differ. The 2% drop was significant on 1 of 3 seeds | `document-ingestion_p01_noise_stemmer_check.txt`, `document-ingestion_p01_noise_seeds.txt` |
| 16 | 4.13: OHRBench generators Llama-3.1-8B and Qwen2-7B | Confirmed for the 14% figure, paper section 4.2. The paper uses a third generator, Qwen2-72B, in other experiments | OHRBench saved text, lines 662 and 853 |
| 17 | 4.4 TEDS 0.9921 and 4.14 fingerprint table, output not saved | Confirmed and saved. The simulator's wall time was 5.8 s, not 2.0 s | `document-ingestion_p02_teds_p001.txt`, `document-ingestion_p05_page_hash.txt`, `document-ingestion_p05_page_hash_sim.txt` |

Summary: the Metal rule and the Haiku prices were wrong, and the 4.11 wording was too strong. The unsaved anchors now have run files.
