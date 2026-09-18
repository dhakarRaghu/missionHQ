# Notes for course 8

Two short lists the phases refer to. Both exist so the written material does
not repeat facts that turned out to be wrong, and does not promise labs that
cannot run on a laptop.

## Deliberately out of scope

Each of these had real evidence behind it in the research. Each is excluded
because a senior backend engineer cannot practise it without hardware, a paid
account, or an employer's environment. Naming them is better than pretending
the course is complete.

| Topic | Why excluded |
|---|---|
| BGP, anycast, route leaks, BYOIP | Needs a real AS and peering. No laptop lab exists. |
| Data centre power and cooling | Physical. The Google Cloud europe-west4-a writeup is worth reading once, not building a phase on. |
| GPU fleet operations | Needs GPUs. Belongs with the inference course if ever. |
| FinOps and cost attribution | Needs a real bill. The mechanism is a join, not an infrastructure skill. |
| FedRAMP and regulatory authorization | Needs an authorized environment and an auditor. |
| Post-quantum migration, PKI at org scale | Real, but the practising unit is an organisation, not an engineer. Certificate *expiry* is in phase 3, which is the part an engineer owns. |
| Workload identity platforms (SPIFFE/SPIRE) | Strong job-market signal, but it is a platform-team build. Phase 5 covers the part a service owner needs: federated short-lived credentials instead of stored keys. |

If any of these becomes relevant later, it is a separate course, not a phase
bolted onto this one.

**An independent check disagreed on two of these.** A separate research pass
argued that the network layer below the application (anycast, virtual IPs,
encapsulation and MTU, IP address planning) and certificate and workload
identity lifecycle are both defensible standalone gaps, with primary-source
evidence. Both exclusions stand for now, for one reason each:

- *Network layer*: the practising unit is a real autonomous system with real
  peering. There is no laptop lab. Worth revisiting if a simulator is found.
- *Certificate and identity lifecycle*: the part an individual engineer owns is
  in this course already, as phase 3.3 and 3.4 (expiry, renewal breakage,
  rotation order) and phase 5.5 (federated short-lived credentials instead of
  stored keys). What is excluded is the platform build: private certificate
  authorities, revocation at scale, SPIFFE/SPIRE trust domains. That is a
  platform-team course.

The same check found one thing genuinely missing that has now been added:
**provider quotas as an external ceiling**, including keeping enough quota
headroom in the standby region for a failover to land. That is phase 3.5
and 3.6.

## Corrections to facts that are commonly repeated wrongly

Check these before writing any phase content. Each was verified against
primary source during the research pass on 2026-09-18, and each contradicts
something widely published.

**Infrastructure as code**

- Terraform plan JSON `format_version` is `"1.2"` at v1.16.3. The docs still say `"1.0"`. Read it from your own output.
- `-target` does not refresh non-targeted resources. The targets transformer removes those nodes from the graph, so they are never walked.
- `terraform apply <planfile>` performs no refresh at all.
- `prevent_destroy` does not survive deleting the resource block, because the check returns early when there is no config. This is a mechanism, not a caveat.
- tfsec was never archived. It has simply had no release since 2025-05-02.
- CDKTF is discontinued, archived 2025-12-10. Do not put it in any lesson.
- OpenTofu does not accept state written by Terraform 1.6.0 or later. Migration is one-way in practice.
- The AWS 2017 S3 writeup never uses the word "typo". It says a larger set of servers was removed than intended. Use their wording.

**Supply chain**

- SLSA v1.0 is not current. v1.2 was approved 2025-11-24 and added a Source track with four levels. The Build track has L0 to L3 only; there is no Build L4.
- The NTIA minimum elements are superseded. CISA's 2026 minimum elements, version 2.1, published 2026-07-29, define 17 fields rather than 7 and drop SWID.
- SPDX 3.0 is not an ISO standard. ISO/IEC 5962:2021 is SPDX 2.2.1. CycloneDX 1.7 *is* ECMA-424, 2nd edition.
- "Software Engineering at Google" chapter 18 does not contain the word "hermetic". The Google source for hermeticity is the SRE Book, chapter 8.
- Sigstore's Rekor v2 went GA on 2025-10-10, and in June 2026 the project stated the public instance will keep using v1 as the default for the foreseeable future. Teach this as a migration that was shipped and not adopted, not as a failure.

**Measurement**

- There is no 2026 DORA report. The 2025 report contains no Elite/High/Medium/Low table; the word "elite" does not appear in it. The last threshold table is 2024.
- "MTTR" is not a DORA metric. It was renamed failed deployment recovery time in 2023 and moved from stability to throughput.
- The Beck and Orosz article on measuring developer productivity is not a criticism of DORA. It holds DORA up as the good example.

**Things with no published number, where the honest answer is to say so**

- No measurement exists of what fraction of incidents came from changes that passed staging.
- No independent, non-vendor measurement of infrastructure drift prevalence exists. Every published figure has an undisclosed denominator.
- No measurement exists of how often consumers actually verify signatures. Verification is client-side and leaves no trace in the transparency log, which is the structural reason.
- No published measurement exists of what fraction of projects reach each SLSA level.

Do not let a phase imply any of these numbers exists.
