"""The rules code checks in a video's plan, series and narration (2026-10-14).

The first form was correct line by line and still lost the viewer: each
concept gave its answer before its question, the same fixed phrases opened
every concept, and one video ran 20 to 49 minutes. The story order, the ban
on fixed phrases and the parts of about ten minutes are checked here.
"""

from __future__ import annotations

from hq.video import checks
from hq.video.models import Line, PartPlan, SeriesPlan

LONG = " ".join(["word"] * 30) + "."


def _concept(**swap: str) -> list[Line]:
    """A concept beat in the story order, with lines replaced by key."""
    text = {
        "s0": "Your job's output buffer filled while the sink slowed to a crawl.",
        "q0": "Why did a job that could not take one more record look idle?",
        "t0": "Low CPU looks like spare capacity, because in your Go services it usually is.",
        "t1": "But a stage waiting on a full buffer has no capacity and runs no code.",
        "m0": "The worker blocks on the full buffer, so it stops pulling new input.",
        "m1": "Blocking runs no code, so CPU stays near fifteen percent while lag grows.",
        "n0": "In the same second CPU reads fifteen percent and busy time reads all of it.",
        "k0": "Waiting is load, and only a signal measured inside the stage can see it.",
        "h0": "Knowing the stage is full still does not say how much capacity it has.",
    }
    text.update(swap)
    return [Line(key=k, text=v) for k, v in text.items() if v]


def test_a_concept_in_the_story_order_passes() -> None:
    assert checks.concept_problems("c1", _concept()) == []


def test_the_claim_before_the_question_is_refused() -> None:
    lines = _concept()
    claim_first = [lines[-2], *lines[:-2], lines[-1]]
    found = checks.concept_problems("c1", claim_first)
    assert any("out of order" in p for p in found)


def test_a_fixed_phrase_is_refused_in_a_concept() -> None:
    found = checks.line_problems("c1", Line(key="q0", text="Here is the question. Why is it idle?"))
    assert any("fixed phrase" in p for p in found)
    found = checks.line_problems("c1", Line(key="m0", text="Step 1. The worker blocks."))
    assert any("fixed phrase" in p for p in found)
    # Outside a concept the words are not a template.
    assert not any("fixed phrase" in p for p in checks.line_problems(
        "end", Line(key="x0", text="Try this: log the blocked milliseconds once a second.")))


def test_the_question_ends_the_q_lines_and_appears_nowhere_else() -> None:
    found = checks.concept_problems("c1", _concept(q0="Why did the job look idle."))
    assert any("ends with ?" in p for p in found)
    found = checks.line_problems("c1", Line(key="m0", text="Does the worker block?"))
    assert any("a question outside" in p for p in found)
    assert not checks.line_problems("end", Line(key="x0", text="So how much capacity is left?"))


def test_the_thinking_says_what_the_first_answer_misses() -> None:
    found = checks.concept_problems("c1", _concept(t1="A stage waiting on a full buffer runs no code."))
    assert any("'but'" in p for p in found)


def test_the_takeaway_is_said_once() -> None:
    lines = [*_concept()[:-1], Line(key="k1", text="Again."), Line(key="k2", text="Again."),
             _concept()[-1]]
    assert any("said once" in p for p in checks.concept_problems("c1", lines))


def test_the_last_concept_needs_no_bridge() -> None:
    assert checks.concept_problems("c3", _concept(h0=""), last=True) == []
    assert any("'h' is missing" in p for p in checks.concept_problems("c3", _concept(h0="")))


def test_a_long_line_is_split() -> None:
    found = checks.line_problems("c1", Line(key="s0", text=LONG))
    assert any("split it" in p for p in found)


def _series(*sizes: int, leads: list[str] | None = None) -> SeriesPlan:
    n = 0
    parts = []
    for i, size in enumerate(sizes):
        heads = [f"Concept question number {n + j + 1}?" for j in range(size)]
        n += size
        last = i == len(sizes) - 1
        parts.append(PartPlan(title=f"Part title {i + 1}", question="Why is it idle?",
                              concepts=heads, answer="Because waiting burns no CPU.",
                              leads_to="" if last else "How much capacity is left?"))
    if leads is not None:
        for part, lead in zip(parts, leads):
            part.leads_to = lead
    return SeriesPlan(title="Why a busy job read as idle", running_case="your job", parts=parts)


def test_a_lesson_is_told_in_parts_of_two_to_four_concepts() -> None:
    assert checks.series_problems(_series(3, 2), "course") == []
    assert checks.series_problems(_series(4), "course") == []
    # Eight concepts in one video is the forty-minute video again.
    assert any("parts" in p for p in checks.series_problems(_series(8), "course"))
    # And five one-concept parts are not ten-minute videos either.
    assert any("parts" in p for p in checks.series_problems(_series(1, 1, 1, 1, 1), "course"))


def test_each_part_hands_over_to_the_next_and_the_last_ends() -> None:
    found = checks.series_problems(_series(2, 2, leads=["", ""]), "course")
    assert any("part 1: `leads_to`" in p for p in found)
    found = checks.series_problems(_series(2, 2, leads=["Next?", "And then?"]), "course")
    assert any("part 2: the last part" in p for p in found)


def test_a_concept_is_taught_in_one_part_only() -> None:
    series = _series(2, 2)
    series.parts[1].concepts[0] = series.parts[0].concepts[0]
    assert any("earlier part" in p for p in checks.series_problems(series, "course"))


def test_a_mechanism_has_at_least_two_lines() -> None:
    # The scene needs 2 to 6 items, each on its own m line, so one m line
    # passed every narration check and then failed every scene round.
    found = checks.concept_problems("c1", _concept(m1=""))
    assert any("at least 2 m lines" in p for p in found)
