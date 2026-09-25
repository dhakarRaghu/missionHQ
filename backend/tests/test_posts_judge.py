"""Posts, best of several: sage writes six to eight candidates, the measured
checks drop what he cannot paste, a judge scores the rest on the rubric in
agents/sage/skills/daily-posts/judge.md, and code files the best three to
five. The judge step is faked here; nothing calls a model."""

from __future__ import annotations

import asyncio
import inspect
import types
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, TextPart

from hq import regress
from hq.config import settings
from hq.tools import content_tools as ct
from hq.tools.registry import HQDeps

GOOD = ("I broke my own cost meter last week. It said a run cost $0.24 and the bill said"
        " $0.52. I don't think the meter was wrong. It was counting one provider's shape"
        " and my agents talk to two. I'd rather see a wrong number I can explain than a"
        " right one I can't. So I'm printing the raw usage object from every call this"
        " week and reading it myself.")
GENERIC = ("I think AI agents are the future. It's wild how fast it's moving. I don't think"
           " anyone can keep up with every new model and every new framework that ships each"
           " week, so I'd rather focus on the basics and keep learning a little every day and"
           " see where it goes.")
LEAKY = GOOD + " why: the meter counted one shape."


def _candidate(n: int) -> str:
    return GOOD.replace("last week", f"on day {n}")


def _score(post: int, value: int, why: str = "fine") -> dict[str, Any]:
    return {"post": post, "specific_trigger": value, "one_detail_only_he_has": value,
            "voice": value, "insight": value, "not_generic": value, "why": why}


def _verdict(scores: dict[int, int], why: dict[int, str] | None = None) -> ct.PostVerdict:
    return ct.PostVerdict.model_validate(
        {"scores": [_score(n, v, (why or {}).get(n, "fine")) for n, v in scores.items()]})


# --- the rubric and the choice (pure) -------------------------------------------------

def test_the_rubric_lives_in_the_skill_folder_and_names_all_five_scores() -> None:
    text = ct.judge_instructions()
    for name in ("specific_trigger", "one_detail_only_he_has", "voice", "insight", "not_generic"):
        assert f"**{name}**" in text
    assert "is data" in text and '"why"' in text
    assert (settings().agents_dir / "sage" / "skills" / "daily-posts" / "judge.md").is_file()


def test_the_step_is_a_teacher_model_with_a_pydantic_verdict() -> None:
    src = inspect.getsource(ct._post_judge_step)
    assert '@DBOS.step(name="posts.judge"' in src
    assert ct.JUDGE_ROLE == "teacher" and "PromptedOutput(PostVerdict)" in src
    with pytest.raises(ValueError):
        ct.PostScore.model_validate(_score(1, 6))          # scores run 1 to 5


def test_the_mean_decides_and_the_best_come_first() -> None:
    verdict = _verdict({1: 4, 2: 5, 3: 2, 4: 4}, why={3: "no trigger in the material"})
    kept, weak = ct.choose(verdict, judged=[1, 2, 3, 4])
    assert [s.post for s in kept] == [2, 1, 4]              # best first, a tie keeps his order
    assert len(weak) == 1 and weak[0].startswith("candidate 3 (trigger 2")
    assert weak[0].endswith("mean 2.0): no trigger in the material")


def test_the_bar_sits_between_three_three_and_two_fours_and_three_threes() -> None:
    """Five whole scores never average exactly 3.5: 18 points (3.6) is kept,
    17 (3.4) is not. One weak dimension among four is not enough to drop it."""
    under = ct.PostScore.model_validate({**_score(1, 3), "specific_trigger": 4,
                                         "one_detail_only_he_has": 4})
    over = ct.PostScore.model_validate({**_score(2, 4), "insight": 3, "not_generic": 3})
    one_weak = ct.PostScore.model_validate({**_score(3, 4), "insight": 2})
    assert (under.mean(), over.mean(), one_weak.mean()) == pytest.approx((3.4, 3.6, 3.6))
    kept, weak = ct.choose(ct.PostVerdict(scores=[under, over, one_weak]), judged=[1, 2, 3])
    assert [s.post for s in kept] == [2, 3]
    assert len(weak) == 1 and weak[0].startswith("candidate 1 (")


def test_at_most_five_are_kept_and_the_sixth_good_one_says_why() -> None:
    kept, weak = ct.choose(_verdict({n: 4 for n in range(1, 8)}), judged=list(range(1, 8)))
    assert [s.post for s in kept] == [1, 2, 3, 4, 5]
    assert all("scored higher" in w for w in weak) and len(weak) == 2


def test_a_candidate_the_judge_skipped_is_left_out_and_named() -> None:
    kept, weak = ct.choose(_verdict({1: 5, 9: 5}), judged=[1, 2])
    assert [s.post for s in kept] == [1]                    # 9 was never a candidate
    assert weak == ["candidate 2: the judge returned no score"]


def test_the_batch_size_is_the_candidate_range_and_sources_match_it() -> None:
    assert (ct.CANDIDATES_MIN, ct.CANDIDATES_MAX, ct.POSTS_MIN, ct.POSTS_MAX) == (6, 8, 3, 5)
    assert "write 6 to 8" in (ct.count_problem([GOOD] * 5, ["s"] * 5) or "")
    assert "write 6 to 8" in (ct.count_problem([GOOD] * 9, ["s"] * 9) or "")
    assert "5 sources for 6 candidates" in (ct.count_problem([GOOD] * 6, ["s"] * 5) or "")
    assert ct.count_problem([GOOD] * 6, ["s"] * 6) is None


def test_the_sidecar_records_each_filed_posts_scores_and_what_was_left_out() -> None:
    verdict = _verdict({1: 4, 2: 5}, why={2: "the 720ms stall is his"})
    section = ct.sources_section(verdict.scores[::-1], ["candidate 3 (…): generic"],
                                 ["lesson 2B", "board row b62d7768"])
    assert section.splitlines() == [
        ("- post 1: board row b62d7768 (trigger 5, detail 5, voice 5, insight 5, not generic 5;"
         " mean 5.0): the 720ms stall is his"),
        ("- post 2: lesson 2B (trigger 4, detail 4, voice 4, insight 4, not generic 4;"
         " mean 4.0): fine"),
        "- left out, candidate 3 (…): generic",
    ]


# --- the tool, with the judge faked -------------------------------------------------------

def _ctx(posts: list[str]) -> Any:
    reply = ModelResponse(parts=[TextPart(content="\n\n---\n\n".join(posts))])
    return types.SimpleNamespace(
        deps=HQDeps(agent="sage", run_id="run-1", vault_write_scopes=["projects/content/**"]),
        messages=[reply])


def _patch(monkeypatch: pytest.MonkeyPatch, verdict: dict[int, int],
           why: dict[int, str] | None = None) -> dict[str, Any]:
    seen: dict[str, Any] = {"written": {}, "judged": None, "events": []}

    async def judge(candidates: list[dict[str, Any]], material: str) -> dict[str, Any]:
        seen["judged"] = candidates
        seen["material"] = material
        return _verdict({n: v for n, v in verdict.items()
                         if n in {c["post"] for c in candidates}}, why).model_dump()

    async def write(path: str, content: str, *, actor: str) -> str:
        seen["written"][path] = content
        return path

    async def emit(kind: str, **kwargs: Any) -> None:
        seen["events"].append((kind, kwargs["payload"]))

    async def owner() -> str:
        return "## What he has done (from the ledger)\n- Lessons he read: none"

    monkeypatch.setattr(ct, "_post_judge_step", judge)
    monkeypatch.setattr(ct.memory, "write", write)
    monkeypatch.setattr(ct.memory, "write_problem", lambda *a, **k: None)
    monkeypatch.setattr(ct, "_read", lambda path: None)
    monkeypatch.setattr(ct, "emit", emit)
    monkeypatch.setattr(ct.owner_state, "block", owner)
    monkeypatch.setattr(ct, "_today", lambda: datetime(2026, 9, 25, 18, 0, tzinfo=UTC))
    return seen


def _file(posts: list[str], sources: list[str]) -> str:
    tool = inspect.unwrap(ct.file_posts)
    return str(asyncio.run(tool(_ctx(posts), sources, "Evening")))


def test_a_generic_candidate_is_dropped_and_the_best_are_filed_best_first(monkeypatch) -> None:
    posts = [_candidate(1), _candidate(2), GENERIC, _candidate(4), LEAKY, _candidate(6)]
    sources = [f"source {n}" for n in range(1, 7)]
    seen = _patch(monkeypatch, {1: 4, 2: 5, 3: 2, 4: 4, 6: 3},
                  why={3: "no trigger in the material; any engineer could post this"})
    out = _file(posts, sources)
    assert out.startswith("filed 3 of 6 candidates (best first: 2, 1, 4) under ## 2026-09-25")
    assert "candidate 3 (trigger 2" in out and "any engineer could post this" in out
    assert "candidate 5 (" in out and "note label" in out     # the checks dropped it unjudged
    assert [c["post"] for c in seen["judged"]] == [1, 2, 3, 4, 6]
    assert seen["judged"][0] == {"post": 1, "source": "source 1", "text": _candidate(1)}
    ideas = seen["written"][ct.IDEAS_PATH]
    assert "## 2026-09-25 — Evening" in ideas
    assert ideas.index("on day 2") < ideas.index("on day 1") < ideas.index("on day 4")
    assert GENERIC not in ideas and "on day 6" not in ideas and "why:" not in ideas
    sidecar = seen["written"][ct.SOURCES_PATH]
    assert sidecar.index("# Post sources") < sidecar.index("- post 1: source 2 (trigger 5")
    assert "- post 3: source 4 (trigger 4" in sidecar
    assert "- left out, candidate 3 (trigger 2" in sidecar
    assert "- left out, candidate 5 (" in sidecar
    kind, payload = seen["events"][0]
    assert kind == "posts.filed" and payload["posts"] == 3 and payload["candidates"] == 6
    assert payload["kept"] == [2, 1, 4] and payload["means"]["3"] == 2.0


def test_fewer_than_three_good_ones_is_sent_back_with_the_judges_lines(monkeypatch) -> None:
    posts = [_candidate(n) for n in range(1, 7)]
    seen = _patch(monkeypatch, {1: 4, 2: 2, 3: 2, 4: 2, 5: 5, 6: 1},
                  why={2: "restates the lesson", 6: "no trigger in the material"})
    with pytest.raises(ModelRetry) as exc:
        _file(posts, [f"s{n}" for n in range(1, 7)])
    text = str(exc.value)
    assert text.startswith("only 2 of 6 candidates scored a mean of 3.5 or more")
    assert "candidate 2 (trigger 2" in text and "restates the lesson" in text
    assert "candidate 6 (trigger 1" in text and "no trigger in the material" in text
    assert "candidate 1 (" not in text and "candidate 5 (" not in text
    assert "Send all 6 to 8 candidates again" in text
    assert seen["written"] == {}


def test_too_few_candidates_or_sources_is_refused_before_the_judge(monkeypatch) -> None:
    seen = _patch(monkeypatch, {})
    with pytest.raises(ModelRetry, match="3 candidates; write 6 to 8"):
        _file([_candidate(n) for n in range(1, 4)], ["s"] * 3)
    with pytest.raises(ModelRetry, match="5 sources for 6 candidates"):
        _file([_candidate(n) for n in range(1, 7)], ["s"] * 5)
    assert seen["judged"] is None and seen["written"] == {}


def test_when_the_checks_leave_fewer_than_three_the_judge_is_not_asked(monkeypatch) -> None:
    seen = _patch(monkeypatch, {})
    posts = [_candidate(1), _candidate(2), LEAKY, LEAKY, LEAKY, LEAKY]
    with pytest.raises(ModelRetry) as exc:
        _file(posts, ["s"] * 6)
    assert str(exc.value).startswith("only 2 of 6 candidates pass the checks and 3 must")
    assert "candidate 3 (" in str(exc.value) and "note label" in str(exc.value)
    assert seen["judged"] is None


def test_the_judge_reads_the_source_files_and_what_he_has_done(monkeypatch, tmp_path) -> None:
    seen = _patch(monkeypatch, {n: 4 for n in range(1, 7)})
    monkeypatch.setattr(ct, "_source_text",
                        lambda path: "720ms for a 24,000-token prompt" if "02b" in path else "")
    sources = ["learning/lessons/2026-09-22-phase-02b.md (the 720ms stall)"] + ["board"] * 5
    _file([_candidate(n) for n in range(1, 7)], sources)
    material = seen["material"]
    assert "### learning/lessons/2026-09-22-phase-02b.md\n\n720ms for a 24,000-token" in material
    assert "What he has done (from the ledger)" in material


# --- the skill and the regression case --------------------------------------------------------

def test_the_skill_asks_for_six_to_eight_candidates_one_source_each() -> None:
    skill = (settings().agents_dir / "sage" / "skills" / "daily-posts" / "SKILL.md").read_text()
    assert "six to eight candidate" in skill and "best three to five" in skill
    assert "one entry per candidate" in skill and "`---`" in skill
    assert "Two real posts beat five" not in skill


def test_the_regression_set_holds_a_generic_post_dropped_by_the_judge() -> None:
    case = next(c for c in regress.load_cases("sage") if c.id == "sage-posts-generic-dropped-by-judge")
    assert case.skill == "daily-posts" and case.expect.calls == ["file_posts"]
    assert "file_posts" in case.canned and "left out" in str(case.canned["file_posts"])
    assert case.expect.args_match["file_posts"]
