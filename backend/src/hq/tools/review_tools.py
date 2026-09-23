"""The review side of a course phase: the lab tutor ships, and the reviewer's checks.

Two agents, one gate. Tutor writes the lab with `write_lab_files`. Reviewer
reads the spec with `read_course_spec` and the lab with `read_lab`, runs the
lab with `run_lab`, checks
the lesson with `check_phase`, and files a verdict with `record_review`.

Reviewer never rewrites. A reviewer that edits the lesson becomes a second
writer that nobody reviews, which is how the inference course shipped
commands that did not run: the author was also the only check.

None of these tools read the web and none of them act outward.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic_ai import ModelRetry, RunContext

from hq import courses as courses_spec
from hq import db, labs, memory
from hq.config import settings
from hq.learning_pipeline import COURSE_REVIEW_STAGE
from hq.obs import emit
from hq.safety import ActionClass, Trust
from hq.tools.learning_tools import REVIEW_TASK_WRITES, current_task_stage
from hq.tools.registry import HQDeps, hq_tool

log = logging.getLogger(__name__)

VERDICTS = {"pass": "passed", "revise": "revise"}
MAX_REVIEW_NOTES = 20_000
# The 130-point rubric: thirteen dimensions scored 0-10, the same scale the
# review-phase skill, tutor's self-score and the course reader all use.
MAX_SCORE = 130


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
    if await current_task_stage(ctx.deps.task_id) == COURSE_REVIEW_STAGE:
        raise ModelRetry(REVIEW_TASK_WRITES)
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
async def read_course_spec(ctx: RunContext[HQDeps], slug: str) -> dict[str, Any]:
    """The spec a course phase was written against. Reads no web.

    A local phase returns its spec from `learning/courses/`: the question,
    the numbered sections, what it assumes, introduces and leaves for later,
    and the lab, demonstrate and test-out blocks. A platform phase has no
    spec file; its shape is in hunter's study note.
    """
    slug = _clean_slug(slug)
    local = await asyncio.to_thread(courses_spec.find_phase, slug)
    if local is not None:
        course, phase = local
        return {
            "source": "local",
            "slug": slug,
            "course": course.title,
            "title": phase.title,
            "question": phase.question,
            "sections": [f"{phase.order}.{i + 1} {title}"
                         for i, title in enumerate(phase.sections)],
            "assumes": phase.assumes,
            "introduces": phase.introduces,
            "leaves_for_later": phase.leaves_for_later,
            "lab": phase.lab,
            "demonstrate": phase.demonstrate,
            "test_out": phase.test_out,
            "spec_block": phase.body,
            "spec_path": course.path,
        }
    row = await _phase_row(slug)
    if row is None:
        raise ModelRetry(f"no course phase with slug {slug!r}")
    note = (
        "this phase comes from his study platform and has no spec file; the"
        " module's shape (word count, headings, sequence) is in hunter's study note"
    )
    if row.get("source") == "local":
        note = "the phase is recorded as local but its spec is no longer in learning/courses/"
    return {**row, "source": row.get("source") or "platform", "note": note}


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


async def _phase_findings(slug: str) -> dict[str, Any]:
    """The deterministic findings for the newest lesson of a phase.

    Shared by `check_phase`, which reports them, and `record_review`, which
    refuses a pass while any of them blocks.
    """
    lesson = await _newest_course_lesson(slug)
    if lesson is None:
        if await _phase_row(slug) is None:
            raise ModelRetry(f"no course phase with slug {slug!r}")
        return {"error": "no course lesson recorded for this phase", "findings": [],
                "blocking": 0}
    md = await asyncio.to_thread(_read_repo_text, lesson["md_path"])
    html = await asyncio.to_thread(_read_repo_text, lesson["html_path"])
    note_path, note = await _study_note(slug)

    numbers: list[str] = []
    sections: list[str] = []
    lab_expected = True
    local = await asyncio.to_thread(courses_spec.find_phase, slug)
    if local is not None:
        _, phase = local
        sections = list(phase.sections)
        numbers = [f"{phase.order}.{i + 1}" for i in range(len(sections))]
        lab_expected = bool(phase.lab.strip())
    manifest = await asyncio.to_thread(labs.read_manifest, labs.lab_dir(slug))

    findings = labs.check_phase_text(md, html, note, sections, numbers, manifest,
                                     lab_expected)
    if not md:
        findings.insert(0, labs._finding(
            "lesson file", "block", lesson["md_path"] or "md_path",
            "the recorded lesson markdown is missing from the repo",
            "tutor must write the lesson with write_lesson and record it again",
        ))
    blocking = sum(f["severity"] == "block" for f in findings)
    return {
        "lesson_path": lesson["md_path"],
        "html_path": lesson["html_path"],
        "note_path": note_path,
        "findings": findings,
        "blocking": blocking,
    }


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def check_phase(ctx: RunContext[HQDeps], slug: str) -> dict[str, Any]:
    """Run the deterministic checks on the newest lesson for a course phase.

    Spec coverage, url provenance against the study note, page completeness,
    the could-not-verify section, the lab's exercises, banned words, idioms
    and prose walls. Code, not judgement: a `block` finding stands until the
    lesson changes.
    """
    return await _phase_findings(_clean_slug(slug))


@hq_tool(action=ActionClass.VAULT_WRITE, trust=Trust.TOOL, owner_only=False)
async def run_lab(ctx: RunContext[HQDeps], slug: str) -> dict[str, Any]:
    """Run the phase's lab in the sandbox and write `RESULTS.md` beside it.

    Each `verify: auto` exercise runs on a fresh copy with no network and no
    writes outside its temp folder; pass means the exit code and every
    `expect` regex matched. These results are final for the review: a failed
    exercise cannot be argued into a pass.
    """
    slug = _clean_slug(slug)
    directory = labs.lab_dir(slug)
    if not (directory / labs.MANIFEST).is_file():
        return {"error": "no lab written for this phase"}
    try:
        results = await asyncio.to_thread(labs.run_exercises, directory)
    except (ValueError, RuntimeError) as exc:
        return {"error": str(exc)}
    md = await asyncio.to_thread(labs.write_results, directory, results)
    counts = labs.summarize(results)
    await emit("lab.ran", run_id=ctx.deps.run_id, agent=ctx.deps.agent,
               payload={"slug": slug, **counts,
                        "failed_ids": [r.id for r in results if r.status == "fail"]})
    return {**counts, "results_path": _rel(md),
            "results": [r.to_dict() for r in results]}


@hq_tool(action=ActionClass.VAULT_WRITE, trust=Trust.TOOL, owner_only=False)
async def record_review(
    ctx: RunContext[HQDeps], slug: str, verdict: str, score: int, findings: str
) -> str:
    """File the verdict on the newest lesson for a course phase.

    `verdict` is `pass` or `revise`; `score` is 0 to 130, the sum of the
    thirteen 0-10 rubric dimensions; `findings` are the
    notes the writer acts on. A pass is refused while an auto exercise has
    failed, or while the lab exists and has not been run: those results are
    measured, and a verdict is not allowed to outvote them.
    """
    if await current_task_stage(ctx.deps.task_id) != COURSE_REVIEW_STAGE:
        raise ModelRetry(
            "record_review runs only in a review task. A writing run cannot"
            " approve its own work; the review is a separate run started after"
            " this one finishes."
        )
    slug = _clean_slug(slug)
    choice = (verdict or "").strip().lower()
    if choice not in VERDICTS:
        raise ModelRetry("verdict must be 'pass' or 'revise'")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= MAX_SCORE:
        raise ModelRetry(f"score must be an integer from 0 to {MAX_SCORE}")
    lesson = await _newest_course_lesson(slug)
    if lesson is None:
        raise ModelRetry(f"no course lesson recorded for {slug!r}; nothing to review")

    if choice == "pass":
        directory = labs.lab_dir(slug)
        results = await asyncio.to_thread(labs.read_results, directory)
        if results is not None and int(results.get("failed") or 0) > 0:
            raise ModelRetry("an auto exercise failed; the verdict cannot be pass")
        if results is None and (directory / labs.MANIFEST).is_file():
            raise ModelRetry("the lab has not been run; call run_lab before a pass")
        # The skill already said a blocking finding means revise. It was a
        # sentence the reviewer could talk itself past, and every rule on this
        # path that lived only in prose was eventually ignored. So it is code.
        checks = await _phase_findings(slug)
        blocking = int(checks.get("blocking") or 0)
        if blocking:
            raise ModelRetry(
                f"check_phase still has {blocking} blocking finding(s); the verdict"
                " cannot be pass until the lesson changes"
            )

    notes = (findings or "").strip()[:MAX_REVIEW_NOTES]
    row = await db.fetchone(
        "UPDATE hq.lessons SET review_status = %s, review_score = %s,"
        " review_notes = %s, reviewed_at = now(), review_round = review_round + 1"
        " WHERE id = %s::uuid RETURNING review_round",
        (VERDICTS[choice], score, notes, lesson["id"]),
    )
    review_round = int((row or {}).get("review_round") or 0)
    await emit("lesson.reviewed", run_id=ctx.deps.run_id, agent=ctx.deps.agent,
               payload={"slug": slug, "lesson_id": lesson["id"], "verdict": choice,
                        "score": score, "round": review_round})
    return (f"recorded {choice} ({score}/{MAX_SCORE}) for {lesson['title'][:80]!r},"
            f" review round {review_round}")
