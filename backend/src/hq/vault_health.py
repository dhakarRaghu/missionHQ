"""Vault maintenance pass, dry-run only: reports, never writes.

Checks:
  near_duplicates   per-path mean embedding from hq.memory_chunks, pairwise
                    cosine distance < DUP_DISTANCE, plus title-lexeme overlap
  orphans           notes with no outgoing note link and no incoming link
  unsourced         quarantine/, learnings/, projects/ notes without a
                    source / sources / source_urls frontmatter key
  stale_quarantine  quarantine/ notes older than STALE_DAYS that no other note
                    links to or mentions
  future_dated      a YYYY-MM-DD in the filename later than today in CRON_TZ
  memory_blocks     fill level of each core memory block against BLOCK_CAPS

``merge_plan`` describes, for each near-duplicate pair, what a merge would
do (keep newest, append the other note's unique lines, leave a redirect
stub). Nothing is written in this version.
"""

from __future__ import annotations

import asyncio
import math
import re
from datetime import date, datetime
from itertools import combinations
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from hq import db
from hq.config import settings
from hq.memory import BLOCK_CAPS

DUP_DISTANCE = 0.12
STALE_DAYS = 14
# Folders that are not notes for link purposes: memory blocks are injected
# into prompts, inbox/ is a drop zone the owner empties.
SKIP_DIRS = ("memory/", "inbox/")
AI_DIRS = ("quarantine/", "learnings/", "projects/")
SOURCE_KEYS = ("source_urls", "sources", "source")

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_H1_RE = re.compile(r"^#\s+(.*?)\s*#*\s*$", re.MULTILINE)


def _vault() -> Path:
    return settings().vault_dir


def _skipped(rel: str) -> bool:
    return rel.startswith(SKIP_DIRS)


def read_notes() -> dict[str, str]:
    """All vault ``*.md`` as ``{rel_path: text}``; ``.git`` skipped."""
    root = _vault()
    notes: dict[str, str] = {}
    for p in sorted(root.rglob("*.md")):
        if ".git" in p.parts:
            continue
        try:
            notes[p.relative_to(root).as_posix()] = p.read_text()
        except OSError:
            continue
    return notes


def frontmatter(text: str) -> dict:
    """Parsed YAML frontmatter, ``{}`` when absent or unparsable."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


def title_of(rel: str, text: str) -> str:
    m = _H1_RE.search(text)
    return m.group(1).strip() if m else Path(rel).stem


def filename_date(rel: str) -> date | None:
    m = _DATE_RE.search(Path(rel).name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def note_date(rel: str) -> date:
    """Date in the filename when present, else the file's mtime in CRON_TZ."""
    d = filename_date(rel)
    if d is not None:
        return d
    mtime = (_vault() / rel).stat().st_mtime
    return datetime.fromtimestamp(mtime, ZoneInfo(settings().cron_tz)).date()


def today() -> date:
    return datetime.now(ZoneInfo(settings().cron_tz)).date()


# --- links ------------------------------------------------------------------


def _resolve(target: str, src: str, notes: dict[str, str]) -> str | None:
    """Map a link target to a vault path. Accepts ``a/b``, ``a/b.md``, a bare
    stem (``[[b]]``) matched anywhere in the vault, and paths relative to the
    linking note. External URLs and non-note targets resolve to None."""
    t = target.strip()
    if not t or "://" in t or t.startswith(("mailto:", "#")):
        return None
    t = t.split("#", 1)[0].strip("/")
    cands = [t, f"{t}.md"]
    src_dir = Path(src).parent.as_posix()
    if src_dir and src_dir != ".":
        cands += [f"{src_dir}/{t}", f"{src_dir}/{t}.md"]
    for c in cands:
        c = Path(c).as_posix().removeprefix("./")
        if c in notes:
            return c
    if "/" not in t:
        stem = t.removesuffix(".md")
        for rel in notes:
            if Path(rel).stem == stem:
                return rel
    return None


def outgoing_links(rel: str, text: str, notes: dict[str, str]) -> set[str]:
    targets = _WIKILINK_RE.findall(text) + _MDLINK_RE.findall(text)
    out = set()
    for t in targets:
        r = _resolve(t, rel, notes)
        if r is not None and r != rel:
            out.add(r)
    return out


def link_graph(notes: dict[str, str]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """``(outgoing, incoming)`` over non-skipped notes."""
    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = {rel: set() for rel in notes}
    for rel, text in notes.items():
        if _skipped(rel):
            continue
        outgoing[rel] = outgoing_links(rel, text, notes)
        for dst in outgoing[rel]:
            incoming[dst].add(rel)
    return outgoing, incoming


def mentioned_elsewhere(rel: str, notes: dict[str, str], incoming: dict[str, set[str]]) -> bool:
    """Linked from another note, or its path / stem appears in another
    note's text (agents often cite ``quarantine/x.md`` in backticks)."""
    if incoming.get(rel):
        return True
    stem = Path(rel).stem
    for other, text in notes.items():
        if other == rel or _skipped(other):
            continue
        if rel in text or stem in text:
            return True
    return False


# --- near duplicates --------------------------------------------------------


def _parse_vec(s: str) -> list[float]:
    return [float(x) for x in s.strip("[]").split(",") if x]


def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - dot / (na * nb)


async def mean_embeddings() -> dict[str, list[float]]:
    """Per-path mean of chunk embeddings, memory/ excluded. Empty when the
    table has no embeddings or the column is missing."""
    try:
        rows = await db.fetch(
            "SELECT path, avg(embedding)::text AS vec FROM hq.memory_chunks"
            " WHERE embedding IS NOT NULL AND path NOT LIKE 'memory/%%'"
            " GROUP BY path ORDER BY path"
        )
    except Exception:  # noqa: BLE001 - the vector half is optional
        return {}
    return {r["path"]: _parse_vec(r["vec"]) for r in rows if r["vec"]}


async def title_lexemes(titles: dict[str, str]) -> dict[str, set[str]]:
    """English-stemmed lexemes of each title via Postgres, for overlap."""
    if not titles:
        return {}
    rows = await db.fetch(
        "SELECT p AS path, tsvector_to_array(to_tsvector('english', t)) AS lex"
        " FROM unnest(%s::text[], %s::text[]) AS u(p, t)",
        (list(titles), list(titles.values())),
    )
    return {r["path"]: set(r["lex"] or []) for r in rows}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


async def near_duplicates(notes: dict[str, str]) -> list[dict]:
    vecs = await mean_embeddings()
    vecs = {p: v for p, v in vecs.items() if p in notes}
    lex = await title_lexemes({p: title_of(p, notes[p]) for p in vecs})
    scored: list[tuple[float, str, str]] = []
    for a, b in combinations(sorted(vecs), 2):
        dist = cosine_distance(vecs[a], vecs[b])
        if dist < DUP_DISTANCE:
            scored.append((dist, a, b))
    scored.sort()
    return [
        {
            "a": a, "b": b, "distance": round(dist, 4),
            "title_overlap": round(_jaccard(lex.get(a, set()), lex.get(b, set())), 2),
        }
        for dist, a, b in scored
    ]


# --- report -----------------------------------------------------------------


def memory_blocks() -> list[dict]:
    rows = []
    for rel, cap in BLOCK_CAPS.items():
        p = _vault() / rel
        chars = len(p.read_text()) if p.exists() else 0
        rows.append({"path": rel, "chars": chars, "cap": cap, "pct": round(100 * chars / cap)})
    return rows


def _sync_checks(notes: dict[str, str]) -> dict:
    outgoing, incoming = link_graph(notes)
    orphans = sorted(
        rel for rel in outgoing if not outgoing[rel] and not incoming[rel]
    )
    unsourced = sorted(
        rel for rel, text in notes.items()
        if rel.startswith(AI_DIRS) and not any(k in frontmatter(text) for k in SOURCE_KEYS)
    )
    now = today()
    stale = []
    for rel in sorted(notes):
        if not rel.startswith("quarantine/"):
            continue
        age = (now - note_date(rel)).days
        if age > STALE_DAYS and not mentioned_elsewhere(rel, notes, incoming):
            stale.append({"path": rel, "age_days": age})
    future = [
        {"path": rel, "date": d.isoformat()}
        for rel in sorted(notes)
        if (d := filename_date(rel)) is not None and d > now
    ]
    return {
        "orphans": orphans,
        "unsourced": unsourced,
        "stale_quarantine": stale,
        "future_dated": future,
        "memory_blocks": memory_blocks(),
    }


async def report() -> dict:
    """Full read-only health report. ``counts`` has one entry per check;
    ``notes`` is the number of markdown files scanned."""
    notes = await asyncio.to_thread(read_notes)
    out = await asyncio.to_thread(_sync_checks, notes)
    out["near_duplicates"] = await near_duplicates(notes)
    out["notes"] = len(notes)
    out["today"] = today().isoformat()
    out["counts"] = {
        "near_duplicates": len(out["near_duplicates"]),
        "orphans": len(out["orphans"]),
        "unsourced": len(out["unsourced"]),
        "stale_quarantine": len(out["stale_quarantine"]),
        "future_dated": len(out["future_dated"]),
        "memory_blocks_over_80pct": sum(1 for b in out["memory_blocks"] if b["pct"] >= 80),
    }
    return out


def verdict(rep: dict) -> str:
    """One line. ``healthy`` when every count is zero."""
    c = rep["counts"]
    issues = [f"{n} {k.replace('_', ' ')}" for k, n in c.items() if n]
    if not issues:
        return f"vault-health: healthy ({rep['notes']} notes, no findings)"
    return f"vault-health: {sum(c.values())} finding(s): " + ", ".join(issues)


# --- merge plan (dry-run) ---------------------------------------------------


def merge_plan(pair: dict, notes: dict[str, str]) -> dict:
    """Proposed merge for one near-duplicate pair: keep the newest note,
    append the other's unique non-blank lines, leave a redirect stub in the
    old note's place. Pure computation; nothing is written."""
    a, b = pair["a"], pair["b"]
    keep, drop = (a, b) if note_date(a) >= note_date(b) else (b, a)
    keep_lines = {ln.strip() for ln in notes[keep].splitlines() if ln.strip()}
    unique = [
        ln for ln in notes[drop].splitlines()
        if ln.strip() and ln.strip() not in keep_lines
    ]
    stem = keep.removesuffix(".md")
    return {
        "keep": keep,
        "drop": drop,
        "append_lines": unique,
        "stub": f"Merged into [[{stem}]]",
    }


def format_report(rep: dict, *, with_merge_plan: bool = False, notes: dict[str, str] | None = None) -> str:
    lines = [f"vault: {_vault()}  notes: {rep['notes']}  today: {rep['today']}", ""]

    lines.append(f"near-duplicates (cosine distance < {DUP_DISTANCE}): {rep['counts']['near_duplicates']}")
    for p in rep["near_duplicates"]:
        lines.append(f"  {p['a']}  <->  {p['b']}  dist {p['distance']}  title overlap {p['title_overlap']}")
        if with_merge_plan and notes is not None:
            plan = merge_plan(p, notes)
            lines.append(f"    merge plan: keep {plan['keep']}, fold in {plan['drop']}")
            lines.append(f"      append {len(plan['append_lines'])} unique line(s) to {plan['keep']}")
            for ln in plan["append_lines"][:8]:
                lines.append(f"        + {ln[:100]}")
            if len(plan["append_lines"]) > 8:
                lines.append(f"        + ... {len(plan['append_lines']) - 8} more")
            lines.append(f"      rewrite {plan['drop']} as stub: {plan['stub']!r}")
            lines.append("      (dry run: nothing written)")

    lines.append(f"orphans (no links in or out; memory/, inbox/ skipped): {rep['counts']['orphans']}")
    lines.extend(f"  {p}" for p in rep["orphans"])

    lines.append(f"unsourced AI notes (no source/sources/source_urls): {rep['counts']['unsourced']}")
    lines.extend(f"  {p}" for p in rep["unsourced"])

    lines.append(f"stale quarantine (> {STALE_DAYS} days, never referenced): {rep['counts']['stale_quarantine']}")
    lines.extend(f"  {p['path']}  ({p['age_days']} days)" for p in rep["stale_quarantine"])

    lines.append(f"future-dated filenames: {rep['counts']['future_dated']}")
    lines.extend(f"  {p['path']}  ({p['date']})" for p in rep["future_dated"])

    lines.append("memory blocks:")
    for b in rep["memory_blocks"]:
        flag = "  <-- near cap" if b["pct"] >= 80 else ""
        lines.append(f"  {b['path']:<28} {b['chars']:>5}/{b['cap']} chars ({b['pct']}%){flag}")

    lines.append("")
    lines.append(verdict(rep))
    return "\n".join(lines)
