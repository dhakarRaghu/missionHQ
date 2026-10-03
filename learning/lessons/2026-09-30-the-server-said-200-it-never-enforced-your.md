In Phase 2B you saw that constrained decoding makes output legal without making it complete: the grammar stops invalid JSON, but it does not know which fields your application needs. Now look at a failure one step earlier. Your agent calls two stateful tools in order: write_file, then compile. You set parallel_tool_calls=false so the server cannot return both calls in one turn, because running them together corrupts the state. The request returns HTTP 200. The response is well-formed. The tool calls array holds two calls.

The server did not reject your parameter. The output was valid JSON. Every signal you normally trust said the request worked. Yet the constraint you set was never applied at all, and nothing in the response told you. So before your agent executes any tool call, you need a way to answer one question: when a serving stack accepts a constraint parameter without an error, how do you know whether it acted on it or only read it and moved on?

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- A constraint parameter an OpenAI-compatible server accepts without error is not enforced; parse, honor and reject are three separate behaviors, and silence means the first only. Decide which constraints you must re-check in your own layer before executing tool calls, and which engine flags he can trust.

## What did the caller see, and what did the engine do?

A server that silently ignores your constraint returns the same 200 as one that enforces it.

Your agent has two stateful tools: write_file, then compile. Running them in the wrong order corrupts the state, so you set parallel_tool_calls=false. The response arrives with HTTP 200. It has a well-formed tool_calls array holding two calls. The same failure was measured in a public bug report. SGLang 0.5.1.post1, serving Qwen3-30B-A3B on eight H20 GPUs, returned finish_reason='tool_calls'. It sent two calls in one turn, to an add tool and a multiply tool, despite the flag.

To read this failure you need three behaviors, because a constraint parameter can meet three fates. The server can parse it: read the field, see it is valid, move on. It can honor it: change what the engine produces. It can reject it: return a 400 saying "not supported". Your instinct says parse implies honor, so silence means safety. It does not. Silence proves parse only, and that space between accepted and acted-on is the accepted-not-enforced gap: the parameter crossed the API layer and never reached the engine.

Predict: you send parallel_tool_calls=false and get a 200 with two tool calls. Where was the constraint dropped, and what told you?It was dropped between the API layer that parsed the request and the decoding engine that produced the tokens. Nothing told you: no error, no warning, no log line. The only signal in this incident was the maintainer's reply. HTTP 200 proves parse, never honor.

parallel_tool_calls=false
API layer: parsed

-
engine
no arrow. nothing enforces it.

-
response_format (JSON schema)
API layer: parsed

-
grammar FSM in the decoder

-
legal tokens only

The same request path, two parameters. A grammar parameter is wired into decoding; the tool-call flag stops at the API layer. Enforced versus parsed looks identical from the client. Illustration, not measured.

The contrast in the figure is real. A grammar parameter feeds constrained decoding, the technique from section 2.5 where a grammar filters each token the model may emit so the output stays valid. SGLang does that for JSON schemas. The tool-call flag got no such wiring. The reporter's first theory was the model, a reasonable guess: he tested GLM-4.5 and DeepSeek models, saw the same behavior, and corrected himself, because three unrelated models failing identically points to the serving layer.

There was no log to trace. The locating signal was a human sentence. A maintainer wrote: "Chat completion doesn't support this field yet, but I'll add support for it." Trying the Responses API path returned a 500, which confirmed the field had no working path anywhere. The thread ended with no fix: a bot auto-closed the issue as state_reason: "completed" in January 2026 while it was still reproducible on main in July 2026, so anyone skimming the tracker reads a hazard as resolved.

EvidenceSGLang issue #9696, read in full: reporter on SGLang 0.5.1.post1, Qwen3-30B-A3B, 8x H20; maintainer quote and the bot auto-close fields (closed_by: github-actions[bot], state_reason: "completed", 2026-01-05) verified from the GitHub API. Reproduced on latest main by riZZZhik in July 2026.

A 200 with valid output proves the constraint was parsed, never that it was honored.

"No error and valid JSON means applied": that belief executes two stateful tools in parallel.

Open the params file of your client library and list the constraint fields it accepts; ask which ones your engine enforces.

The maintainer's fuller answer came next: "whether tools are invoked in parallel is determined by the model." That defense sounds like impossibility, and it is only half true. The next section asks why the engine could not just keep the promise, and finds two places enforcement could already live.

## Why couldn't the engine just keep the promise?

The constraint vanished between the API layer and the engine, and the maintainer said the model decides parallelism. That is only half an answer, and this section finds the other half: two places enforcement could already live.

Return to your agent, where write_file must finish before compile starts. If the engine truly cannot keep the parallel_tool_calls=false promise, you must build the check yourself. If it can but did not, the gap is a choice, and you should know which case you are in.

The maintainer's claim has a true core. Emitting one call per turn is not a sampling property the base model exposes, because no model has a setting for it. He said so directly: "As far as I'm aware, no model currently provides explicit support for this functionality." So an engine cannot forward the flag to the model and be done.

But the engine sits between the model and you, and it has two places to act. The first is decode-level enforcement, where a grammar filters the tokens the model may emit at each decode step. You met this as constrained decoding in the section on structured output. And SGLang already uses it to guarantee valid JSON via xgrammar. A grammar that closes the tool_calls array after one call makes two calls unreachable at the token level.

- model proposes tokensscores for the whole vocabulary at each step

- grammar masksafter one complete call, every token except the array's close is removed

- one call survivesthe response can hold at most one tool call, by construction

That strength has a price, and you have seen it before. It is the constraint tax, the extra latency and complexity a grammar adds to every decoded token, because the mask is rebuilt at each step. In Phase 2B you paid it for valid JSON. For one-call-per-turn you would pay it across the whole response.

The second place is cheaper and needs no grammar at all. It is the post-filter backstop: generate as usual. Then drop every tool call but the first before the response leaves the engine. A community member proposed exactly this in the issue thread, motivated by race safety for stateful tools. It costs a few lines of code and one pass over an array that is already parsed.

  Say it is impossible"The model decides" ends the conversation. The two calls ship. Your compile runs against a file that may not exist yet.

  Pick an enforcement pointDecode-level grammar: strong, pays the constraint tax per token. Post-filter: cheap, and the order of the surviving call is the same one the model emitted first.

So the gap in SGLang was wiring, not physics, and the same gap appears across the ecosystem. The vLLM v0.11.0 tool-calling docs enforce tool_choice through structured output but document no enforcement of the parallel_tool_calls flag. Switching engines does not buy you the guarantee.

EvidencevLLM docs/features/tool_calling.md at tag v0.11.0, read in full. It covers auto, required and none, and mentions parallel calls only as a model-capability limit. Enforcement could exist undocumented in code; it was not checked there.

"The model decides" is half true: a grammar or a post-filter enforces the flag, both already exist in engines.

Treating an unenforced flag as engine impossibility means you never build the check that was always yours.

Read your engine's tool-calling docs end to end and write down which request flags it actually wires into decoding.

So enforcement is possible, and your engine provides neither path. The next section asks what that changes in your own agent: where the check goes, and what to assert on instead of the status code.

## What does this change in your own agent?

Enforcement will not come from your engine, so the check lives in code you own.

The section above named two places enforcement could live. They are a decode-level grammar and a post-filter backstop that drops every tool call after the first. Your engine provides neither, so the surviving option is the layer between the response and your executor.

Your agent runs write_file and then compile, and that order is the safety property. When two calls arrive in one turn, compile can run before write_file finishes. Then the compile step reads a half-written file. You set parallel_tool_calls=false to buy that ordering, and the section above showed the flag was never wired into the engine.

The fix is an output-level invariant check, a rule about the response's shape that your code verifies before anything executes. The rule is one line of logic: if the response carries more tool calls than the turn allows, reject it or keep the first and drop the rest. Because the check runs on the parsed response, it works whatever the engine does with the flag.

def enforce_single_call(msg):
    calls = msg.tool_calls or []
    if len(calls) > 1:
        log.warn("dropped %d extra tool calls", len(calls) - 1)
        msg.tool_calls = calls[:1]
    return msg

This is the community member's proposal from the incident thread, written as six lines. It is also the cheapest of the two enforcements from the section above: no grammar, no per-token constraint tax. The surviving call is the one the model emitted first.

One detail from the incident belongs in your parser too. The returned calls had index=None, a second spec deviation. Some client libraries mis-handle it when you push tool results back into one message. Check the field before you trust it.

The same shift applies to your tests. A conformance test that asserts on HTTP 200 passed in the incident while the constraint was violated, because 200 only says the response parsed. Assert on the output instead: send a prompt that invites two calls, and fail the test when two come back. Each new flag and each engine upgrade then gets its own output assertion. Then the accepted-not-enforced gap becomes a test failure instead of a race condition.

Treat engine constraint flags as hints; enforce the invariant in the layer that executes.

Testing that the request returned 200 passes while the constraint is silently ignored.

Send one prompt inviting write_file and compile, count the tool_calls that come back (the lab does this).

Then add the guard above to your executor and send the same prompt again. The count drops to one, and the "dropped 1 extra tool calls" warn line fires exactly once. That pair of observations is the proof that the gap was real and that your layer now closes it.

You can now read every constraint parameter on a request as a claim, not a guarantee. When you read constrained decoding and the constraint tax in section 2.5, read it as a capability. An engine can have it, and read this incident as one that was accepted and never wired in. The recall section below collects the claims from all three sections.

## Lab: prove the gap in fifteen minutes

The sections above gave you two defenses. One is an output-level invariant check in your own layer. The other is the habit of treating every constraint parameter as a hint. This lab turns both into one script you run against every model you serve.

-  E1 self-hosted
The assertion, not the 200, is the test. Write a roughly 30-line client that proves or disproves the accepted-not-enforced gap on your own stack. It sends a chat completion with two tools, parallel_tool_calls=false, and a prompt that invites both tools. Then it asserts on the raw response: at most one tool call came back.

The shape of the test:

import json, requests

TOOLS = [
    {"type": "function", "function": {
        "name": "write_file",
        "parameters": {"type": "object",
            "properties": {"path": {"type": "string"},
                           "content": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "compile",
        "parameters": {"type": "object",
            "properties": {"path": {"type": "string"}}}}},
]

resp = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "your-model",
        "messages": [{"role": "user", "content":
            "Write hello.c printing hi, then compile it."}],
        "tools": TOOLS,
        "parallel_tool_calls": False,
    },
)
body = resp.json()
calls = body["choices"][0]["message"].get("tool_calls", [])
assert resp.status_code == 200, body
assert len(calls) <= 1, (
    f"server ignored parallel_tool_calls=false: "
    f"{json.dumps(body, indent=2)}")

Run: python check_parallel_calls.py

Expected on an enforcing engine: the script exits cleanly. One call, or zero.

Expected where the gap exists: an AssertionError printing the full raw response, with two entries in tool_calls. On SGLang 0.5.1.post1 this is what the incident reporter saw: finish_reason='tool_calls' and two calls in one turn.

-  E2 self-hosted
Check the second deviation. Extend the assertion to the index field. The OpenAI spec gives every parallel call an integer index, and the incident response had index=None. Assert each returned call has an integer index if more than one comes back. Some client libraries mis-handle None, so catching it here is cheaper than debugging tool-result assembly later.

-  E3 self-hosted
Run it everywhere, and re-run it after upgrades. The gap is per-parameter and per-version. Point the same script at every model you serve, and keep it in your conformance suite so an engine upgrade that rewires the field cannot pass unnoticed. When the test starts passing, the engine has earned your trust for this flag, and not before.

If a run fails, you now hold a reproduction in 30 lines. Keep the raw response it printed: that output, not the assertion message, is what an engine maintainer needs to see.

## Checkpoint

Earlier sections gave you three ideas: an accepted parameter is not an enforced one, enforcement can live at decode level or as a post-filter, and the only layer you fully control is your own. This checkpoint asks you to use all three at once.

Scenario. Your teammate proposes switching your agent's serving engine. The reason: the current one ignores parallel_tool_calls=false, and your agent runs write_file then compile, two stateful calls that must stay in order. The new engine's README lists the flag as supported. Before the switch, what do you check, and where does the real guarantee have to live?

Answer sketch
You check three things, in this order.

- Reproduce, do not read. Run the 30-line assertion client from the lab against the new engine: two tools, parallel_tool_calls=false, a prompt inviting two calls. A README line is a claim. The assertion on the raw response is evidence. The vLLM v0.11.0 docs showed no documented enforcement, so "supported" often means "parsed".

- Ask which level enforces it. Decode-level enforcement, where a grammar stops generation after one call, survives any prompt. Prompt-level hints can be overridden by a long or unusual context. If the engine cannot say which one it does, treat it as prompt level.

- Keep your own check either way. The post-filter backstop, dropping every call after the first before execution, stays in your agent after the switch. The engine flag is a hint. Your output-level invariant is the guarantee, because the next engine upgrade can silently un-wire the flag, the same way the SGLang issue was auto-closed as "completed" while still broken.

The one-line version: switch if the new engine passes your test, but never move the guarantee out of your layer.

Next, two things you could post from what this lesson showed.

## What you could post

Two posts this lesson earns, each one claim you can stand behind.

"I set parallel_tool_calls=false. The server sent 200 and two calls."

The claim: a constraint parameter that the server accepts is not enforced. The proof is one 30-line client that asserts on the output. Post it only after you run the lab against your own stack. Then the post names your engine, its version and the raw response you saw, instead of quoting someone else's bug report.

"A bot closed this bug as completed. It still reproduces."

The claim: a closed issue with state reason "completed" can hide a live bug. So triage by evidence, not by state. Post it after you read the SGLang thread yourself: the maintainer quotes, the auto-close and the three comments after it. Then you can say what it means for anyone reading an engine's tracker.

Both posts carry one habit: assert on outputs, not status codes or issue states.

## Sources

- SGLang issue #9696: the incident thread. It gave the original report on 0.5.1.post1, the reporter's correction after testing GLM-4.5 and DeepSeek, both maintainer replies, the post-filter proposal, and the bot auto-close with state_reason: "completed" on 2026-01-05. It also gave the three later comments: riZZZhik confirming the bug still reproduces on main, and AdemFr noting the linked PR was closed and asking to reopen.

- openai-python v1.99.1 params file: shows parallel_tool_calls is a documented first-class field in the reference client, not an exotic parameter SGLang invented.

- vLLM v0.11.0 tool-calling docs: documents enforcement for tool_choice but no documented enforcement of parallel_tool_calls. Absence in the docs is not proof of absence in the engine.

- OpenAI community thread: engineers with ordered stateful tools, write file then compile, are told to set parallel_tool_calls=false. It shows the flag is load-bearing in real designs, which is why silent non-enforcement is a hazard.