"""The staged writer: plan checked by code, sections written alone, page
assembled under the real contract, sentences checked against the note."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import pytest

from hq import lesson_writer as lw
from hq.tools import learning_tools as lt
from hq.tools.registry import HQDeps

NOTE = """---
source_urls:
- https://ex.dev/orca
---
# Orca, study note

Iteration-level scheduling returns a finished request to the client at the end
of the iteration it finished in. Measured on GPT-3 175B, Orca served 36.9x the
throughput of FasterTransformer at the same latency.
"""


def _concept(**kw: Any) -> dict[str, Any]:
    base = {"id": "c1", "claim": "A batch that is rebuilt every iteration never makes a short request wait for a long one",
            "lets_him": "predict tail latency under mixed lengths", "wrong_belief": "batching always adds wait",
            "predict": "A short and a long request share a batch. When does the short one return?",
            "evidence": "36.9x throughput over FasterTransformer at the same latency, GPT-3 175B",
            "evidence_quote": "Orca served 36.9x the throughput of FasterTransformer",
            "picture": "a timeline of iterations"}
    return {**base, **kw}


def _outline(**kw: Any) -> dict[str, Any]:
    base = {
        "title": "Why does a short request stop waiting for a long one",
        "subtitle": "What changes when the batch is rebuilt every iteration",
        "eyebrow": "paper · Inference Internals Phase 2A · iteration-level scheduling",
        "outcome": "Predict when a request returns in a mixed batch",
        "opening": "Your chat endpoint is fast alone and slow under load.",
        "concepts": [_concept()],
        "sections": [
            {"heading": "What happens to a short request in a static batch", "concept": "c1", "covers": "the wait"},
            {"heading": "How much does rebuilding the batch buy", "concept": "c1", "covers": "the number"},
            {"heading": "Fifteen minutes today", "kind": "lab", "covers": "one thing to try"},
            {"heading": "A question to test the transfer", "kind": "checkpoint", "covers": "one scenario"},
            {"heading": "Two things you could post", "kind": "post", "covers": "two angles"},
            {"heading": "Sources", "kind": "sources", "covers": "the urls"},
        ],
    }
    return {**base, **kw}


def test_a_plan_is_checked_before_a_word_is_written() -> None:
    ok = lw.Outline.model_validate(_outline())
    assert lw.outline_problems(ok, NOTE, article=True) == []

    two = lw.Outline.model_validate(_outline(concepts=[_concept(), _concept(id="c2")]))
    assert any("exactly one" in p for p in lw.outline_problems(two, NOTE, article=True))

    invented = lw.Outline.model_validate(_outline(concepts=[_concept(
        evidence_quote="Orca served 50x the throughput of vLLM")]))
    assert any("not in the study note" in p for p in lw.outline_problems(invented, NOTE, article=True))

    told = lw.Outline.model_validate(_outline(concepts=[_concept(predict="It returns early.")]))
    assert any("predict question" in p for p in lw.outline_problems(told, NOTE, article=True))

    orphan = _outline()
    orphan["sections"] = [s for s in orphan["sections"] if s.get("kind")]
    assert any("no section teaches c1" in p
               for p in lw.outline_problems(lw.Outline.model_validate(orphan), NOTE, article=True))


def test_a_phase_plan_needs_three_to_five_concepts_and_its_apparatus() -> None:
    plan = lw.Outline.model_validate(_outline())
    probs = lw.outline_problems(plan, NOTE, article=False)
    assert any("three to five" in p for p in probs)
    assert not any("no checkpoint" in p for p in probs)
    assert any("no cheatsheet section" in p for p in probs)


def test_a_section_is_cleaned_of_what_the_writer_adds_itself() -> None:
    raw = '```html\n<h2 data-concept="c1">Mine</h2>\n<p>Body.</p>\n```'
    assert lw.clean_section(raw) == "<p>Body.</p>"


def test_a_whole_page_refusal_is_traced_to_the_parts_it_quotes() -> None:
    w = lw.Writer.__new__(lw.Writer)
    w.parts = ["<p>opening</p>", "<h2>a</h2><p>Run the comparison with a large prompt now.</p>",
               "<h2>b</h2><p>Something else.</p>"]
    msg = ("1 sentence(s) carry a verification date, such as “Run the comparison with a"
           " large prompt…”. When something was checked belongs in the sources")
    assert w._parts_quoting(msg) == [1]


def _section_html(i: int, s: lw.SectionPlan) -> str:
    """A section a good writer would return: short sentences, a picture, and a
    predict question on the concept's first section."""
    if s.kind == "sources":
        return '<ul class="sources"><li><a href="https://ex.dev/orca">The Orca paper</a> gave the number.</li></ul>'
    if s.kind == "post":
        return "<p>One: batching per iteration ends the convoy.</p><p>Two: measure the short request, not the mean.</p>"
    if s.kind == "lab":
        return '<div class="lab"><p>Send one short and one long request together. Time the short one.</p></div>'
    if s.kind == "checkpoint":
        return ('<p>Two requests share a batch. One needs 20 tokens and one needs 2,000.</p>'
                '<details class="answer"><summary>Answer sketch</summary><p>The short one returns after its'
                ' own twenty iterations.</p></details>')
    predict = ('<details class="predict"><summary>Predict: when does the short request return?'
               '</summary><p>At the end of its own last iteration.</p></details>') if i == 1 else ""
    body = [
        "<p>A static batch holds every request until the longest one ends.</p>",
        "<p>The short request is done early. It still waits.</p>",
        (f'<figure class="diagram"><svg viewBox="0 0 100 20"><rect id="s{i}-bar" width="40" height="10"/>'
         '<text x="0" y="18" fill="currentColor">iterations</text></svg>'
         "<figcaption>Illustration, not measured.</figcaption></figure>"),
        "<p>Rebuilding the batch each iteration lets the short request leave.</p>",
        "<p>The server checks the batch after every forward pass.</p>",
        "<p>A finished request goes back to the client at once.</p>",
        "<p>A new request can take its slot in the next pass.</p>",
    ]
    if i == 2:
        body = [
            "<p>The paper measured the effect on a large model.</p>",
            '<div class="stats"><div class="stat"><b>36.9x</b><span>throughput at equal latency</span></div></div>',
            "<p>That is 36.9x the throughput of FasterTransformer at the same latency, on GPT-3 175B.</p>",
            "<p>The gain comes from not holding finished work.</p>",
            "<p>The slot a request frees is filled in the next pass.</p>",
        ]
    closing = ('<div class="keypoints"><p class="remember">Rebuild the batch every iteration.</p>'
               '<p class="trap">Holding finished work costs throughput.</p>'
               '<p class="try">Time a short request under load.</p></div>')
    return predict + "".join(body) + closing


def test_an_article_is_written_in_stages_and_passes_the_real_page_contract(
        tmp_path: Path, monkeypatch) -> None:
    learning = tmp_path / "learning"
    (learning / "lessons").mkdir(parents=True)
    monkeypatch.setattr(lt.settings(), "learning_dir", learning)

    async def outline_step(model: str, article: bool, material: str, problems: list[str],
                           page: str = "", previous: Any = None):
        return _outline()

    async def release_step(claims):
        return {"fails": [], "reasons": []}

    calls: list[int] = []

    async def section_step(model: str, prompt: str) -> str:
        if "Id prefix: s0-" in prompt:
            return "<p>Your endpoint is fast alone.</p><p>Under load, short answers wait.</p>"
        number = int(prompt.split("Id prefix for this section: s")[1].split("-")[0])
        calls.append(number)
        plan = lw.Outline.model_validate(_outline())
        return _section_html(number, plan.sections[number - 1])

    async def citation_step(note: str, claims):
        return {"unsupported": [], "reasons": []}

    recorded: dict[str, Any] = {}

    async def record_row(**kw: Any) -> str:
        recorded.update(kw)
        return "lesson-1"

    async def no_emit(*a: Any, **k: Any) -> None:
        return None

    monkeypatch.setattr(lw, "_outline_step", outline_step)
    monkeypatch.setattr(lw, "_release_step", release_step)
    monkeypatch.setattr(lw, "_section_step", section_step)
    monkeypatch.setattr(lw, "_citation_step", citation_step)
    reviews: list[tuple[str, str, str]] = []

    async def set_review(lesson_id: str, status: str, notes: str = "") -> None:
        reviews.append((lesson_id, status, notes))

    monkeypatch.setattr(lt, "record_lesson_row", record_row)
    monkeypatch.setattr(lt, "set_review", set_review)
    monkeypatch.setattr(lt, "emit", no_emit)

    material = lw.Material(article=True, slug="", kind="paper", relationship="foundation",
                           note=NOTE, prompt="the material", source_urls=["https://ex.dev/orca"],
                           payload={"phase_slug": "inference-internals-phase-02a-scheduling-memory"})
    spec = type("Spec", (), {"model": "teacher", "name": "tutor"})()
    w = lw.Writer(spec, HQDeps(agent="tutor", task_id="t-1", run_id=None), material)  # type: ignore[arg-type]
    try:
        result = asyncio.run(w.run())
    finally:
        shutil.rmtree(learning / "lessons" / lt.DRAFTS_SUBDIR, ignore_errors=True)
    assert result is not None, w.report
    _md_path, html_path, lesson_id = result
    page = (tmp_path / html_path).read_text()
    assert '<ol class="concepts">' in page and 'data-concept="c1"' in page
    assert calls == [1, 2, 3, 4, 5, 6]          # each section written once, in order
    assert recorded["kind"] == "topic" and recorded["phase_slug"].endswith("02a-scheduling-memory")
    assert recorded["source_urls"] == "https://ex.dev/orca"
    assert lesson_id == "lesson-1"
    assert reviews == [("lesson-1", "passed", "")]   # a clean page is passed
    assert lw.saved_outline("t-1") is None           # the plan is dropped once recorded


@pytest.mark.parametrize("stage,source,expected", [
    ("course_lesson", "platform", True), ("course_lesson", "local", False),
    ("lesson_synthesis", None, True), ("lab_card", None, True), ("week_review", None, True),
    ("post_draft", None, True), ("source_hunt", None, False),
])
def test_the_writer_takes_what_tutor_writes(stage: str, source: str | None,
                                                   expected: bool) -> None:
    from hq.config import settings
    from hq.loader import parse_job_md

    tutor = parse_job_md(settings().agents_dir / "tutor")
    payload: dict[str, Any] = {"workflow": "learning_journey", "stage": stage}
    if source:
        payload["source"] = source
    assert lw.handles(tutor, payload) is expected


def test_code_settles_what_code_can_settle_in_a_plan() -> None:
    plan = _outline()
    plan["sections"][2] = {"heading": "What this changes in the course", "concept": "c1",
                           "kind": "orientation", "covers": "the change"}
    outline = lw.normalize_outline(lw.Outline.model_validate(plan))
    assert outline.sections[2].concept == "" and outline.sections[2].kind == "orientation"
    assert lw.outline_problems(outline, NOTE, article=True) == []


def test_a_long_claim_is_sent_back_with_the_claim_quoted() -> None:
    long = " ".join(["word"] * 41)
    plan = lw.Outline.model_validate(_outline(concepts=[_concept(claim=long)]))
    probs = lw.outline_problems(plan, NOTE, article=True)
    assert any(long in p and "aim for 20" in p for p in probs)


def _fake_writer(tmp_path: Path, monkeypatch, *, fail_at: int | None = None,
                 unsupported: set[int] | None = None):
    """A writer with every model call faked; returns (writer factory, log)."""
    learning = tmp_path / "learning"
    (learning / "lessons").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(lt.settings(), "learning_dir", learning)
    log: dict[str, Any] = {"outline": 0, "sections": [], "cited": [], "reviews": []}

    async def outline_step(*a: Any, **k: Any):
        log["outline"] += 1
        return _outline()

    async def release_step(claims):
        return {"fails": [], "reasons": []}

    async def section_step(model: str, prompt: str) -> str:
        if "Id prefix: s0-" in prompt:
            return "<p>Your endpoint is fast alone.</p><p>Under load, short answers wait.</p>"
        number = int(prompt.split("Id prefix for this section: s")[1].split("-")[0])
        if fail_at is not None and number == fail_at and not log.get("failed"):
            log["failed"] = True
            raise RuntimeError("gateway went away")
        log["sections"].append(number)
        plan = lw.Outline.model_validate(_outline())
        return _section_html(number, plan.sections[number - 1])

    async def citation_step(note: str, claims):
        log["cited"].append([c["id"] for c in claims])
        bad = [c["id"] for c in claims
               if unsupported and int(c["id"][1:].split("-")[0]) in unsupported]
        return {"unsupported": bad, "reasons": ["not in the note"] * len(bad)}

    async def record_row(**kw: Any) -> str:
        return "lesson-1"

    async def set_review(lesson_id: str, status: str, notes: str = "") -> None:
        log["reviews"].append((status, notes))

    async def no_emit(*a: Any, **k: Any) -> None:
        return None

    monkeypatch.setattr(lw, "_outline_step", outline_step)
    monkeypatch.setattr(lw, "_release_step", release_step)
    monkeypatch.setattr(lw, "_section_step", section_step)
    monkeypatch.setattr(lw, "_citation_step", citation_step)
    monkeypatch.setattr(lt, "record_lesson_row", record_row)
    monkeypatch.setattr(lt, "set_review", set_review)
    monkeypatch.setattr(lt, "emit", no_emit)

    def make() -> lw.Writer:
        material = lw.Material(article=True, slug="", kind="paper", relationship="foundation",
                               note=NOTE, prompt="the material",
                               source_urls=["https://ex.dev/orca"], payload={})
        spec = type("Spec", (), {"model": "teacher", "name": "tutor"})()
        return lw.Writer(spec, HQDeps(agent="tutor", task_id="t-9", run_id=None),  # type: ignore[arg-type]
                         material)
    return make, log


def test_a_requeued_lesson_resumes_from_its_plan_and_finished_parts(
        tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch, fail_at=4)
    with pytest.raises(RuntimeError):
        asyncio.run(make().run())
    assert log["outline"] == 1 and log["sections"] == [1, 2, 3]
    assert lw.saved_outline("t-9") is not None

    w = make()
    assert asyncio.run(w.run()) is not None, w.report
    assert log["outline"] == 1                    # the plan was not asked for again
    assert log["sections"] == [1, 2, 3, 4, 5, 6]  # only the missing parts were written
    assert any("earlier attempt" in r for r in w.report)


def test_every_part_is_cited_and_an_unmapped_sentence_flags_without_blocking(
        tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch, unsupported={4})
    w = make()
    assert asyncio.run(w.run()) is not None, w.report
    # The fake sections carry checkable sentences in sections 2 and 4 only;
    # both are sent, tagged with their section, in one batch.
    assert log["cited"][0] == ["p2-c1", "p4-c1"]
    assert log["sections"].count(4) == 2          # section 4 was sent back once
    assert log["cited"][1] == ["p4-c1"]           # and only it was checked again
    status, notes = log["reviews"][-1]
    assert status == "flagged" and "not in the note" in notes


def test_model_text_in_a_heading_is_escaped() -> None:
    s = lw.SectionPlan(heading="Why p99 < p50 & more", concept="c1", covers="x")
    assert lw._h2(1, s) == '<h2 data-concept="c1">Why p99 &lt; p50 &amp; more</h2>'


def test_the_writer_is_told_the_charter_first() -> None:
    text = lw.section_instructions()
    assert text.startswith("# Mission HQ charter")
    assert len(lw.bundle_sha()) == 12


def test_a_part_that_names_an_employer_is_sent_back_alone(monkeypatch) -> None:
    from hq import privacy
    from hq.config import settings

    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp",))
    privacy._pattern.cache_clear()
    html = '<h2 data-concept="c1">Queues</h2><p>At Acme Corp the queue grew every night.</p>'
    probs = lw.section_problems(html, earlier="", article=True, kind="", apparatus=True,
                                total_words=0)
    assert any("employers" in p for p in probs)
    assert not any("Acme" in p for p in probs)   # the refusal never repeats the name


def test_a_one_idea_plan_cannot_carry_three_concepts() -> None:
    plan = _outline()
    concept = {**plan["concepts"][0], "id": "c7"}
    one = lw.ArticleOutline.model_validate(
        {k: v for k, v in plan.items() if k != "concepts"} | {"concept": concept})
    outline = one.as_outline()
    assert [c.id for c in outline.concepts] == ["c1"]
    assert "concepts" not in lw.ArticleOutline.model_json_schema()["properties"]


def test_a_claim_a_word_past_the_target_is_not_sent_back() -> None:
    claim = " ".join(["word"] * 33)
    plan = lw.Outline.model_validate(_outline(concepts=[_concept(claim=claim)]))
    assert not any("claim is" in p for p in lw.outline_problems(plan, NOTE, article=True))


def test_an_article_page_is_budgeted_before_it_is_written() -> None:
    outline = lw.Outline.model_validate(_outline())
    budgets = lw.word_budgets(outline, lt.ARTICLE_MAX_WORDS)
    assert set(budgets) == set(range(1, len(outline.sections) + 1))
    assert sum(budgets.values()) + lw.OPENING_WORDS <= lt.ARTICLE_MAX_WORDS
    long = "<h2 data-concept=\"c1\">Q</h2><p>" + "word " * 700 + "</p>"
    probs = lw.section_problems(long, earlier="", article=True, kind="", apparatus=False,
                                total_words=3000, budget=400)
    assert any("its share of the page is about 400" in p for p in probs)
    assert not any(p.startswith("the article is already") for p in probs)


def test_a_sent_back_plan_is_repaired_from_the_previous_one(tmp_path: Path, monkeypatch) -> None:
    seen: list[Any] = []
    plans = [_outline(concepts=[_concept(claim=" ".join(["word"] * 45))]), _outline()]

    async def outline_step(model, article, material, problems, page="", previous=None):
        seen.append((list(problems), previous))
        return plans[len(seen) - 1]

    async def release_step(claims):
        return {"fails": [], "reasons": []}

    monkeypatch.setattr(lw, "_outline_step", outline_step)
    monkeypatch.setattr(lw, "_release_step", release_step)
    material = lw.Material(article=True, slug="", kind="paper", note=NOTE, prompt="m")
    spec = type("Spec", (), {"model": "teacher", "name": "tutor"})()
    w = lw.Writer(spec, HQDeps(agent="tutor", task_id=None, run_id=None), material)  # type: ignore[arg-type]
    assert asyncio.run(w.plan()) is not None
    assert seen[0] == ([], None)
    assert seen[1][0] and seen[1][1] == plans[0]   # the problems AND the plan they are about


def test_the_part_check_and_the_page_check_agree_on_figures() -> None:
    long = " ".join(["The course said the batch was fixed; this run shows it is rebuilt."] * 30)
    part = f'<h2 data-kind="orientation">What this changes in the course</h2><p>{long}</p>'
    page_says = lt.sections_without_a_visual(part)
    part_says = [p for p in lw.section_problems(part, earlier="", article=True, kind="",
                                                apparatus=True, total_words=0)
                 if p.startswith("nothing to look at")]
    assert bool(page_says) == bool(part_says) == True
    short = '<h2 data-kind="orientation">What this changes</h2><p>It changes one thing.</p>'
    assert not lt.sections_without_a_visual(short)


def test_a_part_that_restates_too_much_is_sent_back_alone() -> None:
    body = "<p>" + "The scheduler rebuilds the batch every step. " * 30 + "</p>"
    heavy = ('<h2 data-concept="c1">Why?</h2><p class="why">' + "It matters because. " * 20
             + "</p>" + body + '<div class="keypoints"><p class="remember">'
             + "Rebuild the batch every step. " * 12 + "</p></div>")
    probs = lw.section_problems(heavy, earlier="", article=True, kind="", apparatus=False,
                                total_words=0)
    assert any("key-point box and the lead here" in p for p in probs)


def test_a_dated_teaching_sentence_is_caught_on_its_part() -> None:
    html = ('<h2 data-concept="c1">Q</h2><p>The read multiplier is 0.1x of the base input'
            ' price, verified on 2026-09-23 against the pricing page today.</p>')
    probs = lw.section_problems(html, earlier="", article=True, kind="", apparatus=False,
                                total_words=0)
    assert any("carries a date" in p for p in probs)
    assert "at most\n15 words" in (lw.writer_dir() / "section.md").read_text()


def test_an_invented_lab_command_is_sent_back_on_its_part() -> None:
    source = "**E1** Run: `python phase02/sim.py --turns 4`\n"
    part = ('<h2 data-kind="lab">Lab</h2><ul class="exercises"><li><b>E1</b> Run: '
            '<code>python phase02/sim.py --turns 12 --inject-overflow 5</code></li></ul>')
    probs = lw.section_problems(part, earlier="", article=False, kind="", apparatus=True,
                                total_words=0, source=source)
    assert any("not in his lab" in p for p in probs)
    assert lt.lab_fidelity_problems(part, source)   # the same rule the page runs


def test_a_page_is_planned_without_concepts() -> None:
    plan = lw.PageOutline.model_validate({
        "title": "Lab card", "subtitle": "s", "eyebrow": "e", "outcome": "o", "opening": "x",
        "takeaway": "A chunked prefill keeps decode ticking.",
        "sections": [{"heading": "What you will have", "kind": "orientation", "covers": "c"},
                     {"heading": "The build", "kind": "lab", "covers": "c"},
                     {"heading": "Sources", "kind": "sources", "covers": "c"}]}).as_outline()
    assert plan.concepts == [] and lw.page_problems(plan, "lab") == []
    assert "no checkpoint section" in " ".join(lw.page_problems(plan, "review"))
    bad = plan.model_copy(update={"sections": [lw.SectionPlan(heading="Q", concept="c1", covers="c")]})
    assert any("needs a kind" in p for p in lw.page_problems(bad, "lab"))


def test_a_page_is_held_to_every_check_but_the_concept_contract() -> None:
    body = "<p>" + "Run the simulator and read the queue depth every step. " * 60 + "</p>"
    page = f'<h2 data-kind="lab">The build</h2><div class="steps">{body}</div>'
    assert "concept" not in lt.page_coverage("", page, "", least=0, most=0)


def test_a_week_review_recalls_each_lesson_whole() -> None:
    page = ('<ol class="concepts"><li id="c1"><b>Batches rebuild each step.</b><span>x</span></li></ol>'
            '<h2 data-concept="c1">Why?</h2><p>' + "long prose. " * 500 + '</p>'
            '<div class="keypoints"><p class="remember">Rebuild the batch.</p>'
            '<p class="trap">A static batch waits.</p></div>'
            '<h2 data-kind="checkpoint">Checkpoint</h2><p>Q1?</p><details class="answer">A1</details>')
    out = lw.lesson_essentials(page)
    assert "Batches rebuild each step." in out and "Rebuild the batch." in out
    assert "A1" in out and "long prose" not in out


def test_an_over_length_page_is_cut_where_the_parts_ran_over() -> None:
    w = lw.Writer.__new__(lw.Writer)
    w.budgets = {1: 100, 2: 100, 3: 100}
    w.parts = ["", "<p>" + "word " * 90 + "</p>", "<p>" + "word " * 300 + "</p>",
               "<p>" + "word " * 150 + "</p>"]
    assert w._over_budget("the article is 2829 words, which is about 14 minutes") == [2, 3]
    assert w._over_budget("some other refusal") == []


def test_an_evidence_quote_with_a_small_edit_is_still_the_notes_words() -> None:
    body = lw._norm("The paper reports that chunked prefill cut p99 TPOT by 2.6x on "
                    "Mistral-7B with a 512 token budget.")
    assert lw.quoted_from(lw._norm("chunked prefill cut p99 TPOT by 2.6x on Mistral-7B "
                                   "with 512 token budget"), body)
    assert not lw.quoted_from(lw._norm("speculative decoding doubled throughput on every "
                                       "model we tried"), body)
