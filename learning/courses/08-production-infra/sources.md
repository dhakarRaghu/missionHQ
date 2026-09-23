# Sources for course 8, pinned per phase

Read this before generating any phase of `elite-production-infra`. It exists so
generation does not have to repeat the research.

Everything below was fetch-verified on **2026-09-18** by a research pass that
used its full web-search budget. Re-verify a version number before publishing,
because versions move. Do not re-verify the incidents; they are dated and fixed.

Labels follow `SKILL.md`. Anything not listed here is **not checked**, and the
corrections list in `notes.md` names facts that are commonly published wrongly.

---

## Phase 1 — state and the plan

**Open with.** GitLab, 2023-07-07. A CI pipeline restarted a Terraform plan
computed three weeks earlier. Engineers reading the plan mid-apply saw **617
resources to be destroyed**. GitLab.com returned 503 from 16:25 to 18:42 UTC,
137 minutes. Git pushes between 15:55 and 16:17 UTC were lost permanently.
`gitlab.com/gitlab-com/gl-infra/production/-/issues/15999` (review) and
`/issues/15997` (incident).

**Version baseline.** Terraform v1.16.3, released 2026-09-16. OpenTofu v1.12.6,
2026-08-19.

**Primary sources.**

| Claim | Source |
|---|---|
| Why state exists; the rejected tag-based alternative; "round trip time for each resource is hundreds of milliseconds" | `developer.hashicorp.com/terraform/language/state/purpose` |
| State format version 4; `sensitive_attributes` holds paths while `attributes` holds the cleartext secret | `internal/states/statefile/version4.go` |
| The seven fields of a lock record (`ID`, `Operation`, `Info`, `Who`, `Version`, `Created`, `Path`) | `internal/states/statemgr/locker.go` |
| `-force` disables the lineage and serial safety checks on push | `developer.hashicorp.com/terraform/cli/commands/state/push` |
| Plan JSON `FormatVersion = "1.2"` at v1.16.3, against `"1.0"` in the docs | `internal/command/jsonplan/plan.go` line 34 |
| The plan/apply contract in one sentence | `internal/plans/objchange/compatible.go`, `AssertObjectCompatible` |
| `terraform apply <planfile>` performs no refresh: zero occurrences of "refresh" | `internal/terraform/graph_builder_apply.go` |
| `-target` removes non-targeted nodes from the graph, so they are never refreshed | `internal/terraform/transform_targets.go`, `g.Remove(v)` |
| Saved plans hold secrets in cleartext; a saved plan can go stale | `developer.hashicorp.com/terraform/cli/commands/plan` |

**Failure-at-apply case studies.** `terraform-provider-aws` issue 33690
(provider changed the planned action from Update to DeleteThenCreate) and issue
8029 (`InvalidInstanceID.NotFound` at ~1000 VMs).

---

## Phase 2 — drift, blast radius, the test ladder

**Open with.** Atlassian, 2022-04-05. A deactivation ran with site identifiers
instead of app identifiers, and the API accepted both in the same parameter.
Review checked the operation, not the target set. **883 sites deleted, 775
customers**, restoration up to 14 days, complete 2022-04-18.
`atlassian.com/blog/atlassian-engineering/post-incident-review-april-2022-outage`

**The centrepiece exercise.** AWS provider v4 S3 drift behaviour. v4.0.0 shipped
2022-02-10 and made 13 `aws_s3_bucket` arguments read-only. v4.9.0, 2022-04-07,
reversed it 56 days later and introduced the bug: drift detection runs for those
parameters **only if a configuration value is provided**. Remove a `cors_rule`
block and the rule stays live while the plan is empty. Source: the provider's
`website/docs/guides/version-4-upgrade.html.markdown`.

**Primary sources.**

| Claim | Source |
|---|---|
| `resource_drift` versus `planned_change` as separate JSON UI events | `terraform/internals/machine-readable-ui` |
| `prevent_destroy` is 22 lines, and the `n.Config == nil` guard is why it dies with the code block | `internal/terraform/node_resource_abstract_instance.go`, `checkPreventDestroy` |
| The three rings: HCL, provider attribute, cloud API. Only the third survives a deleted block | `google_sql_database_instance` has both `deletion_protection` (Terraform scope) and `deletion_protection_enabled` (all surfaces) |
| Four permadiff root causes: eventual consistency, equivalent-not-equal, response disconnect, colliding defaults | `terraform-provider-aws` issue 23288 |
| Blast radius as a weighted score, not a yes/no rule; and the three blind spots (unknown values, dynamic blocks, unevaluated functions) | `openpolicyagent.org/docs/terraform` |
| `terraform test` `command` defaults to `apply` and creates real infrastructure; mocked strings are 8-character random | `terraform/cli/commands/test`, and `internal/configs/test_file.go` |
| `-parallelism` defaults to 10 | `plan` and `apply` command references |

**EC2 throttling, for the refresh-cost section.** Per account, per Region, per
action. Non-mutating `Describe*` bucket 100, refill 20/sec. **Unfiltered and
unpaginated** `DescribeInstances`, `DescribeVolumes` and similar: bucket 50,
refill 10/sec. Mutating: bucket 50, refill 5/sec. Source:
`docs.aws.amazon.com/AWSEC2/latest/APIReference/throttling.html`.

**Honest gap to state in the phase.** No independent, non-vendor measurement of
drift prevalence exists. Firefly's State of IaC 2025 reports 89% IaC adoption
and **only 6% with complete coverage**, but publishes no sample size and sells
drift detection. Use the 6% figure only with that caveat attached.

---

## Phase 3 — changes that arrive without a deploy

**Open with.** ImprovMX, 2026-05-15. SMTP certificates expired because
auto-renewal had been broken weeks earlier by a rotated credential, and the
third-party expiry monitor did not fire.
`improvmx.com/blog/2026-05-15-postmortem-smtp-tls-cert-expiry/`

**Rotation, three verified incidents of one class.**

| Incident | Mechanism |
|---|---|
| Cloudflare R2, 2025-03-21, 21:38–22:45 UTC | New credentials deployed to a development instance instead of production. 100% write failure, ~35% read failure |
| GitHub Audit Log, 2026-04-01, 4 minutes | "lost connectivity to its backing data store due to a failed credential rotation" |
| ImprovMX, 2026-05-14/15 | Renewal credential broken weeks earlier, monitoring silent |

**Quotas.**

- Provider ceilings: AWS Well-Architected reliability pillar makes quotas the first best-practice area. `REL01-BP02` manage quotas across accounts and regions. `REL01-BP06` keep a sufficient gap between current quota and maximum usage **to accommodate failover**. `docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/manage-service-quotas-and-constraints.html`
- Third-party exhaustion: Railway, 2026-01-26 to 2026-01-29. "~82 new tokens per second" against a 2,000/hour GitHub limit, with an hourly sawtooth as each window reset. `blog.railway.com/p/incident-report-january-26-2026`

**Latent configuration, with numbers.** PCheck, OSDI 2016. Latent-config errors
are **47.6%** of one vendor's customer config issues but **75.0%** of the
high-severity ones. Parameters with no startup check at all range from **14.0%
to 93.2%** by system (HDFS 41 of 44 = 93.2%). Scope caveat: the study covers
only RAS parameters, 182 of 1,180.
`people.cs.uchicago.edu/~shanlu/paper/osdi16-final321-pcheck.pdf`

**Why config checks miss.** Yin et al., SOSP 2011, 546 cases. 27% of support
cases are config-related, **31% of high-severity**, the largest category.
**38.1%–53.7%** of parameter mistakes are illegal values a checker could catch.
Only **7.2%–15.5%** of systems emit a message that pinpoints the parameter.
`sigops.org/s/conferences/sosp/2011/current/2011-Cascais/printable/12-yin.pdf`

**Version skew and last-known-good poisoning.** Azure Front Door, 2025-10-29,
15:45 UTC to 00:05 UTC. "performed across two different control plane build
versions, resulted in incompatible customer configuration metadata", and the
data-plane crash "surfaced asynchronously, after approximately five minutes",
so it passed the synchronous health gate and the bad config became the rollback
target. `azure.status.microsoft/en-us/status/history/?trackingId=YKYN-BWZ`

**Certificate validity timeline.** CA/Browser Forum ballot SC-081v3 passed
2025-04-11, 25 votes to 0. Maximum public TLS validity: 200 days from
2026-03-15, 100 days in 2027, **47 days in 2028**.

**Do not reuse here.** The Cloudflare 18 Nov 2025 generated-file incident and
the CrowdStrike 21-versus-20-field incident both belong to 06-reliability phase
3, which already uses them.

---

## Phase 4 — build once, promote, reconcile

**Open with.** tj-actions/changed-files, 2025-03-12 00:00 to 2025-03-15 12:00
UTC. A stolen PAT was used to **retarget existing version tags** at one
malicious commit, `0e58ed8671d6b60d0890c21b07f8835ace038e67`. Over **23,000
repositories** used the action. CVE-2025-30066, High, CVSS 8.6. Secrets were
dumped from runner process memory into build logs, which are public on public
repositories. Patched in v46.0.1. Pinning to a full commit SHA was immune.

**Version baseline.** Argo CD v3.5.3 (2026-09-14). Flux v2.9.5 (2026-08-31).
Kargo v1.11.4 (2026-09-03). OpenGitOps principles v1.0.0.

**Primary sources.**

| Claim | Source |
|---|---|
| Build once, and deploy the same way to every environment | Humble and Farley, *Continuous Delivery* ch. 5, excerpt at `informit.com/articles/article.aspx?p=1621865&seqNum=3`. Note: Fowler's DeploymentPipeline bliki does **not** state this |
| Hermeticity definition and the four causes of non-hermeticity | `bazel.build/basics/hermeticity` |
| Google's hermetic-build sentence | SRE Book ch. 8. **Not** *Software Engineering at Google* ch. 18, which does not contain the word |
| Digests are immutable, tags move; avoid `:latest` | `kubernetes.io/docs/concepts/containers/images/` |
| Argo CD: reconcile 120s + up to 60s jitter; self-heal timeout 5s; prune off by default; **rollback cannot be performed with automated sync enabled** | `argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/` |
| Flux: `.spec.interval` required, minimum 60s; `driftDetection.mode` is `enabled`/`warn`/`disabled`; `wait: true` silently ignores `healthChecks` | `fluxcd.io/flux/components/kustomize/kustomizations/` and the v1 API reference |
| Endless diff causes: HPA reordering `spec.metrics`, Helm `randAlphaNum`, CRD marshalling (`100m` vs `0.1`) | `argo-cd.readthedocs.io/en/stable/user-guide/diffing/` |
| GitOps gives no promotion guidance | `docs.kargo.io/user-guide/core-concepts` |
| Sync waves: 2-second delay between waves, `ARGOCD_SYNC_WAVE_DELAY` | `argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/` |

**Lab checklist source.** Kostis Kapelonis, "30 Argo CD antipatterns for GitOps",
published 2025-08-19 at `octopus.com/blog/30-argo-cd-antipatterns-for-gitops`
(the codefresh.io URL 301-redirects there). Item 12 is mutable tags, item 19 is
attempting to promote Applications.

---

## Phase 5 — the pipeline as an attack surface

**Open with, either.** Adnan Khan poisoned GitHub's own `actions/runner-images`
build fleet, 2023-12-20, $20,000 bounty. Or John Stawinski on PyTorch,
2024-01-11, $5,000: `GITHUB_TOKEN` read from `.git/config` on a persistent
runner during an active workflow, reaching 93+ repositories. Both gained
contributor status with a trivial PR, then targeted runners by label.

**The detection trick for the lab.** A workflow log containing "Cleaning the
repository" means `actions/checkout` ran on a **non-ephemeral** runner.

**Primary sources.**

| Claim | Source |
|---|---|
| Self-hosted runners "can be persistently compromised by untrusted code in a workflow" | `docs.github.com/en/actions/reference/security/secure-use` |
| Pinning to a full-length commit SHA is "the only way to use an action as an immutable release" | same page |
| Pwn requests: `pull_request_target` plus explicit checkout of the PR head | GitHub Security Lab part 1, 2021-08-03 |
| Script injection, and the intermediate-environment-variable fix | part 2, 2021-08-04 |
| Cache and artifact poisoning, TOCTOU, `workflow_run` boundaries | part 4, Alvaro Munoz, 2025-01-16 |
| Cache poisoning mechanics: branches are the boundary, cache token valid 6 hours after the job, 10 GB eviction | `adnanthekhan.com/2024/05/06/the-monsters-in-your-build-cache-github-actions-cache-poisoning/` |
| The platform fix, read-only cache for untrusted triggers | GitHub changelog, 2026-06-26 |
| OIDC: the `sub` condition is what scopes the role; repositories created after **2026-07-15** use an immutable subject format carrying owner and repo IDs | `docs.github.com/.../oidc-in-aws` |

**Provenance and inventory.**

- **SLSA v1.2**, approved **2025-11-24**, added the **Source track** (L1–L4). Build track is L0–L3; there is no Build L4. `slsa.dev/spec/v1.2/build-requirements` and `/source-requirements`.
- **in-toto** attestation framework v1.2, release v1.2.0 dated 2026-03-18. Four layers: Predicate, Statement, Envelope, Bundle.
- **Sigstore**: Fulcio issues certificates valid for **10 minutes**; Rekor public instance SLO **99.5%**. Rekor v2 went GA 2025-10-10, and on 2026-06-28 the project stated the public instance keeps **v1** as default for the foreseeable future. Teach that as a shipped migration that was not adopted.
- **Worked example, runnable with curl**: `registry.npmjs.org/-/npm/v1/attestations/react@19.3.0` returns two attestations. The SLSA one is `predicateType: https://slsa.dev/provenance/v1`, in an in-toto Statement v1, in a DSSE envelope, Fulcio certificate, Rekor logIndex 2,771,636,351, carrying both an inclusion proof and an inclusion promise.
- **The verification CVE to teach**: CVE-2026-22703, cosign accepted **any** valid Rekor entry whether or not it referenced the artifact. A regression of a bug fixed in 2022.

**SBOM, the honest numbers.**

| Finding | Value | Sample |
|---|---|---|
| Organisations using SBOMs that used them to find vulnerable Log4j deployments | **none reported** | CSRB report, 2022-07-11, ~80 organisations |
| Inter-tool consistency for package detection | 7.84%–12.77% | 55,444 SBOMs, 6 tools, 3,287 repos |
| SBOMs declaring no dependency edges at all | 52.9% | 78,612 files |
| Syft coverage of JavaScript lockfile packages | 43.78% (Trivy 32.71%, cdxgen 98.72%) | ANSSI/Inria, arXiv 2609.19920, 2026-09-17 |
| Scanner false-positive rate | 92.0%, of which 61.9% pruned by reachability analysis | 2,414 repos |

**Spec versions.** CISA 2026 Minimum Elements v2.1, 2026-07-29, **17 fields**,
supersedes the 2021 NTIA 7. CycloneDX 1.7 is ECMA-424 2nd edition (Dec 2025).
SPDX 3.0.1 is current; ISO/IEC 5962:2021 covers SPDX **2.2.1**, not 3.0.

---

## Phase 6 — parity, rehearsal, recovery

**Open with.** Matrix.org, 2025-09-02 17:45 UTC to 2025-09-03 18:00 UTC, about
24 hours. Primary database failed during routine maintenance, the team failed
over, then lost the secondary while restoring the original. 51 TB restore. WAL
archiving to S3 had been silently broken, an outdated `wal-g` blocked
incremental restore, and replay ran at a fraction of the expected rate. No data
lost. `matrix.org/blog/2025/10/post-mortem/`

**Parity.**

| Claim | Source |
|---|---|
| The test environment added **1** Cassandra node; production added **6**, so whole replica sets were reallocated at once. 13:10–15:08 BST, 2019-07-29 | `monzo.com/blog/2019/09/08/why-monzo-wasnt-working-on-july-29th` |
| Production runs several versions at once, so it "is intentionally not representative of any given version of a binary checked into source control" | Google SRE Book ch. 17 |
| A named four-stage pre-production ladder (DOG, PIG, Canary, Global) that the WAF deliberately bypasses, plus a correctness-only test gate blind to CPU. 27 minutes, ~80% traffic lost, 2019-07-02 | `blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/` |
| Three axes on which test environments differ: traffic volume, time in environment, error states | Sillito and Kutomi, ICSME 2020, arXiv 2008.11192, 30 incidents |

**Choosing a validation technique in production.** Netflix, 2023-06-14: idempotent
and functional → replay testing; non-idempotent → sticky canary; non-functional
→ AB test or sticky canary. Their phase 1 AB test carried 1,000,000 users and
reached 100% of mobile homepage traffic in 6 months.

**Shadow traffic sharp edges.** Istio mirrors **100%** when `mirrorPercentage`
is absent. Envoy and Istio both append `-shadow` to the host header, and both
discard the response, so a shadow-side latency regression is invisible through
the client path.

**Chaos.** `principlesofchaos.org`; Basiri et al., "Chaos Engineering", IEEE
Software; the ChAP paper, ICSE-SEIP 2019; the ACM Queue GameDay roundtable
(Robbins, Krishnan, Allspaw, Limoncelli); Google DiRT; Slack's Disasterpiece
Theater. Tool versions were not verified in this pass, so check them before
naming any tool.

**Restore as a measured objective.**

- AWS Well-Architected: `REL09-BP04` periodically recover data to verify backup integrity, `REL13-BP03` test the DR implementation, `REL13-BP04` manage configuration drift at the DR site.
- Google SRE Book ch. 26: "No one really *wants* to make backups; what people *really* want are *restores*", and you only know you can recover recent state if you actually do so.
- Veeam, 2026-04-14, 900+ leaders: **90%** are confident they can recover, **28%** of ransomware victims fully recovered their data, average 72% of data recovered.
- Uptime Institute, 2026-05-13: power is the leading cause of impactful outages; **20%** of most-recent outages cost over $1M, second year running.

---

## What this pass could not verify

State these as not checked if a phase needs them.

- No measurement exists of what fraction of incidents came from changes that passed staging.
- No independent measurement of drift prevalence.
- No measurement of how often consumers verify signatures. Verification is client-side and leaves no trace in the log.
- No measurement of what fraction of projects reach each SLSA level.
- The Skyscanner 2021 IaC incident write-up. The Medium slug 404s and the correct URL was not found. Do not cite it.
- Chaos tooling versions for 2026.
