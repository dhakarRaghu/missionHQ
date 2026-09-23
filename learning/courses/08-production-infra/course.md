# Course 8 — Production infrastructure: change, supply chain and proof
slug: elite-production-infra
order: 8
source: local
language: Terraform/OpenTofu HCL, Go for the harnesses, shell for the pipeline work

## Why this course

The earlier courses teach how a system behaves. This one teaches how a system
*changes*, and how you find out whether the change did what you thought.

Every phase here starts from a change that passed review and still took the
system down. A three-week-old Terraform plan restarted against an estate that
had drifted under it. A version tag retargeted beneath thousands of pipelines
that had changed nothing. A certificate renewal that broke weeks before anyone
noticed. In each case the thing that was reviewed and the thing that broke were
not the same object.

The platform courses already cover the systems themselves: Kubernetes,
Kafka, Redis, Elasticsearch, SQL and MySQL, NoSQL, Docker and Lambda. Courses
1 and 4 to 7 cover performance, storage, distributed behaviour, reliability and
design. This course covers the layer none of them own: the code that creates
the infrastructure, the pipeline that builds and ships the artifact, the
configuration that arrives without a deploy, and the rehearsal that proves the
system recovers.

Scope note: this is a senior engineer's working set, not a survey. Topics that
need hardware, a paid account or an employer's environment are named in
`notes.md` with the reason. Every lab here runs on one laptop.

## What you will be able to do

Read a Terraform plan and say exactly what it will destroy and why. Bound the
blast radius of a change at the layer that survives a deleted code block.
Validate machine-generated configuration before it reaches a consumer. Explain
what a signature and an SBOM actually prove, and what they do not. Compromise
your own build runner in a lab and show what it reached. Rehearse a restore and
publish the measured time.

## Rules for this course

- **Anchor: none. Learning-only mode.** Do not ask whether Mission HQ is the
  anchor for this course; the answer is no, and it is recorded here so
  generation does not have to ask. Mission HQ is background only.
- **Labs run locally.** A local state backend, a `kind` cluster, a local
  registry, a local runner. No cloud account, no employer environment, no
  credentials beyond ones you generate for the lab. Where a mechanism genuinely
  needs a cloud API, the lab substitutes a recorded response and says so.
- **Read `sources.md` before researching anything**, and `notes.md` before
  writing any sentence that states a version, a standard or a metric.
- **Every claim carries its evidence.** Version, date, and the command that
  produced the number. The research behind this outline found several widely
  repeated facts to be wrong; the corrections list is in `notes.md`.
- **Mechanism over tool.** Terraform is the example because its plan is
  inspectable, not because it is the answer.

---

## Phase 1 — Infrastructure as code: the state file and the plan
question: Your plan says "0 to add, 0 to change, 0 to destroy". What has it actually proven, and what has it not even looked at?
minutes: 130
assumes: declarative versus imperative (kubernetes phase 0); reconciliation loop (kubernetes phase 0); optimistic concurrency (04-storage phase 3)
introduces: state file, lineage, serial, refresh, plan graph, unknown value, the plan/apply contract, drift detection versus change detection
leaves-for-later: drift remediation and blast radius (phase 2); policy gates (phase 2); promotion between environments (phase 4)

### Why you're here

On 7 July 2023 someone restarted a GitLab CI pipeline. The Terraform plan in
it had been computed three weeks earlier, before a production database upgrade.
Engineers watching the apply read the plan mid-run and found 617 resources
queued for destruction. GitLab.com returned 503 for 137 minutes, and a
twenty-two minute window of git pushes was lost permanently.

Nothing was wrong with the plan when it was made. The open question is what a
plan is a statement *about*, and for how long that statement stays true.

### Sections

1.1 — Why state exists at all: the rejected alternative of reading the live world, and the one argument that survives (a deleted resource has no record in the world, only in state)
1.2 — What is actually in the file: version 4, `lineage`, `serial`, and why `sensitive_attributes` stores paths while the secret sits in `attributes` in cleartext
1.3 — Locking, and the orphaned lock: what the seven fields of a lock record tell you, and what `force-unlock` does and does not touch
1.4 — The plan is a graph walk: why `-target` prunes a finished graph rather than building a smaller one, and what that means for refresh
1.5 — What a plan cannot know: unknown values, why `count` must be known at plan time, and how unknown-ness propagates through modules
1.6 — The plan/apply contract: `AssertObjectCompatible` in one sentence, and the four ways a successful plan still fails at apply
1.7 — The saved plan file: why it is the right CI artifact, why it holds secrets in cleartext, and why it expires

### Lab

Build a small estate against a local backend and a null/local provider, then
break the assumptions one at a time:

1. Dump your own plan JSON and read `format_version` from it. Compare it with
   what the docs claim. Record both.
2. Corrupt `serial` and `lineage` by hand and observe what a push refuses, then
   what `-force` allows.
3. Write a resource whose `count` depends on another resource's output. Capture
   the exact error, then fix it two ways and compare the plans.
4. Save a plan, change the world underneath it, apply the saved plan, and
   record what happened.

### Demonstrate

A written answer to "what does an empty plan prove?" of at most 300 words,
citing your own captured output for each claim, plus the plan JSON showing the
`format_version` you actually observed.

### Test out

- **Explain**: why `terraform apply <planfile>` performs no refresh, and what that means for a plan that sat in a queue for an hour.
- **Predict**: given a plan JSON with one `delete_because_no_resource_config`, say what changed in the source and whether `prevent_destroy` would have stopped it. Then check.
- **Demonstrate**: produce a config change that yields an empty plan while the live resource is wrong.

---

## Phase 2 — Drift, blast radius, and the limits of the test ladder
question: You have fmt, validate, tflint, checkov and a policy gate in CI, and they all pass. Which class of failure have you ruled out, and which have you not touched?
minutes: 140
assumes: state and plan (1.1-1.7); the plan/apply contract (1.6); SLO and error budget (inference-internals 5B)
introduces: drift versus change, permadiff, the three rings of destroy protection, policy as code, plan-assertion tools and their blind spot, blast-radius scoring
leaves-for-later: configuration arriving without a deploy (phase 3); rehearsing recovery (phase 6)

### Why you're here

On 5 April 2022 an Atlassian team ran a routine deactivation. The identifiers
they supplied were site identifiers, not app identifiers, and the API accepted
both in the same parameter. Peer review checked the operation and did not
cross-check the target set. 883 sites were deleted and restoration took up to
14 days.

The review was real. It checked the verb and not the object set. The question
is which control catches that, and at which layer it has to live.

### Sections

2.1 — Drift and change are different questions: separating `resource_drift` from `planned_change` in the JSON UI stream
2.2 — What refresh costs: per-resource round trips, default parallelism of 10, and why the performance workaround (`-refresh=false`) is itself the drift generator
2.3 — Permadiff, and its four root causes: eventual consistency, equivalent-but-not-equal, response disconnect, and colliding defaults
2.4 — Three concentric rings of destroy protection, and why only the outermost survives deleting the code block
2.5 — Policy as code where it belongs: gating the plan JSON, not the HCL, and blast radius as a score rather than a rule
2.6 — The blind spot every plan-assertion tool inherits: unknown values, dynamic blocks, unevaluated functions
2.7 — The bug that defeats the whole ladder: a config change that produces no plan at all

### Lab

The centrepiece is section 2.7, run as an experiment:

1. Reproduce the AWS provider v4.9.0 S3 behaviour in a recorded-response
   harness: remove a `cors_rule` block from config and show the rule remains
   live while the plan is empty.
2. Run the full ladder against it — `fmt`, `validate`, `tflint`, `checkov`,
   `terraform test`, and a conftest policy over the plan JSON. Record each result.
3. Set `prevent_destroy`, delete the resource block, plan, and record whether
   the destroy is allowed. Explain the result from the guard clause, not from
   the docs.
4. Write a policy that gates on `action_reason` and show it catching what
   `prevent_destroy` cannot.

### Demonstrate

A one-page table: seven failure classes down the side, your six tools across
the top, each cell filled from your own run, not from documentation. Every
"no" cell needs one sentence saying why.

### Test out

- **Explain**: why a resource can be protected in state and unprotected in code at the same time.
- **Predict**: given a plan JSON containing an unknown value inside a policy's target expression, say what your policy will decide. Then run it.
- **Demonstrate**: a change your CI approves and your cloud would regret, with the gate that catches it.

---

## Phase 3 — The changes that arrive without a deploy
question: Nobody deployed anything, nobody edited a config file, and it broke at 04:00. What changed?
minutes: 130
assumes: config as production code, validation of generated config, staged rollout, feature flags, rollback and compatibility windows (06-reliability 6.3); blast radius rings (2.4); SLO burn (inference-internals 5B)
introduces: latent configuration, expiry as a scheduled change, provider quota as an external ceiling, third-party quota exhaustion, control-plane version skew, last-known-good poisoning
leaves-for-later: signing and provenance of the artifact (phase 5); rehearsing the recovery (phase 6)

### Why you're here

Course 6 phase 3 taught you to treat a config push like a deploy: version it,
validate it, roll it out in stages, and be able to roll it back. Assume all of
that from here.

This phase is about the changes that never enter that pipeline. On 14 May 2026
ImprovMX's SMTP certificates expired. Auto-renewal had been silently broken
weeks earlier by an unrelated credential rotation, and the expiry monitoring
did not fire. Nobody pushed anything. The system changed because time passed.

The same shape appears in a broken failover setting nobody reads until the
failover, in a provider quota you did not set, in a third-party rate limit you
hit on a schedule, and in two control-plane versions writing the same record.
None of these is a deploy, so none of them meets a canary.

### Sections

3.1 — Latent configuration: fail-over, retry, backup and replication settings that nothing reads until the incident, and what fraction of them have no startup check at all
3.2 — Exercising the failure path at startup: making latent settings non-latent, and what that costs
3.3 — Expiry as a scheduled change: certificates and credentials, why the renewal path breaks silently, and what shortening validity to 47 days does to a manual process
3.4 — Rotation has an order: the two-phase rule, and why deleting the old secret before confirming the new one is a distinct failure
3.5 — Provider quotas: an external ceiling you cannot compute, tracked per account and per region, and why the standby region needs headroom for the failover to land
3.6 — Third-party quota exhaustion: a limit that resets on a schedule, and the sawtooth outage that follows
3.7 — Control-plane version skew: two builds, each correct alone, writing one shared record — and last-known-good poisoning, where the rollback target is the broken thing

### Lab

No deploys allowed in this lab. Every failure must arrive on its own.

1. Take a service with a failover setting. Break the setting, confirm nothing
   notices, then trigger the failover and record how long the fault was latent.
   Add a startup check that reads the setting and measure what it costs.
2. Issue a short-lived local certificate. Break the renewal path by rotating
   the credential it uses. Measure the time from breakage to first symptom, then
   add the alert that would have caught it, and prove the alert fires.
3. Rotate a secret in the wrong order and record the failure. Then do it in
   two phases and show zero failed requests.
4. Build a client against a local rate-limited dependency that resets hourly.
   Exhaust the quota without caching, and reproduce the sawtooth. Add caching
   and measure the new steady state.
5. Run two versions of a writer against one shared record, each valid alone.
   Produce a record neither version can read, then show your rollback landing
   on it.

### Demonstrate

A written inventory of every way the system you run can change without a
deploy: expiry dates, quota ceilings, external limits, and settings nothing
reads. For each row, say what would notice, and how long it would take. Plus
the alert from lab step 2, proven firing.

### Test out

- **Explain**: why a staged rollout and a canary cannot catch any of the failures in this phase.
- **Predict**: given a quota, a request rate and a reset interval, say when the first failure occurs and whether it recurs. Then measure it.
- **Demonstrate**: a latent setting made non-latent, with the before and after timings.

---

## Phase 4 — Delivery: build once, promote, reconcile
question: The artifact in production passed every test in staging. Is it the same artifact?
minutes: 130
assumes: image tags and digests (docker phase 2); registries (docker phase 3); rolling update, Helm, rollback (kubernetes phase 4); config separated from artifact (3.4)
introduces: build-once-and-promote, hermetic build, the promotion artifact, pull-based reconciliation, self-heal versus rollback, digest pinning
leaves-for-later: who signed the artifact (phase 5); whether staging resembles production at all (phase 6)

### Why you're here

A tag is a mutable pointer. On 14 March 2025 an attacker with a stolen token
retargeted the existing version tags of a GitHub Action used by over 23,000
repositories at a single malicious commit. Every workflow pinned to a tag
silently started running new code. Nothing in those repositories changed.

This phase is about what moves between environments, and what makes "the same
artifact" a checkable claim rather than an assumption.

### Sections

4.1 — Build once and promote: the original rule, and its harder half — deploy the same way to every environment
4.2 — Hermetic builds: what isolation from the host buys, what it does not, and why distributed builds force the issue
4.3 — What promotion actually moves: digests not tags, and what gets left behind when you re-tag
4.4 — Pull-based reconciliation: the four GitOps principles, the reconcile interval, and drift correction as a mode rather than a switch
4.5 — The trap in self-heal: why an agent that continuously reconciles cannot also roll back
4.6 — When desired state and cluster state cannot be reconciled: immutable fields, shared field ownership, and the endless diff
4.7 — Promotion is not a deploy: why the tool that reconciles does not promote, and what fills the gap

### Lab

On a local `kind` cluster with a local registry:

1. Build an artifact, promote it by digest through three namespaces, and prove
   by hash that all three run the same bytes.
2. Retarget a tag underneath a running deployment and show what changes and
   what does not. Then pin by digest and repeat.
3. Install a reconciling agent. Enable self-heal, change a field with
   `kubectl`, and watch it revert. Then try to roll back and record what the
   agent refuses.
4. Create an endless diff on purpose by changing an immutable field, and
   resolve it two ways.

### Demonstrate

A promotion pipeline that fails closed: the same artifact reaching a third
environment, with a check that refuses to promote anything whose digest does
not match what was tested. Plus your written answer to "what did self-heal cost
you?"

### Test out

- **Explain**: why pinning to a tag is not pinning.
- **Predict**: given a reconcile interval and a manual change, say the worst-case time before reversion. Then measure it.
- **Demonstrate**: an agent-managed resource that reports Synced while being wrong.

---

## Phase 5 — The pipeline as an attack surface, and what verification proves
question: Your CI has your cloud credentials, your signing key and write access to your repository. What is stopping a pull request from using them?
minutes: 140
assumes: promotion by digest (4.3); registries and supply chain (docker phase 3); threat modelling for a service, and dependency and supply-chain risk including what a dependency can do and pinning (06-reliability 6.4)
introduces: the build threat model, ephemeral versus persistent runners, script injection in workflows, OIDC federation and the subject claim, provenance, SBOM, VEX, what a signature does and does not assert
leaves-for-later: rehearsing the compromise response (phase 6)

### Why you're here

Two researchers, separately, got contributor status on large projects with a
one-character typo fix, then targeted persistent self-hosted runners by label.
One compromised GitHub's own runner-image build fleet. The other read
`GITHUB_TOKEN` out of `.git/config` on a shared runner and reached 93
repositories in the PyTorch organisation. Both were paid bounties.

Meanwhile, of the organisations using SBOMs that the Cyber Safety Review Board
interviewed after Log4j, none reported having used them to find a vulnerable
deployment.

### Sections

5.1 — What a compromised build reaches: secrets, the cache, the artifact, and other builds sharing the machine
5.2 — Ephemeral or not: the one-line log test that tells you which kind of runner you are on, and why it decides everything else
5.3 — Untrusted input in a privileged context: script injection, the dangerous trigger, and the two-workflow pattern
5.4 — Cache and artifact poisoning: why read-only repository permissions do not help
5.5 — OIDC federation instead of long-lived keys, and the one missing condition that opens the role to the whole platform
5.6 — Provenance: what "this artifact came from this source through this builder" asserts, and the one field a verifier actually decides on
5.7 — SBOM: name matching versus reachability, why two tools disagree about the same repository, and where VEX fits
5.8 — The honest limit: which attacks provenance and signing would not have caught, and why

### Lab

Run a local CI server with a persistent runner and attack your own pipeline:

1. Determine whether your runner is ephemeral from the logs alone. Then make it
   persistent and leave a process behind that survives a job.
2. Land a script injection through a job input and print a secret. Fix it with
   the environment-variable pattern and show the payload failing.
3. Poison a cache entry from a low-privilege job and have a privileged job
   consume it.
4. Decode a real published attestation bundle and walk its four layers by hand.
   State what each layer proves.
5. Generate an SBOM for one repository with two different tools and diff the
   component lists. Explain every difference.

### Demonstrate

A written threat model for your own pipeline, with each of the five lab results
attached as evidence, and one paragraph naming which of your controls would not
have stopped a stolen publish token.

### Test out

- **Explain**: what a verified signature tells you about the safety of the code, precisely.
- **Predict**: given a trust policy with an audience condition and no subject condition, say who can assume the role. Then check against the documented behaviour.
- **Demonstrate**: two SBOMs of one repository that disagree, with the root cause of each difference named.

---

## Phase 6 — Proving it: parity, rehearsal and recovery
question: You have never restored this database. What is your recovery time?
minutes: 140
assumes: everything above; SLO and error budget (inference-internals 5B); incident roles and rollback (inference-internals 6B); metastable failure (06-reliability phase 2)
introduces: the parity inventory, request-level isolation, shadow traffic and its limits, the chaos experiment as a written hypothesis, the game day, restore time as a measured objective
leaves-for-later: nothing — this is the last phase

### Why you're here

On 2 September 2025 Matrix.org lost a primary database during routine
maintenance, failed over, and then lost the secondary while trying to restore
the original. Recovery took about 24 hours for 51 TB. WAL archiving to S3 had
been silently broken. The backup tool was too old to read its own incremental
backups. Replay ran at a fraction of the expected rate.

Every one of those facts was discoverable before the incident. None of them had
been measured.

### Sections

6.1 — The parity inventory: naming every axis on which your pre-production environment differs from production, and which differences are deliberate
6.2 — Why parity is partly impossible: production runs several versions at once, so it represents no single build
6.3 — Isolating a change inside a shared environment: request-level routing, and the part it cannot isolate
6.4 — Validating in production: choosing between replay, shadow traffic, canary and experiment by whether the operation is idempotent
6.5 — Shadow traffic's sharp edges: fire-and-forget, the default mirror percentage, and the header that tells a downstream it is serving a copy
6.6 — The chaos experiment as a written hypothesis: steady state, the variable, the blast radius, and the stop condition decided in advance
6.7 — The game day: rehearsing the response, not just the failure
6.8 — Restore as a number: measuring it, publishing it, and re-measuring it after every version bump

### Lab

1. Write the parity inventory for the stack you built in phases 4 and 5. For
   each axis, say whether you could close it and what it would cost.
2. Mirror traffic to a second instance. Measure what the mirror does to the
   shadow target's load, then find out what happens when the shadow is slower
   than the primary.
3. Run one chaos experiment with the hypothesis written down first. Kill the
   dependency your steady-state metric depends on. Record whether the
   prediction held.
4. Destroy your lab database and restore it from your own backup. Time it.
   Then break the backup the way Matrix.org's was broken, and time it again.
5. Run a 45-minute game day against your own stack with the lab notes as the
   runbook. Note every step where the runbook was wrong.

### Demonstrate

A published recovery number with its conditions: data volume, tool versions,
the exact restore command, and the date measured. Plus the corrected runbook
from the game day, with the diff from the original.

### Test out

- **Explain**: why an environment that is a perfect copy of production still fails to catch a whole class of defect.
- **Predict**: state your restore time before running it, then run it. Passing requires being within 2x, and explaining the gap.
- **Demonstrate**: a game day that surfaced a wrong step in your own runbook.

---

## Ledger

Terms this course assumes from elsewhere, with their source:

| Term | Introduced in |
|---|---|
| reconciliation loop, desired state | kubernetes phase 0 |
| rolling update, canary, rollback, Helm values layering | kubernetes phase 4 |
| image tags, digests, registries, supply chain | docker phases 2-3 |
| SLO, error budget, burn-rate alerting | inference-internals 5B |
| retry amplification, circuit breaker | inference-internals 5A |
| incident roles, postmortem | inference-internals 6B |
| optimistic concurrency | 04-storage phase 3 |
| metastable failure, bulkheads, recovery ramps | 06-reliability phase 2 |
| config as production code, validation of generated config, staged rollout, feature flags, rollback and compatibility windows | 06-reliability phase 3 |
| threat modelling, dependency and supply-chain risk, pinning | 06-reliability phase 4 |

**Boundary with 06-reliability phase 3.** That phase owns the discipline of a
config *push*: versioning it, validating it, ramping it, rolling it back. It
already uses the doubled-generated-file and the 21-versus-20-field incidents as
its worked examples. This course does not repeat any of that. Phase 3 here
covers only the changes that never enter a push pipeline at all — expiry,
rotation order, quota ceilings, latent settings and control-plane skew.

Terms this course introduces that later work may assume: state file, plan
graph, unknown value, drift versus change, permadiff, blast-radius ring,
latent configuration, quota headroom, build-once-and-promote, hermetic build,
reconciliation agent, provenance, SBOM, parity inventory, restore objective.
