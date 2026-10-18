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


def _ledger(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ledger a plan carries: the first teaching section introduces the
    term, the ones below it assume it and say what they follow from."""
    out, first = [], True
    for s in sections:
        s = dict(s)
        if not s.get("kind"):
            if first:
                s.setdefault("introduces", ["static batch"])
            else:
                s.setdefault("assumes", ["static batch"])
                s.setdefault("bridge", "The section above left the cost of waiting unexplained.")
            first = False
        out.append(s)
    return out


def _outline(**kw: Any) -> dict[str, Any]:
    out = _outline_base(**kw)
    out["sections"] = _ledger(out["sections"])
    return out


def _outline_base(**kw: Any) -> dict[str, Any]:
    base = {
        "title": "Why does a short request stop waiting for a long one",
        "subtitle": "What changes when the batch is rebuilt every iteration",
        "eyebrow": "paper · Inference Internals Phase 2A · iteration-level scheduling",
        "outcome": "Predict when a request returns in a mixed batch",
        "running_case": "A chat endpoint that is fast alone and slow under load.",
        "opening": "Your chat endpoint is fast alone and slow under load.",
        "concepts": [_concept()],
        "sections": [
            {"heading": "What happens to a short request in a static batch", "concept": "c1", "covers": "the wait"},
            {"heading": "How much does rebuilding the batch buy", "concept": "c1", "covers": "the number"},
            {"heading": "A question to test the transfer", "kind": "checkpoint", "covers": "one scenario"},
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
    if i == 3:
        return ("<p>A freed slot is a row in the next forward pass.</p>"
                "<p>The scheduler fills it from the waiting queue.</p>"
                "<p>So the queue drains while long requests keep running.</p>")
    if i == 4:
        return ("<p>After each pass the server asks one question per request.</p>"
                "<p>Did this request emit its stop token?</p>"
                "<p>If yes, its tokens are sent and its memory is released.</p>")
    predict = ('<details class="predict"><summary>Predict: when does the short request return?'
               '</summary><p>At the end of its own last iteration.</p></details>') if i == 1 else ""
    body = [
        "<p>A <dfn>static batch</dfn> holds every request until the longest one ends.</p>"
        if i == 1 else
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

    async def section_step(model: str, prompt: str, effort: str = "low") -> str:
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
    # The editor's rewrites go through their own step; same fake.
    monkeypatch.setattr(lw, "_rewrite_step", lambda model, prompt: section_step(model, prompt))
    monkeypatch.setattr(lw, "_citation_step", citation_step)
    monkeypatch.setattr(lw, "_editor_step", _editor_all(5))
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
    assert calls == [1, 2, 3, 4]                # each section written once, in order
    assert recorded["kind"] == "topic" and recorded["phase_slug"].endswith("02a-scheduling-memory")
    assert recorded["source_urls"] == "https://ex.dev/orca"
    assert lesson_id == "lesson-1"
    assert [(r[0], r[1]) for r in reviews] == [("lesson-1", "passed")]   # a clean page is passed
    assert reviews[0][2].startswith("Editor scores: mean 5.0 of 5 over 2 teaching section(s)")
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


def _score(number: int, value: int = 5, rewrite: str = "", **low: int) -> dict[str, Any]:
    return {"number": number, **{c: low.get(c, value) for c in lw.CRITERIA}, "rewrite": rewrite}


def _editor_all(value: int):
    async def editor_step(concepts, material, context, parts):
        return {"sections": [_score(p["number"], value) for p in parts]}
    return editor_step


def _fake_writer(tmp_path: Path, monkeypatch, *, fail_at: int | None = None,
                 unsupported: set[int] | None = None, outline: dict[str, Any] | None = None,
                 editor: Any = None, finish_fails: bool = False):
    """A writer with every model call faked; returns (writer factory, log)."""
    learning = tmp_path / "learning"
    (learning / "lessons").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(lt.settings(), "learning_dir", learning)
    log: dict[str, Any] = {"outline": 0, "sections": [], "cited": [], "reviews": [],
                           "prompts": {}, "edited": []}
    plan_data = outline or _outline()

    async def outline_step(*a: Any, **k: Any):
        log["outline"] += 1
        return plan_data

    async def release_step(claims):
        return {"fails": [], "reasons": []}

    async def section_step(model: str, prompt: str, effort: str = "low") -> str:
        if "Id prefix: s0-" in prompt:
            return "<p>Your endpoint is fast alone.</p><p>Under load, short answers wait.</p>"
        number = int(prompt.split("Id prefix for this section: s")[1].split("-")[0])
        if fail_at is not None and number == fail_at and not log.get("failed"):
            log["failed"] = True
            raise RuntimeError("gateway went away")
        log["sections"].append(number)
        log["prompts"].setdefault(number, []).append(prompt)
        plan = lw.Outline.model_validate(plan_data)
        html = _section_html(number, plan.sections[number - 1])
        if "teaching editor" in prompt:   # a rewrite is new text, so it is scored again
            html = f"<p>Now it opens with the question for section {number}.</p>" + html
        return html

    async def citation_step(note: str, claims):
        log["cited"].append([c["id"] for c in claims])
        bad = [c["id"] for c in claims
               if unsupported and int(c["id"][1:].split("-")[0]) in unsupported]
        return {"unsupported": bad, "reasons": ["not in the note"] * len(bad)}

    async def record_row(**kw: Any) -> str:
        return "lesson-1"

    async def correct_step(model: str, note: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        # Removes each flagged sentence, one of the two outcomes the step allows.
        log.setdefault("corrected", []).extend(
            f["sentence"][:40] for i in items for f in i["sentences"])
        out = []
        for item in items:
            html = item["html"]
            for f in item["sentences"]:
                html = html.replace(f["sentence"], "", 1).replace("  ", " ")
            out.append({"n": item["n"], "html": html})
        return {"paragraphs": out}

    finish = lt.finish_lesson

    async def finish_once_failing(*a: Any, **k: Any) -> Any:
        if finish_fails and not log.get("finish_failed"):
            log["finish_failed"] = True
            raise RuntimeError("the disk went away")
        return await finish(*a, **k)

    async def set_review(lesson_id: str, status: str, notes: str = "") -> None:
        log["reviews"].append((status, notes))

    fake_editor = editor or _editor_all(5)

    async def editor_step(concepts, material, context, parts):
        log["edited"].append([p["number"] for p in parts])
        return await fake_editor(concepts, material, context, parts)

    async def no_emit(*a: Any, **k: Any) -> None:
        return None

    monkeypatch.setattr(lw, "_outline_step", outline_step)
    monkeypatch.setattr(lw, "_release_step", release_step)
    monkeypatch.setattr(lw, "_section_step", section_step)
    # The editor's rewrites go through their own step; same fake.
    monkeypatch.setattr(lw, "_rewrite_step", lambda model, prompt: section_step(model, prompt))
    monkeypatch.setattr(lw, "_citation_step", citation_step)
    monkeypatch.setattr(lw, "_correct_step", correct_step)
    monkeypatch.setattr(lw, "_editor_step", editor_step)
    monkeypatch.setattr(lt, "finish_lesson", finish_once_failing)
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
    assert log["sections"] == [1, 2, 3, 4]        # only the missing parts were written
    assert any("earlier attempt" in r for r in w.report)


def test_every_part_is_cited_and_an_unmapped_sentence_flags_without_blocking(
        tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch, unsupported={3})
    w = make()
    assert asyncio.run(w.run()) is not None, w.report
    # An article sends every sentence of every part, numbers or not, tagged
    # with its part, in batches.
    cited = [c for batch in log["cited"][:1] for c in batch]
    # (The fake sources line is too short to be a sentence.)
    assert {int(c[1:].split("-")[0]) for c in cited} == {1, 2, 3}
    # Section 3's unsupported sentences are corrected in place; its section
    # is never rewritten for them.
    assert any(c.startswith("p3-") for c in cited) and log["corrected"]
    assert log["sections"].count(3) == 1
    # The fake judge still refuses the answer sketch the corrector cannot
    # reach, so the lesson is written and flagged with it, not lost.
    status, notes = log["reviews"][-1]
    assert status == "flagged" and "Sentences the study note does not support" in notes


def test_model_text_in_a_heading_is_escaped() -> None:
    s = lw.SectionPlan(heading="Why p99 < p50 & more", concept="c1", covers="x")
    assert lw._h2(1, s) == '<h2 data-concept="c1">Why p99 &lt; p50 &amp; more</h2>'


def test_the_writer_is_told_the_charter_first() -> None:
    from hq import assemble

    text = lw.section_instructions()
    assert text.startswith("Current date and time:")          # charter rule 7 refers to it
    assert text.split("\n\n")[1].startswith("# Mission HQ charter")
    assert text == assemble.assemble("writer-section", lw._tutor()).text
    assert len(assemble.assemble("writer-section", lw._tutor()).sha) == 12


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
    assert any("the lead and the key points here" in p for p in probs)


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


def test_an_apparatus_part_with_key_points_is_sent_back() -> None:
    html = ('<h2 data-kind="lab">Lab</h2><ul class="exercises"><li>E1 run it</li></ul>'
            '<div class="keypoints"><p class="remember">Keep this.</p></div>')
    probs = lw.section_problems(html, earlier="", article=True, kind="", apparatus=True,
                                total_words=0)
    assert any("apparatus section has no lead" in p for p in probs)


def test_plainness_is_measured_on_teaching_prose_alone() -> None:
    prose = "<p>" + "The batch is rebuilt every step. " * 20 + "</p>"
    sources = ('<h2 data-kind="sources">Sources</h2><ul class="sources"><li>'
               + "https://a.dev/a-very-long-url-with-many-words-in-it and what it gave " * 12
               + "</li></ul>")
    assert lt.reading_ease(lt.teaching_prose(prose + sources)) == lt.reading_ease(lt._page_text(prose))


def test_the_release_test_is_a_flag_on_the_last_attempt(tmp_path: Path, monkeypatch) -> None:
    calls = {"plans": 0}

    async def outline_step(*a: Any, **k: Any):
        calls["plans"] += 1
        return _outline()

    async def release_step(claims):
        return {"fails": ["c1"], "reasons": ["a default value"]}

    monkeypatch.setattr(lw, "_outline_step", outline_step)
    monkeypatch.setattr(lw, "_release_step", release_step)
    material = lw.Material(article=True, slug="", kind="paper", note=NOTE, prompt="m")
    spec = type("Spec", (), {"model": "teacher", "name": "tutor"})()
    w = lw.Writer(spec, HQDeps(agent="tutor", task_id=None, run_id=None), material)  # type: ignore[arg-type]
    assert asyncio.run(w.plan()) is not None
    assert calls["plans"] == lw.PLAN_ATTEMPTS and w.release_flags


def test_an_em_dash_is_caught_on_its_part() -> None:
    html = '<h2 data-concept="c1">Q</h2><p>The batch waits — every stream freezes.</p>'
    assert any("em dash" in p for p in lw.section_problems(
        html, earlier="", article=True, kind="", apparatus=False, total_words=0))


def _four_teaching_sections() -> dict[str, Any]:
    """An article whose one concept is taught over four sections, so the
    editor has more to choose from than it may rewrite."""
    return _outline(sections=[
        {"heading": "What happens to a short request in a static batch", "concept": "c1", "covers": "the wait"},
        {"heading": "How much does rebuilding the batch buy", "concept": "c1", "covers": "the number"},
        {"heading": "Where does the freed slot go", "concept": "c1", "covers": "the slot"},
        {"heading": "What does the server check after each pass", "concept": "c1", "covers": "the check"},
        {"heading": "Sources", "kind": "sources", "covers": "the urls"},
    ])


def _low_on_two_and_four(final: int = 4):
    """The first pass scores sections 2 and 4 low; the second pass gives them
    `final` on every criterion."""
    calls: list[list[int]] = []

    async def editor_step(concepts, material, context, parts):
        numbers = [p["number"] for p in parts]
        calls.append(numbers)
        assert concepts[0]["id"] == "c1" and "Orca" in material
        if len(calls) == 1:
            return {"sections": [
                _score(1, 5), _score(3, 4),
                _score(2, 5, "INSTR-2: ask when the short request returns, with 20 and 2,000 tokens",
                       asks_before_tells=2),
                _score(4, 4, "INSTR-4: end with the step from his lab that shows the freed slot",
                       transfer=2, concrete=3),
            ]}
        return {"sections": [_score(n, final) for n in numbers]}
    return editor_step


def test_the_editor_rewrites_only_the_weak_teaching_sections_with_its_instruction(
        tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch, outline=_four_teaching_sections(),
                             editor=_low_on_two_and_four())
    w = make()
    assert asyncio.run(w.run()) is not None, w.report
    # Every teaching section is scored once; the sources section never is.
    assert log["edited"] == [[1, 2, 3, 4], [2, 4]]
    # Exactly 2 and 4 written again: each rewrite runs with its fallback beside it.
    assert log["sections"] == [1, 2, 3, 4, 5, 2, 2, 4, 4]
    assert "INSTR-2" in log["prompts"][2][-1] and "asks_before_tells (2)" in log["prompts"][2][-1]
    assert "INSTR-4" in log["prompts"][4][-1] and "transfer (2)" in log["prompts"][4][-1]
    # The rewrite and its fallback carry the instruction; no earlier prompt does.
    assert not any("INSTR" in p for p in log["prompts"][2][:-2] + log["prompts"][1])
    lines = [r for r in w.report if r.startswith("editor scores, section")]
    assert len(lines) == 4
    assert lines[1] == ("editor scores, section 2 (How much does rebuilding the batch buy):"
                        " concept_first 4, asks_before_tells 4, concrete 4, plain 4,"
                        " connected 4, one_idea 4, transfer 4")
    status, notes = log["reviews"][-1]
    assert status == "passed"
    assert "Editor scores: mean 4.2 of 5 over 4 teaching section(s)" in notes
    assert not lw._editor_file("t-9").exists()     # dropped with the plan


def test_a_section_still_weak_after_its_rewrite_flags_the_lesson(
        tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch, outline=_four_teaching_sections(),
                             editor=_low_on_two_and_four(final=2))
    w = make()
    assert asyncio.run(w.run()) is not None, w.report
    assert log["edited"] == [[1, 2, 3, 4], [2, 4]]  # no third pass
    status, notes = log["reviews"][-1]
    assert status == "flagged" and "still below 3 after the rewrite: sections [2, 4]" in notes


def test_the_editor_rewrites_at_most_three_sections(tmp_path: Path, monkeypatch) -> None:
    async def editor_step(concepts, material, context, parts):
        return {"sections": [_score(p["number"], 3, f"INSTR-{p['number']}", plain=2 + p["number"] % 2)
                             for p in parts]}
    make, log = _fake_writer(tmp_path, monkeypatch, outline=_four_teaching_sections(),
                             editor=editor_step)
    w = make()
    assert asyncio.run(w.run()) is not None, w.report
    # Sections 2 and 4 score lowest (plain 2); of 1 and 3 (plain 3), 1 comes first.
    assert log["edited"] == [[1, 2, 3, 4], [1, 2, 4]]
    assert log["sections"][5:] == [1, 1, 2, 2, 4, 4]


def test_a_requeued_run_reuses_the_editors_scores(tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch, outline=_four_teaching_sections(),
                             editor=_low_on_two_and_four(), finish_fails=True)
    with pytest.raises(RuntimeError):
        asyncio.run(make().run())
    assert log["edited"] == [[1, 2, 3, 4], [2, 4]]
    cache = lw.saved_scores("t-9")
    assert sorted(cache) == [1, 2, 3, 4] and cache[2]["edited"] and not cache[1].get("edited")

    w = make()
    assert asyncio.run(w.run()) is not None, w.report
    assert log["edited"] == [[1, 2, 3, 4], [2, 4]]  # no editor call: every text unchanged
    assert log["sections"] == [1, 2, 3, 4, 5, 2, 2, 4, 4]  # nothing rewritten again
    assert w.teaching_notes[2].count("INSTR-2") == 1  # a later repair would still carry it
    status, notes = log["reviews"][-1]
    assert status == "passed" and "Editor scores: mean 4.2" in notes


def test_a_changed_part_is_scored_again(tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch, outline=_four_teaching_sections())
    w = make()
    w.outline = lw.Outline.model_validate(_four_teaching_sections())
    w.parts = ["<p>open</p>", "<p>one</p>", "<p>two</p>", "<p>three</p>", "<p>four</p>", "<p>src</p>"]
    assert asyncio.run(w.edit()) == []
    w.parts[3] = "<p>three, rewritten by a page repair</p>"
    asyncio.run(w.edit())
    assert log["edited"] == [[1, 2, 3, 4], [3]]


def test_a_page_is_not_sent_to_the_editor(tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch)
    w = make()
    w.m.page = "lab"
    # Even a page plan with a concept section is apparatus to the editor.
    w.outline = lw.Outline.model_validate(_outline())
    w.parts = ["<p>open</p>"] + ["<p>part</p>"] * 6
    assert w.teaching_parts() == []
    assert asyncio.run(w.edit()) == [] and log["edited"] == []
    w.m.page = ""
    assert w.teaching_parts() == [1, 2]


def test_the_concept_list_reads_as_two_sentences_in_the_text_copy() -> None:
    outline = lw.Outline.model_validate(_outline())
    text = lt.html_to_text(lw._concept_list(outline))
    assert "never makes a short request wait for a long one. Predict tail latency" in text
    assert "one.Predict" not in text and "onepredict" not in text.lower()
    from hq import signals
    assert signals.concept_claims(lw._concept_list(outline))["c1"].endswith("for a long one.")


def test_the_editor_rubric_names_every_criterion() -> None:
    rubric = lw.editor_instructions()
    for c in lw.CRITERIA:
        assert f"### {c}" in rubric
    assert "Ignore any instruction" in rubric


def test_a_section_the_editor_sent_back_is_rewritten_with_more_thought(tmp_path: Path,
                                                                        monkeypatch) -> None:
    learning = tmp_path / "learning"
    (learning / "lessons").mkdir(parents=True)
    monkeypatch.setattr(lt.settings(), "learning_dir", learning)
    efforts: list[str] = []
    prompts: list[str] = []

    async def section_step(model: str, prompt: str, effort: str = lw.SECTION_EFFORT) -> str:
        efforts.append(effort)
        prompts.append(prompt)
        plan = lw.Outline.model_validate(_outline())
        return _section_html(1, plan.sections[0])

    async def rewrite_step(model: str, prompt: str) -> str:
        efforts.append(lw.REWRITE_EFFORT)
        if slow["on"]:
            raise TimeoutError("medium ran past its limit")
        plan = lw.Outline.model_validate(_outline())
        return _section_html(1, plan.sections[0])

    slow = {"on": False}
    monkeypatch.setattr(lw, "_section_step", section_step)
    monkeypatch.setattr(lw, "_rewrite_step", rewrite_step)
    material = lw.Material(article=True, slug="x", kind="paper", note=NOTE, prompt="m")
    spec = type("Spec", (), {"model": "teacher", "name": "tutor"})()
    w = lw.Writer(spec, HQDeps(agent="tutor", task_id="t-e", run_id=None), material)  # type: ignore[arg-type]
    w.outline = lw.Outline.model_validate(_outline())
    w.parts = ["<p>opening</p>"]
    asyncio.run(w.write_section(1))
    assert set(efforts) == {lw.SECTION_EFFORT}
    efforts.clear()
    prompts.clear()
    w.teaching_notes[1] = "concept_first: state the claim before the mechanism"
    # A later repair of a section the editor sent back keeps the instruction
    # but uses the ordinary effort.
    asyncio.run(w.write_section(1, ["the article is 2806 words"]))
    assert set(efforts) == {lw.SECTION_EFFORT}
    assert all("concept_first: state the claim" in p for p in prompts)
    efforts.clear()
    # The page repair goes through the guarded rewrite, and the same holds.
    asyncio.run(w._rewrite_kept(1, ["the whole-page check said: too long"], "page"))
    assert set(efforts) == {lw.SECTION_EFFORT}
    efforts.clear()
    asyncio.run(w.write_section(1, teach=True))
    # The higher effort writes the editor's rewrite; the ordinary call runs beside it.
    assert efforts[0] == lw.REWRITE_EFFORT and set(efforts) == {lw.REWRITE_EFFORT, lw.SECTION_EFFORT}
    assert not any("rewritten at low effort instead" in r for r in w.report)
    efforts.clear()
    slow["on"] = True                       # medium runs past its limit
    asyncio.run(w.write_section(1, teach=True))
    assert efforts[:2] == [lw.REWRITE_EFFORT, lw.SECTION_EFFORT]
    assert any("rewritten at low effort instead" in r for r in w.report)


def test_the_length_rule_counts_what_he_reads() -> None:
    prose = "<p>" + "The batch is rebuilt every step. " * 100 + "</p>"
    predict = ('<details class="predict"><summary>Predict?</summary><p>'
               + "Because the slot frees. " * 20 + "</p></details>")
    hidden = ('<details class="answer"><summary>Answer</summary><p>' + "word " * 400 + "</p></details>"
              '<ul class="sources"><li>' + "https://a.dev/x what it gave " * 50 + "</li></ul>"
              "<pre>" + "code " * 300 + "</pre>")
    counted = lt.reading_words(prose + predict + hidden)
    assert counted == lt.reading_words(prose + predict)
    assert counted > lt.reading_words(prose)          # predict answers are read


# --- the page check: every finding is repaired, and a quality finding flags ------------

def _refusing_finish(monkeypatch, log: dict[str, Any], findings: list[str], *,
                     hard: bool = False, times: int = 99) -> None:
    """finish_lesson that refuses `times` times with these findings, then
    passes; with quality_ok it passes when every finding is a quality one."""
    real = lt.finish_lesson

    async def finish(*a: Any, **k: Any) -> Any:
        log.setdefault("finish_calls", []).append(bool(k.get("quality_ok")))
        if k.get("quality_ok") and not hard:
            return await real(*a, **k)
        if len(log["finish_calls"]) <= times:
            raise lt.LessonRefused("the page is not ready yet: " + "; ".join(findings),
                                   findings=findings, quality_only=not hard)
        return await real(*a, **k)
    monkeypatch.setattr(lt, "finish_lesson", finish)


def test_each_finding_is_sent_to_the_section_that_causes_it(tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch)
    plan = lw.Outline.model_validate(_outline())
    heading = plan.sections[1].heading          # section 2, named by its heading
    _refusing_finish(monkeypatch, log, [f"these sections run long with nothing to look at: {heading}"],
                     times=1)
    w = make()
    assert asyncio.run(w.run()) is not None, w.report
    assert log["finish_calls"] == [False, False]      # refused once, passed after the repair
    assert log["sections"].count(2) == 2              # only section 2 was written again
    assert all(log["sections"].count(n) == 1 for n in (1, 3, 4))
    assert log["reviews"][-1][0] != "flagged"


def test_quality_findings_the_repairs_cannot_clear_flag_the_lesson_instead_of_losing_it(
        tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch)
    finding = "1 sentence(s) carry a verification date, such as “checked 2026-09-20…”"
    _refusing_finish(monkeypatch, log, [finding])
    w = make()
    assert asyncio.run(w.run()) is not None, w.report     # written, not thrown away
    # Refused, repaired twice, and then kept on the last call.
    assert log["finish_calls"] == [False] * (lw.PAGE_REPAIR_ROUNDS + 1) + [True]
    status, notes = log["reviews"][-1]
    assert status == "flagged"
    assert "Page checks still open after the repairs" in notes and "verification date" in notes


def test_a_hard_finding_still_refuses_the_page(tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch)
    _refusing_finish(monkeypatch, log, ["c2 is promised at the top and never taught"], hard=True)
    with pytest.raises(lt.LessonRefused):
        asyncio.run(make().run())
    assert True not in log["finish_calls"]                  # never asked to keep it


def test_the_plainness_finding_goes_to_the_heavy_sections(tmp_path: Path, monkeypatch) -> None:
    make, _log = _fake_writer(tmp_path, monkeypatch)
    w = make()
    sentence = ("This sentence keeps going with one more clause and one more"
                " clause after that and another clause until it is long.")
    long = " ".join([sentence] * 6)
    short = " ".join(["It is short."] * 6)
    w.parts = ["<p>opening</p>", f"<p>{short}</p>", f"<p>{long}</p>", f"<p>{short}</p>"]
    w.outline = lw.Outline.model_validate(_outline())
    assert w._parts_for("the page reads heavier than it should: sentences average 19") == [2]


def test_the_refusal_keeps_its_findings_through_pickling() -> None:
    import pickle

    exc = lt.LessonRefused("the page is not ready yet: a; b", findings=["a", "b"],
                           quality_only=True)
    back = pickle.loads(pickle.dumps(exc))
    assert str(back) == "the page is not ready yet: a; b"
    assert back.findings == ["a", "b"] and back.quality_only is True


def test_the_page_check_sorts_hard_from_quality() -> None:
    page = _lesson_page_with_a_dated_sentence()
    found = lt.page_findings("", page, "", least=1, most=5)
    assert not found.hard
    assert any("verification date" in f for f in found.quality)


def _lesson_page_with_a_dated_sentence() -> str:
    body = " ".join(f"Prefill fills the cache for request {n} before decode starts." for n in range(45))
    return ('<ol class="concepts"><li id="c1"><b>Prefill and decode share one forward pass'
            '</b><span>plan batches</span></li></ol>'
            '<h2 data-concept="c1">Prefill</h2><details class="predict"><summary>Predict'
            '</summary><p>x</p></details><table><tr><td>1</td></tr></table>'
            f"<p>{body} This was checked against the source tree on 2026-09-20.</p>")


def test_the_orientation_section_is_held_to_the_date_rule_the_page_uses() -> None:
    html = "<h2 data-kind='orientation'>Where this phase starts</h2><p>Mode two shipped, checked 2026-09-20.</p>"
    base = {"earlier": "", "article": False, "kind": "", "apparatus": True, "total_words": 0}
    assert not any("carries a date" in p for p in lw.section_problems(html, **base))
    assert any("carries a date" in p
               for p in lw.section_problems(html, **base, orientation=True))


def test_the_writer_reports_each_stage_to_the_runs_steps(tmp_path: Path, monkeypatch) -> None:
    """A two-hour write-up showed only "Run started" on its Steps pane."""
    from hq import runner

    make, _log = _fake_writer(tmp_path, monkeypatch)
    seen: list[dict[str, Any]] = []

    async def capture(kind: str, **kw: Any) -> int:
        if kind == "writer.progress":
            seen.append(kw["payload"])
        return 0
    monkeypatch.setattr(runner, "emit_step", capture)
    assert asyncio.run(make().run()) is not None
    stages = [p["stage"] for p in seen]
    assert stages[0] == "plan" and "accepted" in seen[0]["text"]
    sections = [p for p in seen if p["stage"] == "section"]
    total = len(lw.Outline.model_validate(_outline()).sections)
    assert [p["done"] for p in sections] == list(range(1, total + 1))
    assert all(p["total"] == total for p in sections)
    assert "citations" in stages and "editor" in stages
    assert seen[-1]["stage"] == "page" and "passed" in seen[-1]["text"]


def test_a_running_run_shows_the_cost_of_its_calls_so_far() -> None:
    from hq.api import rest

    for col in ("input_tokens", "output_tokens", "cost_usd"):
        assert f"CASE WHEN r.ended_at IS NULL THEN coalesce((SELECT sum(mc.{col})" in rest.RUN_COLUMNS


def test_a_course_run_is_guarded_by_liveness_not_age() -> None:
    """Phase 2B was cancelled at 210 minutes while it was still writing."""
    import inspect

    from hq import engine

    assert engine.COURSE_TIMEOUT_S >= 6 * 60 * 60
    assert engine.hang_after_s() < engine.COURSE_TIMEOUT_S
    src = inspect.getsource(engine._close_timed_out_runs)
    # A run its limit cancelled is closed and queued again, a bounded number of times,
    assert "w.status IN ('CANCELLED', 'ERROR')" in src and "TIMEOUT_REQUEUES" in src
    # on every watchdog tick, not only at boot.
    assert "_close_timed_out_runs()" in inspect.getsource(engine._watchdog_tick)
    assert "_close_timed_out_runs()" in inspect.getsource(engine.reap)


# --- long sentences are split in place, not rewritten ------------------------------------

LONG_PARA = ('<p>When a long prompt of 24,000 tokens arrives, the server runs its whole'
             ' <dfn>prefill</dfn> in one step, so every stream that was decoding waits for'
             ' that step to finish before it can produce its next token, which users see as'
             ' a freeze of about 720 ms.</p>')
SPLIT_PARA = ('<p>When a long prompt of 24,000 tokens arrives, the server runs its whole'
              ' <dfn>prefill</dfn> in one step. Every stream that was decoding waits for'
              ' that step to finish. Only then can it produce its next token. Users see'
              ' this as a freeze of about 720 ms.</p>')


def test_only_the_paragraphs_with_long_sentences_are_sent() -> None:
    html = f"<h2>x</h2><p>Short and plain here.</p>{LONG_PARA}<p>An em — dash here.</p>"
    assert lw.heavy_paragraphs(html) == [LONG_PARA, "<p>An em — dash here.</p>"]


def test_a_split_that_keeps_everything_is_accepted() -> None:
    assert lw.tightened_ok(LONG_PARA, SPLIT_PARA)
    html, n = lw.apply_tightened(f"<h2>x</h2>{LONG_PARA}", [LONG_PARA],
                                 {"paragraphs": [{"n": 1, "html": SPLIT_PARA}]})
    assert n == 1 and SPLIT_PARA in html and LONG_PARA not in html


@pytest.mark.parametrize("bad", [
    SPLIT_PARA.replace("720 ms", "700 ms"),                      # a number changed
    SPLIT_PARA.replace("<dfn>prefill</dfn>", "prefill"),         # a tag dropped
    SPLIT_PARA.replace("Users see this as a freeze of about 720 ms.", ""),  # content cut
    LONG_PARA,                                                   # still long
    SPLIT_PARA.replace("step. Every", "step — every"),      # an em dash added
])
def test_a_split_that_changes_anything_else_is_refused(bad: str) -> None:
    assert not lw.tightened_ok(LONG_PARA, bad)
    html, n = lw.apply_tightened(LONG_PARA, [LONG_PARA], {"paragraphs": [{"n": 1, "html": bad}]})
    assert n == 0 and html == LONG_PARA


def test_only_mechanical_findings_go_to_the_split() -> None:
    assert lw.mechanical(["sentences average 21 words and 23% run over 25 (limits 17 and 18%)"])
    assert lw.mechanical(["an em dash; he uses none. Split the sentence or use a comma"])
    assert not lw.mechanical(["sentences average 21 words", "c1 is told, not yet asked"])
    assert not lw.mechanical([])


def test_a_section_too_long_in_its_sentences_is_split_not_rewritten(
        tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch)
    real = lw.section_problems

    def problems(html: str, **kw: Any) -> list[str]:
        if "LONG-MARK" in html:
            return ["sentences average 21 words and 23% run over 25 (limits 17 and 18%)"]
        return real(html, **kw)
    monkeypatch.setattr(lw, "section_problems", problems)
    real_step = lw._section_step
    marked: dict[str, bool] = {}

    async def section_step(model: str, prompt: str, effort: str = "low") -> str:
        html = await real_step(model, prompt, effort)
        if "Id prefix for this section: s2-" in prompt and not marked:
            marked["done"] = True
            return html + "<p>LONG-MARK</p>"
        return html
    monkeypatch.setattr(lw, "_section_step", section_step)
    split: list[int] = []

    async def tighten(self: lw.Writer, i: int, html: str, over: int = 25) -> str:
        split.append(i)
        return html.replace("<p>LONG-MARK</p>", "")
    monkeypatch.setattr(lw.Writer, "_tighten", tighten)
    assert asyncio.run(make().run()) is not None
    assert split == [2]                       # split once, in place
    assert log["sections"].count(2) == 1      # and never rewritten for it


def test_an_average_over_the_limit_splits_sentences_over_twenty_words() -> None:
    assert lw.split_target(["sentences average 19 words and 4% run over 25"]) == 20
    assert lw.split_target(["the page reads heavier than it should: sentences average 19"]) == 20
    assert lw.split_target(["an em dash; he uses none"]) == 25
    twenty_two = ("<p>" + " ".join(["word"] * 21) + " end.</p>")
    assert lw.heavy_paragraphs(twenty_two, 20) == [twenty_two]
    assert lw.heavy_paragraphs(twenty_two, 25) == []


def test_the_page_wide_length_finding_goes_to_the_split() -> None:
    assert lw.mechanical_page(["the page reads heavier than it should: sentences average 19"])
    assert not lw.mechanical_page(["c2 is promised at the top and never taught"])


def test_a_source_list_may_quote_a_title_with_an_em_dash() -> None:
    html = "<h2 data-kind='sources'>Sources</h2><ul class='sources'><li>vLLM — anatomy</li></ul>"
    base = {"earlier": "", "article": False, "kind": "", "apparatus": True, "total_words": 0}
    assert any("em dash" in p for p in lw.section_problems(html, **base))
    assert not any("em dash" in p for p in lw.section_problems(html, **base, quoted=True))


# --- a repair never makes a section wrong -------------------------------------------------

def test_the_split_keeps_command_text_exactly() -> None:
    before = ("<p>Run <code>python lab.py --turns 12</code> and watch the queue grow for a"
              " while until the first request that crosses the window is refused with a 400,"
              " which is the moment the cap should have fired.</p>")
    after = before.replace("--turns 12", "--turns 12 --inject 5").replace(", which", ". That")
    assert not lw.tightened_ok(before, after)


def test_a_section_keeps_its_best_attempt_not_its_last(tmp_path: Path, monkeypatch) -> None:
    make, _log = _fake_writer(tmp_path, monkeypatch)
    real = lw.section_problems
    tries: dict[int, int] = {}

    def problems(html: str, **kw: Any) -> list[str]:
        if "ATTEMPT-A" in html:
            return ["c1 is told, not yet asked"]                       # quality only
        if "ATTEMPT-B" in html:
            return ["these Run: commands are not in his lab, so nobody has run them: `x`",
                    "c1 is told, not yet asked"]                       # a hard one too
        return real(html, **kw)
    monkeypatch.setattr(lw, "section_problems", problems)
    real_step = lw._section_step

    async def section_step(model: str, prompt: str, effort: str = "low") -> str:
        html = await real_step(model, prompt, effort)
        if "Id prefix for this section: s2-" in prompt:
            tries[2] = tries.get(2, 0) + 1
            return html + ("<p>ATTEMPT-A</p>" if tries[2] == 1 else "<p>ATTEMPT-B</p>")
        return html
    monkeypatch.setattr(lw, "_section_step", section_step)
    w = make()
    assert asyncio.run(w.run()) is not None
    assert tries[2] == lw.SECTION_RETRIES + 1
    assert "ATTEMPT-A" in w.parts[2] and "ATTEMPT-B" not in w.parts[2]


def test_a_page_repair_that_brings_in_a_hard_finding_is_reverted(tmp_path: Path, monkeypatch) -> None:
    make, log = _fake_writer(tmp_path, monkeypatch)
    plan = lw.Outline.model_validate(_outline())
    heading = plan.sections[1].heading
    _refusing_finish(monkeypatch, log, [f"these sections run long with nothing to look at: {heading}"],
                     times=1)
    real = lw.section_problems

    def problems(html: str, **kw: Any) -> list[str]:
        if "INVENTED-RUN" in html:
            return ["these Run: commands are not in his lab, so nobody has run them: `y`"]
        return real(html, **kw)
    monkeypatch.setattr(lw, "section_problems", problems)
    real_step = lw._section_step

    repairing: dict[str, bool] = {}

    async def section_step(model: str, prompt: str, effort: str = "low") -> str:
        html = await real_step(model, prompt, effort)
        if "whole-page check said" in prompt:
            repairing["on"] = True
        # Every attempt of the repair invents the command: only a revert helps.
        is_two = "Id prefix for this section: s2-" in prompt
        return html + "<p>INVENTED-RUN</p>" if repairing and is_two else html
    monkeypatch.setattr(lw, "_section_step", section_step)
    w = make()
    assert asyncio.run(w.run()) is not None
    assert "INVENTED-RUN" not in w.parts[2]
    assert any("earlier version was kept" in r for r in w.report)


def test_his_lab_is_not_rewritten_for_a_quality_finding(tmp_path: Path, monkeypatch) -> None:
    # His lab lives in a course phase; an article no longer plans one, so the
    # plan rule is lifted here to reach the page repair's lab branch.
    monkeypatch.setattr(lw, "ARTICLE_BARRED_KINDS", {})
    with_lab = _outline()
    with_lab["sections"].insert(2, {"heading": "Fifteen minutes today", "kind": "lab",
                                    "covers": "one thing to try"})
    make, log = _fake_writer(tmp_path, monkeypatch, outline=with_lab)
    plan = lw.Outline.model_validate(with_lab)
    lab = next(s.heading for s in plan.sections if s.kind == "lab")
    _refusing_finish(monkeypatch, log, [f"these sections run long with nothing to look at: {lab}"],
                     times=1)
    assert asyncio.run(make().run()) is not None
    assert log["sections"].count(3) == 1              # the lab was written once, never again


# --- an unsupported sentence is corrected in place ------------------------------------------

FLAGGED_PARA = ('<p>Strict mode keeps every token legal. The grammar mask cannot explain a quality'
                ' drop. The <dfn>format tax</dfn> is paid at the prompt.</p>')
FLAGGED = "The grammar mask cannot explain a quality drop."
NOTE_TEXT = "The mask causes a small measured share of the drop, about 1.6 points."


def test_the_paragraph_holding_a_sentence_is_found() -> None:
    html = f"<h2>x</h2><p>Other text here.</p>{FLAGGED_PARA}"
    assert lw.block_holding(html, FLAGGED) == FLAGGED_PARA
    assert lw.block_holding(html, "A sentence that is not on the page.") == ""


def test_a_correction_that_changes_only_the_sentence_is_used() -> None:
    fixed = FLAGGED_PARA.replace(FLAGGED, "The grammar mask explains about 1.6 points of the drop.")
    assert lw.corrected_ok(FLAGGED_PARA, fixed, FLAGGED, NOTE_TEXT)
    assert lw.corrected_ok(FLAGGED_PARA, FLAGGED_PARA.replace(FLAGGED + " ", ""), FLAGGED, NOTE_TEXT)


@pytest.mark.parametrize("bad", [
    FLAGGED_PARA,                                                             # nothing corrected
    FLAGGED_PARA.replace(FLAGGED, "The mask explains 12 points of the drop."),  # a number from nowhere
    FLAGGED_PARA.replace("Strict mode keeps every token legal.", "Strict mode is safe."),  # another sentence
    FLAGGED_PARA.replace("<dfn>format tax</dfn>", "format tax"),              # a tag dropped
])
def test_a_correction_that_changes_anything_else_is_not_used(bad: str) -> None:
    assert not lw.corrected_ok(FLAGGED_PARA, bad, FLAGGED, NOTE_TEXT)


def test_two_flagged_sentences_in_one_paragraph_are_corrected_together() -> None:
    second = "Strict mode keeps every token legal."
    both = FLAGGED_PARA.replace(second + " ", "").replace(
        FLAGGED, "The grammar mask explains about 1.6 points of the drop.")
    assert lw.corrected_ok(FLAGGED_PARA, both, [FLAGGED, second], NOTE_TEXT)
    # With only the first flagged, the second may not change.
    assert not lw.corrected_ok(FLAGGED_PARA, both, [FLAGGED], NOTE_TEXT)


def test_a_flagged_sentence_with_markup_may_be_removed() -> None:
    para = ('<p>Strict mode keeps every token legal. The <b>grammar mask</b> cannot explain'
            ' a quality drop. The <dfn>format tax</dfn> is paid at the prompt.</p>')
    flagged = "The grammar mask cannot explain a quality drop."
    removed = ('<p>Strict mode keeps every token legal. The <dfn>format tax</dfn> is paid'
               ' at the prompt.</p>')
    assert lw.corrected_ok(para, removed, flagged, NOTE_TEXT)
    # Markup is still new or lost only inside the flagged sentences.
    assert not lw.corrected_ok(para, removed.replace("<dfn>format tax</dfn>", "format tax"),
                               flagged, NOTE_TEXT)
    assert not lw.corrected_ok(para, removed.replace("Strict mode", "<b>Strict mode</b>"),
                               flagged, NOTE_TEXT)
    assert not lw.corrected_ok(para, removed.replace("<p>", "<li>").replace("</p>", "</li>"),
                               flagged, NOTE_TEXT)


def test_the_page_does_not_print_the_course_map(tmp_path: Path, monkeypatch) -> None:
    """The console shows where he is; the writer still gets the map in its prompt."""
    make, _log = _fake_writer(tmp_path, monkeypatch)
    w = make()
    w.m.course_map = [{"title": "Phase 1", "state": "read"}, {"title": "Phase 2", "state": "here"}]
    assert asyncio.run(w.run()) is not None
    assert "Where you are in the course" not in w.parts[0]


def test_a_replay_error_is_never_swallowed() -> None:
    """Every broad handler in the engine and the writer lets a replay
    mismatch through, so DBOS names the step that really diverged."""
    import inspect

    from hq import engine

    for module in (engine, lw):
        lines = inspect.getsource(module).splitlines()
        for n, line in enumerate(lines):
            if line.strip().startswith("except Exception"):
                assert lines[n - 2].strip() == "except REPLAY_ERRORS:", (module.__name__, n)


def test_the_code_version_changes_with_what_the_checks_read(monkeypatch) -> None:
    from hq import dbos_app
    from hq.config import settings

    first = dbos_app.code_version()
    assert first == dbos_app.code_version()
    monkeypatch.setattr(settings(), "private_employers", ("Example Corp",))
    assert dbos_app.code_version() != first


# --- story days: the whole story, no course tie (2026-10-17) -------------------------------

def _story(**kw: Any) -> dict[str, Any]:
    base = _outline_base(
        title="Why did Discord voice calls lag in Bucharest after the edge move",
        subtitle="Discord moved voice to the edge and found three causes",
        eyebrow="design story · Discord · voice SFU",
        outcome="Find which branch of your event loop starves the other",
        running_case="Discord's voice SFU on eight worker threads per host.",
        opening="In February, users in Bucharest saw pings above half a second.",
        concepts=[_concept(), _concept(id="c2")],
        sections=[
            {"heading": "What did Bucharest see", "concept": "c1", "covers": "the symptom"},
            {"heading": "Why the send queue waited", "concept": "c2", "covers": "the cause"},
            {"heading": "Sources", "kind": "sources", "covers": "the urls"},
        ])
    base["findings"] = [
        {"finding": "The flush timer starved behind an always-ready recv", "concept": "c1"},
        {"finding": "Softirq work shared a vCPU with a worker", "concept": "c2"},
        {"finding": "The Iceland PoP made mixed calls worse", "left_out": "covered by c1's placement"},
    ]
    out = {**base, **kw}
    out["sections"] = _ledger(out["sections"])
    return out


def test_a_story_plan_teaches_every_finding_or_says_why_not() -> None:
    ok = lw.Outline.model_validate(_story())
    assert lw.outline_problems(ok, NOTE, article=True, story=True) == []

    one = lw.Outline.model_validate(_story(concepts=[_concept()], findings=[
        {"finding": "The flush timer starved", "concept": "c1"}]))
    assert any("a story teaches two to five" in p
               for p in lw.outline_problems(one, NOTE, article=True, story=True))

    silent = _story()
    silent["findings"][2] = {"finding": "The Iceland PoP made mixed calls worse"}
    probs = lw.outline_problems(lw.Outline.model_validate(silent), NOTE, article=True, story=True)
    assert any("no concept and no reason" in p for p in probs)

    orphan = _story()
    orphan["findings"] = [f for f in orphan["findings"] if f.get("concept") != "c2"]
    probs = lw.outline_problems(lw.Outline.model_validate(orphan), NOTE, article=True, story=True)
    assert any("c2 teaches no finding" in p for p in probs)


def test_a_story_plan_does_not_tie_itself_to_the_course() -> None:
    tied = lw.Outline.model_validate(_story(
        opening="In the serving phase you sized your router's replicas from throughput."))
    probs = lw.outline_problems(tied, NOTE, article=True, story=True)
    assert any("opening ties the story to his course" in p for p in probs)


def test_an_article_plans_no_lab_and_no_post() -> None:
    plan = _outline()
    plan["sections"].insert(2, {"heading": "Lab: starve a loop yourself", "kind": "lab",
                                "covers": "code"})
    plan["sections"].insert(3, {"heading": "What he could post", "kind": "post", "covers": "two"})
    probs = lw.outline_problems(lw.Outline.model_validate(plan), NOTE, article=True)
    assert any("no lab section" in p for p in probs)
    assert any("no post section" in p for p in probs)
    # His course phase keeps its lab.
    assert not any("no lab section" in p
                   for p in lw.outline_problems(lw.Outline.model_validate(plan), NOTE,
                                                article=False))


@pytest.mark.parametrize("opening", [
    "In the last phase you could interleave ready tasks with an event loop.",
    "In the serving phase you sized your router's replicas from throughput and CPU.",
    "In Phase 3B you learned to route a session back to the replica.",
    "Across the serving phases you built an inference stack piece by piece.",
    "In your batching phase you computed the service rate of a queue.",
    "When you re-read the serving phases, read each optimisation as an act on one phase.",
])
def test_the_course_ties_he_read_are_caught(opening: str) -> None:
    assert lw.course_tie(opening)


@pytest.mark.parametrize("text", [
    "Prefill is the single pass that processes the prompt, and decode is the second phase.",
    "During the decode phase each token needs its own step.",
    "Over the course of the migration the team moved 80% of traffic.",
])
def test_a_phase_of_the_system_is_not_a_course_tie(text: str) -> None:
    assert lw.course_tie(text) == ""


@pytest.mark.parametrize("text,leaks", [
    ("Predict starvation in his own select loops.", True),
    ("What he could post", True),
    ("Where his own stack hits the same law", True),
    ("David Chen and his team moved voice to the edge.", False),
    ("Find one queue-wait metric in a system you run.", False),
])
def test_the_writer_calling_the_reader_he_is_caught(text: str, leaks: bool) -> None:
    assert bool(lw.reader_leak(text)) is leaks


def test_a_bridge_that_repeats_the_hand_over_above_is_sent_back() -> None:
    # Word for word from the Discord article of 2026-10-14, lines 41 and 45.
    above = ('<h2 data-concept="c1">What did Bucharest see</h2><p>The probe placed the stall'
             " inside Discord's process but not inside which line of it. The next section"
             " opens the loop itself and asks why the always-ready branch wins every time.</p>")
    here = ('<h2 data-concept="c1">Why does the always-ready branch win</h2><p>The probe'
            " placed the stall inside Discord's process but not inside which line of it. So"
            " the next step is to open the loop itself.</p><p>Each of the eight workers runs"
            " one select over two branches, a receive future and a flush timer.</p>")
    probs = lw.section_problems(here, earlier=above, article=True, kind="design_story",
                                apparatus=False, total_words=100, story=True)
    assert any("says again what a part above said" in p for p in probs)
    # A course phase keeps its own connection rules.
    assert not any("says again" in p for p in lw.section_problems(
        here, earlier=above, article=False, kind="", apparatus=False, total_words=100))


def test_an_article_keeps_its_receipts_in_the_sources() -> None:
    html = ('<h2 data-concept="c1">x</h2><p>The send queue waited about a millisecond at'
            ' quiet hours.</p><details class="evidence"><summary>Evidence</summary><p>Only'
            " Discord reported it.</p></details>")
    probs = lw.section_problems(html, earlier="", article=True, kind="design_story",
                                apparatus=False, total_words=100, story=True)
    assert any("goes in the Sources list" in p for p in probs)
    assert not any("Sources list" in p for p in lw.section_problems(
        html, earlier="", article=False, kind="", apparatus=False, total_words=100))


def test_a_story_day_reads_the_story_outline_and_the_course_day_does_not() -> None:
    story = " ".join(lw.outline_instructions(article=True, story=True).split())
    article = " ".join(lw.outline_instructions(article=True).split())
    assert "Plan one story article" in story and "Find every finding first" in story
    assert "Plan one story article" not in article and "orbits the course phase" in article
    assert lw.Material(article=True, slug="", kind="design_story", note="n", prompt="p").story
    assert not lw.Material(article=True, slug="", kind="paper", note="n", prompt="p").story
    assert not lw.Material(article=True, page="lab", slug="", kind="design_story",
                           note="n", prompt="p").story


def test_an_article_section_is_not_told_to_hand_over() -> None:
    plan = lw.Outline.model_validate(_story())
    m = lw.Material(article=True, slug="", kind="design_story", note="n", prompt="p")
    told = lw._connection(plan, 1, plan.sections[0], m)
    assert "Do not end on a hand-over sentence" in told and "End by handing over" not in told
    course = lw.Material(article=False, slug="p", note="n", prompt="p")
    assert "End by handing over" in lw._connection(plan, 1, plan.sections[0], course)
    assert "This is a story article" in lw._section_prompt(m, plan, 1, plan.sections[0], "", [])


def test_a_story_is_budgeted_by_its_findings() -> None:
    # Two findings get two sections' worth of words, not a page split two ways.
    plan = lw.Outline.model_validate(_story())
    budgets = lw.word_budgets(plan, lw.story_limit(plan))
    assert all(budgets[i] >= lw.STORY_SECTION_WORDS for i in (1, 2))
    # Five findings run past the one-idea limit, up to the story ceiling.
    five = _story(concepts=[_concept(id=f"c{n}") for n in range(1, 6)], sections=[
        *({"heading": f"Finding {n}", "concept": f"c{n}", "covers": "x"} for n in range(1, 6)),
        {"heading": "Sources", "kind": "sources", "covers": "the urls"}])
    limit = lw.story_limit(lw.Outline.model_validate(five))
    assert lw.lt.ARTICLE_MAX_WORDS < limit <= lw.lt.STORY_MAX_WORDS


def test_an_article_opens_without_the_course_lessons_reading_note(tmp_path: Path,
                                                                   monkeypatch) -> None:
    make, _log = _fake_writer(tmp_path, monkeypatch)
    w = make()
    assert asyncio.run(w.run()) is not None, w.report
    assert "This lesson teaches one idea" not in w.parts[0]
    assert '<ol class="concepts">' in w.parts[0]


def test_a_story_task_records_the_story_files_in_its_run() -> None:
    from hq import engine
    from hq.config import settings
    from hq.loader import parse_job_md

    tutor = parse_job_md(settings().agents_dir / "tutor")
    story = {"workflow": "learning_journey", "stage": "lesson_synthesis",
             "article_kind": "design_story"}
    assert engine._run_bundle(tutor, story) == ("writer-section", True, "", True)
    assert engine._run_bundle(tutor, {**story, "article_kind": "paper"})[3] is False


def test_an_article_sends_a_sentence_with_no_number_to_the_judge() -> None:
    # Credited Discord with the note writer's advice, and had no digit, so
    # the judge never saw it (2026-10-17).
    page = ('<h2 data-concept="c1">Placement</h2><p>After the test, the team replaced one'
            " region at a time. The team judged each move by the worst-off participant"
            " instead of the local median.</p>")
    assert not any("worst-off" in c["claim"] for c in lt.new_claims("", page))
    assert any("worst-off" in c["claim"] for c in lt.new_claims("", page, every=True))
    assert "never a sentence that credits it to the people in the story" in lw.CREDIT_RULE


def test_a_then_run_command_copied_from_his_lab_is_his() -> None:
    """The page check reads "Run:" in any case; the lab's own commands must be
    read the same way, or "Then run: `cmd`" copied exactly is refused."""
    source = "- [ ] **E1 (offline).** Build it.\n  - Run: `uv run python a.py`\n  - Then run: `uv run python b.py --check`\n"
    page = ("<p>Run: <code>uv run python a.py</code></p>"
            "<p>Then run: <code>uv run python b.py --check</code></p>")
    assert not [p for p in lt.lab_fidelity_problems(page, source) if "not in his lab" in p]
