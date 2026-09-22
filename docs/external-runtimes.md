# Running an agent through Codex or Claude Code

Mission HQ runs its own agents in-process, where every tool call passes the
registry's gates. One thing that loop cannot do is reach a browser you are
signed into, because that needs a browser extension and Mission HQ has no
browser of its own.

Two runtimes cover that one case. `runtime: codex` hands the task to the Codex
CLI, which drives your Chrome through the ChatGPT extension. `runtime: claude`
does the same through Claude Code and the Claude in Chrome extension.

Which one a machine can use is a fact about that machine, not a preference: a
managed laptop may allow one extension and block the other. The `operator`
agent ships on `codex`; change one line in its `job.md` to use `claude`.

## Setup, on a machine you control

1. **Install the CLI** and sign in: Codex, or Claude Code.
2. **Install that product's Chrome extension**, in the profile holding the
   logins you want read. A managed work laptop may block one or both.
3. **Check the browser is reachable**, with Chrome open:

   ```bash
   codex exec --skip-git-repo-check "Use your browser tool and tell me what tabs are open"
   ```

   A list of your tabs means it works. "Browser is not available" or
   `NO_BROWSER_TOOL` means step 2 is incomplete, and nothing else will work
   until it is.
4. **Switch the runtime on** in `backend/.env`:

   ```
   CODEX_RUNTIME_ENABLED=true
   ```

   If Codex on that machine defaults to a provider it cannot reach headlessly,
   point it somewhere it can:

   ```
   CODEX_CONFIG=model_provider=grid,model=open-fast
   ```
5. **Activate the operator agent.** It ships as a draft. Open it in the console
   under Agents, or set `status: active` in `agents/operator/job.md`, then
   restart the backend.

## What happens on a run

1. You create a task for `operator`, from the board or from chat.
2. Mission HQ opens **one approval ticket for the whole run** and waits. The
   in-process loop asks per tool call because it sees each one; this runtime
   cannot, so the unit of consent is the run, and the ticket shows the task.
3. On approval it starts the CLI. One turn per run: the CLI loops
   internally as much as its turn cap allows, but Mission HQ does not yet send
   a follow-up. The session id makes that a small change later, because
   `--resume` would still have everything the first turn read.
4. Claude reads pages in your browser and returns text.
5. **Mission HQ writes that text** into `quarantine/`, through the same
   `memory.write` every agent uses: same provenance stamp, same path scope,
   committed with that night's other vault writes.
6. The run appears under Runs with its real cost. That cost is dollars on your
   Claude account, not gateway tokens.

## What the external process may do

This differs between the two, and it matters.

**Claude Code** takes `--allowedTools`, and in headless mode an unlisted tool
is **refused, not prompted for**. That one line is the whole permission model.

**Codex has no tool allowlist.** The boundary there is `--sandbox read-only`:
model-generated commands cannot write to disk. It can still read and search.
So on Codex the approval ticket before the run, and the fact that Mission HQ
does all the writing, are carrying more of the weight.

Neither can write to your vault. Mission HQ does that.

The agent-level rules apply too. A `runtime: claude` agent is treated as a web
reader by the trifecta validator at load time, so it may hold no outward tool,
no `notify_owner`, no `create_subtask`, and no vault scope except
`quarantine/**`. Getting that wrong stops the agent loading, loudly.

## What it will not do

Bulk collection from a social platform. Reading a page you have open is your
own browsing; walking a hundred profiles is not, and it is the account you are
signed into that carries the risk. Use those platforms' APIs for anything at
volume. `operator`'s manifest says this, and it is the reason the rule exists
rather than a suggestion.

## When something is wrong

Each failure names itself rather than looking like a failed agent.

| What you see | What it means |
|---|---|
| `the codex runtime is switched off` | `CODEX_RUNTIME_ENABLED` is false |
| `the codex CLI ... is not on this machine's PATH` | Not installed. The ChatGPT app bundles a copy and it is found automatically; otherwise set `CODEX_CLI_PATH` |
| `the codex CLI failed: Missing environment variable ...` | Its default provider only works inside the desktop app. Set `CODEX_CONFIG` to one it can reach |
| `the codex browser extension is not connected` | Step 2 is incomplete. The CLI answers normally with no browser, so this is detected and the run is blocked rather than filed as a success |
| `the reply named no source URL, so it was not filed` | A quarantine note must cite its sources, so an answer that names no page is reported but not written |

## Turning it off

`CODEX_RUNTIME_ENABLED=false` (or `CLAUDE_RUNTIME_ENABLED=false`) blocks any such run with a readable reason. The
in-process agents are untouched by any of this.
