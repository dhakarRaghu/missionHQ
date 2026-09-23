"""The lab behind a course phase, and the study note a phase was written from.

Tutor writes a lab with `write_lab_files` and reads it back with `read_lab`
(the Saturday lab card). `_study_note` finds hunter's note for a phase; the
staged lesson writer and the page checks read it.

None of these tools read the web and none of them act outward.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic_ai import ModelRetry, RunContext

from hq import db, labs, memory
from hq.config import settings
from hq.obs import emit
from hq.safety import ActionClass, Trust
from hq.tools.registry import HQDeps, hq_tool

log = logging.getLogger(__name__)

def _clean_slug(slug: str) -> str:
    clean = (slug or "").strip()
    if not labs.SLUG_RE.match(clean):
        raise ModelRetry(
            f"slug {slug!r} is not a phase slug; use the exact course_phases slug,"
            " e.g. elite-performance-phase-01-measurement-before-optimisation"
        )
    return clean


def _repo_root() -> Path:
    return settings().learning_dir.parent


def _rel(path: Path) -> str:
    try:
        return path.relative_to(_repo_root()).as_posix()
    except ValueError:
        return str(path)


async def _phase_row(slug: str) -> dict[str, Any] | None:
    return await db.fetchone(
        "SELECT slug, course, phase_order, title, summary, category, difficulty,"
        " minutes, url, status, source, question, sections, lab, test_out, spec_path"
        " FROM hq.course_phases WHERE slug = %s",
        (slug,),
    )


async def _newest_course_lesson(slug: str) -> dict[str, Any] | None:
    return await db.fetchone(
        "SELECT id::text AS id, title, md_path, html_path FROM hq.lessons"
        " WHERE kind = 'course' AND course_slug = %s"
        " ORDER BY created_at DESC LIMIT 1",
        (slug,),
    )


def _read_repo_text(rel: str) -> str:
    """A lesson file by its repo-relative path, or "" when there is none.
    Same containment rule as read_lesson: under learning/, nowhere else."""
    clean = (rel or "").strip()
    if not clean:
        return ""
    path = PurePosixPath(clean)
    if path.is_absolute() or ".." in path.parts:
        return ""
    root = settings().learning_dir.resolve()
    full = (root.parent / path).resolve()
    if root not in full.parents or not full.is_file():
        return ""
    return full.read_text(encoding="utf-8", errors="replace")


async def _study_note(slug: str) -> tuple[str, str]:
    """(vault path, text) of hunter's study note for this phase, or ("", "").

    'taught' counts as well as 'digested': when tutor passes the phase url to
    record_lesson the reading flips to taught, and a review that runs after
    that must still find the note it is checking against.
    """
    row = await db.fetchone(
        "SELECT r.digest_path FROM hq.readings r"
        " JOIN hq.course_phases c ON r.url = c.url"
        " WHERE c.slug = %s AND r.status IN ('digested', 'taught') AND r.digest_path <> ''"
        " ORDER BY (r.status = 'digested') DESC, r.last_seen DESC LIMIT 1",
        (slug,),
    )
    path = str((row or {}).get("digest_path") or "")
    if not path:
        return "", ""
    try:
        return path, await asyncio.to_thread(memory.read, path)
    except (OSError, PermissionError) as exc:
        log.warning("study note %s for %s unreadable: %s", path, slug, exc)
        return path, ""


@hq_tool(action=ActionClass.VAULT_WRITE, trust=Trust.TOOL, owner_only=False)
async def write_lab_files(ctx: RunContext[HQDeps], slug: str, files: dict[str, str]) -> str:
    """Write the lab for one course phase: its files plus `exercises.json`.

    `files` maps a path relative to the lab (`e01/main.go`) to its text. It
    replaces the whole lab at `learning/labs/<slug>/`; send every file each time.

    The rules, and why. His inference course shipped commands that did not
    run, so every exercise here is run by the reviewer, in a sandbox, before
    he sees it:
      - no network. The sandbox denies it, so an exercise that downloads or
        calls an API fails.
      - standard library only. `go.mod` may not `require` anything and
        GOPROXY is off; a dependency can never be fetched.
      - no shell. `run` is one command starting with `go` or `python3`, with
        no pipes, redirects, `;`, `&` or `$`. Do that work inside the program.
      - `expect` regexes are matched against the combined stdout and stderr;
        `verify: manual` needs `why_manual` saying why code cannot check it.
    """
    slug = _clean_slug(slug)
    if await _phase_row(slug) is None:
        raise ModelRetry(f"no course phase with slug {slug!r}; call list_courses for the slug")
    problems = labs.validate_lab_files(slug, files)
    if problems:
        raise ModelRetry(
            "the lab was not written. Fix every one of these and call write_lab_files"
            " again with the full set of files:\n- " + "\n- ".join(problems)
        )
    try:
        path = await asyncio.to_thread(labs.write_lab, slug, files)
    except ValueError as exc:
        # A symlink in the lab's path. Not something a retry fixes.
        return f"the lab was not written: {exc}"
    manifest = labs.read_manifest(path) or {}
    exercises = len(manifest.get("exercises") or [])
    rel = _rel(path)
    await emit("lab.written", run_id=ctx.deps.run_id, agent=ctx.deps.agent,
               payload={"slug": slug, "path": rel, "files": len(files),
                        "exercises": exercises})
    return (f"wrote {len(files)} files with {exercises} exercises to {rel};"
            " the reviewer runs them with run_lab")


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def read_lab(ctx: RunContext[HQDeps], slug: str) -> dict[str, Any]:
    """Read a course phase's lab without running it. Reads no web.

    Returns `files` (each text file's `path`, `bytes` and `content`, cut at
    60 KB per file and 400 KB in total with a marker where cut), `manifest`
    (the parsed `exercises.json`, or null) and `results` (the last
    `RESULTS.json` from run_lab, or null). Symlinks are listed in `skipped`
    and never followed. Call it before rewriting a lab: `write_lab_files`
    replaces the whole folder.
    """
    slug = _clean_slug(slug)
    try:
        return await asyncio.to_thread(labs.read_lab_snapshot, labs.lab_dir(slug))
    except (ValueError, OSError) as exc:
        return {"slug": slug, "error": str(exc)}
