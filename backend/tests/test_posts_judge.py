"""Posts, best of several: sage writes six to eight candidates, the measured
checks drop what he cannot paste, a judge scores the rest on the rubric in
agents/sage/skills/daily-posts/judge.md, and code files the best one or
two. The judge step is faked here; nothing calls a model."""

from __future__ import annotations

import asyncio
import inspect
import types
from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, TextPart

from hq import regress
from hq.config import settings
from hq.tools import content_tools as ct
from hq.tools.registry import HQDeps

GOOD = ("I was reading how vLLM handles a long prompt last week. It doesn't run the whole"
        " prompt in one step. It cuts it into chunks and mixes them with decode steps, so a"
        " short request doesn't wait behind a 24,000-token one. I think that's the part most"
        " people miss when they only watch average latency. I'd rather read the tail than"
        " the mean, because the tail is where the waiting shows.")
GENERIC = ("I think AI agents are the future. It's wild how fast it's moving. I don't think"
           " anyone can keep up with every new model and every new framework that ships each"
           " week, so I'd rather focus on the basics and keep learning a little every day and"
           " see where it goes.")
LEAKY = GOOD + " why: the meter counted one shape."


def _candidate(n: int) -> str:
    return GOOD.replace("last week", f"on day {n}")


def _score(post: int, value: int, why: str = "fine") -> dict[str, Any]:
    return {"post": post, "source": value, "teaches": value, "accurate": value,
            "voice": value, "insight": value, "clear": value, "share": value,
            "reply": value, "why": why}


def _verdict(scores: dict[int, int], why: dict[int, str] | None = None) -> ct.PostVerdict:
    return ct.PostVerdict.model_validate(
        {"scores": [_score(n, v, (why or {}).get(n, "fine")) for n, v in scores.items()]})


# --- the rubric and the choice (pure) -------------------------------------------------

def test_the_rubric_lives_in_the_skill_folder_and_names_all_eight_scores() -> None:
    text = ct.judge_instructions()
    for name in ("source", "teaches", "accurate", "voice", "insight", "clear", "share",
                 "reply", "repeats"):
        assert f"**{name}**" in text
    assert "<earlier>" in text
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
    assert [s.post for s in kept] == [2, 1]                 # best first, a tie keeps his order
    assert weak[0].startswith("candidate 3 (source 2")
    assert weak[0].endswith("mean 2.0): no trigger in the material")
    assert weak[1].startswith("candidate 4 (") and "2 scored higher" in weak[1]


def test_the_bar_sits_between_three_three_and_two_fours_and_three_threes() -> None:
    """Eight whole scores: 30 points (3.75) is kept, 26 (3.25) is not, and 28
    (3.5) sits on the bar. One weak dimension among eight is not enough to
    drop it."""
    under = ct.PostScore.model_validate({**_score(1, 3), "source": 4, "voice": 4})
    over = ct.PostScore.model_validate({**_score(2, 4), "insight": 3, "voice": 3})
    one_weak = ct.PostScore.model_validate({**_score(3, 4), "insight": 2})
    assert (under.mean(), over.mean(), one_weak.mean()) == pytest.approx((26 / 8, 30 / 8, 30 / 8))
    kept, weak = ct.choose(ct.PostVerdict(scores=[under, over, one_weak]), judged=[1, 2, 3])
    assert [s.post for s in kept] == [2, 3]
    assert len(weak) == 1 and weak[0].startswith("candidate 1 (")


def test_at_most_two_are_kept_and_the_third_good_one_says_why() -> None:
    kept, weak = ct.choose(_verdict({n: 4 for n in range(1, 8)}), judged=list(range(1, 8)))
    assert [s.post for s in kept] == [1, 2]
    assert all("scored higher" in w for w in weak) and len(weak) == 5


def test_a_candidate_the_judge_skipped_is_left_out_and_named() -> None:
    kept, weak = ct.choose(_verdict({1: 5, 9: 5}), judged=[1, 2])
    assert [s.post for s in kept] == [1]                    # 9 was never a candidate
    assert weak == ["candidate 2: the judge returned no score"]


def test_the_batch_size_is_the_candidate_range_and_sources_match_it() -> None:
    assert (ct.CANDIDATES_MIN, ct.CANDIDATES_MAX, ct.POSTS_MIN, ct.POSTS_MAX) == (6, 8, 1, 2)
    assert "write 6 to 8" in (ct.count_problem([GOOD] * 5, ["s"] * 5) or "")
    assert "write 6 to 8" in (ct.count_problem([GOOD] * 9, ["s"] * 9) or "")
    assert "5 sources for 6 candidates" in (ct.count_problem([GOOD] * 6, ["s"] * 5) or "")
    assert ct.count_problem([GOOD] * 6, ["s"] * 6) is None


def test_the_sidecar_records_each_filed_posts_scores_and_what_was_left_out() -> None:
    verdict = _verdict({1: 4, 2: 5}, why={2: "the 720ms stall is his"})
    section = ct.sources_section(verdict.scores[::-1], ["candidate 3 (…): generic"],
                                 ["lesson 2B", "board row b62d7768"])
    assert section.splitlines() == [
        ("- post 1: board row b62d7768 (source 5, teaches 5, accurate 5, voice 5, insight 5,"
         " clear 5, share 5, reply 5; mean 5.0): the 720ms stall is his"),
        ("- post 2: lesson 2B (source 4, teaches 4, accurate 4, voice 4, insight 4,"
         " clear 4, share 4, reply 4; mean 4.0): fine"),
        "- left out, candidate 3 (…): generic",
    ]


# --- the tool, with the judge faked -------------------------------------------------------

def _ctx(posts: list[str], retry: int = 1) -> Any:
    # retry 1: a later call, after the one round of repairs the checks ask for.
    reply = ModelResponse(parts=[TextPart(content="\n\n---\n\n".join(posts))])
    return types.SimpleNamespace(
        deps=HQDeps(agent="sage", run_id="run-1", vault_write_scopes=["projects/content/**"]),
        messages=[reply], retry=retry)


def _patch(monkeypatch: pytest.MonkeyPatch, verdict: dict[int, int],
           why: dict[int, str] | None = None, existing: str | None = None) -> dict[str, Any]:
    seen: dict[str, Any] = {"written": {}, "judged": None, "events": []}

    async def judge(candidates: list[dict[str, Any]], material: str,
                    earlier: list[dict[str, str]]) -> dict[str, Any]:
        seen["judged"] = candidates
        seen["material"] = material
        seen["earlier"] = earlier
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
    monkeypatch.setattr(ct, "_read", lambda path: existing)
    monkeypatch.setattr(ct, "emit", emit)
    monkeypatch.setattr(ct.owner_state, "block", owner)
    monkeypatch.setattr(ct, "_today", lambda: datetime(2026, 9, 25, 18, 0, tzinfo=UTC))
    return seen


def _file(posts: list[str], sources: list[str], retry: int = 1) -> str:
    tool = inspect.unwrap(ct.file_posts)
    return str(asyncio.run(tool(_ctx(posts, retry), sources, "Evening")))


def test_on_the_first_call_a_candidate_that_fails_a_check_comes_back_to_be_fixed(
        monkeypatch) -> None:
    seen = _patch(monkeypatch, {n: 4 for n in range(1, 7)})
    posts = [_candidate(1), _candidate(2), _candidate(3), _candidate(4), LEAKY, _candidate(6)]
    with pytest.raises(ModelRetry) as exc:
        _file(posts, [f"source {n}" for n in range(1, 7)], retry=0)
    assert str(exc.value).startswith("fix these candidates and keep every other")
    assert "candidate 5 (" in str(exc.value) and seen["judged"] is None


def test_at_most_one_kept_post_rests_on_his_lessons_and_a_reading_takes_the_place(
        monkeypatch) -> None:
    """The limit applies before the cut: the second slot goes to the best
    post from his reading, not to a second post from his course."""
    seen = _patch(monkeypatch, {1: 5, 2: 5, 3: 5, 4: 4, 5: 4, 6: 3})
    sources = [f"learning/lessons/2026-09-29-x{n}.md" for n in (1, 2, 3)] + [
        "quarantine/reading-a.md", "quarantine/reading-b.md", "project p"]
    out = _file([_candidate(n) for n in range(1, 7)], sources)
    assert out.startswith("filed 2 of 6 candidates (best first: 1, 4)")
    assert "candidate 2 (" in out and "beyond the 1 kept" in out
    assert "candidate 5 (" in out and "2 scored higher" in out
    ideas = seen["written"][ct.IDEAS_PATH]
    assert "on day 1" in ideas and "on day 4" in ideas and "on day 2" not in ideas


def test_a_generic_candidate_is_dropped_and_the_best_are_filed_best_first(monkeypatch) -> None:
    posts = [_candidate(1), _candidate(2), GENERIC, _candidate(4), LEAKY, _candidate(6)]
    sources = [f"source {n}" for n in range(1, 7)]
    seen = _patch(monkeypatch, {1: 4, 2: 5, 3: 2, 4: 4, 6: 3},
                  why={3: "no trigger in the material; any engineer could post this"})
    out = _file(posts, sources)
    assert out.startswith("filed 2 of 6 candidates (best first: 2, 1) under ## 2026-09-25")
    assert "candidate 3 (source 2" in out and "any engineer could post this" in out
    assert "candidate 5 (" in out and "note label" in out     # the checks dropped it unjudged
    assert [c["post"] for c in seen["judged"]] == [1, 2, 3, 4, 6]
    assert seen["judged"][0] == {"post": 1, "source": "source 1", "text": _candidate(1)}
    ideas = seen["written"][ct.IDEAS_PATH]
    assert "## 2026-09-25 — Evening" in ideas
    assert ideas.index("on day 2") < ideas.index("on day 1")
    assert GENERIC not in ideas and "on day 4" not in ideas and "why:" not in ideas
    sidecar = seen["written"][ct.SOURCES_PATH]
    assert sidecar.index("# Post sources") < sidecar.index("- post 1: source 2 (source 5")
    assert "- post 2: source 1 (source 4" in sidecar
    assert "- left out, candidate 4 (source 4" in sidecar
    assert "- left out, candidate 3 (source 2" in sidecar
    assert "- left out, candidate 5 (" in sidecar
    kind, payload = seen["events"][0]
    assert kind == "posts.filed" and payload["posts"] == 2 and payload["candidates"] == 6
    assert payload["kept"] == [2, 1] and payload["means"]["3"] == 2.0


def test_none_good_enough_is_sent_back_with_the_judges_lines(monkeypatch) -> None:
    posts = [_candidate(n) for n in range(1, 7)]
    seen = _patch(monkeypatch, {1: 3, 2: 2, 3: 2, 4: 2, 5: 3, 6: 1},
                  why={2: "restates the lesson", 6: "no trigger in the material"})
    with pytest.raises(ModelRetry) as exc:
        _file(posts, [f"s{n}" for n in range(1, 7)])
    text = str(exc.value)
    assert text.startswith("0 of 6 candidates scored a mean of 3.5 or more")
    assert "at least 1 must" in text
    assert "candidate 2 (source 2" in text and "restates the lesson" in text
    assert "candidate 6 (source 1" in text and "no trigger in the material" in text
    assert "Send all 6 to 8 candidates again" in text
    assert seen["written"] == {}


def test_too_few_candidates_or_sources_is_refused_before_the_judge(monkeypatch) -> None:
    seen = _patch(monkeypatch, {})
    with pytest.raises(ModelRetry, match="3 candidates; write 6 to 8"):
        _file([_candidate(n) for n in range(1, 4)], ["s"] * 3)
    with pytest.raises(ModelRetry, match="5 sources for 6 candidates"):
        _file([_candidate(n) for n in range(1, 7)], ["s"] * 5)
    assert seen["judged"] is None and seen["written"] == {}


def test_when_the_checks_leave_none_the_judge_is_not_asked(monkeypatch) -> None:
    seen = _patch(monkeypatch, {})
    posts = [LEAKY] * 6
    with pytest.raises(ModelRetry) as exc:
        _file(posts, ["s"] * 6)
    assert str(exc.value).startswith("0 of 6 candidates pass the checks, and at least 1 must")
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
    assert "six to eight candidate" in skill and "best one or two" in skill
    assert "three to five" not in skill
    assert "one entry per candidate" in skill and "`---`" in skill
    assert "Two real posts beat five" not in skill


def test_the_regression_set_holds_a_generic_post_dropped_by_the_judge() -> None:
    case = next(c for c in regress.load_cases("sage") if c.id == "sage-posts-generic-dropped-by-judge")
    assert case.skill == "daily-posts" and case.expect.calls == ["file_posts"]
    assert "file_posts" in case.canned and "left out" in str(case.canned["file_posts"])
    assert case.expect.args_match["file_posts"]



# --- what he shares: what he learns and builds, never the system around him -----------

@pytest.mark.parametrize("post", [
    ("I watched my agents fail three nights in a row. I don't think it's the model. It's the"
     " retry path, and it's the part I'd rather fix first before anything else this week."),
    ("My job sweep found forty roles last night. I think most of them aren't worth it. It's"
     " the same few companies again, and I don't think the market has moved at all."),
    ("Mission HQ wrote me a lesson on prefill tonight. I think it's good. It's the first one"
     " that didn't need a second pass, and I'd rather have that than a faster writer."),
])
def test_a_post_about_his_agent_system_is_refused(post: str) -> None:
    assert any("agent system" in p for p in ct.post_problems(post))


def test_a_post_about_what_he_learned_is_not_refused_for_it() -> None:
    post = ("I was reading how vLLM handles long prompts. It doesn't run the whole prompt"
            " at once. It cuts it into chunks and mixes them with decode steps, so short"
            " requests don't wait behind a long one. I think that's the part most people"
            " miss when they only look at average latency.")
    assert not any("agent system" in p for p in ct.post_problems(post))


def test_a_post_that_teaches_nothing_or_invents_is_not_kept_whatever_its_mean() -> None:
    fine = {1: 5, 2: 5, 3: 5}
    verdict = _verdict(fine)
    # Post 2 is a pleasure to read and teaches nothing; post 3 invents a number.
    verdict.scores[1].teaches = 2
    verdict.scores[2].accurate = 1
    kept, weak = ct.choose(verdict, [1, 2, 3])
    assert [s.post for s in kept] == [1]
    assert any("teaches 2" in w for w in weak) and any("accurate 1" in w for w in weak)



def test_a_one_line_take_passes_the_checks() -> None:
    take = ("The main appeal of open-weight agent harnesses isn't the price. It's that you"
            " can read what they do on your own machine.")
    assert ct.post_problems(take) == []
    assert any("words" in p for p in ct.post_problems("More tokens per second, please."))


def test_a_post_links_only_to_one_of_his_own_posts() -> None:
    body = ("I was reading how vLLM handles a long prompt. It cuts it into chunks and mixes"
            " them with decode steps, so short requests don't wait behind a long one.")
    own = "https://www.raghvendra.xyz/blog/kv-cache-llm-inference"
    assert ct.link_problems(f"{body} {own}") == []
    assert "his own site" in ct.link_problems(f"{body} https://vllm.ai/blog/anatomy")[0]
    assert "one at most" in ct.link_problems(f"{body} {own} {own}")[0]


def test_his_published_posts_are_listed_with_their_public_links(tmp_path, monkeypatch) -> None:
    from hq.config import settings
    from hq.tools import radar_tools as rt

    blog = tmp_path / "content" / "blog"
    blog.mkdir(parents=True)
    (blog / "kv-cache.md").write_text('---\ntitle: "KV cache"\ndate: 2026-09-28\ndraft: false\n---\nx')
    (blog / "wip.md").write_text("---\ntitle: WIP\ndate: 2026-09-29\ndraft: true\n---\nx")
    monkeypatch.setattr(settings(), "portfolio_dir", tmp_path)
    raw = inspect.unwrap(rt.list_my_posts)
    posts = asyncio.run(raw(types.SimpleNamespace(deps=None)))
    assert [p["url"] for p in posts] == [f"{settings().site_url}/blog/kv-cache"]


def test_a_post_the_reader_cannot_follow_is_not_kept_whatever_its_mean() -> None:
    """On 2026-09-29 he read a batch built on course terms and said he could
    not follow it himself."""
    lost = ct.PostScore.model_validate({**_score(1, 5), "clear": 2})
    assert lost.mean() > 4 and "clear 2" in lost.floor_problem()
    kept, weak = ct.choose(ct.PostVerdict(scores=[lost]), judged=[1])
    assert not kept and "clear 2" in weak[0]


def test_a_post_built_on_course_terms_is_sent_back() -> None:
    notes = ("Then they ran GSM8K on the served model and it scored 0.0099. The code viewed"
             " the FP8 KV cache through the wrong memory format.")
    assert any("only people who study model serving" in p for p in ct.post_problems(notes))
    plain = ("Put the part of your prompt that changes at the end, not the top. Providers"
             " charge about a tenth for text they have seen before, but only when it matches"
             " from the first character.")
    assert not any("only people who study model serving" in p for p in ct.post_problems(plain))


# --- what X counts against a post: bait and a repeat -----------------------------------

@pytest.mark.parametrize("bait", [
    "Like if you agree.", "Repost if your team does this too.", "Comment “YES” and I'll",
    "Tag 3 dev friends who need this.", "Tag someone who ships on Fridays.",
    "Bookmark this before you forget.", "Save this for later.", "Follow me for more.",
    "Drop a \U0001f525 if this happened to you.", "Reply \"cache\" and I'll send it.",
])
def test_a_post_that_asks_for_a_reaction_is_refused(bait: str) -> None:
    post = ("Put the part of your prompt that changes at the end. Providers charge about a"
            " tenth for text they've seen before, but only when it matches from the start. "
            + bait)
    assert any("asks for a reaction" in p for p in ct.post_problems(post))


@pytest.mark.parametrize("plain", [
    "Run git tag before you deploy, so a rollback knows where to go.",
    "The API will reply with a 200 even when the model refused.",
    "Comment it for the next person, and drop a table in staging first.",
    "The model will like it if the prompt is short, and the comment below the function says why.",
    "Save this file to disk before the next call, then tag a dev build.",
])
def test_a_developers_ordinary_words_are_not_bait(plain: str) -> None:
    assert not ct._BAIT_RE.search(plain)


EARLIER = ("---\ncreated: 2026-09-01\n---\n# Content ideas\n\n"
           "## 2026-09-24 — Evening\n\n" + GOOD + "\n\n---\n\n" + GENERIC + "\n\n"
           "## 2026-09-20 — One post\n\nPut the changing part of your prompt at the end. It's"
           " cheaper, because the provider reuses what it saw before.\n\n"
           "## 2026-09-19 — Ideas\n\n1. An idea, not a post.\n2. Another idea.\n\n"
           "## 2026-08-01 — Last summer\n\nOld post about tokens and caching and prompts.\n")


def test_the_posts_of_the_last_month_are_read_newest_first() -> None:
    earlier = ct.recent_posts(EARLIER, date(2026, 9, 25))
    assert [(e["id"], e["day"]) for e in earlier] == [
        ("E1", "2026-09-24"), ("E2", "2026-09-24"), ("E3", "2026-09-20")]
    assert earlier[0]["text"] == GOOD and earlier[2]["text"].startswith("Put the changing")
    assert ct.recent_posts(EARLIER, date(2026, 9, 24))[0]["day"] == "2026-09-20"  # not today
    assert ct.recent_posts(None, date(2026, 9, 25)) == []


def test_a_near_copy_of_a_recent_post_is_refused_and_a_new_angle_is_not() -> None:
    earlier = ct.recent_posts(EARLIER, date(2026, 9, 25))
    copy = GOOD.replace("last week", "this week").replace("people miss", "devs miss")
    assert "shares" in ct.repeat_problem(copy, earlier) and "2026-09-24" in ct.repeat_problem(
        copy, earlier)
    angle = ("A long prompt makes every short request behind it wait. If your chat app feels"
             " slow only sometimes, look at the longest prompt in the batch, not the average.")
    assert ct.repeat_problem(angle, earlier) == ""
    assert ct.overlap(GOOD, GENERIC) < 0.2


TIP = ("Put the part of your prompt that changes at the end, not the top. Providers charge"
       " about a tenth for text they've seen before, but only when it matches from the first"
       " character. One date at the top and you pay full price every time.")


def test_the_judge_sees_the_last_months_posts_and_a_repeat_is_not_kept(monkeypatch) -> None:
    seen = _patch(monkeypatch, {n: 4 for n in range(1, 7)},
                  existing="# Content ideas\n\n## 2026-09-24 — Evening\n\n" + TIP + "\n")
    copy = TIP.replace("One date at the top", "A timestamp at the top")
    posts = [copy] + [_candidate(n) for n in range(2, 7)]
    with pytest.raises(ModelRetry) as exc:          # the first call sends the copy back
        _file(posts, [f"s{n}" for n in range(1, 7)], retry=0)
    assert "candidate 1 (" in str(exc.value) and "2026-09-24" in str(exc.value)
    assert seen["judged"] is None
    out = _file(posts, [f"s{n}" for n in range(1, 7)])
    assert seen["earlier"] == [{"id": "E1", "day": "2026-09-24", "text": TIP}]
    assert 1 not in [c["post"] for c in seen["judged"]] and "candidate 1 (" in out


def test_a_post_the_judge_marks_as_a_repeat_is_not_kept_whatever_its_mean() -> None:
    again = ct.PostScore.model_validate({**_score(1, 5), "repeats": "E2"})
    assert "repeats E2" in again.floor_problem()
    kept, weak = ct.choose(ct.PostVerdict(scores=[again]), judged=[1])
    assert not kept and "repeats E2" in weak[0]


def test_a_post_nobody_would_send_on_is_not_kept_whatever_its_mean() -> None:
    dull = ct.PostScore.model_validate({**_score(1, 5), "share": 2})
    assert dull.mean() > 4 and "share 2" in dull.floor_problem()


def test_a_batch_of_one_post_counts_as_one() -> None:
    from hq import value

    md = ("# Content ideas\n\n## 2026-10-02 — Evening\n\n" + GOOD + "\n\n"
          "## 2026-10-01 — Evening\n\n" + GOOD + "\n\n---\n\n" + GENERIC + "\n")
    assert value.count_ideas(md, date(2026, 10, 1), date(2026, 10, 2)) == 3


def test_a_title_that_starts_with_the_date_and_a_colon_loses_both() -> None:
    """On 2026-10-02 sage titled the batch "2026-10-02: package-cache ...",
    and the heading read "## 2026-10-02 — : package-cache ..."."""
    out = ct.with_batch(None, GOOD, "2026-10-02", "2026-10-02: package-cache board, 16-token blocks")
    assert "## 2026-10-02 — package-cache board, 16-token blocks\n" in out


def test_a_post_that_loses_a_condition_is_not_kept_whatever_its_mean() -> None:
    """The judge scored the post that called vLLM's 16-token blocks how
    "prompt caches" work accurate 3 with a mean of 3.5, on the bar."""
    lost = ct.PostScore.model_validate({**_score(1, 4), "accurate": 3, "teaches": 3,
                                        "insight": 3, "share": 3, "reply": 3, "source": 5})
    assert lost.mean() >= ct.KEEP_MEAN and "accurate 3" in lost.floor_problem()
    kept, weak = ct.choose(ct.PostVerdict(scores=[lost]), judged=[1])
    assert not kept and "accurate 3" in weak[0]
