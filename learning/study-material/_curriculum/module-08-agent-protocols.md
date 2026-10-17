# Module 08: Agent protocols and agent identity

Research date: 2026-09-23. Status: research dossier, not course material. Reviewed on 2026-09-23 by an independent reviewer. Corrections are in the text and listed in section 13, Review log. Corrections found while the five phases were built are in the text and listed in the last section.

Module question: **Your agent must call another company's agent and a partner's MCP server on behalf of a signed-in user. What does each protocol carry, who is the agent acting as at each hop, and what can you prove afterwards?**

This question replaces the draft question in `_curriculum/README.md`, "What can the protocol express, and what does it silently leave to trust?". The README question is still answered, in section 1 and in 4.1, 4.2 and 4.11.

## How this dossier was built

- **Inputs.** Three research reports written on 2026-09-23 in `scratchpad/reports/`: `research_agent-protocols_a2a.md`, `research_agent-protocols_identity.md` and `research_agent-protocols_web.md`. Their saved sources, run files and labs are in `scratchpad/research_agent-protocols/<topic>/`. Below, `AP/` means `scratchpad/research_agent-protocols/`. `SDK/` means `AP/a2a/lab/.venv/lib/python3.12/site-packages/a2a/`, the installed `a2a-sdk` 1.1.5 source. `D8/` means `scratchpad/dossier_m08/`, the dossier author's notes.
- **Other inputs.** The Module 8 brief in `_curriculum/README.md`. The Module 8 section of `scratchpad/reports/curriculum_audit.md`, lines 261 to 297. The rules in `scratchpad/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`.
- **Work done for this dossier.** No lab ran. The dossier author did four read-only things:
  1. Re-grepped 115 anchors of section 4 in their saved files. Script `D8/anchor_check.py`, output `D8/anchor_check.txt`. Line numbers in `D8/anchor_lines.txt`. Section 12 has the result.
  2. Read the installed SDK source in `SDK/` to confirm five file and line claims.
  3. Read the IETF datatracker files the identity agent saved, to settle a date conflict. Section 7, conflict c.
  4. Fetched one URL, `https://pypi.org/pypi/x402/json`, HTTP 200, saved as `D8/pypi_x402.json`. It settles conflict f.
- **Labels.** Every claim is **verified**, **inferred** or **not checked**. A verified claim names its file and line or section. "Verified by run" means a research agent ran a script on 2026-09-23 on the learner's Apple arm64 Mac, and the output file is named. An inferred claim names its basis and the check that would confirm it.
- **Run conditions for every lab number.** A2A labs used `a2a-sdk` 1.1.5 from PyPI and Python 3.12 on macOS, Apple arm64. Server and client ran on 127.0.0.1 with the JSON-RPC binding. The store was `InMemoryTaskStore` unless the row says SQLite. The output timestamps put the runs between about 15:36 and 15:41 UTC on 2026-09-23. The test agent sleeps 0.3 s before each of two artifact chunks. Identity labs: PyJWT 2.14.0 for `txchain.py`. `spiffe` 0.3.1 with PyJWT 2.13.0 and `cryptography` 50.0.1 for `svid_check.py`. The reports do not record the machine's core count, memory or load. Not checked.
- **Status words for standards.** They are used the same way in the whole dossier.
  - **RFC**: a published IETF document. Standards Track or BCP is stated each time.
  - **WG draft**: an Internet-Draft adopted by an IETF working group, named `draft-ietf-<wg>-...`. It can still change.
  - **Individual draft**: an Internet-Draft with no working group. It has no IETF standing.
  - **CG draft**: a W3C Community Group report. It is not on the W3C Standards Track.
  - **Project specification**: a specification published by an open-source project. A2A is a Linux Foundation project. MCP is published by the MCP project. Neither comes from a standards body.
  - **Vendor document**: a page from one company about its own product.
- **Terms used in the whole dossier.**
  - **Principal**: a party that can hold rights. A user, an agent or a service.
  - **Subject**: the principal on whose behalf a request is made. In a JWT it is the `sub` claim.
  - **Actor**: the principal that performs the request. RFC 8693 names it in the `act` claim.
  - **Audience, `aud`**: the service a token is meant for.
  - **Scope**: the rights a token carries, as space-separated strings.
  - **STS**: security token service. A server that takes one token and returns another.
  - **Token exchange**: RFC 8693. A client sends a token to an STS and gets a new token for another audience.
  - **Workload identity**: the identity of a running program, not of a person.
  - **SVID**: SPIFFE Verifiable Identity Document. A certificate or JWT that carries a workload's SPIFFE ID.
  - **Agent Card**: the A2A JSON document that describes an agent. It is served at `/.well-known/agent-card.json`.
  - **JWS**: JSON Web Signature, RFC 7515. `jku` is a JWS header that holds a URL of a key set.
  - **Task**: the A2A unit of work. The remote agent creates it and returns its id. An agent may also answer `SendMessage` with a direct `Message` and create no task. Verified: spec v1.0.1 section 3.1.1, `AP/a2a/spec_v101.txt` line 666.
  - **Delegation**: the actor acts for the subject and keeps its own identity. **Impersonation**: the receiver cannot tell the actor from the subject.

---

## 1. What this module is for

Module 6 teaches how one MCP call works and how an MCP server checks a token. This module covers what happens when several parties and several protocols sit between a user and the work.

The short answer: **none of the three protocols carries the delegation chain.** MCP carries an OAuth bearer token in an HTTP header. A2A declares which schemes it accepts and leaves the credential to an out-of-band process. WebMCP carries nothing and runs on the user's browser session. The chain of who acted for whom lives in OAuth token exchange, in RFC 8693 `act` claims, and in the logs each hop writes.

| Hop | What the protocol carries | Who the agent acts as | What you can prove afterwards |
|---|---|---|---|
| User signs in to your agent | Not an agent protocol. Your own login | The user authenticates. Your agent gets a user-bound token from your identity provider | Your own login record |
| Your agent to the partner's MCP server | A JSON-RPC `tools/call` with `_meta` version fields. An OAuth 2.1 bearer token in the HTTP `Authorization` header. Module 6, 5.3 | Core MCP: the token names the user and your client. The token format is set by the authorization server. Inferred, see 4.4. With the MCP Enterprise-Managed Authorization extension: an RFC 8693 exchange through the enterprise identity provider, 4.9 | What the MCP server logged, and the claims of the token if it is a JWT. Core MCP defines no audit record. 4.16 |
| Your agent to the other company's A2A agent | A `Message` with `Part`s, a `taskId` and `contextId`, the `A2A-Version` header. A credential for one of the card's `securitySchemes`, obtained "through an out-of-band process". 4.1 | Whatever that credential says. A2A has no field for a user, an actor or an audience. 4.1 | The task id and its states, only while the remote agent keeps them, 4.13. A card signature, only if you pinned the key, 4.2. Nothing about user consent, 4.11 |
| The other agent to its own tools | Hidden from you. It may use MCP. A2A spec, Appendix B | Not visible to you. The agent can send `TASK_STATE_AUTH_REQUIRED` back up the chain, 4.11 | Nothing from the protocol |
| A browser agent to a web page, WebMCP | A JavaScript call with arguments. No token, no scope, no agent id | The user, through the browser's cookies and session, 4.12 | Nothing from the protocol |

So the proof after the fact comes from three places outside the protocols:

1. A token chain from an STS that intersects scopes and writes `act` claims, 4.6 and 4.7.
2. A log line at every hop with the subject, the actor, the tool, the decision and a shared transaction id, 4.16.
3. Your own copy of the remote task's final state, taken with `GetTask`, 4.14.

Summary: the protocols move calls. OAuth token exchange and your own logs record who acted for whom.

## 2. Scope

### In scope

- What MCP, A2A and WebMCP carry about identity, authorization, delegation, consent and revocation.
- Agent Cards: what a signature proves, key sources, canonical form.
- Discovery documents: Agent Card, AI Catalog, MCP Server Card, MCP Registry, `llms.txt`, and what each proves.
- Who the agent acts as: subject and actor, delegation and impersonation, workload identity.
- OAuth token exchange, down-scoping, `act` chains, audience per hop.
- The status of each standard and draft on 2026-09-23.
- Revocation: what exists and what no protocol defines.
- Audit records for multi-hop agent calls.
- The A2A task handle, its states and the three update paths. Only as far as a caller needs them.
- Version skew between A2A 0.3 and 1.0.
- Added by Phase 5: a grant must name the action with RFC 9396 `authorization_details`, not only a scope. Verified by run: `runs/agent-protocols_p05_consent.txt` line 5.
- Added by Phase 5: token introspection with exchange lineage, from child `jti` to parent `jti`, is a third revocation fix. Verified by run: `runs/agent-protocols_p05_revoke_introspect.txt` line 7.
- Added by Phase 5: a `txn` claim in the token joins the hops. A hash chain over the log records makes the log tamper-evident. Verified by run: `runs/agent-protocols_p05_audit_tamper.txt` line 12.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| MCP wire format, stateless requests, `server/discover`, version negotiation | Module 6, 4.1 to 4.3 |
| The MCP audience check, RFC 8707, RFC 9728 metadata, the no-token-passthrough rule | Module 6, 5.3 |
| MCP tool annotations as claims, tool definitions that change after approval | Module 6, 5.1 and 5.2 |
| Durable task state, crash recovery, idempotent side effects | Module 9, dossier sections 4.5 and 4.6 |
| Human approval as a durable workflow wait | Module 9, dossier section 4.7 |
| Attacks: card spoofing walk-throughs, tool poisoning, confused deputy exploits, webhook SSRF | Module 16. The consent-cookie form of the confused deputy comes from the MCP Security Best Practices page. The spec's Confused Deputy section names static client IDs and dynamic registration, and has 0 hits for "cookie". Verified: `AP/identity/mcp/auth_security-considerations.mdx` lines 107 to 114. `scratchpad/research_tools-mcp/mcp/md/secbp.md` lines 36 to 38 |
| Audit log retention and legal duties | Module 18, per `module-16-security.md` line 33 |
| Approval screen design | Module 19, per `module-16-security.md` line 34 |
| Agent loop and permission prompts inside one harness | Module 7 |
| Agent payments: x402, AP2, UCP, Agentic Commerce Protocol | Module 22 |
| Sub-agent token cost inside one application | Module 2, 4.1 |

### Overlap with built modules

Headings were read with `grep '^## '` on `inference-internals/*.md`, `context-engineering/*.md`, `retrieval-internals/*.md`, `advanced-retrieval/*.md` and `tools-mcp/*.md` on 2026-09-23. The first four were filtered with 17 keywords. Examples are agent, auth, token, identity, task, protocol, mcp and permission. The Module 6 dossier `_curriculum/module-06-tools-mcp.md` line 55 assigns "OAuth flows, token exchange, agent identity, A2A" to Module 8.

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| MCP has no protocol session | Module 6, "4.1 — An open connection is not a session" | Only the state row of the comparison in section 5. Link 4.1 |
| Replay of sealed request state | Module 6, "4.2 — A sealed request state can be replayed" | Not repeated |
| Header and body must agree | Module 6, "4.3 — The server must check headers against the body" | Not repeated |
| Annotations are claims | Module 6, "5.1 — Annotations are claims, not permissions" | WebMCP annotations are the same kind of claim, set by the site. 4.12. Link 5.1 |
| Approval does not freeze a definition | Module 6, "5.2 — Approval does not freeze a tool definition" | A user click is not an authorization grant. 4.11 is about the grant, not the definition |
| Audience check, no passthrough | Module 6, "5.3 — Reject a token for another audience, never forward it" | Token exchange with a new audience per hop, 4.6 and 4.7. The per-hop audience check in lab L1 reuses 5.3. Link, do not re-teach |
| MCP tasks moved to an extension, DCR deprecated | Module 6 phase 4, lines 976 and 980, one line each | 4.13 uses the tasks extension for the comparison. 4.9 uses the DCR to CIMD change |
| Handles instead of payloads | Module 2, "2.4 — Handles, not payloads: shrink context at the tool" | MCP now keeps cross-call state in server-minted handles. 4.13. Different purpose: state, not context size |
| MCP server-minted handles for state | Module 6, 4.1, subsection "State that spans calls moves into a handle", `tools-mcp-phase-04-mcp-protocol.md` line 213 | 4.13 and section 5 use one line each and link 4.1. Do not re-teach the handle pattern |
| A relayed token hides the relay in the downstream log | Module 6, 5.3 lab, `tools-mcp-phase-05-mcp-trust.md` line 463: billing logs `client_id=support-agent` and nothing shows the relay | 4.4 and 4.16 start from this result. They add the actor chain and the shared transaction id. Link 5.3 |
| Sub-agents | Module 2, "4.1 — A sub-agent moves tokens, it does not remove them" | This module covers the identity of a remote agent, not the token cost of a local one |
| Inference, retrieval and advanced retrieval | No heading on identity, protocols or authorization in Modules 1, 3 and 4 | None |

---

## 3. What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2025-01 | RFC 9700, OAuth Security BCP | `AP/identity/rfc9700.txt` | Audience and action restriction become a SHOULD |
| 2025-06-23 | A2A moves to the Linux Foundation | LF press release, A2A report 2.1 | Governance leaves one vendor. Google created the protocol |
| 2025-07-30 | A2A v0.3.0: `signatures` field, mTLS, extended card, `agent-card.json` path | A2A CHANGELOG | Signed cards start here, without a canonical form |
| 2025-08-01 | `agent-card.json` registered at IANA, permanent | `AP/web/iana_wellknown.xml` line 25 | The only agent-specific registered well-known name |
| 2025-08-21 | Last IBM ACP release. The repo is archived and merged into A2A | `AP/web/ghr_i-am-bee_acp.rel.json` | Drop ACP from comparisons |
| 2025-08-29 | OpenID SSF 1.0 and CAEP 1.0 Final | `AP/identity/oidf/` | A finished standard to push revocation events |
| 2025-09-08 | MCP Registry in preview. API frozen at v0.1 on 2025-10-24 | MCP registry README | Still preview on 2026-09-23 |
| 2025-11-25 | MCP adds experimental Tasks | A2A report 3 | MCP starts to hold long-running state |
| 2026-01-21 | SEP-2127, MCP Server Cards, opened. Still `in-review` | `AP/web/sep2127.json` | Pre-connection MCP discovery is not in the spec |
| 2026-03-02 | `draft-klrc-aiagent-auth-00`. Later adopted by the WIMSE WG and replaced by AIMS -00 | `AP/identity/dt/draft-klrc-aiagent-auth.json` and `.html` | Multi-vendor agent-auth draft. "First" is not checked |
| 2026-03-12 | A2A v1.0.0: PascalCase methods, `TASK_STATE_` enums, JCS signing rules, `A2A-Version` header | A2A releases | Breaking wire change. 0.3 clients break without a compat layer |
| 2026-05-21 | ID-JAG -04, OAuth WG draft | `AP/identity/dt_revdates.txt` line 7 | The MCP enterprise extension depends on it |
| 2026-05-28 | A2A v1.0.1 | GitHub releases API | Current A2A release |
| 2026-06-03, 2026-06-17 | WebKit opposes WebMCP. Mozilla neutral | `AP/web/positions_comments.txt` | WebMCP has no second engine |
| 2026-06-09 | Chrome WebMCP origin trial from Chrome 149, ends 2026-11-17 | `AP/web/cs_ot.json` | A trial, not a shipped feature |
| 2026-06-18 | MCP Enterprise-Managed Authorization, Stable, last commit | Status: `AP/identity/mcp/ext_README.md` line 14. Date: `AP/identity/mcp/ext_ema_commits.json`, newest commit 2026-06-18T08:44:30Z | MCP's route to enterprise identity-provider federation |
| 2026-06-22 | Identity chaining enters the RFC Editor queue at revision -15. Revisions -16 and -17 follow inside the queue. -17 is dated 2026-07-19 | Queue date: datatracker history page, saved as `scratchpad/factcheck_ap4/idchain_hist.html`, row "2026-06-22 15 (System) IESG state changed to RFC Ed Queue". -17 date: `AP/identity/dt_revdates.txt` line 8 | Cross-domain token exchange is close to an RFC |
| 2026-07-06 | CIMD -02. MCP still links -00 | `AP/identity/dt_revdates.txt` line 5 | Section numbers moved |
| 2026-07-28 | MCP 2026-07-28: stateless, sessions removed, tasks to an extension, DCR deprecated for CIMD | `AP/web/mcp_changelog.txt` lines 59 to 67 | Changes the state and registration rows of every comparison |
| 2026-07-30 | Transaction Tokens -11 | `AP/identity/dt_revdates.txt` line 10 | Adds the "equal or less" scope rule that RFC 8693 lacks |
| 2026-07-21 to 2026-09-17 | WebMCP adds `getTools`, `executeTool`, `consequentialHint`, events | `AP/web/webmcp_commits_summary.txt` | Spring 2026 tutorials do not match |
| 2026-08-21 | SPIRE v1.15.3. Release assets are `linux-amd64-musl`, `linux-arm64-musl` and `windows-amd64`. No macOS binary | `AP/identity/spiffe/rel_spire.json`, `assets` list | No macOS binary for a lab |
| 2026-09-15 | `draft-ietf-wimse-aims-00`, WG draft, Informational | `AP/identity/drafts/draft-ietf-wimse-aims-00.txt` line 7 | First IETF WG document on AI agent auth. Lists audit fields |
| 2026-09-17 | WebMCP CG draft revision | `AP/web/webmcp_spec.txt` line 5 | Cite this date with the spec |
| 2026-09-21 | `a2a-sdk` 1.1.5. Agno issue 10387: a 0.3-only server rejects 1.0 clients | PyPI, `AP/web/agno_10387.txt` | Version to pin. Version skew is live |
| Not dated | OTel v1.44.0 deprecates 60 `gen_ai.*` rows. 50 say "Moved to the OpenTelemetry GenAI semantic conventions repository". 2 say "Removed, no replacement". 8 say "Replaced by" another name. The new repo has no release | `AP/identity/otel/docs_registry_attributes_gen-ai.md` lines 18 to 67 for the 50, lines 288 to 292 and 330 to 334 for the 10 | Agent span names have no released home |
| After 2026-05-28 | A2A spec on `latest` adds section 7.6.4, not released | `AP/a2a/spec.txt` line 2867 | Label it "unreleased text" when quoting |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept gives one best piece of evidence first, with its conditions. Supporting evidence follows. Every quote in a "Best evidence" line was re-grepped in its saved file. Section 12 gives the counts.

### 4.1 A2A declares how a client authenticates. It carries no authorization, no delegation and no consent

An A2A request carries a credential in an HTTP header. The spec says how the client learns the scheme. It does not say how the client gets the credential, what it may do, or for whom.

- **Best evidence, verified.** A2A specification v1.0.1, section 7.3, step 2: the client obtains credentials "through an out-of-band process". Section 7.5: authorization "is implementation-specific". File `AP/a2a/spec_v101.txt`, lines 2744 and 2761. Status: project specification, Linux Foundation, v1.0.1, released 2026-05-28.
- **Verified by absence.** Case-insensitive counts in the v1.0.1 page text: "consent" 0, "audience" 0, "token exchange" 0, "8693" 0. The same counts are 0 in the Markdown source at tag v1.0.1, `AP/identity/a2a/specification_v1.0.1.md`, for "consent" and "audience".
- **Verified.** The card lists five scheme types: API key, HTTP auth, OAuth 2.0, OpenID Connect and mutual TLS. Section 4.5.1. OpenID Connect appears only as a scheme the server accepts. A2A report 2.7.
- **Verified in SDK source.** The `a2a-sdk` 1.1.5 client `AuthInterceptor` walks the card's schemes in order. It adds the first credential it can use as one header, then returns. It does not add a second credential. `SDK/client/auth/interceptor.py` lines 36 to 91: each branch ends in `return` after one header. Source: Phase 3 fact check, `reports/agent-protocols_p03_factcheck.md` line 24.
- **Verified, unreleased text.** The `latest` spec page adds section 7.6.4. It says the protocol "does not define the scope, representation, validity, or revocation semantics" of the credential. The sentence is about the credential a client gets in response to `TASK_STATE_AUTH_REQUIRED`, not every A2A credential. `AP/a2a/spec.txt` line 2867. The same sentence has 0 hits in the v1.0.1 page. Quote it as unreleased text on the main branch.
- **Answer to the README question.** The protocol can express which schemes a server accepts, the task and its states. It leaves to trust the key behind a card, what the credential allows, who the user is, and whether the user agreed.

### 4.2 A valid Agent Card signature proves who holds a key. It does not prove who owns the domain

The spec lets the verifier take the key from a URL inside the signed card. An attacker who controls that URL can sign any card.

- **Best evidence, verified by run.** `AP/a2a/lab/sign_check.out` lines 3 and 4. An attacker changes the interface URL, signs with their own ES256 key, and sets `jku` to their own key set. A verifier that fetches the key from `jku` prints `VERIFIED`. The same card with a key pinned out of band prints `REJECTED (InvalidSignaturesError)`. Conditions: `a2a-sdk` 1.1.5 signing helpers, fresh ES256 keys per run, run under 3 s.
- **Verified in the spec.** Section 8.4.3, step 2: "Retrieve the public key using the `kid` and `jku` (or from a trusted key store)". `AP/a2a/spec_v101.txt` line 3012. Nothing in section 8.4 binds the `jku` host to the card's host. Signing is optional: cards "MAY be digitally signed", line 2880.
- **Verified in SDK source.** Verification is opt-in. `signature_verifier` defaults to `None`, `SDK/client/card_resolver.py` line 150. If the header has no `alg`, the signer uses HS256, a shared-secret algorithm, `SDK/utils/signing.py` line 82. Run: `sign_check.out` line 6 prints `{'alg': 'HS256', 'kid': 'k1', 'typ': 'JWT'}`.
- **Verified by run.** The SDK's canonical form drops empty strings and empty lists. The spec's worked example, section 8.4.1, keeps the required fields `description: ""` and `skills: []` and drops only the non-required empty `extensions`. `AP/a2a/spec_v101.txt` lines 2894 to 2934. `AP/a2a/lab/canon_check.out` line 4: `equal: False`. Two SDKs can disagree on a signature. That cross-SDK failure is inferred, not run.
- **Verified in the spec.** Section 8.4.2 says the protected header MUST include `alg`, `typ` and `kid`. The value of `typ` SHOULD be "JOSE". `AP/a2a/spec_v101.txt` lines 2951 to 2955. The A2A research report, section 2.3, listed only `alg` and `kid`. That list is wrong. `reports/agent-protocols_p02_factcheck.md` line 13.
- **Verified by absence.** Section 8.4.2 lists no expiry or issue-time header. A card signed last year with a still-valid key verifies today. A2A report section 4.
- **Verified by run, Phase 2.** Three signing facts from `runs/agent-protocols_p02_card_sign.txt`. Conditions: `a2a-sdk` 1.1.5, PyJWT 2.14.0, line 1.
  1. A verifier that allows only ES256 rejects the HS256-signed card: `REJECTED (InvalidSignaturesError)`, line 8. The same card passes a verifier that allows HS256, line 9.
  2. The owner signature header has the keys `['alg', 'jku', 'kid', 'typ']`. Time fields `exp`, `iat` and `nbf`: `[]`, lines 10 and 11.
  3. The SDK card fetcher skips signature checks by default. `A2ACardResolver.get_agent_card(signature_verifier=...)` defaults to `None`, line 15.
- **History, one line.** `signatures` arrived in v0.3.0. RFC 8785 canonical form arrived in v1.0: "8785" has 0 hits in `AP/a2a/spec_v030.txt` and 5 lines in the v1.0.1 page, lines 2884 to 3015.

### 4.3 A discovery file is an unsigned claim by a domain, and only the A2A card path is a registered well-known name

A file at a well-known path says what a domain wants you to think. It does not prove an agent answers there.

- **Best evidence, verified.** The IANA Well-Known URIs registry lists `agent-card.json`, controller "Linux Foundation", `AP/web/iana_wellknown.xml` lines 25 and 26. The strings `ai-catalog` and `mcp` appear 0 times in the same file. Registry updated 2026-09-16, fetched 2026-09-23.
- **Verified, measured.** The web research agent probed 8 domains for 6 paths. It used `curl -sL --max-time 20` with a browser User-Agent. The run was around 15:40 UTC on 2026-09-23, from one network. `AP/web/probe/probe_results.txt`. No saved JSON file in `AP/web/probe/` contains `"signatures"`: 0 files, re-counted by the dossier author.
- **Verified.** The one Agent Card found, on modelcontextprotocol.io, has `"url":"https://modelcontextprotocol.io/"`, a documentation home page. `AP/web/probe/modelcontextprotocol.io__.well-known_agent-card.json` line 1.
- **Verified.** MCP Server Cards are "not an accepted or official MCP extension". `AP/web/extsc_readme.md` line 3. The README status still says "Experimental". The `$schema` URL both real server cards cite returned HTTP 404 on 2026-09-23. Web report 2.3.
- **Verified.** The Server Card repository is now `modelcontextprotocol/ext-server-card`. Its old name was `experimental-ext-server-card`. `AP/web/extsc_repo.json` field `full_name`. `AP/web/fetch_log.txt` line 36 shows the old name resolving to the same repository id.
- **Verified by run, Phase 2.** Two catalog entries point to another site, not one. github.com points to `api.githubcopilot.com`. huggingface.co points to `huggingface-hf-discover.hf.space`, which answered HTTP 404. `runs/agent-protocols_p02_crawl.txt` lines 32, 34 and 43: `cross-domain catalog entries: 2`. The web report counted one.
- **Verified, with a release label.** A2A v1.0.1 section 8.2 lists "Registries/Catalogs" and says only "curated catalogs of agents". It defines no registry API. `AP/a2a/spec_v101.txt` lines 2844 to 2850. The sentence "does not prescribe a standard API for curated registries" is from the Agent Discovery page on the unreleased `latest` docs. `AP/web/a2a_discovery.txt` line 147, fetched from `https://a2a-protocol.org/latest/topics/agent-discovery/`, `AP/web/fetch_log.txt` line 46. Quote it as unreleased text.
- **Verified.** The MCP Registry checks who owns a name. It "delegates security scanning" to package registries. Web report 4.5.
- **Link.** How a client uses `server/discover` after it connects is Module 6, 4.1.

### 4.4 A token for an agent that acts for a user must name two principals, or the receiver sees impersonation

The user is the subject. The agent is the actor. A token that names only the user cannot answer "which agent did this".

- **Best evidence, verified.** RFC 8693, section 1.1. With delegation, "principal A still has its own identity separate from B", line 204. With impersonation, "A is B within the context of the rights authorized by the token", line 196. `AP/identity/rfc8693.txt`. Status: RFC 8693, Standards Track, January 2020.
- **Verified, open disagreement between drafts.** The drafts do not agree where the agent goes.
  - AIMS -00 puts the agent in `client_id` and the user in `sub`: "The access token includes the Agent identity as the 'client_id' claim". `AP/identity/drafts/draft-ietf-wimse-aims-00.txt` lines 756 to 761, section 10.3. The string `"act"` has 0 hits in that file. AIMS still names RFC 8693 token exchange as a way to get a new credential, lines 457 and 912. Status: WIMSE WG draft -00, Informational, 2026-09-15.
  - Transaction Tokens for Agents uses `act` for the agent. The current text is `draft-araut-oauth-transaction-tokens-for-agents-02`, individual draft, Informational, 22 May 2026. Its abstract "defines the use of the act field to identify the agent performing the action". `scratchpad/agent-protocols_p04/araut.txt` lines 5 to 19. The older `draft-oauth-transaction-tokens-for-agents-06` of 2026-04-11 is "Replaced by draft-araut-oauth-transaction-tokens-for-agents". `scratchpad/agent-protocols_p04/ttfa_dt.txt`.
  - ID-JAG -04 allows an optional `act`. OAuth WG draft, 2026-05-21. Identity report 2.4.
- **Verified.** RFC 8693 section 4.4 defines `may_act`. A subject token can name the party "authorized to become the actor and act on behalf of another party". The STS can use it to refuse an exchange by any other agent. `AP/identity/rfc8693.txt` lines 805 to 813. It is the only RFC 8693 claim that limits which agent may act for a user.
- **Verified, the hop into another company.** Identity chaining -17 is the OAuth mechanism for crossing a trust domain. A token exchange inside your domain yields a JWT authorization grant. The other domain's authorization server trades it for an access token. "Chaining across multiple domains is achieved by using the same protocol every time a trust domain boundary is crossed." `AP/identity/drafts/draft-ietf-oauth-identity-chaining-17.txt`, Abstract, lines 24 to 32. OAuth WG draft, intended Proposed Standard. The MCP enterprise extension in 4.9 uses the same two steps with ID-JAG.
- **Verified.** Microsoft's "on-behalf-of" flow is not RFC 8693. It uses a JWT-bearer grant with `requested_token_use`. `AP/identity/cloud/entra_obo.txt` line 74. Vendor document. The name "on-behalf-of" does not mean RFC 8693.
- **Inferred, bridging.** IBM ContextForge can "register external AI agents and expose them as MCP tools", `AP/web/contextforge_a2a.txt` line 311. Its example stores one API key per agent. So the downstream A2A agent sees the gateway's key, not the user. Inferred from the docs example. Check: run ContextForge with a stub A2A agent and read the request headers.
- **Verified by run, Phase 2.** The ContextForge docs example carries an A2A 0.3 body: `"method": "message/send"` with `"role": "user"`. `AP/web/contextforge_a2a.txt` lines 384 to 389. The 0.3 model accepts it and the 1.0 model rejects it, `runs/agent-protocols_p02_version_skew.txt` line 8. A default `a2a-sdk` 1.1.5 server answers `-32601 Method not found`, with or without the header, lines 26 and 27.
- **Inferred for core MCP.** Core MCP authorization is an OAuth 2.1 flow where your agent is the client. The token's content is set by the authorization server. So core MCP can express "user via this client". It has no actor chain. Check: decode a token from a real MCP authorization server.

### 4.5 A workload identity names the software. It does not name the user or grant any rights

An SVID answers "which program holds this key". It does not answer "for which user" or "allowed to do what".

- **Best evidence, verified.** SPIFFE JWT-SVID standard, section 3: "The JWT-SVID specification does not introduce any new claims". `AP/identity/spiffe/JWT-SVID.md` line 69. Status: SPIFFE standard, CNCF project, read at `main` on 2026-09-23.
- **Verified by run.** `AP/identity/proto/svid_run.txt` line 10: `claims carried: ['aud', 'exp', 'iat', 'sub']`. Lines 8 and 9: a two-audience token was accepted at both `https://mail-tool.local` and `https://billing.local`. Conditions: `spiffe` 0.3.1, PyJWT 2.13.0, run time 0.12 s.
- **Verified.** JWT-SVID section 7.2 names the replay: "Chuck can impersonate Alice by sending the same token to Bob". Line 121.
- **Verified.** A SPIFFE ID path has no fixed meaning: "The meaning behind the path is left open-ended". `AP/identity/spiffe/SPIFFE-ID.md` line 76.
- **Verified in source.** SPIRE v1.15.3 default JWT-SVID lifetime is 5 minutes: `DefaultJWTSVIDTTL = time.Minute * 5`, `AP/identity/spiffe/builder_v1.15.3.go` line 38. X.509-SVID default is 1 hour.
- **Where it fits.** The workload identity can be the actor token in an RFC 8693 exchange. The user token stays the subject token. AIMS section 6 says an agent "MUST be assigned exactly one WIMSE identifier, which MAY be a SPIFFE ID". Identity report 2.3.

### 4.6 Token exchange does not narrow the scope by itself. The STS policy does

RFC 8693 lets an STS return a token with more rights than the one it received. A scope rule exists only in later drafts.

- **Best evidence, verified by run.** `AP/identity/proto/txchain_run.txt` lines 14 and 15. A toy STS that intersects scopes returns `mail.read`. The same STS without intersection returns `mail.read mail.send` from a `mail.read` subject token. Conditions: PyJWT 2.14.0, HS256 with one shared demo key, `AP/identity/proto/txchain.py` lines 12 and 20, all offline, 0.17 s wall. A real STS signs with an asymmetric key such as ES256 or RS256.
- **Verified in the RFC.** RFC 8693 section 2.1 calls `scope` "service specific", `AP/identity/rfc8693.txt` line 334. The word "subset" has 0 hits in the RFC. Section 2.1.1: the requested rights are "the Cartesian product of all the scopes at all the target services", line 399.
- **Verified, the rule in drafts.**
  - Transaction Tokens -11, section 13.6: the STS "MUST ensure that the requested scope of the Txn-Token is equal or less than the scope(s) associated with the original subject_token". Line 1252. OAuth WG draft -11, intended Standards Track, 2026-07-30.
  - Identity chaining -17: servers "need to verify that the requested scopes are not higher privileged than the scopes of the presented subject_token". Line 623. OAuth WG draft -17 of 2026-07-19. It has been in the RFC Editor queue since 2026-06-22, when it was at -15. `AP/identity/dt/draft-ietf-oauth-identity-chaining.json`: `iesg_state` "RFC Ed Queue". Queue date: `scratchpad/factcheck_ap4/idchain_hist.html`.
- **Verified.** RFC 9396 section 6.1: "there is no standardized mechanism to compare two arbitrary authorization detail requests". A narrowing check for rich authorization requests is per-type code. Identity report 2.4.

### 4.7 Only the current actor in an `act` chain counts for access control. Earlier actors are an audit record, as true as the STS that wrote it

A resource server MUST base its decision only on the top-level claims and the current actor, the outermost `act`. Earlier actors in the chain are for the record. The chain is as true as the STS that wrote it.

- **Best evidence, verified.** RFC 8693 section 4.1: the consumer "MUST only consider the token's top-level claims and the party identified as the current actor", lines 723 and 724. "Prior actors identified by any nested "act" claims are informational only and are not to be considered in access control decisions." `AP/identity/rfc8693.txt` line 725. The outermost `act` is the current actor. "The least recent actor is the most deeply nested", line 715.
- **Verified by run.** A token whose `act` names an agent that never ran still verifies. PyJWT 2.14.0 returns it as given: `decoded act: {'sub': 'spiffe://corp/agent/anything-i-say'}`. `AP/identity/proto/txchain_run.txt` line 11. PyJWT does not check `act`. Condition: the lab minted this token with the STS's own HS256 key, `txchain.py` lines 70 and 71. So the run shows that anyone who holds the signing key can write any chain. It does not show that an outsider can forge one.
- **Verified by run.** The chain rebuilds in order: `alice -> spiffe://corp/agent/planner -> spiffe://corp/agent/summarizer`. Same file, line 18.
- **Verified, a trap in a draft.** AAuth -10 keeps nested `act`, but each node uses an `agent` field, "not RFC 8693's sub". The presenter sits in a top-level `agent` claim. `AP/identity/drafts/draft-hardt-oauth-aauth-protocol-10.txt` line 3835. Individual draft, 2026-08-06. An RFC 8693 reader would take the wrong hop as current. That consequence is inferred. Check: decode the AAuth example tokens with the `chain()` function of lab L1.
- **Consequence.** A policy such as "deny if any earlier hop was sub-agent X" is a local extension, not the standard.

### 4.8 Revoking the user's token does not stop a token that was already exchanged from it, and no agent protocol defines revocation

After an exchange, the new token lives until it expires, unless the deployment adds a revocation channel.

- **Best evidence, verified.** RFC 8693 section 2.1: an exchange "does not create a tight linkage between the input and output tokens". Revocation propagation "is not a general property of the STS protocol". `AP/identity/rfc8693.txt` lines 380 and 386.
- **Verified, A2A.** The v1.0.1 page has one line with "revoc": "Agents SHOULD implement credential revocation mechanisms", section 13.4, `AP/a2a/spec_v101.txt` line 4274. It defines no mechanism. A separate line says "Expired or revoked keys MUST NOT be used for verification", line 3025, with no way to learn that a key is revoked.
- **Verified, MCP core.** Nine `.mdx` files are saved in `AP/identity/mcp/`. Two of them, `authorization.mdx` and `security_best_practices.mdx`, are 14-byte stubs that say "404: Not Found". Check: `wc -c` prints 14 for both. "revoc", case-insensitive, has 0 hits in the 7 files with content. They are the four `auth_*.mdx` files, `changelog.mdx`, `ext_enterprise-managed-authorization.mdx` and `ext_oauth-client-credentials.mdx`. Check: `grep -ic revoc` prints 0 for each.
- **Verified, MCP Security Best Practices page.** A good copy of the 2026-07-28 page is in the Module 6 research folder. `scratchpad/research_tools-mcp/mcp/md/secbp.md`, canonical URL `https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices`. "revoc" has 2 hits, lines 889 and 895. Both are in "Scope Minimization". They name revocation as a cost of broad scopes: "Higher friction on revocation". The page defines no revocation mechanism.
- **Verified, WebMCP.** WebMCP has no token to revoke, 4.12.
- **Verified, the standard that exists.** OpenID CAEP 1.0 Final defines `session-revoked`, `token-claims-change` and `credential-change` events. `AP/identity/oidf/openid-caep-1_0-final.txt`. OpenID Foundation Final specification, 29 August 2025. AIMS -00 section 11 says cached tokens "MUST NOT continue to be used after a revocation or risk notification", line 1139.
- **Short lifetimes are the other tool.** Txn-Tokens are "on the order of minutes or less". SPIRE JWT-SVIDs default to 5 minutes. AWS web-identity sessions default to 1 hour, minimum 15 minutes. Identity report 2.5.

### 4.9 Only MCP adopted OIDC-style federation, and only in an extension. A2A and WebMCP have none

The brief asks whether any protocol adopted OIDC-style federation. The answer: MCP did, in a Stable extension, not in its core. A2A and WebMCP did not.

- **Best evidence, verified.** MCP extension "Enterprise-Managed Authorization", status "Stable". The client exchanges an enterprise ID token for an ID-JAG with RFC 8693, then presents it as an RFC 7523 JWT grant. `audience` "MUST be the issuer identifier of the Resource Authorization Server". `AP/identity/mcp/ext_enterprise-managed-authorization.mdx` lines 5, 40, 48 and 129. It depends on ID-JAG -04, an OAuth WG draft.
- **Verified by absence, MCP core.** "8693" has 0 hits in each of the four saved MCP 2026-07-28 authorization pages. "token exchange" has 0 hits in `auth_index.mdx`.
- **Verified, MCP core registration.** MCP 2026-07-28 deprecates Dynamic Client Registration, RFC 7591, "in favor of Client ID Metadata Documents". `AP/identity/mcp/changelog.mdx` lines 96 to 99. CIMD proves control of a URL, not trust. MCP says CIMD "cannot prevent `localhost` URL impersonation". Identity report 2.4.
- **Verified by absence, A2A.** 0 hits for "token exchange" and "8693" in the v1.0.1 page, 4.1.
- **Verified by absence, WebMCP.** "OAuth" has 0 hits in the WebMCP spec text, `AP/web/webmcp_spec.txt`.
- **Not checked.** Open MCP proposals, called SEPs, on token exchange in the core. Check: search the `modelcontextprotocol` pull requests for "8693" and "actor".

### 4.10 No agent-specific authorization standard exists. The only WG document is an Informational -00 draft that defines no new protocol

The parts that are standards are general OAuth RFCs. Everything that names agents is a draft.

- **Best evidence, verified.** `draft-ietf-wimse-aims-00`, "AI Identity Management System". Header: "Intended status: Informational", line 7. Abstract: "Rather than defining new protocols, this document describes how existing and widely deployed standards can be applied", lines 28 to 29. Published 2026-09-15 by the WIMSE working group. Authors from Defakto, AWS, Zscaler, Ping Identity, OpenAI and Okta.
- **Verified.** The datatracker API returned 551 Internet-Drafts with "agent" in the name changed on or after 2026-01-01. Only 3 carry a working-group name, and none of the 3 is about AI agents. `AP/identity/dt_agent_count.txt` lines 1 to 5. The count includes non-AI uses of "agent". AIMS is not counted because its name does not contain "agent".
- **Verified.** The closest document to an RFC is identity chaining -17, in the RFC Editor queue on 2026-09-23, intended Proposed Standard. `AP/identity/dt_revdates.txt` line 8. It entered the queue on 2026-06-22 at revision -15. `scratchpad/factcheck_ap4/idchain_hist.html`, row "IESG state changed to RFC Ed Queue". It is about cross-domain token exchange, not agents.
- **Status table of the documents the course will cite.** Revision dates come from the datatracker `rev_history`, not from its `time` field. Section 7, conflict c.

| Document | Status | Revision, date |
|---|---|---|
| RFC 8693 Token Exchange | RFC, Standards Track | January 2020 |
| RFC 9396 Rich Authorization Requests | RFC, Standards Track | May 2023 |
| RFC 9700 OAuth Security BCP | RFC, BCP 240 | January 2025 |
| Identity chaining | OAuth WG draft, intended Proposed Standard, in the RFC Editor queue since 2026-06-22, entered at -15 | -17, 2026-07-19 |
| Transaction Tokens | OAuth WG draft, intended Standards Track | -11, 2026-07-30 |
| ID-JAG | OAuth WG draft, intended Standards Track | -04, 2026-05-21 |
| CIMD | OAuth WG draft, intended Standards Track. MCP links -00 | -02, 2026-07-06 |
| AIMS | WIMSE WG draft, Informational | -00, 2026-09-15 |
| `draft-klrc-aiagent-auth` | WIMSE WG draft under its original name, then replaced by AIMS -00 on 2026-09-15. Datatracker: stream IETF, WG state "Adopted by a WG", state Replaced, intended status none given. The page says "Last updated 2026-09-09 (Latest revision 2026-07-06)". 2026-09-09 is the date of the "Replaced" change | -03, 2026-07-06, the latest revision |
| Transaction Tokens for Agents, `draft-araut-oauth-transaction-tokens-for-agents` | Individual draft, Informational. It replaced `draft-oauth-transaction-tokens-for-agents-06` | -02, 2026-05-22 |
| On-Behalf-Of User Authorization for AI Agents | Individual draft, Informational, expired 2026-02-27 | -02, 2025-08-26 |
| AAuth | Individual draft, header says intended Standards Track | -10, 2026-08-06 |
| OpenID SSF 1.0, CAEP 1.0 | OpenID Foundation Final | 29 August 2025 |
| A2A | Project specification, Linux Foundation | v1.0.1, 2026-05-28 |
| MCP | Project specification, MCP project | 2026-07-28 |
| MCP Enterprise-Managed Authorization | Project extension, Stable | last commit 2026-06-18 |
| WebMCP | W3C CG draft | 17 September 2026 |

### 4.11 A click on Approve in the agent's UI is not an authorization grant, and no protocol records the user's consent

The only WG text on the topic says a local confirmation must be bound to a grant from the authorization server. A2A moves the auth request out of band. No protocol stores where consent was given.

- **Best evidence, verified.** AIMS -00 section 10.7: user confirmations "do not by themselves constitute authorization and MUST be bound to a verifiable authorization grant issued by the authorization server". And the agent "MUST NOT treat local UI confirmation alone as sufficient authorization". `AP/identity/drafts/draft-ietf-wimse-aims-00.txt` lines 972 and 983. WG draft -00, Informational. It can change.
- **Verified.** The same section says OpenID CIBA "doesn't map well to cases that envision the need for User confirmation to occur mid-execution". Line 989. CIBA is Client-Initiated Backchannel Authentication: the agent starts a request and the user approves on another device.
- **Verified, A2A.** `TASK_STATE_AUTH_REQUIRED` lets an agent pass an authorization need up to its client. A client that is an agent may pass it further, "forming a chain of Tasks". `AP/a2a/spec_v101.txt` line 2813. Credentials then arrive out of band. If a deployment passes credentials in-band, section 7.6.3 warns this risks "exposing those credentials to each agent" in the chain, line 2827.
- **Consequence for the module question.** Consent is recorded only where a deployment chooses to record it. That is the authorization server that issued the grant, and your own logs. Module 9, 4.7, owns the durable wait for an approval. This module owns what the approval must bind to.

### 4.12 WebMCP is a Community Group draft, and a WebMCP tool runs with the user's session and no agent identity

WebMCP is a browser API proposal from Google and Microsoft editors. It is not a standard. A tool call carries no token and no agent id.

- **Best evidence, verified.** WebMCP spec, "Draft Community Group Report, 17 September 2026". Status section: "It is not a W3C Standard nor is it on the W3C Standards Track." `AP/web/webmcp_spec.txt` lines 4, 5 and 24. Editors from Microsoft and Google.
- **Verified.** Section 6.2: "When an agent visits a website, it carries the user's logged-in credentials and session state." Line 862. Section 6.3.2: "There is no guarantee that a WebMCP tool's declared intent matches its actual behavior." Line 981.
- **Verified.** The spec "does not prescribe the format in which tools are exposed to the browser agent". Line 837. Browsers may use MCP or another format.
- **Verified.** The only access control is a permissions-policy feature `tools`, default `'self'`. A site can turn it off with `Permissions-Policy: tools=()`, line 1078.
- **Verified, engine positions.** WebKit issue 670 has the label `position: oppose`, `AP/web/webkit_pos.json` line 38. Mozilla issue 1412 has `position: neutral`, `AP/web/moz_pos.json` line 49. Chrome runs an origin trial, milestones 149 to 156, ends 2026-11-17, status `ACTIVE`, `AP/web/cs_ot.json`.
- **Inferred.** Nothing in `registerTool()`, `getTools()` or `executeTool()` carries a token, a scope or an agent id. The web agent read the full IDL in section 4 and found none. Check: grep the IDL index for any identity member.
- **Verified, churn.** The 2025-12-04 proposal used `navigator.modelContext.provideContext`. The current draft uses `document.modelContext` and has no `provideContext`. Web report 2.1.

### 4.13 The three protocols keep state in three places, and an A2A task id lasts only as long as the remote agent's store

A caller must know who holds the state to know what it can ask for later.

- **Verified in the spec. A2A does not always make a task.** Section 3.1.1, "Send Message": clients "receive either a task that tracks the processing or a direct response message". `AP/a2a/spec_v101.txt` line 666. Inferred from that text: with a direct `Message`, the client has no task id to pass to `GetTask`. Check: run an agent that returns a `Message` and read the response.

- **Best evidence, verified by run.** `AP/a2a/lab/db_trace.out` lines 1 to 4. With the SDK's SQLite `DatabaseTaskStore`, the server was killed with SIGKILL during `TASK_STATE_WORKING`. After restart, `GetTask` returned `TASK_STATE_WORKING` with timestamp `2026-09-23T15:40:12.614287Z`. 12 s later it returned the same state and timestamp. The record survived. The work did not. The agent in this run sleeps 10 s per chunk.
- **Verified by run.** With the default `InMemoryTaskStore`, `GetTask` after a restart returned `{"code":-32001,"message":"Task not found"}`. `AP/a2a/lab/trace.out` line 75. The spec allows this: a task "might be invalid, expired, or already completed and purged", `AP/a2a/spec_v101.txt` line 1204.
- **Verified by absence.** A2A `Task` and `TaskStatus` have no lease, heartbeat or timeout field. A client that polls for a terminal state can poll forever. A2A report section 4.
- **Verified, MCP.** MCP 2026-07-28 removed "protocol-level sessions and the Mcp-Session-Id header". Servers keep cross-call state in "explicit, server-minted handles passed as ordinary tool arguments". `AP/web/mcp_changelog.txt` line 59. Tasks moved to the extension `io.modelcontextprotocol/tasks`, `AP/a2a/mcp_changelog.txt` line 137. The extension says "A task ID is a durable handle", `AP/a2a/mcp_tasks.txt` line 126.
- **Verified, WebMCP.** The browser keeps a "pending tool executions map" per top-level page. It drops pending executions when the document unloads. `AP/web/webmcp_spec.txt` line 101 for the map, lines 194 to 203 for the unloading document cleanup steps.
- **Scope line.** Module 8 teaches the A2A task handle, its states and how to follow it. Module 9 teaches how the agent behind the handle survives a crash.

### 4.14 If the call, the stream or the webhook is lost, only `GetTask` tells you how an A2A task ended. The default call blocks, and a webhook gets one attempt in SDK 1.1.5

A2A has three update paths. The spec makes none of them reliable on its own. A blocking `SendMessage` that completes does return the final state. The spec says so, and the lab shows it below. `GetTask` is the only path that still works after a lost connection or a failed webhook, while the remote agent keeps the task, 4.13.

- **Best evidence, verified by run.** `AP/a2a/lab/push_trace_503.out` line 2: `webhook status returned: 503; deliveries received: 5`. The task had 5 events. `push_trace_503.err` has 5 lines "Error sending push-notification". The SDK made no retry.
- **Verified in the spec.** Section 4.3.3: agents "MUST attempt delivery at least once" and "MAY stop attempting delivery after a configured number of consecutive failures". `AP/a2a/spec_v101.txt` lines 1629 and 1632. Section 4.3.3 also says agents "MAY implement retry logic", line 1630. Section 13.2 says agents "SHOULD implement retry logic", line 4178. The two sections disagree. SDK 1.1.5 does neither.
- **Verified in the spec.** Section 3.7: streamed messages "MUST NOT be considered a reliable delivery mechanism for critical information". `AP/a2a/spec_v101.txt` line 1439.
- **Verified in the spec and by run.** `SendMessage` blocks by default. If `returnImmediately` is unset, the call "MUST wait until the task reaches a terminal" or interrupted state, line 1069. Run: the default call returned `TASK_STATE_COMPLETED` in 0.61 s, `trace.out` line 7. With `returnImmediately: true` it returned `TASK_STATE_SUBMITTED` in 0.01 s, line 13.
- **Verified in SDK source and by run.** The spec says push MUST carry credentials from the config's `authentication` field, section 4.3.3, line 1616, and section 13.2, line 4176. The lab set `authentication` to `{scheme: Bearer, credentials: secret-abc}`, `AP/a2a/lab/push_trace.py` line 24. The SDK sends only `X-A2A-Notification-Token`, `SDK/server/tasks/base_push_notification_sender.py` line 102. Run: "Authorization header present in any delivery: False", `push_trace_200.out` line 8. The SDK screens push URLs only if the caller passes a validator: "Defaults to None (no library screening)", lines 49 to 50.
- **Verified by run.** Duplicate `messageId`: the spec says agents "may utilize the messageId to detect duplicate messages", line 1137. The SDK ran the agent twice: `### 10 result: same task? False`, `trace.out` line 67. A retry can run the job twice.
- **Inferred.** A long task behind a default `SendMessage` holds an HTTP request open. A proxy idle timeout will cut it. Check: a 60 s agent behind a proxy with a 30 s timeout.

### 4.15 A missing `A2A-Version` header means version 0.3. Whether that fails loudly depends on the server

The spec turns an empty header into 0.3. A 1.0-only server then rejects the call loudly. A server with 0.3 support answers a 0.3-shaped request with 0.3 rules and no error.

- **Best evidence, verified.** Spec v1.0.1, section 3.6.2: "Agents MUST interpret empty value as 0.3 version." `AP/a2a/spec_v101.txt` line 1414. Clients MUST send the header with each request, "except for 0.3 Clients", section 3.6.1, line 1387.
- **Verified by run.** With no header, the default `a2a-sdk` 1.1.5 server on the JSON-RPC binding returned `-32009`, "A2A version '0.3' is not supported by this handler. Expected version '1.0'.", with HTTP 200. `AP/a2a/lab/trace.out` line 53. The reason: `enable_v0_3_compat: bool = False` is the default, `SDK/server/routes/jsonrpc_routes.py` line 32.
- **Verified by run, Phase 2.** `runs/agent-protocols_p02_version_skew.txt`, `a2a-sdk` 1.1.5, JSON-RPC binding. Every row is HTTP 200. The error is in the JSON-RPC body.
  - Default server, `enable_v0_3_compat=False`. A 1.0 body with no header gets `-32009`, line 23. A 0.3 body gets `-32601 Method not found`, lines 24 and 25.
  - Server with `enable_v0_3_compat=True`. A 0.3 body with no header is answered as 0.3, with task state `completed`, line 34. A 0.3 body with header 1.0 gets `-32603`, line 33. A 1.0 body with no header still gets `-32009`, line 32.
  - So the earlier guess was wrong. Compat on does not serve the 1.0 request without a header. It serves only a 0.3-shaped request.
- **Verified in the spec, not run.** Section 5.4 maps `-32009`, `VersionNotSupportedError`, to HTTP 400 in the HTTP+JSON binding. `AP/a2a/spec_v101.txt` line 2034. The lab did not run that binding.
- **Verified, real incident.** Agno issue 10387, opened 2026-09-21: the Agno A2A interface "rejects A2A Protocol v1.0 clients with HTTP 400". `AP/web/agno_10387.txt` line 138.
- **Verified.** Version choice is a client pick, not a handshake. The client reads `protocolVersion` per interface in the card. Section 3.6.3, line 1420: clients that need the latest features "should" request a version and "avoid automatic fallback to older versions". The "should" is lower case, so it is advice, not a normative SHOULD.

### 4.16 What you can prove afterwards is what each hop logged with a shared key. No released convention has a field for the delegation chain

The token chain proves what the STS issued. The logs prove what each service did. Only a shared transaction id joins them.

- **Best evidence, verified.** AIMS -00 section 11: "At a minimum, audit events MUST record" seven fields. They are the agent id, the delegated subject, and the resource or tool. They also include the action and decision, a timestamp with a correlation id, the risk state, and revocation events. Records "MUST be tamper-evident". `AP/identity/drafts/draft-ietf-wimse-aims-00.txt` lines 1144 and 1147. WG draft -00, Informational. It is the only standards-track text the identity agent found with an agent audit field list.
- **Verified.** Transaction Tokens -11 section 15.2: "Complete Txn-Tokens MUST NOT be logged verbatim." Line 1441. Log a hash or the payload without the signature.
- **Verified.** OpenTelemetry semantic conventions v1.44.0 mark `gen_ai.agent.id` and `gen_ai.agent.name` deprecated: "Moved to the OpenTelemetry GenAI semantic conventions repository". `AP/identity/otel/docs_registry_attributes_gen-ai.md` lines 18 to 20. Not every deprecated `gen_ai.*` row moved. The file has 60 deprecated rows. 50 say "Moved to" the GenAI repository, lines 18 to 67. The other 10 say "Removed, no replacement" or "Replaced by" another name, lines 288 to 292 and 330 to 334. Check: `grep -c 'badge/-deprecated-red'` prints 60 and `grep -c 'Moved to the'` prints 50. `enduser.scope` is "Deprecated, no replacement at this time", `docs_registry_attributes_enduser.md` line 39.
- **Verified.** At commit `8ffdf568`, `AP/identity/otel/genai_head.txt`, the three saved GenAI repository files `genai_main_*.md` have 0 hits for "enduser", "user.id", "authoriz", "principal" and "actor". "delegat" has 1 hit, in prose about sub-agents, not an attribute. Re-grepped by the reviewer on 2026-09-23. Only three files were saved, so an attribute in another file of the repository is not checked. "No release": identity report 2.6, not re-checked.
- **Verified.** RFC 8693 calls nested `act` claims "a history trail", line 716. That trail sits inside the last token only.
- **Inferred.** A complete record today combines OTel `gen_ai.*` names, `user.id` or `enduser.id`, and custom fields for the actor chain and the decision. Check: watch the GenAI repository for a first release with an actor attribute.

---

## 5. Mechanism comparison: MCP, A2A and WebMCP

Every cell is verified unless it says otherwise. Sources are the three reports, Module 6 and the anchors in section 12.

| | MCP 2026-07-28 | A2A v1.0.1 | WebMCP CG draft 2026-09-17 |
|---|---|---|---|
| Status | Project specification, MCP project | Project specification, Linux Foundation, TSC with eight company seats | W3C CG draft, not Standards Track. WebKit opposes, Mozilla neutral |
| Purpose | Agent host to tool server | Agent to agent, a whole job | Web page to an in-browser agent |
| Who holds state | The server, in server-minted handles passed as tool arguments. No protocol session. Optional tasks extension holds tasks | The remote agent holds a `Task` with `id` and `contextId`, in a store it picks. It may instead answer with a direct `Message` and keep no task, spec 3.1.1 | The page's JavaScript. The browser tracks pending calls and drops them on unload |
| Transport | JSON-RPC over stdio or Streamable HTTP. Module 6, 4.1 | JSON-RPC, gRPC or HTTP+JSON, one per interface in the card | In-process JavaScript calls. The format to the browser agent is not defined |
| Auth model | Optional. A protected server is an OAuth 2.1 resource server with RFC 9728 metadata. Clients register by CIMD. Module 6, 5.3 | The card declares `securitySchemes`. The credential comes out of band. Authorization is implementation-specific | None. The user's cookies and session. Permissions policy `tools`, default `'self'` |
| Who the caller is, in the message | A bearer token in the HTTP header. The actor chain only with the enterprise extension | Whatever the credential says. No user, actor or audience field | Nothing. The page sees an origin, not an agent |
| Delegation and consent | Enterprise-Managed Authorization extension: RFC 8693 plus ID-JAG. Consent is the authorization server's | `AUTH_REQUIRED` passes the need up a chain. Consent is out of band | None. `consequentialHint` is a site-set hint for a confirmation prompt |
| Revocation | Not defined. "revoc" has 0 hits in the 7 saved MCP auth files with content. Two more saved files are 404 stubs. The Security Best Practices page names revocation only as a cost of broad scopes. 4.8 | "SHOULD implement credential revocation mechanisms". None defined | Nothing to revoke |
| Discovery | `server/discover` after connect. Server Cards experimental, repository `ext-server-card`. Registry in preview | `/.well-known/agent-card.json`, IANA permanent. Optional JWS signatures | Only after the page loads and runs script. Service-worker discovery is "TBD" |
| Streaming | A response stream per request. `subscriptions/listen` for change notices. SSE resumability removed | `SendStreamingMessage` over SSE. Push to webhooks, one attempt in SDK 1.1.5 | None. Open question, issue 82 |
| Version negotiation | Version in `_meta` on each request. `server/discover` lists versions. Error on mismatch. Module 6, 4.1 | `A2A-Version` header. Empty means 0.3. The client picks from the card | None. It is a browser API |

The A2A spec, Appendix B, states the split in one line: an A2A server "might use MCP" to do the work behind an A2A task. A2A report C6.

---

## 6. Lab inventory

### Built and run on 2026-09-23

| Lab | Script | Saved output | Run time | Download | Proves |
|---|---|---|---|---|---|
| A2A raw trace: card, blocking and non-blocking `SendMessage`, SSE, `GetTask`, errors, duplicate `messageId`, restart | `AP/a2a/lab/server.py`, `trace.py` | `trace.out`, `trace.err` | Under 10 s | `a2a-sdk[http-server,signing,sqlite]==1.1.5`, `uvicorn`, `cryptography` | 4.13, 4.14, 4.15 |
| A2A restart with SQLite store, SIGKILL during work | `AP/a2a/lab/db_server.py`, `db_trace.py` | `db_trace.out`, `db_trace.err`, `tasks.db` | About 20 s | as above | 4.13 |
| A2A push, webhook 200 and 503 | `AP/a2a/lab/push_server.py`, `push_trace.py` | `push_trace_200.out`, `push_trace_503.out`, `.err` files | Not recorded | as above | 4.14 |
| Signed card: owner, tamper, `jku` spoof, pinned key, unsigned, default `alg` | `AP/a2a/lab/sign_check.py` | `sign_check.out` | Under 3 s | as above | 4.2 |
| Canonical form, SDK against spec example | `AP/a2a/lab/canon_check.py` | `canon_check.out` | Not recorded | as above | 4.2 |
| Card HTTP headers | not saved as a separate script | `AP/a2a/lab/card_headers.out` | Not recorded | as above | A2A report 2.2, no `Cache-Control` or `ETag` |
| L1 token-exchange simulator: audience per hop, forged `act`, down-scoping, chain rebuild | `AP/identity/proto/txchain.py` | `txchain_run.txt`, prints `SELF-TEST OK` | 0.17 s wall | `pyjwt==2.14.0` | 4.6, 4.7 |
| L4 what a JWT-SVID proves | `AP/identity/proto/svid_check.py` | `svid_run.txt` | 0.12 s wall | `spiffe==0.3.1`, first run downloaded grpcio, about 11.8 MiB | 4.5 |
| Discovery probe, 8 domains, 6 paths | curl commands in the web report 2.3 | `AP/web/probe/`, 56 files, 3.9 MB, `probe_results.txt` | Not recorded | none | 4.3 |
| Server-card schema check | `AP/web/probe/validate_cards.py` | `validate_cards.out` | Not recorded | `jsonschema==4.26.0` | 4.3 |

**Self-tests that exist.** `txchain.py` asserts chain order, the intersected scope and the widened scope, then prints `SELF-TEST OK`. The A2A labs have no saved assert step. The A2A report proposes asserts in its Lab 1 to Lab 3. **Pin warning, verified:** `spiffe==0.3.1` needs `pyjwt<2.14`. Use separate environments for L1 and L4, `AP/identity/proto/svid_run.txt` line 1.

### Designed, not built

| Lab | Source | What it would print | Proves |
|---|---|---|---|
| L2 down-scoping check for `scope` and `authorization_details` | Identity report 5 | A table of 8 to 10 pairs with expected and actual verdicts. A naive dict-subset check calls a request without `folders` narrower | 4.6. The trap case is inferred from RFC 9396 section 6.1 |
| L3 audit-trail rebuild | Identity report 5 | One line per transaction: user, agent chain, tool, action, decision. Break-its: log only `sub`, log the raw token, drop the transaction id | 4.16 |
| Lab A: one task, three protocols | Web report 5 | A table of operation, arguments, state holder, identity and version per protocol. 0.3 against 1.0 validator errors | Section 5, 4.15 |
| Lab B: discovery crawler over the saved probe files | Web report 5 | Per domain: mechanisms found, versions, signatures, cross-domain entries. Phase 2 built it and measured 2 cross-domain entries, `runs/agent-protocols_p02_crawl.txt` line 43. Break-its: 401 read as "exists", 0.3-only field reader | 4.3 |
| L1 additions: `may_act` check, revoke-then-use | Identity report 5 | The exchanged token still verifies after the subject token is revoked | 4.8 |
| A2A Lab 2 addition: reconciler | A2A report 5 | `GetTask` after 2 s reports `TASK_STATE_COMPLETED` when every webhook failed | 4.14 |

### The module lab, proposed

The audit asks for three things. Two local agents. A signed card broken by a key swap. A token passed down a delegation chain with an audience check at each hop. All parts exist in pieces. None is joined. Proposal, not built:

1. Start two A2A agents from `server.py`. Agent B serves a signed card. Agent A verifies it with a pinned key, then with `jku`, as in `sign_check.py`.
2. A toy STS from `txchain.py` mints a user token for `alice`. Agent A exchanges it with its own actor token for audience agent B. Agent B exchanges again for an MCP-style tool audience.
3. Each hop writes one L3 log line with a shared transaction id and a token hash.
4. The self-test rebuilds `alice -> A -> B -> tool` from the logs and compares it with the `act` chain in the last token.
5. Break-its: STS without scope intersection, a forged `act`, `verify_aud=False`, revoke the subject token then call again.

It answers all three parts of the module question with numbers the learner produces. Run time is not measured. Inferred: under 30 s, no new download beyond the two pinned environments.

---

## 7. Conflicts resolved

| Conflict | Reports | Evidence used | Resolution |
|---|---|---|---|
| a. Where A2A mentions revocation | A2A report: the one "revoc" hit is section 8.4.3, "Expired or revoked keys". Identity report: A2A says agents "SHOULD implement credential revocation mechanisms" | Dossier author grep of `AP/a2a/spec_v101.txt`. "revoc" case-insensitive: 1 line, 4274, section 13.4, the SHOULD line. "revoked" is a separate word on line 3025, section 8.4.3 | Both sentences exist. The A2A report attached the "revoc" hit to the wrong line. The spec has a SHOULD in 13.4 and a key rule in 8.4.3, and no mechanism in either. 4.8 |
| b. What happens with no `A2A-Version` header | Web report 4.4: a 1.0 client "gets 0.3 semantics with no error". A2A report: SDK 1.1.5 returns `-32009` | Spec line 1414. `trace.out` line 53. `SDK/server/routes/jsonrpc_routes.py` line 32 | The spec maps empty to 0.3. The outcome depends on the server. A 1.0-only server, the SDK default, fails loudly with `-32009` and HTTP 200. A server with 0.3 support answers a 0.3-shaped request with no header quietly with 0.3 rules. Phase 2 measured this, `runs/agent-protocols_p02_version_skew.txt` line 34. A 1.0 request with no header still gets `-32009` with compat on, line 32. 4.15 |
| c. Date and status of the agent-auth WG draft | Web report: `draft-klrc-aiagent-auth` rev 03, 2026-09-09, "in the WIMSE working group". Identity report: -03 published 2026-07-06, replaced by `draft-ietf-wimse-aims-00` of 2026-09-15 | `AP/identity/dt/draft-klrc-aiagent-auth.json`: `rev_history` gives -03 at 2026-07-06T19:39. The `time` field 2026-09-09 16:57 is a state change to "Replaced". The same file has group `wimse` and stream IETF. `draft-klrc-aiagent-auth.html`: WG state "Adopted by a WG". `AP/identity/dt/draft-ietf-wimse-aims.json`: -00 at 2026-09-15 | Date: the web report used the `time` field. Cite `draft-ietf-wimse-aims-00`, 2026-09-15. Cite klrc -03 as 2026-07-06, replaced. Status, corrected by the reviewer: the web report was right that klrc sat in the WIMSE WG. It was adopted, not an individual draft, when it was replaced |
| d. AIMS intended status | Identity report: Informational. Datatracker `intended_std_level`: None | Draft header line 7: "Intended status: Informational" | Use the header. The datatracker field is not set for -00 |
| e. Does MCP hold task state | Web report 1.5: MCP has no protocol session, only handles. A2A report C6: MCP has server-held tasks | MCP changelog line 59 and item 6. `mcp_tasks.txt` line 126 | Both are true. The core is stateless. The official tasks extension adds server-held tasks. Section 5 states both |
| f. x402 version | Web report: `pypi-x402@v2.7.0`, 2026-04-13, repo `coinbase/x402`. Audit: `x402` 2.24.0, 2026-09-22, repo `x402-foundation/x402` | Dossier author fetched `https://pypi.org/pypi/x402/json` today, HTTP 200: version 2.24.0, uploaded 2026-09-22T18:28:24, Homepage `github.com/x402-foundation/x402`. `D8/pypi_x402.json`. The web agent's GitHub API call hit a rate limit, `AP/web/ghr_coinbase_x402.rel.json` | Use 2.24.0 and `x402-foundation/x402`. The web value came from the first rows of an Atom feed. Module 22 owns it |
| g. Did v1.0 introduce signed cards | LF release and v1.0 blog: v1.0 feature. CHANGELOG: v0.3.0 | CHANGELOG 0.3.0 "Add `signatures`". "8785" has 0 hits in `spec_v030.txt` | v0.3.0 added the field. v1.0 added canonical form and verification steps. 4.2 |
| h. Which A2A page to quote | Web report cites `latest`. A2A report says quote v1.0.1 | Anchors of 4.15 found in `spec_v101.txt`. 7.6.4 found only in `spec.txt`. The curated-registry sentence found only in the `latest` Agent Discovery page, `AP/web/a2a_discovery.txt` line 147 | Quote v1.0.1. Label `latest` text as unreleased. Two claims used here come from `latest`: section 7.6.4, 4.1, and the curated-registry sentence, 4.3 |
| i. Where the agent goes in a token | AIMS: `client_id`. Transaction Tokens for Agents and the expired WSO2 draft: `act`. ID-JAG: optional `act` | Each draft file, identity report 8.1 | Not a conflict between reports. It is an open disagreement between drafts. Teach both. 4.4 |
| j. Does `SendMessage` return immediately | Spec 3.3.3 wording against 3.2.2 | Spec line 1069, run `trace.out` line 7, CHANGELOG #1403 | 3.2.2 wins. Default blocks |
| k. Push retries | Spec 4.3.3 "MAY" against 13.2 "SHOULD" | `spec_v101.txt` line 1630, 4.3.3 "MAY implement retry logic". Line 4178, 13.2 "SHOULD implement retry logic". `push_trace_503.out` line 2 | Not settled by the spec. SDK 1.1.5 does neither. Teach "one attempt, then reconcile" |

---

## 8. Gap list, ranked by how much the module question needs it

| Rank | Gap | Why the module question needs it | What was done |
|---|---|---|---|
| 1 | The joined module lab: user, agent A, A2A agent B and an MCP-style tool with token exchange and a log join | The question asks what you can prove afterwards. Every piece exists alone | Not built. Design in section 6 |
| 2 | Revoke-then-use: an exchanged token still verifies after the subject token is revoked | 4.8 rests on RFC text only | Not built. L1 addition |
| 3 | Which real identity providers issue nested `act` chains with RFC 8693: Keycloak, Okta, Auth0, Entra | "Who is the agent acting as" depends on what a real token carries | Not checked |
| 4 | A real token from an MCP authorization server, and whether any client implements Enterprise-Managed Authorization | 4.4 and 4.9 for the MCP hop are partly inferred | Not checked |
| 5 | The A2A `experimental-ext-oid4vp-auth` repository | It may be the first A2A identity extension. It would change 4.1 and 4.9 | Only the repo name was seen. Not read |
| 6 | A2A deployments that accept user-delegated tokens, not only service keys | The A2A hop's "acting as" row rests on the spec and one gateway doc | Not checked |
| 7 | ContextForge mapping of `AUTH_REQUIRED` and `INPUT_REQUIRED` into an MCP tool result | 4.4 bridging claim is inferred | Not run |
| 8 | Cross-SDK card signature, JS 1.2.0 against Python 1.1.5 | 4.2 canonical-form mismatch is shown on one SDK | Not run |
| 9 | A2A `SendMessage` behind a proxy idle timeout | 4.14 consequence is inferred | Not run |
| 10 | 0.3 compat on: no header served quietly as 0.3 | 4.15 quiet case | Closed by Phase 2. Only a 0.3-shaped request is served, `runs/agent-protocols_p02_version_skew.txt` lines 32 to 34 |
| 11 | OTel GenAI release with actor or delegation attributes | 4.16 audit record has no released convention | Watch item |
| 12 | Edge, ChatGPT Desktop and Brave WebMCP support | 4.12 lists only Chrome as verified | Not checked. Needs a browser |
| 13 | Whether Entra OBO tokens carry an actor claim | 4.4 vendor example | Not checked |
| 14 | Sender-constrained tokens, DPoP, RFC 9449, Standards Track. It proves the presenter holds a key, so a stolen token fails at the next hop. RFC 9700 section 4.10 says sender-constrained tokens SHOULD be used, and audience restriction SHOULD be used, `AP/identity/rfc9700.txt` lines 1570 to 1576 | "What can you prove afterwards" is stronger when each hop proves key possession. Neither the dossier nor Module 6 covers it | Added by the reviewer as a gap. Source saved, `AP/identity/rfc9449.txt` lines 24 to 27, not used by any report. No lab |
| 15 | `may_act` enforcement in an STS | 4.4 now names `may_act`. No lab shows an STS refusing an exchange by an agent the subject token does not name | Designed only, as the L1 addition in section 6 |

---

## 9. Primary sources

All were fetched on 2026-09-23 by a research agent and returned HTTP 200 unless noted. Each report's source table has the full list. None is peer reviewed. RFCs and OpenID Final specs passed standards-body consensus. Drafts did not.

- **A2A Protocol Specification v1.0.1, Linux Foundation** — https://a2a-protocol.org/v1.0.1/specification/. Sections 3.2.2, 3.6, 4.3.3, 7, 8.4, 13.4.
- **A2A `a2a.proto` at tag v1.0.1** — https://raw.githubusercontent.com/a2aproject/A2A/v1.0.1/specification/a2a.proto. The normative data model, per section 1.4.
- **A2A specification, latest, unreleased text** — https://a2a-protocol.org/latest/specification/. Section 7.6.4 only.
- **A2A Agent Discovery, latest, unreleased text**: https://a2a-protocol.org/latest/topics/agent-discovery/. The curated-registry sentence only.
- **MCP Security Best Practices, 2026-07-28, MCP project**: https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices. Confused Deputy with consent cookies, Scope Minimization. Saved in Module 6 research, `scratchpad/research_tools-mcp/mcp/md/secbp.md`.
- **Transaction Tokens For Agents -02, individual draft**: https://www.ietf.org/archive/id/draft-araut-oauth-transaction-tokens-for-agents-02.txt. It replaced `draft-oauth-transaction-tokens-for-agents-06`.
- **What's New in A2A v1.0** — https://a2a-protocol.org/latest/whats-new-v1/. Breaking changes.
- **A2A GOVERNANCE.md** — https://raw.githubusercontent.com/a2aproject/A2A/main/GOVERNANCE.md. TSC with eight seats.
- **`a2a-sdk` 1.1.5 source, A2A project** — https://pypi.org/project/a2a-sdk/1.1.5/. `utils/signing.py`, `client/card_resolver.py`, `server/tasks/base_push_notification_sender.py`, `server/routes/jsonrpc_routes.py`.
- **MCP 2026-07-28 changelog, MCP project** — https://modelcontextprotocol.io/specification/2026-07-28/changelog. Sessions removed, tasks extension, DCR deprecated.
- **MCP Tasks extension** — https://modelcontextprotocol.io/extensions/tasks/overview. Reached by redirect.
- **MCP Enterprise-Managed Authorization, Stable extension** — https://raw.githubusercontent.com/modelcontextprotocol/ext-auth/main/specification/stable/enterprise-managed-authorization.mdx.
- **RFC 8693, OAuth 2.0 Token Exchange, IETF** — https://www.rfc-editor.org/rfc/rfc8693.txt. Sections 1.1, 2.1, 2.1.1, 4.1, 4.4.
- **RFC 9396 Rich Authorization Requests** and **RFC 9700 OAuth Security BCP, IETF** — https://www.rfc-editor.org/rfc/rfc9396.txt and https://www.rfc-editor.org/rfc/rfc9700.txt. 9396 section 6.1, 9700 section 2.3.
- **Transaction Tokens -11, IETF OAuth WG** — https://www.ietf.org/archive/id/draft-ietf-oauth-transaction-tokens-11.txt. Sections 6, 12, 13.6, 13.12, 13.13, 15.2.
- **Identity Chaining -17, IETF OAuth WG** — https://www.ietf.org/archive/id/draft-ietf-oauth-identity-chaining-17.txt. Scope control near line 623. Queue-entry date: https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-chaining/history/.
- **ID-JAG -04** and **CIMD -02, IETF OAuth WG** — https://www.ietf.org/archive/id/draft-ietf-oauth-identity-assertion-authz-grant-04.txt and https://www.ietf.org/archive/id/draft-ietf-oauth-client-id-metadata-document-02.txt.
- **AI Identity Management System -00, IETF WIMSE WG** — https://www.ietf.org/archive/id/draft-ietf-wimse-aims-00.txt. Sections 6, 7, 10.3, 10.7, 11.
- **AAuth -10, individual draft, Hellō** — https://www.ietf.org/archive/id/draft-hardt-oauth-aauth-protocol-10.txt. The `act` layout near line 3835.
- **SPIFFE standards, CNCF** — https://github.com/spiffe/spiffe/tree/main/standards. JWT-SVID sections 3 and 7, SPIFFE-ID.
- **SPIRE v1.15.3 `builder.go`** — https://raw.githubusercontent.com/spiffe/spire/v1.15.3/pkg/server/credtemplate/builder.go. TTL defaults, lines 28 to 42.
- **OpenID CAEP 1.0 Final and SSF 1.0 Final, OpenID Foundation** — https://openid.net/specs/openid-caep-1_0-final.html and https://openid.net/specs/openid-sharedsignals-framework-1_0-final.html.
- **OpenTelemetry semantic conventions v1.44.0** — https://github.com/open-telemetry/semantic-conventions/tree/v1.44.0. `gen_ai`, `enduser` and `user` registries.
- **WebMCP, Draft CG Report 17 September 2026, W3C Web Machine Learning CG** — https://webmachinelearning.github.io/webmcp/. Status, 4.2 IDL, 4.5, 5.2, 6.2, 6.3.2, 6.4.
- **WebKit position on WebMCP** — https://github.com/WebKit/standards-positions/issues/670. **Mozilla position** — https://github.com/mozilla/standards-positions/issues/1412.
- **Chrome origin trials API** — https://chromestatus.com/api/v0/origintrials. WebMCP entry.
- **IANA Well-Known URIs** — https://www.iana.org/assignments/well-known-uris/well-known-uris.xml.
- **Agno issue 10387** — https://github.com/agno-agi/agno/issues/10387. Version skew in a real server.
- **IBM ContextForge A2A integration** — https://ibm.github.io/mcp-context-forge/using/agents/a2a/. Vendor document.
- **Microsoft identity platform OBO flow** — https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow. Vendor document.
- **MCP Server Card schema URL** — https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json. **HTTP 404** on 2026-09-23.

---

## 10. Tools and versions to pin

Checked on 2026-09-23 by the research agents, except x402, checked by the dossier author.

| Item | Version | Date | Note |
|---|---|---|---|
| A2A spec | v1.0.1 | 2026-05-28 | GitHub releases API |
| `a2a-sdk`, Python | 1.1.5 | 2026-09-21 | Python 3.10 or later. Used in all A2A labs |
| `@a2a-js/sdk` | 1.2.0 | 2026-09-18 | Not tested |
| `a2a-tck`, conformance kit | 1.0.0.alpha2 | 2026-05-27 | Not run |
| MCP spec | 2026-07-28 | 2026-07-28 | Same as Module 6 |
| `mcp`, Python | 2.2.0 | 2026-09-07 | Same as Module 6 |
| WebMCP spec | CG draft of 2026-09-17 | 2026-09-17 | No versioned releases. Pin by date or commit |
| `pyjwt` | 2.14.0 | 2026-09-11 | L1. Does not check `act` |
| `spiffe`, py-spiffe | 0.3.1 | 2026-08-08 | Needs `pyjwt<2.14`. Resolves to 2.13.0 |
| `cryptography` | 50.0.1 | 2026-08-25 | ES256 keys |
| `authlib` | 1.8.0 | 2026-08-30 | Its `rfc8693` package holds only a docstring. No token exchange code |
| `jsonschema` | 4.26.0 | 2026-01-07 | Server-card check |
| SPIRE | v1.15.3 | 2026-08-21 | Linux and windows-amd64 binaries. No macOS binary |
| OTel semantic conventions | v1.44.0 | 2026-08-04 | Latest tag |
| OTel GenAI semconv | no release | `main` at `8ffdf568` | Pin by commit |
| MCP Registry | v1.8.1 | 2026-08-06 | API v0.1, preview |
| Chrome | 149 or later for the trial | trial ends 2026-11-17 | Optional browser part only |
| `x402`, Python | 2.24.0 | 2026-09-22 | Module 22 only. `D8/pypi_x402.json` |

---

## 11. Things not verified

From all three reports and from this dossier. Each item has the check that would settle it.

**From the A2A report.**

1. Other SDKs share the Python SDK gaps: push `Authorization`, canonical form, `-32602` on terminal tasks. Check: run Labs 1 and 3 against `@a2a-js/sdk` 1.2.0.
2. A card signed by the JS SDK verifies in the Python SDK. Check: sign with JS, verify with `create_signature_verifier`.
3. Production A2A use in Azure AI Foundry, Copilot Studio and Bedrock AgentCore. Only the LF release says so. Check: each vendor's own docs page and the A2A version it supports.
4. "More than 150 organizations". Self-reported, no list. Check: a member list on the LF or A2A site.
5. An IETF or W3C draft for A2A. Not searched. Check: datatracker and W3C groups for "Agent2Agent".
6. What `experimental-ext-oid4vp-auth` defines. Check: read its README and spec.
7. A default `SendMessage` fails behind a proxy idle timeout. Check: a 60 s agent behind a 30 s proxy.
8. A later SDK marks orphaned `WORKING` tasks as failed on startup. Check: rerun `db_trace.py` on each new release.
9. Spec `latest` equals the main branch. Check: compare with `specification/` at the main commit.
10. The TCK catches the gaps in A2A report 2.9. Check: run `a2a-tck` 1.0.0.alpha2 against `server.py`.

**From the identity report.**

11. Content of the OpenID Foundation paper, arXiv 2510.25819. Only metadata was fetched. Check: fetch the PDF and read its recommendations.
12. Which identity providers issue nested `act` chains today. Check: product docs at a pinned version, or Keycloak locally.
13. Whether Entra OBO tokens carry an actor claim. Check: the Entra access token claims reference.
14. When OTel moved GenAI conventions to their own repo. Check: `git log` on the move commit.
15. Whether a GCP workload identity pool without an attribute condition accepts any token from its identity provider. Check: provider setup docs or a sandbox project.
16. Whether GitHub Actions or Kubernetes OIDC tokens carry an end-user field. Check: decode a sample token from each docs page.
17. SPIRE build and run on macOS arm64. Check: `go build ./cmd/...` at v1.15.3.
18. AAuth -10 beyond its `act` layout. Check: read sections 1 to 6 of the saved file.
19. WIMSE architecture -08 beyond its title. Check: read the saved file.
20. Cyera and Oso method for "96% unused". Check: the full report.
21. Open MCP SEPs on token exchange or agent identity. Check: search the MCP repo pull requests for "8693" and "actor".

**From the web report.**

22. Edge 150 runs a WebMCP origin trial. Check: the Edge origin-trials page in a browser.
23. ChatGPT Desktop and Brave Leo support WebMCP. Check: vendor notes or a test page.
24. The exact commit that renamed `navigator.modelContext` to `document.modelContext`. The rename itself is verified. Check: page through commits between 2025-12-04 and 2026-07-21.
25. AG-UI and Agent Client Protocol auth and state models. Check: their spec pages.
26. ANP adoption. Check: production users or dependent packages.
27. What Google Search says about `llms.txt`. Check: the Google Search Central page on AI features.
28. ContextForge maps A2A `input-required` into an MCP tool result. Check: run it with a stub agent.
29. Lab A and Lab B run times. Check: build and time the labs.
30. The Hugging Face discovery registry API path. Check: `huggingface/hf-discover` docs.

**From this dossier.**

31. Closed by Phase 2. With `enable_v0_3_compat=True`, a 0.3 body with no header is served as 0.3. A 1.0 body with no header still gets `-32009`. `runs/agent-protocols_p02_version_skew.txt` lines 32 and 34. See 4.15.
32. Closed. "revoc" has 0 hits in the 7 saved MCP auth files with content. Two saved files are 404 stubs. The Module 6 copy of the Security Best Practices page has 2 hits, both about broad scopes. See 4.8.
33. Partly closed by the reviewer. The three saved GenAI files have no such attribute, 4.16. Other files in the repository are not checked. Check: grep the full repository at `8ffdf568`.
34. The machine conditions of the research runs: core count, memory, load. Not recorded in the reports. Check: `sysctl hw.ncpu hw.memsize` and `uptime` on the next run.
35. The grep in section 12 proves a string is in a saved file. It does not prove the live page still says it today. Check: re-fetch before the phase is published.

---

## 12. Anchor number re-check

The dossier author grepped 115 anchors from section 4 on 2026-09-23. Each search ran over the saved source, run output or installed SDK file named in the concept. Whitespace is collapsed to one space, so a quote split across lines still matches. Backticks and double asterisks are removed from the file text first. Script: `D8/anchor_check.py`. Output: `D8/anchor_check.txt`. First line numbers: `D8/anchor_lines.txt`.

- **115 of 115 anchors match their expected count.** 97 are presence checks. 18 are absence or exact-count checks, such as "8693" with 0 hits in the A2A page and 5 push errors in `push_trace_503.err`.
- Per concept, found of checked:

| Concept | Anchors | Concept | Anchors |
|---|---|---|---|
| 4.1 | 8 of 8 | 4.9 | 9 of 9 |
| 4.2 | 11 of 11 | 4.10 | 6 of 6 |
| 4.3 | 6 of 6 | 4.11 | 5 of 5 |
| 4.4 | 6 of 6 | 4.12 | 9 of 9 |
| 4.5 | 6 of 6 | 4.13 | 8 of 8 |
| 4.6 | 7 of 7 | 4.14 | 11 of 11 |
| 4.7 | 5 of 5 | 4.15 | 5 of 5 |
| 4.8 | 7 of 7 | 4.16 | 6 of 6 |

- **Two needles were fixed before they matched.** Neither changed a fact.
  1. The SPIRE default is written `DefaultJWTSVIDTTL = time.Minute * 5`, not `5 * time.Minute`. `builder_v1.15.3.go` line 38.
  2. The OTel deprecation text is a Markdown link: "Moved to the [OpenTelemetry GenAI semantic conventions repository]". The report quoted it without the bracket.
- **One report statement was found wrong by the grep.** The A2A report said the one "revoc" hit is section 8.4.3. It is section 13.4, line 4274. Section 7, conflict a.
- **One count was added by the dossier author.** No file in `AP/web/probe/` contains `"signatures"`: 0 of 56 files.
- **Anchors taken from reports without a re-grep** are marked in section 4 as "identity report" or "A2A report" with a section number. They are supporting evidence, never the best evidence.
- Every quote in section 4 is 25 words or shorter.

---

## 13. Review log


Reviewer: independent reviewer, not the dossier author. Date: 2026-09-23. Method: read-only greps of the saved files in `AP/`, `D8/`, the installed `a2a-sdk` 1.1.5 in `AP/a2a/lab/.venv`, and the Module 6 phase files. No lab was run. No URL was fetched. Writers: read "Corrections" first. Each one is already applied in the text above.

### Corrections, most serious first

| # | Where | What was wrong | Evidence | Fix applied |
|---|---|---|---|---|
| R1 | 4.14 heading and lead | "Only `GetTask` tells you how an A2A task ended" is false. A blocking `SendMessage` that completes returns the final state | `spec_v101.txt` line 1075: the blocking response "MUST include the latest task state". `trace.out` line 7 returned `TASK_STATE_COMPLETED` | Heading now says "If the call, the stream or the webhook is lost, only `GetTask` ...". Added spec 3.7, line 1439: streaming is not "a reliable delivery mechanism" |
| R2 | 4.7 heading and lead | "The `act` chain ... is not an input to access control" is false for the current actor. RFC 8693 requires the consumer to use the current actor | `rfc8693.txt` lines 723 and 724: "MUST only consider the token's top-level claims and the party identified as the current actor" | Heading now says only the current actor counts, earlier actors are the audit record. "may read only" changed to MUST |
| R3 | 4.6 conditions | Lab L1 was said to use ES256. It uses HS256 with one shared demo key | `AP/identity/proto/txchain.py` lines 12, 20 and 24 | Conditions now say HS256. Added that a real STS signs with an asymmetric key. ES256 in the identity report belongs to L4, `svid_check.py` |
| R4 | 4.7 forged `act` run | The run was read as "a forged chain verifies". The lab minted the forged token with the STS's own key | `txchain.py` lines 70 and 71 call `mint()`, which signs with the STS key | Added the condition: it shows the key holder can write any chain, not that an outsider can forge one |
| R5 | Section 3, 4.10 table, conflict c | `draft-klrc-aiagent-auth` was labelled "Individual draft". The datatracker shows it was adopted by the WIMSE WG before AIMS replaced it | `AP/identity/dt/draft-klrc-aiagent-auth.json`: group `wimse`, stream `IETF`, state Replaced. `draft-klrc-aiagent-auth.html`: "WG state Adopted by a WG" | Label corrected in three places. Conflict c now says the web report was right on status and wrong on date |
| R6 | Section 3, 4.6, 4.10 | Identity chaining "enters the RFC Editor queue 2026-07-19". 2026-07-19 is the date of revision -17. The queue-entry date is not in the saved files. Later found: 2026-06-22 at -15, see the last section. This is the same `rev_history` against state-change error that conflict c settled | `AP/identity/dt/draft-ietf-oauth-identity-chaining.json`: -17 published 2026-07-19T14:03, `iesg_state` "RFC Ed Queue", `time` 2026-08-21 20:25 | Now says "in the RFC Editor queue on 2026-09-23". Entry date listed as not in the files |
| R7 | 4.10 status table | WG and individual drafts had no intended status | Headers: Txn Tokens -11, ID-JAG -04, CIMD -02, AAuth -10 say "Intended status: Standards Track". OBO -02 says Informational. Chaining JSON: `intended_std_level` Proposed Standard. OBO JSON: state Expired, expires 2026-02-27 | Intended status added to each row |
| R8 | 4.1, 7.6.4 bullet | The unreleased sentence was presented as about every A2A credential. It is about the credential obtained in response to `TASK_STATE_AUTH_REQUIRED` | `AP/a2a/spec.txt` line 2867, full sentence | Scope of the sentence stated |
| R9 | 4.14 push bullets | Spec lines for the push `Authorization` MUST and the 4.3.3 "MAY implement retry logic" were missing. The retry disagreement is MAY against SHOULD for the same act | `spec_v101.txt` lines 1616, 1630, 4176, 4178. `push_trace.py` line 24 sets `authentication` | Lines added. Conflict k row updated |
| R10 | 4.15 | "Clients MUST send the header on every request" left out "except for 0.3 Clients". "avoid automatic fallback" is a lower-case "should" in section 3.6.3, not a normative rule | `spec_v101.txt` lines 1387 and 1420, headings 3.6.1 and 3.6.3 | Both corrected |
| R11 | 4.2 | "8785" was counted as 3 lines in the v1.0.1 page. It is 5 lines. The canonical form bullet said the spec keeps empty strings and lists. The spec keeps only required empty fields and drops the non-required empty `extensions` | `grep -n 8785 spec_v101.txt`: lines 2884, 2894, 2933, 2971, 3015. Spec lines 2894 to 2934 | Both corrected |
| R12 | 4.4 | The delegation and impersonation quotes had their line numbers swapped | `rfc8693.txt` line 204 is delegation, line 196 is impersonation | Line per quote |
| R13 | 4.13 | WebMCP unload claim cited line 98. Line 98 is the page-local map. The unload rule is elsewhere | `webmcp_spec.txt` line 101 and lines 194 to 203, "unloading document cleanup steps" | Lines corrected |
| R14 | Section 3 row 2026-06-18 | The date was cited to `ext_README.md` line 14, which gives only the Stable listing | `AP/identity/mcp/ext_ema_commits.json`: newest commit 2026-06-18T08:44:30Z | Date source added |
| R15 | Section 3 row 2026-03-02 | "First multi-vendor agent-auth draft" had no evidence | None found | Marked "not checked" |
| R16 | 2, overlap table | Two Module 6 overlaps were missing. Module 6 4.1 already teaches server-minted handles. Module 6 5.3 lab already shows that a relayed token hides the relay in the downstream log | `tools-mcp-phase-04-mcp-protocol.md` line 213. `tools-mcp-phase-05-mcp-trust.md` line 463 | Two rows added. Writers link, do not re-teach |

### Additions for the module question, with evidence from saved files

| # | Where | Added | Evidence |
|---|---|---|---|
| A1 | 4.4 | `may_act`: the subject token can name which party may act for the user. The only RFC 8693 control on which agent may act | `rfc8693.txt` lines 805 to 813, section 4.4 |
| A2 | 4.4 | The hop into "another company's" domain: identity chaining -17, token exchange inside your domain, then a JWT grant at the other domain | `draft-ietf-oauth-identity-chaining-17.txt` lines 24 to 32 |
| A3 | 4.4 | AIMS puts the user in `sub` beside the agent in `client_id`, and still names RFC 8693 token exchange | `draft-ietf-wimse-aims-00.txt` lines 756 to 761, 457, 912 |
| A4 | 8, gap 14 | Sender-constrained tokens, DPoP, RFC 9449. Saved but used by no report. Listed as a gap, not taught | `rfc9449.txt` lines 24 to 27. `rfc9700.txt` lines 1570 to 1576 |
| A5 | 8, gap 15 | No lab shows an STS enforcing `may_act` | Section 6 lists it as a designed L1 addition only |

### Items closed by reviewer greps

- Section 11 item 32 and 4.8: "revoc" has 0 hits in `auth_authorization-server-discovery.mdx`, `auth_client-registration.mdx`, `auth_index.mdx`, `auth_security-considerations.mdx`, `authorization.mdx` and `security_best_practices.mdx`. Later correction: `authorization.mdx` and `security_best_practices.mdx` are 14-byte "404: Not Found" stubs. The verified claim is 0 hits in the 7 files with content. See 4.8 and the last section.
- Section 11 item 33 and 4.16: the three saved `genai_main_*.md` files have 0 hits for "enduser", "user.id", "authoriz", "principal" and "actor". "delegat" has 1 prose hit. Partly closed. Only three files were saved.

### Spot checks that matched, 61 anchors

Each was read at the stated line in the saved file. Section numbers were read from the nearest heading.

- **A2A spec v1.0.1, `AP/a2a/spec_v101.txt`, 19 anchors.** Lines 2744, section 7.3, 2761, section 7.5, 2813, section 7.6.2, 2827, section 7.6.3, 2880, section 8.4, 3012 and 3025, section 8.4.3, 4274, section 13.4, 1069, section 3.2.2, 1137, section 3.3.1, 1204, section 3.3.2, 1414, section 3.6.2, 1629 and 1632, section 4.3.3, 4688, Appendix B. Counts: "consent" 0, "audience" 0, "token exchange" 0, "8693" 0, "revoc" 1 line, 4274. Conflict a is correct.
- **A2A unreleased text.** `spec.txt` line 2867, the 7.6.4 sentence, present.
- **A2A lab outputs, 12 anchors.** `trace.out` lines 7, 13, 53, 67, 75. `push_trace_503.out` line 2, 5 "Error sending push" lines in `.err`. `push_trace_200.out` line 8. `sign_check.out` lines 3, 4, 6. `canon_check.out` line 4. `db_trace.out` lines 1 to 4.
- **SDK 1.1.5 source, 5 anchors.** `card_resolver.py` line 150, `signing.py` line 82, `base_push_notification_sender.py` lines 49 to 50 and 102, `jsonrpc_routes.py` line 32. All match. The installed package is `a2a_sdk-1.1.5.dist-info`.
- **A2A history.** CHANGELOG 0.3.0 of 2025-07-30 has "Add `signatures`", `changelog.raw` line 107. 1.0.0 of 2026-03-12. #1403 "Clarify blocking calls return on interrupted states", line 47. "8785" has 0 hits in `spec_v030.txt`.
- **RFC 8693, 8 anchors.** Lines 196, 204, 334, 380, 386, 399, 715, 716, 725. Sections 1.1, 2.1, 2.1.1, 4.1 match. "subset" 0 hits. Header: Standards Track, January 2020.
- **Drafts, 12 anchors.** AIMS lines 7, 28 to 29, 756, 972, 983, 989, 1139, 1144, 1147, 403. Header date 15 September 2026. Authors include Defakto, AWS, Zscaler, Ping Identity, OpenAI and Okta. Txn Tokens -11 line 1252, section 13.6, line 1441, section 15.2, date 30 July 2026. Chaining -17 line 623, date 19 July 2026. AAuth -10 line 3835, date 6 August 2026. ID-JAG -04 21 May 2026. CIMD -02 6 July 2026.
- **Datatracker.** `dt_revdates.txt` and the JSON files. AIMS -00 2026-09-15, group wimse. klrc -03 2026-07-06. Chaining in "RFC Ed Queue". AAuth group "Individual Submissions".
- **MCP, 7 anchors.** Extension lines 5, 40, 48, 129. It links ID-JAG -04. `changelog.mdx` lines 96 to 99. "8693" and "token exchange" 0 hits in the four `auth_*.mdx` files. The fifth file, `authorization.mdx`, is a 14-byte 404 stub, so it proves nothing. `auth_security-considerations.mdx` line 95, CIMD and `localhost`. `AP/web/mcp_changelog.txt` line 59. `AP/a2a/mcp_changelog.txt` line 137. `mcp_tasks.txt` line 126.
- **SPIFFE and L4.** `JWT-SVID.md` lines 69 and 121. `SPIFFE-ID.md` line 76. `builder_v1.15.3.go` line 38. `svid_run.txt` lines 1, 8, 9, 10.
- **L1.** `txchain_run.txt` lines 11, 14, 15, 18, 21. Line 22 gives 0.17 s real.
- **WebMCP and web.** `webmcp_spec.txt` lines 4, 5, 24, 837, section 5.2, 862, section 6.2, 981, section 6.3.2, 1078, section 6.4.1, "OAuth" 0 hits, `'self'` default at lines 781 to 782. `webkit_pos.json` line 38 oppose. `moz_pos.json` line 49 neutral. `cs_ot.json`: WebMCP, ACTIVE, milestones 149 to 156, ends 2026-11-17. `iana_wellknown.xml` lines 24 to 26, registered 2025-08-01, updated 2026-09-16, "ai-catalog" 0, "mcp" 0. `extsc_readme.md` line 3. `agno_10387.txt` line 138. `contextforge_a2a.txt` line 311. `entra_obo.txt` line 74.
- **OTel and OIDF.** `docs_registry_attributes_gen-ai.md` lines 18 to 20. `docs_registry_attributes_enduser.md` line 39. CAEP 1.0 Final, Standards Track, published 29 August 2025, with all three event names.
- **RFC status.** RFC 9700 BCP 240, January 2025. RFC 9396 Standards Track, May 2023. RFC 9449 Standards Track.
- **x402.** `D8/pypi_x402.json`: 2.24.0, uploaded 2026-09-22T18:28:24, repository `x402-foundation/x402`. Conflict f is correct.

### The 11 conflicts, checked against their evidence

| Conflict | Result |
|---|---|
| a | Correct. "revoc" matches only line 4274. "revoked" on line 3025 does not contain "revoc" |
| b | Correct. Lines 1414, `trace.out` line 53, `jsonrpc_routes.py` line 32. The quiet 0.3 case was later measured in Phase 2. See 4.15 |
| c | Date part correct. Status part corrected, R5 |
| d | Correct. Header line 7 says Informational. JSON `intended_std_level` is None |
| e | Correct. MCP changelog line 59 and item 6, `mcp_tasks.txt` line 126 |
| f | Correct. `D8/pypi_x402.json` |
| g | Correct. CHANGELOG line 107 under 0.3.0. "8785" 0 in 0.3.0, 5 lines in v1.0.1 |
| h | Correct for the claims checked. Only 7.6.4 came from `latest` |
| i | Correct. It is a disagreement between drafts. AIMS lines 756 and 761, AAuth line 3835 |
| j | Correct. Section 3.3.3 line 1216 says operations "return immediately". Section 3.2.2 lines 1069 and 1075 say blocking is the default. CHANGELOG #1403. Run `trace.out` line 7 |
| k | Correct. Line numbers added, R9 |

### Labels and status words

- Every standard in 4.10 now has its status, intended status where the header gives one, revision and date.
- SDK behaviour is tied to `a2a-sdk` 1.1.5 and a run file in 4.2, 4.13, 4.14 and 4.15. The 4.14 heading now says "in SDK 1.1.5" for the one-attempt webhook, because the spec allows retries.
- No place was found where a spec rule is claimed from SDK behaviour only. 4.14 and 4.15 keep spec and SDK in separate bullets.

### Module 6 overlap

- `grep '^## '` on `tools-mcp/*.md`: headings 4.1 to 4.4 and 5.1 to 5.4. Module 8 does not re-teach the audience check, passthrough, annotations or the wire format. The section 5 rows for MCP transport and version negotiation are one line each with a link to Module 6, 4.1. Keep them that way.
- Module 6 does not mention RFC 8693, `act`, `may_act`, CIMD, ID-JAG, revocation or DPoP. Its phase 4 line 966 assigns token exchange and agent identity to Module 8.

### What the reviewer could not check

- Any live page. The saved files were not re-fetched. Section 11 item 35 still applies.
- Whether the GenAI OTel repository has no release. Taken from the identity report.
- Engine and editor names in 4.12 beyond the position labels. "Editors from Microsoft and Google" was not re-read.
- The 551 and 3 counts in 4.10, `dt_agent_count.txt`. The first lines were read. The query itself was not re-run.
- The machine conditions of the runs. Still not recorded.
- Section 6 run times marked "Not recorded" and the push lab duration.

---

## Corrections found while building the course

The fact checks of Phases 1 to 5 found these items on 2026-09-23. Each one is fixed in the text above. Paths starting with `reports/`, `runs/`, `factcheck_ap4/` or `agent-protocols_p04/` are in `scratchpad/`. Line numbers in the first column are this file after the edit.

| # | Where | What the dossier said before | What is correct | Evidence |
|---|---|---|---|---|
| C1 | 4.8, line 254 | "revoc" has 0 hits in five MCP auth files, `auth_*.mdx` and `authorization.mdx`, and 0 in `security_best_practices.mdx` | Two of the nine saved `.mdx` files are 404 stubs. The claim is 0 hits in the 7 files with content | `wc -c AP/identity/mcp/authorization.mdx AP/identity/mcp/security_best_practices.mdx` prints 14 for each. Each file reads "404: Not Found". `grep -ic revoc` prints 0 for the other 7 |
| C2 | 4.8, line 255 | Not stated. The page was treated as checked | The Module 6 copy of the MCP Security Best Practices page has 2 "revoc" hits. Both are in "Scope Minimization". The page defines no revocation mechanism | `research_tools-mcp/mcp/md/secbp.md` line 889 "difficult revocation" and line 895 "Higher friction on revocation" |
| C3 | Section 5 line 386, section 11 item 32 line 590, review log line 663 | "0 hits in the five saved auth files". "Now verified" | Same as C1 | Same as C1 |
| C4 | Review log, line 678 | "8693" and "token exchange" 0 hits "in all five auth files" | 0 hits in the four `auth_*.mdx` files. The fifth file is a stub | Same as C1 for `authorization.mdx` |
| C5 | Section 3 line 150, 4.16 line 366 | "OTel GenAI conventions moved to their own repo" | 60 `gen_ai.*` rows are deprecated. 50 say "Moved to". 2 say "Removed, no replacement". 8 say "Replaced by" | `AP/identity/otel/docs_registry_attributes_gen-ai.md` lines 18 to 67, 288 to 292, 330 to 334. `grep -c 'badge/-deprecated-red'` prints 60. `grep -c 'Moved to the'` prints 50. `reports/agent-protocols_p05_factcheck.md`, change at line 461 |
| C6 | Section 3 line 146, section 10 line 535 | SPIRE v1.15.3 "Linux binaries only" | Linux and `windows-amd64` binaries. No macOS binary | `AP/identity/spiffe/rel_spire.json`, `assets` has `spire-1.15.3-windows-amd64.zip`. `reports/agent-protocols_p03_factcheck.md` line 21 |
| C7 | Section 3 line 141, 4.6 line 235, 4.10 lines 277 and 285 | The date identity chaining entered the RFC Editor queue "is not in the saved files". Timeline row dated 2026-07-19 | It entered the queue on 2026-06-22 at revision -15. -16 and -17 came later | `factcheck_ap4/idchain_hist.html`, row dated 2026-06-22, revision 15, "IESG state changed to RFC Ed Queue". `reports/agent-protocols_p04_factcheck.md` line 15 |
| C8 | 4.2, line 178 | Not stated. The A2A research report listed `alg` and `kid` only | Section 8.4.2 MUST list: `alg`, `typ` and `kid`. `typ` SHOULD be "JOSE" | `AP/a2a/spec_v101.txt` lines 2951 to 2955. `reports/agent-protocols_p02_factcheck.md` line 13 |
| C9 | 4.3 line 196, conflict h line 450 | Only 7.6.4 came from the unreleased `latest` docs | The curated-registry sentence is also from `latest`, the Agent Discovery page. v1.0.1 section 8.2 says only "curated catalogs of agents" | `AP/a2a/spec_v101.txt` line 2849. `AP/web/a2a_discovery.txt` line 147. `AP/web/fetch_log.txt` line 46, URL `https://a2a-protocol.org/latest/topics/agent-discovery/` |
| C10 | Line 39, 4.13 line 325, section 5 line 381 | A task is what the remote agent creates. The text implied every call makes one | An agent may answer `SendMessage` with a direct `Message` and no task | `AP/a2a/spec_v101.txt` line 666: "receive either a task that tracks the processing or a direct response message" |
| C11 | 4.4 line 207, 4.10 line 291 | Transaction Tokens for Agents -06, 2026-04-11, cited as active | The current text is `draft-araut-oauth-transaction-tokens-for-agents-02`, 22 May 2026. It replaced -06 | `agent-protocols_p04/araut.txt` lines 6 and 12. `agent-protocols_p04/ttfa_dt.txt`: "Replaced by draft-araut-oauth-transaction-tokens-for-agents". `reports/agent-protocols_p04_factcheck.md` line 46 |
| C12 | 4.10, line 290 | klrc row gave -03 of 2026-07-06 but not what 2026-09-09 is | -03 of 2026-07-06 is the latest revision. 2026-09-09 is the date of the "Replaced" change. WG state "Adopted by a WG". Intended status none given. Agrees with Phase 4 section 4.4 | `agent-protocols_p04/klrc_dt.txt`: "Last updated 2026-09-09 (Latest revision 2026-07-06)", "WG state Adopted by a WG". `agent-protocols-phase-04-exchange.md` line 566 |
| C13 | 4.15 lines 348 to 356, conflict b line 444, gap 10 line 470, item 31 line 589, review log line 691 | "Inferred, not run. With `enable_v0_3_compat=True`, the same request would be served as 0.3 with no error" | Default server: `-32009` inside HTTP 200 on JSON-RPC. Compat on: a 0.3 body with no header is answered as 0.3. A 0.3 body with header 1.0 gets `-32603`. A 1.0 body with no header still gets `-32009`. Spec 5.4 maps `-32009` to HTTP 400 on HTTP+JSON, not run | `runs/agent-protocols_p02_version_skew.txt` line 23 "error -32009", line 32 "error -32009", line 33 "error -32603", line 34 "task state 'completed'". `AP/a2a/spec_v101.txt` line 2034 "400 Bad Request" |
| C14 | 4.3 line 195, section 6 line 421 | No count. The web report counted one cross-site catalog entry | Two. huggingface.co points to `huggingface-hf-discover.hf.space` | `runs/agent-protocols_p02_crawl.txt` line 43: "cross-domain catalog entries: 2". Lines 32 and 34 name the two entries |
| C15 | 4.4, line 213 | Not stated | The ContextForge example body is A2A 0.3. A default `a2a-sdk` 1.1.5 server answers `-32601` | `AP/web/contextforge_a2a.txt` line 388 `"method": "message/send"`. `runs/agent-protocols_p02_version_skew.txt` lines 26 and 27 "error -32601 Method not found" |
| C16 | 4.3 line 194, section 5 line 387 | Server Card source cited without a repository name. Research reports used `experimental-ext-server-card` | The repository is `modelcontextprotocol/ext-server-card`. The README still says "Experimental" | `AP/web/extsc_repo.json` `full_name` "modelcontextprotocol/ext-server-card". `AP/web/extsc_readme.md` line 3 |
| C17 | Section 2, line 93 | "confused deputy exploits" with no source | The consent-cookie detail is from the MCP Security Best Practices page. The spec's Confused Deputy section has no cookie | `AP/identity/mcp/auth_security-considerations.mdx` lines 107 to 114, `grep -ic cookie` prints 0. `research_tools-mcp/mcp/md/secbp.md` lines 37 and 38: "static client IDs, dynamic client registration, and consent cookies" |
| C18 | Section 2, lines 80 to 82 | Phase 5 concepts not in scope | Three concepts added: action-bound grants with `authorization_details`, introspection with exchange lineage, a `txn` claim plus a hash-chained log | `runs/agent-protocols_p05_consent.txt` line 5. `runs/agent-protocols_p05_revoke_introspect.txt` line 7 "REJECT (introspection: active=false)". `runs/agent-protocols_p05_audit_tamper.txt` line 12 "hash chain: broken at record 7" |
| C19 | 4.2, line 180 | Not stated | An ES256-only verifier rejects an HS256-signed card. The signature header has no time fields. The SDK card fetcher skips signature checks by default | `runs/agent-protocols_p02_card_sign.txt` line 8 "REJECTED (InvalidSignaturesError)", line 11 "time fields present (exp, iat, nbf): []", line 15 "None" |
| C20 | 4.1, line 166 | Not stated | The SDK `AuthInterceptor` adds only the first usable credential, then stops | `SDK/client/auth/interceptor.py` lines 56 to 63: sets `Authorization`, then `return`. `reports/agent-protocols_p03_factcheck.md` line 24 |
| C21 | Section 9, lines 486 to 488 and 498 | These sources were not listed | Agent Discovery page labelled unreleased. MCP Security Best Practices page. Transaction Tokens For Agents -02. Identity chaining history page | The evidence in C7, C9, C11 and C17 |
