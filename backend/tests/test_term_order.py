"""Term order: every term is explained before a page uses it, for any course.

On 2026-10-20 the lessons of five courses used terms before they explained
them: Redis Phase 0 used "eviction policy" at word 338 and explained it at
word 7,553. The plan's ledger checked only the plan, so a lesson from any
other writer, and the sentences of this one, were never checked.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from hq import assemble, term_order
from hq import lesson_writer as lw
from hq.tools import learning_tools as lt

SKILL_COPY = Path.home() / ".claude/skills/study/scripts/term_order.py"


def test_the_rules_pass_their_own_self_test() -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        assert term_order.self_test() == 0


def test_the_copy_matches_the_study_skill() -> None:
    """One set of rules for both pipelines. Mission HQ runs on a machine that
    may not have the skill, so the test only compares when the file is there."""
    if not SKILL_COPY.is_file():
        return
    assert Path(term_order.__file__).read_text() == SKILL_COPY.read_text(), (
        "hq/term_order.py differs from the study skill's scripts/term_order.py: copy one over the other")


def _course(tmp_path: Path, monkeypatch: Any, *, outline: list[dict[str, Any]] | None = None) -> Path:
    learning = tmp_path / "learning"
    study = learning / "study-material"
    (study / "shop").mkdir(parents=True)
    (learning / "lessons").mkdir()
    (study / "_learner.json").write_text(json.dumps({
        "schemaVersion": 1, "reader": "The reader builds web services.",
        "knownTerms": ["HTTP"], "courses": {"shop": {"level": "new to it", "knownTerms": ["cart"]}}}))
    for key in ("00-why", "01-orders", "02-payments"):
        (study / "shop" / f"shop-phase-{key}.md").write_text(f"# Phase {key}\n")
    (study / "shop" / "course.json").write_text(json.dumps({"topic": "shop", "outline": outline or [
        {"phase": 0, "title": "Why", "terms": {"introduces": ["basket"], "assumes": []}},
        {"phase": 1, "title": "Orders", "terms": {"introduces": ["order", "refund"], "assumes": ["basket"]}},
        {"phase": 2, "title": "Payments", "terms": {"introduces": ["capture"], "assumes": ["order"]}},
    ]}))
    monkeypatch.setattr(lt.settings(), "learning_dir", learning)
    return learning


def test_a_page_that_uses_a_term_before_it_explains_it_is_refused(tmp_path, monkeypatch) -> None:
    learning = _course(tmp_path, monkeypatch)
    (learning / "lessons" / "2026-01-01-shop-phase-00-why.html").write_text(
        "<main><p>A <dfn>basket</dfn> holds items.</p></main>")
    page = ("<main><p>Phase 0 showed a basket. An order can get a refund.</p>"
            "<h2 data-concept=\"c1\">What is an order?</h2><p>An <dfn>order</dfn> is a basket that was"
            " paid. A cart and HTTP need no explanation.</p>"
            "<h2 data-kind=\"recall\">What you can do now</h2><p>Phase 2 asks how money moves.</p></main>")
    found = lt.term_findings("shop-phase-01-orders", page)
    assert any("'order' is used at word" in f for f in found.hard)
    # "refund" is the map's term for this phase, and the page never defines it.
    assert any("'refund'" in f and "never marks" in f for f in found.hard)
    # "basket" is from Phase 0, "cart" and "HTTP" from the profile: none is a finding.
    assert not any(t in f for f in found.hard for t in ("'basket'", "'cart'", "'HTTP'"))
    # The page names Phase 0 at its start and Phase 2 at its end.
    assert not any("opening" in f or "ending" in f for f in found.hard)


def test_a_page_must_name_the_phase_before_and_after_it(tmp_path, monkeypatch) -> None:
    _course(tmp_path, monkeypatch)
    page = ("<main><p>Here we start.</p><h2 data-concept=\"c1\">One</h2><p>A <dfn>order</dfn>"
            " is paid. A <dfn>refund</dfn> returns it.</p><h2 data-kind=\"recall\">Now</h2>"
            "<p>Done.</p></main>")
    found = lt.term_findings("shop-phase-01-orders", page)
    assert any(f.startswith("the opening does not say where Phase 0") for f in found.hard)
    assert any(f.startswith("the ending does not lead to Phase 2") for f in found.hard)
    assert lt.term_findings("lab-shop-phase-01-orders", page).hard == []


def test_a_course_with_no_term_map_still_checks_the_page(tmp_path, monkeypatch) -> None:
    learning = _course(tmp_path, monkeypatch, outline=[])
    (learning / "study-material" / "shop" / "course.json").write_text(json.dumps({"topic": "shop"}))
    page = "<main><p>Each replica lags.</p><p>A <dfn>replica</dfn> is a copy.</p></main>"
    found = lt.term_findings("shop-phase-00-why", page)
    assert any("'replica' is used at word" in f for f in found.hard)


def test_the_plan_gets_where_the_reader_starts(tmp_path, monkeypatch) -> None:
    _course(tmp_path, monkeypatch)
    terms = lt.course_terms("shop-phase-01-orders")
    assert terms is not None
    assert terms.reader_terms == ["HTTP", "cart"] and "basket" in terms.earlier_terms
    assert terms.phase_terms == ["order", "refund"]
    assert (terms.previous, terms.following) == ("Phase 0", "Phase 2")
    block = lw.reader_block(terms)
    assert "The reader builds web services. In this subject: new to it." in block
    assert "order, refund" in block and "Phase 0, Why" in block


def _plan(**kw: Any) -> lw.Outline:
    concept = {"id": "c1", "claim": "A paid order can be returned with a refund",
               "lets_him": "decide when money goes back", "wrong_belief": "b", "predict": "What?",
               "evidence": "e", "evidence_quote": "q", "picture": "p"}
    sections = [{"heading": "What is an order", "concept": "c1", "covers": "c",
                 "introduces": ["order"], "assumes": ["cart"]}]
    return lw.Outline.model_validate({
        "title": "T", "subtitle": "S", "eyebrow": "E", "outcome": "O", "opening": "Op",
        "running_case": "A shop that loses orders.", "concepts": [concept], "sections": sections, **kw})


def test_the_plan_must_teach_the_map_terms_and_keep_the_claims_plain() -> None:
    found = lw.ledger_problems(_plan(), reader=["cart"], required=["order", "refund"])
    # "cart" is the reader's already, so assuming it is fine.
    assert not any("'cart'" in f for f in found)
    assert any("gives 'refund' to this phase" in f for f in found)
    # The claim says "order", which a section explains only later.
    assert any("c1's claim uses 'order'" in f for f in found)
    # Without the profile, assuming "cart" is a finding, as before.
    assert any("assumes 'cart'" in f for f in lw.ledger_problems(_plan()))


def test_the_writer_and_editor_are_told_about_the_reader_from_data(tmp_path, monkeypatch) -> None:
    _course(tmp_path, monkeypatch)
    assert assemble.reader_section() == "## The reader\n\nThe reader builds web services."
    assert "The reader builds web services." in lw.editor_instructions()
    teacher = (lw.writer_dir() / "teacher.md").read_text()
    assert "Go and gRPC" not in teacher and '"The reader" below' in teacher


def test_one_name_per_idea_except_in_his_own_lab(tmp_path, monkeypatch) -> None:
    learning = _course(tmp_path, monkeypatch)
    cj = learning / "study-material" / "shop" / "course.json"
    course = json.loads(cj.read_text())
    course["aliases"] = {"chargeback": "refund"}
    cj.write_text(json.dumps(course))
    page = ("<main><p>Phase 0 showed a basket.</p><h2 data-concept=\"c1\">One</h2><p>An"
            " <dfn>order</dfn> is paid. A <dfn>refund</dfn> returns it. A chargeback is slow.</p>"
            "<h2 data-kind=\"recall\">Now</h2><p>Phase 2 asks how money moves.</p>"
            "<h2 data-kind=\"lab\">Lab</h2><p>E1: issue a chargeback.</p></main>")
    found = lt.term_findings("shop-phase-01-orders", page)
    assert sum("'chargeback' is another name for 'refund'" in f for f in found.hard) == 1
    clean = page.replace(" A chargeback is slow.", "")
    assert lt.term_findings("shop-phase-01-orders", clean).hard == []
