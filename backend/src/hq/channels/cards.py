"""Telegram message layout.

Telegram renders a small HTML subset, and nothing else: no tables, no columns,
no colour. What it does have is bold, monospace, and blank lines, and on a
phone those are enough. A card here is a title line, then short grouped lines
with space between the groups, so the eye lands on the answer instead of
reading a paragraph.

Two rules the rest of the module depends on:

* **Everything interpolated is escaped.** Agent text, note paths and error
  messages all reach here, and one stray ``<`` in a message makes Telegram
  reject the whole send with a parse error rather than dropping a tag.
* **A tag never spans a line.** Long replies are split into 4096-byte chunks
  on line boundaries, so a tag left open at a cut would break the next chunk.
"""

from __future__ import annotations

import re
from html import escape

BAR_WIDTH = 10

# One glyph per task state, so a board scan is a colour scan.
STATE_DOT = {
    "needs_approval": "🟣",
    "running": "🔵",
    "blocked": "🟠",
    "backlog": "⚪️",
    "done": "🟢",
    "failed": "🔴",
}

STATE_LABEL = {
    "needs_approval": "Needs you",
    "running": "Running",
    "blocked": "Blocked",
    "backlog": "Backlog",
    "done": "Done",
    "failed": "Failed",
}


def esc(value: object) -> str:
    """Escape anything going into an HTML message."""
    return escape(str(value), quote=False)


def title(text: str, *, icon: str = "", count: int | None = None) -> str:
    """The bold first line of a card."""
    head = f"{icon} {esc(text)}".strip()
    if count is not None:
        head = f"{head} · {count}"
    return f"<b>{head}</b>"


def bullet(text: str, *, sub: str = "") -> str:
    """A list row, with an optional quiet second line indented under it."""
    line = f"• {esc(text)}"
    return f"{line}\n  <i>{esc(sub)}</i>" if sub else line


def bar(fraction: float, width: int = BAR_WIDTH) -> str:
    """A text meter. A number alone does not show how close to the cap it is."""
    # Any spend at all shows at least one block: an empty bar next to a
    # non-zero number reads as "nothing spent", which is the wrong answer.
    filled = max(0, min(width, round(fraction * width)))
    if fraction > 0 and filled == 0:
        filled = 1
    return "█" * filled + "░" * (width - filled)


def card(*blocks: str) -> str:
    """Join blocks with a blank line, dropping any that are empty."""
    return "\n\n".join(b for b in blocks if b)


def lines(*rows: str) -> str:
    """Join rows with a single newline, dropping any that are empty."""
    return "\n".join(r for r in rows if r)


def truncate(text: str, limit: int) -> str:
    """Cut on a word boundary where one is close, with an ellipsis."""
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut).rstrip() + "…"


def ago(seconds: float) -> str:
    """"4 min", "3 h", "2 d" — the shortest form that is still unambiguous."""
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h"
    return f"{int(seconds // 86400)} d"


# --- markdown -> Telegram HTML ------------------------------------------------
# Agent answers are markdown. Telegram renders a small HTML subset and nothing
# else, so a reply sent as-is arrives as literal ``**`` and ``##`` around the
# words that were meant to stand out — a wall of punctuation on a phone. Worse,
# one ``<`` in an agent's text makes Telegram reject the entire send.
#
# So: escape first, then translate the handful of markdown forms Telegram can
# actually express. Anything it cannot (tables, nesting, images) degrades to
# plain text rather than breaking the message.

_FENCE_RE = re.compile(r"```[a-zA-Z0-9]*\n(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*$")
_BULLET_RE = re.compile(r"(?m)^(\s*)[-*+]\s+")
_QUOTE_RE = re.compile(r"(?m)^\s{0,3}&gt;\s?(.*)$")
_RULE_RE = re.compile(r"(?m)^\s*(?:[-*_]\s*){3,}$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
# Single-asterisk italics only. Underscores are left alone on purpose: agent
# text is full of snake_case tool and column names, and _job_board_ is a name,
# not emphasis.
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])")
_CODE_RE = re.compile(r"`([^`\n]+?)`")
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_BLANKS_RE = re.compile(r"\n{3,}")


def md_to_html(text: str) -> str:
    """One agent answer, as something readable on a phone.

    Escapes everything first, so no agent text can inject a tag or break the
    send, then renders the forms Telegram supports: fenced code, headings as
    bold, bullets as dots, quotes, bold, italic, inline code and links.
    """
    out = escape(str(text or ""), quote=False)

    # Fenced code first: its contents must not be touched by the inline rules.
    blocks: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        blocks.append(match.group(1).rstrip())
        return f"\x00{len(blocks) - 1}\x00"

    out = _FENCE_RE.sub(_stash, out)

    out = _RULE_RE.sub("", out)
    out = _HEADING_RE.sub(r"<b>\1</b>", out)
    out = _QUOTE_RE.sub(r"<blockquote>\1</blockquote>", out)
    out = _BULLET_RE.sub(r"\1• ", out)
    out = _LINK_RE.sub(r'<a href="\2">\1</a>', out)
    out = _BOLD_RE.sub(r"<b>\1</b>", out)
    out = _ITALIC_RE.sub(r"<i>\1</i>", out)
    out = _CODE_RE.sub(r"<code>\1</code>", out)

    for i, block in enumerate(blocks):
        out = out.replace(f"\x00{i}\x00", f"<pre>{block}</pre>")

    return _BLANKS_RE.sub("\n\n", out).strip()


def clip(text: str, limit: int) -> str:
    """Shorten a multi-line body while KEEPING its line structure.

    ``truncate`` is for a label: it collapses newlines, which is right for one
    line and wrong for a message. Collapsing a whole answer put every line on
    one line, and the heading rule then wrapped the entire body in bold.
    """
    clean = str(text or "").strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    # Prefer a paragraph break, then a line break, then a word.
    for sep in ("\n\n", "\n", " "):
        idx = cut.rfind(sep)
        if idx > limit * 0.5:
            return cut[:idx].rstrip() + "\n…"
    return cut.rstrip() + "…"


TELEGRAM_LIMIT = 4096


def render_for_telegram(text: str, limit: int = 4000) -> str:
    """Markdown to HTML, guaranteed to fit and never cut inside a tag.

    Rendering first and slicing after is the obvious version and it is wrong:
    a cut lands inside ``<b>`` or a half-written href, and Telegram rejects
    malformed HTML outright rather than dropping the tag — the whole message
    fails to send. So the SOURCE is clipped first and rendered after, and if
    the tags push it over anyway, clip harder and render again.
    """
    budget = limit
    for _ in range(4):
        rendered = md_to_html(clip(text, budget))
        if len(rendered) <= limit:
            return rendered
        # Tag overhead is roughly proportional; back off and retry rather than
        # guessing a ratio.
        budget = int(budget * 0.7)
    # Last resort: plain escaped text, which has no tags to break.
    return esc(clip(text, limit - 16))


def answer_card(
    *, agent: str, title_text: str, body: str, icon: str = "",
    footer: str = "", body_limit: int = 1200,
) -> str:
    """An agent's finished answer as a card: who, what, the answer, the trail.

    The body is the agent's own markdown, rendered. Truncation happens BEFORE
    rendering, so a cut can never land inside a tag and leave it open.
    """
    head = f"{icon} <b>{esc(title_text)}</b>".strip()
    who = f"<i>{esc(agent)}</i>" if agent else ""
    return card(
        lines(head, who),
        render_for_telegram(body, body_limit),
        f"<i>{esc(footer)}</i>" if footer else "",
    )


def readable_args(tool: str, args: dict) -> str:
    """What an approval is actually asking for.

    A JSON dump is the wrong thing to put in front of someone deciding on a
    phone: the decision usually turns on one value, and it is buried. Show
    that value as itself, and fall back to a short key list otherwise.
    """
    if not args:
        return ""
    if tool == "announce" and "text" in args:
        return f"<blockquote>{esc(truncate(args['text'], 600))}</blockquote>"
    if "path" in args:
        rest = [k for k in args if k != "path"]
        tail = f"\n<i>plus {', '.join(rest)}</i>" if rest else ""
        return f"<code>{esc(args['path'])}</code>{tail}"
    rows = [
        f"<b>{esc(k)}</b> {esc(truncate(v, 160))}"
        for k, v in list(args.items())[:6]
        if v not in (None, "", [], {})
    ]
    return lines(*rows)
