"""Run one agent turn through the Codex CLI.

Same job as ``claude_cli`` and the same trade: an external agent CLI can reach
a browser the owner is signed into, through that product's Chrome extension,
which Mission HQ's own loop cannot. Which one to use is a per-machine fact,
not a design choice, so both adapters exist and an agent names one.

Two differences from the Claude adapter, both of which change what is safe:

* **No tool allowlist.** Claude Code takes ``--allowedTools`` and refuses
  anything unlisted. Codex has no equivalent, so the boundary here is
  ``--sandbox read-only``: model-generated commands cannot write to disk. It
  can still read and search. The approval ticket before the run, and the fact
  that Mission HQ does all the writing, carry more weight because of this.
* **No budget flag.** Claude Code takes ``--max-budget-usd``. Codex does not,
  so the only ceiling is the timeout. Codex runs on the owner's ChatGPT plan
  rather than per-token billing, so the recorded cost is 0 and the token
  counts are what the run actually consumed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from hq.config import settings

log = logging.getLogger(__name__)

# Codex ships inside the ChatGPT desktop app as well as standalone, and the
# app's copy is not on PATH. A machine with either one can run this.
_CLI_FALLBACKS = (
    Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
    Path.home() / ".local/bin/codex",
    Path("/opt/homebrew/bin/codex"),
    Path("/usr/local/bin/codex"),
)

# Codex answers normally when its browser backend is absent, so a run that
# reached no page would otherwise look like a successful answer.
#
# Exact phrases were not enough. The list below started as literal strings and
# missed "Browser unavailable." — two words, no verb, and the run was filed as
# a success. The model paraphrases its own failure, so match the shape of the
# sentence rather than its wording: something browser-ish near something
# absent-ish, in either order.
_BROWSER_WORD = r"(?:browser|chrome|browser extension|cua_repl)"
_ABSENT_WORD = (
    r"(?:unavailable|not available|no longer available|not connected|"
    r"unreachable|cannot be reached|could not connect|unable to reach|"
    r"could not reach|failed to (?:reach|connect|start)|"
    r"isn'?t available|isn'?t connected|not supported|unsupported|"
    r"cannot open|could not open|unable to open|cannot inspect|was denied)"
)
_NO_BROWSER_RE = re.compile(
    rf"(?:\bno\s+{_BROWSER_WORD}\b)"                 # "no browser is available"
    rf"|(?:{_BROWSER_WORD}.{{0,30}}?{_ABSENT_WORD})"   # "browser is not available"
    rf"|(?:{_ABSENT_WORD}.{{0,30}}?{_BROWSER_WORD})",  # "unable to reach the browser"
    re.IGNORECASE,
)
# Kept verbatim because they do not fit the shape above.
_NO_BROWSER_EXACT = (
    "no_browser_tool",
    "native messaging host",
    "tool is not currently supported or available",
    # 2026-09-16/17: the extension lost its sign-in. Codex said so without
    # the word "browser" near it — "Codex auth token is unavailable" — or
    # talked about a "signed-in browser tab" it "cannot open", and three
    # feed runs were filed as no_artifact instead of this clear block.
    "auth token is unavailable",
    "computer use was not approved",
)


class CodexRuntimeError(RuntimeError):
    """The CLI could not be run, or answered with something unusable."""


@dataclass(frozen=True)
class CodexResult:
    text: str
    input_tokens: int
    output_tokens: int
    session_id: str
    is_error: bool


def missing_browser(text: str) -> bool:
    """True when Codex answered without ever reaching a browser."""
    low = text.lower()
    if any(phrase in low for phrase in _NO_BROWSER_EXACT):
        return True
    return _NO_BROWSER_RE.search(low) is not None


def resolve_cli() -> str | None:
    """Absolute path to the codex CLI, or None when it cannot be found."""
    configured = settings().codex_cli_path
    if not configured:
        return None
    if "/" in configured:
        return configured if Path(configured).exists() else None
    found = shutil.which(configured)
    if found:
        return found
    return next((str(p) for p in _CLI_FALLBACKS if p.exists()), None)


def available() -> str | None:
    """The reason this runtime cannot be used, or None when it can."""
    cfg = settings()
    if not cfg.codex_runtime_enabled:
        return "the codex runtime is switched off (CODEX_RUNTIME_ENABLED=true)"
    if resolve_cli() is None:
        return (
            f"the codex CLI ({cfg.codex_cli_path!r}) is not on this machine's"
            " PATH. Install Codex, or set CODEX_CLI_PATH in .env to its full"
            " path (the ChatGPT app bundles one)."
        )
    return None


def _parse_events(raw: str) -> tuple[int, int, str, str]:
    """``(input tokens, output tokens, session id, error message)`` from JSONL.

    Unparseable lines are skipped rather than fatal: the CLI also writes plain
    log lines to stdout, and one of those must not lose a whole run's usage.
    """
    tokens_in = tokens_out = 0
    session_id = ""
    # Codex reports why a turn failed in the stream. Without this the caller
    # only sees "exited 1", which says nothing about a missing key or a model
    # the account cannot reach.
    error = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = str(event.get("type") or "")
        if "error" in kind and not error:
            detail = event.get("error")
            if isinstance(detail, dict):
                error = str(detail.get("message") or "")
            error = error or str(event.get("message") or "")
        if not session_id:
            # Codex names it thread_id on thread.started; older builds used
            # session_id. Take whichever the stream offers.
            session_id = str(
                event.get("thread_id")
                or event.get("session_id")
                or (event.get("session") or {}).get("id")
                or ""
            )
        if kind == "turn.completed":
            usage = event.get("usage") or {}
            # Cached input is still input the model saw.
            tokens_in += int(usage.get("input_tokens") or 0)
            tokens_out += int(usage.get("output_tokens") or 0)
    return tokens_in, tokens_out, session_id, error


async def run_turn(
    prompt: str, *, session_id: str | None = None, workdir: str | None = None
) -> CodexResult:
    """One turn. ``session_id`` resumes an earlier one.

    Unlike Claude Code, Codex assigns the session id itself, so a first turn
    reports the id to resume rather than being told one.
    """
    reason = available()
    if reason:
        raise CodexRuntimeError(reason)
    cfg = settings()
    cli = resolve_cli()
    if cli is None:  # pragma: no cover - available() checked this already
        raise CodexRuntimeError("the codex CLI could not be found")

    # --output-last-message is the reliable way to get the final answer; the
    # JSONL stream is for usage and errors.
    fd, out_path = tempfile.mkstemp(prefix="hq-codex-", suffix=".txt")
    os.close(fd)
    argv = [cli, "exec", "--json", "--skip-git-repo-check",
            "--sandbox", "read-only", "--output-last-message", out_path,
            "--cd", workdir or str(settings().vault_dir)]
    if cfg.codex_model:
        argv += ["-m", cfg.codex_model]
    for pair in (p.strip() for p in cfg.codex_config.split(",")):
        if pair:
            argv += ["-c", pair]
    if session_id:
        argv += ["resume", session_id, prompt]
    else:
        argv.append(prompt)

    try:
        # Forward whatever provider key Codex needs. The backend runs under
        # launchd, which does not source a login shell, so a key exported in
        # ~/.zshrc reaches the terminal and not this process. Anything unset
        # in .env is left alone rather than blanked, so a machine that really
        # does inherit the key from its environment still works.
        # Codex's own `grid` provider reads GRID_API_KEY, while Mission HQ
        # calls the same gateway through GATEWAY_API_KEY. One gateway, one
        # key, two names, so fall back rather than making the owner paste the
        # same secret into .env twice and keep both in step.
        grid = cfg.grid_api_key or (
            cfg.gateway_api_key if "grid" in cfg.gateway_base_url else ""
        )
        forwarded = {
            "GRID_API_KEY": grid,
            "AZURE_OPENAI_API_KEY": cfg.azure_openai_api_key,
            "OPENAI_API_KEY": cfg.openai_api_key_for_codex,
        }
        present = {k: v for k, v in forwarded.items() if v}
        child_env = {**os.environ, **present} if present else None
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=child_env,
        )
        try:
            raw, err = await asyncio.wait_for(
                proc.communicate(), timeout=cfg.codex_timeout_s
            )
        except TimeoutError:
            # Cancelling the await does not stop the child. Kill it, or it
            # keeps the browser and keeps working.
            proc.kill()
            await proc.wait()
            raise
    except FileNotFoundError as exc:
        raise CodexRuntimeError(f"codex CLI not found at {cli!r}") from exc
    except TimeoutError as exc:
        raise CodexRuntimeError(
            f"the codex CLI did not finish within {cfg.codex_timeout_s:.0f}s"
        ) from exc
    finally:
        text = ""
        try:
            text = Path(out_path).read_text().strip()
        except OSError:
            pass
        Path(out_path).unlink(missing_ok=True)

    stdout = (raw or b"").decode(errors="replace")
    tokens_in, tokens_out, sid, error = _parse_events(stdout)
    if proc.returncode != 0:
        detail = error or (err or b"").decode(errors="replace").strip()[:300]
        raise CodexRuntimeError(
            f"the codex CLI failed: {detail or 'no output'}"
        )

    return CodexResult(
        text=text,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        session_id=sid or (session_id or ""),
        is_error=bool(error) and not text,
    )
