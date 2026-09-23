"""The regression harness grades what an agent did, and cannot write for real."""

from __future__ import annotations

import pytest

from hq import regress


def _case(**expect) -> regress.Case:
    return regress.Case(id="c", agent="sage", source="s", prompt="p",
                        expect=regress.Expect(**expect))


def test_calls_and_arguments_are_checked() -> None:
    calls = [{"tool": "create_subtask", "args": {"agent": "operator"}, "ok": True},
             {"tool": "read_activity", "args": {}, "ok": True}]
    case = _case(calls=["create_subtask"], max_calls={"read_activity": 0},
                 args_match={"create_subtask": "operator"},
                 args_not_match={"create_subtask": "hunter"})
    fails = regress._check(case, "handed to operator", calls)
    assert fails == ["called read_activity 1 times (max 0)"]


def test_a_lesson_counts_only_when_write_lesson_got_through() -> None:
    refused = [{"tool": "write_lesson", "args": {}, "ok": False}]
    assert regress._check(_case(lesson_written=True), "", refused) == [
        "no lesson got through write_lesson"]
    accepted = [{"tool": "write_lesson", "args": {}, "ok": True}]
    assert regress._check(_case(lesson_written=True), "", accepted) == []


def test_naming_the_employer_fails_the_case() -> None:
    employer = regress.settings().private_employers[0]
    calls = [{"tool": "vault_write", "args": {"content": f"I work at {employer}."}, "ok": True}]
    assert "names his employer" in regress._check(_case(), "", calls)


def test_a_writing_tool_cannot_run_for_real(tmp_path, monkeypatch) -> None:
    (tmp_path / "x.yaml").write_text(
        "- {id: bad, agent: sage, source: s, prompt: p, real: [vault_write]}\n")
    monkeypatch.setattr(regress, "CASES_DIR", tmp_path)
    with pytest.raises(ValueError, match="cannot run for real"):
        regress.load_cases()


def test_the_lesson_sandbox_never_touches_real_lessons() -> None:
    real = regress.settings().learning_dir
    with regress._sandboxed_learning() as tmp:
        assert regress.settings().learning_dir == tmp != real
        assert not (tmp / "lessons").is_symlink()
    assert regress.settings().learning_dir == real
    assert not tmp.exists()


def test_every_case_file_loads() -> None:
    cases = regress.load_cases()
    assert len({c.id for c in cases}) == len(cases)
    assert {c.agent for c in cases} >= {"tutor", "hunter", "sage"}
