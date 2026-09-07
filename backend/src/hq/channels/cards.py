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
