"""A part knows where it sits in its series (2026-10-14).

Each part is its own ten-minute video: it picks up the question the last
part ended on, answers its own, and hands over to the next part, so he wants
to watch it. The last part ends the series with the one thing to try.
"""

from __future__ import annotations

import json

from hq import engine
from hq.video import BUILD_STAGE, SCRIPT_STAGE, SERIES_STAGE, script
from hq.video.models import PartPlan, PlannedConcept, SeriesPlan, VideoPlan
from hq.video.series import part_id

SERIES = SeriesPlan(title="Why a busy job read as idle", running_case="your job", parts=[
    PartPlan(title="Busy and idle at once", question="Why did it look idle?",
             concepts=["Why is waiting invisible to CPU?"], answer="Waiting burns no CPU.",
             leads_to="How much capacity is left?"),
    PartPlan(title="The real ceiling", question="How much can it do?",
             concepts=["What is the true rate?"], answer="Throughput over busy."),
])

PLAN = VideoPlan(
    title="The real ceiling", question="How much can it do?", running_case="your job",
    cold_open=["200 records a second"], payoff="1,000", try_this="Log busy milliseconds.",
    concepts=[PlannedConcept(
        id="c1", heading="What is the true rate?", situation="s", question="q?",
        first_thought="f", why_reasonable="w", what_it_misses="m", steps=["a", "b"],
        number="n", evidence_quote="e", takeaway="k")])


def _material(part: int) -> dict:
    return {"series": SERIES.model_dump(), "part": part}


def test_a_later_part_picks_up_where_the_last_one_ended() -> None:
    row = json.loads(script._beat_row(PLAN, "cold", _material(2)))
    assert row["the_last_part_ended_on"] == "How much capacity is left?"
    assert "the_last_part_ended_on" not in json.loads(script._beat_row(PLAN, "cold", _material(1)))


def test_a_part_hands_over_and_the_last_part_ends_the_series() -> None:
    first = json.loads(script._beat_row(PLAN, "end", _material(1)))
    assert first["hand_over"] == "How much capacity is left?"
    assert first["next_part"]["title"] == "The real ceiling"
    last = json.loads(script._beat_row(PLAN, "end", _material(2)))
    assert last["try_this"] == "Log busy milliseconds." and "next_part" not in last


def test_the_plan_prompt_names_the_part_and_its_concepts() -> None:
    m = {**_material(2), "lesson_md": "learning/lessons/x.md", "lesson": "text"}
    prompt = script._plan_prompt("course", m, [], None)
    assert "part 2 of 2" in prompt and "What is the true rate?" in prompt
    assert "The last part ended on this question: How much capacity is left?" in prompt


def test_part_ids_stay_valid_for_a_long_lesson() -> None:
    from hq.video import paths

    assert part_id("some-lesson", 2) == "some-lesson-p2"
    assert paths.valid_id(part_id("x" * 80, 5))


def test_writing_never_waits_behind_a_render() -> None:
    # The phase-05a script waited seven hours behind a render on 2026-10-11.
    assert engine.lane_for({"stage": SERIES_STAGE}) == "video_scripts"
    assert engine.lane_for({"stage": SCRIPT_STAGE}) == "video_scripts"
    assert engine.lane_for({"stage": BUILD_STAGE}) == "videos"


def test_what_the_last_editor_round_finds_is_rewritten_not_only_noted(monkeypatch) -> None:
    # A part went through with a merged figure and a contradiction that the
    # editor found in its last round and only noted (2026-10-15).
    import asyncio

    from hq.video.models import Line, VideoJob

    finding = {"beat": "c1", "criterion": "numbers", "quote": "q", "problem": "two values",
               "instruction": "keep one"}
    score = {"beat": "c1", "answers_question": 5, "connected": 5, "thinks_aloud": 5,
             "defined": 5, "spoken": 5, "numbers": 5, "stakes": 5}
    rewrites: list[str] = []

    async def editor(prompt: str) -> dict:
        return {"scores": [score], "findings": [finding], "whole_video": []}

    async def write_beat(self, beat: str, problems=()) -> list:
        rewrites.append(beat)
        return self.beats[beat]

    async def save(*_a: object) -> None:
        return None

    monkeypatch.setattr(script, "_editor_step", editor)
    monkeypatch.setattr(script.ScriptWriter, "write_beat", write_beat)
    monkeypatch.setattr(script, "_save_step", save)
    w = script.ScriptWriter(VideoJob(id="x-p1", mode="course", lesson_md="l.md"), {})
    w.plan = PLAN
    w.beats = {"c1": [Line(key="k0", text="A line.")]}
    asyncio.run(w.edit())
    assert rewrites == ["c1"] * (script.REVIEW_ROUNDS + 1)


def test_a_long_title_becomes_a_chapter_the_spec_accepts() -> None:
    title = "Your service froze for 3 s, but the load test printed p99 50 ms"
    assert len(title) > 60
    chapter = script._chapter(title)
    assert len(chapter) <= 60
    assert title.startswith(chapter)
    assert script._chapter("Short title") == "Short title"


def test_the_whole_review_cuts_a_long_script_and_checks_the_last_rewrite(monkeypatch) -> None:
    """2026-10-17: a 14.6-minute script was only noted, never cut, and the
    rewrite of a long concept was never checked again before the stop."""
    import asyncio
    import math
    import re
    from types import SimpleNamespace

    from hq.video import checks
    from hq.video.models import Line, VideoJob

    def words(n: int) -> list:
        return [Line(key=f"m{i}", text=" ".join(["word"] * 9) + " end.") for i in range(n // 10)]

    calls: list[str] = []

    async def write_beat(self, beat: str, problems=()) -> list:
        calls.append(beat)
        asked = [int(m.group(1)) for p in problems if (m := re.search(r"Cut about (\d+)", p))]
        if not asked:
            return self.beats[beat]
        # The first rewrite of a beat cuts only half of what it was asked.
        cut = asked[0] if calls.count(beat) > 1 else asked[0] // 2
        return self.beats[beat][: len(self.beats[beat]) - math.ceil(cut / 10)]

    monkeypatch.setattr(script.ScriptWriter, "write_beat", write_beat)
    w = script.ScriptWriter(VideoJob(id="x-p1", mode="course", lesson_md="l.md"), {})
    w.plan = SimpleNamespace(concepts=[1, 2, 3])
    w.beats = {"cold": words(100), "c1": words(900), "c2": words(800), "c3": words(400)}
    rewritten = asyncio.run(w.review_whole())
    assert checks.minutes(w.beats) <= checks.MINUTES["course"][1]
    assert "c1" in rewritten and calls.count("c1") >= 2
    assert not any("narration runs" in n for n in w.report)
