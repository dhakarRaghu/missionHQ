"""His daily X posts, checked and filed by code.

The posts file is newest-first and grows every day. Rewriting it through
`vault_write` meant either sending the whole file as one tool argument, which
the gateway does not stream, or sending only the new batch and wiping the
rest. So sage writes the posts as the text of its reply and this tool checks
each one against his measured voice and puts the batch at the top.

What reaches the file is paste-ready: his register (hq.voice), no private
words, no file paths, no employer. When the retired scout's posts became
weekly "idea" notes with why/Sources lines, the page he reads to post from
filled with notes about posts instead of posts.
"""

from __future__ import annotations

import asyncio
import re

from pydantic_ai import ModelRetry, RunContext

from hq import memory, privacy, voice
from hq.obs import emit
from hq.safety import ActionClass
from hq.tools import learning_tools as lt
from hq.tools.learning_tools import _today, reply_text
from hq.tools.registry import HQDeps, hq_tool

IDEAS_PATH = "projects/content/ideas.md"
def with_batch(existing: str | None, batch: str, day: str, title: str) -> str:
    """The file with `batch` as the newest dated section, under the title."""
    lines = batch.strip().splitlines()
    if lines and lines[0].startswith("## "):
        lines = lines[1:]
    title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*[—–-]?\s*", "", title.strip())  # the date is added here
    heading = f"## {day}" + (f" — {title}" if title else "")
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


POSTS_MIN, POSTS_MAX = 2, 5
POST_WORDS = (25, 200)
SOURCES_PATH = "projects/content/post-sources.md"
_POST_SPLIT = re.compile(r"^\s*-{3,}\s*$", re.MULTILINE)
_PATHISH = re.compile(r"\b[\w./-]+\.md\b|\bquarantine/|\bwhy:|\bsources?:", re.IGNORECASE)


def split_posts(text: str) -> list[str]:
    body = "\n".join(ln for ln in text.strip().splitlines() if not ln.startswith("## "))
    return [p.strip() for p in _POST_SPLIT.split(body) if p.strip()]


def post_problems(post: str) -> list[str]:
    """Why this post is not something he can paste as it is, or []."""
    probs = list(voice.register_problems(post))
    words = len(post.split())
    if not POST_WORDS[0] <= words <= POST_WORDS[1]:
        probs.append(f"{words} words; his posts run {POST_WORDS[0]} to {POST_WORDS[1]}"
                     " (87 is his median)")
    private = sorted({w for w in lt.PRIVATE_WORDS
                      if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", post, re.IGNORECASE)})
    if private:
        probs.append("private words a reader cannot follow: " + ", ".join(private))
    if _PATHISH.search(post):
        probs.append("a file path or a note label (why:, Sources:); a post carries neither")
    if privacy.problem(post):
        probs.append("it names one of his employers")
    return probs


def batch_problems(posts: list[str]) -> list[str]:
    if not POSTS_MIN <= len(posts) <= POSTS_MAX:
        return [(f"{len(posts)} posts; write {POSTS_MIN} to {POSTS_MAX}, separated by a line"
                 " holding only ---")]
    out = []
    for i, post in enumerate(posts, 1):
        found = post_problems(post)
        if found:
            out.append(f"post {i} (\u201c{post[:50]}\u2026\u201d): " + "; ".join(found))
    return out


def _read(path: str) -> str | None:
    try:
        return memory.read(path)
    except FileNotFoundError:
        return None


@hq_tool(action=ActionClass.VAULT_WRITE)
async def file_posts(ctx: RunContext[HQDeps], sources: list[str], title: str = "") -> str:
    """File today's posts, which you wrote as the text of this same reply.

    Write only the posts in your reply, each exactly as he would paste it on
    X, separated by a line holding only `---`. Then, in that same reply, call
    this with `sources`: for each post in order, the lesson, note or board row
    it rests on. Code checks every post against his voice and files them at
    the top of projects/content/ideas.md; a post that fails is named with why.
    """
    if not memory.in_scope(IDEAS_PATH, ctx.deps.vault_write_scopes):
        raise ModelRetry(f"refused: agent {ctx.deps.agent} may not write {IDEAS_PATH}")
    posts = split_posts(reply_text(ctx.messages))
    problems = batch_problems(posts)
    if len(sources) != len(posts):
        problems.append(f"{len(sources)} sources for {len(posts)} posts; one per post, in order")
    if problems:
        raise ModelRetry(
            "; ".join(problems) + ". Rewrite what is named and send the whole batch again as"
            " your reply's text, then call file_posts in that same reply")
    day = f"{_today():%Y-%m-%d}"
    existing = await asyncio.to_thread(_read, IDEAS_PATH)
    if existing and re.search(rf"^## {day}\b", existing, re.MULTILINE):
        raise ModelRetry(f"today's posts ({day}) are already filed; say so and stop")
    batch = "\n\n---\n\n".join(posts)
    content = memory.stamp_frontmatter(
        with_batch(existing, batch, day, title), author=ctx.deps.agent, provenance="agent")
    problem = memory.write_problem(IDEAS_PATH, content, actor=ctx.deps.agent, existing=existing)
    if problem:
        raise ModelRetry(problem)
    where = "\n".join(f"- post {i}: {s}" for i, s in enumerate(sources, 1))
    prior = await asyncio.to_thread(_read, SOURCES_PATH)
    try:
        await memory.write(IDEAS_PATH, content, actor=ctx.deps.agent)
        await memory.write(SOURCES_PATH, memory.stamp_frontmatter(
            with_batch(prior, where, day, title).replace("# Content ideas", "# Post sources", 1),
            author=ctx.deps.agent, provenance="agent"), actor=ctx.deps.agent)
    except memory.WriteRefused as exc:
        raise ModelRetry(str(exc)) from None
    await emit("posts.filed", run_id=ctx.deps.run_id, agent=ctx.deps.agent,
               payload={"posts": len(posts), "day": day})
    return f"filed {len(posts)} posts under ## {day} at the top of {IDEAS_PATH}"
