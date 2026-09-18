# Module 06 — The tool layer and MCP internals

Research date: 2026-09-17. Status: research dossier, not course material.

## 1. What this module is for

This module teaches how a model calls tools, and how the Model Context Protocol carries those calls. The Model Context Protocol, or MCP, is an open JSON-RPC protocol between an AI application and tool servers. A support agent calls tools on every turn, such as order lookup and refund. Each tool definition costs input tokens on every call and sits at the start of the cache prefix. A poor name, description, or error message makes the model pick the wrong tool or retry in a loop. A third-party MCP server can change its descriptions after approval, or accept a token meant for another service. Model-written code needs a sandbox, and each sandbox type stops different things. MCP changed in a breaking way on 2026-07-28, so older tutorials are out of date.

## 2. Scope

### In scope

- Tool design: names, descriptions, schemas, result size, and error messages the model can act on.
- Token and cache cost of tool definitions. Measured evidence on tool count and selection accuracy.
- Function calling for Anthropic, OpenAI, and Google: rendering, `tool_choice`, parallel calls, strict schemas, streaming arguments.
- Deferred tool loading, tool search, code execution, and programmatic tool calling.
- Agent Skills as a packaging format.
- MCP 2026-07-28: transports, stateless requests, features, structured output, authorization profile, registry, SDKs.
- MCP attack mechanisms with dated primary reports.
- Sandboxes: namespaces, cgroups, seccomp, gVisor, Firecracker, and OS sandboxes.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Tokenizers, prefix caching, `cache_control` | Module 1, sections 1.1, 3.2, 3.3 |
| Constrained decoding and the format tax | Module 1, section 2.5 |
| Clearing tool results, compaction | Module 1, section 2.6, then Module 2 |
| Agent loop and permission prompts | Module 7, harness engineering |
| Agent identity, OAuth flows, token exchange, A2A | Module 8, protocols and identity |
| Prompt-injection defences, red teaming | Module 16, security |
| Tool-call evals | Modules 11 and 12 |
| Tracing tool calls | Module 15 |

### Overlap with earlier modules

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Compact JSON in tool results | Module 1, 1.1. Pretty JSON cost 1.92x. | `response_format`, pagination, truncation limits |
| Schema enforcement | Module 1, 2.5 | Strict limits per provider, and what strict mode does not check |
| Tool definitions in the cache prefix | Module 1, 3.2 and 3.3 | Deferred loading and `allowed_tools`, which keep the prefix fixed |
| Tool results filling the context | Module 1, 2.6 | Programmatic calls that keep intermediate results out |
| Cache side channels | Module 1, 6.2 | Nothing new |

## 3. What changed recently

| Change | Date | Source | Why it matters |
|---|---|---|---|
| MCP Registry preview | 2025-09-08 | MCP blog | Still "preview" on 2026-09-17 |
| "Writing effective tools for agents" | 2025-09-11 | Anthropic engineering | Namespacing, `response_format`, actionable errors |
| Cloudflare Code Mode | 2025-09-26 | Cloudflare blog | Tools as a TypeScript API. No numbers. |
| Agent Skills | 2025-10-16. Open standard 2025-12-18. | Anthropic engineering | Three loading levels |
| Claude Code OS sandbox | 2025-10-20 | Anthropic engineering | Seatbelt and bubblewrap with a proxy |
| Code execution with MCP | 2025-11-04 | Anthropic engineering | Tools as files |
| Tool search and programmatic tool calling | Beta 2025-11-24. No header from 2026-02-17. | Anthropic post, release notes | Up to 10,000 deferred tools |
| MCP 2025-11-25 | 2025-11-25 | MCP changelog | URL elicitation, Client ID Metadata Documents, experimental tasks |
| MCP moves to the Agentic AI Foundation | 2025-12-09 | MCP blog | Linux Foundation governance |
| Strict tool use leaves beta | 2026-01-29 | Anthropic release notes | Grammar limits apply |
| Code Mode MCP server | 2026-02-20 | Cloudflare blog | 2,500+ endpoints in about 1,000 tokens |
| MCP SDK v2, TypeScript and Python | 2026-07-27, 2026-07-28 | npm, PyPI | Package split, renamed APIs |
| **MCP 2026-07-28, breaking** | 2026-07-28 | MCP changelog | No handshake, no sessions, `server/discover`, Multi Round-Trip Requests |
| MCP scanner reliability study | 2026-07-13 | arXiv 2607.11086 | Average scanner precision 45.53% |

## 4. Core concepts, with verified facts

### 4.1 A tool definition is prompt text

Providers render tool definitions as text in the prompt. So tools cost input tokens on every request, and they are part of the cache prefix. Providers also add hidden tool-use instructions.

- Anthropic builds "a special system prompt from the tool definitions, tool configuration, and any user-specified system prompt". Source: Anthropic "Define tools". Verified.
- Anthropic's hidden tool prompt for Claude Opus 5 is 286 tokens with `auto` or `none`, and 406 with `any` or `tool`. Sonnet 5: 354 and 474. Opus 4.7: 675 and 804. Source: Anthropic tool use overview. Verified by fetch.
- The value "346 tokens" from the module plan is not on the current page. Verified by grep.
- OpenAI: functions "are injected into the system message in a syntax the model has been trained on". They are "billed as input tokens". Source: OpenAI function calling guide. Verified.
- Anthropic caches in the order tools, system, messages. A tool definition change invalidates all three. A `tool_choice` or `disable_parallel_tool_use` change invalidates only messages. Source: Anthropic prompt caching and tool-use caching pages. Verified.
- OpenAI `allowed_tools` limits callable tools without changing `tools`, to "maximize savings from prompt caching". Source: OpenAI guide. Verified.

### 4.2 Choosing, forcing, and parallel calls

`tool_choice` says whether the model may, must, or must not call a tool. Parallel calls put several tool requests in one turn.

- Anthropic values are `auto`, `any`, `tool`, `none`. With `any` or `tool`, "the API prefills the assistant message to force a tool to be used". Source: "Define tools". Verified.
- Anthropic rejects `any` and `tool` with manual extended thinking, and on Claude Fable 5.1 and Mythos 5.1. Source: same page and release notes of 2026-09-01. Verified.
- Anthropic parallel calls are on by default. Turn them off with `disable_parallel_tool_use` inside `tool_choice`. Source: parallel tool use page. Verified.
- OpenAI values are `auto`, `required`, one named function, `allowed_tools`, `none`. `parallel_tool_calls: false` "ensures exactly zero or one tool is called". Verified.
- Google Gemini lists `auto`, `any`, `none`, `validated`, and an `allowed_tools` block. Source: Gemini function calling page. Verified. Older SDKs use upper-case enums. Inferred from the Go sample.

### 4.3 Strict tool inputs and streaming

Strict mode samples only tokens that keep the input valid for the schema. Module 1 section 2.5 covers the decoder. Streaming sends tool inputs as partial JSON strings.

- Anthropic strict limits per request: 20 strict tools, 24 optional parameters, 16 union-type parameters. Larger schemas return 400 "Schema is too complex for compilation". Source: Anthropic structured outputs page. Verified.
- "Each optional parameter roughly doubles a portion of the grammar's state space." Grammars are cached up to 24 hours. A `name` or `description` change does not invalidate them. Source: same page and strict tool use page. Verified.
- OpenAI strict mode needs `additionalProperties: false` on every object and every field in `required`. Chat Completions stays non-strict by default. Source: OpenAI guide. Verified.
- Strict mode checks shape, not meaning. A valid `order_id` can name the wrong order. Inferred from the mechanism.
- Anthropic streams `input_json_delta` events with `partial_json`. Clients parse at `content_block_stop`. Source: Anthropic streaming page. Verified.
- With `eager_input_streaming: true`, Anthropic streams "without server-side buffering or JSON validation". Source: fine-grained tool streaming page. Verified.
- OpenAI sends `response.function_call_arguments.delta` then `.done`. Gemini sends `partial_arguments` inside `step.delta` events. Sources: OpenAI and Gemini guides. Verified.

### 4.4 Tool design the model can use

The model reads names, descriptions, results, and error text. Each one changes what it does next.

- Anthropic: "More tools don't always lead to better outcomes." It prefers `search_contacts` over `list_contacts`. Source: "Writing effective tools for agents". Verified.
- The same post says prefix or suffix namespacing had "non-trivial effects" that "vary by LLM". No numbers are given. Verified quote.
- A `response_format` example: detailed 206 tokens, concise 72 tokens. Source: same post. Verified.
- "For Claude Code, we restrict tool responses to 25,000 tokens by default." Claude Code warns above 10,000. Sources: the post and Claude Code MCP docs. Verified.
- Errors should give "specific and actionable improvements, rather than opaque error codes or tracebacks". Source: the post. Verified.
- MCP 2025-11-25 returns input validation errors as tool execution errors, so the model sees them. Source: changelog, SEP-1303. Verified.
- Anthropic `input_examples` cost about 20 to 50 tokens each for simple cases. Invalid examples return 400. Source: "Define tools". Verified.

### 4.5 Tool count, selection accuracy, and tool search

More tools cost more tokens and cause more wrong picks. Vendors give thresholds, but none cites an evaluation. Deferred loading keeps definitions out of the prompt until a search tool finds them.

- Vendor advice, verified quotes, no evaluation cited:
  - Anthropic: selection "degrades once you exceed 30–50 available tools".
  - OpenAI: "Aim for fewer than 20 functions available at the start of a turn", "a soft suggestion".
  - Google: "Keep active set to 10-20 tools maximum."
- RAG-MCP, arXiv 2505.03275, Table 1. MCPBench web-search subset, qwen-max-0125, 20 trials. All tools in prompt: 13.62% accuracy, 2,133.84 prompt tokens. Retrieval first: 43.13%, 1,084 tokens. Verified. The paper names two different judges. Verified. The token cut is 49.2%, not "over 50%". Inferred by arithmetic.
- "Less is More", arXiv 2411.15399, Table II. Llama 3.1 8B q4_K_M on Jetson AGX Orin, one query: 46 tools failed, 19 succeeded. Verified. One query on a small model only.
- LiveMCPBench, arXiv 2508.01780. 527 tools, 95 tasks, LLM judge. Claude Sonnet 4 78.95%, GPT-5 52.63%. "retrieval errors account for nearly half of all failures". Verified.
- MCP-Bench, arXiv 2508.20453. 250 tools, o4-mini judge. Overall: gpt-5 0.749, claude-sonnet-4 0.681. Schema compliance 85.0% to 99.9%. Verified.
- No current frontier-model curve of accuracy against tool count was found. Lab 5 measures one.
- Anthropic tool search: `tool_search_tool_regex_20251119` and `_bm25_20251119`, `defer_loading: true`, up to 10,000 deferred tools, 5 results by default. Source: tool search page. Verified.
- "Deferred tools are not included in the system-prompt prefix", so "prompt caching is preserved". Strict grammars still build "from the full toolset". Source: tool-use caching page. Verified.
- Anthropic post, 2025-11-24: 58 tools used about 55K tokens. Tool search used about 8.7K against 77K, "an 85% reduction". No model is named. Verified quote.
- Same post: "Opus 4 improved from 49% to 74%, and Opus 4.5 improved from 79.5% to 88.1%". Condition given: "Internal testing". Verified quote. Eval and scorer not stated.
- OpenAI `tool_search` needs `gpt-5.4` or later. Found tools are "injected at the end of the context window". Verified.
- Claude Code loads only tool names at start. It truncates descriptions at 2KB. Source: Claude Code MCP docs. Verified.

### 4.6 Code as the tool call, and Skills

In programmatic tool calling the model writes code that calls tools. Intermediate results stay in the sandbox. A skill is a folder with `SKILL.md` that loads in levels.

- Anthropic programmatic calling needs `code_execution_20260120` or later and `allowed_callers`. "intermediate results are not loaded into Claude's context window". Source: programmatic tool calling page. Verified.
- It does not support `strict: true`, forced `tool_choice`, MCP connector tools, Bedrock, or Google Cloud. Verified.
- Code execution tool `code_execution_20260521`: 5 GiB RAM, 1 CPU, no internet. $0.05 per container hour after 1,550 free hours monthly. Free with `web_search_20260209` or later. Source: code execution tool page. Verified.
- Two Anthropic pages disagree on idle containers: "reclaimed after about 5 minutes" and "checkpointed", restorable for 30 days. Verified.
- Anthropic post: tokens fell "from 43,588 to 27,297", "a 37% reduction". No model named. Verified quote.
- Anthropic "Code execution with MCP": "150,000 tokens to 2,000 tokens". No method given. Verified quote. Inferred to be an illustration.
- Cloudflare: an equivalent MCP server "would consume 1.17 million tokens". The chart was "measured with tiktoken". Definition tokens only. Verified quote, scope inferred.
- Felendler et al., arXiv 2602.15945. MCP-Bench, GPT-4o and GPT-4.1 models, three GPT-4o judges. Code execution cut tokens and turns with "comparable" quality. It scored lower on some three-server tasks and had more latency outliers. Verified. Numbers are in figures only.
- AIMultiple, third party. GPT-4.1, 2 tasks, 50 runs each. Input tokens 15,417 to 3,310. Latency 9.66 s to 10.37 s. Output tokens 87 to 192. Verified.
- Skills level 1 metadata costs "~100 tokens per Skill". Level 2 is "Under 5k tokens". `name` at most 64 characters, `description` at most 1,024. Source: Anthropic Skills overview, agentskills.io spec. Verified.
- Codex caps its skill list at "2% of the model's context window". Copilot, VS Code, Cursor, and Gemini CLI call Agent Skills an open standard. Verified on each vendor page.

### 4.7 MCP protocol, version 2026-07-28

MCP is JSON-RPC 2.0 between a client in the host application and a server. Version 2026-07-28 removed the handshake and sessions. Each request now stands alone.

- Current version is 2026-07-28. `schema.ts` line 30 at that tag sets `LATEST_PROTOCOL_VERSION`. Earlier: 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25. Verified by fetch.
- Removed: the `initialize` handshake and `Mcp-Session-Id`. Each request carries version and capabilities in `_meta`. Servers MUST implement `server/discover`. Source: changelog, SEP-2575 and SEP-2567. Verified.
- Multi Round-Trip Requests replace server-initiated sampling, roots, and elicitation. The server returns `resultType: "input_required"`. The client retries with `inputResponses`. Source: changelog, SEP-2322. Verified.
- Streamable HTTP uses one POST endpoint. The GET stream and SSE resumability are gone. POSTs need `MCP-Protocol-Version` and `Mcp-Method`. Servers "MUST validate the `Origin` header". Source: transport page. Verified.
- Deprecated: Roots, Sampling, Logging, Dynamic Client Registration. Earliest removal is on or after 2027-07-28. "No features have been removed under this policy yet." Source: deprecated page. Verified.
- Tasks moved to the extension `io.modelcontextprotocol/tasks`. Source: changelog. Verified.
- `structuredContent` can match an optional `outputSchema`. Tools "SHOULD also return the serialized JSON in a TextContent block". Source: tools page. Verified.
- Annotation defaults: `readOnlyHint` false, `destructiveHint` true, `openWorldHint` true. Clients "MUST consider tool annotations to be untrusted unless they come from trusted servers". Source: `schema.ts` lines 1912 to 1954, tools page. Verified.
- `tools/list` order SHOULD be deterministic. Source: changelog. Verified. This helps the prompt cache. Inferred from Module 1 section 3.3.
- Registry: "currently in preview". API frozen at v0.1 since 2025-10-24. Sources: registry docs and README. Verified.

### 4.8 MCP authorization and attacks, mechanism only

A remote MCP server is an OAuth 2.1 resource server. Module 8 teaches the flows. Module 16 teaches defences.

- "MCP servers MUST implement OAuth 2.0 Protected Resource Metadata", RFC 9728. Clients "MUST implement Resource Indicators", RFC 8707. Source: authorization page. Verified.
- Client ID Metadata Documents are recommended. Dynamic Client Registration is deprecated. Verified.
- Token passthrough "is an anti-pattern where an MCP server accepts tokens from an MCP client without validating" their audience. Source: Security Best Practices page. Verified, paraphrased after "validating".
- Tool poisoning hides instructions "invisible to users but visible to AI models". A rug pull is when a server changes "the tool description after the client has already approved it". Source: Invariant Labs, 2025-04-01. Verified.
- Scanner study, arXiv 2607.11086: 37,288 runnable servers. 96.89% flagged by at least one of eight scanners. Average precision 45.53%, range 10.40% to 96.88%. Tables 5 to 7. Verified.
- arXiv 2506.13538: 7.2% of 1,899 servers had vulnerabilities by SonarQube. The 5.5% poisoning figure comes from only 73 scanned servers. Verified.

### 4.9 Sandboxes for tool execution

A sandbox limits what executed code can reach. Each technology draws its boundary in a different place.

| Technology | Boundary | What it does not stop |
|---|---|---|
| Container, runc | Namespaces, cgroups, seccomp, shared host kernel | A kernel bug in an allowed syscall |
| seccomp-bpf | Syscall filter | Path or buffer checks |
| gVisor | User-space kernel, the Sentry | Side channels, bugs in higher layers |
| Firecracker | KVM microVM plus jailer | VMM or KVM bugs, side channels |
| Seatbelt, bubblewrap | OS process sandbox | Allowed paths and hosts, domain fronting |

- Kernel docs: "System call filtering isn't a sandbox." Filters cannot dereference pointers. Verified.
- Docker's default profile "disables around 44 system calls out of 300+". Source: Docker docs. Verified.
- gVisor "never passes through any system call to the host". Systrap is the default. ptrace "is no longer supported". Verified.
- gVisor performance data uses ptrace on a GCE n1-standard-4 with kernel 4.19. Raw syscall: runc 1,939 ns, runsc ptrace 38,219 ns, runsc KVM 763 ns. Verified. Old numbers.
- Firecracker v1.17.0 spec, m5d.metal and m6g.metal: VMM starts in 8 CPU ms. Boot to guest init within 125 ms with a minimal kernel and serial console off. Overhead at most 5 MiB for 1 vCPU and 128 MiB. Source: `SPECIFICATION.md` lines 8 to 42. Verified.
- Firecracker NSDI 2020, v0.20.0 on m5d.metal: p99 boot 146 ms at 50 concurrent boots. Stock Ubuntu kernel adds about 900 ms. Memory overhead about 3 MB, QEMU about 131 MB. Sections 5.1 and 5.2. Verified.
- Claude Code uses Seatbelt and bubblewrap, with network via a proxy outside the sandbox. Anthropic reports 84% fewer prompts "In our internal usage". Verified quote, no method.
- sandbox-runtime v0.0.76 README: domain fronting may bypass network filtering. Verified.
- Codex on Linux uses bubblewrap plus a seccomp network filter. Landlock is a legacy fallback. Source: README at `rust-v0.154.0`. Verified.
- On an Apple Silicon Mac, Docker Desktop, Apple `container`, and Lima run Linux inside a VM. Apple `container` 1.4.1 needs macOS 26. Verified.
- Pydantic archived mcp-run-python: "Python code running in pyodide can run arbitrary javascript". Verified.

## 5. Proposed phase outline

| Phase | Title | What it teaches | Labs it needs | Runs where, costs what |
|---|---|---|---|---|
| 1 | Tool definitions as prompt | Rendering, hidden prompt cost, cache invalidation, `tool_choice`, parallel calls, strict limits, streaming | 1, 2, 3 | Laptop, offline |
| 2 | Tool design and selection at scale | Naming, results, errors, count evidence, deferred loading, tool search | 4, 5, 6 | Laptop. Lab 5 live option about $1 to $3. |
| 3 | Code as the tool call, and Skills | Code execution, programmatic calls, code mode evidence, Skills loading | 7, 8 | Laptop, offline |
| 4 | MCP protocol internals | 2026-07-28 model, discovery, Multi Round-Trip Requests, transports, features, deprecations, registry, SDK v2 | 9, 10 | Laptop, Python `mcp` 2.2.0 |
| 5 | MCP authorization and attack surface | Resource server role, audience checks, passthrough, poisoning, rug pulls, CVEs, scanner reliability | 11, 12 | Laptop, offline |
| 6 | Sandboxes for tool execution | seccomp, gVisor, Firecracker, OS sandboxes, start time with conditions, bypass CVEs | 13, 14 | Laptop with Docker. gVisor and Firecracker need a Linux KVM host, about $0.20 an hour. |

Six phases fit because most topics are new. Module 1 covers only JSON token cost, strict decoding, and cache order. The 2026-07-28 revision needs its own protocol phase. Security and identity stay at mechanism level because Modules 8 and 16 own them.

## 6. Lab ideas

All labs are offline-first, with a self-test.

1. **Tool token meter.** Counts tokens for 1 to 200 tool schemas and hashes the prefix. Prints tools, tokens, hash. Break-it: shuffle order or keys. Self-test: sorted output gives one hash across 10 runs. A local tokenizer only approximates Claude counts.
2. **Strict schema linter.** Checks OpenAI strict rules and Anthropic limits of 20, 24, and 16. Prints violations. Break-it: a 25th optional field. Self-test: five fixtures with known counts.
3. **Partial JSON replay.** Replays recorded delta events and prints when input first parses. Break-it: parse every delta. Self-test: final object equals the fixture.
4. **Tool search recall.** BM25 and regex over 500 synthetic tools and 100 labelled queries. Prints recall at 1, 3, 5. Break-it: vague descriptions. Self-test: fixed seed, known recall.
5. **Accuracy versus tool count.** Scores stored outputs offline. Optional live run with 5, 20, 50, 100 tools on 50 requests. Needs an API key, about $1 to $3 on a Haiku-class model. Self-test: scorer matches hand labels.
6. **Results and errors.** A mock tool returns concise or detailed results, and opaque or actionable errors. A scripted policy retries by error text. Prints tokens and retries. Self-test: fixture retry count.
7. **Direct calls versus code.** Simulates N calls with result size S. Prints cumulative context tokens for both. Self-test: closed-form sum. Break-it: summary size near S.
8. **Skill budget checker.** Validates `SKILL.md` fields and prints level 1 tokens. Break-it: a 1,100-character description. Self-test: fixtures with known errors.
9. **Raw MCP trace.** A stdio server on `mcp` 2.2.0 logs every JSON-RPC message for a 2025-11-25 client and a 2026-07-28 client. Self-test: no `initialize` in the new trace. The dual-version behaviour is taken from the SDK blog, so run it first.
10. **Multi Round-Trip flow.** A tool returns `input_required`, and the client retries. Break-it: drop `requestState`. Self-test: second result is `complete`.
11. **Audience check.** A toy resource server validates JWT `aud` and `iss`. Break-it: disable the check and a passthrough token is accepted. Self-test: fixed accept table.
12. **Rug pull and poisoning detector.** Hashes approved descriptions and scans a labelled set. Prints precision and recall. Break-it: zero-width characters. Self-test: known counts.
13. **Sandbox probe matrix.** Runs probes under Docker, Docker with a custom seccomp profile, and `sandbox-exec`. Prints pass or fail for file read, egress, a blocked syscall, and a process limit. Self-test: the blocked syscall returns EPERM.
14. **Cold start timer.** Times 30 starts of a subprocess, `docker run`, and optional Apple `container`. Prints median and p95 with host and cache state. Self-test: statistics on a fixture.

## 7. Failure stories and case studies

| Case | Date | Mechanism | Numbers | Source |
|---|---|---|---|---|
| WhatsApp MCP exfiltration | 2025-04-07 | A sleeper server shadowed `whatsapp-mcp` | No CVE | Invariant Labs |
| GitHub MCP toxic agent flow | 2025-05-26 | A public issue leaked private repo data into a public PR | Design issue | Invariant Labs |
| MCP Inspector, CVE-2025-49596 | 2025-06-13 | No auth between client and proxy, plus DNS rebinding | CVSS 4.0 9.4. Fixed 0.14.1. | Oligo, NVD |
| Filesystem server, CVE-2025-53109 and 53110 | 2025-07-02 | Path prefix escape and symlink bypass | 7.3 each. Upgrade to 2025.7.1. | Cymulate |
| Supabase MCP | 2025-07-08 | A ticket injected instructions to an agent with `service_role` | No CVE | General Analysis |
| mcp-remote, CVE-2025-6514 | 2025-07-09 | Crafted `authorization_endpoint` ran a command | CVSS 3.1 9.6. Fixed 0.1.16. | JFrog advisory |
| Codex CLI, CVE-2025-59532 | 2025-09-19 | Model-chosen `cwd` became the writable root | 8.6. Fixed 0.39.0. | GitHub advisory |
| postmark-mcp | 2025-09 | Version 1.0.16 added a hidden BCC | 1,643 downloads per The Hacker News | Postmark, Snyk |
| Smithery hosting | 2025-10-22 | Build path traversal leaked admin credentials | "over 3,000 hosted AI servers" | GitGuardian |
| mcp-server-git, CVE-2025-68143 to 68145 | 2025-12-17 | Path traversal and argument injection chained to code execution | 68143 CVSS 3.1 8.8 | NVD, The Hacker News |
| Claude Code, CVE-2026-25725, 39861, 55607 | 2026-02 to 2026-06 | Settings write, symlink, git fsmonitor escapes | Fixed 2.1.2, 2.1.64, 2.1.163 | GitHub advisories |
| runc, CVE-2024-21626 | 2024-01-31 | Leaked fd gave a host working directory | 8.6. Fixed 1.1.12. | NVD, runc |

The Asana MCP exposure was found on Jun 4 and customers were told on Jun 16. The year 2025 is inferred. Source: UpGuard.

## 8. Primary sources

All fetched 2026-09-17. All returned HTTP 200 on the final check. SecurityWeek returned 403 to the research agent's plain fetch and 200 on the final check with a browser user agent.

### Provider tool calling

- **Tool use overview, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview, 200. Focus: hidden prompt token table.
- **Define tools, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools, 200. Focus: template, `tool_choice`, examples.
- **Parallel tool use, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use, 200.
- **Strict tool use, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use, 200.
- **Structured outputs, Anthropic, 2026** — https://platform.claude.com/docs/en/build-with-claude/structured-outputs, 200. Focus: limits.
- **Fine-grained tool streaming, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming, 200.
- **Streaming messages, Anthropic, 2026** — https://platform.claude.com/docs/en/build-with-claude/streaming, 200.
- **Prompt caching, Anthropic, 2026** — https://platform.claude.com/docs/en/build-with-claude/prompt-caching, 200. Focus: invalidation table.
- **Tool use with prompt caching, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching, 200.
- **Function calling, OpenAI, 2026** — https://developers.openai.com/api/docs/guides/function-calling, 200. Redirected from platform.openai.com.
- **Tool search, OpenAI, 2026** — https://developers.openai.com/api/docs/guides/tools-tool-search, 200.
- **Function calling, Google, 2026** — https://ai.google.dev/gemini-api/docs/function-calling, 200.

### Tool design, selection, code, Skills

- **Writing effective tools for agents, Anthropic, 2025** — https://www.anthropic.com/engineering/writing-tools-for-agents, 200.
- **Introducing advanced tool use, Anthropic, 2025** — https://www.anthropic.com/engineering/advanced-tool-use, 200. Note the missing conditions.
- **Code execution with MCP, Anthropic, 2025** — https://www.anthropic.com/engineering/code-execution-with-mcp, 200.
- **Tool search tool, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool, 200.
- **Programmatic tool calling, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling, 200.
- **Code execution tool, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool, 200.
- **Claude Code MCP, Anthropic, 2026** — https://code.claude.com/docs/en/mcp, 200.
- **Code Mode, Cloudflare, 2025** — https://blog.cloudflare.com/code-mode/, 200.
- **Code Mode MCP server, Cloudflare, 2026** — https://blog.cloudflare.com/code-mode-mcp/, 200. Focus: tiktoken chart.
- **From Tool Orchestration to Code Execution, Felendler et al., arXiv 2026** — https://arxiv.org/abs/2602.15945, 200. Focus: Figures 4 to 8. The only counter-evidence found.
- **Code execution with MCP benchmark, AIMultiple, 2026** — https://aimultiple.com/code-execution-with-mcp, 200. Two tasks.
- **Executable Code Actions, Wang et al., arXiv 2024** — https://arxiv.org/abs/2402.01030, 200.
- **RAG-MCP, Gan and Sun, arXiv 2025** — https://arxiv.org/abs/2505.03275, 200. Focus: Table 1.
- **Less is More, Paramanayakam et al., arXiv 2024** — https://arxiv.org/abs/2411.15399, 200. Focus: Table II.
- **LiveMCPBench, Mo et al., arXiv 2025** — https://arxiv.org/abs/2508.01780, 200. Focus: Table 2.
- **MCP-Bench, Wang et al., arXiv 2025** — https://arxiv.org/abs/2508.20453, 200. Focus: Table 3.
- **BFCL, Patil et al., ICML 2025** — https://proceedings.mlr.press/v267/patil25a.html, 200. Focus: AST scorer.
- **Agent Skills, Anthropic engineering, 2025** — https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills, 200.
- **Agent Skills overview, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview, 200.
- **Agent Skills specification, agentskills.io** — https://agentskills.io/specification, 200.
- **Build skills, OpenAI, 2026** — https://learn.chatgpt.com/docs/build-skills, 200.

### MCP specification, registry, SDKs

- **Versioning, MCP, 2026** — https://modelcontextprotocol.io/specification/versioning, 200.
- **Changelog 2026-07-28, MCP, 2026** — https://modelcontextprotocol.io/specification/2026-07-28/changelog, 200. Focus: major changes 1 to 9.
- **Deprecated features, MCP, 2026** — https://modelcontextprotocol.io/specification/2026-07-28/deprecated, 200.
- **Changelog 2025-11-25, MCP, 2025** — https://modelcontextprotocol.io/specification/2025-11-25/changelog, 200.
- **Streamable HTTP, MCP, 2026** — https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http, 200.
- **Tools, MCP, 2026** — https://modelcontextprotocol.io/specification/2026-07-28/server/tools, 200.
- **Authorization, MCP, 2026** — https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/index, 200.
- **Security Best Practices, MCP, 2026** — https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices, 200.
- **schema.ts at tag 2026-07-28, MCP** — https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/2026-07-28/schema/2026-07-28/schema.ts, 200.
- **The 2026-07-28 Specification, MCP blog, 2026** — https://blog.modelcontextprotocol.io/posts/2026-07-28/, 200.
- **Beta SDKs for 2026-07-28, MCP blog, 2026** — https://blog.modelcontextprotocol.io/posts/sdk-betas-2026-07-28/, 200.
- **Introducing the MCP Registry, MCP blog, 2025** — https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/, 200.
- **Registry about, MCP, 2026** — https://modelcontextprotocol.io/registry/about, 200.
- **MCP joins the Agentic AI Foundation, MCP blog, 2025** — https://blog.modelcontextprotocol.io/posts/2025-12-09-mcp-joins-agentic-ai-foundation/, 200.

### MCP security

- **Tool poisoning attacks, Invariant Labs, 2025** — https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks, 200. Contains an attack example written as instructions.
- **WhatsApp MCP exploited, Invariant Labs, 2025** — https://invariantlabs.ai/blog/whatsapp-mcp-exploited, 200.
- **GitHub MCP vulnerability, Invariant Labs, 2025** — https://invariantlabs.ai/blog/mcp-github-vulnerability, 200.
- **MCP Inspector RCE, Oligo Security, 2025** — https://www.oligo.security/blog/critical-rce-vulnerability-in-anthropic-mcp-inspector-cve-2025-49596, 200.
- **mcp-remote advisory, JFrog, 2025** — https://research.jfrog.com/vulnerabilities/mcp-remote-command-injection-rce-jfsa-2025-001290844/, 200.
- **EscapeRoute, Cymulate, 2025** — https://cymulate.com/blog/cve-2025-53109-53110-escaperoute-anthropic/, 200.
- **MCP git server flaws, The Hacker News, 2026** — https://thehackernews.com/2026/01/three-flaws-in-anthropic-mcp-git-server.html, 200. Secondary. The Cyata page redirects away.
- **Asana MCP exposure, UpGuard** — https://www.upguard.com/blog/asana-discloses-data-exposure-bug-in-mcp-server, 200.
- **Supabase MCP leak, General Analysis, 2025** — https://www.generalanalysis.com/blog/supabase-mcp-blog, 200.
- **postmark-mcp, Postmark, 2025** — https://postmarkapp.com/blog/information-regarding-malicious-postmark-mcp-package, 200.
- **postmark-mcp analysis, Snyk, 2025** — https://snyk.io/blog/malicious-mcp-server-on-npm-postmark-mcp-harvests-emails/, 200.
- **Breaking MCP server hosting, GitGuardian, 2025** — https://blog.gitguardian.com/breaking-mcp-server-hosting/, 200.
- **Rethinking MCP Security, Chen et al., arXiv 2026** — https://arxiv.org/abs/2607.11086, 200. Focus: Tables 5 to 7.
- **MCP at First Glance, Hasan et al., arXiv 2025** — https://arxiv.org/abs/2506.13538, 200. Focus: Table 7.
- **Remote MCP authentication, Zhou et al., arXiv 2026** — https://arxiv.org/abs/2605.22333, 200. Abstract only: 40.55% of 7,973 servers exposed tools without authentication.

### Sandboxes

- **Firecracker, Agache et al., NSDI 2020** — https://www.usenix.org/system/files/nsdi20-paper-agache.pdf, 200. Focus: sections 3.4.1, 5.1, 5.2.
- **Firecracker SPECIFICATION.md v1.17.0, AWS** — https://raw.githubusercontent.com/firecracker-microvm/firecracker/v1.17.0/SPECIFICATION.md, 200. Some figures are marked "integration test pending".
- **gVisor architecture, Google** — https://gvisor.dev/docs/architecture_guide/intro/, 200.
- **gVisor platforms, Google** — https://gvisor.dev/docs/architecture_guide/platforms/, 200.
- **gVisor performance, Google** — https://gvisor.dev/docs/architecture_guide/performance/, 200. Old ptrace data.
- **Seccomp BPF, Linux kernel docs** — https://docs.kernel.org/userspace-api/seccomp_filter.html, 200.
- **Seccomp profiles, Docker** — https://docs.docker.com/engine/security/seccomp/, 200.
- **CVE-2019-5736 disclosure, oss-security, 2019** — https://seclists.org/oss-sec/2019/q1/119, 200.
- **runc GHSA-xr7r-f8xq-vfvv, 2024** — https://github.com/opencontainers/runc/security/advisories/GHSA-xr7r-f8xq-vfvv, 200.
- **Claude Code sandboxing, Anthropic, 2025** — https://www.anthropic.com/engineering/claude-code-sandboxing, 200.
- **Codex sandboxing, OpenAI, 2026** — https://learn.chatgpt.com/docs/sandboxing, 200.
- **Docker Sandboxes, Docker, 2026** — https://docs.docker.com/ai/sandboxes/, 200.
- **Meet Containerization, Apple WWDC25** — https://developer.apple.com/videos/play/wwdc2025/346/, 200. "Sub-second" claim, no conditions.
- **Sandbox benchmarks, ComputeSDK, 2026** — https://github.com/computesdk/benchmarks, 200. The owner sells a multi-provider SDK.
- **Claude Code sandbox bypass, SecurityWeek, 2026** — https://www.securityweek.com/anthropic-silently-patches-claude-code-sandbox-bypass/, 200 with a browser user agent.

## 9. Tools and versions to pin

| Tool | Current version | Release date | Source | Notes on breaking changes |
|---|---|---|---|---|
| MCP specification | 2026-07-28 | 2026-07-28 | versioning page, git tag | No handshake or sessions. Error codes renumbered. |
| `mcp`, Python | 2.2.0 | 2026-09-07 | PyPI | v2 renames FastMCP to `MCPServer`. v1 line is 1.30.0. |
| `@modelcontextprotocol/server`, `/client` | 2.0.0 | 2026-07-27 | npm | Split from `@modelcontextprotocol/sdk`. Node 20+. |
| `@modelcontextprotocol/sdk` | 1.30.0 | 2026-07-27 | npm | v1 line |
| `fastmcp` | 4.0.4 | 2026-09-16 | PyPI | 4.0 changes not checked |
| `anthropic`, Python | 1.6.0 | 2026-09-15 | PyPI | not checked |
| `@anthropic-ai/sdk` | 0.126.0 | 2026-09-15 | npm | not checked |
| `openai`, Python / npm | 3.14.1 / 7.17.0 | 2026-09-15 / 2026-09-16 | PyPI, npm | not checked |
| `google-genai` | 2.24.0 | 2026-09-16 | PyPI | Interactions API in docs |
| `claude-agent-sdk`, Python | 0.2.154 | 2026-09-17 | PyPI | frequent releases |
| `@anthropic-ai/sandbox-runtime` | 0.0.76 | 2026-09-10 | npm | pre-1.0 |
| Firecracker | v1.17.0 | 2026-09-10 | GitHub | Linux with KVM only |
| gVisor | release-20260914.0 | 2026-09-16 | GitHub | ptrace unsupported |
| Docker Engine | docker-v29.8.1 | 2026-09-15 | GitHub | seccomp profile moved to `moby/profiles` |
| Apple `container` | 1.4.1 | 2026-09-09 | GitHub | macOS 26, Apple Silicon |
| Codex CLI | rust-v0.154.0 | 2026-09-09 | GitHub | Landlock is a legacy fallback |

## 10. Open questions and disagreements

- **Tool count thresholds.** Anthropic says 30 to 50, OpenAI fewer than 20, Google 10 to 20. None cites an evaluation.
- **Code mode savings.** Each figure counts something different. Anthropic 98.7% is an example. Cloudflare 99.9% counts definitions with tiktoken. AIMultiple measured 78.5% fewer input tokens on GPT-4.1, with higher latency. Felendler et al. found lower quality on some multi-server and iterative tasks.
- **Anthropic idle containers.** "Reclaimed" on one page, "checkpointed" on another.
- **RAG-MCP judge.** DeepSeek-v3 in one section, a Llama judge in another.
- **Firecracker boot.** Under 125 ms in the abstract, 150 ms with a production kernel, p99 146 to 153 ms under concurrency.
- **Sandbox start.** Vendors claim about 80 ms for E2B from a snapshot and under 90 ms for Daytona. ComputeSDK measured median time to first command with 100 parallel starts on 2026-09-16: Daytona 341 ms, Vercel 510 ms, Modal 957 ms, E2B 1,148 ms, Cloudflare 5,093 ms. That test includes network time.
- **TS SDK v2 format.** The beta blog says ESM-only. The v2.0.0 upgrade guide says it also ships CommonJS.
- **SOCKS5 sandbox bypass fix.** Anthropic, via SecurityWeek, says Claude Code 2.1.88. The researcher says 2.1.90.

## 11. Things I could NOT verify

- **Anthropic tool search accuracy, 49% to 74% and 79.5% to 88.1%.** No eval, tool count, or scorer named. Reproduce with Lab 5.
- **Models behind the 37% saving and the 72% to 90% examples gain.** Not stated.
- **The "346 tokens" value in the plan.** An archived page copy would show its model.
- **The evaluation behind each vendor's tool count threshold.** None cited.
- **Numbers inside figures.** Cloudflare, Felendler, LiveMCPBench Figure 7, RAG-MCP Figure 3. Needs manual reading.
- **Current gVisor Systrap overhead.** Only old ptrace data exists. Run on a current Linux host.
- **Docker's "around 44" blocked syscalls.** Not reconciled with the vendored profile. Count it per architecture.
- **JFrog blog, Koi Security post, Cyata post.** Bot challenge or redirects. Facts come from the JFrog advisory, Postmark, Snyk, NVD, and The Hacker News.
- **Asana incident year.** Inferred as 2025.
- **Registry general availability.** No announcement found.
- **Python `mcp` 2.2.0 dual-version behaviour.** From the SDK blog only. Lab 9 must run it.
- **Docker Sandboxes hypervisor and Apple `container` start time.** Not named, or vendor claim only.
- **E2B "~150ms".** Not in E2B docs.
- **Anthropic's 84% fewer permission prompts.** No method.
- **arXiv 2605.22333.** Abstract only.

## 12. Notes for the course generator

- Teach MCP as 2026-07-28. Most web samples still show `initialize` and `Mcp-Session-Id`. Show them only for backward compatibility.
- Sampling, Roots, and Dynamic Client Registration are deprecated, not removed.
- Re-check before generating: hidden tool prompt tokens, strict limits, code execution version and price, OpenAI `tool_search` models, SDK versions, Firecracker and gVisor tags.
- Label each vendor saving with what it counted. Do not compare 98.7%, 99.9%, and 85% as one measure.
- Present the 30 to 50, 20, and 10 to 20 thresholds as vendor advice, not measurements.
- On an Apple Silicon Mac, Docker runs in a Linux VM. Escape probes test that VM, not macOS. gVisor and Firecracker need a Linux KVM host.
- Keep authorization at audience-check level. Link Module 8 and Module 16.
- Invariant Labs pages and some papers contain attack payloads written as instructions. Quote them only inside code blocks.
- Fastest to go stale: SDK versions, tool prompt tokens, sandbox start times, registry status, CVE fixed versions.

Summary: most of this module is new, a breaking MCP revision is at its centre, and most vendor savings figures lack conditions.
