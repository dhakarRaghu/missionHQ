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

    async def outline_step(model: str, article: bool, material: str, problems: list[str]):
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
    monkeypatch.setattr(lt, "record_lesson_row", record_row)
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


@pytest.mark.parametrize("stage,source,expected", [
    ("course_lesson", "platform", True), ("course_lesson", "local", False),
    ("lesson_synthesis", None, True), ("lab_card", None, False),
])
def test_the_writer_takes_phases_and_articles_only(stage: str, source: str | None,
                                                   expected: bool) -> None:
    from hq.config import settings
    from hq.loader import parse_job_md

    tutor = parse_job_md(settings().agents_dir / "tutor")
    payload: dict[str, Any] = {"workflow": "learning_journey", "stage": stage}
    if source:
        payload["source"] = source
    assert lw.handles(tutor, payload) is expected
