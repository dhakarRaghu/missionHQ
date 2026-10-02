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
from datetime import date, timedelta
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
    title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*[—–:-]?\s*", "", title.strip())  # the date is added here
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


# X ranks a post by the reactions it predicts, and the ones that cost most
# are "not interested" (-47.5) and mute (-58.8) (xai-org/x-algorithm,
# home-mixer/params/param.rs, read 2026-10-02). An original post from an
# account his size can take a test slot in its first two hours
# (scorers/author_cold_start.rs), so a weak post is not free: it is shown,
# skipped and muted. One or two of the best of
# eight, not three to five.
POSTS_MIN, POSTS_MAX = 1, 2              # how many code keeps and files
CANDIDATES_MIN, CANDIDATES_MAX = 6, 8    # how many sage writes for the judge
KEEP_MEAN = 3.5                          # a kept post's mean rubric score, at least
LESSON_POSTS_MAX = 1                     # kept posts that rest on his own lessons
FLOOR = 3                                # and at least this on `teaches`, `clear`, `share`
# A 3 on `accurate` is a claim that lost the condition that makes it true.
# On 2026-10-02 the judge gave a post that called vLLM's 16-token blocks how
# "prompt caches" work an accurate 3 and a mean of 3.5, and it would have
# been filed: his readers call hosted APIs and would pad prompts for nothing.
ACCURATE_FLOOR = 4
# A post he filed in the last month is not filed again with new words. The
# judge sees them and names a repeat; code also refuses a near copy without
# asking it. On his file (27 entries from 15 days, read 2026-10-02) no two
# from different days share more than 0.33 of their content words, and the
# highest pairs are old evening notes written to one template.
REPEAT_DAYS = 30
REPEAT_OVERLAP = 0.6
JUDGE_ROLE = "teacher"
JUDGE_PATH = ("sage", "skills", "daily-posts", "judge.md")
# The judge checks every number and name against its source, so it reads the
# whole lesson. At 4,000 characters it saw the start of a 76,000-character
# lesson, called a name in it unsourced, and asked him to check figures that
# were there. 240,000 characters is about 80,000 tokens, a third of its window.
SOURCE_CHARS = 80_000                    # of each source file the judge reads
MATERIAL_CHARS = 240_000
# A one-line take is the most common post of the accounts he studies; 15
# words is room for a claim and the fact under it. 87 is his old median.
POST_WORDS = (15, 160)
# Work an agent did, told as his own doing. His job sweep checks boards; he
# does not. "I was reading" and "my sweep found" are his; these are not.
# Seven of forty drafts promised something he then did not do.
_PROMISE_RE = re.compile(
    r"\b(?:I'll|I will|I'm going to|I am going to|tonight I(?:'m| am| will)"
    r"|tomorrow I(?:'m| am| will)|next week I(?:'m| am| will))\b", re.IGNORECASE)
_CLAIMED_RE = re.compile(
    r"\bI\s+(?:checked|verified|applied|scraped|searched|swept|crawled|fetched|looked up"
    r"|opened|read the board|ran (?:a|the|my) (?:sweep|search|scan))\b", re.IGNORECASE)
# His agent system is private. He said so on 2026-09-28, after a week of posts
# about his own agents' runs, costs and failures. A post names what he read,
# what the field reports, or what he measured, never the machinery around him.
_SYSTEM_RE = re.compile(
    r"\bmission[\s_-]*hq\b"
    r"|\b(?:my|our)\s+(?:own\s+)?(?:[\w-]+\s+){0,2}(?:\w+-)?(?:agents?|agent system)\b"
    r"|\bthe\s+agents?\s+(?:I|we)\s+(?:run|built|wrote|use)\b"
    # "pipeline" and "sweep" only as his system's own names: "my training
    # pipeline" and "our learning-rate sweep" are the field's words.
    r"|\b(?:my|our)\s+(?:own\s+)?(?:job|study|writing|posting|post|content|lesson|course"
    r"|learning|research|reading)\s+(?:pipeline|sweep)\b"
    r"|\bmy\s+(?:study|writing|research|learning|course)\s+(?:system|agent|pipeline|course)\b"
    r"|\b(?:my|the)\s+(?:nightly|evening)\s+run\b",
    re.IGNORECASE)
# Words a reader needs a course in model serving to follow. On 2026-09-29 he
# read a batch built on "FP8 KV cache", "GSM8K", "batch-invariant kernels" and
# "312 TFLOPs against 1.5 TB/s" and said it was too technical for him, let
# alone for people who do not know what he is studying. One such word, said
# in everyday terms around it, can stay; two make the post a lesson extract.
_INTERNALS_RE = re.compile(
    r"\b(?:kv[\s-]?cache|prefill|decode (?:step|phase)|logprobs?|log[\s-]probs?|argmax"
    r"|logits?|fp8|fp16|bf16|int4|int8|tflops?|flops|tb/s|gb/s|hbm|sram|cuda|kernels?"
    r"|batch[\s-]invariant|attention heads?|softmax|moe|mixture of experts|gsm8k|mmlu"
    r"|speculative decoding|paged ?attention|continuous batching|quantiz\w*"
    r"|tensor parallel\w*|prefix cach\w*|radix (?:tree|cache)|mamba|ssm|sliding[\s-]window"
    r"|time to first token|ttft|tpot|p99|throughput-bound|memory[\s-]bound|arithmetic intensity)\b",
    re.IGNORECASE)
INTERNALS_MAX = 1
# Asking for the reaction instead of earning it, anywhere in the post. X's
# own guidance names "like if you agree", "comment yes" and "tag 3 friends",
# and readers answer bait with "not interested" and mute, the two largest
# penalties after a report. voice.yaml refuses an engagement ask as a
# closer; on X it is refused wherever it sits.
_BAIT_RE = re.compile(
    r"\b(?:like|repost|retweet|rt|bookmark)\s+(?:this\s+)?if\b"
    r"|\bcomment\s+(?:yes|[\"'\u201c\u2018]\w+[\"'\u201d\u2019])"
    r"|\breply\s+(?:yes|[\"'\u201c\u2018]\w+[\"'\u201d\u2019])"
    r"|\btag\s+(?:someone|(?:a|your|\d+|two|three|five)\s+(?:\w+\s+)?"
    r"(?:friends?|colleagues?|teammates?|people))\b"
    r"|\bbookmark\s+this\b|\bsave\s+this\s+(?:post|tweet|thread|for\s+later)\b"
    r"|\bfollow\s+(?:me\s+)?for\s+more\b"
    r"|\bdrop\s+an?\s+(?:comment|emoji|reply|like)\b|\bdrop\s+an?\s+[^\w\s]",
    re.IGNORECASE)
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
        probs.append(f"{words} words; his posts run {POST_WORDS[0]} to {POST_WORDS[1]}")
    private = sorted({w for w in lt.PRIVATE_WORDS
                      if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", post, re.IGNORECASE)})
    if private:
        probs.append("private words a reader cannot follow: " + ", ".join(private))
    if _PATHISH.search(post):
        probs.append("a file path or a note label (why:, Sources:); a post carries neither")
    if privacy.problem(post):
        probs.append("it names one of his employers")
    probs += link_problems(post)
    promised = _PROMISE_RE.search(post)
    if promised:
        probs.append(f"\u201c{promised.group(0)}\u201d promises a future action; a post says"
                     " what happened, never what he will do")
    inside = sorted({m.group(0).lower() for m in _INTERNALS_RE.finditer(post)})
    if len(inside) > INTERNALS_MAX:
        probs.append(f"{len(inside)} words only people who study model serving know ("
                     + ", ".join(inside) + "); keep at most one, and say what the rest"
                     " do in everyday words")
    system = _SYSTEM_RE.search(post)
    if system:
        probs.append(f"\u201c{system.group(0)}\u201d is about his agent system, which he keeps"
                     " private; write about what he read, what the field reports or what he"
                     " measured")
    claimed = _CLAIMED_RE.search(post)
    if claimed:
        probs.append(f"\u201c{claimed.group(0)}\u201d claims work an agent did as his own;"
                     " say only what he did himself, or drop the line")
    bait = _BAIT_RE.search(post)
    if bait:
        probs.append(f"\u201c{bait.group(0)}\u201d asks for a reaction; earn it with the post,"
                     " never ask for it")
    return probs


_STOP = frozenset({  # words of three letters or more that carry no subject
    "the", "and", "but", "for", "its", "it's", "that", "this", "with", "are", "was", "you",
    "your", "they", "not", "from", "have", "has", "than", "then", "when", "what", "how", "why",
    "does", "don't", "can"})


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2 and w not in _STOP}


def overlap(a: str, b: str) -> float:
    """The share of content words two posts have in common, 0 to 1."""
    wa, wb = _content_words(a), _content_words(b)
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


_DAY_HEAD_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\b.*$", re.MULTILINE)


def recent_posts(existing: str | None, today: date, days: int = REPEAT_DAYS) -> list[dict[str, str]]:
    """The posts filed in the `days` before `today`, newest first, each as
    ``{"id": "E1", "day": ..., "text": ...}``. A batch with no `---` is one post."""
    if not existing:
        return []
    parts = _DAY_HEAD_RE.split(existing)
    out: list[dict[str, str]] = []
    for i in range(1, len(parts) - 1, 2):
        try:
            day = date.fromisoformat(parts[i])
        except ValueError:
            continue
        if not timedelta(0) < today - day <= timedelta(days=days):
            continue
        body = parts[i + 1].split("\n## ", 1)[0]
        posts = split_posts(body)
        if len(posts) == 1 and not _is_one_post(posts[0]):
            continue                    # an older batch of ideas, not a post
        for text in posts:
            out.append({"id": f"E{len(out) + 1}", "day": parts[i], "text": text})
    return out


_LIST_LINE_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S", re.MULTILINE)


def _is_one_post(text: str) -> bool:
    """A batch body with no `---` is one post when it has no list line and
    no more words than a post (as the Ideas page reads it)."""
    return not _LIST_LINE_RE.search(text) and len(text.split()) <= POST_WORDS[1]


def repeat_problem(post: str, earlier: list[dict[str, str]]) -> str:
    """Why this post is a near copy of one filed in the last month, or ""."""
    for e in earlier:
        share = overlap(post, e["text"])
        if share >= REPEAT_OVERLAP:
            return (f"it shares {share:.0%} of its words with the post of {e['day']}"
                    f" ({_quote(e['text'])}); say something new, or the same subject from a"
                    " new angle")
    return ""


# A bare domain is a link too: X turns "example.com/x" into one. With a
# path, any common ending counts; without one, only endings that are not
# also file and module names ("libcuda.so", "run.sh", "java.io",
# "logging.info", "ASP.NET").
_LINK_RE = re.compile(
    r"(?:https?://|www\.)[^\s)\]]+"
    r"|\b[a-z0-9][\w-]*(?:\.[a-z0-9][\w-]*)*\.(?:com|org|net|io|dev|ai|xyz|co|app|me|sh"
    r"|so|gg|ly|in|info|blog|tech|site|page)/[^\s)\]]*"
    r"|\b[a-z0-9][\w-]*(?:\.[a-z0-9][\w-]*)*\.(?:com|org|dev|ai|xyz|app)\b(?!\.?\w)",
    re.IGNORECASE)


def _host(url: str) -> str:
    from urllib.parse import urlparse

    full = url if "://" in url else f"https://{url}"
    return (urlparse(full).hostname or "").lower().removeprefix("www.")


def link_problems(post: str) -> list[str]:
    """A post may carry one link, to one of his own posts on his site, and
    no other. Larger accounts in his field link to their own write-ups; a
    link to someone else's page sends the reader away from his."""
    links = [u.rstrip(".,;:!?") for u in _LINK_RE.findall(post)]
    if not links:
        return []
    own = _host(settings().site_url)
    foreign = [u for u in links if _host(u) != own]
    if foreign:
        return [f"a link to {foreign[0]}; a post links only to his own site ({own})"]
    if len(links) > 1:
        return [f"{len(links)} links; one at most, to his own post"]
    return []


def count_problem(posts: list[str], sources: list[str]) -> str | None:
    """Why the candidate batch is the wrong size, or None."""
    if not CANDIDATES_MIN <= len(posts) <= CANDIDATES_MAX:
        return (f"{len(posts)} candidates; write {CANDIDATES_MIN} to {CANDIDATES_MAX}, separated"
                f" by a line holding only ---. Code keeps the best {POSTS_MIN} to {POSTS_MAX}")
    if len(sources) != len(posts):
        return f"{len(sources)} sources for {len(posts)} candidates; one per candidate, in order"
    return None


def gate(posts: list[str], earlier: list[dict[str, str]] | None = None) -> dict[int, list[str]]:
    """The measured checks, per candidate number (from 1): [] when it passed.
    `earlier` is what he filed in the last month (`recent_posts`)."""
    out: dict[int, list[str]] = {}
    for i, post in enumerate(posts, 1):
        found = post_problems(post)
        again = repeat_problem(post, earlier or [])
        out[i] = found + ([again] if again else [])
    return out


def _quote(post: str) -> str:
    return f"\u201c{post[:50]}\u2026\u201d"


# --- the judge -------------------------------------------------------------------


class PostScore(BaseModel):
    """One candidate's rubric scores, 1 to 5 each, and the judge's one line.

    On 2026-09-28 he read a week of kept posts and said they were not worth
    sharing, and that his agent system is not something he posts about. The
    old rubric paid for "a detail only he has", and the only details only he
    had were his agents' runs. What a reader gets is what is scored now."""
    post: int = Field(description="the candidate's number, as given")
    source: int = Field(ge=1, le=5, description="a real source: a lesson, an article, a"
                        " field report, or a project he measured")
    teaches: int = Field(ge=1, le=5, description="the reader learns one concrete thing")
    accurate: int = Field(ge=1, le=5, description="every number and claim is in the material")
    voice: int = Field(ge=1, le=5)
    insight: int = Field(ge=1, le=5)
    clear: int = Field(ge=1, le=5, description="a developer who uses AI tools but never"
                       " studied how models are served follows every sentence")
    # What X weighs most among the reactions it predicts (param.rs, read
    # 2026-10-02): a copied link 20, a reply 5 (20 between people who follow
    # each other), a DM share 5, a follow 4; a like is 0.5.
    share: int = Field(ge=1, le=5, description="a developer would send it to a colleague,"
                       " or follow him to see the next one")
    reply: int = Field(ge=1, le=5, description="a reader has something real to answer:"
                       " a view to agree or disagree with, a question he means, a claim to"
                       " add a data point to")
    repeats: str = Field(default="", description="the id (E1, E2, ...) of an earlier post"
                         " that makes the same point from the same angle, or empty")
    why: str = Field(description="one line: what holds the post up or lets it down")

    def mean(self) -> float:
        return (self.source + self.teaches + self.accurate + self.voice + self.insight
                + self.clear + self.share + self.reply) / 8

    def floor_problem(self) -> str:
        """Why a post with a good mean is still not kept, or "". A post that
        teaches nothing, or states what its source does not, is not his to
        share whatever else it does well."""
        if self.accurate < ACCURATE_FLOOR:
            return (f"accurate {self.accurate}: a claim, number or condition is not as its"
                    " source states it")
        if self.teaches < FLOOR:
            return f"teaches {self.teaches}: the reader learns nothing concrete"
        if self.clear < FLOOR:
            return (f"clear {self.clear}: a developer outside model serving would not"
                    " follow it")
        if self.share < FLOOR:
            return f"share {self.share}: nobody would send it to a colleague"
        if self.repeats.strip():
            return f"repeats {self.repeats.strip()}: the same point he filed before"
        return ""

    def line(self) -> str:
        return (f"source {self.source}, teaches {self.teaches}, accurate {self.accurate},"
                f" voice {self.voice}, insight {self.insight}, clear {self.clear},"
                f" share {self.share}, reply {self.reply}; mean {self.mean():.1f}")


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
async def _post_judge_step(candidates: list[dict[str, Any]], material: str,
                           earlier: list[dict[str, str]]) -> dict[str, Any]:
    """Score each candidate on the rubric. The scores come back as JSON in
    the reply's text, which the gateway streams; a tool-call answer it would
    not, and a silent answer is cut at the idle limit."""
    reg = llm.registry()
    agent = Agent(reg.resolve(JUDGE_ROLE), output_type=PromptedOutput(PostVerdict), retries=3,
                  instructions=judge_instructions(),
                  model_settings=reg.model_settings_for(JUDGE_ROLE))
    prompt = (f"<material>\n{material}\n</material>\n\n"
              f"<earlier>\n{json.dumps(earlier, ensure_ascii=False, indent=1)}\n</earlier>\n\n"
              f"<candidates>\n{json.dumps(candidates, ensure_ascii=False, indent=1)}\n"
              "</candidates>")
    result = await agent.run(prompt, usage_limits=UsageLimits(request_limit=4))
    return result.output.model_dump()


def choose(verdict: PostVerdict, judged: list[int], sources: list[str] | None = None,
           posts: list[str] | None = None) -> tuple[list[PostScore], list[str]]:
    """``(kept, weak)``: the judged candidates whose mean is at least
    KEEP_MEAN and that clear every floor, best first (a tie keeps his order),
    at most LESSON_POSTS_MAX of them from his lessons, at most POSTS_MAX in
    all; and one line for every judged candidate left out, with the reason.
    The lesson limit applies before the cut, so a good post from his reading
    is filed in place of a second one from his course. A candidate the judge
    returned no score for is left out and named."""
    by_post = {s.post: s for s in verdict.scores if s.post in judged}
    passing = sorted((s for s in by_post.values()
                      if s.mean() >= KEEP_MEAN and not s.floor_problem()),
                     key=lambda s: (-s.mean(), s.post))
    capped: list[str] = []
    if sources is not None and posts is not None:
        passing, capped = cap_lessons(passing, sources, posts)
    kept = passing[:POSTS_MAX]
    kept_ids = {s.post for s in kept}
    cut_ids = {s.post for s in passing} - kept_ids         # passed, but others scored higher
    weak: list[str] = []
    for n in judged:
        score = by_post.get(n)
        if score is None:
            weak.append(f"candidate {n}: the judge returned no score")
        elif n in kept_ids:
            continue
        elif score.mean() < KEEP_MEAN:
            weak.append(f"candidate {n} ({score.line()}): {score.why}")
        elif score.floor_problem():
            weak.append(f"candidate {n} ({score.line()}): {score.floor_problem()}. {score.why}")
        elif n in cut_ids:
            weak.append(f"candidate {n} ({score.line()}): {score.why}"
                        f" (it passed, but {POSTS_MAX} scored higher)")
    return kept, weak + capped


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
    """What the judge checks a trigger and a detail against: what the ledger
    says he has done, then the text of every file a source names. The ledger
    comes first and is never cut: it is the only record of what he ran and
    built. The sources share what is left of MATERIAL_CHARS equally, so a
    long lesson does not push the last source out."""
    try:
        owner = (await owner_state.block()).strip()
    except Exception:
        log.warning("posts: the owner state could not be read for the judge", exc_info=True)
        owner = ""
    texts: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        for path in _SOURCE_PATH_RE.findall(source):
            if path in seen:
                continue
            seen.add(path)
            text = (await asyncio.to_thread(_source_text, path)).strip()
            if text:
                texts.append((path, text))
    owner = owner[:MATERIAL_CHARS // 2]
    room = max(0, MATERIAL_CHARS - len(owner) - 200 * len(texts))
    share = min(SOURCE_CHARS, room // max(1, len(texts)))
    parts = ([owner] if owner else []) + [f"### {path}\n\n{text[:share]}" for path, text in texts]
    return "\n\n".join(parts) or "(no source text could be read; judge from the source labels)"


def _from_lessons(source: str) -> bool:
    return "learning/lessons/" in source


def cap_lessons(kept: list[PostScore], sources: list[str],
                posts: list[str]) -> tuple[list[PostScore], list[str]]:
    """(kept, left out): at most LESSON_POSTS_MAX of the kept posts rest on
    his own lessons, best first. His readers have not taken his course; a
    batch built from it reads as his notes."""
    out: list[PostScore] = []
    left: list[str] = []
    from_lessons = 0
    for s in kept:
        if _from_lessons(sources[s.post - 1]):
            from_lessons += 1
            if from_lessons > LESSON_POSTS_MAX:
                left.append(f"candidate {s.post} ({_quote(posts[s.post - 1])}): a"
                            f" post from his lessons beyond the {LESSON_POSTS_MAX} kept;"
                            " his readers have not taken his course")
                continue
        out.append(s)
    return out, left


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
    the lesson, article or project it rests on. Code checks every candidate
    against his voice and against what he filed in the last month, a judge
    scores the ones that pass, and code files the best 1 or 2 at the top of
    projects/content/ideas.md. When none is good enough, the weak ones are
    named with the judge's reason: rewrite them.
    """
    if not memory.in_scope(IDEAS_PATH, ctx.deps.vault_write_scopes):
        raise ModelRetry(f"refused: agent {ctx.deps.agent} may not write {IDEAS_PATH}")
    posts = split_posts(reply_text(ctx.messages))
    again = (f" Send all {CANDIDATES_MIN} to {CANDIDATES_MAX} candidates again as your reply's"
             " text, then call file_posts in that same reply")
    wrong_size = count_problem(posts, sources)
    if wrong_size:
        raise ModelRetry(wrong_size + "." + again)
    day = f"{_today():%Y-%m-%d}"
    existing = await asyncio.to_thread(_read, IDEAS_PATH)
    if existing and re.search(rf"^## {day}\b", existing, re.MULTILINE):
        raise ModelRetry(f"today's posts ({day}) are already filed; say so and stop")
    earlier = recent_posts(existing, _today().date())
    checked = gate(posts, earlier)
    failed = [f"candidate {n} ({_quote(posts[n - 1])}): " + "; ".join(found)
              for n, found in checked.items() if found]
    if failed and ctx.retry == 0:
        # A check names something small to fix: a contraction, a word, a
        # length. Dropped at once, a good post was lost for it: on
        # 2026-09-29 the two candidates not taken from his lessons each
        # failed on one contraction, and the batch that was filed came all
        # from his course. Once, they go back to be fixed.
        raise ModelRetry(
            "fix these candidates and keep every other candidate word for word: "
            + "; ".join(failed) + "." + again)
    judged = [n for n, found in checked.items() if not found]
    if len(judged) < POSTS_MIN:
        raise ModelRetry(
            f"{len(judged)} of {len(posts)} candidates pass the checks, and at least"
            f" {POSTS_MIN} must. " + "; ".join(failed) + ". Rewrite what is named." + again)

    candidates = [{"post": n, "source": sources[n - 1], "text": posts[n - 1]} for n in judged]
    verdict = PostVerdict.model_validate(
        await _post_judge_step(candidates, await judge_material(sources), earlier))
    kept, weak = choose(verdict, judged, sources, posts)
    if len(kept) < POSTS_MIN:
        raise ModelRetry(
            f"{len(kept)} of {len(posts)} candidates scored a mean of {KEEP_MEAN:g} or more"
            f" on the post rubric and cleared its floors, and at least {POSTS_MIN} must."
            " Weak: " + "; ".join(weak)
            + (". Failed the checks: " + "; ".join(failed) if failed else "")
            + ". Rewrite the weak ones so each teaches one concrete thing its source states,"
            " or replace them." + again)

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
