"""Run one agent turn through the Claude Code CLI.

Why this exists: an extension runs *inside* the browser the owner is signed
into, which is the only way to read a page that needs a real logged-in session.
Mission HQ cannot install an extension into its own headless world, so for that
one job it asks Claude Code, which can.

What it gives up: the in-process loop checks every tool call as it happens.
A CLI run is a box with a lid — approve before, read after. Three rules make
that trade safe, and all three are enforced here rather than asked for in a
prompt:

1. **Read only.** The child process is started with an allowlist of browser
   tools. In headless mode an unlisted tool is refused, not prompted for, so
   the process cannot write a file, run a command or edit anything.
2. **Mission HQ owns the writing.** The child returns text. The caller writes
   it into the vault through ``memory.write``, so provenance, path scopes,
   caps and the one-commit-per-write rule all still apply.
3. **Approved before it starts.** Driving a browser the owner is signed into
   is an outward act, so ``engine`` opens a ticket first. That gate lives at
   the call site because it must block the workflow, not this module.

Cost is real money on the owner's Claude account, not gateway tokens, so it is
read from the CLI's own report and passed through unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from hq.config import settings

log = logging.getLogger(__name__)

# The CLI prints one JSON object with these keys. Anything else means a
# version we have not seen, and the caller treats that as a failed run.
_RESULT_KEYS = {"result", "is_error"}


class ClaudeRuntimeError(RuntimeError):
    """The CLI could not be run, or answered with something unusable."""


@dataclass(frozen=True)
class ClaudeResult:
    text: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    turns: int
    session_id: str
    is_error: bool


def available() -> str | None:
    """The reason this runtime cannot be used, or None when it can."""
    cfg = settings()
    if not cfg.claude_runtime_enabled:
        return "the claude runtime is switched off (CLAUDE_RUNTIME_ENABLED=true)"
    if not cfg.claude_cli_path:
        return "CLAUDE_CLI_PATH is empty"
    return None


def _usage(payload: dict[str, Any]) -> tuple[int, int]:
    """Input and output tokens, counting cache reads as input.

    Cached input is still input the model saw; leaving it out would make a
    resumed run look far cheaper than it was.
    """
    usage = payload.get("usage") or {}
    read = int(usage.get("cache_read_input_tokens") or 0)
    written = int(usage.get("cache_creation_input_tokens") or 0)
    return (
        int(usage.get("input_tokens") or 0) + read + written,
        int(usage.get("output_tokens") or 0),
    )


async def run_turn(
    prompt: str,
    *,
    session_id: str,
    resume: bool = False,
    system_suffix: str = "",
) -> ClaudeResult:
    """One turn. ``resume`` continues the session of the same id.

    A session id is the run id, so a follow-up keeps everything the first turn
    read. Without that, asking "you missed X" would reopen every page.
    """
    reason = available()
    if reason:
        raise ClaudeRuntimeError(reason)
    cfg = settings()

    argv = [
        cfg.claude_cli_path,
        "-p",
        prompt,
        "--chrome",
        "--output-format",
        "json",
        "--allowedTools",
        cfg.claude_allowed_tools,
        "--max-turns",
        str(cfg.claude_max_turns),
        "--max-budget-usd",
        str(cfg.claude_max_budget_usd),
    ]
    argv += ["--resume", session_id] if resume else ["--session-id", session_id]
    if system_suffix:
        argv += ["--append-system-prompt", system_suffix]

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        raw, err = await asyncio.wait_for(
            proc.communicate(), timeout=cfg.claude_timeout_s
        )
    except FileNotFoundError as exc:
        raise ClaudeRuntimeError(
            f"claude CLI not found at {cfg.claude_cli_path!r}. Install it, or set"
            " CLAUDE_CLI_PATH in .env."
        ) from exc
    except TimeoutError as exc:
        raise ClaudeRuntimeError(
            f"the claude CLI did not finish within {cfg.claude_timeout_s:.0f}s"
        ) from exc

    if proc.returncode != 0:
        detail = (err or b"").decode(errors="replace").strip()[:300]
        raise ClaudeRuntimeError(
            f"the claude CLI exited {proc.returncode}: {detail or 'no output'}"
        )

    try:
        payload = json.loads((raw or b"").decode(errors="replace"))
    except json.JSONDecodeError as exc:
        raise ClaudeRuntimeError("the claude CLI did not answer with JSON") from exc
    if not isinstance(payload, dict) or not _RESULT_KEYS & payload.keys():
        raise ClaudeRuntimeError("the claude CLI answered in an unexpected shape")

    tokens_in, tokens_out = _usage(payload)
    return ClaudeResult(
        text=str(payload.get("result") or ""),
        cost_usd=float(payload.get("total_cost_usd") or 0.0),
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        turns=int(payload.get("num_turns") or 0),
        session_id=str(payload.get("session_id") or session_id),
        is_error=bool(payload.get("is_error")),
    )
