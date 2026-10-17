# Module 06 — The tool layer and MCP internals

Research date: 2026-09-23. This is a refresh of the dossier dated 2026-09-17. Status: research dossier, not course material. Section 13, "Refresh log 2026-09-23", lists every change and every correction to the 2026-09-17 text.

Module question: **What does the model actually see when you give it a tool, and what does MCP let a server change or claim without your consent?**

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-23: `scratchpad/reports/research_tools-mcp_tools.md` and `scratchpad/reports/research_tools-mcp_mcp.md`. Their saved sources and prototype labs are in `scratchpad/research_tools-mcp/tools/` and `scratchpad/research_tools-mcp/mcp/`. The Module 6 fix list is in `scratchpad/reports/curriculum_audit.md`, section 4, "Module 6, tool layer and MCP: grade B". Refresh notes, the anchor list and URL checks are in `scratchpad/m06_refresh/`.
- **Scratchpad path.** `scratchpad/` means `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/2ba7cd59-bd20-4d0a-a9d5-98cef39f2fb7/scratchpad/`.
- **Labels.** Every claim is **verified**, **inferred** or **not checked**. A verified claim names its source and its line, table or section. "Verified by run" means a script ran on the research laptop on 2026-09-23. An inferred claim names its basis and the check that would confirm it.
- **Anchor numbers re-checked.** The dossier author grepped the evidence for each concept in section 4 again on 2026-09-23. The search used `grep -c -F` over the saved source or run file. 52 anchor strings were checked. 52 were found. One quote in `basic.md` and one in `tools.md` are split across a line break, so a shorter part of each was grepped. Files: `scratchpad/m06_refresh/anchors_final.tsv` and `anchors_final.txt`.
- **Run outputs that were not saved.** Most prototype runs printed to the terminal only. Only four kinds of output exist as files: the three rendered chat templates in `tools/render/*.txt` and the HTTP status log `mcp/lab/http.log`. Every other run number in this dossier comes from the report text and could not be re-grepped. Each such number says "run output not saved". This dossier did not re-run any lab.
- **Machine for every run.** Apple M4 Pro, macOS 26.6, Python 3.12, uv 0.12.8. MCP runs used `mcp` 2.2.0. Template renders used `transformers` 5.17.0.
- **Links.** 67 URLs cited in this dossier were fetched on 2026-09-23 with a browser user agent. All 67 returned HTTP 200 after redirects. Three redirected. File: `scratchpad/m06_refresh/url_status.txt`.

---

## 1. What this module is for

A tool definition is text that the model reads on every request. MCP, the Model Context Protocol, is an open JSON-RPC protocol that carries tool definitions and tool calls between an AI application and a tool server. This module teaches four things a senior engineer often gets wrong:

1. **Where the tool text goes.** The provider or the chat template decides where tools sit in the prompt, what they cost, and which parts of the schema the model sees.
2. **How the model chooses.** Choice accuracy falls as the tool list grows. A search step recovers part of the loss, not all of it.
3. **How the call comes back.** Strict mode checks shape, not meaning. A self-hosted server turns generated text into calls with a parser that can drop every call in a batch.
4. **What MCP lets a server do.** A server can change its tools after approval, describe itself falsely, accept a token meant for another service, and render its own HTML in the host.

The learner builds a customer-support agent. It calls tools such as order lookup and refund on every turn. Every concept below appears in that agent.

## 2. Scope

### In scope

- What the model sees: tool rendering in hosted APIs and in open-weight chat templates, fixed tool-prompt overhead, schema loss in templates.
- Mid-conversation tool changes on Anthropic, as an extension of built Module 2, 2.3.
- Strict tool inputs: what they guarantee and what they do not. Only the limits that a lab uses.
- Tool count and selection accuracy. Shortlists, deferred loading and tool search. Agent Skills as the same loading pattern.
- Tool descriptions and error text as part of the tool interface. Only what built Module 2, 2.4 does not cover.
- Code as the tool call: programmatic tool calling and the code execution tool as a tool.
- Tool calling in self-hosted open-weight models: chat templates and server-side parsers.
- MCP 2026-07-28: stateless requests, `server/discover`, Multi Round-Trip Requests, transports, tools and structured output.
- MCP trust boundaries at mechanism level: annotations, changing definitions, the token audience check, MCP Apps, and scanner reliability.

### Out of scope, and where it lives instead

| Topic | Where it lives |
|---|---|
| Tokenizers, prefix caching, `cache_control` | Module 1, 1.1, 3.2 and 3.3 |
| Constrained decoding and the format tax | Module 1, 2.5 |
| Cost of editing the tool list, `allowed_tools`, mask and reject | Built Module 2, 2.3 |
| Result size, handles, `response_format`, the 25,000-token Claude Code cap | Built Module 2, 2.4 |
| Clearing tool results, compaction | Module 1, 2.6, then built Module 2, Phase 3 |
| Sandboxes: namespaces, seccomp, gVisor, Firecracker, Seatbelt, bubblewrap, start times, bypass CVEs | Module 7, harness engineering. Moved there by audit fix 5 |
| Agent loop, permission prompts, hooks | Module 7 |
| OAuth flows, token exchange, agent identity, A2A | Module 8 |
| Prompt-injection defences, red teaming, approval bound to a name | Module 16 |
| Tool-call evals | Modules 11 and 12 |
| Tracing tool calls | Module 15 |

### Overlap with built modules

Headings were read with `grep '^## '` over `context-engineering/*.md` on 2026-09-23, as audit rule 5 asks. The Module 2 coverage file is `_curriculum/module-02-coverage.md`.

| Topic | Where it is already taught | What this module adds |
|---|---|---|
| Tools come first in the cache prefix. Editing the list costs a rewrite | Module 2, 2.3 "Restrict the tools, never edit the list", `context-engineering-phase-02-cost.md` line 278 | Open-weight templates put tools elsewhere, see 4.1. Anthropic mid-conversation tool changes, see 4.2. Link 2.3. Do not re-teach the cost. |
| `allowed_tools`, `tool_choice` as a cache-safe restriction | Module 2, 2.3 | Nothing. Link. |
| Deferred loading keeps the prefix fixed | Module 2, 2.3, "How production agents do it" | The search step can miss, and the strict grammar still holds every tool, see 4.6. |
| Handles, `response_format` 206 and 72 tokens, the 25,000-token cap | Module 2, 2.4 "Handles, not payloads", line 351 | MCP handles carry state across stateless requests, see 4.10. Link 2.4 for cost. |
| Compact JSON in tool results | Module 1, 1.1 | Nothing. Link. |
| Schema enforcement by the decoder | Module 1, 2.5 | What strict mode does not check, see 4.3. MCP `structuredContent` is not constrained decoding, see 4.10. |
| Cache side channels | Module 1, 6.2 | Nothing. |

Module 2, 2.3 says "Anthropic has no `allowed_tools`". That is still true. Its step 3, "On Anthropic, keep the list and reject forbidden calls in the harness", is now incomplete for seven Claude models. Section 4.2 adds the new option. This dossier does not edit Module 2.

## 3. What changed recently

History lives here and in References, one line each. Section 4 teaches only the current state.

| Change | Date | Source | Why it matters |
|---|---|---|---|
| Tool poisoning and rug pull named | 2025-04-01 | Invariant Labs blog | Attack vocabulary used in 4.13 |
| Cursor approved-config swap, CVE-2025-54136, fixed in 1.3 | 2025-08-02 | NVD | A real case of approval not bound to content |
| MCP Registry preview | 2025-09-08 | MCP blog | Still "preview" on 2026-09-23 |
| "Writing effective tools for agents" | 2025-09-11 | Anthropic engineering | Slack and Asana tool rewrites, vendor tasks |
| Agent Skills, then open standard | 2025-10-16, 2025-12-18 | Anthropic engineering | Three loading levels |
| Tool search, programmatic tool calling, tool use examples | Beta 2025-11-24 | Anthropic engineering | Deferred loading |
| MCP 2025-11-25 | 2025-11-25 | MCP changelog | Previous revision. Input validation errors became tool execution errors, SEP-1303 |
| MCP moves to the Agentic AI Foundation | 2025-12-09 | MCP blog | Linux Foundation governance |
| MCP Apps spec marked Stable | 2026-01-26 | `ext-apps` spec file | `ui://` resources, see 4.15 |
| Strict tool use leaves beta | 2026-01-29 | Anthropic release notes | Not re-checked on 2026-09-23 |
| LiveMCPBench v2 | 2026-02-26 | arXiv 2508.01780v2 | Figure 7 numbers now in Appendix I |
| "How Many Tools Should an LLM Agent See?" | 2026-05, v1 | arXiv 2605.24660 | Shortlist length is a design variable, see 4.5 |
| "Scaling Enterprise Agent Routing" | 2026-06-16 | arXiv 2606.17519 | A current tool-count curve with an oracle split, see 4.4 |
| Mid-conversation tool changes, beta header `mid-conversation-tool-changes-2026-07-01` | header date 2026-07-01 | Anthropic docs | Change the offered tools without editing `tools`, see 4.2 |
| MCP scanner reliability study | 2026-07-13 | arXiv 2607.11086 | See 4.16 |
| TypeScript MCP SDK 2.0.0, split packages | 2026-07-27 | npm | New import paths |
| **MCP 2026-07-28** | 2026-07-28 | MCP changelog | Stateless core. One line per change is in section 8, "MCP changelog lines" |
| Python `mcp` 2.2.0 and 1.30.0 | 2026-09-07 | PyPI | Current pins |
| `ext-apps` v2.0.0 | 2026-09-08 | GitHub, npm | Moves to SDK 2 packages. "The MCP Apps wire protocol is unchanged" |
| Inline tools, beta header `inline-tools-2026-09-15` | header date 2026-09-15 | Anthropic docs | Define a tool by value mid-conversation, see 4.2 |
| Opus 5.5 rejects forced `tool_choice` | page read 2026-09-23 | Anthropic `define-tools` | Forcing a tool is not portable, see 4.3 |
| vLLM v0.30.0 | 2026-09-22 | GitHub, PyPI | `strict` opts `auto` into constrained tool calls, see 4.9 |

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept starts with its single best piece of evidence and its conditions. Supporting facts follow.

### 4.1 A tool definition is prompt text, and the provider or chat template decides where it sits, what it costs, and which parts of the schema the model sees

A learner often believes that tools always come first in the prompt and that the model sees the JSON Schema they sent. Both are false for open-weight templates.

- **Best evidence, verified by run.** The same two tools, `get_order` and `refund_order`, were rendered through three chat templates with `transformers` 5.17.0. Tokenizers only, no model weights. Script `tools/render/render.py`, 2026-09-23.

| Model and template, HF revision | Where tools go | Overhead for 2 small tools | Schema text the model sees |
|---|---|---|---|
| `Qwen/Qwen3-0.6B`, sha c1899de289a0 | System turn, after your system prompt | 217 tokens | Raw JSON, one line per tool |
| `openai/gpt-oss-20b`, sha 6cee5e81ee83 | Developer turn, after your instructions | 83 tokens | TypeScript types, not JSON Schema |
| `unsloth/Llama-3.2-1B-Instruct`, sha 5a8abab4a5d6, a mirror of Meta's template | First user turn | 250 tokens | JSON with 4-space indent |

  - The placement is verified in the saved renders: `render/Qwen__Qwen3-0.6B.txt` puts `<tools>` after "You are a support agent." `render/openai__gpt-oss-20b.txt` puts `namespace functions` inside the developer message. `render/unsloth__Llama-3.2-1B-Instruct.txt` puts "Given the following functions" inside the user turn.
  - The token counts are from the report. Run output not saved.
  - Each token count uses that model's own tokenizer. The messages were one system line and one user line.
- **Schema loss, verified by run, run output not saved.** `render/lossy.py` sent one tool with `pattern`, `minimum`, `maximum`, `maxItems`, an `enum`, a `default` and a nested array of objects. The gpt-oss template dropped `pattern`, `minimum`, `maximum`, `maxItems` and the nested item fields. It rendered the array as `items?: any[]`. The Qwen3 and Llama 3.2 templates kept all keywords. Whether OpenAI's own `openai-harmony` renderer does the same: not checked.
- **The date changes the prefix, verified.** The gpt-oss render contains "Current date: 2026-09-23" before the tools. The Llama render contains "Today Date: 23 Sep 2026". Source: the two saved render files. **Inferred:** a self-hosted prefix cache misses on the first request each day for these two templates. Check: render on two dates, serve with vLLM prefix caching, and read the cache-hit metric.
- **Hosted APIs, verified.** Anthropic: "the API constructs a special system prompt from the tool definitions, tool configuration, and any user-specified system prompt". Source: `define-tools`, saved `tools/a_define.md`. OpenAI: functions "are injected into the system message in a syntax the model has been trained on". Source: function calling guide. Google's function calling page does not say how tools are rendered. Verified by absence in `tools/g_fc2.md`.
- **Fixed overhead on Anthropic, verified.** The tool-use system prompt "assumes at least 1 tool". Claude Opus 5.5: 286 tokens for `auto` and `none`, with no row for `any` or `tool`. Opus 5: 286 and 406. Opus 4.8: 290 and 410. Opus 4.7: 675 and 804. Sonnet 5: 354 and 474. Haiku 4.5: 496 and 588. Source: tool use overview, "Pricing", `tools/a_overview.md` lines 865 to 877. OpenAI and Google publish no number. Not checked by measurement.
- **Link, do not re-teach.** The cost of editing the tool list is built Module 2, 2.3.

Summary: the rendered text, not your JSON, is the tool. Read it for any model you serve yourself.

### 4.2 On seven Claude models, you can change which tools the model may call without editing `tools`, so the cache prefix survives. On other models, Module 2, 2.3 still applies

This concept **extends** built Module 2, 2.3. Module 2 teaches that editing the tool list rewrites the cache, and that Anthropic has no `allowed_tools`. Anthropic now offers a beta that changes the offered tools inside the message history.

- **Best evidence, verified.** Anthropic, "Mid-conversation system messages and tool changes": "declare the full tool set in `tools` up front, then use `tool_addition` and `tool_removal` blocks". "The `tools` array itself never changes, so the cached prefix stays intact." Source: `platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages`, section "Mid-conversation tool changes", saved `tools/a_midconv.md` line 27.
- **Conditions, verified.** Same page, lines 18 and 20.
  - Beta header: `mid-conversation-tool-changes-2026-07-01`.
  - Models: Claude Fable 5.1, Claude Mythos 5.1, Claude Fable 5, Claude Mythos 5, Claude Opus 5.5, Claude Opus 4.8 and Claude Opus 5.
  - Not available on Claude Sonnet 5. The page says to use the top-level `system` field there.
  - Platforms: Claude API, Amazon Bedrock and Google Cloud.
- **How it works, verified.** Same page, lines 29 and 31.
  - `tool_addition` and `tool_removal` are content blocks in a `role: "system"` message.
  - Each block references a tool declared in `tools` with `tool_reference`. MCP connector tools use `mcp_tool_reference` or `mcp_toolset_reference`.
  - A name that is not in `tools` returns 400 with error code `tool_reference_unresolved`.
  - A tool declared with `defer_loading: true` stays withheld until a `tool_addition` block offers it.
- **Inline tools, verified.** Header `inline-tools-2026-09-15` lets a `tool_addition` block carry a full tool definition. It is available on the Claude API. It replaces the first header. Same page, lines 20 and 453.
  - Limits: the definitions sent after the first user message may total at most 4 MB, 4,194,304 bytes. The rendered tool text may be at most 4 MB. Above a limit, the API returns 400 with `available_tools_limit_exceeded`. Lines 1022 to 1027.
  - A request whose `tools` has no non-deferred tool pays "one full cache miss" on the first definition by value. Line 1018.
- **Placement rules, verified.** A system message with tool blocks must follow a `user` turn or an assistant turn that ends in a server tool result. It cannot sit between a `tool_use` block and its `tool_result`. It is not accepted right after a paused turn. Same page, "Limitations".
- **What is not known, not checked.**
  - The cost of a `tool_removal` on a real bill. No measurement exists. A live run with usage fields needs an API key.
  - What happens when the model still calls a withdrawn tool. The page does not say.
  - Whether the "orphan call" problem from Module 2, 2.3 applies after a `tool_removal`.
- **Teaching consequence, inferred.** Module 2, 2.3, step 3 gains an option. On the seven models above, withdraw the tool with `tool_removal` and keep rejecting calls to it in the harness. On Sonnet 5, keep mask and reject.

Summary: on supported Claude models, the tool list can change in the history instead of the prefix. The cost of that change is not yet measured.

### 4.3 Strict mode guarantees that arguments parse and match the declared types. It does not check that the values are right, and on Anthropic it does not enforce numeric limits

A learner reads "strict" and assumes the call is correct. `refund_order(order_id="ORD-2", amount=40)` passes strict mode when the user asked about ORD-1.

- **Best evidence, verified.** Anthropic, structured outputs, "Invalid outputs": structured outputs "don't guarantee the capitalization of string `enum` and `const` values". `minimum`, `maximum`, `minLength` and `maxLength` are "Not supported". The SDK moves them into the description and validates client-side. Source: `tools/a_structured.md`, lines 1306 and 1409 to 1417.
- **The other providers say it too, verified.**
  - Google: "Implement robust error handling for schema-compliant but semantically incorrect outputs." Structured output page, "Best practices", `tools/g_structured.txt`.
  - OpenAI: "Structured Outputs can still contain mistakes." Structured outputs guide, "Handling mistakes", `tools/o_structured.txt`.
- **Limits a lab uses, verified.** Anthropic allows 20 strict tools, 24 optional parameters and 16 union-type parameters per request, across all strict schemas. Larger schemas return 400 "Schema is too complex for compilation". Source: `tools/a_structured.md` lines 2976 to 2986. OpenAI needs `additionalProperties: false` and every field in `required`. Other per-provider limits are reference material. Lab 2 carries them.
- **Failure cases, verified.** On Anthropic, `stop_reason: "refusal"` and `"max_tokens"` can return output that does not match the schema. Source: structured outputs page.
- **Forcing a tool is not portable, verified.** On Claude Opus 5.5, Fable 5.1 and Mythos 5.1, `tool_choice` `any` and `tool` "return a 400 error". The page recommends `auto` with strict tool use. Source: `define-tools`, "Forcing tool use", `tools/a_define.md` line 562. On other Claude models, `any` and `tool` make "the API prefill the assistant message". So forced choice and strict mode are two different guarantees.
- **Self-hosted strictness, verified.** In vLLM 0.30.0, `tool_choice="auto"` is constrained "Only when `strict: true` is set on at least one tool". Named and `required` modes are always constrained. Source: vLLM docs at tag v0.30.0, `tools/vllm_tool_calling.md` line 118.

Summary: strict mode checks shape. The harness still checks meaning, ranges and case.

### 4.4 Selection accuracy falls as tools are added, and part of the loss remains even when retrieval is perfect

A learner believes that a good tool search removes the tool-count problem. A 2026 production study shows a loss that remains with the right tools always in the list.

- **Best evidence, verified.** Gillespie and Perry, "Scaling Enterprise Agent Routing", arXiv 2606.17519v1, 2026-06-16, Superhuman Inc., preprint. Source: `tools/enterprise.txt` lines 262 and 282.
  - Conditions: single-step routing on a production catalog of 110 agents and 584 tools. Implicit, under-specified queries. Metric: multi-label routing F1. Three folds at each non-endpoint scale point. Models: GPT-5.1 and GPT-5.4 through the Responses API, and Claude Sonnet 4.5. Sonnet 4.5 ran on fold 0 only.
  - GPT-5.4 flat routing "drops from 58.2% to 42.1%" as the catalog grows from 51 to 584 tools.
  - An oracle shortlist "drops from 79.0% to 68.8%", Figure 1, GPT-5.4. The oracle holds "all dynamically-valid tools plus random distractors to fill 20 slots". The authors call this 10-point loss the confusion gap.
  - The paper says part of that gap comes from larger valid sets, "from 1.6 to 3.2 tools per query at scale". Precision still fell 8 points, which the authors read as real confusion.
  - Embedding shortlisting with `text-embedding-3-large` and k=20 "recovers +10–11pp F1 at full scale across all three models". Line 26.
  - "Sonnet starts higher (66.3% at 51 tools) but degrades faster (−20pp vs. −16pp for GPT-5.4)." Line 311.
- **Supporting, verified.** LiveMCPBench v2, Mo et al., arXiv 2508.01780v2, 2026-02-26, preprint. 95 tasks, 70 servers, 527 tools. Retrieval: Qwen3-Embedding-0.6B, top 5. Judge: DeepSeek-V3. Human annotators labelled the failed trajectories of Claude Opus 4 and Claude Sonnet 4. "Retrieve Error (50.00%)". Source: Appendix I, `tools/livemcp.txt` line 1971. Appendix I gives the numbers behind Figure 7. The abstract says "retrieval errors account for nearly half of all failures", line 327. **Inferred:** the denominator is 60 failed trajectories, because 8/60, 30/60 and 11/60 give the four shares. Check: the appendix figures.
- **Weak evidence, verified, use only with these caveats.** RAG-MCP, Gan and Sun, arXiv 2505.03275v1, preprint, Table 1. MCPBench web-search subset, qwen-max-0125, 20 trials. All descriptions in the prompt: 13.62% accuracy at 2,133.84 prompt tokens. Retrieval first: 43.13% at 1,084.00 tokens. Source: `tools/ragmcp.txt`.
  - The paper names two judges: "Deepseek-v3" and "a Llama-based verifier".
  - Section 4.2 calls a baseline successful if it gives "more than 10 correct answers out of those 20". Table 1 reports percentages. The paper does not explain how the two fit.
  - The pool size for Table 1 is not stated. **Inferred:** 2,133.84 prompt tokens cannot hold thousands of server descriptions. Check: author code.
  - **Figure 3 is not a curve.** Its caption says it "illustrates per-trial success", with "yellow" for success and "purple" for failure. Source: `tools/ragmcp.txt` line 576. It shows the retrieval method, titled "MCP-RAG Success Heatmap", with one binary cell per pool size and key position. The report's pixel count found 159 of 280 cells successful, and 2 of 50 at pool sizes of 2,111 and above. Verified for the count by the report's script `tools/fig3_cells.py`, run output not saved. The paper's text claim of "success rates above 90%" below position 30 is not supported by that count. Inferred.
- **Vendor advice, verified quotes, no evaluation cited.** Anthropic: selection "degrades once you exceed 30–50 available tools", `tools/a_toolsearch.md` line 12. OpenAI: "Aim for fewer than 20 functions available at the start of a turn", "a soft suggestion". Google: "Keep active set to 10-20 tools maximum." Present these as advice, not measurements.

Summary: retrieval recovers part of the tool-count loss. The rest is confusion between similar tools.

### 4.5 A shorter candidate list raises choice accuracy even when the right tool is present, until the list drops the right tool

A learner treats list length only as a token cost. It also changes which tool the model picks.

- **Best evidence, verified.** "How Many Tools Should an LLM Agent See?", arXiv 2605.24660v1, preprint, Table 1. Source: `tools/howmany.txt` lines 258 to 260 and 1948 to 1951.
  - Conditions: BFCL with 370 tools, 120 test queries, 3 seeds, temperature 0. Claude Sonnet 4.6 was forced to pick one tool.
  - When the gold tool was in the list, Sonnet chose it 93.1% of the time with about 2.2 tools shown by a learned policy. With a fixed 5 tools, it chose it 87.1% of the time.
  - With 1 tool shown, choice accuracy was 100%, but the gold tool was present only 65.0% of the time.
  - On medium-difficulty queries the gap widened: "76.8% vs 60.9%".
  - The authors' organization is not stated in the text grepped. Not checked.
- **Where it fails, verified.** On ToolBench with 3,251 tools, a fixed 5 had higher total coverage, 64.7% against 61.9%. It found nothing on hard queries where the gold tool ranked 6th to 20th. Same source, line 240 onward.
- **Supporting, verified.** Gillespie and Perry found rich agent metadata helped "+1.2pp at 20, +4.2pp at 110" agents, and "<1pp" at the tool level. Source: `tools/enterprise.txt`.

Summary: list length is a design variable with two failure modes, confusion when long and a missing tool when short.

### 4.6 Deferred loading keeps the cache prefix fixed, but it adds a search step that can miss, it does not shrink the strict grammar, and on OpenAI it still shows each tool's name and description

A learner reads "85% fewer tokens" and assumes deferred loading is free.

- **Best evidence, verified.** Anthropic, tool use with prompt caching: "Deferred tools are not included in the system-prompt prefix." Found tools arrive as `tool_reference` blocks, so the prefix cache holds. The same page says "The grammar builds from the full toolset regardless of which tools are deferred". Source: `tools/a_toolcache.md`.
- **The search step, verified.** Anthropic tool search: `tool_search_tool_regex_20251119` and `tool_search_tool_bm25_20251119`. Up to 10,000 deferred tools. 5 results by default. At least one tool must be non-deferred. Search covers "tool names, descriptions, argument names, and argument descriptions". Source: tool search page, "Limits", `tools/a_toolsearch.md`. Anthropic advises search at "10 or more tools" and keeping "your 3–5 most frequently used tools non-deferred".
- **OpenAI saves less per tool, verified.** Only "gpt-5.4 and later models support `tool_search`" in the Responses API. For a deferred function, "the model still sees the function name and description, so in practice tool search is mostly deferring the parameter schema". Found tools "are injected at the end of the context window". Source: `tools/o_toolsearch.txt` line 1420 and nearby.
- **Namespace search plateaus, verified quote, numbers not checked.** Gillespie and Perry: OpenAI's namespace-based tool search "provides partial relief at moderate scale but plateaus at larger catalogs". Figure 1 caption: "Tool search helps above ∼180 tools but plateaus." The numbers in section 5.4 were not read.
- **Vendor numbers, verified quotes, conditions missing.** Anthropic's 2025-11-24 post: 58 tools used about 55K tokens. Tool search used about 8.7K against 77K, "an 85% reduction". "Opus 4 improved from 49% to 74%, and Opus 4.5 improved from 79.5% to 88.1%" on "MCP evaluations" in "Internal testing". The eval, the tool count and the scorer are not named. Vendor numbers on vendor-chosen tasks.
- **Claude Code, verified.** Tool search is on by default. "Only tool names and server instructions load at session start." Claude Code truncates each tool description and each server's instructions at 2,048 characters. Source: `tools/claudecode_mcp.md` line 1423.
- **Agent Skills use the same pattern, verified.** A skill is a folder with a `SKILL.md` file. Level 1 metadata costs "~100 tokens per Skill" and is always loaded. Level 2 is "Under 5k tokens" and loads when the skill is chosen. Level 3 loads "only when required". `name` is at most 64 characters, `description` at most 1,024. Sources: Anthropic Agent Skills overview, `tools/a_skills.md`, and the agentskills.io specification. Custom skills "do not sync across surfaces".

Summary: deferred loading moves cost from the prefix to a search step. Measure the search step's recall, as Lab 3 does.

### 4.7 A validation error must reach the model as a tool result it can read, or the model cannot repair the call

A learner returns a bad-argument error as a protocol error or as an opaque code. The model then retries blindly or stops.

- **Best evidence, verified.** MCP 2026-07-28, Tools, "Error Handling": protocol errors are JSON-RPC errors. Tool execution errors are results with `isError: true`. "Clients **SHOULD** provide tool execution errors to language models to enable self-correction." Source: `mcp/md/tools.md` line 779. The same section lists "Input validation errors", such as a date in the wrong format, under tool execution errors, line 756.
- **Vendor advice, verified quote, no measurement.** Anthropic: errors should give "specific and actionable improvements, rather than opaque error codes or tracebacks". Source: "Writing effective tools for agents", `tools/a_writing_tools.txt`.
- **Vendor numbers, verified from images only.** The same post shows held-out test-set accuracy for human-written against Claude-optimized tools: Slack 67.4% to 80.1%, Asana 79.6% to 85.7%. The numbers exist only in the figure images `tools/fig_slack.png` and `fig_asana.png`. The post names no model, task count or scorer.
- **Vendor advice, verified quote.** Anthropic `define-tools`: "Provide extremely detailed descriptions. This is by far the most important factor in tool performance." No measurement.
- **Vendor number, verified quote, conditions missing.** Tool use examples "improved accuracy from 72% to 90% on complex parameter handling", "In our own internal testing". Model and eval not named. Examples cost about 20 to 50 tokens each for simple cases. An invalid example returns 400. Source: `tools/a_define.md` lines 547 to 549.
- **Link, do not re-teach.** Result size, pagination, `response_format` and the 25,000-token Claude Code cap are built Module 2, 2.4.

Summary: error text is part of the tool interface. Lab 4 shows the mechanism with a scripted policy, not a model.

### 4.8 Code as the tool call saves tokens only when calls are many and results are large. On one or two sequential calls per turn it costs more

A learner reads "98.7% fewer tokens" and turns on code execution for every agent.

- **Best evidence, verified, vendor numbers.** Anthropic programmatic tool calling, "Token efficiency". Condition: "In Anthropic's internal evaluations on a production Claude model". The model is not named. Source: `tools/a_ptc.md` lines 1437 to 1441.
  - "On a 75-tool project-management agent benchmark, enabling programmatic tool calling reduced billed input tokens by roughly 38% with no change in task accuracy." The benchmark is internal and not published.
  - "On τ²-bench ..., where each turn makes one or two sequential tool calls, programmatic tool calling left scores unchanged and cost roughly 8% more. Sequential single-call workflows do not benefit."
  - Production traffic with 10 to 49 tools: "typical token savings of 20% to 40%".
- **Each vendor figure counts something different, verified quotes.**
  - Anthropic "Code execution with MCP": "from 150,000 tokens to 2,000 tokens". No method. Inferred to be an illustration.
  - Cloudflare Code Mode MCP server: about 1,000 tokens for two tools over more than 2,500 endpoints. "An equivalent MCP server without Code Mode would consume 1.17 million tokens". Counted with tiktoken. Definition tokens only.
  - Anthropic advanced tool use post: "43,588 to 27,297 tokens, a 37% reduction". Model not named.
- **Counter-evidence, verified quote, numbers in figures only.** Felendler et al., arXiv 2602.15945. MCP-Bench, GPT-4o and GPT-4.1 models. Quality "comparable to those of the MCP for most configurations". Tasks "dominated by open-ended textual synthesis ... occasionally benefit from the multi-turn interaction pattern". The numbers in Figures 4 to 10 were not read.
- **The code execution tool as a tool, verified.** Source: code execution tool page, `tools/a_codeexec.md`.
  - Current version `code_execution_20260521`. It is the same runtime as `code_execution_20260120`. Its description tells Claude about the "90-second wall-clock limit on each Python cell". Line 52.
  - Container: 5 GiB RAM, 5 GiB disk, 1 CPU, no internet. Lines 1106 to 1107.
  - Pricing: 1,550 free hours per organization per month, then $0.05 per hour per container. Lines 1474 to 1475. Free with `web_search_20260209` or `web_fetch_20260209` or later.
  - Idle containers: the two Anthropic pages still disagree. The code execution page says "After about 5 minutes of inactivity a container is checkpointed", restorable within 30 days, line 1138. The programmatic tool calling page says "Idle containers are currently reclaimed after about 5 minutes", `tools/a_ptc.md` lines 460 and 1494.
- **Programmatic calling limits, verified.** Needs `code_execution_20260120` or later and `allowed_callers`. Incompatible with `strict: true`, forced `tool_choice`, `disable_parallel_tool_use: true`, MCP connector tools, computer-use and browser-use toolsets, and recursive `$ref` schemas. Haiku 4.5 does not support it. Not on Bedrock. `allowed_callers` "is not a hard API-level block on direct invocation". "Do not rely on `allowed_callers` as a security boundary." Source: `tools/a_ptc.md` line 417.
- **Out of scope here.** The sandbox under the container is Module 7.

Summary: code mode pays when many calls return large results. It loses on short sequential chains.

### 4.9 A self-hosted tool call is text until a parser accepts it, and one malformed call can erase every call in the batch

A learner assumes a self-hosted server returns tool calls the way a hosted API does. The server extracts them from generated text.

- **Best evidence, verified in source at tag.** vLLM `vllm/tool_parsers/hermes_tool_parser.py` at `v0.30.0`, released 2026-09-22. Saved as `tools/hermes_parser.py`. Lines 87 to 93 call `json.loads` on every regex match inside one `try`. On any exception, lines 116 to 120 return `tools_called=False, tool_calls=[], content=model_output`. So one bad call in a parallel batch loses all of them, and the raw text goes to the client as content. The parser does not check the tool name or the argument types.
- **Replica run, verified by run, run output not saved.** `tools/render/parser_sim.py` copies the logic, not vLLM itself. It printed: two valid calls parse. One trailing comma in the second call loses both. An unknown tool name `delete_order` passes. `"amount": "ten"` passes. A cut-off call comes back as text. A call with the key `"parameters"` instead of `"arguments"` is lost.
- **Key names differ by template, verified.** The Llama 3.2 template asks for `"parameters"`. The Qwen3 template asks for `"arguments"`. Sources: the saved renders. **Inferred:** a Llama model served with the `hermes` parser drops every call. Check: serve Llama 3.2 1B with `--tool-call-parser hermes` and send one request.
- **Server facts, verified.** vLLM 0.30.0 docs, `tools/vllm_tool_calling.md`.
  - `--enable-auto-tool-choice` is "mandatory" for auto mode. `--tool-call-parser` selects `hermes`, `mistral`, `llama3_json`, `pythonic`, `openai` and others.
  - vLLM "includes tool definitions in the prompt by default, regardless of the `tool_choice` setting".
  - "Parallel tool calls are not supported for Llama 3." "Mistral 7B struggles to generate parallel tool calls correctly."
  - With `tool_choice="auto"`, constraint applies only with `strict: true` on at least one tool, line 118. See 4.3.

Summary: on a self-hosted model, validate every extracted call against the schema. Treat "no calls" as a possible parse failure.

### 4.10 In MCP 2026-07-28, an open connection is not a session. Each request carries its own version and capabilities, so any server instance can answer it

A learner thinks the stdio process or the HTTP connection holds the conversation.

- **Best evidence, verified.** MCP 2026-07-28 Overview, "Statelessness": "Servers **MUST NOT** rely on prior requests over the same connection to establish context". The note continues: "an open connection, such as a STDIO process, is not a conversation or session". Source: `mcp/md/basic.md` lines 193 and 205 to 210.
- **Per-request metadata, verified.** Every request carries `_meta` with `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities`, both required. A missing capability returns `-32021`. Source: Overview, section `_meta`, `mcp/md/basic.md` line 391.
- **Live behaviour, verified by run, run output not saved.** On Python `mcp` 2.2.0 over stdio, `mcp/lab/trace.py` sent `tools/call` with no `initialize` and a full `_meta`. The server returned `3`. Without `_meta` it returned `-32602`. With version `1999-01-01` it returned `-32022` and `"supported":["2026-07-28"]`.
- **HTTP behaviour, verified by run, log saved.** The same server on Streamable HTTP, port 8731. `mcp/lab/http.log` shows one `200 OK`, two `400 Bad Request` and one `403 Forbidden`. The report maps them to: all headers correct, `Mcp-Name` missing, `Mcp-Name` not matching the body, and `Origin: https://evil.example`. The spec requires `Mcp-Method` on all requests and `Mcp-Name` on `tools/call`, `resources/read` and `prompts/get`, `mcp/md/streamable.md` lines 291 to 292. Servers "MUST validate the `Origin` header".
- **Discovery, verified.** Servers MUST implement `server/discover`. The live 2.2.0 response had `supportedVersions: ["2026-07-28"]`, `ttlMs: 0` and `cacheScope: "private"`. Run output not saved.
- **Old clients still work on the Python SDK, verified by run, run output not saved.** `mcp/lab/legacy.py`: the 2.2.0 server accepted a legacy `initialize` with `protocolVersion: "2025-11-25"` and answered a later call without `resultType`. So `server/discover` lists only `2026-07-28`, yet the server serves the old handshake. The stdio page says a dual-version client "**SHOULD** probe with `server/discover`" and the fallback "**MUST NOT** be keyed to one specific error code", `mcp/md/stdio.md` lines 131 and 146.
- **State moves into handles, verified.** Tools page, "Stateful Tools": state that spans calls lives in a server-minted handle passed as an argument. "a handle is a name, not a capability". Source: `mcp/md/tools.md` line 715. Built Module 2, 2.4 uses handles to shrink context. Link it.
- **Tool output, verified.** `structuredContent` can match an optional `outputSchema`. Servers "MUST provide structured results that conform to this schema". A tool "SHOULD also return the serialized JSON in a TextContent block". The spec notes it is "unrelated to LLM 'structured outputs'". The live 2.2.0 `add(a: int, b: int) -> int` returned `structuredContent: {"result": 3}` and a text block `"3"`. Run output not saved.
- **The tool list and the cache, verified.** "Servers **SHOULD** return tools in a deterministic order", which "improves LLM prompt cache hit rates", `mcp/md/tools.md` line 71. The list "**MUST NOT** vary per-connection" but "**MAY** vary by the authorization presented on the request".

Summary: every MCP request stands alone. State that must persist lives in a handle or in the server's own store.

### 4.11 A sealed `requestState` lets the server forget between rounds, but it is not single-use, so the same state can confirm the same action twice

MRTR, Multi Round-Trip Requests, lets a server ask for input inside a result. The server returns `resultType: "input_required"` with a `requestState`. The client answers and retries with the same state.

- **Best evidence, verified.** MRTR page, "Server Requirements (Basic Workflow)": servers "**MUST** treat `requestState` as an attacker-controlled input". Integrity and binding measures "do not by themselves guarantee single-use". A one-time action "**MUST** enforce that invariant server-side". Source: `mcp/md/mrtr.md` lines 236, 245 and 247.
- **Live replay, verified by run, run output not saved.** `mcp/lab/mrtr_replay.py` on `mcp` 2.2.0. A `refund(order_id)` tool asks the user to confirm through a form elicitation.
  - Round 1 returned `input_required` with a sealed state that starts with `v1.` and is 339 characters long.
  - The same retry sent twice returned "refunded A17" both times.
  - `mcp/lab/mrtr_trace.py`: a tampered state and a state reused with another `order_id` both returned `-32602` "Invalid or expired requestState". So the SDK binds the state to the request parameters. It does not stop a replay of the same request.
- **SDK default, verified in source.** `mcp/server/request_state.py` at 2.2.0 uses AES-GCM with a key made at process start. The default TTL is 600 seconds, line 122. State "minted before a restart or by another worker is rejected", line 146. Saved as `mcp/gh/pysdk_src/request_state_v2.2.0.py`. **Inferred:** a load-balanced deployment on the defaults fails every retry that reaches another instance. Check: two workers without shared keys.
- **Other MRTR rules, verified.** Only `tools/call`, `resources/read` and `prompts/get` may return `input_required`. The retry needs a new JSON-RPC `id`. The client "**MUST** echo back the exact value" of `requestState`. Results of retries "**MUST NOT** be cached". Servers "**MUST NOT** use form mode elicitation to request sensitive information".

Summary: MRTR makes the server stateless, not the action idempotent. A refund needs its own idempotency key.

### 4.12 Tool annotations are claims a server makes about itself, so a client must not base a safety decision on them unless it trusts the server

A learner skips confirmation when a tool says `readOnlyHint: true`.

- **Best evidence, verified.** Tools page: "clients **MUST** consider tool annotations to be untrusted unless they come from trusted servers." Source: `mcp/md/tools.md` lines 305 to 306.
- **Defaults, verified by the MCP report in `schema.ts` at tag 2026-07-28, lines 1903 to 1953.** `readOnlyHint` false, `destructiveHint` true, `idempotentHint` false, `openWorldHint` true. An absent annotation means the most careful reading. `schema.ts` was not saved, so these lines were not re-grepped for this dossier.
- **The same rule covers `serverInfo`, verified.** Discovery page: clients "**SHOULD NOT** rely on it for security decisions". Source: `mcp/md/discover.md`.
- **What is open, inferred.** The spec does not define how a host decides that a server is trusted. No incident was found where a false `readOnlyHint` caused harm. Not checked in CVE databases.

Summary: an annotation is a hint for a trusted server and nothing for an untrusted one.

### 4.13 A user's approval does not freeze a tool's definition, so the client must keep a hash of what the user approved

A learner assumes that once a user approves a server, its tools stay as approved.

- **Best evidence, verified.** Tools page, "Capabilities": the tool set "**MAY** change over time". Source: `mcp/md/tools.md` line 64. The MCP report searched six spec files for "pin", "pinning", "signature" and "signed". No match describes an integrity mechanism for tool definitions. This proves absence in those files only.
- **Attack definition, verified.** Invariant Labs, 2025-04-01, vendor blog: "a malicious server can change the tool description after the client has already approved it." The post suggests "using a hash or checksum". Source: `mcp/attacks/invariant_tpa.txt`. The post contains attack payloads written as instructions. Quote them only inside code blocks.
- **Live detection, verified by run, run output not saved.** `mcp/lab/rug_detect.py` hashes the canonical JSON of each tool at approval and after each call. When `rug_server.py` swapped the description after the first call, it printed `approved=b0c21005c71cb66c now=3dbcdcf9662ddf0d -> CHANGED`.
- **Where a hash does not help, inferred.** A hash of `description` alone misses changes in `inputSchema` property descriptions, `title` or annotations. Hash the whole tool object. A hash of the list also misses a changed binary that returns the same list. CVE-2025-54136 in Cursor 1.2.4 and below swapped an approved MCP launch command "without triggering any warning or re-prompt". Source: `mcp/attacks/nvd_54136.json`. Module 16 owns that case.

Summary: approval is bound to a name unless the client binds it to a hash of the content.

### 4.14 The spec requires an MCP server to check the token audience, but the Python SDK 2.2.0 does not check it by default

A learner assumes the SDK enforces the spec's MUST.

- **Best evidence, verified.** Spec: "MCP servers **MUST** validate that access tokens were issued specifically for them as the intended audience". Servers "**MUST NOT** accept or transit any other tokens". Source: Authorization page, "Token Handling", `mcp/md/auth.md` lines 287 and 299. SDK: `validate_token_resource` defaults to `None`. "With `resource_server_url` set, leaving it unset warns and behaves as False; 3.0 makes True the default there." Source: `mcp/server/auth/settings.py` at 2.2.0, lines 48 to 54, saved as `mcp/gh/pysdk_src/auth_settings_v2.2.0.py`.
- **So a server on the defaults accepts a token for another audience, inferred.** Two things stop it: `validate_token_resource=True`, or a `TokenVerifier` that checks `aud`. Inferred from `bearer_auth.py` line 74. Not run. Lab 9 would confirm it. The TypeScript SDK 2.0.0 default was not checked.
- **Three different things, verified.** The spec's Security Best Practices page names them separately. Source: `mcp/md/secbp.md`.
  1. **Audience validation failure.** The server accepts a token that was issued for another service. This "breaks a fundamental OAuth security boundary". Section "Token Passthrough", item 1, line 292.
  2. **Token passthrough.** The server accepts that token and also forwards it unmodified to a downstream API. The page defines the anti-pattern as accepting tokens "without validating that the tokens were properly issued *to the MCP server*" and passing "them through to the downstream API", lines 283 to 286. Item 2 says this "can potentially cause the 'confused deputy' problem" at the downstream API, lines 300 to 305.
  3. **The spec's own "Confused Deputy Problem".** A different attack. An MCP proxy server with a static client ID, dynamic client registration and a consent cookie lets a malicious client obtain an authorization code without user consent. Section "Confused Deputy Problem", lines 30 to 40.
- **Correct wording for the course.** "A server that accepts a token issued for another audience has an audience validation failure. If it also forwards that token, that is token passthrough, and the downstream API can become a confused deputy." Do not call the accepting server itself "a confused deputy".
- **Authorization facts at mechanism level, verified.** Authorization is optional. stdio servers "SHOULD NOT" use it and take credentials from the environment. A protected server is an OAuth 2.1 resource server. It "MUST implement OAuth 2.0 Protected Resource Metadata", RFC 9728. Clients "MUST implement Resource Indicators", RFC 8707. Client ID Metadata Documents are the recommended registration. Dynamic Client Registration is deprecated. Module 8 teaches the flows.

Summary: the audience check is a spec MUST and an SDK opt-in. Name the three failures separately.

### 4.15 An MCP App is server-supplied HTML that the host renders in a sandboxed iframe. The app never talks to the MCP server directly. Every call goes through the host

MCP Apps is the extension `io.modelcontextprotocol/ui`. A learner either treats the app as trusted host UI or thinks it can call the server on its own.

- **Best evidence, verified.** MCP Apps specification, SEP-1865, "**Status:** Stable (2026-01-26)", file `specification/2026-01-26/apps.mdx` at tag v2.0.0 of `modelcontextprotocol/ext-apps`. Saved as `mcp/gh/apps_spec_2026-01-26.mdx`, line 9.
  - The view talks to the host "via a `postMessage` transport".
  - A web host "MUST wrap the View" in a sandbox proxy on a different origin. The host "MAY decide to block some messages or subject them to further user approval".
  - If `ui.csp` is omitted, the host MUST use `connect-src 'none'`, line 283. The host "MUST NOT allow undeclared domains", line 286.
- **How a tool links to its UI, verified.** The UI resource URI "MUST start with `ui://`". Its `mimeType` "MUST be `text/html;profile=mcp-app`". The tool carries `_meta.ui.resourceUri`, and the host fetches it with `resources/read`. Tool `visibility` defaults to `["model", "app"]`. A tool without `"model"` stays out of the agent's tool list.
- **Where the sandbox stops, verified.** The spec's own "Other risks": "UI can still display misleading content", line 1762. The default CSP allows `script-src 'self' 'unsafe-inline'`, line 279. **Inferred:** the sandbox isolates the app from the host page. It does not stop script inside the app.
- **Package version is not spec version, verified.** `ext-apps` v2.0.0 was published 2026-09-08. Its release notes say "The MCP Apps wire protocol is unchanged". Source: `mcp/gh/extapps_releases.json`. The spec date is 2026-01-26.
- **Two negotiation texts disagree, verified.** The Apps spec section on capability negotiation still shows `initialize` with `protocolVersion "2024-11-05"`. The Extensions Overview shows per-request `_meta` under 2026-07-28. Teach the Extensions Overview for host to server. The view to host side keeps its own `ui/initialize`.
- **Hosts, verified vendor list, not a test.** The Apps overview lists Claude, Claude Desktop, VS Code GitHub Copilot, Microsoft 365 Copilot, Goose, Postman, MCPJam and Archestra.AI. The client matrix also marks ChatGPT.

Summary: an MCP App is untrusted HTML with a narrow channel to the host. The host decides every call.

### 4.16 Most MCP scanner alerts are false positives, and the most precise scanners missed every known CVE in the test set

A learner runs a scanner and trusts a clean report or a red flag. Module 16 owns defences. This concept stays here because it measures MCP servers directly.

- **Best evidence, verified.** Chen et al., "Rethinking MCP Security", arXiv 2607.11086, Fudan University and Shanghai Innovation Institute, preprint, submitted 2026-07-13. Source: `mcp/papers/2607.11086.txt`, Section 5.3 and Table 7.
  - Corpus: MCPZoo, 64,611 unique servers, 37,288 that support dynamic analysis.
  - "96.89% of the 37,288 interactable MCP servers are reported as risky by at least one scanner". Table 5. No server was flagged by all eight scanners.
  - Precision method: 100 flagged servers sampled, stratified by scanner and risk category. 685 alerts in total. Two reviewers, Cohen's kappa 0.87, a third for disagreements.
  - "overall average precision is 45.53%", line 1540. It is the unweighted mean of the nine rows in Table 7, because A.I.G appears twice, static and dynamic. The MCP report recomputed each row. Pooled over all alerts, precision is 276/685 = 40.29%. Verified by arithmetic from Table 7.
  - The mean equals MCPScan's own row by coincidence, 56/123 = 45.53%. Do not cite them as two findings.
  - Recall ground truth is "10 CVEs affecting 38 MCPZoo servers", line 1641. mcp-gateway at 96.88% precision, MCPSafetyScanner at 74.03% and nova-proximity at 52.78% all had 0.00% recall.
- **Supporting, verified 2026-09-17, not re-read.** arXiv 2506.13538: 7.2% of 1,899 servers had vulnerabilities by SonarQube. Its 5.5% poisoning figure comes from only 73 scanned servers.

Summary: a scanner flag is a lead to check, not a finding. A clean scan does not rule out a known CVE.

## 5. Proposed phase outline

Five phases. Sandboxes moved to Module 7, as audit fix 5 asks. Inferred from the audit's ownership recommendation.

| Phase | Title | Concepts | Labs | Runs where, costs what |
|---|---|---|---|---|
| 1 | What the model sees when you give it a tool | 4.1, 4.2, 4.3 | 1, 2 | Laptop. Tokenizer downloads, size not measured |
| 2 | Choosing among many tools | 4.4, 4.5, 4.6, 4.7 | 3, 4 | Laptop, offline. Optional live run, see Lab 11 |
| 3 | Code as the call, and self-hosted calls | 4.8, 4.9 | 5, 6 | Laptop, offline |
| 4 | MCP as stateless requests | 4.10, 4.11 | 7, 8 | Laptop, `mcp` 2.2.0 in a 33 MB venv |
| 5 | MCP trust boundaries | 4.12, 4.13, 4.14, 4.15, 4.16 | 9, 10 | Laptop, offline |

Phase 5 stays at mechanism level. Module 8 owns OAuth flows. Module 16 owns defences.

## 6. Lab inventory and lab ideas

All labs run offline on the learner's Mac unless marked. No API keys.

### Prototypes that ran on 2026-09-23

| Prototype | Path under `scratchpad/research_tools-mcp/` | What it printed | Output saved? |
|---|---|---|---|
| Template renderer | `tools/render/render.py` | Placement, token overhead 217, 83 and 250, order-swap hash change | Renders saved as `tools/render/*.txt`. Counts and hashes not saved |
| Schema survival | `tools/render/lossy.py` | Keyword kept or dropped per template. gpt-oss drops 4 keywords and nested fields | No |
| Parser replica | `tools/render/parser_sim.py` | Six cases, see 4.9 | No |
| RAG-MCP Figure 3 cell count | `tools/fig3_cells.py` | 159 of 280 cells successful | No |
| Raw stdio trace | `mcp/lab/trace.py` with `mcp/lab/server.py` | Discover, list, call, and error codes `-32602`, `-32022`. Five responses in 0.36 s | No |
| Legacy handshake | `mcp/lab/legacy.py` | 2.2.0 accepts `initialize` for 2025-11-25 | No |
| Streamable HTTP | `mcp/lab/http_server.py` | 200, 400, 400, 403 | Yes, `mcp/lab/http.log` |
| MRTR flow and replay | `mcp/lab/mrtr_server.py`, `mrtr_trace.py`, `mrtr_replay.py` | `input_required`, 339-character state, replay refunds twice | No |
| Rug-pull detector | `mcp/lab/rug_server.py`, `rug_detect.py` | `-> CHANGED` after the swap | No |

A course generator must re-run each prototype and save its output before quoting a number from it.

### Lab designs

1. **Tool token meter and template renderer.** Proves 4.1. Renders 1 to 200 tools through the Qwen3, gpt-oss and Llama 3.2 templates, pinned by sha. Prints tokens with no tools, tokens per added tool, fixed wrapper tokens, the offset of the first tool, and the SHA-256 of the prefix before the first user message. Break-it: shuffle tool order, or patch the date. The hash changes. For gpt-oss and Llama the date alone changes it. Self-test: sorted tools give one hash across 10 runs on one date. About 6 seconds per model after download, from the report.
2. **Schema survival and strict linter.** Proves 4.1 and 4.3. Sends one rich schema through each template and prints a keyword-by-template table. Then lints against Anthropic's 20, 24 and 16, OpenAI's strict rules, and Anthropic's unsupported keywords. Break-it: a 25th optional parameter, a 17th `["string","null"]` field. Self-test: five fixtures with known violation counts. The gpt-oss row must show `items?: any[]`.
3. **Tool search recall.** Proves 4.6. 500 synthetic tools in 25 namespaces, 100 labelled queries. Regex, BM25 and MiniLM from the shared harness at `retrieval-internals/code/`. Prints recall at 1, 3, 5 and 10 per method and per query class. Break-it: vague descriptions. Self-test: a query equal to a tool name is found at rank 1 by regex. Design only. Run time not measured.
4. **Results and errors, retry simulation.** Proves the mechanism in 4.7. A mock `get_order` returns opaque or actionable errors. A scripted policy repairs a call only when the error names the field and the format. Prints calls, retries and context tokens. Break-it: an actionable error that names the wrong field. Self-test: fixture retry counts. The lab must say it simulates the mechanism and does not measure a model.
5. **Direct calls against code, context growth.** Proves 4.8. Simulates N calls with result size S. Prints cumulative input tokens for both modes and the break-even N. Break-it: N = 1 with a fixed code overhead, which matches the τ²-bench case. Self-test: closed-form sums.
6. **Parser failure matrix.** Proves 4.9. Replicates the vLLM 0.30.0 `hermes` logic and a `llama3_json`-style parser on 12 fixtures. Prints `tools_called`, call count, and whether raw text leaks. Then adds a `jsonschema` 4.26.0 gate. Self-test: "second call malformed" gives 0 calls, as in `hermes_tool_parser.py` lines 116 to 120. Importing the real vLLM class on macOS arm64: not checked.
7. **Raw MCP trace.** Proves 4.10. Built from the `trace.py`, `legacy.py` and `http_server.py` prototypes. Break-it: drop `_meta`, send version `1999-01-01`, send a legacy `initialize`, print to stdout inside a tool. The last one was not run. Self-test: response ids match request ids, every result has `resultType`, error codes equal `-32602`, `-32021` and `-32022`. Use a free port. Port 8000 was taken on the research machine.
8. **Multi Round-Trip flow.** Proves 4.11. Built from the `mrtr_*` prototypes. Break-it: tamper with the state, reuse it on another order, declare no elicitation capability, replay the same retry. Fix: an idempotency set keyed by `order_id`. Self-test: the refund counter is 2 before the fix and 1 after it.
9. **Audience check.** Proves 4.14. Design only, not built. Two local HS256 JWTs, one for the server and one for `https://other-api.example`. A `TokenVerifier` that sets `AccessToken.resource` from `aud`. Expected: with `validate_token_resource` unset, both tokens get 200. With `True`, the foreign token gets 401. UNVERIFIED until run. Break-it: a proxy tool forwards the bearer token to a fake downstream API, which shows token passthrough. Self-test: a fixed four-cell table.
10. **Rug-pull detector.** Proves 4.13. Built from the `rug_*` prototypes. Break-it: hash only `description` and change an `inputSchema` description instead. Hash without `sort_keys`. Change behaviour but not the definition. The first two were not run. Self-test: 0 alarms for an unchanged server over 10 calls, exactly 1 for the swapping server.
11. **Optional, UNVERIFIED: accuracy against tool count on a hosted model.** 5, 20, 50 and 100 tools, 50 requests each, 200 requests in total. Needs an API key. **Cost estimate, inferred:** about $1.1 on Claude Haiku 4.5 at $1 per million input tokens and $5 per million output tokens, from the Anthropic pricing page fetched 2026-09-23, `scratchpad/m06_refresh/pricing.md` line 33. The estimate assumes 100 tokens per tool, the 496-token Haiku 4.5 tool prompt, a 100-token query and 100 output tokens, with no caching. About 1.0 million input tokens and 20,000 output tokens.

## 7. Failure stories and case studies

These MCP cases were verified on 2026-09-17. Their URLs returned 200 on 2026-09-23. Their content was not re-read today except CVE-2025-54136.

| Case | Date | Mechanism | Numbers | Source |
|---|---|---|---|---|
| WhatsApp MCP exfiltration | 2025-04-07 | A sleeper server shadowed `whatsapp-mcp` | No CVE | Invariant Labs |
| GitHub MCP toxic agent flow | 2025-05-26 | A public issue leaked private repo data into a public PR | Design issue | Invariant Labs |
| MCP Inspector, CVE-2025-49596 | 2025-06-13 | No auth between client and proxy, plus DNS rebinding | CVSS 4.0 9.4. Fixed 0.14.1 | Oligo, NVD |
| Filesystem server, CVE-2025-53109 and 53110 | 2025-07-02 | Path prefix escape and symlink bypass | 7.3 each. Upgrade to 2025.7.1 | Cymulate |
| Supabase MCP | 2025-07-08 | A ticket injected instructions to an agent with `service_role` | No CVE | General Analysis |
| mcp-remote, CVE-2025-6514 | 2025-07-09 | A crafted `authorization_endpoint` ran a command | CVSS 3.1 9.6. Fixed 0.1.16 | JFrog advisory |
| Cursor, CVE-2025-54136 | 2025-08-02 | An approved MCP config entry swapped without a re-prompt. Verified today | Fixed 1.3 | NVD |
| postmark-mcp | 2025-09 | Version 1.0.16 added a hidden BCC | 1,643 downloads per The Hacker News | Postmark, Snyk |
| Smithery hosting | 2025-10-22 | Build path traversal leaked admin credentials | "over 3,000 hosted AI servers" | GitGuardian |
| mcp-server-git, CVE-2025-68143 to 68145 | 2025-12-17 | Path traversal and argument injection chained to code execution | 68143 CVSS 3.1 8.8 | NVD, The Hacker News |

The Asana MCP exposure was found on Jun 4 and customers were told on Jun 16. The year 2025 is inferred. Source: UpGuard.

Moved to Module 7 with the sandboxes: Codex CLI CVE-2025-59532, Claude Code CVE-2026-25725, 39861 and 55607, and runc CVE-2024-21626.

## 8. Primary sources

All fetched 2026-09-23. All returned HTTP 200 after redirects with a browser user agent, `scratchpad/m06_refresh/url_status.txt`. Anthropic docs pages also serve Markdown at the same URL plus `.md`, which is what the reports saved.

### Provider tool calling

- **Tool use overview, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview. Focus: "Pricing", tool-use system prompt table.
- **Define tools, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools. Focus: "Tool use system prompt", "Forcing tool use".
- **Structured outputs, Anthropic, 2026** — https://platform.claude.com/docs/en/build-with-claude/structured-outputs. Focus: "Invalid outputs", "Schema complexity limits".
- **Strict tool use, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use.
- **Prompt caching, Anthropic, 2026** — https://platform.claude.com/docs/en/build-with-claude/prompt-caching. Focus: "What invalidates the cache".
- **Tool use with prompt caching, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching. Focus: `defer_loading` and the grammar.
- **Mid-conversation system messages and tool changes, Anthropic, 2026** — https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages. Focus: "Mid-conversation tool changes", "Define tools in a message", "Limitations".
- **Pricing, Anthropic, 2026** — https://platform.claude.com/docs/en/about-claude/pricing. Focus: Haiku 4.5 row for Lab 11.
- **Function calling, OpenAI, 2026** — https://developers.openai.com/api/docs/guides/function-calling. Focus: "Token Usage", best practices.
- **Structured outputs, OpenAI, 2026** — https://developers.openai.com/api/docs/guides/structured-outputs. Focus: "Supported schemas", "Handling mistakes".
- **Tool search, OpenAI, 2026** — https://developers.openai.com/api/docs/guides/tools-tool-search. Focus: supported models, deferred functions.
- **Function calling, Google, 2026** — https://ai.google.dev/gemini-api/docs/function-calling. Returned 200 with a browser user agent today. The tools report saw a 302 to a login page. The Markdown copy is at `function-calling.md.txt`.
- **Structured output, Google, 2026** — https://ai.google.dev/gemini-api/docs/structured-output. Focus: "Best practices", "Limitations".

### Tool selection, deferred loading, code, Skills

- **Scaling Enterprise Agent Routing, Gillespie and Perry, Superhuman Inc., arXiv preprint 2026** — https://arxiv.org/abs/2606.17519. Focus: Section 4, Figure 1, Appendix A. The best current tool-count evidence.
- **How Many Tools Should an LLM Agent See?, arXiv preprint 2026** — https://arxiv.org/abs/2605.24660. Focus: Table 1.
- **LiveMCPBench v2, Mo et al., arXiv preprint 2026** — https://arxiv.org/abs/2508.01780. Focus: Table 2, Appendix I.
- **RAG-MCP, Gan and Sun, arXiv preprint 2025** — https://arxiv.org/abs/2505.03275. Focus: Table 1 with the caveats in 4.4. Figure 3 is not a curve.
- **MCP-Bench, Wang et al., arXiv preprint 2025** — https://arxiv.org/abs/2508.20453. Not re-read today. Old dossier facts: 250 tools, o4-mini judge.
- **Tool search tool, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool. Focus: "Limits".
- **Claude Code MCP, Anthropic, 2026** — https://code.claude.com/docs/en/mcp. Focus: tool search, output limits, 2,048-character truncation.
- **Writing effective tools for agents, Anthropic, 2025** — https://www.anthropic.com/engineering/writing-tools-for-agents. Focus: Slack and Asana figure images.
- **Introducing advanced tool use, Anthropic, 2025** — https://www.anthropic.com/engineering/advanced-tool-use. Vendor numbers without eval, model or scorer.
- **Programmatic tool calling, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling. Focus: "Token efficiency", constraints.
- **Code execution tool, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool. Focus: versions, container, pricing.
- **Code execution with MCP, Anthropic, 2025** — https://www.anthropic.com/engineering/code-execution-with-mcp. An illustration, no method.
- **Code Mode, Cloudflare, 2025** — https://blog.cloudflare.com/code-mode/.
- **Code Mode MCP server, Cloudflare, 2026** — https://blog.cloudflare.com/code-mode-mcp/. Focus: 1,000 and 1.17 million tokens, tiktoken.
- **From Tool Orchestration to Code Execution, Felendler et al., arXiv preprint 2026** — https://arxiv.org/abs/2602.15945. Focus: Figures 4 to 10, not read.
- **Agent Skills overview, Anthropic, 2026** — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview.
- **Agent Skills specification, agentskills.io** — https://agentskills.io/specification.

### Open-weight tool calling

- **vLLM tool calling docs at v0.30.0, vLLM project, 2026** — https://raw.githubusercontent.com/vllm-project/vllm/v0.30.0/docs/features/tool_calling.md. Focus: "Constrained Decoding Behavior", parsers, known issues.
- **vLLM hermes parser at v0.30.0, vLLM project, 2026** — https://raw.githubusercontent.com/vllm-project/vllm/v0.30.0/vllm/tool_parsers/hermes_tool_parser.py. Focus: lines 38 to 120.
- **Qwen3-0.6B chat template, Alibaba Qwen** — https://huggingface.co/Qwen/Qwen3-0.6B, revision c1899de289a0.
- **gpt-oss-20b chat template, OpenAI** — https://huggingface.co/openai/gpt-oss-20b, revision 6cee5e81ee83.
- **Llama-3.2-1B-Instruct template mirror, Unsloth, a copy of Meta's template** — https://huggingface.co/unsloth/Llama-3.2-1B-Instruct, revision 5a8abab4a5d6.

### MCP specification, extensions, SDKs

- **Versioning, MCP, 2026** — https://modelcontextprotocol.io/docs/2026-07-28/learn/versioning. The old URL `/specification/versioning` redirects here.
- **Key Changes, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/changelog.
- **Overview, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/basic/index. Focus: "Statelessness", `_meta`, error codes.
- **Multi Round-Trip Requests, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr. Focus: Server Requirements items 4 to 8.
- **Discovery, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/server/discover.
- **stdio, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio. Focus: "Backward Compatibility".
- **Streamable HTTP, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http. Focus: "Security & Endpoint", "Standard Request Headers".
- **Tools, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/server/tools. Focus: annotations warning, "Stateful Tools", "Error Handling".
- **Elicitation, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation.
- **Deprecated features, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/deprecated.
- **Authorization, MCP 2026-07-28** — https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/index. Focus: "Token Handling".
- **Security Best Practices, MCP 2026-07-28** — https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices. Focus: "Confused Deputy Problem", "Token Passthrough", "State Handle Hijacking".
- **schema.ts at tag 2026-07-28, MCP** — https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/2026-07-28/schema/2026-07-28/schema.ts. Focus: line 30, lines 1900 to 1954.
- **The 2026-07-28 Specification, MCP blog** — https://blog.modelcontextprotocol.io/posts/2026-07-28/. Focus: rationale, "any request can land on any instance".
- **Extensions Overview, MCP** — https://modelcontextprotocol.io/extensions/overview. Focus: "Negotiation".
- **MCP Apps overview, MCP** — https://modelcontextprotocol.io/extensions/apps/overview.
- **MCP Apps spec, SEP-1865, stable 2026-01-26, at tag v2.0.0** — https://raw.githubusercontent.com/modelcontextprotocol/ext-apps/v2.0.0/specification/2026-01-26/apps.mdx. Focus: "UI Resource Format", "Sandbox proxy", "Security Implications".
- **Python SDK README at v2.2.0, MCP** — https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v2.2.0/README.md. Focus: "A server in 15 lines".
- **Registry about, MCP** — https://modelcontextprotocol.io/registry/about. Still preview.

### MCP security

- **Tool poisoning attacks, Invariant Labs, vendor blog, 2025** — https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks. Contains payloads written as instructions.
- **WhatsApp MCP exploited, Invariant Labs, 2025** — https://invariantlabs.ai/blog/whatsapp-mcp-exploited.
- **GitHub MCP vulnerability, Invariant Labs, 2025** — https://invariantlabs.ai/blog/mcp-github-vulnerability.
- **MCP Inspector RCE, Oligo Security, 2025** — https://www.oligo.security/blog/critical-rce-vulnerability-in-anthropic-mcp-inspector-cve-2025-49596.
- **mcp-remote advisory, JFrog, 2025** — https://research.jfrog.com/vulnerabilities/mcp-remote-command-injection-rce-jfsa-2025-001290844/.
- **EscapeRoute, Cymulate, 2025** — https://cymulate.com/blog/cve-2025-53109-53110-escaperoute-anthropic/.
- **MCP git server flaws, The Hacker News, 2026** — https://thehackernews.com/2026/01/three-flaws-in-anthropic-mcp-git-server.html. Secondary.
- **Supabase MCP leak, General Analysis, 2025** — https://generalanalysis.com/blog/supabase-mcp-blog.
- **postmark-mcp, Postmark, 2025** — https://postmarkapp.com/blog/information-regarding-malicious-postmark-mcp-package.
- **Breaking MCP server hosting, GitGuardian, 2025** — https://blog.gitguardian.com/breaking-mcp-server-hosting/.
- **CVE-2025-54136, NIST NVD** — https://nvd.nist.gov/vuln/detail/CVE-2025-54136.
- **Rethinking MCP Security, Chen et al., Fudan University, arXiv preprint 2026** — https://arxiv.org/abs/2607.11086. Focus: Section 5.3, Tables 5 and 7.
- **MCP at First Glance, Hasan et al., arXiv preprint 2025** — https://arxiv.org/abs/2506.13538. Focus: Table 7.

### MCP changelog lines, 2026-07-28, for References

One line each, from the changelog page. Verified by the MCP report.

1. Sessions and `Mcp-Session-Id` removed. Cross-call state uses handles, SEP-2567.
2. `initialize` handshake removed. Version and capabilities go per request in `_meta`, SEP-2575.
3. `server/discover` added. Servers MUST implement it, SEP-2575.
4. `subscriptions/listen` replaces the HTTP GET stream and `resources/subscribe`, SEP-2575.
5. `ping`, `logging/setLevel` and `notifications/roots/list_changed` removed, SEP-2575.
6. Tasks moved to the extension `io.modelcontextprotocol/tasks`, SEP-2663.
7. MRTR replaces server-initiated requests, SEP-2322.
8. `resultType` required on every result, SEP-2322.
9. SSE resumability and `Last-Event-ID` removed, SEP-2575.
10. Minor: `extensions` capability, OpenTelemetry `_meta` keys, deterministic `tools/list` order, `Mcp-Method` and `Mcp-Name` headers, `ttlMs` and `cacheScope`, `iss` validation, any JSON Schema 2020-12 keyword, `elicitationId` removed, error codes renumbered to `-32020`, `-32021`, `-32022`.
11. Deprecated, earliest removal on or after 2027-07-28: Roots, Sampling, Logging, HTTP+SSE, `includeContext` values, Dynamic Client Registration. "No features have been removed under this policy yet."

### Moved to Module 7

The sandbox sources move with the topic: Firecracker NSDI 2020 and `SPECIFICATION.md` v1.17.0, the gVisor architecture, platform and performance pages, the kernel seccomp docs, Docker seccomp profiles, the runc advisory, Claude Code sandboxing, Codex sandboxing, Docker Sandboxes, Apple Containerization, ComputeSDK benchmarks and the SecurityWeek bypass report. They were verified on 2026-09-17 and not re-checked today.

## 9. Tools and versions to pin

Checked on PyPI and npm on 2026-09-23. File: `scratchpad/m06_refresh/versions.txt`.

| Tool | Version | Release date | Source | Note |
|---|---|---|---|---|
| MCP specification | 2026-07-28 | 2026-07-28 | versioning page, `schema.ts` line 30 | Current |
| `mcp`, Python | 2.2.0 | 2026-09-07 | PyPI | `MCPServer`. v1 line is 1.30.0. Audience check off by default |
| `@modelcontextprotocol/server`, `/client` | 2.0.0 | 2026-07-27 | npm | Node 20 or later, `type: module` |
| `@modelcontextprotocol/sdk` | 1.30.0 | 2026-07-27 | npm | v1 line |
| `@modelcontextprotocol/ext-apps` | 2.0.0 | 2026-09-08 | npm, GitHub | Apps spec 2026-01-26. Needs zod 4.2 or later, from the MCP report |
| MCP Registry API | v0.1, preview | freeze 2025-10-24 | registry README | Repo release v1.8.1, 2026-08-06, from the MCP report |
| `fastmcp` | 4.0.5 | 2026-09-17 | PyPI | Not the official SDK |
| `anthropic`, Python | 1.8.0 | 2026-09-22 | PyPI | Not used in labs |
| `@anthropic-ai/sdk` | 0.128.0 | 2026-09-22 | npm | Not used in labs |
| `claude-agent-sdk`, Python | 0.2.158 | 2026-09-23 | PyPI | Not used in labs |
| `openai`, Python | 3.19.0 | 2026-09-23 | PyPI | Not used in labs. npm not re-checked |
| `google-genai` | 2.25.0 | 2026-09-22 | PyPI | Not used in labs |
| `transformers` | 5.17.0 | 2026-09-09 | PyPI | Lab 1 and 2 |
| `tokenizers` | 0.23.2 | 2026-09-03 | PyPI | |
| `huggingface-hub` | 1.32.0 | 2026-09-17 | PyPI | Pin model revisions by sha |
| `vllm` | 0.30.0 | 2026-09-22 | PyPI, GitHub | Parser source read at this tag. Not installed |
| `tiktoken` | 0.14.0 | 2026-08-17 | PyPI | Approximation only for hosted models |
| `jsonschema` | 4.26.0 | 2026-01-07 | PyPI | Lab 6 gate |
| uv | 0.12.8 | 2026-08-31 | local | From the MCP report |
| Anthropic tool versions | `tool_search_tool_*_20251119`, `code_execution_20260521` | docs 2026-09-23 | Anthropic docs | Beta headers `mid-conversation-tool-changes-2026-07-01`, `inline-tools-2026-09-15`, `mcp-client-2026-09-15` |

Sandbox tools move to Module 7: `@anthropic-ai/sandbox-runtime`, Firecracker, gVisor, Docker Engine, Apple `container` and Codex CLI.

## 10. Open questions and disagreements

- **Module 2, 2.3 is incomplete for seven Claude models.** It says to keep the list and reject in the harness. `tool_removal` now withdraws a tool without a cache rewrite on those models. Sonnet 5 lacks it. The cost is not measured. Consider a correction note on 2.3. This dossier does not edit Module 2.
- **Tool-count thresholds.** Anthropic says 30 to 50, OpenAI fewer than 20, Google 10 to 20, and Anthropic advises search at 10 or more. Gillespie and Perry find "an elbow at 40–60 agents" on their catalog. These are advice against measurement, and agents against tools.
- **RAG-MCP is weak evidence.** Unknown pool size, two judges, a binary rule next to percentages, and a Figure 3 whose text claim the cell count does not support. Prefer Gillespie and Perry.
- **Idle code execution containers.** "Checkpointed" on the code execution page, "reclaimed" on the programmatic tool calling page. Both read today.
- **Code mode savings.** Anthropic 98.7% is an illustration. Cloudflare 99.9% counts definitions with tiktoken. Anthropic's own τ²-bench case costs 8% more. Felendler et al. found lower quality on some open-ended tasks.
- **gpt-oss rendering.** The HF template drops nested schemas. The `openai-harmony` renderer may differ.
- **The Python SDK serves the legacy handshake but lists only 2026-07-28 in `server/discover`.** SDK inconsistency or intended. Open.
- **Apps negotiation text.** The Apps spec still shows `initialize` with "2024-11-05". The Extensions Overview shows per-request `_meta`. The Apps spec cites SEP-1724 for extensions, the Extensions Overview cites SEP-2133.
- **The draft Apps spec** relaxes two sandbox-proxy MUSTs to SHOULDs and adds `sampling/createMessage` from the view, while Sampling is deprecated in core. Whether it ships is open.
- **Scanner "overall precision".** 45.53% is a macro mean over nine rows. The pooled figure is 40.29%. Say which one you use.
- **Default audience check.** Spec MUST, Python default off with a warning until 3.0. TypeScript default not checked.
- **TS SDK v2 module format.** The beta blog said ESM-only. The v2.0.0 upgrade guide said it also ships CommonJS. Carried from 2026-09-17, not re-checked.

## 11. Things I could NOT verify

| Item | Check that would settle it |
|---|---|
| Token counts 217, 83 and 250, and the other stdout-only run numbers in section 6 | Re-run the prototypes and save their output |
| Cost of `tool_removal` and inline tools on a real bill | A live run with usage fields. Needs a key |
| What happens when the model calls a tool withdrawn by `tool_removal` | A live run. Needs a key |
| Whether the date line breaks vLLM prefix caching in practice | Serve gpt-oss-20b with prefix caching across midnight |
| Whether `hermes` with a Llama model drops every call | Serve Llama 3.2 1B with `--tool-call-parser hermes` |
| `openai-harmony` output for nested schemas | Run it on the Lab 2 schema |
| Felendler et al. numbers in Figures 4 to 10 | Read the figure images or released data |
| Pool size N for RAG-MCP Table 1, and the meaning of the Figure 3 axes | Author code |
| Gillespie and Perry section 5.4 numbers for OpenAI tool search | Read section 5.4 in `tools/enterprise.txt` |
| Organization of arXiv 2605.24660 | Read the PDF title page |
| Anthropic's 49% to 74%, 79.5% to 88.1%, 72% to 90%, 37% and 38% | Eval, model and scorer not published. Reproduce with Lab 11 |
| OpenAI and Google fixed tool-prompt overhead | Count tokens with and without tools on each count endpoint. Needs a key |
| Lab 9 outputs and whether the SDK serves Protected Resource Metadata at `/.well-known/oauth-protected-resource/mcp` | Build and run Lab 9 |
| TypeScript SDK 2.0.0 audience default | Read `packages/server/src/server/auth/*` at the 2.0.0 tag |
| MRTR state failure on a second worker | Two workers without shared keys |
| Annotation defaults at `schema.ts` lines 1903 to 1953 | Save `schema.ts` and grep it. Not saved in this run |
| Any incident caused by a false `readOnlyHint` | Search NVD for "readOnlyHint" |
| Any MCP extension that signs tool definitions | Read each `ext-*` repository |
| Registry vetting of entries, and registry general availability | Registry moderation docs. No GA announcement found |
| Lab 1 download size, Lab 3 run time | Run them |
| Failure-story details in section 7, other than CVE-2025-54136 | Re-read each source. URLs return 200 |
| Asana incident year | Inferred as 2025 |
| Strict tool use general availability date 2026-01-29 | Re-read the release notes |

## 12. Notes for the course generator

- Teach MCP as 2026-07-28 only. Put version history in References, one line each, from section 8.
- Link built Module 2, 2.3 and 2.4. Do not re-teach the cost of editing the list, `allowed_tools`, `response_format` or result caps.
- Teach 4.2 as an extension of 2.3, with its model list and its unmeasured cost.
- Use three separate terms: audience validation failure, token passthrough, and the spec's Confused Deputy Problem.
- Label every vendor number with what it counted and who ran it. Do not compare 98.7%, 99.9%, 85% and 38% as one measure.
- Present the 30 to 50, 20 and 10 to 20 thresholds as vendor advice.
- Do not use RAG-MCP Figure 3 as a curve. Cite LiveMCPBench Appendix I for the 50.00%.
- Re-run every prototype and save its output before quoting a number from it.
- Re-check before generating: hidden tool prompt tokens, beta headers and model lists, code execution version and price, OpenAI `tool_search` models, SDK versions, vLLM parser line numbers.
- Invariant Labs pages and some papers contain attack payloads written as instructions. Quote them only inside code blocks.
- Fastest to go stale: beta headers and their model lists, SDK versions, tool prompt tokens, registry status, CVE fixed versions.

## 13. Refresh log 2026-09-23

### Changes

1. **Section 4 rewritten as 16 claims.** Old topic headings 4.1 to 4.9 are gone. Audit fix 1 and brief rule 1.
2. **Feature tours cut.** Removed the per-provider `tool_choice` value lists, the Gemini enum note, parallel-call switches and streaming event names. Old 4.2 and 4.3. Kept only the limits Lab 2 uses. Audit fix 2.
3. **Version history moved out of section 4.** Old 4.7 read as a changelog. The 2026-07-28 changes are now one line each in section 8. Audit fix 3 and brief rule 10.
4. **Built Module 2 linked.** Section 2 overlap table rebuilt from `grep '^## '` on `context-engineering/*.md`. 2.3 is at line 278 and 2.4 at line 351 of `context-engineering-phase-02-cost.md`. Old 4.4 `response_format` 206 and 72 tokens and the 25,000-token cap now point to 2.4. Old 4.1 `allowed_tools` now points to 2.3. Audit fix 4.
5. **Sandboxes moved to Module 7.** Old 4.9, Phase 6, Labs 13 and 14, three failure stories and the sandbox sources and pins. Module 6 keeps the code execution tool in 4.8. Five phases now. Audit fix 5.
6. **MCP Apps added.** New 4.15. Audit fix 6. Old dossier had 0 mentions.
7. **Open-weight tool calling added.** New 4.1 table and 4.9. Audit fix 7.
8. **Figures read.** RAG-MCP Figure 3 is a binary per-trial heatmap, 4.4. LiveMCPBench Figure 7 numbers are in Appendix I, 4.4. Cloudflare's 1.17 million is in the text. Felendler figures are still not read. Audit fix 8.
9. **Links updated.** 67 URLs checked, all 200. The versioning URL now cites its redirect target. Audit fix 9.
10. **Versions re-pinned.** Section 9. Audit fix 10.
11. **New beta recorded.** 4.2 records `mid-conversation-tool-changes-2026-07-01` and `inline-tools-2026-09-15` with the seven-model list, as an extension of Module 2, 2.3. Module 2 was not edited.
12. **New evidence added.** arXiv 2606.17519 in 4.4, arXiv 2605.24660 in 4.5, the Anthropic PTC "Token efficiency" numbers in 4.8, the vLLM parser in 4.9, and the MCP live runs in 4.10, 4.11 and 4.13.
13. **New claims from the MCP report.** 4.11 replayable `requestState`, 4.13 approval does not freeze a definition, 4.14 SDK audience default.
14. **Lab list rebuilt.** Old labs 1 to 12 map to new labs 1 to 10, plus optional Lab 11. Old Lab 5's live option became Lab 11 with a cost recomputed from today's price.
15. **Dropped from section 4.** "Less is More", arXiv 2411.15399, a single query on one small model. MCP-Bench and AIMultiple, not re-read today. arXiv 2605.22333, abstract only.

### Corrections to the 2026-09-17 text

1. **Token passthrough was defined too narrowly.** Old 4.8 quoted the anti-pattern as accepting tokens "without validating" their audience. The page continues "and passes them through to the downstream API". Evidence: `mcp/md/secbp.md` lines 283 to 286. The page separates audience validation failure, line 292, from token passthrough, lines 300 to 305. Its "Confused Deputy Problem" section, lines 30 to 40, is a third, different attack. The audit's phrase "becomes a confused deputy" was also wrong for the accepting server. Fixed in 4.14.
2. **"No current frontier-model curve of accuracy against tool count was found" was wrong.** Old 4.5. arXiv 2606.17519 was submitted 2026-06-16, before the old dossier. It measures GPT-5.1, GPT-5.4 and Sonnet 4.5 from 51 to 584 tools. Evidence: `tools/enterprise.txt` lines 262, 282 and 311.
3. **"Strict mode checks shape, not meaning" was labelled inferred.** Old 4.3. All three providers state it in their docs. Now verified. Evidence: `tools/a_structured.md`, `tools/g_structured.txt`, `tools/o_structured.txt`. Added: Anthropic does not enforce `minimum`, `maximum`, `minLength` or `maxLength`, and does not guarantee enum casing.
4. **Forced `tool_choice` list was incomplete.** Old 4.2 named Fable 5.1 and Mythos 5.1. Opus 5.5 also returns 400 for `any` and `tool`. Evidence: `tools/a_define.md` line 562.
5. **Hidden tool prompt table updated.** Old 4.1 values for Opus 5, Sonnet 5 and Opus 4.7 are unchanged. Opus 5.5 has only an `auto` and `none` row, 286 tokens. Opus 4.8 and Haiku 4.5 rows added. Evidence: `tools/a_overview.md` lines 869 to 877.
6. **Scanner "average precision 45.53%" lacked its method.** Old 4.8. It is an unweighted mean over nine Table 7 rows. Pooled precision is 276/685 = 40.29%. The mean equals MCPScan's row by coincidence. Evidence: `mcp/papers/2607.11086.txt` line 1540 and Table 7, arithmetic in 4.16.
7. **Claude Code truncation unit.** Old 4.5 said "2KB". The page says "2,048 characters", and the limit also applies to each server's instructions. Evidence: `tools/claudecode_mcp.md` line 1423.
8. **Code execution container facts updated.** Old 4.6 lacked the 5 GiB disk, the `web_fetch_20260209` condition and the 90-second cell limit of `code_execution_20260521`. Evidence: `tools/a_codeexec.md` lines 52, 1106 and 1107.
9. **"Python `mcp` 2.2.0 dual-version behaviour" was listed as unverified.** Old section 11. The MCP report ran `mcp/lab/legacy.py` and saw the legacy handshake accepted. Run output not saved, so it stays "verified by run per the report".
10. **Annotation line numbers.** Old 4.7 cited `schema.ts` lines 1912 to 1954. The MCP report cites 1903 to 1953 for the hint text and defaults. `schema.ts` was not saved, so neither range was re-checked here. 4.12 now cites `mcp/md/tools.md` lines 305 to 306.
11. **Old Lab 5 cost "$1 to $3".** Recomputed as about $1.1 on Haiku 4.5 from today's pricing page. Evidence: `scratchpad/m06_refresh/pricing.md` line 33. The estimate rests on an assumed 100 tokens per tool.
12. **Versions.** `anthropic` 1.6.0 to 1.8.0. `@anthropic-ai/sdk` 0.126.0 to 0.128.0. `openai` 3.14.1 to 3.19.0. `google-genai` 2.24.0 to 2.25.0. `fastmcp` 4.0.4 to 4.0.5. `claude-agent-sdk` 0.2.154 to 0.2.158. Evidence: `scratchpad/m06_refresh/versions.txt`.

### Corrections to the 2026-09-23 research reports, found while merging

1. **The tools report said the LiveMCPBench phrase "nearly half" is gone from v2.** It is still there. `tools/livemcp.txt` line 327 has "retrieval errors account for nearly half of all failures". Line 169 shows the file is v2. The old dossier quote stands. The 50.00% in Appendix I is added beside it.
2. **The tools report said the "reclaimed against checkpointed" disagreement was resolved.** It is not. The code execution page says "checkpointed", `tools/a_codeexec.md` line 1138. The programmatic tool calling page still says "reclaimed after about 5 minutes", `tools/a_ptc.md` lines 460 and 1494. The old dossier's disagreement stands.
3. **The tools report said Google pages return 302 to a login page with a browser user agent.** The URL check today returned 200 for both Google pages with a browser user agent. Evidence: `scratchpad/m06_refresh/url_status.txt`. The behaviour may depend on the request.

### Anchor re-check

52 anchor strings across 4.1 to 4.16 were grepped in the saved source or run files on 2026-09-23. All 52 were found. The list names the concept, the count of matching lines, the file and the string. Files: `scratchpad/m06_refresh/anchors_final.tsv` and `anchors_final.txt`. Numbers that exist only in terminal output of the prototype runs could not be grepped. Section 6 lists them.

Summary: section 4 now holds 16 claims with conditions. Sandboxes moved to Module 7. MCP Apps, open-weight tool calling and the Anthropic mid-conversation tool beta were added. Twelve corrections to the old text and three to today's reports are logged above.

## 14. Corrections found while building the course

The five phases of `tools-mcp` were written, fact-checked and reviewed on 2026-09-23. These facts in this dossier, or in the two research reports, turned out wrong, weaker or incomplete. Run files are in `scratchpad/runs/`. The course text is the current version of each fact.

| # | Dossier or report claim | What the course found | Evidence |
|---|---|---|---|
| 1 | 4.1: the counts 217, 83 and 250 come from the report, run output not saved. Section 11 lists them as not verified | Verified by a re-run. The Qwen3 wrapper is 77 tokens and 84 tokens per tool, measured with synthetic tools of one shape. The tools report's inferred "about 85" wrapper is not used | `tools-mcp_p01_meter_render.txt`, `tools-mcp_p01_meter_sweep.txt`. Phase 1 section 1.1 |
| 2 | 4.3: on Anthropic, strict mode "does not enforce numeric limits" | Stronger than that. A strict schema that contains `minimum`, `maximum`, `minLength`, `maxLength` or array limits beyond 0 or 1 is rejected when sent raw. The SDK helpers can move them into the description. A simple `pattern` is supported | Phase 1 fact check, `a_structured.md` "JSON Schema limitations" and "Pattern support (regex)". `tools-mcp_p01_schema_lint.txt` |
| 3 | 4.3: "Larger schemas return 400" for the 20, 24 and 16 limits | The page names no status code for these three limits. A 400 is inferred. Only the internal grammar limit, "Schema is too complex for compilation", is documented as 400 | `a_structured.md` lines 2964 to 2986. Phase 1 section 1.3 |
| 4 | 4.4: "Precision still fell 8 points, which the authors read as real confusion", in the oracle paragraph | The 68.1% to 60.2% drop is flat routing precision, Table 3. The oracle's own precision is only a curve in Figure 3. So the confusion reading of the oracle rests on the flat figure. Not checked for the oracle | `tools/enterprise.txt` Table 3. Phase 2 section 2.1 |
| 5 | 4.4: "Sonnet 4.5 ran on fold 0 only" | Table 1 says fold 0 only. Table 5 says its flat runs at middle catalog sizes were averaged over three folds. The captions disagree | `tools/enterprise.txt` lines 452 to 454 and 1095 to 1097 |
| 6 | 4.4: LiveMCPBench, "the denominator is 60 failed trajectories" | The shares fit 60, and any multiple of 60 fits too. The paper does not state the count | Arithmetic: 30/60 and 60/120 give the same share. Phase 2 section 2.3 |
| 7 | 4.6: "58 tools used about 55K tokens. Tool search used about 8.7K against 77K, an 85% reduction" | These are two examples in one post. The 85% comes from 50+ MCP tools at about 77,000 tokens, not from the 58-tool setup | `tools/a_advanced.txt` lines 44 and 53 to 61. Phase 2 section 2.3 |
| 8 | Section 11: Gillespie and Perry section 5.4 numbers not read | Read. With GPT-5.4 at 584 tools, a BM25 shortlist scored 32.8% F1 against 42.1% flat. OpenAI hosted tool search with namespaces scored 50.3% | `tools/enterprise.txt` section 5.4. Phase 2 section 2.3 |
| 9 | Section 11: organization of arXiv 2605.24660 not checked | Meta Platforms. Also verified: 23 medium queries, top 5 presence 100% with choice 60.9%, adaptive presence 62.3% with choice 76.8% | `tools/howmany.txt` lines 2042 to 2066. Phase 2 section 2.2 |
| 10 | Section 11: Lab 1 download size and Lab 3 run time not measured | Tokenizer and template files: 15.88 + 27.89 + 17.27 = 61.04 MB. `tool_search.py` finishes in about a second | `tools-mcp_p01_meter_sizes.txt`. Phase 2 writer report |
| 11 | Section 11: Lab 9 outputs and Protected Resource Metadata not checked | Run. `validate_token_resource` unset gave 200 for a foreign-audience token, and True gave 401. The 401 points to `/.well-known/oauth-protected-resource/mcp`, and the SDK served that document | `tools-mcp_p05_aud_table.txt`, `tools-mcp_p05_aud_passthrough.txt`. Phase 5 section 5.3 |
| 12 | Section 11: MRTR state failure on a second worker not checked | Run. A second process with its own key answers `-32602`. With a shared key and an in-memory record in each process, a replay refunds twice across two processes | `tools-mcp_p04_mrtr_all.txt`. Phase 4 section 4.2 |
| 13 | Section 11: annotation defaults at `schema.ts` lines 1903 to 1953 not re-checked | Verified in the saved `schema.ts` at tag 2026-07-28: the hint note at lines 1903 and 1907, and the four defaults in lines 1911 to 1954 | Phase 5 fact check. Phase 5 section 5.1 |
| 14 | Lab designs: whether `mcp` 2.2.0 lets a tool set `_meta` was not checked, with a raw JSON fixture as fallback | The SDK has an Apps extension, `mcp.server.apps.Apps`. Its `tool` decorator sets `_meta.ui`. No JSON fixture was needed | `apps.py:91` in the pinned SDK. `tools-mcp_p04_app_host.txt`. Phase 4 section 4.4 |
| 15 | 4.10: header routing described for the 2026-07-28 path only | In `mcp` 2.2.0 a POST with no `MCP-Protocol-Version` header, or with a handshake version from 2024-11-05 to 2025-11-25, takes the legacy path. That path has no `Mcp-Method` or `Mcp-Name` check. The SDK also checks `Host` before `Origin`, and a foreign `Host` gets HTTP 421 | `streamable_http_manager.py` lines 192 to 198, `transport_security.py` line 116. Phase 4 section 4.3 |
| 16 | 4.15: the default CSP rule | The Apps spec's own example code builds `connect-src 'self'` plus the declared domains. That conflicts with its rule that a host "MUST NOT allow undeclared domains". The course follows the rule | Apps spec at ext-apps v2.0.0, "Content Security Policy Enforcement". Phase 4 section 4.4 |
| 17 | Tools report section 5, Lab 1: the `o200k_base` count of the raw JSON is an approximation for hosted models. The Phase 1 draft added that no open-weight model here uses that tokenizer | The gpt-oss tokenizer gave the same token ids as `o200k_base` on three samples. So the gpt-oss gap against the o200k JSON count comes from the template text | Phase 1 fact check, `tools-mcp_p01_fc/o200k_vs_gptoss.txt` |

Still open after the course: the cost of `tool_removal` on a real bill, what happens when the model calls a withdrawn tool, the date line on a real vLLM prefix cache, the `hermes` parser on a real Llama server, the `openai-harmony` render, the TypeScript SDK audience default and the Felendler figures. Each phase states these as limits.

Summary: 17 facts were corrected, sharpened or resolved while building the course. The open items above stay labelled as not checked in the phases.
