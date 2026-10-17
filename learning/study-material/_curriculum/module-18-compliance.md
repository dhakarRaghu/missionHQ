# Module 18: Compliance and auditability

Research date: 2026-09-25. Status: research dossier, not course material. Reviewed by an independent reviewer on 2026-09-25. Section 10 lists every correction.

Module question: **A regulator asks you to show why the agent did what it did, nine months ago. What do you hand over?**

**This is not legal advice.** This dossier is study material for an engineer. It reads legal texts and official guidance, and it reports what they say. A lawyer must check any decision about a real system.

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-25 in `scratchpad/reports/`: `research_compliance_law.md` and `research_compliance_evidence.md`. Below they are the law report and the evidence report.
- **Path short names.** `L/` means `scratchpad/research_compliance/law/`. `LP/` means `L/proto/`. `E/` means `scratchpad/research_compliance/evidence/src/`. `EP/` means `scratchpad/research_compliance/evidence/proto/`. `D18/` means `scratchpad/dossier_m18/`, the dossier author's notes. Line numbers in `L/` and `E/` refer to the saved `.txt` or `.md` file.
- **Other inputs.** The Module 18 brief in `_curriculum/README.md` lines 355 to 372. The rules in `scratchpad/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`. The structure of `_curriculum/module-10-memory.md`.
- **Work done for this dossier.** No lab ran. No URL was fetched. The dossier author did four read-only things:
  1. Re-grepped every section 4 anchor in its saved file. Script `D18/anchor_check.py`, output `D18/anchor_check.txt`. Section 4 ends with the result.
  2. Ran the self-tests of both saved prototypes. Output `D18/selftest_law.txt` and `D18/selftest_evidence.txt`. Both pass. Python 3.9.6, Apple M4 Pro, 2026-09-25.
  3. Recomputed every date difference and every proof size. Script `D18/recompute.py`, output `D18/recompute.txt`: 30 of 30 checks match.
  4. Read the saved Anthropic deprecations page again. It settles one item the evidence report left as not checked. Section 7, conflict d.

### Labels

Every claim carries two labels.

| Label kind | Label | Meaning |
|---|---|---|
| Source kind | **Legal text** | Words of a regulation, a Commission decision or a court document, from EUR-Lex |
| Source kind | **Official guidance** | Commission or EDPB guidelines. Or a national data protection authority, such as the CNIL in France or the ICO in the UK |
| Source kind | **Commentary** | Reasoning in this dossier or a report. Also a built module, a draft standard, an auditor's blog post, or a vendor page |
| Evidence status | **verified** | The file and line, or a run output, is named next to the claim |
| Evidence status | **verified by run** | A research agent ran a script on the learner's Apple M4 Pro Mac on 2026-09-25. The output file is named |
| Evidence status | **inferred** | The basis is named, and the check that would confirm it |
| Evidence status | **not checked** | No evidence. The check that would settle it is named |

**Vendor claim** marks what a company says about its own product. **Auditor source** marks a named auditor writing on a blog.

### Terms used in the whole dossier

- **AI Act**: Regulation (EU) 2024/1689. **Omnibus**: Regulation (EU) 2026/1744, which amends the AI Act.
- **High-risk system**: an AI system classed as high-risk under Article 6 of the AI Act. Annex III lists use areas such as employment and credit. Annex I lists products under other EU safety laws.
- **Provider**: the organisation that develops the AI system and places it on the market. **Deployer**: the organisation that uses it.
- **GDPR**: Regulation (EU) 2016/679. **Controller**: the organisation that decides why and how personal data is processed. **Processor**: an organisation that processes personal data for a controller. A model provider is often a processor.
- **Audit record**: one stored record of one agent decision, written at decision time.
- **Hash chain**: a log where each record stores the hash of the record before it.
- **Anchor**: a copy of the latest hash or of a signed tree root. It is kept where the log writer cannot change it.
- **Merkle tree**: a tree of hashes. A short proof shows that one record is in the tree. RFC 9162 defines the version used here.
- **WORM storage**: write once, read many. Storage that refuses to overwrite or delete a file before a set date.
- **Replay manifest**: the list of versions and hashes needed to run a past decision again.
- **Deletion certificate**: a record of which copies of a person's data were deleted. It says how, when, and how the deletion was checked.
- **Crypto-shredding**: encrypting data with a key and deleting the key, so the stored bytes can no longer be read.
- **Transfer**: in GDPR Chapter V, making personal data available to an organisation in a country outside the European Economic Area.
- **Adequacy decision**: a Commission decision that a country protects personal data well enough for transfers without extra safeguards.
- **SCCs**: standard contractual clauses, Commission Implementing Decision (EU) 2021/914. A contract that allows a transfer where no adequacy decision exists.
- **DPF**: the EU-US Data Privacy Framework, Commission Implementing Decision (EU) 2023/1795.
- **SOC 2 Type 2**: an auditor's report on whether an organisation's controls worked over a period.

---

## 1. Purpose and the module question

Module 8 taught which fields one audit record needs. Module 10 taught how to delete a person's data from every copy. It proves the deletion with an audit that prints zero. This module adds two things: the legal duty, and the evidence that still works nine months later.

The short answer: **hand over the records you wrote on the decision day. Add proof that they were not changed, and the rules that applied on that day.** The law names almost no fields. So the record must be designed from what a reviewer will ask.

"Nine months ago" from 2026-09-25 is 2025-12-25. Recomputed in `D18/recompute.txt`. On that date no AI Act log duty and no Article 50 duty applied. Article 50 started on 2 August 2026. The high-risk log duties start on 2 December 2027 at the earliest. The GDPR applied. Some AI Act duties also applied: Article 4 on AI literacy and the Article 5 prohibitions, from 2 February 2025. Neither asks for a log. Inferred from the dates in 4.1 and 4.2. This date matters, because the reviewer judges the decision under the rules in force when it was made.

| Part of the question | Short answer | Where |
|---|---|---|
| Who may ask, and on what basis | A data protection authority under GDPR Article 58(1)(a). AI Act log access under Article 21(2) only from 2 December 2027 | 4.12 |
| Which duty applied on the decision day | GDPR duties to demonstrate compliance. AI Act Articles 4 and 5, which ask for no log. Article 50 only for decisions on or after 2 August 2026. High-risk log duties not before 2 December 2027 | 4.1, 4.2 |
| Does the record still exist | Only if retention was set above nine months. The AI Act floor is six months, and it yields to data protection law | 4.3 |
| What the record must contain | The law names fields only for remote biometric identification. Use the Module 8 fields, plus versions, input hashes and the processing region | 4.4 |
| Proof the record was not changed | A hash chain plus an anchor stored outside the writer's reach. A chain alone fails against a rewrite | 4.5, 4.6 |
| Can you run the decision again | Often not. The model ID may be retired. The stored transcript and its hashes are the evidence | 4.7 |
| Where the person's data went, and whether it was deleted | A deletion certificate dated by the last copy, not the API delete. Link Module 10 for the mechanism | 4.8, 4.9 |
| Which region processed it | GDPR controls transfers, not storage location. Remote access counts | 4.10 |
| What an auditor will test | A sample event, rebuilt from your own records, over a period. A vendor's 90-day log does not cover it | 4.11 |

Summary: store versions, hashes and an anchored chain on the decision day. Keep them past nine months. Keep the personal part erasable.

---

## 2. Scope

### 2.1 In scope

- AI Act Articles 4, 5, 12, 18, 19, 21, 26, 50, 86 and 111. Their dates after the omnibus. Commission guidelines on Article 50 and the transparency code of practice.
- GDPR Articles 5, 12, 15, 17, 19, 30, 31, 33, 44 to 49 and 58(1)(a), and Recital 39. Article 33 has no concept yet, gap 17.
- Retention periods: legal floors, one national authority's range, and the periods you must choose.
- Tamper evidence: hash chains, anchors, Merkle proofs, WORM storage, managed ledgers.
- Replay nine months later: model retirement rules and what to pin.
- The deletion certificate and the vendor retention windows that set its date.
- Data residency and transfers: EDPB transfer criteria, adequacy, the DPF and its appeal, SCCs.
- What SOC 2 and ISO/IEC 42001 auditors test.

### 2.2 Out of scope, and the owner of each item

| Topic | Owner |
|---|---|
| The fields of one agent audit record, the actor chain, the transaction id, the basic hash chain | Module 8, built section 5.3 |
| The deletion mechanism: copies an API delete leaves, lineage, the zero audit, the survivor check, backups in SQLite | Module 10, built sections 4.1 to 4.3 |
| Deleted vector bytes in index files, HNSW tombstones, pgvector `VACUUM` | Module 3, built section 7.3 |
| Telemetry: trace pipelines, OpenTelemetry names, sampling, per-request version fields | Module 15, phase files `observability-ops/observability-ops-phase-02-pipeline.md` section 2.1 and `observability-ops-phase-04-incidents.md` section 4.2. Dossier concepts 4.3 and 4.8 |
| Attacks on agents: injection channels, approval binding, protocol attacks | Module 16, phase files in `security/`. Section 5.4 of `security-phase-05-supply-chain.md` hands the consent-record and log attacks to this module, 2.3 |
| The price of data-residency endpoints | Module 14, dossier concept 4.15 |
| Classification of a product as high-risk | Counsel. This dossier states the rules only |
| Financial-services log periods under AI Act Articles 19(2) and 26(6) | Not covered. Not checked |
| Human approval screens | Module 19, not built |

### 2.3 Overlap with built modules

Headings were read with `grep '^## '` on `study-material/*/*.md` on 2026-09-25. Modules 13 and 14 have no built phases. Their dossiers in `_curriculum/` were read instead. **Reviewer correction.** Modules 15 and 16 now have phase files. `observability-ops/` has phases 01 to 04 and `security/` has phases 01 to 05, all dated 2026-09-25. They are still being written, so re-check their headings before a phase links them. Handoffs to this module are verified in these files:

- `agent-protocols/agent-protocols-phase-05-proof.md` line 46: "Retention, legal hold and regulatory audit belong to Module 18 (planned)."
- `memory/memory-phase-04-deletion-scope.md` lines 448 and 465: the legal duty to keep or delete. Also how long a backup may keep a fact.
- `memory/memory-phase-01-writers-recall.md` line 248: how long the turn log may be kept.
- `retrieval-internals/retrieval-internals-phase-07-freshness.md` line 439: "Right to erasure as a legal process belongs to Module 18."
- `_curriculum/module-15-observability-ops.md` line 89, `module-16-security.md` line 53 and `module-10-memory.md` line 87.
- Added by the reviewer. `observability-ops/observability-ops-phase-02-pipeline.md` line 147: "Module 18 (planned) owns the retention and deletion duty for captured content and for ids under `app.`".
- Added by the reviewer. `security/security-phase-05-supply-chain.md` lines 436, 444 and 671: attacks on "consent records, tokens and logs" have no source in Module 16. "Full treatment belongs with audit logs in Module 18 (planned)." This dossier has no source for those attacks either. Gap 16 in section 8.

| Built heading or dossier concept | What it owns | What this module adds |
|---|---|---|
| Module 8, "5.3 — An audit record names subject, actor and decision" | Seven AIMS section 11 fields plus `actor_chain` and `token_hash`. A hash chain with a `prev` field. The `--tamper 6` break-it. It says a full rewrite "is caught only if the last hash is stored somewhere else", labelled "inferred from the construction, not run", line 456 | Runs that rewrite and a truncation, 4.5. Adds the anchor, Merkle proofs and WORM storage, 4.6. Adds the time fields a nine-month reviewer needs, 4.4. Link 5.3. Do not re-teach the fields |
| Module 8, "4.3 — The act chain is for audit, not for access" | The act chain as audit data | Nothing new. Link only |
| Module 10, sections 4.1 to 4.3. "4.1 — An API delete leaves copies the API does not show". "4.2 — Lineage lets a deletion find every copy". "4.3 — Prove a deletion with an audit that prints zero" | The mechanism, the 12-step `forget(subject)`, the survivor check, a backup list with expiry dates | The legal clock, the vendor windows that set the certificate date, and the certificate fields, 4.8. Link 4.1 to 4.3 |
| Module 10, "1.1 — Memory is a derived index, not the record" | The turn log is the record of truth | How long it may be kept, 4.3 |
| Module 3, "7.3 — Deleted is not gone" | HNSW tombstones in hnswlib, pgvector 0.8.6 `VACUUM`, a per-group key deletion idea from one preprint | The duty and the certificate. Link 7.3. Do not re-teach the bytes |
| Module 3, "7.4 — A new model invalidates every vector" | Embedding model change | The index version in the replay manifest, 4.7 |
| Module 1, "1.5 — Sampling (temperature, top_p, and the determinism myth)" and "5.5 — The run record (what to store, under which names)" | Temperature 0 is not deterministic. The run record schema | 4.7 uses both. It adds retirement dates and the Anthropic parameter deprecation |
| Module 9, "1.1 — Replay runs your code again and skips finished steps" | Workflow replay inside a durable engine | A name clash only. "Replay" in this module means running a past decision again for a reviewer |
| Module 15, "2.1 — The privacy default drops retrieval ids, not tool ids" and "4.2 — Record which change served each request". Also dossier 4.3 and 4.8 | The privacy default drops retrieval document ids. Every part that can change needs a version on the request | The same version fields, kept for nine months and hashed, 4.7. The retention and deletion duty for captured ids, 4.3 and 4.9. Link phase sections 2.1 and 4.2. Do not re-teach them |
| Module 16, "5.4 — Protocol attacks change who the server thinks is asking" | Consent and token attacks as protocol properties. It defers log attacks to this module | Nothing yet. No source for log attacks, gap 16. Link 5.4 |
| Module 14 dossier, 4.15 | "Data residency adds 10% on OpenAI models released on or after 2026-03-05", line 345 | The legal meaning of residency, 4.10. Link 4.15 for the price |
| Module 13 dossier, gap 13 | Residency as a reason to self-host, not checked there | 4.10 gives the transfer rules. The self-host decision stays open |

---

## 3. Sources, with dates, tags and versions

### 3.1 Primary legal and official sources

All fetched 2026-09-25 with `curl --max-time 60` by the research agents. HTTP status as recorded in the law report section 8. Peer review does not apply to legislation, court documents or regulator guidance.

| Source | Org, date | Kind | URL | What to read | HTTP |
|---|---|---|---|---|---|
| Regulation (EU) 2024/1689, AI Act, OJ text | EU, 2024 | Legal text | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689 | Arts 12, 18, 19, 26, 50, 86, 99, 113 | 200 |
| Regulation (EU) 2026/1744, Digital Omnibus on AI | EU, 8 July 2026, OJ 24.7.2026 | Legal text | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32026R1744 | Art 1 points (39) and (40), Art 4 | 200 |
| OEIL procedure 2025/0359(COD) | European Parliament | Official record | https://oeil.secure.europarl.europa.eu/oeil/en/procedure-file?reference=2025/0359(COD) | "Procedure completed" | 200 |
| OEIL procedure 2025/0360(COD), GDPR omnibus | European Parliament | Official record | https://oeil.secure.europarl.europa.eu/oeil/en/procedure-file?reference=2025/0360(COD) | Stage | 200 |
| OEIL procedure 2025/0130(COD), Omnibus IV | European Parliament | Official record | https://oeil.secure.europarl.europa.eu/oeil/en/procedure-file?reference=2025/0130(COD) | Stage | 200 |
| Guidelines on Article 50, annex to C(2026) 5054, 20.7.2026 | European Commission | Official guidance | https://ec.europa.eu/newsroom/dae/redirection/document/131215 | Paras 38, 73, 148 | 200 |
| Code of Practice on Transparency of AI-generated Content page | European Commission | Official guidance | https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content | Status, signatories | 200 |
| Regulation (EU) 2016/679, GDPR | EU, 2016 | Legal text | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679 | Arts 5, 12, 15, 17, 19, 30, 33, 44 to 49, Recital 39 | 200 |
| Implementing Decision (EU) 2023/1795, DPF | European Commission | Legal text | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32023D1795 | Arts 1, 3 | 200 |
| Implementing Decision (EU) 2021/914, SCCs | European Commission | Legal text | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32021D0914 | Clauses 8.5, 8.9, 14 | 200 |
| Adequacy decisions page | European Commission | Official guidance | https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/adequacy-decisions_en | Country list | 200 |
| Judgment T-553/23, Latombe v Commission, 3 September 2025 | General Court | Legal text | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62023TJ0553 | Operative part | 200 |
| Appeal C-703/25 P, lodged 31 October 2025 | Court of Justice | Legal text | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62025CN0703 | Form of order | 200 |
| CELEX 62025CJ0703 and 62025CC0703 | EUR-Lex | Absence | judgment and AG opinion | "The requested document does not exist" | 404 |
| EDPB Guidelines 05/2021, version 2, adopted 14 February 2023 | EDPB | Official guidance | https://www.edpb.europa.eu/system/files/documents/2023-02/edpb_guidelines_05-2021_interplay_between_the_application_of_art3-chapter_v_of_the_gdpr_v2_en_0.pdf | Three transfer criteria, remote access | 200 |
| CNIL Deliberation 2021-122 of 14 October 2021 on logging | CNIL, France | Official guidance, one country | https://www.cnil.fr/fr/la-cnil-publie-une-recommandation-relative-aux-mesures-de-journalisation | Retention range | 200 |
| ICO "Right to erasure" | ICO, UK | Official guidance, UK GDPR | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/right-to-erasure/ | Backup systems | 200 |
| NIST SP 800-88 Rev. 2, September 2025 | NIST | Official guidance, US | https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-88r2.pdf | 4.6, Appendix C | 200 |
| ISO/IEC FDIS 24970, AI system logging | ISO/IEC JTC 1 | Draft standard, commentary | https://isrsm.gov.mk/en/project/show/iso:proj:88723 is a national mirror. iso.org returned 403 | Stage 50.20 | 200 on the mirror |
| ISO/IEC 42001:2023 | ISO/IEC JTC 1/SC 42 | Standard, paid, not read | https://www.iso.org/standard/42001 | Metadata only, read in a browser | 403 to curl |

### 3.2 Technical, vendor and auditor sources

All fetched 2026-09-25. Status from `scratchpad/research_compliance/evidence/http_status_2026-09-25.txt`. None is peer reviewed. RFC 9162 is an IETF Experimental RFC.

| Source | Org, date or version | Kind | URL | HTTP |
|---|---|---|---|---|
| RFC 9162, Certificate Transparency 2.0 | IETF, December 2021, Experimental | Standard | https://www.rfc-editor.org/rfc/rfc9162.txt | 200 |
| transparency-dev/merkle test vectors | commit `fbbcd741` | Source code | https://raw.githubusercontent.com/transparency-dev/merkle/fbbcd741c3d1c69d8498487baa8edc9e5824847c/testonly/constants.go | 200 |
| Trillian README | Google, tag v1.8.0 | Source docs | https://github.com/google/trillian | 200 |
| Tessera README | transparency-dev, tag v1.0.4, 2026-07-14 | Source docs | https://github.com/transparency-dev/tessera | 200 |
| SQL ledger overview | Microsoft | Vendor docs | https://learn.microsoft.com/en-us/sql/relational-databases/security/ledger/ledger-overview | 301, then 200 |
| QLDB end of support | AWS Japan blog, 2024-10-08 | Vendor blog | https://aws.amazon.com/jp/blogs/news/migration-from-amazon-qldb/ | 200 |
| Replace QLDB with Aurora PostgreSQL, Japanese translation of a 2024-07-18 post | AWS | Vendor blog | https://aws.amazon.com/jp/blogs/news/replace-qldb-with-amazon-aurora-postgresql/ | 200. English URL redirects away |
| QLDB developer guide | AWS | Absence | https://docs.aws.amazon.com/qldb/latest/developerguide/what-is.html | 404 |
| S3 Object Lock | AWS | Vendor docs | https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html | 200 |
| Model deprecations | Anthropic | Vendor docs | https://platform.claude.com/docs/en/about-claude/model-deprecations | 200 |
| Model IDs and versions | Anthropic | Vendor docs | https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions | 200 |
| Deprecation commitments, 2025-11-04 | Anthropic | Vendor post | https://www.anthropic.com/research/deprecation-commitments | 200 |
| Deprecations | OpenAI | Vendor docs | https://developers.openai.com/api/docs/deprecations | 200 |
| Model retirements, Azure OpenAI in Foundry | Microsoft | Vendor docs | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements | 200 |
| Model lifecycle | AWS Bedrock | Vendor docs | https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html | 200 |
| Model versions | Google Cloud | Vendor docs | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions | 200 |
| Gemini API deprecations | Google | Vendor docs | https://ai.google.dev/gemini-api/docs/deprecations | 200 |
| Data deletion, Backups overview | Pinecone | Vendor docs | https://docs.pinecone.io/guides/production/data-deletion | 200 |
| Optimizer, Snapshots | Qdrant, v1.19.1 | Vendor docs | https://qdrant.tech/documentation/ops-optimization/optimizer/ | 200 |
| Vector index config, Backups | Weaviate, v1.39.6 | Vendor docs | https://docs.weaviate.io/deploy/configuration/backups | 200 |
| pgvector CHANGELOG at v0.8.6 | pgvector | Source docs | https://raw.githubusercontent.com/pgvector/pgvector/v0.8.6/CHANGELOG.md | 200 |
| Routine vacuuming | PostgreSQL | Docs | https://www.postgresql.org/docs/current/routine-vacuuming.html | 200 |
| 2017 TSC, revised points of focus 2022 | AICPA | Landing page only. PDF needs an account | https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022 | 200 |
| Trust services criteria | Linford & Co, audit firm | Auditor source | https://linfordco.com/blog/trust-services-critieria-principles-soc-2/ | 200 |
| Selecting your SOC 2 Type 2 period | Compass IT Compliance | Compliance firm | https://www.compassitc.com/blog/selecting-your-soc-2-type-2-observation-period | 200 |
| How auditors test | Strike Graph | Vendor blog | https://www.strikegraph.com/blog/how-auditors-test-and-what-to-expect | 200 |
| ISO 42001 evidence, Preet Dhatt, 2026-09-03 | Teleport blog | Auditor source on a vendor blog | https://goteleport.com/blog/iso-42001-audit-evidence/ | 200 |

### 3.3 What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-07-31 | Amazon QLDB support ended | AWS Japan blog, `E/qldb_jp_blog.txt` line 21 | The one managed AWS ledger with built-in verification is gone |
| 2025-09 | NIST SP 800-88 Rev. 2 | `E/nist_80088r2.txt` | Certificate of sanitization form. Cryptographic erase for cloud storage |
| 2025-09-03 | General Court dismisses the DPF challenge, T-553/23 | `L/T553_23_judgment.txt` line 582 | The DPF stays usable for listed US organisations |
| 2025-10-31 | Appeal C-703/25 P lodged | `L/C703_25_appeal.txt` line 9 | The DPF can still fall |
| 2025-11-04 | Anthropic commits to keep model weights | `E/anth_depr_commit.txt` line 20 | Kept weights are not API access |
| 2026-04-14 to 2026-06-15 | Claude Sonnet 4 and Opus 4 retired after 62 days' notice | `E/anth_deprecations.txt` lines 173 to 185 | A logged model ID can stop working inside nine months |
| 2026-06-10 | Final transparency code of practice | `L/cop_page.txt` line 109 | The recognised way to show Article 50(2) and (4) compliance |
| 2026-06-11 | OpenAI notice: GPT-5 and o3 snapshots shut down 2026-12-11 | `E/openai_deprecations.txt` lines 774 to 779 | About six months' notice |
| 2026-07-08, OJ 2026-07-24 | Omnibus adopted. High-risk Sections 1 to 3 move to 2 December 2027 and 2 August 2028 | `L/omnibus_32026R1744.txt` lines 617 to 621 | AI Act log duties are not in force today |
| 2026-07-20 | Commission guidelines on Article 50 | `L/guidelines_art50.txt` line 11 | Says what counts as disclosure. No logging duty |
| 2026-08-02 | Article 50 applies | `L/aiact.txt` line 2198 | The first AI Act duty that touches most agent products |
| 2026-08-28 | ISO/IEC FDIS 24970, AI system logging, at stage 50.20 | `L/isrsm_24970.txt` lines 83 to 89 | A future field model. Not law |
| 2026-09-07 | New Bedrock lifecycle policy | `E/bedrock_lifecycle.txt` | Legacy periods of 6 months or 45 days |

### 3.4 Versions to pin, checked 2026-09-25

| Tool | Version | How checked |
|---|---|---|
| Python for both prototypes | 3.9.6, macOS system Python. Standard library only | `python3 --version`, `D18/selftest_law.txt` |
| Trillian | v1.8.0, maintenance mode | evidence report section 7 |
| Tessera | v1.0.4, 2026-07-14 | `E/tessera_releases.atom` |
| transparency-dev/merkle | commit `fbbcd741` | evidence report section 7 |
| Qdrant server and `qdrant-client` | 1.19.1 | evidence report section 7 |
| Weaviate | v1.39.6 | evidence report section 7 |
| pgvector | v0.8.6, 2026-07-29 | `E/pgvector_changelog.md` |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept states its source kind and its evidence status.

### 4.1 The AI Act log duties do not apply to anyone yet. They start on 2 December 2027 at the earliest, so no AI Act log duty covers a decision made nine months ago

- **Best evidence. Legal text, verified.** The omnibus replaces Article 113 point (c): "Chapter III, Sections 1, 2, and 3, with the exception of Article 6(5), shall apply from". The dates are 2 December 2027 for Annex III systems and 2 August 2028 for Annex I systems. `L/omnibus_32026R1744.txt` lines 617 to 621. **Reviewer re-fetch, 2026-09-25.** The reviewer fetched CELEX 32026R1744 from EUR-Lex again. After whitespace and quote normalisation it matches the saved file word for word, apart from 5 spacing differences before a semicolon. The EUR-Lex consolidated text `02024R1689-20260727`, dated 27.07.2026, prints the same Article 113 point (c) dates, marked `▼M1`. Both dates verified.
- **Legal text, verified. Added by the reviewer.** Systems already on the market get a transition. The new Article 111(2): high-risk systems placed on the market before the Chapter III date fall under the regulation "only if, as from that date, those systems are subject to significant changes in their designs". Systems for public authorities must comply "by 2 August 2030". `L/omnibus_32026R1744.txt` line 601.
- **Legal text, verified. Added by the reviewer.** Other AI Act duties already applied on 2025-12-25. Chapters I and II apply from 2 February 2025, `L/aiact.txt` Article 113 point (a). That covers Article 4, AI literacy, `L/aiact.txt` lines 594 to 596, and the Article 5 prohibitions, line 599. Chapter V, general-purpose AI models, applies from 2 August 2025, point (b). None of these asks a deployer for an event log. The omnibus replaced Article 4 from 27 July 2026, `L/omnibus_32026R1744.txt` lines 166 to 170.
- **Legal text, verified.** Article 12 is in Chapter III Section 2. Articles 19 and 26 are in Section 3. `L/aiact.txt` lines 709, 785, 868, 944 and 1017.
- **Legal text, verified.** The omnibus does not amend Articles 12, 19 or 26. The law report lists the amended articles from `L/omnibus_32026R1744.txt` lines 128 to 626. The list does not name 12, 19 or 26. **Reviewer check.** The EUR-Lex document page for 32024R1689, fetched 2026-09-25, lists 88 changes by 32026R1744, all from 27/07/2026. None touches Articles 12, 19, 26 or 86. One touches Article 50: paragraph 7 is replaced, 4.2. The only other entries are four corrigenda for other language versions. No other 2025 or 2026 act amends the AI Act. The consolidated text prints Article 19(1) and Article 26(6) with the same words as `L/aiact.txt` lines 946 and 1025.
- **Legal text, verified.** The omnibus enters into force "on the third day following that of its publication", `L/omnibus_32026R1744.txt` line 759. Published 24.7.2026, lines 5 to 8. So in force on 27 July 2026. The date is recomputed in `D18/recompute.txt`. It matches "Articles 102 to 110 shall apply from 27 July 2026", line 626.
- **Official record, verified.** The separate GDPR omnibus, procedure 2025/0360(COD), is a proposal: "Awaiting committee decision", `L/oeil_2025_0360.txt` line 210. Omnibus IV, 2025/0130(COD), is "Awaiting Parliament's position in 1st reading", `L/oeil_2025_0130.txt` line 219. So the GDPR text below is current. **Reviewer re-fetch, 2026-09-25.** Both OEIL pages show the same stages today. 2025/0359(COD), the AI omnibus, shows "Procedure completed". The EUR-Lex page for the GDPR lists no amending act, only corrigenda and the two proposals 52025PC0501 and 52025PC0837.
- **Commentary, inferred.** A support chatbot or a coding agent is usually not in Annex III. Classification depends on the intended purpose. Not checked for any product.
- **Commentary, inferred.** The decision date is 2025-12-25. Article 50 did not apply then. The high-risk duties did not apply then. So no AI Act log duty or transparency duty covers it. The GDPR duties in 4.4 apply, and so do AI Act Articles 4 and 5, which ask for no log. **Reviewer correction.** The first draft said "the GDPR alone". That was wrong, see the bullet on Chapters I and II. Check: ask counsel how a regulator treats records made before a duty applied.
- **Conditions.** The dossier author read the OJ text of the AI Act plus the amending act. The reviewer then read the EUR-Lex consolidated version `02024R1689-20260727`. The consolidated text "has no legal effect", by its own header. The OJ texts are the law.

### 4.2 Article 50 applies from 2 August 2026, and it asks for disclosure and marking, not logs

- **Best evidence. Legal text, verified.** Article 113: "It shall apply from 2 August 2026." `L/aiact.txt` line 2198. The omnibus does not change that sentence. Article 50 is in Chapter IV, line 1286, so this general date applies. **Reviewer re-fetch.** The EUR-Lex consolidated text of 27.07.2026 prints "It shall apply from 2 August 2026." unchanged, marked `▼B`. Date verified.
- **Legal text, verified.** The duties are outcomes. 50(1): systems "intended to interact directly with natural persons" must tell people they talk to an AI, line 1290. 50(2): synthetic output is "marked in a machine-readable format and detectable", line 1291. 50(5): information "at the latest at the time of the first interaction or exposure", line 1295.
- **Legal text, verified. Absence.** The words "log" and "record" do not appear in Article 50, `L/aiact.txt` lines 1288 to 1297. Re-checked by the dossier author with a word count over those lines: 0.
- **Legal text, verified.** One grace period. Generative systems placed on the market before 2 August 2026 "shall take the necessary steps in order to comply with Article 50(2) by 2 December 2026". New Article 111(4), `L/omnibus_32026R1744.txt` line 605. It covers 50(2) only.
- **Legal text, verified. Added by the reviewer.** The omnibus replaces Article 50(7), `L/omnibus_32026R1744.txt` lines 309 and 310. The Commission now assesses whether adherence to a code of practice "is adequate to ensure compliance" with 50(2) and (4). If not, it may adopt an implementing act. The duties in 50(1) to 50(5) are not changed.
- **Official guidance, verified.** Commission guidelines, annex to C(2026) 5054, 20.7.2026. Paragraph 73: "providers are not required to record or keep a full provenance chain", `L/guidelines_art50.txt` line 1240. Paragraph 73 is about the marking techniques for 50(2), lines 1236 to 1241. It is not about interaction logs. Paragraph 38: disclosure only in "terms and conditions, URLs, or documentation" is not enough alone, line 784. Paragraph 148: non-signatories of the code "are expected to demonstrate how they have complied". The phrase spans lines 2360 and 2361. It names 50(2), (4) and (5), line 2361.
- **Official guidance, verified.** The Commission and the AI Board "have confirmed that the code is an adequate voluntary tool", `L/cop_page.txt` line 53. About 190 organisations signed by the end of July 2026, line 65.
- **Commentary.** A record that the disclosure was shown, with its time, is useful evidence. Article 50 does not require it. The law prototype models it as `ai_disclosure_shown` and `ai_disclosure_time`, `LP/duties.json`.
- **Legal text, verified.** Fines for breaches of Article 50 or Article 26 reach EUR 15 000 000 or 3% of worldwide annual turnover, whichever is higher. Article 99(4), `L/aiact.txt` lines 2012, 2022 and 2026. The "whichever is higher" rule applies when the offender is an undertaking. For SMEs, Article 99(6) already took the lower amount, line 2028. The omnibus adds the same lower rule for small mid-caps, new Article 99(6a), `L/omnibus_32026R1744.txt` line 595.
- **Conditions.** The README note "Article 50 applies from 2 August 2026" is correct. Re-verified as the brief asked.

### 4.3 "At least six months" is a floor, and it gives way to data protection law. A policy set to the floor has nothing to show at month nine

- **Best evidence. Legal text, verified.** Article 19(1) sets the period for provider logs. It must be "appropriate to the intended purpose of the high-risk AI system". It is "of at least six months". Then comes the exception: "unless provided otherwise in the applicable Union or national law, in particular in Union law on the protection of personal data". `L/aiact.txt` line 946. Article 26(6) sets the same floor for deployers, line 1025.
- **Legal text, verified.** Article 19(1) covers logs only "to the extent such logs are under their control", line 946.
- **Legal text, verified.** Article 18(1): technical documentation is kept for "a period ending 10 years after" placing on the market, line 931. That is documentation, not logs.
- **Legal text, verified.** GDPR has no fixed retention period. Recital 39: "time limits should be established by the controller for erasure or for a periodic review", `L/gdpr.txt` line 97. Article 5(1)(e) limits storage to what is necessary.
- **Official guidance, one country, verified.** The CNIL recommends access and action logs "pour une durée comprise entre six mois et un an", `L/cnil_journalisation.txt` line 175. Longer than one year needs a documented reason, "une durée maximale de trois ans" in common cases, line 179. When source data is kept under six months, logs must not keep it past that period, line 184. **Reviewer condition.** The CNIL range is for security logs of the "utilisateurs habilités", the staff with access to the system, line 175. The page frames it as a security measure, lines 160 to 174. Applying it to agent decision records is this dossier's inference.
- **Verified by run.** Law prototype case 2: "6-month retention fails the 9-month reviewer floor on 7 fields". `D18/selftest_law.txt`. Re-run by the reviewer on 2026-09-25: same output. The 9-month floor is the `REVIEWER-nine-months` duty in `LP/duties.json`. It is labelled commentary, not law.
- **Commentary, inferred.** Nine months is inside the CNIL range. It is above the AI Act floor. So a nine-month or twelve-month retention can be justified under both. Write the reason down under Article 5(2). Check: counsel, for your own system and country.
- **Conditions.** The AI Act floor applies only to high-risk systems and only from 2 December 2027, 4.1. The CNIL range is French guidance. Other authorities: not checked.

### 4.4 The law names audit fields only for remote biometric identification. For every other agent, the record is designed from what a reviewer will ask

- **Best evidence. Legal text, verified.** Article 12(3) is the only field list in the AI Act. It covers systems in Annex III point 1(a), remote biometric identification. It lists the period of each use, the reference database, "the input data for which the search has led to a match", and the persons who verified the result. `L/aiact.txt` lines 795 to 803.
- **Legal text, verified.** Article 12(2) names purposes, not fields: risk situations and substantial modifications, post-market monitoring, and deployer monitoring. Lines 788 to 794.
- **Legal text, verified. Absence.** The GDPR has no event-log duty. A script over `L/gdpr.txt` finds one match for `log`, `logs` or `logging`: "log-in" in Recital 57, line 134. Law report section 2.4 shows the command.
- **Legal text, verified.** The GDPR requires the controller to "be able to demonstrate compliance with, paragraph 1", Article 5(2), `L/gdpr.txt` line 486. Article 30 requires a record of processing activities. It describes activities, not events. Item (f) is "where possible, the envisaged time limits for erasure", line 884. Article 15(1)(h) gives a person "meaningful information about the logic involved" for decisions under Article 22, line 614.
- **Legal text, verified.** AI Act Article 86(1) covers a person affected by an Annex III decision. That person has a right to "clear and meaningful explanations of the role of the AI system in the decision-making procedure". `L/aiact.txt` line 1884.
- **Auditor source, verified.** An ISO/IEC 42001 auditor: "Then I pick an event and ask you to rebuild it from the records", `E/teleport_42001.txt` line 90. "I would not accept activity that cannot be tied back to the engineer", line 91. Preet Dhatt, Teleport blog, 2026-09-03. Teleport sells access software.
- **Commentary. The fields.** Module 8 section 5.3 owns the decision fields. They are subject, actor, actor chain, tool, decision, reason, time and transaction id. Link it. This module adds the fields that a nine-month gap needs:

| Nine-month condition | Why the law alone does not give it | Field | Label |
|---|---|---|---|
| The record still exists | The legal floor is six months, 4.3 | retention of 9 months or more, with a written reason | Commentary |
| The system that acted can be named exactly | Article 12(2)(a) cares about substantial modification | `system_version`, `model_id`, `prompt_version` | Commentary. Link Module 15 dossier 4.8 |
| The inputs can be rebuilt | Documents and indexes change in nine months | `retrieved_ids` with content hashes, `tool_calls` | Commentary |
| The record still makes sense after an erasure | Article 17 can remove the person's data | `subject_ref` as a pseudonym whose key can be destroyed | Commentary. 4.9 |
| The record was not changed | No legal text found requires tamper evidence | `record_hash`, `prev_hash`, plus an anchor | Commentary. 4.5 |
| A human decision is separate from the AI output | Article 86 asks for "the role of the AI system" | `decision`, `human_reviewer` | Commentary |
| The processing region is known | Article 30(1)(e) names third countries at activity level only | `processing_region`, `transfer_mechanism` | Commentary. 4.10 |

- **Verified by run.** Law prototype case 1 uses a high-risk Annex III deployer profile. It gets 7 duties, 9 missing reviewer fields, 1 retention warning and 1 erasure error. The reviewer list has 15 fields. The example schema has 6 of them. `D18/selftest_law.txt`. The dossier author recounted the fields from `LP/duties.json` and `LP/example_schema.json`: 15 and 6.
- **Conditions.** ISO/IEC FDIS 24970 may become a reference field model. Its text is paywalled. Not checked.

### 4.5 A hash chain alone does not prove the log was not rewritten. The head hash must be anchored outside the writer's reach

- **Best evidence. Verified by run.** `EP/audit_evidence.py`, six records, Python 3.9.6, Apple M4 Pro, 2026-09-25. Attack C edits record 4 and recomputes the later hashes. The plain check prints `chain only: intact, 6 records`. The anchored check prints `with anchor: record 5 hash differs from the anchored head: history rewritten`. `EP/run_output.txt`.
- **Verified by run.** Attack D drops records 4 and 5. The plain check prints `chain only: intact, 4 records`. The anchored check prints `log has 4 records, anchor says at least 6: truncated`. Same file.

| Attack | Plain chain check | Check against the anchor, size 6 |
|---|---|---|
| A. Edit record 4 in place | `record 4 content does not match its hash` | not needed |
| B. Delete record 2 | `seq gap at position 2 (found seq 3)` | not needed |
| C. Edit record 4, recompute hashes 4 and 5 | `intact, 6 records` | `history rewritten` |
| D. Drop records 4 and 5 | `intact, 4 records` | `truncated` |

- **Vendor docs, verified.** Microsoft's SQL ledger page says an attacker could "Modify the digests to represent the updated hash of the transactions in the block", `E/azure_sql_ledger.txt` line 75. So Microsoft keeps digests "outside the database in tamper-proof storage", line 53. It "can't prevent such attacks but guarantees that any tampering will be detected", line 78. Vendor claim about its own product.
- **Verified by run. The anchor covers only what it has seen.** A forged log rewrites record 4. It passes a consistency check against a size-4 checkpoint. It fails against a size-5 checkpoint. `EP/run_output.txt` section 2.
- **Commentary, inferred.** So the interval between anchors is the window in which a rewrite goes unseen. Inferred from the construction. It holds for a chain and for a tree.
- **Standard, verified.** RFC 9162 defines Merkle inclusion and consistency proofs. It is "Category: Experimental" and "Obsoletes: 6962", `E/rfc9162.txt` lines 7 and 8. The prototype matches 9 root hashes from `transparency-dev/merkle` at commit `fbbcd741`. Self-test passed, `D18/selftest_evidence.txt`.
- **Verified by run.** At 100,000 records an inclusion proof is 17 hashes, 544 bytes. A chain walk to check one record reads all 100,000 records. Section 5 has the times. **Reviewer correction.** The prototype proves leaf n // 3, `EP/audit_evidence.py` lines 405 and 406. 17 is the maximum, ceil(log2 n). In a tree that is not a power of two some leaves need fewer hashes. The reviewer counted the RFC 9162 path length for every leaf. At n = 1,000 it is 8 to 10 hashes. At n = 100,000 it is 10 to 17 hashes, and 98.3% of leaves need 17. So the sizes are exact for the leaf proved, and an upper bound for any leaf.
- **Link.** Module 8 section 5.3 labelled the rewrite limit "inferred from the construction, not run", `agent-protocols-phase-05-proof.md` line 456. This concept is that run. Do not re-teach the chain.

### 4.6 An undeletable store is not a tamper-evident log. The managed ledger that did both is gone

- **Best evidence. Vendor docs, verified.** S3 Object Lock in compliance mode: an object version "can't be overwritten or deleted by any user, including the root user". The phrase spans lines 118 and 119 of `E/s3_objectlock.txt`. "The only way to delete an object under the compliance mode before its retention date expires is to delete the associated AWS account", line 126. It "works only in buckets that have S3 Versioning enabled", line 35.
- **Commentary, inferred.** Object Lock protects the file. It does not check what was written. A writer can lock a wrong record on day one. So an anchor in Object Lock plus a chain or tree gives both properties. Inferred from the two mechanisms.
- **Vendor blog, verified.** QLDB support ended on 2025-07-31: "2025 年 7 月 31 日にサポートが終了", `E/qldb_jp_blog.txt` line 21. AWS Japan, 2024-10-08.
- **Vendor blog, verified.** The AWS replacement for audit use moves to Aurora PostgreSQL with pgAudit and trigger-based audit tables. It says users with the right permissions can modify the audit-table data. Section "history() 関数の置き換え", `E/qldb_replace_jp.txt` line 28. pgAudit output to `postgres.log` is kept "最大 7 日間", up to 7 days, line 26.
- **Verified. Absence.** The QLDB developer guide returns 404. The English migration post redirects to a product index. Only the Japanese translations were readable.
- **Source docs, verified.** "Trillian is in maintenance mode", `E/trillian_readme.md` line 9. Tessera is its "logical successor", `E/tessera_readme.md` line 8.
- **Conditions.** The Cohasset assessment that AWS cites for SEC 17a-4 was not fetched. Not checked.

### 4.7 A logged model ID may not answer nine months later. A replay then proves that the record is intact, not that the model would decide the same

- **Best evidence. Vendor docs, verified.** Anthropic gives "at least 60 days' notice before model retirement for publicly released models", `E/anth_deprecations.txt` line 53. Claude Sonnet 4, `claude-sonnet-4-20250514`, was notified on April 14, 2026 and retired on June 15, 2026, lines 176 to 181. That is 62 days, recomputed in `D18/recompute.txt`.
- **Verified by run.** Evidence prototype section 4. A decision logged on 2025-12-10 is replayed on 2026-09-10: `RETIRED anthropic/claude-sonnet-4-20250514 on 2026-06-15, 87 days before the replay`. `EP/run_output.txt`.
- **Vendor docs, verified. Notice periods and lifetimes are different numbers.**

| Provider | Notice before retirement | Lifetime rule | Evidence |
|---|---|---|---|
| Anthropic, Claude API | at least 60 days. Measured 60 to 114 days over five retirements | none stated | `E/anth_deprecations.txt` line 53 and the history, lines 166 to 214 |
| OpenAI | GA models "At least 6 months" | none stated | `E/openai_deprecations.txt` line 704 |
| Azure OpenAI in Foundry | GA "At least 60 days" | retirement "18 months out" set at launch. Then "all inference returns 410 Gone" | `E/azure_retirements.txt` lines 102, 110, 147 |
| Amazon Bedrock, models launched from 2026-09-07 | The Legacy period is "the notice period before EOL". It is 6 months for most models, or 45 days | An "EOL no sooner than date" on each model card | `E/bedrock_lifecycle.txt` lines 8, 9 and 18 to 22. Reviewer correction: the first draft put the Legacy period in the lifetime column |
| Google Cloud model versions | not stated in the saved lines | "available for at least 12 months after initial release", for the models in that table only | `E/vertex_versions.txt` lines 1066 to 1068 |

- **Vendor docs, verified.** The Anthropic dates "apply to Anthropic-operated platforms". Bedrock and Google Cloud "set their own retirement schedules", `E/anth_deprecations.txt` line 47. So the manifest needs the platform, not only the model ID.
- **Vendor docs, verified.** "Each Claude model ID identifies a pinned version of the model", `E/anth_model_ids.txt` line 37. For older models an alias "resolves to the most recent dated snapshot", line 69. Log the snapshot, not the alias.
- **Vendor docs, verified. New in this dossier.** Anthropic lists `temperature`, `top_p` and `top_k` as "Deprecated (Claude Opus 4.7 and later)". The API "Returns a 400 error when set to a non-default value" on those models. The Python SDK v1.0 and later removes them, "so passing them raises a TypeError". `E/anth_deprecations.txt` lines 284 to 291. Section 7, conflict d. **Reviewer correction.** The SDK sentence on line 284 names no model. So a replay script on Python SDK v1.0 or later fails for any model if it passes `temperature`. That includes a model that still accepts the parameter over HTTP. The replay manifest must pin the SDK name and version, as well as the model. Inferred from line 284. Check: install the SDK in a scratch environment and call it with `temperature`, no key needed for the TypeError.
- **Vendor post, verified.** Anthropic commits "to preserving the weights of all publicly released models", `E/anth_depr_commit.txt` line 20. **Commentary, inferred.** Kept weights are not API access. So this does not make a retired model replayable.
- **Commentary, inferred.** When the model is retired, the stored transcript is the evidence. It holds inputs, retrieved chunks, tool results and output, with their hashes. Check: ask an auditor whether a transcript without a replay is accepted. Not checked.
- **Link.** Module 1 sections 1.5 and 5.5 own determinism and the run record. The Module 15 dossier 4.8 owns the version fields on each request. This concept adds the retirement date and the time dimension.

### 4.8 An API delete does not start a short erasure clock. The last copy sets the date on the deletion certificate

- **Best evidence. Vendor docs, verified.** Pinecone: "Pinecone retains the data for a maximum of 90 days", `E/pinecone_deletion_policy.md` line 21. Vendor claim.
- **Vendor docs, verified.** Qdrant 1.19.1 marks a deleted point "as deleted" and vacuums at `deleted_threshold: 0.2` with `vacuum_min_vector_number: 1000`, `E/qdrant_optimizer.txt` lines 164, 170 and 172. Both thresholds are per segment, lines 169 and 171. **Reviewer check.** The docs page carries no version. The reviewer fetched `config/config.yaml` at tag v1.19.1 from GitHub on 2026-09-25: `deleted_threshold: 0.2` on line 139 and `vacuum_min_vector_number: 1000` on line 142. The GitHub latest release is v1.19.1, published 2026-09-04. Defaults verified at the tag. The snapshots page has 0 matches for "retention", `E/qdrant_snapshots.txt`. It documents a delete-snapshot call, line 192. **Inferred** from that absence: snapshot expiry is your job. Check: the snapshot section of the v1.19.1 config file.
- **Vendor docs, verified.** Weaviate incremental backups store unchanged files "as references rather than copied", `E/weaviate_backups.txt` line 380. Pinecone: "Deleting a schedule doesn't delete any backups that were previously created by it", `E/pinecone_backups.md` line 55.
- **Legal text, verified.** GDPR Article 17(1): erase "without undue delay", `L/gdpr.txt` line 693. Article 12(3): answer "within one month of receipt", extendable "by two further months", `L/gdpr.txt` line 574. Article 19: tell each recipient, "unless this proves impossible or involves disproportionate effort", line 733.
- **Official guidance, UK, verified.** The ICO: "ensure erasure from backup systems as well as live systems", `E/ico_erasure.txt` line 100. Backup data may stay "for a certain period of time until it is overwritten", line 102, if it is put "beyond use", line 103. UK GDPR guidance. EU authority guidance on backups: not checked.
- **Official guidance, US, verified.** NIST SP 800-88 Rev. 2 section 4.6 lists certificate fields, including "Sanitization method", "Tool used, including version" and "Verification method", `E/nist_80088r2.txt` lines 1317 to 1320. **Commentary.** NIST writes one certificate per storage medium. A per-request certificate borrows its fields. That mapping is this dossier's design.
- **Verified by run.** Evidence prototype section 5. Request 2026-09-01. Live stores audit to zero. A 35-day database backup expires 2026-10-05. A 90-day vector snapshot expires 2026-11-28. Pinecone's soft delete ends 2026-11-30. Output: `fully erased by 2026-11-30 = 90 days after the request`. `EP/run_output.txt`. Dates recomputed in `D18/recompute.txt`.
- **Commentary, inferred.** The live delete finishes on day 0. The certificate's honest date is day 90. The one-month deadline is for the answer and the live systems. The backups need the "beyond use" statement. Whether a vendor's soft-delete store counts as a backup under the ICO text: not stated by either source. Section 7, conflict h.
- **Link.** Module 10 sections 4.1 to 4.3 own the mechanism, the zero audit and the survivor check. Module 3 section 7.3 owns the bytes. This concept adds only the clock and the certificate.

### 4.9 An erasure request does not always mean deleting the audit record. Keep personal data out of the locked record, or encrypt it with a key you can delete

- **Best evidence. Legal text, verified.** Article 17(3) removes the erasure duty "to the extent that processing is necessary" for listed reasons. Point (b) is "compliance with a legal obligation". Point (e) is "for the establishment, exercise or defence of legal claims". `L/gdpr.txt` lines 707 to 717.
- **Legal text, verified.** The AI Act floor yields to data protection law, Article 19(1), `L/aiact.txt` line 946. **Commentary, not checked.** Each rule points to the other. No EDPB or court text found that settles it. Section 7, conflict i.
- **Vendor docs, verified.** S3 Object Lock compliance mode has no override before the retention date, 4.6. So personal data inside a locked object cannot be erased until that date.
- **Official guidance, US, verified.** NIST SP 800-88 Rev. 2 names cryptographic erase as possibly "the only viable purge sanitization technique option" for some storage, `E/nist_80088r2.txt` line 608.
- **Official guidance, one country, verified.** The CNIL says logs must not keep data past a shorter source retention, `L/cnil_journalisation.txt` line 184. That is the same conflict, stated by an authority.
- **Verified by run, toy.** Evidence prototype section 3. The payload is encrypted with a per-subject key. The chain hashes the ciphertext. After the key is deleted: `key present=False, chain intact, 2 records`. `EP/run_output.txt`. The cipher is SHA-256 in counter mode, a teaching toy.
- **Commentary. The design.** Split each record in two:
  1. A skeleton with no personal data: time, versions, hashes, decision, region. Kept for the audit period.
  2. A personal payload keyed by a pseudonym, encrypted with a per-subject key. Deleting the key erases it.
- **Commentary, not checked.** The pseudonym in the skeleton is still personal data while its key exists. Whether deleting the pseudonym key makes it anonymous is a legal question.
- **Link.** Module 3 section 7.3 already mentions per-group key deletion for vectors. Do not re-teach it.

### 4.10 A provider's EU endpoint is not the whole residency answer. The GDPR controls transfers, and remote access from a third country counts

- **Best evidence. Official guidance, verified.** EDPB Guidelines 05/2021 give three cumulative criteria for a transfer. The second is that the exporter "discloses by transmission or otherwise makes personal data ... available" to an importer. `L/edpb_05_2021.txt` line 52. The guidelines name "remote access" as one way, lines 275 and 276. Remote access from a third country is a transfer "even if it takes place only by means of displaying personal data on a screen, for example in support situations", lines 276 to 280, if the three criteria are met.
- **Legal text, verified. Absence.** The GDPR does not use the word "residency". Reviewer count on `L/gdpr.txt`: 0 matches.
- **Legal text, verified.** The order of transfer tools: adequacy, which "shall not require any specific authorisation", Article 45(1), `L/gdpr.txt` line 1127. Then safeguards such as SCCs, "on condition that enforceable data subject rights and effective legal remedies for data subjects are available", Article 46(1), line 1145. Then derogations in Article 49, only in their absence.
- **Legal text, verified.** The DPF covers only organisations on the "Data Privacy Framework List", `L/dpf_decision.txt` line 529. A US provider not on that list needs SCCs.
- **Legal text, verified.** The General Court dismissed the DPF challenge on 3 September 2025, "Dismisses the action", `L/T553_23_judgment.txt` line 582. An appeal was "brought on 31 October 2025 by Philippe Latombe", `L/C703_25_appeal.txt` line 9. EUR-Lex has no judgment and no opinion yet: 404, "The requested document does not exist", `L/62025CJ0703.txt` line 2. **Inferred.** The appeal is pending. The CURIA page did not render. Not checked there.
- **Legal text, verified.** SCC Clause 14(b) makes the parties consider "the storage location of the data transferred", `L/scc_2021_914.txt` line 514. Clause 14(d): "document the assessment under paragraph (b) and make it available to the competent supervisory authority on request", line 522.
- **Official guidance, verified. Absence.** India does not appear on the Commission adequacy page, `L/adequacy_page.txt`: 0 matches.
- **Commentary, inferred.** Prompts, retrieved passages and tool results may go to a model endpoint in a third country. That is a transfer if they hold personal data. Support staff or sub-processors abroad with remote access can create a transfer even with an EU endpoint. That rule is official guidance, verified in the bullet above. Whether a given provider has such access: not checked. It varies by contract.
- **Link.** The Module 14 dossier 4.15 has the price. OpenAI data-residency endpoints add 10% for models released on or after 2026-03-05.

### 4.11 Auditors test controls over a period, from samples they pick. A vendor's 90-day audit log does not cover a nine-month question

- **Best evidence. Auditor source, verified.** "Then I pick an event and ask you to rebuild it from the records", `E/teleport_42001.txt` line 90. The author says they are "a certified ISO 42001 and ISO 27001 auditor", line 46. The same post: "ISO 42001 does not make you compliant with the AI Act", line 43.
- **Compliance firm, verified.** A SOC 2 Type 2 period is "Typically ranging from 3 to 12 months", `E/compassitc_period.txt` line 159.
- **Auditor source, verified.** SOC 2 criteria do not name controls: "the 2017 TSC document does not define the controls a service organization must have in place", `E/linford_tsc.txt` line 56. So SOC 2 does not require a hash chain. You choose the control, then prove it ran.
- **Vendor blog, verified.** "You won't know which samples they plan to test", `E/strikegraph_test.txt` line 125. Annual controls are always tested, line 126.
- **Vendor docs, verified.** Pinecone's own audit log events are "retained for 90 days", `E/pinecone_deletion_policy.md` line 28.
- **Commentary, inferred.** A 12-month period plus the time to fieldwork needs evidence older than nine months. A 90-day vendor log does not reach it. Export it to your own store.
- **Vendor claim, not a requirement.** ISMS.online writes "ISO 42001 compliance now demands tamper-evident" event trails, `E/isms_a628.txt` line 521. The standard text was not read. Do not teach this as a requirement. Section 7, conflict g.
- **Conditions.** The AICPA criteria PDF needs an account. ISO/IEC 42001 is paid. Neither primary text was read.

### 4.12 A data protection authority can order the records today. The AI Act right to see the logs starts only with the high-risk duties

Added by the reviewer. The module question starts with "a regulator asks". The first draft did not say which rule lets a regulator ask.

- **Best evidence. Legal text, verified.** GDPR Article 58(1)(a): each supervisory authority may order the controller and the processor "to provide any information it requires for the performance of its tasks". `L/gdpr.txt` lines 1355 to 1359.
- **Legal text, verified.** GDPR Article 31: the controller and the processor "shall cooperate, on request, with the supervisory authority". `L/gdpr.txt` lines 899 to 901.
- **Legal text, verified.** AI Act Article 21(2): "upon a reasoned request by a competent authority", providers give "access to the automatically generated logs" of a high-risk system. `L/aiact.txt` line 955. Article 21 is in Chapter III Section 3, so it applies from 2 December 2027 or 2 August 2028, 4.1.
- **Commentary, inferred.** For a decision made on 2025-12-25, the likely requester is a data protection authority, under Article 58. The GDPR names no format and no fields for the answer. So the bundle in 6.3 is a design, not a legal form. Check: ask counsel which authority is competent for your organisation.

### Anchor check

The dossier author re-grepped every anchor of section 4 on 2026-09-25. Script `D18/anchor_check.py`, output `D18/anchor_check.txt`. The script collapses whitespace and makes curly quotes straight. It counts lines by newline only, as `grep -n` does.

- **129 of 129 anchors match.** 104 check a quote on a named line. 11 check that a quote is present. 13 check an exact count, such as 1 hit of "log-in" in the GDPR text. 3 are absence checks. They cover "log" and "record" in Article 50, "retention" on the Qdrant snapshots page, and "India" on the adequacy page. 2 anchors are in built course files: Module 8 line 456 and the Module 14 dossier line 345.
- Per concept, found of checked:

| Concept | Anchors | Concept | Anchors |
|---|---|---|---|
| 4.1 | 12 of 12 | 4.7 | 18 of 18 |
| 4.2 | 14 of 14 | 4.8 | 17 of 17 |
| 4.3 | 9 of 9 | 4.9 | 5 of 5 |
| 4.4 | 11 of 11 | 4.10 | 13 of 13 |
| 4.5 | 14 of 14 | 4.11 | 8 of 8 |
| 4.6 | 8 of 8 | | |

- **One anchor needed a script fix, not a text fix.** The first run reported `isms_a628.txt` line 521 as missing. Python's `splitlines()` also splits on rare control characters, so its line numbers drifted from `grep -n`. Splitting on newline only made it match.
- **Two quotes run across a line break.** The paragraph 148 phrase is on lines 2360 and 2361 of `L/guidelines_art50.txt`. The S3 Object Lock "root user" phrase is on lines 118 and 119 of `E/s3_objectlock.txt`. The script checks each on its first line joined with the next one.

---

## 5. Numbers, with their conditions

| Number | What it is | Conditions | Label |
|---|---|---|---|
| 2 February 2025 | Chapters I and II apply, including Art 4 AI literacy and Art 5 prohibitions | AI Act Art 113 point (a). Neither asks for a log | Legal text, verified by the reviewer |
| 2 August 2026 | Article 50 applies | AI Act Art 113, not changed by the omnibus. Same in the consolidated text of 27.07.2026, re-fetched by the reviewer | Legal text, verified |
| 2 December 2026 | Article 50(2) deadline for generative systems on the market before 2 August 2026 | New Art 111(4). Covers 50(2) only | Legal text, verified |
| 2 December 2027 | Chapter III Sections 1 to 3 apply, Annex III systems. Includes Arts 12, 19, 21, 26 | Omnibus Art 1 point (40). Omnibus re-fetched and consolidated text read by the reviewer | Legal text, verified |
| 2 August 2028 | Same, Annex I systems | Same | Legal text, verified |
| 2 August 2030 | Deadline for high-risk systems used by public authorities and already on the market | New Art 111(2). Other systems already on the market fall under Chapter III only after significant design changes | Legal text, verified by the reviewer |
| 27 July 2026 | Omnibus in force | Third day after OJ publication on 24.7.2026. Recomputed | Legal text, verified. Date recomputed |
| 6 months | Log floor, high-risk providers and deployers | "at least", yields to personal-data law. Not in force before 2 December 2027 | Legal text, verified |
| 10 years | Technical documentation retention | Art 18(1). Not logs | Legal text, verified |
| 6 to 12 months, up to 3 years with a reason | Access and action log retention | CNIL, France only | Official guidance, verified |
| 1 month, plus up to 2 | Time to answer an erasure request | GDPR Art 12(3) | Legal text, verified |
| 250 persons | Article 30 record exemption threshold | Exceptions apply. Omnibus IV may change it. Not adopted on 2026-09-25 | Legal text, verified |
| EUR 15 000 000 or 3% | Maximum fine for Art 26 or Art 50 breaches | Whichever is higher. The omnibus adds a lower rule for small mid-caps | Legal text, verified |
| About 190 | Signatories of the transparency code | End of July 2026, Commission page | Official guidance, verified |
| 274 days | Nine months before 2026-09-25 | 2025-12-25 to 2026-09-25. Recomputed | Arithmetic |
| 60 days | Anthropic minimum notice before retirement | Claude API and other Anthropic-operated platforms | Vendor docs, verified |
| 60, 61, 62, 62, 114 days | Measured Anthropic notice periods | Five retirements, 2025-10-28 to 2026-08-05. Recomputed | Vendor docs, verified. Recomputed |
| 183 days | OpenAI notice for `gpt-5-2025-08-07` | 2026-06-11 to 2026-12-11. Recomputed | Vendor docs, verified |
| 18 months | Azure OpenAI GA lifetime, then 410 Gone | Set at launch | Vendor docs, verified |
| 87 days | Sonnet 4 retired before a replay on 2026-09-10 | Prototype case. Recomputed | Verified by run |
| 90 days | Pinecone soft-delete retention, and Pinecone audit-log retention | Vendor claims | Vendor docs, verified |
| 0.2 and 1,000 | Qdrant vacuum threshold and minimum vector count | Qdrant 1.19.1 docs | Vendor docs, verified |
| 7 days | pgAudit `postgres.log` retention in the AWS QLDB replacement | AWS Japan translation | Vendor blog, verified |
| 3 to 12 months | SOC 2 Type 2 period | Compliance firm, not AICPA | Commentary, verified quote |
| 90 days | Certificate date in the prototype | Request 2026-09-01. Pinecone window is the last copy. Recomputed | Verified by run |
| 10 hashes, 320 bytes | Inclusion proof at n = 1,000, leaf 333 | SHA-256, RFC 9162. ceil(log2 n) × 32 bytes is the maximum. Other leaves need 8 to 10 hashes. Recomputed by the reviewer for every leaf | Verified by run |
| 17 hashes, 544 bytes | Inclusion proof at n = 100,000, leaf 33,333 | log2 100,000 = 16.61. Other leaves need 10 to 17 hashes. 98.3% need 17. Recomputed by the reviewer | Verified by run |
| 9 and 14 hashes | Consistency proofs n/2 to n at 1,000 and 100,000 | From the run. Not recomputed by formula | Verified by run |
| 6 µs and 14 µs | Inclusion proof verify time at 1,000 and 100,000 | Single runs. No load control. The dossier author's rerun printed 18 µs at 100,000 | Verified by run. Rough |
| 2 ms and 211 ms | Chain walk to check one record at 1,000 and 100,000 | Same. The rerun printed 207 ms | Verified by run. Rough |
| 0.03 s | Self-test time of each prototype | `/usr/bin/time -p`, `D18/selftest_*.txt` | Verified by run |

---

## 6. Lab designs

Every lab runs on the learner's Apple Silicon Mac, offline, CPU only, standard library, no keys. Every lab costs $0. No lab needs a download beyond the saved legal texts, except lab 6.2 F.

### 6.1 Built and run on 2026-09-25

| Lab | Script | Where it runs | Cost and time | Prints | Break-it | Self-test |
|---|---|---|---|---|---|---|
| Duty and schema check | `LP/audit_check.py` with `duties.json`, `example_schema.json`, `example_profile.json` | Mac, Python 3.9.6, stdlib | $0. 0.03 s | Duties in force on a date, missing fields per duty, retention floor and ceiling, erasure conflicts | Set retention to 6 months: the 9-month floor fails on 7 fields | Five hand-worked cases. `python3 test_audit_check.py`. `D18/selftest_law.txt`. Reviewer re-run 2026-09-25: all pass, 0.02 s |
| Chain attacks, Merkle proofs, crypto-shredding, replay manifest, deletion certificate | `EP/audit_evidence.py` | Mac, Python 3.9.6, stdlib | $0. Under 1 s for the whole script | Section 1 to 5 outputs quoted in 4.5, 4.7, 4.8, 4.9 | Move the anchor from size 6 to size 4. Attack C passes both checks. Log an alias ending in `-latest`: `ALIAS` | Hand chain, SHA-256 of "abc", 9 RFC 9162 roots, all proofs for n ≤ 8, the 87-day and 34-day cases. The flag is `--selftest`. `--self-test` is not recognised and runs the full demo instead. `D18/selftest_evidence.txt`. Reviewer re-run 2026-09-25: all pass, 0.03 s |

Limits, commentary:

- `audit_check.py` counts whole months. How the law counts periods was not checked. Check: Regulation (EEC, Euratom) No 1182/71 on periods, dates and time limits. Not fetched.
- `applies_if` is exact matching. Real classification needs legal judgment.
- It uses the one-month answer deadline as a trigger for "this field needs an erasure method". That is not a retention limit.
- Its field lists for the AI Act log duties are commentary. Article 12 names no fields for these systems. Section 7, conflict f.
- Reviewer finding: the same problem affects two more duties. `AIA-50-1-disclosure` and `GDPR-46-49-transfer` are labelled `legal_text`, yet their `why` text calls the fields commentary. `audit_check.py` line 60 makes a missing field an error when the duty is `legal_text` and in force. So the lab prints a legal-text error for a missing `ai_disclosure_shown`, which no law requires. Section 7, conflict f.
- The AI Act log duties in `LP/duties.json` use 2027-12-02 only. There is no Annex I profile with 2028-08-02. Article 111(2) for systems already on the market is not modelled.
- `LP/duties.json` cites "Module 7 agent-protocols section 5.3" in the `REVIEWER-nine-months` duty. It is Module 8. Conflict a.
- The evidence prototype's cipher is a toy. The certificate does not model Weaviate incremental-backup references.

### 6.2 Designed, not built

| Lab | Where it runs | Cost | Prints | Break-it | Self-test |
|---|---|---|---|---|---|
| A. Date lab | Mac, stdlib | $0. Under 0.1 s, estimated | Duties in force for a profile on a date | Step the date through 2026-08-01, 2026-08-02 and 2027-12-02. Watch Art 50, then Art 26(6), turn on | The Art 113 table in 4.1 |
| B. Split-record lab | Mac, stdlib | $0. Under 1 s, estimated | One event before and after erasure: skeleton, payload, chain status, reviewer fields that still resolve | Put the user's email in `trace_id`. The erasure audit must find it | Chain verifies after key deletion. Uses Module 10's audit for the zero count |
| C. Transfer map lab | Mac, stdlib | $0 | Per processing hop: the three EDPB criteria and the named Chapter V tool | Add "support staff remote access from a third country" | An EEA-only hop prints "no transfer" |
| D. Replay manifest refresh | Mac, stdlib, plus reading provider pages in a browser | $0 | RETIRED, SCHEDULED, AT RISK, NONDETERMINISTIC, UNPINNED | Log a model with `temperature` set on a model where it is deprecated | The 87-day case. The table rots, so refresh it on lab day |
| E. Certificate with incremental backups | Mac, stdlib | $0 | "Fully erased by" date when a later backup refers to an older base file | Expire the base by age while a reference remains | The 34-day case, then a hand case with a reference |
| F. Qdrant physical deletion, optional, UNVERIFIED | Mac, Qdrant 1.19.1 binary, no Docker | $0. About 50 MB download, size not checked | Byte hits of one deleted point in segment files, before and after a forced vacuum | Delete 1 point of 10,000 and do not force a vacuum | Not designed |

### 6.3 The module lab, proposed

**The nine-month evidence bundle.** Input: one decision id and a question date. Output: the files a reviewer receives.

1. The audit record, from Module 8's record plus the fields in 4.4.
2. An inclusion proof for that record against a signed or anchored root. A consistency proof from the anchor to today. From `EP/audit_evidence.py` sections 1 and 2.
3. The replay manifest, with each model's status on the decision date and on the question date. Section 4 of the same script.
4. Every deletion certificate that touches the record's subject, with its last-copy date. Section 5, and Module 10's `forget(subject)` audit.
5. The duties in force on the decision date, with their labels, from `LP/audit_check.py`.
6. The processing region and the transfer tool for each hop, from lab C.

Break-it: set retention to six months and ask on month nine. The bundle must say "record expired" and name the policy, not fail silently. Self-test: a hand-built decision whose bundle is written out before the run. Where: Mac, stdlib. Cost: $0. Time: not measured. Estimated under 2 s.

---

## 7. Conflicts resolved

| Conflict | Reports | Evidence used | Resolution |
|---|---|---|---|
| a. Which module owns the audit record fields | Law report 2.3 says "Module 7, `agent-protocols/...` 5.3" | `_curriculum/README.md` line 195: "Module 8 — Agent protocols and agent identity". Module 7 is agent harness, line 186 | Module 8 section 5.3. The law report used the wrong number |
| b. Is the AI Act log floor a duty today | Evidence report 2.4 cites Arts 12, 19, 26(6) from the 2024 OJ text and says later amendments were not checked | Law report 2.1. `L/omnibus_32026R1744.txt` lines 617 to 621. The amended-article list does not name 12, 19 or 26 | The article text is unchanged. The start date moved to 2 December 2027 or 2 August 2028. Teach the floor as a future duty for high-risk systems only |
| c. "A model ID can stop working in about two months on one provider, and after 18 months on another" | Evidence report concept 3 | `E/anth_deprecations.txt` line 53, `E/azure_retirements.txt` lines 102, 110, 147 | The sentence compares a notice period with a lifetime. Azure also gives "At least 60 days" notice. The dossier separates the two columns in 4.7. **Reviewer correction.** The first draft still put Bedrock's 6-month Legacy period in the lifetime column. `E/bedrock_lifecycle.txt` line 20 calls it "the notice period before EOL". Moved to the notice column |
| d. The Anthropic temperature rule | Evidence report 9.9: taken from the Module 11 dossier, not re-fetched. Module 11 dossier line 109: deprecated "for models after Claude Opus 4.6. Only 1.0 is accepted" | The saved page `E/anth_deprecations.txt` lines 284 to 291, fetched 2026-09-25: "Deprecated (Claude Opus 4.7 and later)". "Returns a 400 error when set to a non-default value". The Python SDK v1.0 and later removes the parameters, so passing them raises `TypeError` | Verified today. Same rule as Module 11. New fact: the SDK raises before the request is sent. **Reviewer correction.** The SDK sentence on line 284 names no model. So a replay script on Python SDK v1.0 or later that passes `temperature` fails for every model, not only Opus 4.7 and later. Pin the SDK version in the replay manifest, 4.7 |
| e. Merkle proof timings | Evidence report: 14 µs verify and 211 ms chain walk at 100,000 | `EP/run_output.txt`, and the dossier author's full rerun on 2026-09-25: 18 µs and 207 ms | Single runs, no load control. Teach proof sizes, which are exact for the leaf proved and a maximum for any leaf, 4.5. Give times as rough |
| f. Do the AI Act log duties require fields | Law prototype marks missing fields as errors for legal-text duties in force. Its AI Act duties list `event_time`, `system_id`, `system_version` | `LP/duties.json`. `L/aiact.txt` lines 788 to 794: Art 12(2) names purposes, not fields | The duty is legal text. The field list for Art 12(1) and (2) is commentary. The lab must print it as a warning with the commentary label, or say so in the lab text. Only Art 12(3) fields are legal text. **Reviewer addition.** The same fix applies to `AIA-50-1-disclosure` and `GDPR-46-49-transfer`, whose own `why` text says their fields are commentary. Checked in `LP/duties.json` and `LP/audit_check.py` line 60 |
| g. Is tamper evidence required | ISMS.online: ISO 42001 "now demands tamper-evident" trails. The IETF AIMS draft that Module 8 quotes says "MUST be tamper-evident". Law report: no legal text found | `E/isms_a628.txt` line 521. `agent-protocols-phase-05-proof.md` section 5.3. Law report 2.3 | No law read here requires it. ISO 42001 text was not read. AIMS is an Informational draft. Teach tamper evidence as a design choice that makes the record credible to a reviewer. Label it commentary |
| h. Vendor soft-delete windows against the one-month deadline | Evidence report 8.4 | Pinecone 90 days, `E/pinecone_deletion_policy.md` line 21. ICO "beyond use", `E/ico_erasure.txt` line 103. GDPR Art 12(3) | Not settled. Neither source says whether a soft-delete store counts as a backup. The certificate states the 90-day date and the "beyond use" condition. Counsel decides |
| i. Is the AI Act six-month floor a legal obligation under GDPR Art 17(3)(b) | Law report 10.2 | Art 19(1) yields to personal-data law. Art 17(3)(b) exempts what a legal obligation needs | Not settled. Each rule points to the other. No EDPB or court text found. Teach the split record of 4.9, which avoids the question for the personal part |
| j. When Article 86 applies | Law report 10.1 | Art 86 is in Chapter IX, so 2 August 2026 applies. It refers to Annex III systems, whose Chapter III duties start 2 December 2027 | Not settled. Teach both dates and the open question |
| k. The README note on Article 50 | README line 364 asked for re-verification | `L/aiact.txt` line 2198. `L/guidelines_art50_page.txt` line 55 | Correct. Add the 50(2) grace period to 2 December 2026 for systems already on the market |

---

## 8. Gap list, ranked by what the module question needs

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | The nine-month evidence bundle, run end to end | The question asks what to hand over. No single run produces it | Not built. Design in 6.3 |
| 2 | Whether a transcript without a replay satisfies a reviewer | Most models logged nine months ago may be retired, 4.7 | Not checked. No auditor or regulator source states it |
| 3 | The split record with key deletion, run with the chain and the reviewer fields | 4.9 joins two sources. No run tests the full design | Not built. Lab B. The toy in `EP/` covers one record pair |
| 4 | Does the AI Act six-month floor count as a legal obligation under Art 17(3)(b) | Decides whether a high-risk log may keep personal data after an erasure request | Not checked. No EDPB or court text found |
| 5 | Whether a vendor soft-delete window meets the erasure duty | Sets the date on the deletion certificate | Not checked. Conflict h |
| 6 | ISO/IEC 42001 Annex A and AICPA TSC criterion text | Tells what an auditor may require of logs | Not read. Paid standard, and a PDF behind an account |
| 7 | EU authority guidance on backups and erasure | 4.8 rests on UK ICO guidance | Not checked |
| 8 | Provider staff remote access and sub-processor locations | Decides whether an EU endpoint still makes a transfer, 4.10 | Not checked. Contract-specific |
| 9 | CURIA status of C-703/25 P and the DPF periodic review findings | Decides whether the DPF stays a valid transfer tool | Not checked. CURIA did not render. Review report not opened |
| 10 | Physical deletion in Qdrant after one delete, Weaviate incremental backups, PostgreSQL WAL archives | Sets the real last-copy date | Inferred from docs. Lab F and two experiments in the evidence report 2.3 |
| 11 | ISO/IEC 24970 field model | May become the reference record format | Not checked. Paywalled |
| 12 | Consolidated AI Act text after 27 July 2026 | Confirms the article-level reading of the omnibus | Closed by the reviewer. `02024R1689-20260727` fetched 2026-09-25. Article 113 dates and Articles 19(1) and 26(6) match 4.1 |
| 13 | Other national authorities' log retention ranges | 4.3 rests on the CNIL alone | Not checked |
| 14 | Omnibus IV agreed text and the Art 30(5) threshold | Decides who must keep an Article 30 record | Not checked |
| 15 | Trusted time for each record: clock source, clock drift, and signed timestamps such as RFC 3161 | The reviewer asks when the agent acted. A hash chain proves order, not the clock time. Added by the reviewer | Not checked. No source saved |
| 16 | Attacks on consent records, tokens and logs | Module 16 phase 5 section 5.4 hands them to this module. A reviewer trusts the log only if these attacks are covered | Not checked. Neither Module 16 nor this dossier has a source. Added by the reviewer |
| 17 | GDPR Article 33(5), the record of personal data breaches | In scope in 2.1, but no concept uses it. A regulator may ask for it with the decision records | Not read by the reviewer. Added by the reviewer |
| 18 | The form of the hand-over: export format, chain of custody, language | Article 21(1) asks for a language "easily understood by the authority", `L/aiact.txt` line 954. The GDPR names no form | Not checked beyond that line. Added by the reviewer |

---

## 9. Things not verified

Each item names the check that would settle it.

1. **CURIA status of C-703/25 P.** The CURIA page is a JavaScript app and did not render. Check: open it in a normal browser, or wait for a EUR-Lex judgment document.
2. **DPF first periodic review report.** Linked on the adequacy page, `L/adequacy_page.txt` line 283. Not opened. Check: fetch and read its conclusions.
3. **Omnibus IV agreed text.** Only the procedure stage was read. Check: fetch the trilogue text from the Parliament register.
4. **What Article 6(5) says after the omnibus.** It is excluded from the delay. Check: read the omnibus lines on Article 6, about `L/omnibus_32026R1744.txt` lines 220 to 225.
5. **Whether any given agent product is high-risk.** Check: classification per product with counsel.
6. **Financial-services log periods under AI Act Arts 19(2) and 26(6).** Check: the sector law.
7. **The consolidated AI Act text.** Settled by the reviewer on 2026-09-25. EUR-Lex `02024R1689-20260727` prints the Article 113 dates in 4.1. The EUR-Lex document page lists 32026R1744 as the only amending act.
8. **Whether logs are always personal data.** Inferred from GDPR Art 4(1). Check: CJEU case law on identifiability, such as C-582/14 Breyer.
9. **AICPA TSC criterion text, such as CC7.2.** The PDF needs an account. Check: a person downloads it and greps the criteria.
10. **ISO/IEC 42001 Annex A text, including A.6.2.8.** Paid standard. The control name appears only in vendor and auditor summaries. Check: the purchased standard.
11. **SOC 2 sample sizes by control frequency.** The Strike Graph table is an image. A search summary gave "25 to 40" for daily controls. No page read states it as text. Do not cite it.
12. **The English AWS QLDB migration posts.** Both redirect away. Check: the Wayback Machine.
13. **The Cohasset assessment of S3 Object Lock.** Not fetched.
14. **Qdrant physical removal after one delete.** Inferred from the 20% default. Check: lab F.
15. **Weaviate incremental backups keep deleted bytes.** Inferred from "stored as references". Check: base and incremental backups, one delete, expire the base, byte search.
16. **PostgreSQL WAL archives keep deleted rows.** Inferred. Check: the continuous-archiving docs and a byte search.
17. **Release dates of Anthropic models.** The 365-day life of Opus 4.1 assumes one thing. The release date equals the date in its ID. Check: the Anthropic models overview.
18. **Weaviate v1.37.8 release date.** Check: the release page.
19. **Ed25519 signed checkpoints.** Suggested as a lab extension. Not built.
20. **Whether an auditor accepts a transcript without a replay.** Check: ask an auditor. Or find a published audit guide that states it.
21. **Other national authorities' log retention ranges.** Check: the German, Dutch and Irish authorities.
22. **ISO/IEC 24970 stage on iso.org itself.** iso.org returned 403. Check: open iso.org in a browser.
23. **Machine load during the prototype timings.** Not recorded. The dossier author's rerun differs by up to 4 µs and 4 ms. Treat times as rough.
24. **The Python SDK TypeError for older models.** Inferred from `E/anth_deprecations.txt` line 284. Check: call SDK v1.0 or later with `temperature` in a scratch environment. The error is raised before any request, so no key is needed.
25. **Qdrant snapshot retention settings.** Inferred from the absence on the docs page. Check: the snapshot section of `config/config.yaml` at tag v1.19.1.

---

## 10. Review log

Independent review, 2026-09-25. The reviewer did not write this dossier. Reviewer notes and fetched files are in the reviewer's scratchpad, `fetch/` and `review_notes.md`. The dossier before review is saved there as `module-18-before-review.md`.

### 10.1 What the reviewer did

1. **Re-fetched the law.** EUR-Lex CELEX 32026R1744, the omnibus. It matches the saved `L/omnibus_32026R1744.txt` word for word after whitespace normalisation. Also the EUR-Lex consolidated AI Act `02024R1689-20260727` and the EUR-Lex document pages for the AI Act and the GDPR. Also the three OEIL procedure pages. All HTTP 200 with `curl --max-time 60`.
2. **Checked amendments.** The AI Act document page lists 88 changes, all by 32026R1744, all from 27/07/2026. Articles 12, 19, 26 and 86 are not among them. Article 50(7) is. The GDPR page lists no amending act. The GDPR omnibus and Omnibus IV are still proposals.
3. **Spot-checked about 90 anchors** against the saved files. All quotes were found on the named lines, with the errors below. The count covers 40 legal-text anchors, 12 official-guidance anchors and about 38 vendor, auditor and standard anchors.
4. **Re-ran both self-tests.** `test_audit_check.py`: 5 of 5 cases pass. `audit_evidence.py --selftest`: all pass. Python 3.9.6, macOS, 2026-09-25.
5. **Recomputed the arithmetic.** 274 days, 87 days, 62 days, 34 days, 90 days, 183 and 92 days, and 27 July 2026 all match. The retention floor is max(6, 9) = 9 months and the ceiling is the CNIL 12 months. Case 3 reports a floor of 36 months above the ceiling of 12, as stated. Merkle proof sizes match for the leaf proved. See correction 8.
6. **Re-read the overlap** with `grep '^## '` on `agent-protocols`, `memory`, `observability-ops` and `security`.

### 10.2 Date labels

| Date | What | Label |
|---|---|---|
| 2 February 2025 | AI Act Chapters I and II, including Arts 4 and 5 | Verified, OJ text and consolidated text |
| 2 August 2025 | AI Act Chapter III Section 4, Chapter V, VII, XII | Verified, OJ text |
| 27 July 2026 | Omnibus in force. Arts 102 to 110 apply | Verified, re-fetched omnibus Art 4 and consolidated Art 113 point (d) |
| 2 August 2026 | AI Act general date. Art 50 and Art 86 | Verified, OJ text and consolidated text. Not moved by the omnibus |
| 2 December 2026 | Art 50(2) grace period end, new Art 111(4) | Verified, re-fetched omnibus |
| 2 December 2027 | Chapter III Sections 1 to 3, Annex III. Arts 12, 19, 21, 26 | Verified, re-fetched omnibus and consolidated text |
| 2 August 2028 | Same, Annex I | Verified, same |
| 2 August 2030 | Public-authority high-risk systems already on the market, new Art 111(2) | Verified, re-fetched omnibus |
| One month, plus two | GDPR Art 12(3) answer deadline | Verified, `L/gdpr.txt` line 574. GDPR not amended |

### 10.3 Corrections

| # | Kind | Where | Was | Now | Evidence |
|---|---|---|---|---|---|
| 1 | Legal, serious | 1, 4.1 heading and bullets | A decision on 2025-12-25 "falls under the GDPR alone" | AI Act Arts 4 and 5 applied from 2 February 2025. They ask for no log. No AI Act log or Art 50 duty applied | `L/aiact.txt` Art 113 point (a), lines 594 to 599 |
| 2 | Legal, missing fact | 4.2 | Art 50 described as unchanged apart from the 111(4) grace period | The omnibus replaces Art 50(7), the code-of-practice procedure. 50(1) to 50(5) unchanged | `L/omnibus_32026R1744.txt` lines 309 and 310. EUR-Lex change list |
| 3 | Legal, missing fact | 4.1, section 5 | No transition rule for systems already on the market | New Art 111(2): Chapter III applies to them only after significant design changes. Public authorities by 2 August 2030 | `L/omnibus_32026R1744.txt` line 601 |
| 4 | Missing concept | New 4.12, section 1 table | The dossier did not say which rule lets a regulator ask | GDPR Arts 58(1)(a) and 31. AI Act Art 21(2) log access from 2 December 2027 | `L/gdpr.txt` lines 899 to 901 and 1355 to 1359. `L/aiact.txt` line 955 |
| 5 | Evidence status | 4.1 conditions, gap 12, item 9.7 | Consolidated text not read | Read. Dates match. Noted that the consolidated text has no legal effect | EUR-Lex `02024R1689-20260727` |
| 6 | Technical, serious | 4.7 table, conflict c | Bedrock 6-month Legacy period shown as a lifetime rule | It is the notice period. The lifetime floor is the "EOL no sooner than date" | `E/bedrock_lifecycle.txt` lines 18 to 22 |
| 7 | Technical, serious | 4.7, conflict d | Python SDK `TypeError` read as affecting only Opus 4.7 and later | The SDK sentence names no model. A replay on SDK v1.0 or later fails for any model that gets `temperature`. Pin the SDK version. Labelled inferred | `E/anth_deprecations.txt` line 284 |
| 8 | Arithmetic | 4.5, section 5, conflict e | Proof sizes "exact", ceil(log2 n) for any record | Exact for leaf n // 3. A maximum for other leaves. 8 to 10 hashes at 1,000. 10 to 17 at 100,000 | `EP/audit_evidence.py` lines 405 and 406. Reviewer script over every leaf |
| 9 | Prototype labels | 6.1, conflict f | Only the AI Act log duties had commentary fields marked as legal-text errors | `AIA-50-1-disclosure` and `GDPR-46-49-transfer` have the same fault | `LP/duties.json`, `LP/audit_check.py` line 60 |
| 10 | Prototype | 6.1 | Not stated | No Annex I date. No Art 111(2). `duties.json` cites "Module 7" | `LP/duties.json` |
| 11 | Prototype usage | 6.1 | "Self-test" with no flag given | The flag is `--selftest`. `--self-test` runs the demo silently | `EP/audit_evidence.py` lines 21 and 502 |
| 12 | Label | 4.1 | OEIL stage pages labelled legal text | Labelled official record | OEIL pages are procedure records, not law |
| 13 | Label | 6.1 | "The law counts calendar periods", with no source | Not checked. Names Regulation 1182/71 as the check | No saved source |
| 14 | Label | 4.2 | "The law does not require it" | "Article 50 does not require it" | Only the regulation text may be called the law |
| 15 | Condition | 4.3 | CNIL range applied to agent logs without comment | Stated that the CNIL range covers security logs of staff with access. Applying it to agent records is inference | `L/cnil_journalisation.txt` lines 160 to 175 |
| 16 | Condition | 4.2 | Guidelines para 73 cited as "no logging duty" | Para 73 is about marking techniques under 50(2) | `L/guidelines_art50.txt` lines 1236 to 1241 |
| 17 | Evidence | 4.8 | Qdrant defaults from an unversioned docs page | Verified at tag v1.19.1 in `config/config.yaml` lines 139 and 142. Per segment. Snapshot expiry relabelled inferred | GitHub raw file at tag, fetched 2026-09-25 |
| 18 | Evidence | 4.10 | Remote access transfer labelled commentary, inferred | The rule is official guidance, verified. Provider access stays not checked | `L/edpb_05_2021.txt` lines 275 to 280 |
| 19 | Evidence | 4.7 table | Google Cloud 12 months shown as a general rule | Applies to the models in that table only | `E/vertex_versions.txt` lines 1066 to 1068 |
| 20 | Evidence | 4.2 | Fine rule without the SME rule | Art 99(6) SME rule already existed. Omnibus adds 99(6a) for small mid-caps. Point (g) line added | `L/aiact.txt` lines 2026 and 2028. Omnibus line 595 |
| 21 | Anchor | 4.8, 4.10 | Art 17(1) had no line. "Residency" absence cited to a report | Art 17(1) line 693. Reviewer count of "residency": 0 | `L/gdpr.txt` |
| 22 | Overlap, serious | 2.2, 2.3 | "Modules 13 to 16 have no built phases" | Modules 15 and 16 have phase files. Links moved to Module 15 phase sections 2.1 and 4.2 and Module 16 section 5.4 | `grep '^## '` output, 2026-09-25 |
| 23 | Overlap | 2.3 | Two handoffs missing | Module 15 phase 2 line 147, retention and deletion of captured ids. Module 16 phase 5 lines 436, 444 and 671, attacks on consent records and logs | The named lines |
| 24 | Gaps | Section 8, section 9 | Not listed | Gaps 15 to 18: trusted time, log attacks, Art 33(5), hand-over form. Items 24 and 25 | Each gap names its check |

### 10.4 Checked and found correct

- Conflicts a, b, e, g, h, i, j and k: the evidence named supports each resolution. Conflict c and d needed the additions in corrections 6 and 7. Conflict f needed correction 9.
- The "this is not legal advice" notice is present, line 7.
- The ownership split holds. Module 8 owns the record fields, Module 10 the deletion mechanism, Module 15 the telemetry and Module 16 security. This dossier links them and does not re-teach them.

### 10.5 Not done by the reviewer

- The saved html of the CURIA pages, the DPF review report and ISO texts were not re-opened.
- No lab was run. The reviewer did not install any SDK or server.

Summary: the dates hold after a re-fetch. The serious fixes are the "GDPR alone" claim, the Bedrock notice column, the SDK scope of the `TypeError`, and the links to the now-built Modules 15 and 16.
