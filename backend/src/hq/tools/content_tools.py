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

Paste-ready is not the same as worth posting. A post can pass every measured
check and still be one any engineer could have written. So sage writes more
candidates than he needs, the teacher model scores each one that passed the
checks on a fixed rubric (agents/sage/skills/daily-posts/judge.md), and code
keeps the best few. The judge scores; code decides what is kept.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext
from pydantic_ai.usage import UsageLimits

from hq import llm, memory, owner_state, privacy, voice
from hq.config import settings
from hq.dbos_app import DBOS
from hq.obs import emit
from hq.safety import ActionClass
from hq.tools import learning_tools as lt
from hq.tools.learning_tools import _today, reply_text
from hq.tools.registry import HQDeps, hq_tool

log = logging.getLogger(__name__)

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


POSTS_MIN, POSTS_MAX = 3, 5              # how many code keeps and files
CANDIDATES_MIN, CANDIDATES_MAX = 6, 8    # how many sage writes for the judge
KEEP_MEAN = 3.5                          # a kept post's mean rubric score, at least
JUDGE_ROLE = "teacher"
JUDGE_PATH = ("sage", "skills", "daily-posts", "judge.md")
SOURCE_CHARS = 4_000                     # of each source file the judge reads
MATERIAL_CHARS = 30_000
POST_WORDS = (40, 160)       # 87 is his median; rendered into the skill text
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
# Work an agent did, told as his own doing. His job sweep checks boards; he
# does not. "I was reading" and "my sweep found" are his; these are not.
# Seven of forty drafts promised something he then did not do.
_PROMISE_RE = re.compile(
    r"\b(?:I'll|I will|I'm going to|I am going to|tonight I(?:'m| am| will)"
    r"|tomorrow I(?:'m| am| will)|next week I(?:'m| am| will))\b", re.IGNORECASE)
_CLAIMED_RE = re.compile(
    r"\bI\s+(?:checked|verified|applied|scraped|searched|swept|crawled|fetched|looked up"
    r"|opened|read the board|ran (?:a|the|my) (?:sweep|search|scan))\b", re.IGNORECASE)
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
    if _URL_RE.search(post):
        probs.append("a link; his posts carry none")
    promised = _PROMISE_RE.search(post)
    if promised:
        probs.append(f"\u201c{promised.group(0)}\u201d promises a future action; a post says"
                     " what happened, never what he will do")
    claimed = _CLAIMED_RE.search(post)
    if claimed:
        probs.append(f"\u201c{claimed.group(0)}\u201d claims work an agent did as his own;"
                     " say who did it (\u201cmy job sweep found\u201d) or drop the line")
    return probs


def count_problem(posts: list[str], sources: list[str]) -> str | None:
    """Why the candidate batch is the wrong size, or None."""
    if not CANDIDATES_MIN <= len(posts) <= CANDIDATES_MAX:
        return (f"{len(posts)} candidates; write {CANDIDATES_MIN} to {CANDIDATES_MAX}, separated"
                f" by a line holding only ---. Code keeps the best {POSTS_MIN} to {POSTS_MAX}")
    if len(sources) != len(posts):
        return f"{len(sources)} sources for {len(posts)} candidates; one per candidate, in order"
    return None


def gate(posts: list[str]) -> dict[int, list[str]]:
    """The measured checks, per candidate number (from 1): [] when it passed."""
    return {i: post_problems(post) for i, post in enumerate(posts, 1)}


def _quote(post: str) -> str:
    return f"\u201c{post[:50]}\u2026\u201d"


# --- the judge -------------------------------------------------------------------


class PostScore(BaseModel):
    """One candidate's rubric scores, 1 to 5 each, and the judge's one line."""
    post: int = Field(description="the candidate's number, as given")
    specific_trigger: int = Field(ge=1, le=5)
    one_detail_only_he_has: int = Field(ge=1, le=5)
    voice: int = Field(ge=1, le=5)
    insight: int = Field(ge=1, le=5)
    not_generic: int = Field(ge=1, le=5)
    why: str = Field(description="one line: what holds the post up or lets it down")

    def mean(self) -> float:
        return (self.specific_trigger + self.one_detail_only_he_has + self.voice
                + self.insight + self.not_generic) / 5

    def line(self) -> str:
        return (f"trigger {self.specific_trigger}, detail {self.one_detail_only_he_has},"
                f" voice {self.voice}, insight {self.insight}, not generic {self.not_generic};"
                f" mean {self.mean():.1f}")


class PostVerdict(BaseModel):
    scores: list[PostScore]


def judge_instructions() -> str:
    return settings().agents_dir.joinpath(*JUDGE_PATH).read_text().strip()


# A step covers every model in the teacher's chain timing out in turn; two
# attempts, as the writer's judges have.
_STEP: dict[str, Any] = {"retries_allowed": True, "max_attempts": 2, "interval_seconds": 5.0,
                         "backoff_rate": 2.0,
                         "timeout_seconds": llm.registry().longest_chain_timeout_s() + 30.0}


@DBOS.step(name="posts.judge", **_STEP)
async def _post_judge_step(candidates: list[dict[str, Any]], material: str) -> dict[str, Any]:
    """Score each candidate on the rubric. The scores come back as JSON in
    the reply's text, which the gateway streams; a tool-call answer it would
    not, and a silent answer is cut at the idle limit."""
    reg = llm.registry()
    agent = Agent(reg.resolve(JUDGE_ROLE), output_type=PromptedOutput(PostVerdict), retries=3,
                  instructions=judge_instructions(),
                  model_settings=reg.model_settings_for(JUDGE_ROLE))
    prompt = (f"<material>\n{material[:MATERIAL_CHARS]}\n</material>\n\n"
              f"<candidates>\n{json.dumps(candidates, ensure_ascii=False, indent=1)}\n"
              "</candidates>")
    result = await agent.run(prompt, usage_limits=UsageLimits(request_limit=4))
    return result.output.model_dump()


def choose(verdict: PostVerdict, judged: list[int]) -> tuple[list[PostScore], list[str]]:
    """``(kept, weak)``: the judged candidates whose mean is at least
    KEEP_MEAN, best first (a tie keeps his order), at most POSTS_MAX; and one
    line for every judged candidate left out, with the judge's reason. A
    candidate the judge returned no score for is left out and named."""
    by_post = {s.post: s for s in verdict.scores if s.post in judged}
    passing = sorted((s for s in by_post.values() if s.mean() >= KEEP_MEAN),
                     key=lambda s: (-s.mean(), s.post))
    kept = passing[:POSTS_MAX]
    kept_ids = {s.post for s in kept}
    weak: list[str] = []
    for n in judged:
        score = by_post.get(n)
        if score is None:
            weak.append(f"candidate {n}: the judge returned no score")
        elif n not in kept_ids:
            reason = (score.why if score.mean() < KEEP_MEAN
                      else f"{score.why} (it passed, but {POSTS_MAX} scored higher)")
            weak.append(f"candidate {n} ({score.line()}): {reason}")
    return kept, weak


_SOURCE_PATH_RE = re.compile(r"[\w./-]+\.md\b")


def _source_text(path: str) -> str:
    """A source's own text for the judge: a lesson, else a vault file, else ""."""
    text = lt._read_lesson_text(path)
    if text:
        return text
    try:
        return memory.read(path)
    except (OSError, ValueError, PermissionError):
        return ""


async def judge_material(sources: list[str]) -> str:
    """What the judge checks a trigger and a detail against: the text of every
    file a source names, and what the ledger says he has done."""
    parts: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for path in _SOURCE_PATH_RE.findall(source):
            if path in seen:
                continue
            seen.add(path)
            text = await asyncio.to_thread(_source_text, path)
            if text.strip():
                parts.append(f"### {path}\n\n{text.strip()[:SOURCE_CHARS]}")
    try:
        owner = await owner_state.block()
    except Exception:
        log.warning("posts: the owner state could not be read for the judge", exc_info=True)
        owner = ""
    if owner.strip():
        parts.append(owner.strip())
    return "\n\n".join(parts) or "(no source text could be read; judge from the source labels)"


def sources_section(kept: list[PostScore], left_out: list[str], sources: list[str]) -> str:
    """The sidecar's section: each filed post's source and scores, in the
    order filed, then every candidate left out and why."""
    lines = [f"- post {i}: {sources[s.post - 1]} ({s.line()}): {s.why}"
             for i, s in enumerate(kept, 1)]
    lines += [f"- left out, {w}" for w in left_out]
    return "\n".join(lines)


def _read(path: str) -> str | None:
    try:
        return memory.read(path)
    except FileNotFoundError:
        return None


@hq_tool(action=ActionClass.VAULT_WRITE)
async def file_posts(ctx: RunContext[HQDeps], sources: list[str], title: str = "") -> str:
    """File today's posts: the best of the candidates you wrote as the text of
    this same reply.

    Write only the candidates in your reply, 6 to 8 of them, each exactly as
    he would paste it on X, separated by a line holding only `---`. Then, in
    that same reply, call this with `sources`: for each candidate in order,
    the lesson, note or board row it rests on. Code checks every candidate
    against his voice, a judge scores the ones that pass, and code files the
    best 3 to 5 at the top of projects/content/ideas.md. When too few are
    good, the weak ones are named with the judge's reason: rewrite them.
    """
    if not memory.in_scope(IDEAS_PATH, ctx.deps.vault_write_scopes):
        raise ModelRetry(f"refused: agent {ctx.deps.agent} may not write {IDEAS_PATH}")
    posts = split_posts(reply_text(ctx.messages))
    again = (f" Send all {CANDIDATES_MIN} to {CANDIDATES_MAX} candidates again as your reply's"
             " text, then call file_posts in that same reply")
    wrong_size = count_problem(posts, sources)
    if wrong_size:
        raise ModelRetry(wrong_size + "." + again)
    checked = gate(posts)
    failed = [f"candidate {n} ({_quote(posts[n - 1])}): " + "; ".join(found)
              for n, found in checked.items() if found]
    judged = [n for n, found in checked.items() if not found]
    if len(judged) < POSTS_MIN:
        raise ModelRetry(
            f"only {len(judged)} of {len(posts)} candidates pass the checks and {POSTS_MIN}"
            " must. " + "; ".join(failed) + ". Rewrite what is named." + again)
    day = f"{_today():%Y-%m-%d}"
    existing = await asyncio.to_thread(_read, IDEAS_PATH)
    if existing and re.search(rf"^## {day}\b", existing, re.MULTILINE):
        raise ModelRetry(f"today's posts ({day}) are already filed; say so and stop")

    candidates = [{"post": n, "source": sources[n - 1], "text": posts[n - 1]} for n in judged]
    verdict = PostVerdict.model_validate(
        await _post_judge_step(candidates, await judge_material(sources)))
    kept, weak = choose(verdict, judged)
    if len(kept) < POSTS_MIN:
        raise ModelRetry(
            f"only {len(kept)} of {len(posts)} candidates scored a mean of {KEEP_MEAN:g} or more"
            f" on the post rubric and {POSTS_MIN} must. Weak: " + "; ".join(weak)
            + (". Failed the checks: " + "; ".join(failed) if failed else "")
            + ". Rewrite the weak ones on a real trigger with a detail only he has, or replace"
            " them." + again)

    batch = "\n\n---\n\n".join(posts[s.post - 1] for s in kept)
    content = memory.stamp_frontmatter(
        with_batch(existing, batch, day, title), author=ctx.deps.agent, provenance="agent")
    problem = memory.write_problem(IDEAS_PATH, content, actor=ctx.deps.agent, existing=existing)
    if problem:
        raise ModelRetry(problem)
    left_out = weak + failed
    where = sources_section(kept, left_out, sources)
    prior = await asyncio.to_thread(_read, SOURCES_PATH)
    try:
        await memory.write(IDEAS_PATH, content, actor=ctx.deps.agent)
        await memory.write(SOURCES_PATH, memory.stamp_frontmatter(
            with_batch(prior, where, day, title).replace("# Content ideas", "# Post sources", 1),
            author=ctx.deps.agent, provenance="agent"), actor=ctx.deps.agent)
    except memory.WriteRefused as exc:
        raise ModelRetry(str(exc)) from None
    await emit("posts.filed", run_id=ctx.deps.run_id, agent=ctx.deps.agent,
               payload={"posts": len(kept), "candidates": len(posts), "day": day,
                        "kept": [s.post for s in kept],
                        "means": {str(s.post): round(s.mean(), 2) for s in verdict.scores}})
    order = ", ".join(str(s.post) for s in kept)
    return (f"filed {len(kept)} of {len(posts)} candidates (best first: {order}) under ## {day}"
            f" at the top of {IDEAS_PATH}"
            + ("; left out: " + "; ".join(left_out) if left_out else ""))
