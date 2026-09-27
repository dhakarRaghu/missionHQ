"""A course is one line of thought: what each lesson is given about the
lessons before it, and the order of terms checked before a word is written.

He could follow the lessons written before the staged writer and not the
ones after it. Measured on the pages, the later ones used a term long before
explaining it, never explained a term an earlier phase had defined, opened
every phase on a new situation and handed over to nothing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from hq import lesson_writer as lw
from hq.tools.registry import HQDeps

PAGE = """<!doctype html><html><body><main>
<p>Your support agent answers in two seconds when you test it alone, and the same
prompt takes six seconds at three in the afternoon.</p>
<p>Nothing in your own logs explains the difference, because the cause sits inside
the server that runs the model.</p>
<ol class="concepts"><li id="c1"><b>One pass serves every request in the batch.</b>
<span>Predict latency under load.</span></li></ol>
<h2 data-concept="c1">What does the server do between your requests?</h2>
<p><dfn>Prefill</dfn> is the pass that reads your whole prompt and produces the first
token, so its cost grows with the length of the prompt.</p>
<p>A forward pass is one run of the model over a set of tokens.</p>
<p>The fix is a shorter prompt. They are a third class of token, and that is all.</p>
<p>Every forward pass costs time. A forward pass that carries a long prompt costs
more, so the scheduler limits each forward pass. One forward pass serves the whole
batch, and the next forward pass starts when it ends.</p>
<h3>Continuous batching is the current way</h3>
<pre class="ascii">prefill is not a term here</pre>
<div class="keypoints"><p class="remember">One pass, every request.</p></div>
<p>The loop now explains the slow afternoon, but it does not explain why one long
prompt freezes the streams that were already running.</p>
<h2 data-kind="lab">The lab</h2>
<p>Run the simulator with sixty requests and read the worst gap it prints out.</p>
</main></body></html>"""


def test_a_lesson_is_remembered_by_its_situation_its_terms_and_its_ending() -> None:
    m = lw.phase_memory(PAGE, slug="p1", title="Phase 1")
    assert m.situation.startswith("Your support agent answers in two seconds")
    assert "Prefill" in m.terms and "reads your whole prompt" in m.terms["Prefill"]
    # A definition sentence counts where the term was not marked, when the
    # lesson goes on using the term. A sentence of the same form about an
    # ordinary word, a pronoun or a heading defines nothing.
    assert "forward pass" in m.terms and m.terms["forward pass"].startswith("A forward pass is")
    assert set(m.terms) == {"Prefill", "forward pass"}
    # The last teaching paragraph, not the lab's and not a key point.
    assert m.ended.startswith("The loop now explains the slow afternoon")


def test_the_course_so_far_names_each_phase_and_keeps_the_nearest_when_short() -> None:
    near = lw.PhaseMemory(slug="p2", title="Phase 2", situation="s" * 300,
                          terms={"KV cache": "the keys and values the GPU keeps"}, ended="e")
    far = lw.PhaseMemory(slug="p1", title="Phase 1", situation="x" * (lw.MEMORY_CHARS + 50))
    block = lw.memory_block([far, near])
    assert "### Phase 2" in block and "- KV cache: the keys and values" in block
    assert "### Phase 1" not in block          # no room left, and the nearest phase won
    assert lw.memory_block([]) == ""
    assert lw.known_terms([near, near]) == ["KV cache"]


def _plan(sections: list[dict[str, Any]], **kw: Any) -> lw.Outline:
    concept = {"id": "c1", "claim": "One pass serves every request in the batch at once",
               "lets_him": "predict latency", "wrong_belief": "b", "predict": "What happens?",
               "evidence": "e", "evidence_quote": "q", "picture": "p"}
    return lw.Outline.model_validate({
        "title": "T", "subtitle": "S", "eyebrow": "E", "outcome": "O", "opening": "Op",
        "running_case": "A support agent that slows down every afternoon.",
        "concepts": [concept], "sections": sections, **kw})


def test_a_term_used_before_it_is_introduced_is_sent_back() -> None:
    good = _plan([
        {"heading": "What is one pass", "concept": "c1", "covers": "c", "introduces": ["prefill"]},
        {"heading": "Who waits", "concept": "c1", "covers": "c", "assumes": ["Prefill"],
         "bridge": "One pass is known; who pays for a long one is not.",
         "introduces": ["token budgets"]},
        {"heading": "Sources", "kind": "sources", "covers": "urls"},
    ])
    assert lw.ledger_problems(good) == []

    early = good.model_copy(deep=True)
    early.sections[0].assumes = ["token budget"]      # defined one section later
    found = lw.ledger_problems(early)
    assert len(found) == 1 and "'token budget'" in found[0] and "no section above" in found[0]


def test_a_term_from_an_earlier_phase_is_explained_again() -> None:
    plan = _plan([
        {"heading": "What is one pass", "concept": "c1", "covers": "c", "assumes": ["KV cache"]},
    ])
    found = lw.ledger_problems(plan, known=["KV cache"])
    assert len(found) == 1 and "explained again" in found[0]
    plan.sections[0].introduces = ["KV cache"]
    assert lw.ledger_problems(plan, known=["KV cache"]) == []


def test_a_section_needs_a_bridge_and_at_most_three_new_terms() -> None:
    plan = _plan([
        {"heading": "One", "concept": "c1", "covers": "c", "introduces": ["a1", "b1", "c1", "d1"]},
        {"heading": "Two", "concept": "c1", "covers": "c", "assumes": ["a1"]},
    ], running_case="")
    found = " | ".join(lw.ledger_problems(plan))
    assert "running_case is empty" in found
    assert "introduces 4 terms" in found and "keep every term" in found
    assert "'Two' has no bridge" in found
    # A plan with no ledger at all is asked for one, once.
    bare = _plan([{"heading": "One", "concept": "c1", "covers": "c"}])
    found = lw.ledger_problems(bare)
    assert len(found) == 1 and found[0].startswith("no section carries its ledger")


def test_a_section_must_define_what_the_plan_says_it_introduces() -> None:
    plan = lw.SectionPlan(heading="Who waits", concept="c1", covers="c",
                          introduces=["token budget"])
    body = "<p>The server spends a token budget on every pass, shared by all requests.</p>"
    found = lw.connection_problems(body, plan)
    assert len(found) == 1 and "<dfn>token budget</dfn>" in found[0] and "uses it" in found[0]
    marked = body.replace("token budget", "<dfn>token budget</dfn>")
    assert lw.connection_problems(marked, plan) == []
    # Apparatus teaches no term of its own.
    lab = lw.SectionPlan(heading="Lab", kind="lab", covers="c", introduces=["token budget"])
    assert lw.connection_problems(body, lab) == []


def test_prose_cut_into_very_short_sentences_is_sent_back_with_every_fact_kept() -> None:
    plan = lw.SectionPlan(heading="Who waits", concept="c1", covers="c")
    choppy = "".join(f"<p>The names differ. The steps match. Request {i} waits for the pass"
                     " that serves every request in the batch.</p>" for i in range(5))
    found = lw.connection_problems(choppy, plan)
    assert len(found) == 1 and "because, so or but" in found[0] and "Keep every fact" in found[0]
    joined = "".join(f"<p>The names differ but the steps match, so request {i} waits for the"
                     " pass that serves every request in the batch.</p>" for i in range(15))
    assert lw.connection_problems(joined, plan) == []


def test_a_section_is_told_what_it_follows_and_what_follows_it() -> None:
    plan = _plan([
        {"heading": "What is one pass", "concept": "c1", "covers": "c", "introduces": ["prefill"]},
        {"heading": "Who waits", "concept": "c1", "covers": "c", "assumes": ["prefill", "KV cache"],
         "bridge": "One pass is known; who pays for a long one is not."},
        {"heading": "What you can do now", "kind": "recall", "covers": "c"},
    ], hands_over="You can explain a slow afternoon. Next: why one prompt freezes a stream.")
    m = lw.Material(article=False, slug="p2", note="n", prompt="p", known_terms=["KV cache"],
                    memory="## The course so far\n\n### Phase 1\nIts situation: slow afternoons")
    first = lw._section_prompt(m, plan, 1, plan.sections[0], "", [])
    assert "first teaching section: open from the running case" in first
    assert "The next section answers: Who waits" in first
    assert "## The course so far" in first and "A support agent that slows down" in first
    second = lw._section_prompt(m, plan, 2, plan.sections[1], "<p>above</p>", [])
    assert "The bridge from the section above: One pass is known" in second
    assert "Explain again in one clause, because an earlier phase defined them: KV cache" in second
    assert "last teaching section" in second and "why one prompt freezes a stream" in second
    recall = lw._section_prompt(m, plan, 3, plan.sections[2], "", [])
    assert "The hand-over this section ends on" in recall


def test_the_course_map_marks_where_he_is_and_drops_a_split_parent() -> None:
    rows = [{"slug": "c-phase-01-life", "title": "Phase 1"},
            {"slug": "c-phase-02-internals", "title": "Phase 2 (whole)"},
            {"slug": "c-phase-02a-sched", "title": "Phase 2A"},
            {"slug": "c-phase-02b-decode", "title": "Phase 2B"}]
    kept = lw._without_split_parents(rows)
    assert [r["slug"] for r in kept] == ["c-phase-01-life", "c-phase-02a-sched", "c-phase-02b-decode"]
    phases = lw.course_map(kept, "c-phase-02a-sched")
    assert [p["state"] for p in phases] == ["read", "here", "later"]
    html = lw._map_html(phases)
    assert "<b>Phase 2A</b> (you are here)" in html and "Phase 2B (comes later)" in html
    assert lw._map_html(phases[:1]) == ""
    text = lw._sequence_text(kept, "c-phase-02a-sched")
    assert "explained again" in text and "known to him" not in text


def test_a_plan_is_never_lost_over_the_order_of_its_terms(monkeypatch) -> None:
    """The order is sent back like any finding; on the last try the plan is
    kept and the doubt is reported, so a phase is not lost to it."""
    calls: list[list[str]] = []
    plan = _plan([{"heading": "One", "concept": "c1", "covers": "c", "assumes": ["missing term"]},
                  {"heading": "Check", "kind": "checkpoint", "covers": "c"},
                  {"heading": "Sheet", "kind": "cheatsheet", "covers": "c"},
                  {"heading": "Sources", "kind": "sources", "covers": "c"}]).model_dump()
    plan["concepts"] = [dict(plan["concepts"][0], id=f"c{i}", evidence_quote="the note says this")
                        for i in (1, 2, 3)]
    plan["sections"][:1] = [dict(plan["sections"][0], heading=f"S{i}", concept=f"c{i}")
                            for i in (1, 2, 3)]
    for s in plan["sections"][1:3]:
        s["bridge"] = "what the one above left open"

    async def outline_step(model, article, material, problems, page="", previous=None):
        calls.append(list(problems))
        return plan

    async def release_step(claims):
        return {"fails": [], "reasons": []}

    monkeypatch.setattr(lw, "_outline_step", outline_step)
    monkeypatch.setattr(lw, "_release_step", release_step)
    material = lw.Material(article=False, slug="p", note="the note says this", prompt="m")
    spec = type("Spec", (), {"model": "teacher", "name": "tutor"})()
    w = lw.Writer(spec, HQDeps(agent="tutor", task_id=None, run_id=None), material)  # type: ignore[arg-type]
    assert asyncio.run(w.plan()) is not None
    assert len(calls) == lw.PLAN_ATTEMPTS
    assert calls[1] and "'missing term'" in calls[1][0]
    assert any(r.startswith("order of terms, kept with doubts") for r in w.report)


def test_the_opening_shows_where_he_is_before_the_list_of_ideas() -> None:
    plan = _plan([{"heading": "One", "concept": "c1", "covers": "c", "introduces": ["a"]}])
    lead = lw._concept_lead(plan)
    assert "teaches one idea" in lead and "come back to this list at the end" in lead
    assert lw._concept_lead(plan.model_copy(update={"concepts": []})) == ""


def test_the_writer_is_told_to_connect_and_never_to_shorten() -> None:
    teacher = " ".join((lw.writer_dir() / "teacher.md").read_text().split())
    section = " ".join((lw.writer_dir() / "section.md").read_text().split())
    course = " ".join((lw.writer_dir() / "outline-course.md").read_text().split())
    editor = " ".join((lw.writer_dir() / "editor.md").read_text().split())
    assert "Length is not the lever" in teacher and "He is new to this subject" in teacher
    assert "join them with because, so or but" in teacher
    assert "No figurative nouns" in teacher
    for old in ("He is not a beginner", ):
        assert old not in teacher and old not in editor, old
    assert "<dfn>" in section and "The picture first" in section and "The hand-over" in section
    for old in ("never more detail", "Say each point once"):
        assert old not in section, old
    assert "running_case" in course and "`bridge`" in course and "`hands_over`" in course
    assert "A lesson is never made shorter to make it easier" in course
    assert "Never ask for a section to be shortened" in editor
    assert lw.SOURCE_CHARS >= 80_000


LESSONS = Path(__file__).resolve().parents[2] / "learning" / "lessons"


@pytest.mark.parametrize("name", [
    "2026-09-17-inference-internals-phase-01-lifecycle.html",
    "2026-09-20-inference-internals-phase-02a-scheduling-memory.html",
])
def test_the_lessons_he_already_has_can_be_remembered(name: str) -> None:
    page = LESSONS / name
    if not page.is_file():
        pytest.skip("the lesson is not in this checkout")
    m = lw.phase_memory(page.read_text(), slug=name, title=name)
    assert len(m.situation.split()) >= 20
    assert len(m.terms) >= 3
    assert len(m.ended.split()) >= 10
    assert len(lw.memory_block([m])) <= lw.MEMORY_CHARS + 400


def test_a_phase_is_read_by_its_slug_and_not_looked_up_in_a_capped_list(monkeypatch) -> None:
    """The platform's list stops at 100 documents. Phase 2B was the 101st or
    later, the tool said it did not exist, and hunter filled its context
    window with two copies of the list instead."""
    from hq.tools import learning_tools as lt

    asked: list[str] = []

    async def one(slug: str) -> dict[str, Any]:
        asked.append(slug)
        if slug != "c-phase-02-decode":
            raise ValueError("the study platform has no content for it")
        return {"slug": slug, "title": "Phase 2B", "summary": "s", "sections": [],
                "content": "## 2.4 Chunked prefill\n\nBody."}

    async def rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return [{"slug": "c-phase-01-sched", "title": "Phase 1"},
                {"slug": "c-phase-02-decode", "title": "Phase 2B"},
                {"slug": "c-phase-03-cache", "title": "Phase 3"}]

    async def no_emit(*a: Any, **k: Any) -> None:
        return None

    monkeypatch.setattr(lt, "fetch_platform_document", one)
    monkeypatch.setattr(lt.db, "fetch", rows)
    monkeypatch.setattr(lt, "emit", no_emit)
    monkeypatch.setattr(lt.courses_spec, "find_phase", lambda slug: None)
    ctx = type("Ctx", (), {"deps": HQDeps(agent="hunter", task_id=None, run_id=None)})()
    import inspect

    raw = inspect.unwrap(lt.read_course_phase)
    got = asyncio.run(raw(ctx, "c-phase-02-decode"))
    assert asked == ["c-phase-02-decode"]
    assert got["content"].startswith("## 2.4 Chunked prefill")
    assert got["sequence"]["previous"]["slug"] == "c-phase-01-sched"
    assert got["sequence"]["next"]["slug"] == "c-phase-03-cache"
    from pydantic_ai import ModelRetry
    with pytest.raises(ModelRetry):
        asyncio.run(raw(ctx, "c-phase-09-missing"))


def test_the_phase_before_a_second_part_is_the_first_part() -> None:
    from hq.tools import learning_tools as lt

    rows = [{"slug": "c-phase-01-life", "title": "1"}, {"slug": "c-phase-02-whole", "title": "2"},
            {"slug": "c-phase-02a-sched", "title": "2A"}, {"slug": "c-phase-02b-decode", "title": "2B"},
            {"slug": "c-phase-03a-cache", "title": "3A"}]
    seq = lt.course_sequence(rows, "c-phase-02b-decode")
    assert seq["previous"]["slug"] == "c-phase-02a-sched" and seq["next"]["slug"] == "c-phase-03a-cache"
    seq = lt.course_sequence(rows, "c-phase-02a-sched")
    assert seq["previous"]["slug"] == "c-phase-01-life" and seq["next"]["slug"] == "c-phase-02b-decode"
    plain = [{"slug": f"k-phase-0{i}-x", "title": str(i)} for i in (1, 2, 3)]
    seq = lt.course_sequence(plain, "k-phase-02-x")
    assert seq["previous"]["slug"] == "k-phase-01-x" and seq["next"]["slug"] == "k-phase-03-x"


def test_a_figure_typed_as_characters_is_sent_back_to_be_drawn() -> None:
    typed = '<p>The pass is shared.</p><pre class="ascii">iteration: 1 2 3 prefill: - - X</pre>'
    found = lw.figure_problems(typed)
    assert len(found) == 1 and '<div class="lanes" data-play>' in found[0]
    assert "Keep every number" in found[0]
    # One typed layout beside a drawn figure is allowed; two are not.
    beside = typed + '<ol class="flow"><li><b>a</b></li><li><b>b</b></li></ol>'
    assert lw.figure_problems(beside) == []
    assert lw.figure_problems(beside + '<pre class="ascii">x</pre>')
    assert lw.figure_problems('<div class="lanes" data-play></div>') == []
    # Code is not a figure.
    assert lw.figure_problems('<pre><code data-lang="python">x = 1</code></pre>') == []


def test_the_habits_of_generated_prose_are_sent_back_with_the_plain_form() -> None:
    plain = "".join(f"<p>The scheduler runs pass {i} and gives each running request one"
                    " token, so the queue gets shorter by the requests that finished.</p>"
                    for i in range(14))
    assert lw.voice_problems(plain) == []
    reveal = plain + "".join(f"<p>The table held one open problem in row {i}: a pause of"
                             " 764ms inside one answer.</p>" for i in range(4))
    assert any("colon and a reveal" in p for p in lw.voice_problems(reveal))
    absolute = plain + "".join(f"<p>Nothing in metric {i} shows the pause and a retry never"
                               " helps the request.</p>" for i in range(3))
    assert any("nothing, never, none" in p for p in lw.voice_problems(absolute))
    asked = plain + "".join(f"<p>What does the server do in pass {i} of the run?</p>"
                            for i in range(3))
    assert any("questions are asked inside the prose" in p for p in lw.voice_problems(asked))
    # The section's own heading and its predict box are not prose questions.
    boxed = ('<h2 data-concept="c1">Why does the stream freeze?</h2><details class="predict">'
             "<summary>Predict: what happens to the three streams?</summary><p>They wait.</p>"
             "</details>" + plain)
    assert lw.voice_problems(boxed) == []
    spoken = "<p>Every request fights over the same pass, whether the server wants it or not.</p>"
    found = lw.voice_problems(spoken)
    assert len(found) == 1 and "fights over" in found[0] and "whiteboard" in found[0]


def test_the_kit_draws_flows_lanes_stacks_and_trees() -> None:
    from hq import lesson_kit
    from hq.tools import learning_tools as lt

    for piece in (".flow", ".lanes", ".lane i", ".stack", ".tree", "dfn{", "td.ok"):
        assert piece in lesson_kit.KIT_CSS, piece
    assert "data-play" in lesson_kit.KIT_JS and ".stack" in lesson_kit.KIT_JS
    assert "http" not in lesson_kit.KIT_CSS + lesson_kit.KIT_JS
    long = "<p>" + " ".join(["word"] * (lt.VISUAL_SECTION_WORDS + 20)) + ".</p>"
    assert lt.sections_without_a_visual("<h2>How admission works</h2>" + long)
    for mark in ('<ol class="flow">', '<div class="lanes" data-play>', '<div class="stack">',
                 '<ul class="tree">'):
        assert lt.sections_without_a_visual("<h2>How admission works</h2>" + mark + long) == []
    kit = " ".join((lw.writer_dir() / "page-kit.md").read_text().split())
    assert "Draw, do not type" in kit and "Let him move it" in kit
    assert 'class="lanes"' in kit and 'class="stack"' in kit and 'class="tree"' in kit
    section = " ".join((lw.writer_dir() / "section.md").read_text().split())
    assert 'one `<div class="cards">`, a card per earlier idea' in section
    teacher = " ".join((lw.writer_dir() / "teacher.md").read_text().split())
    assert "Write as a person explains at a whiteboard" in teacher


def test_a_term_the_orientation_explains_again_may_be_assumed_below_it() -> None:
    plan = _plan([
        {"heading": "Where this phase starts", "kind": "orientation", "covers": "c",
         "introduces": ["prefill", "decode"]},
        {"heading": "Why does the stream freeze", "concept": "c1", "covers": "c",
         "assumes": ["prefill", "decode"], "introduces": ["inter-token gap"]},
        {"heading": "What does chunking trade", "concept": "c1", "covers": "c",
         "assumes": ["inter-token gap", "prefill"], "bridge": "The freeze has a cause; its fix has a cost."},
        {"heading": "The lab", "kind": "lab", "covers": "c", "introduces": ["not a term"]},
    ])
    assert lw.ledger_problems(plan, known=["prefill", "decode"]) == []
    # A term only the lab names is not explained for a teaching section.
    plan.sections[2].assumes = ["not a term"]
    assert len(lw.ledger_problems(plan)) == 1
