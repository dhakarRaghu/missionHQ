"""The phone reader: every lesson as files the frontend can ship.

He reads on his laptop through the console, which talks to the backend, which
talks to Postgres on that same machine. None of that exists on his phone, and
he asked for the plain answer: "like a normal web app, when we create content
and then we push and then we have the content online."

So this writes the whole library into `frontend/public/reader`. The lesson
pages are already complete HTML documents with their stylesheet and their
scripts inline, so nothing has to be rendered again: they are copied as they
are, and one `index.json` says what exists. He commits the folder, pushes, and
Vercel serves it. The reader route fetches those files and nothing else, so
the phone needs no database, no token and no backend awake.

What it deliberately does NOT carry: anything the reader cannot use without
the backend. No study notes, no review notes, no task or run history. The
bundle is what he reads, and it goes on a Vercel deployment, so the less that
leaves this machine the better.

The read flags are true as of the export. The bundle itself stays read-only:
"Mark read" and concept taps on the phone go straight to the backend through
`hq.api.reader` (when the phone is on his tailnet), and the next export
carries the new flags.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from hq import db
from hq.config import REPO_DIR, settings

log = logging.getLogger(__name__)

READER_DIR = REPO_DIR / "frontend" / "public" / "reader"
READER_BRANCH = "reader"
FINGERPRINT_TRAILER = "Reader-Fingerprint"
GIT_TIMEOUT_S = 120


def _page_file(html_path: str) -> Path | None:
    """The lesson page on disk, or None when the row points at nothing."""
    if not html_path.strip():
        return None
    page = settings().learning_dir.parent / html_path.strip()
    return page if page.is_file() else None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def _courses() -> list[dict[str, Any]]:
    """Every course that has at least one written phase, in reading order.

    The join starts at the phases, not at `hq.courses`. That table is his own
    roster, and a course imported from the study platform has no row in it:
    Kubernetes is taught, he reads it in the console, and an inner join left
    it out of the bundle entirely. A course with no roster row sorts last and
    is named after its slug.
    """
    rows = await db.fetch(
        "SELECT p.course, c.title, c.course_order,"
        "       p.slug, p.title AS phase_title, p.phase_order, p.minutes,"
        "       p.summary, l.title AS lesson_title, l.html_path, l.lesson_date,"
        "       l.read_at, l.one_liner"
        " FROM hq.course_phases p"
        " JOIN hq.lessons l ON l.id = p.lesson_id"
        " LEFT JOIN hq.courses c ON c.course = p.course"
        " ORDER BY c.course_order NULLS LAST, p.course, p.phase_order, p.slug",
        (),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        page = _page_file(str(row["html_path"] or ""))
        if page is None:
            continue
        slug = str(row["course"])
        course = out.setdefault(
            slug,
            {
                "slug": slug,
                "title": str(row["title"] or "") or slug.replace("-", " ").title(),
                "phases": [],
            },
        )
        course["phases"].append(
            {
                "slug": str(row["slug"]),
                "title": str(row["lesson_title"] or row["phase_title"] or ""),
                "one_liner": str(row["one_liner"] or row["summary"] or "")[:400],
                "minutes": int(row["minutes"] or 0) or None,
                "date": _iso(row["lesson_date"]),
                "read": row["read_at"] is not None,
                "file": page.name,
            }
        )
    return list(out.values())


async def _articles() -> list[dict[str, Any]]:
    """The Learn side: standalone articles, newest first."""
    rows = await db.fetch(
        "SELECT title, one_liner, topic, lesson_date, html_path, read_at,"
        "       article_kind, course_slug"
        " FROM hq.lessons WHERE kind <> 'course' ORDER BY lesson_date DESC",
        (),
    )
    out = []
    for row in rows:
        page = _page_file(str(row["html_path"] or ""))
        if page is None:
            continue
        out.append(
            {
                "title": str(row["title"] or ""),
                "one_liner": str(row["one_liner"] or "")[:400],
                "topic": str(row["topic"] or ""),
                "kind": str(row["article_kind"] or ""),
                "date": _iso(row["lesson_date"]),
                "read": row["read_at"] is not None,
                "file": page.name,
            }
        )
    return out


async def build(target: Path | None = None) -> dict[str, Any]:
    """Write the bundle. Returns what went into it, for the CLI to print."""
    out = target or READER_DIR
    pages = out / "lessons"
    # Rebuilt from scratch every time: a lesson he deleted, or one rebuilt
    # under a new date, must not linger in the folder he pushes.
    if pages.exists():
        shutil.rmtree(pages)
    pages.mkdir(parents=True, exist_ok=True)

    courses = await _courses()
    articles = await _articles()

    wanted = {p["file"] for c in courses for p in c["phases"]}
    wanted |= {a["file"] for a in articles}
    # Every page gets the same hardening the console's endpoint applies, and
    # for a stronger reason: on Vercel there is no endpoint in front of it.
    # Without it a lesson's source link navigates the frame itself to the live
    # site, which is the 2026-09-12 bug, and the in-document content policy
    # that blocks outside loads is gone too.
    from hq.api.learning import harden_page

    lessons_dir = settings().learning_dir / "lessons"
    copied = 0
    for name in sorted(wanted):
        source = lessons_dir / name
        if source.is_file():
            (pages / name).write_text(harden_page(source.read_text()))
            copied += 1

    index = {
        "built_at": datetime.now().astimezone().isoformat(),
        "courses": courses,
        "articles": articles,
    }
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return {
        "dir": str(out),
        "courses": len(courses),
        "phases": sum(len(c["phases"]) for c in courses),
        "articles": len(articles),
        "pages": copied,
        "bytes": sum(f.stat().st_size for f in pages.iterdir()),
    }


# --- nightly publishing -----------------------------------------------------
#
# The loop he ran by hand was export, commit, push. Done nightly, a commit on
# `main` would be wrong twice over: `git add` in his working tree can sweep
# up his half-done work, and a bot commit ahead of his HEAD makes him rebase
# every morning. So the bundle goes to its own branch, `reader`, which Vercel
# deploys from, and it gets there without the working tree or `main` being
# touched: the files are hashed into the object store, a tree is built in a
# throwaway index, and the commit is made with `commit-tree` onto the
# branch's previous commit. Nothing is checked out, nothing is staged in his
# index, and HEAD does not move.
#
# The tree is the app as it was last pushed (`origin/main`: already public,
# so nothing unpushed leaves this machine) with `frontend/public/reader`
# replaced by tonight's bundle. A commit is made only when the bundle's
# content changed; `built_at` changes every run and is left out of that
# comparison, so an unchanged library makes no commit and no Vercel build.


def fingerprint(bundle: Path) -> str:
    """A hash of what the phone would show: every file in the bundle, with
    `index.json`'s `built_at` left out."""
    digest = hashlib.sha256()
    for path in sorted(p for p in bundle.rglob("*") if p.is_file()):
        rel = path.relative_to(bundle).as_posix()
        data = path.read_bytes()
        if rel == "index.json":
            try:
                index = json.loads(data)
                index.pop("built_at", None)
                data = json.dumps(index, sort_keys=True).encode()
            except (ValueError, AttributeError):
                pass
        digest.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())
    return digest.hexdigest()


def _git(repo: Path, *args: str, env: dict[str, str] | None = None,
         stdin: str | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, capture_output=True, text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})},
        timeout=GIT_TIMEOUT_S, check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {result.stderr.strip()[:400]}")
    return result.stdout.strip()


def _rev(repo: Path, ref: str) -> str:
    """The commit a ref names, or "" when it does not exist."""
    return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)


def _identity(repo: Path) -> dict[str, str]:
    """His configured identity when there is one; a named bot otherwise, so a
    machine without `user.email` still commits."""
    if _git(repo, "config", "user.email", check=False):
        return {}
    return {"GIT_AUTHOR_NAME": "Mission HQ", "GIT_AUTHOR_EMAIL": "hq@localhost",
            "GIT_COMMITTER_NAME": "Mission HQ", "GIT_COMMITTER_EMAIL": "hq@localhost"}


def publish_to_branch(bundle: Path, *, repo: Path = REPO_DIR, branch: str = READER_BRANCH,
                      remote: str = "origin", prefix: str = "frontend/public/reader",
                      base: str = "main", push: bool = True) -> dict[str, Any]:
    """Commit `bundle` at `prefix` on `branch` and push it, when it changed.

    Returns what happened: `committed` (the new commit or ""), `pushed`,
    `fingerprint`, and `error` when a step failed. Never raises: it runs
    inside the nightly tick, and a failed push (no network, no credential)
    must not cost the night anything else. A commit that could not be pushed
    stays on the local branch and goes out with the next run that can push.
    """
    out: dict[str, Any] = {"branch": branch, "committed": "", "pushed": False,
                           "fingerprint": "", "error": ""}
    try:
        if not bundle.is_dir():
            raise RuntimeError(f"no bundle at {bundle}")
        prefix = prefix.strip("/")
        fp = fingerprint(bundle)
        out["fingerprint"] = fp
        local = _rev(repo, f"refs/heads/{branch}")
        parent = local or _rev(repo, f"refs/remotes/{remote}/{branch}")
        previous = _git(repo, "log", "-1", "--format=%B", parent, check=False) if parent else ""
        if f"{FINGERPRINT_TRAILER}: {fp}" not in previous:
            base_commit = (_rev(repo, f"refs/remotes/{remote}/{base}") or parent
                           or _rev(repo, f"refs/heads/{base}"))
            if not base_commit:
                raise RuntimeError(f"nothing to build on: no {remote}/{base}, {branch} or {base}")
            tree = _bundle_tree(repo, bundle, prefix, base_commit)
            count = sum(1 for p in bundle.rglob("*") if p.is_file())
            message = (f"Reader bundle, {datetime.now().astimezone():%Y-%m-%d %H:%M}\n\n"
                       f"{count} file(s) at {prefix}, on {base_commit[:12]}.\n\n"
                       f"{FINGERPRINT_TRAILER}: {fp}\n")
            commit = _git(repo, "commit-tree", tree, *(["-p", parent] if parent else []),
                          "-F", "-", env=_identity(repo), stdin=message)
            # The old value makes this a compare-and-swap: if anything moved
            # the branch meanwhile, this fails instead of dropping its commit.
            _git(repo, "update-ref", f"refs/heads/{branch}", commit, local or "0" * 40)
            out["committed"] = commit
        tip = _rev(repo, f"refs/heads/{branch}")
        if push and tip and tip != _rev(repo, f"refs/remotes/{remote}/{branch}"):
            _git(repo, "push", "--quiet", remote, f"refs/heads/{branch}:refs/heads/{branch}")
            out["pushed"] = True
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        out["error"] = str(exc)[:500]
        log.warning("reader: publish to %s failed: %s", branch, exc)
    return out


def _bundle_tree(repo: Path, bundle: Path, prefix: str, base_commit: str) -> str:
    """The base commit's tree with `prefix` replaced by the bundle, built in a
    throwaway index so his own index and working tree are never read or written."""
    files = sorted(p for p in bundle.rglob("*") if p.is_file())
    with tempfile.TemporaryDirectory(prefix="hq-reader-index-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(repo, "read-tree", base_commit, env=env)
        old = _git(repo, "ls-files", "-z", "--", prefix, env=env)
        if old:
            _git(repo, "update-index", "-z", "--force-remove", "--stdin", env=env, stdin=old)
        blobs = _git(repo, "hash-object", "-w", "--no-filters", "--stdin-paths",
                     stdin="".join(f"{p}\n" for p in files)).splitlines() if files else []
        entries = "".join(
            f"100644 {sha}\t{prefix}/{p.relative_to(bundle).as_posix()}\0"
            for p, sha in zip(files, blobs, strict=True))
        if entries:
            _git(repo, "update-index", "-z", "--index-info", env=env, stdin=entries)
        return _git(repo, "write-tree", env=env)


async def publish_nightly() -> dict[str, Any]:
    """Build the bundle and publish it to the `reader` branch. Never raises.

    Built into a temporary folder, not `frontend/public/reader`: that folder
    is tracked on `main`, and rewriting it every night would leave his
    working tree dirty. `export-reader` still writes it for a manual run.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="hq-reader-") as tmp:
            made = await build(Path(tmp) / "reader")
            result = await asyncio.to_thread(publish_to_branch, Path(made["dir"]))
            return {**result, "pages": made["pages"]}
    except Exception as exc:
        log.warning("reader: nightly export failed", exc_info=True)
        return {"branch": READER_BRANCH, "committed": "", "pushed": False,
                "fingerprint": "", "error": str(exc)[:500]}
