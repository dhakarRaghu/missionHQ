"""Content ideas, filed by code.

The ideas file is newest-first and grows every week; it passed 38k characters
in September 2026. Rewriting it through `vault_write` meant either sending the
whole file as one tool argument, which the gateway does not stream, or
sending only the new batch and wiping the rest. So sage writes the batch as
the text of its reply and this tool puts it at the top of the file.
"""

from __future__ import annotations

import asyncio
import re

from pydantic_ai import ModelRetry, RunContext

from hq import memory
from hq.obs import emit
from hq.safety import ActionClass
from hq.tools.learning_tools import _today, reply_text
from hq.tools.registry import HQDeps, hq_tool

IDEAS_PATH = "projects/content/ideas.md"
MAX_IDEAS = 8
_IDEA = re.compile(r"^(?:- |\d+\. )", re.MULTILINE)


def batch_problems(text: str) -> list[str]:
    n = len(_IDEA.findall(text))
    if n == 0:
        return ["no ideas found: write each idea as a top-level '- ' bullet"]
    if n > MAX_IDEAS:
        return [f"{n} ideas; keep the {MAX_IDEAS} strongest at most, two real ones beat five"]
    return []


def with_batch(existing: str | None, batch: str, day: str, title: str) -> str:
    """The file with `batch` as the newest dated section, under the title."""
    lines = batch.strip().splitlines()
    if lines and lines[0].startswith("## "):
        lines = lines[1:]
    heading = f"## {day}" + (f" — {title.strip()}" if title.strip() else "")
    section = heading + "\n\n" + "\n".join(lines).strip() + "\n"
    if not existing:
        return "# Content ideas\n\n" + section
    meta, body = memory.parse_frontmatter(existing)
    head = existing[: len(existing) - len(body)] if meta else ""
    body_lines = body.splitlines()
    at = next((i for i, ln in enumerate(body_lines) if ln.startswith("# ")), -1)
    top = "\n".join(body_lines[: at + 1]).rstrip() + "\n\n" if at >= 0 else "# Content ideas\n\n"
    rest = "\n".join(body_lines[at + 1:]).strip()
    return head + top + section + ("\n" + rest + "\n" if rest else "")


@hq_tool(action=ActionClass.VAULT_WRITE)
async def file_ideas(ctx: RunContext[HQDeps], title: str = "") -> str:
    """File the batch of content ideas you wrote in this same reply.

    Write the ideas as plain markdown text in your reply, one top-level `- `
    bullet each, then call this in that same reply after them, with a short
    `title` for the batch. Code adds today's dated heading and puts the batch
    at the top of projects/content/ideas.md; nothing already there changes.
    """
    if not memory.in_scope(IDEAS_PATH, ctx.deps.vault_write_scopes):
        raise ModelRetry(f"refused: agent {ctx.deps.agent} may not write {IDEAS_PATH}")
    text = reply_text(ctx.messages)
    problems = batch_problems(text)
    if problems:
        raise ModelRetry(
            "; ".join(problems) + ". Write the batch as the text of your reply, then call"
            " file_ideas in that same reply")
    day = f"{_today():%Y-%m-%d}"

    def _read() -> str | None:
        try:
            return memory.read(IDEAS_PATH)
        except FileNotFoundError:
            return None

    existing = await asyncio.to_thread(_read)
    if existing and re.search(rf"^## {day}\b", existing, re.MULTILINE):
        raise ModelRetry(f"today's batch ({day}) is already filed; say so and stop")
    content = memory.stamp_frontmatter(
        with_batch(existing, text, day, title), author=ctx.deps.agent, provenance="agent")
    try:
        await memory.write(IDEAS_PATH, content, actor=ctx.deps.agent)
    except memory.WriteRefused as exc:
        raise ModelRetry(str(exc)) from None
    n = len(_IDEA.findall(text))
    await emit("ideas.filed", run_id=ctx.deps.run_id, agent=ctx.deps.agent,
               payload={"ideas": n, "day": day})
    return f"filed {n} ideas under ## {day} at the top of {IDEAS_PATH}"
