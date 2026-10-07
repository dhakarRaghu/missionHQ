"""Stage 1: from a finished lesson to a reviewed script and scene spec.

The writer is the `deep` model (kimi_deep). The two reviewers run on the
`teacher` model (kimi_k3), a different model, so a mistake the writer makes
is not repeated by its own judge. Every call is at the effort value that is
measured to work on this gateway ("high", see backend/models.yaml); depth
comes from the reviews and the repair rounds, not from the effort string.

Order of work, each step checked before the next:

1. gather   the lesson (and, for a course phase, hunter's study note)
2. plan     one plan, checked by code; sent back with what failed (4 tries)
3. beats    one call per beat, each given the end of the beat before it;
            every line checked by code, a beat sent back twice at most
4. whole    the narration checked as a whole (order, length, short sentences)
5. editor   the teacher scores each concept; weak beats are rewritten with
            its instructions, twice at most
6. facts    the teacher maps every factual line to the material and redoes
            the arithmetic; wrong lines are rewritten, twice at most
7. scenes   one call per beat returns the spec as data; check-spec.mjs
            checks the whole spec; a failing beat is sent back

Every model call is a DBOS step and every artifact is written to the job
folder as soon as it exists, so a restart resumes where it stopped.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.usage import UsageLimits

from hq import db, llm
from hq.dbos_app import DBOS
from hq.tools import learning_tools as lt
from hq.video import checks, paths, register
from hq.video.models import (
    BeatLines,
    EditorVerdict,
    FactVerdict,
    Line,
    VideoJob,
    VideoPlan,
)

log = logging.getLogger(__name__)

WRITER_MODEL = "deep"         # kimi_deep: writes the plan, the beats and the scenes
REVIEW_MODEL = "teacher"      # kimi_k3: a different model reviews what the writer wrote
EFFORT = "high"               # the highest value measured to change anything here
CALL_LIMIT_S = 1500.0         # a long beat at high effort; the idle limit catches a stall
PLAN_ATTEMPTS = 4
BEAT_RETRIES = 2
REVIEW_ROUNDS = 2
SCENE_ATTEMPTS = 3
EDITOR_BAR = 4                # a criterion under this sends the beat back
EDITOR_MEAN = 3.5             # so does a beat whose mean is under this
MATERIAL_CHARS = 120_000
NOTE_CHARS = 60_000

_STEP: dict[str, Any] = {"retries_allowed": True, "max_attempts": 2, "interval_seconds": 10.0,
                         "backoff_rate": 2.0, "timeout_seconds": CALL_LIMIT_S * 3 + 60.0}


# --- instructions ----------------------------------------------------------------

def _read(name: str) -> str:
    return (paths.prompts_dir() / name).read_text()


def _charter() -> str:
    path = paths.prompts_dir().parent.parent / "_shared" / "charter.md"
    return path.read_text() if path.is_file() else ""


def _teacher() -> str:
    return (paths.prompts_dir().parent / "writer" / "teacher.md").read_text()


def instructions(stage: str) -> str:
    """Writer stages get the charter, the teacher and the video rules; the
    reviewers get only what they judge against, so they read as outsiders."""
    if stage in {"editor", "factcheck", "frames"}:
        extra = _read("rules.md") if stage == "editor" else ""
        return "\n\n".join(x for x in (_read(f"{stage}.md"), extra) if x)
    parts = [_charter(), _teacher(), _read("rules.md"), _read(f"{stage}.md")]
    if stage == "scenes":
        parts.append((paths.project_dir() / "SPEC.md").read_text())
    return "\n\n".join(p for p in parts if p)


def _settings(role: str) -> Any:
    reg = llm.registry()
    out = dict(reg.model_settings_for(role) or {})
    out["openai_reasoning_effort"] = EFFORT
    out["timeout"] = CALL_LIMIT_S
    return cast(Any, out)


async def _ask(role: str, stage: str, prompt: str, output: Any, requests: int = 4) -> Any:
    reg = llm.registry()
    agent = Agent(reg.resolve(role), output_type=PromptedOutput(output) if output is not str
                  else str, retries=3, instructions=instructions(stage),
                  model_settings=_settings(role))
    result = await agent.run(prompt, usage_limits=UsageLimits(request_limit=requests))
    return result.output


# --- the model calls, each a durable step ------------------------------------------

@DBOS.step(name="video.plan", **_STEP)
async def _plan_step(prompt: str) -> dict[str, Any]:
    return cast(VideoPlan, await _ask(WRITER_MODEL, "plan", prompt, VideoPlan)).model_dump()


@DBOS.step(name="video.beat", **_STEP)
async def _beat_step(prompt: str) -> dict[str, Any]:
    return cast(BeatLines, await _ask(WRITER_MODEL, "beat", prompt, BeatLines)).model_dump()


@DBOS.step(name="video.editor", **_STEP)
async def _editor_step(prompt: str) -> dict[str, Any]:
    return cast(EditorVerdict, await _ask(REVIEW_MODEL, "editor", prompt,
                                          EditorVerdict)).model_dump()


@DBOS.step(name="video.factcheck", **_STEP)
async def _fact_step(prompt: str) -> dict[str, Any]:
    return cast(FactVerdict, await _ask(REVIEW_MODEL, "factcheck", prompt,
                                        FactVerdict)).model_dump()


@DBOS.step(name="video.scenes", **_STEP)
async def _scenes_step(prompt: str) -> str:
    return str(await _ask(WRITER_MODEL, "scenes", prompt, str))


@DBOS.step(name="video.check_spec", retries_allowed=False, timeout_seconds=300.0)
async def _check_spec_step(work: str) -> list[str]:
    """Run video/scripts/check-spec.mjs on the job folder's two files."""
    folder = Path(work)
    node = paths.node_bin() / "node"
    script = paths.project_dir() / "scripts" / "check-spec.mjs"
    proc = await asyncio.create_subprocess_exec(
        str(node), str(script), str(folder / "narration.json"), str(folder / "spec.json"),
        cwd=str(paths.project_dir()), stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT)
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=240)
    text = out.decode(errors="replace").strip()
    if proc.returncode == 0:
        return []
    return [ln for ln in text.splitlines() if ln.strip()][:80] or [f"check-spec exited {proc.returncode}"]


@DBOS.step(name="video.gather")
async def _gather_step(payload: dict[str, Any]) -> dict[str, Any]:
    return await gather(payload)


@DBOS.step(name="video.reset")
async def _reset_step(video_id: str) -> None:
    """A new script makes the old scenes, voice and stills wrong: clear them,
    so nothing later reuses scenes drawn for different lines."""
    import shutil

    folder = paths.work_dir(video_id)
    for name in ("spec.json", f"{video_id}.timing.json", "verify.json", "sheet.jpg"):
        (folder / name).unlink(missing_ok=True)
    for sub in ("stills", "audio"):
        shutil.rmtree(folder / sub, ignore_errors=True)


@DBOS.step(name="video.save")
async def _save_step(video_id: str, name: str, data: Any) -> None:
    folder = paths.work_dir(video_id)
    folder.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2)
    (folder / name).write_text(text + ("\n" if not text.endswith("\n") else ""))


# --- the job file ----------------------------------------------------------------------

def load_job(video_id: str) -> VideoJob | None:
    path = paths.work_dir(video_id) / "job.json"
    return VideoJob.model_validate_json(path.read_text()) if path.is_file() else None


def save_job(job: VideoJob) -> None:
    folder = paths.work_dir(job.id)
    folder.mkdir(parents=True, exist_ok=True)
    job.updated = datetime.now(UTC).isoformat(timespec="seconds")
    (folder / "job.json").write_text(job.model_dump_json(indent=2) + "\n")


@DBOS.step(name="video.job")
async def _job_step(job: dict[str, Any]) -> None:
    save_job(VideoJob.model_validate(job))


# --- material --------------------------------------------------------------------------

def video_id_for(lesson_md: str) -> str:
    stem = Path(lesson_md).stem
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    return register.slugify(stem)[:80]


async def gather(payload: dict[str, Any]) -> dict[str, Any]:
    """The lesson, its study note and what earlier videos of the course asked."""
    from hq.tools.review_tools import _study_note

    lesson_md = str(payload.get("lesson_md") or "")
    text = await asyncio.to_thread(lt._read_lesson_text, lesson_md)
    if not text:
        raise ValueError(f"lesson {lesson_md!r} is missing or outside learning/lessons")
    row = await db.fetchone(
        "SELECT title, kind, phase_slug FROM hq.lessons WHERE md_path = %s", (lesson_md,))
    slug = str((row or {}).get("phase_slug") or payload.get("slug") or "")
    course = ""
    if slug:
        crow = await db.fetchone("SELECT course FROM hq.course_phases WHERE slug = %s", (slug,))
        course = str((crow or {}).get("course") or "")
    course_title = ""
    if course:
        trow = await db.fetchone("SELECT title FROM hq.courses WHERE course = %s", (course,))
        course_title = str((trow or {}).get("title") or "")
    note_path, note = ("", "")
    if payload.get("mode") == "course" and slug:
        note_path, note = await _study_note(slug)
    next_title = ""
    if slug and course:
        nxt = await db.fetchone(
            "SELECT title FROM hq.course_phases WHERE course = %s AND phase_order >"
            " (SELECT phase_order FROM hq.course_phases WHERE slug = %s)"
            " ORDER BY phase_order LIMIT 1", (course, slug))
        next_title = str((nxt or {}).get("title") or "") if payload.get("mode") == "course" else ""
    asked = []
    for v in register.manifest()["videos"]:
        if course and v.get("course") == course:
            asked += [f"- {q}" for q in v.get("think_questions") or []]
    return {
        "lesson_md": lesson_md, "title": str((row or {}).get("title") or Path(lesson_md).stem),
        "kind": str((row or {}).get("kind") or ""), "slug": slug, "course": course,
        "lesson": text[:MATERIAL_CHARS], "note_path": note_path, "note": note[:NOTE_CHARS],
        "asked_before": "\n".join(asked), "next_title": next_title,
        "course_title": course_title,
    }


def material_text(m: dict[str, Any]) -> str:
    parts = [f"# The lesson ({m['lesson_md']})\n\n{m['lesson']}"]
    if m.get("note"):
        parts.append(f"# Hunter's study note for it ({m['note_path']})\n\n{m['note']}")
    if m.get("asked_before"):
        parts.append("# Think-it-through questions earlier videos of this course already"
                     f" asked (do not ask them again)\n\n{m['asked_before']}")
    return "\n\n".join(parts)


# --- prompts -----------------------------------------------------------------------------

def _plan_prompt(mode: str, m: dict[str, Any], problems: Sequence[str],
                 previous: dict[str, Any] | None) -> str:
    prompt = (f"Mode: {mode}\nCourse: {m.get('course') or '(an article, no course)'}\n\n"
              + material_text(m))
    if problems:
        prompt += ("\n\n## Your previous plan\n\n```json\n"
                   + json.dumps(previous, ensure_ascii=False) + "\n```\n\n## What was sent back\n\n"
                   + "\n".join(f"- {p}" for p in problems)
                   + "\n\nChange only what is named and keep every other field. Return the"
                     " whole plan.")
    return prompt


def _beat_row(plan: VideoPlan, beat: str) -> str:
    if checks.CONCEPT_BEAT.match(beat):
        c = next(c for c in plan.concepts if c.id == beat)
        return json.dumps(c.model_dump(), ensure_ascii=False, indent=1)
    if beat == "cold":
        return json.dumps({"running_case": plan.running_case, "cold_open": plan.cold_open,
                           "question": plan.question}, ensure_ascii=False, indent=1)
    if beat == "title":
        return json.dumps({"title": plan.title,
                           "concepts": [c.heading for c in plan.concepts]}, ensure_ascii=False)
    if beat == "payoff":
        return json.dumps({"question": plan.question, "payoff": plan.payoff},
                          ensure_ascii=False, indent=1)
    if beat == "recap":
        return json.dumps({"remember": [c.claim for c in plan.concepts]}, ensure_ascii=False)
    return json.dumps({"left_out": plan.left_out}, ensure_ascii=False)


def _beat_prompt(mode: str, m: dict[str, Any], plan: VideoPlan, beat: str,
                 before: Sequence[Line], problems: Sequence[str] = (),
                 current: Sequence[Line] = ()) -> str:
    tail = "\n".join(f"{ln.key}: {ln.text}" for ln in list(before)[-4:]) or "(this is the first beat)"
    prompt = (f"Mode: {mode}\n\n## The whole plan\n\n```json\n"
              + plan.model_dump_json(indent=1) + "\n```\n\n"
              f"## Write this beat: {beat}\n\n{_beat_row(plan, beat)}\n\n"
              f"## The last lines of the beat before\n\n{tail}\n\n"
              f"## The material\n\n{material_text(m)}")
    if problems:
        prompt += ("\n\n## Your previous lines for this beat\n\n```json\n"
                   + json.dumps([ln.model_dump() for ln in current], ensure_ascii=False)
                   + "\n```\n\n## What must change\n\n" + "\n".join(f"- {p}" for p in problems)
                   + "\n\nKeep every line that was not named. Return all the beat's lines.")
    return prompt


def _narration_text(beats: dict[str, list[Line]]) -> str:
    """The narration as the editor reads it: each caption, and under it what the
    voice actually says when that differs. Without the `say` line the editor
    reported "no line carries a say spelling" on a script where all 62 lines
    that need one had it (first article run, 2026-10-06)."""
    out = []
    for beat, lines in beats.items():
        out.append(f"## {beat}")
        for ln in lines:
            out.append(f"{ln.key}: {ln.text}")
            if ln.say and ln.say != ln.text:
                out.append(f"    (spoken: {ln.say})")
    return "\n".join(out)


# --- the stage ------------------------------------------------------------------------------

class ScriptWriter:
    def __init__(self, job: VideoJob, material: dict[str, Any]) -> None:
        self.job = job
        self.m = material
        self.report: list[str] = []
        self.plan: VideoPlan | None = None
        self.beats: dict[str, list[Line]] = {}

    def note(self, line: str) -> None:
        self.report.append(line)
        log.info("video %s: %s", self.job.id, line)

    async def write_plan(self) -> VideoPlan:
        material = material_text(self.m)
        problems: list[str] = []
        previous: dict[str, Any] | None = None
        for attempt in range(1, PLAN_ATTEMPTS + 1):
            raw = await _plan_step(_plan_prompt(self.job.mode, self.m, problems, previous))
            plan = VideoPlan.model_validate(raw)
            problems = checks.plan_problems(plan, self.job.mode, material)
            if not problems:
                self.note(f"plan accepted on attempt {attempt}: {len(plan.concepts)} concepts")
                return plan
            previous = raw
        raise ValueError("the plan still failed after " f"{PLAN_ATTEMPTS} attempts: {problems[:6]}")

    async def write_beat(self, beat: str, problems: Sequence[str] = ()) -> list[Line]:
        assert self.plan is not None
        order = list(self.beats)
        before = self.beats[order[order.index(beat) - 1]] if beat in order and order.index(beat) else []
        if beat not in order and order:
            before = self.beats[order[-1]]
        current = self.beats.get(beat, [])
        lines: list[Line] = list(current)
        todo = list(problems)
        for attempt in range(BEAT_RETRIES + 1):
            if attempt or not lines or todo:
                raw = await _beat_step(_beat_prompt(self.job.mode, self.m, self.plan, beat,
                                                    before, todo, lines))
                lines = BeatLines.model_validate(raw).lines
            found = [p for ln in lines for p in checks.line_problems(beat, ln)]
            if checks.CONCEPT_BEAT.match(beat):
                found += checks.concept_problems(beat, lines)
            if not found:
                return lines
            todo = found
        self.note(f"{beat}: still {len(todo)} line findings after {BEAT_RETRIES} rewrites,"
                  f" e.g. {todo[0]}")
        return lines

    async def write_all(self) -> None:
        assert self.plan is not None
        for beat in checks.beat_order(len(self.plan.concepts)):
            self.beats[beat] = await self.write_beat(beat)
            await _save_step(self.job.id, "narration.json", self.narration())

    async def review_whole(self) -> None:
        assert self.plan is not None
        problems = checks.narration_problems(self.beats, mode=self.job.mode,
                                             n_concepts=len(self.plan.concepts))
        grouped = checks.by_beat(problems)
        for beat, items in grouped.items():
            if beat in self.beats:
                self.beats[beat] = await self.write_beat(beat, items)
        rest = [p for b, items in grouped.items() if b not in self.beats for p in items]
        for p in rest:
            self.note(f"whole video: {p}")

    async def edit(self) -> dict[str, Any]:
        assert self.plan is not None
        verdict: EditorVerdict | None = None
        for round_no in range(REVIEW_ROUNDS + 1):
            prompt = ("## The plan\n\n```json\n" + self.plan.model_dump_json(indent=1)
                      + "\n```\n\n## The narration\n\n" + _narration_text(self.beats))
            verdict = EditorVerdict.model_validate(await _editor_step(prompt))
            weak: dict[str, list[str]] = {}
            for s in verdict.scores:
                if s.beat in self.beats and (s.low(EDITOR_BAR) or s.mean() < EDITOR_MEAN):
                    weak.setdefault(s.beat, [])
            for f in verdict.findings:
                if f.beat in self.beats:
                    weak.setdefault(f.beat, []).append(
                        f"{f.criterion}: {f.quote!r}: {f.problem}. {f.instruction}")
            # A whole-video finding (one thing with two names, a running case
            # that changes person, a label dropped on a later mention) goes to
            # every beat it names, so it is fixed rather than only reported.
            for item in verdict.whole_video:
                for beat in self.beats:
                    if re.search(rf"\b{re.escape(beat)}\b", item):
                        weak.setdefault(beat, []).append(f"whole video: {item}")
            if not weak or round_no == REVIEW_ROUNDS:
                break
            for beat, items in weak.items():
                self.beats[beat] = await self.write_beat(
                    beat, items or [("the teaching editor scored this beat under the bar;"
                                     " make every step clearer and better connected")])
            await _save_step(self.job.id, "narration.json", self.narration())
        assert verdict is not None
        means = {s.beat: round(s.mean(), 2) for s in verdict.scores}
        self.note("editor means: " + ", ".join(f"{b} {v}" for b, v in means.items()))
        for w in verdict.whole_video:
            self.note(f"editor, whole video: {w}")
        return verdict.model_dump()

    async def check_facts(self, only: Sequence[str] | None = None) -> list[dict[str, Any]]:
        table: list[dict[str, Any]] = []
        material = material_text(self.m)
        for beat in [b for b in self.beats if only is None or b in only]:
            for round_no in range(REVIEW_ROUNDS + 1):
                lines = "\n".join(f"{ln.key}: {ln.text}" for ln in self.beats[beat])
                verdict = FactVerdict.model_validate(await _fact_step(
                    f"## The material\n\n{material}\n\n## The narration of beat {beat}\n\n{lines}"))
                wrong = [i for i in verdict.items if i.verdict in ("contradicted", "unsupported")]
                if not wrong or round_no == REVIEW_ROUNDS:
                    table += [{"beat": beat, **i.model_dump()} for i in verdict.items]
                    for i in wrong:
                        self.note(f"fact still {i.verdict} at {beat}.{i.key}: {i.correction}")
                    break
                fixes = [(f"{i.key} is {i.verdict}: "
                          + (i.correction or "the material does not carry it; remove it or"
                             " teach the mechanism without it")
                          + (f" (material: {i.material_quote!r})" if i.material_quote else ""))
                         for i in wrong]
                self.beats[beat] = await self.write_beat(beat, fixes)
            await _save_step(self.job.id, "narration.json", self.narration())
        return table

    def narration(self) -> dict[str, Any]:
        assert self.plan is not None
        heads = {c.id: c.heading for c in self.plan.concepts}
        heads.update({"cold": self.plan.title, "payoff": "Back to the question", "recap": "Recap"})
        return {
            "engine": "kokoro", "voice": "af_heart", "speed": 0.94, "fadeTailS": 0.3,
            "leadinS": 0.4, "holdS": 1.8, "gapS": 0.8,
            "beats": {b: {**({"chapter": heads[b]} if b in heads else {}),
                          "lines": [ln.model_dump(exclude_defaults=True) for ln in lines]}
                      for b, lines in self.beats.items()},
        }

    async def write_scenes(self) -> dict[str, Any]:
        assert self.plan is not None
        # The course's name as people read it ("Inference Internals"), never
        # its slug; "Learn" for an article.
        label = (self.m.get("course_title") or str(self.m.get("course") or "Learn")
                 .replace("-", " ").title())[:40]
        spec: dict[str, Any] = {
            "version": 1, "id": self.job.id, "mode": self.job.mode, "series": label,
            "number": None, "title": self.plan.title, "label": label,
            "site": "Mission HQ · Learn", "beats": []}
        if self.m.get("next_title"):
            spec["next"] = {"number": None, "title": str(self.m["next_title"])[:60]}
        beats: list[dict[str, Any]] = []
        problems: dict[str, list[str]] = {}
        # A spec saved by an earlier run (a restart, a repair) is checked first,
        # and only the beats check-spec refuses are drawn again.
        saved = paths.work_dir(self.job.id) / "spec.json"
        if saved.is_file():
            old = json.loads(saved.read_text()).get("beats") or []
            if {b.get("id") for b in old} == set(self.beats):
                beats = old
        for attempt in range(SCENE_ATTEMPTS + (1 if beats else 0)):
            if beats and attempt == 0:
                redo: list[str] = []
            else:
                redo = [b for b in self.beats if not beats or problems.get(b)]
            for beat in redo:
                lines = "\n".join(f"{ln.key}: {ln.text}" for ln in self.beats[beat])
                ask = (f"## Return the spec beat for: {beat}\n\nIts narration:\n{lines}\n\n"
                       f"## Its plan row\n\n{_beat_row(self.plan, beat)}\n\n"
                       "Return only the JSON object of this one beat.")
                if problems.get(beat):
                    ask += "\n\n## What check-spec refused last time\n\n" + "\n".join(
                        f"- {p}" for p in problems[beat])
                text = await _scenes_step(ask)
                obj = _json_object(text)
                if obj and checks.CONCEPT_BEAT.match(beat):
                    # What code knows, code writes: the concept's heading and
                    # its "2 of 6" count come from the plan, not the model.
                    n = len(self.plan.concepts)
                    i = int(beat[1:])
                    obj["count"] = f"{i} of {n}"
                    obj["heading"] = self.plan.concepts[i - 1].heading
                beats = [b for b in beats if b.get("id") != beat]
                beats.append(obj if obj else {"id": beat, "kind": "invalid"})
            order = list(self.beats)
            beats.sort(key=lambda b: order.index(b["id"]) if b.get("id") in order else 99)
            spec["beats"] = beats
            await _save_step(self.job.id, "spec.json", spec)
            found = await _check_spec_step(str(paths.work_dir(self.job.id)))
            problems = {}
            narration_fix: dict[str, list[str]] = {}
            for p in found:
                if re.fullmatch(r"\d+ problems?\.?", p.strip()):
                    continue  # check-spec's closing count, not a finding
                b = _beat_in(p, order)
                if p.startswith("narration:") and b:
                    # The spoken lines break the contract (for example a fourth
                    # key point): the narration of that beat is rewritten, and
                    # its scenes are drawn again from the new lines.
                    narration_fix.setdefault(b, []).append(p)
                    problems.setdefault(b, []).append(p)
                elif b:
                    problems.setdefault(b, []).append(p)
                else:
                    # A spec field no beat owns: a fault in this code, not in
                    # what the model wrote, so retrying the model cannot fix it.
                    raise ValueError(f"check-spec refused a field the code writes: {p}")
            for b, items in narration_fix.items():
                self.beats[b] = await self.write_beat(b, items)
            if narration_fix:
                await _save_step(self.job.id, "narration.json", self.narration())
            if not found:
                self.note(f"scenes accepted by check-spec on attempt {attempt + 1}")
                return spec
        self.note(f"check-spec still refuses: {sum(len(v) for v in problems.values())} problems")
        raise ValueError("the scene spec did not pass check-spec: "
                         + "; ".join(p for v in problems.values() for p in v)[:900])


def _json_object(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _beat_in(problem: str, order: Sequence[str]) -> str:
    """check-spec names a JSON path (beats[3], beats.c3) or a beat id; map it to the beat."""
    m = re.search(r"beats\[(\d+)\]", problem)
    if m and int(m.group(1)) < len(order):
        return order[int(m.group(1))]
    m = re.search(r"beats\.([a-z0-9]+)", problem)
    if m and m.group(1) in order:
        return m.group(1)
    for b in order:
        if re.search(rf"\b{re.escape(b)}\b", problem):
            return b
    return ""


def auto_build(payload: dict[str, Any]) -> bool:
    """Build right after the script. Off only for a script-only test run
    (VIDEO_AUTO_BUILD=0 or payload build=false)."""
    import os

    flag = os.environ.get("VIDEO_AUTO_BUILD", "1").strip().lower()
    return flag not in {"0", "false", "no", ""} and payload.get("build", True) is not False


async def _start_build(job: VideoJob, deps: Any) -> str:
    from hq import engine
    from hq.video import BUILD_STAGE

    return await engine.dispatch(
        agent="tutor", title=f"Video build: {job.title or job.id}", source="agent",
        brief="A narrated video of a finished lesson (hq.video).",
        parent_task_id=deps.task_id,
        payload={"stage": BUILD_STAGE, "video_id": job.id, "scale": 1},
        dedup_key=f"video:{job.id}:{BUILD_STAGE}:{deps.task_id}")


async def run(task: dict[str, Any], deps: Any) -> tuple[str, str]:
    """The script stage for one task. Returns (outcome, report)."""
    payload = dict(task.get("payload") or {})
    mode = str(payload.get("mode") or "course")
    lesson_md = str(payload.get("lesson_md") or "")
    video_id = str(payload.get("video_id") or video_id_for(lesson_md))
    job = load_job(video_id) or VideoJob(id=video_id, mode=cast(Any, mode), lesson_md=lesson_md)
    job.state, job.script_task_id = "writing", str(task.get("id") or "")
    await _job_step(job.model_dump())
    await _reset_step(video_id)
    with llm.call_context(run_id=deps.run_id, task_id=deps.task_id, agent="tutor"):
        m = await _gather_step(payload)
        job.course, job.phase_slugs = m["course"], [m["slug"]] if m["slug"] else []
        w = ScriptWriter(job, m)
        w.plan = await w.write_plan()
        job.title, job.mismatches = w.plan.title, w.plan.mismatches
        await _save_step(video_id, "plan.json", w.plan.model_dump())
        await w.write_all()
        await w.review_whole()
        editor = await w.edit()
        facts = await w.check_facts()
        await w.review_whole()
        await _save_step(video_id, "narration.json", w.narration())
        # The reviews are saved before the scenes, so a scene failure keeps them.
        remaining = checks.narration_problems(w.beats, mode=mode,
                                              n_concepts=len(w.plan.concepts))
        job.review = {"editor": editor, "facts": facts, "remaining": remaining,
                      "minutes": round(checks.minutes(w.beats), 1),
                      "think_questions": [ln.text for b in w.beats.values() for ln in b
                                          if ln.key == "q1"]}
        job.report = w.report
        await _save_step(video_id, "review.json", job.review)
        await _job_step(job.model_dump())
        spec = await w.write_scenes()
    job.report = w.report
    job.state = "script_ready"
    await _save_step(video_id, "review.json", job.review)
    wrong = [f for f in facts if f["verdict"] in ("contradicted", "unsupported")]
    weakest = min((float(sc["answers_question"]) for sc in editor.get("scores", [])), default=5.0)
    # No approval step: a script that passed its checks and both reviews goes
    # straight on to the voice and the render. One that still states a wrong
    # fact, or still fails a code check, stops here with its reasons, because
    # the alternative is a video that says the wrong thing aloud.
    blocked = [f"{f['beat']}.{f['key']} {f['verdict']}: {f.get('correction') or ''}"
               for f in wrong] + list(remaining)
    if weakest < 3:
        blocked.append(f"the teaching editor scored a beat {weakest:.0f} of 5 on answering"
                       " the video's question")
    if blocked:
        job.state = "failed"
    elif auto_build(payload):
        job.state = "approved"
        await _job_step(job.model_dump())
        await _start_build(job, deps)
    lines = [
        f"**Video script: {w.plan.title}**",
        (f"Video `{video_id}`, about {job.review['minutes']} minutes,"
         f" {len(w.plan.concepts)} concepts, {len(spec['beats'])} beats."),
        "",
        f"Fact check: {len(facts)} lines checked, {len(wrong)} still flagged.",
        f"Code checks still open: {len(remaining)}.",
        ("Every check and review passed, so the voice and the render started."
         if job.state == "approved" else
         "Stopped before the voice and the render, because of:" if blocked else
         "Script only (build not requested)."),
        *[f"- {b}" for b in blocked[:12]],
    ]
    if job.mismatches:
        lines += ["", "Lesson mismatches found:", *[f"- {x}" for x in job.mismatches]]
    if w.report:
        lines += ["", "Notes:", *[f"- {x}" for x in w.report]]
    await _job_step(job.model_dump())
    return ("failed" if job.state == "failed" else "done"), "\n".join(lines)
