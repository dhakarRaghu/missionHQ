"""Stage 2: from a checked script to a checked video on the Courses page.

A script that passed every check starts this stage (`script.py`). The long
steps (the voice, the stills, the render) run as detached processes, the
way the twelve episodes were built: a process the backend starts and then
polls, writing a log and a done marker in the job folder. Each poll is a
durable step and records a progress event, so the hang watchdog sees a
render as alive, and a backend restart resumes polling instead of starting
the render again.

Before the render, the teacher model reviews a still of every scene step
against what the voice says during it, and failing beats are redrawn. After
the render, the checks are code (`video/scripts/verify.mjs`): audio sync per
spoken line, frame count against the timing file, near-empty or repeated
scene frames, keyframes, loudness, black frames and stream format.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, BinaryContent, PromptedOutput
from pydantic_ai.usage import UsageLimits

from hq import llm
from hq.dbos_app import DBOS
from hq.video import paths, register
from hq.video.models import FrameVerdict
from hq.video.script import (
    _STEP,
    REVIEW_MODEL,
    _check_spec_step,
    _job_step,
    _json_object,
    _scenes_step,
    _settings,
    instructions,
    load_job,
)

FRAME_ROUNDS = 2        # a beat whose frames fail is redrawn at most twice

POLL_S = 30.0
LIMITS_S = {"narrate": 3 * 3600, "stills": 3600, "render": 6 * 3600, "verify": 1800,
            "meta": 900}
# Mission HQ plays videos in the browser, so 1080p is the default; 4K
# (scale 2) is for a video that will also be uploaded.
DEFAULT_SCALE = 1


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{paths.node_bin()}:{env.get('PATH', '')}"
    return env


def _spawn(video_id: str, phase: str, command: str) -> int:
    folder = paths.work_dir(video_id)
    folder.mkdir(parents=True, exist_ok=True)
    done = folder / f"{phase}.done"
    done.unlink(missing_ok=True)
    wrapped = f"{command}; echo $? > {shlex.quote(str(done))}"
    with open(folder / f"{phase}.log", "w") as log:
        proc = subprocess.Popen(["bash", "-c", wrapped], cwd=str(paths.project_dir()),
                                stdout=log, stderr=subprocess.STDOUT, env=_env(),
                                start_new_session=True)
    return proc.pid


@DBOS.step(name="video.start_process")
async def _start_step(video_id: str, phase: str, command: str) -> int:
    """Start one long step detached; it writes <phase>.log and <phase>.done."""
    return await asyncio.to_thread(_spawn, video_id, phase, command)


@DBOS.step(name="video.poll_process")
async def _poll_step(video_id: str, phase: str) -> int | None:
    done = paths.work_dir(video_id) / f"{phase}.done"
    if not done.is_file():
        return None
    text = done.read_text().strip()
    return int(text) if text.lstrip("-").isdigit() else 1


def _log_tail(video_id: str, phase: str, lines: int = 12) -> str:
    path = paths.work_dir(video_id) / f"{phase}.log"
    if not path.is_file():
        return ""
    return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])


async def _run_long(video_id: str, phase: str, command: str, deps: Any) -> None:
    from hq.runner import emit_step

    await _start_step(video_id, phase, command)
    waited = 0.0
    while True:
        code = await _poll_step(video_id, phase)
        if code is not None:
            if code != 0:
                raise RuntimeError(f"{phase} failed (exit {code}):\n{_log_tail(video_id, phase)}")
            return
        if waited > LIMITS_S[phase]:
            raise RuntimeError(f"{phase} ran past {LIMITS_S[phase] // 60} minutes")
        await emit_step("video.progress", run_id=deps.run_id, task_id=deps.task_id,
                        agent="tutor", payload={"video": video_id, "phase": phase,
                                                "waited_s": int(waited)})
        await DBOS.sleep_async(POLL_S)
        waited += POLL_S


# narrate.mjs's timing format. Below 2, line starts were summed from per-line
# MP3s and ran up to a second ahead of the voice; such a voice is made again.
TIMING_VERSION = 2


def _voice_is_current(video_id: str) -> bool:
    """The voice finished, and the narration has not changed since: a second
    build after a failed frame review or render does not voice it again."""
    w = paths.work_dir(video_id)
    done, timing, nar = w / "narrate.done", w / f"{video_id}.timing.json", w / "narration.json"
    if not (done.is_file() and done.read_text().strip() == "0" and timing.is_file()
            and timing.stat().st_mtime >= nar.stat().st_mtime):
        return False
    try:
        version = int(json.loads(timing.read_text()).get("version") or 0)
    except (ValueError, TypeError):
        return False
    return version >= TIMING_VERSION


def commands(video_id: str, scale: int) -> dict[str, str]:
    """The shell commands of each long step, run in video/ (see video/README.md).

    The job folder keeps the pipeline's names (narration.json, spec.json);
    the timing file is written as <id>.timing.json, which render.mjs reads.
    """
    w = paths.work_dir(video_id)
    q = shlex.quote
    node = q(str(paths.node_bin() / "node"))
    spec, timing, audio = q(str(w / "spec.json")), q(str(w / f"{video_id}.timing.json")), q(
        str(w / "audio"))
    files = f"--spec={spec} --timing={timing} --audio={audio}"
    return {
        "narrate": f"{node} scripts/narrate.mjs {q(str(w / 'narration.json'))} {audio} {timing}",
        "stills": f"{node} scripts/render.mjs {q(str(w))} {q(video_id)} --stills=auto {files}",
        "stills_beat": f"{node} scripts/render.mjs {q(str(w))} {q(video_id)} {files} --stills=",
        "render": f"{node} scripts/render.mjs {q(str(w))} {q(video_id)} --scale={scale} {files}",
        # verify.mjs exits 1 when a check fails; its JSON says which, so the
        # exit code is kept apart and the report decides.
        "verify": f"{node} scripts/verify.mjs {q(str(w / mp4_name(video_id, scale)))} {timing}"
                  f" --spec={spec} --out={q(str(w))} --audio={audio}"
                  f" > {q(str(w / 'verify.json'))}; true",
        "meta": f"{node} scripts/captions.mjs {timing} {spec} {q(str(w))}",
    }


def mp4_name(video_id: str, scale: int) -> str:
    return f"{video_id}.mp4" if scale == 1 else f"{video_id}-4K.mp4"


# --- the frame review -------------------------------------------------------------
# The templates draw every frame, and code limits every text field, but a
# label can still be the wrong label, a panel can show too little, and a
# number can disagree with the voice. Kimi reads stills correctly (tested
# 2026-10-06 on a thumbnail: every line and both colours read back, no
# invented overlaps), so the teacher model looks at every scene step next to
# what the voice says during it, before anything is rendered in full.

def _stills_index(video_id: str) -> list[dict[str, Any]]:
    path = paths.work_dir(video_id) / "stills" / "index.json"
    data = json.loads(path.read_text()) if path.is_file() else []
    return [dict(x) for x in data]


def _narration_lines(video_id: str) -> dict[str, dict[str, str]]:
    nar = json.loads((paths.work_dir(video_id) / "narration.json").read_text())
    return {b: {ln["key"]: ln["text"] for ln in v["lines"]} for b, v in nar["beats"].items()}


@DBOS.step(name="video.frames", **_STEP)
async def _frames_step(video_id: str, beat: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    w = paths.work_dir(video_id)
    spec = json.loads((w / "spec.json").read_text())
    spec_beat: dict[str, Any] = next((b for b in spec["beats"] if b.get("id") == beat), {})
    voice = _narration_lines(video_id).get(beat, {})
    content: list[Any] = [
        f"## Beat {beat}: its spec\n\n```json\n{json.dumps(spec_beat, ensure_ascii=False)}\n```"]
    for it in items:
        said = "\n".join(f"{k}: {voice.get(k, '')}" for k in it.get("keys") or [])
        content.append(f"## Still {it['file']} (step {it.get('step')})\nThe voice during it:\n{said}")
        content.append(BinaryContent(data=(w / "stills" / it["file"]).read_bytes(),
                                     media_type="image/jpeg"))
    reg = llm.registry()
    agent = Agent(reg.resolve(REVIEW_MODEL), output_type=PromptedOutput(FrameVerdict),
                  retries=3, instructions=instructions("frames"),
                  model_settings=_settings(REVIEW_MODEL))
    result = await agent.run(content, usage_limits=UsageLimits(request_limit=4))
    return result.output.model_dump()


async def _redraw_beat(video_id: str, beat: str, problems: list[str]) -> None:
    """Ask the writer for this beat's spec again, with what the reviewer saw."""
    w = paths.work_dir(video_id)
    spec = json.loads((w / "spec.json").read_text())
    current: dict[str, Any] = next((b for b in spec["beats"] if b.get("id") == beat), {})
    voice = _narration_lines(video_id).get(beat, {})
    ask = (f"## Return the spec beat for: {beat}\n\nIts narration:\n"
           + "\n".join(f"{k}: {t}" for k, t in voice.items())
           + "\n\n## The current spec of this beat\n\n```json\n"
           + json.dumps(current, ensure_ascii=False) + "\n```\n\n"
           "## What the frame reviewer saw in the rendered stills\n\n"
           + "\n".join(f"- {p}" for p in problems)
           + "\n\nFix exactly these, keep the rest, and return only the JSON object of"
             " this one beat.")
    for _ in range(3):
        obj = _json_object(await _scenes_step(ask))
        if not obj:
            continue
        trial = {**spec, "beats": [obj if b.get("id") == beat else b for b in spec["beats"]]}
        (w / "spec.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n")
        found = await _check_spec_step(str(w))
        if not found:
            return
        ask += "\n\n## check-spec refused your last answer\n\n" + "\n".join(
            f"- {p}" for p in found[:20])
    (w / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")


def _save_frames(video_id: str, round_no: int, failing: dict[str, list[str]],
                 notes: list[str]) -> None:
    """Every round's verdict, kept so a failure can be read in full."""
    path = paths.work_dir(video_id) / "frames.json"
    rounds = json.loads(path.read_text()) if path.is_file() and round_no else []
    rounds.append({"round": round_no, "failing": failing, "template_notes": notes})
    path.write_text(json.dumps(rounds, ensure_ascii=False, indent=2) + "\n")


TEMPLATE_BEATS = frozenset({"title", "recap", "end"})


async def review_frames(video_id: str, cmds: dict[str, str], deps: Any) -> list[str]:
    """Look at every scene step; redraw failing beats; return what still fails.

    Template-drawn beats (title, recap, end) are reviewed too, but only as
    notes in frames.json: their look is fixed code, not spec data.
    """
    failing: dict[str, list[str]] = {}
    notes: list[str] = []
    for round_no in range(FRAME_ROUNDS + 1):
        index = _stills_index(video_id)
        order = [str(it["beat"]) for it in index]
        beats = sorted(set(order), key=order.index)
        todo = beats if round_no == 0 else list(failing)
        failing = {}
        for beat in todo:
            items = [it for it in index if it["beat"] == beat]
            verdict = FrameVerdict.model_validate(await _frames_step(video_id, beat, items))
            bad = [i for i in verdict.items if not i.ok]
            if bad and beat in TEMPLATE_BEATS:
                # The template draws these from fixed fields; no redraw of the
                # spec can change them, so a finding is a note for the template.
                notes += [f"{beat} (template): {'; '.join(i.problems)}" for i in bad]
            elif bad:
                failing[beat] = [f"{i.file}: {'; '.join(i.problems)}. {i.instruction}"
                                 for i in bad]
        _save_frames(video_id, round_no, failing, notes)
        if not failing or round_no == FRAME_ROUNDS:
            break
        for beat, problems in failing.items():
            await _redraw_beat(video_id, beat, problems)
            await _run_long(video_id, "stills", cmds["stills_beat"] + beat, deps)
    return [p for items in failing.values() for p in items]


def verify_problems(report: dict[str, Any]) -> list[str]:
    """verify.mjs prints one JSON report; "ok" is the verdict, the parts say why."""
    if report.get("ok") is True:
        return []
    out: list[str] = []
    if report.get("sync_ok") is False:
        worst = "; ".join(f"{w.get('key')} {w.get('drift_ms')} ms"
                          for w in (report.get("sync_worst") or [])[:5])
        out.append(f"audio out of sync: max drift {report.get('sync_max_drift_ms')} ms ({worst})")
    if report.get("frames_ok") is False:
        fails = (report.get("frames") or {}).get("failing") or []
        out.append("frames: " + "; ".join(f"{f.get('beat')}/{f.get('step')} {f.get('reason')}"
                                          for f in fails[:8]))
    if report.get("frames_ok_count") is False:
        out.append("the frame count differs from the timing file")
    for part in ("keyframes", "loudness", "black"):
        val = report.get(part)
        if isinstance(val, dict) and val.get("ok") is False:
            out.append(f"{part}: {json.dumps(val)[:200]}")
    return out or [f"verify.mjs reported a failure: {json.dumps(report)[:300]}"]


@DBOS.step(name="video.publish")
async def _publish_step(video_id: str) -> dict[str, Any]:
    """Move the checked video into the media folder and register it."""
    job = load_job(video_id)
    assert job is not None
    w = paths.work_dir(video_id)
    timing = json.loads((w / f"{video_id}.timing.json").read_text())
    chapters_file = w / "chapters.json"
    chapters = json.loads(chapters_file.read_text()) if chapters_file.is_file() else []
    folder = job.course or "learn"
    dest = paths.media_root() / folder
    dest.mkdir(parents=True, exist_ok=True)
    files = {"file": f"{folder}/{video_id}.mp4"}
    mp4 = w / mp4_name(video_id, 1)
    if not mp4.is_file():
        mp4 = w / mp4_name(video_id, 2)
    shutil.copy2(mp4, paths.media_root() / files["file"])
    # No thumbnail: the owner is the only viewer, and the player shows the
    # first frame.
    for name, key in (("captions.srt", "captions"),):
        if (w / name).is_file():
            files[key] = f"{folder}/{video_id}{Path(name).suffix}"
            shutil.copy2(w / name, paths.media_root() / files[key])
    review = job.review or {}
    entry = {
        "id": video_id, "kind": job.mode, "course": job.course,
        "phase_slug": job.phase_slugs[0] if job.phase_slugs else None,
        "phase_slugs": job.phase_slugs, "number": None, "title": job.title,
        "duration_s": round(float(timing.get("totalFrames", 0)) / float(timing.get("fps") or 30), 1),
        "chapters": chapters, "youtube_id": None,
        "source_lesson": job.lesson_md, "think_questions": review.get("think_questions", []),
        **files,
    }
    register.upsert_video(entry)
    return entry


async def run(task: dict[str, Any], deps: Any) -> tuple[str, str]:
    payload = dict(task.get("payload") or {})
    video_id = str(payload.get("video_id") or "")
    job = load_job(video_id)
    if job is None or job.state not in ("approved", "building", "failed", "script_ready"):
        return "blocked", f"video {video_id!r} has no checked script to build"
    job.state, job.build_task_id = "building", str(task.get("id") or "")
    await _job_step(job.model_dump())
    cmds = commands(video_id, int(payload.get("scale") or DEFAULT_SCALE))
    try:
        if not _voice_is_current(video_id):
            await _run_long(video_id, "narrate", cmds["narrate"], deps)
        await _run_long(video_id, "stills", cmds["stills"], deps)
        frame_problems = await review_frames(video_id, cmds, deps)
        if frame_problems:
            raise RuntimeError("the frame review still fails after "
                               f"{FRAME_ROUNDS} redraws: " + " | ".join(frame_problems[:8]))
        for phase in ("render", "verify"):
            await _run_long(video_id, phase, cmds[phase], deps)
        text = (paths.work_dir(video_id) / "verify.json").read_text().strip()
        report = json.loads(text) if text.startswith("{") else {"ok": False, "raw": text[:300]}
        problems = verify_problems(report)
        if problems:
            raise RuntimeError("the render did not pass its checks: " + "; ".join(problems))
        await _run_long(video_id, "meta", cmds["meta"], deps)  # captions + chapters
        entry = await _publish_step(video_id)
    except RuntimeError as exc:
        job = load_job(video_id) or job
        job.state = "failed"
        job.report = [*job.report, str(exc)[:1500]]
        await _job_step(job.model_dump())
        return "failed", str(exc)[:1500]
    job = load_job(video_id) or job
    job.state, job.verify = "built", report
    job.duration_s = float(entry["duration_s"])
    await _job_step(job.model_dump())
    minutes = entry["duration_s"] / 60
    return "done", (f"**Video built: {job.title}** ({minutes:.1f} minutes). It is on the Courses"
                    f" page with {len(entry['chapters'])} chapters. Checks passed: audio sync"
                    f" (max drift {report.get('sync_max_drift_ms')} ms), frames, frame count,"
                    " keyframes, loudness, black frames.")
