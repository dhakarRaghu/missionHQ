# Running an agent through Claude Code

Mission HQ runs its own agents in-process, where every tool call passes the
registry's gates. One thing that loop cannot do is reach a browser you are
signed into, because that needs a browser extension and Mission HQ has no
browser of its own.

The `claude` runtime covers that one case. It hands a task to the Claude Code
CLI, which drives your real Chrome through the Claude in Chrome extension.

## Setup, on a machine you control

1. **Install Claude Code** and sign in.
2. **Install the Claude in Chrome extension**, in the Chrome profile that holds
   the logins you want read. Extension id `fcoeoabgfenejglbffodgkkbkcdhcgfn`.
   A managed work laptop may block this; a personal one will not.
3. **Check it is connected.** With Chrome open:

   ```bash
   claude -p --chrome --allowedTools "mcp__claude-in-chrome__*" \
     "Open example.com and reply with its title."
   ```

   "Browser extension is not connected" means step 2 is incomplete.
4. **Switch the runtime on** in `backend/.env`:

   ```
   CLAUDE_RUNTIME_ENABLED=true
   ```
5. **Activate the operator agent.** It ships as a draft. Open it in the console
   under Agents, or set `status: active` in `agents/operator/job.md`, then
   restart the backend.

## What happens on a run

1. You create a task for `operator`, from the board or from chat.
2. Mission HQ opens **one approval ticket for the whole run** and waits. The
   in-process loop asks per tool call because it sees each one; this runtime
   cannot, so the unit of consent is the run, and the ticket shows the task.
3. On approval it starts `claude -p --chrome`, with the run id as the session
   id, a turn cap, and a hard dollar ceiling. One turn per run: the CLI loops
   internally as much as its turn cap allows, but Mission HQ does not yet send
   a follow-up. The session id makes that a small change later, because
   `--resume` would still have everything the first turn read.
4. Claude reads pages in your browser and returns text.
5. **Mission HQ writes that text** into `quarantine/`, through the same
   `memory.write` every agent uses: same provenance stamp, same path scope,
   one git commit.
6. The run appears under Runs with its real cost. That cost is dollars on your
   Claude account, not gateway tokens.

## What the external process may do

Only the tools in `CLAUDE_ALLOWED_TOOLS`, which defaults to the browser tools.
In headless mode an unlisted tool is **refused, not prompted for**, so that one
line is the whole permission model for that process. It cannot write a file,
run a command, or send anything.

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
| `the claude runtime is switched off` | `CLAUDE_RUNTIME_ENABLED` is false |
| `the claude CLI ... is not on this machine's PATH` | Claude Code is not installed, or set `CLAUDE_CLI_PATH` to its full path |
| `the Claude in Chrome extension is not connected` | Step 2 is incomplete. The CLI answers normally with no browser, so this is detected and the run is blocked rather than filed as a success |
| `the reply named no source URL, so it was not filed` | A quarantine note must cite its sources, so an answer that names no page is reported but not written |

## Turning it off

`CLAUDE_RUNTIME_ENABLED=false` blocks any such run with a readable reason. The
in-process agents are untouched by any of this.
