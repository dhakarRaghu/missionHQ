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


def test_naming_the_employer_fails_the_case(monkeypatch) -> None:
    monkeypatch.setattr(regress.settings(), "private_employers", ("Acme Corp",))
    employer = "Acme Corp"
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


def _result(label: str, results: list[dict], where) -> None:
    import json

    (where / f"{label}.json").write_text(json.dumps({"label": label, "results": results}))


def _case_result(cid: str, passed: bool, sha: str, cost: float = 0.1) -> dict:
    return {"id": cid, "passed": passed,
            "trials": [{"passed": passed, "cost_usd": cost, "bundle_sha": sha}]}


def test_compare_names_the_cases_whose_bundle_moved_and_sums_the_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(regress, "RESULTS_DIR", tmp_path)
    _result("before", [_case_result("a", True, "111", 0.2), _case_result("b", True, "222"),
                       _case_result("c", False, "333")], tmp_path)
    _result("after", [_case_result("a", False, "999", 0.3), _case_result("b", True, "222"),
                      _case_result("c", True, "333")], tmp_path)
    lines = regress.compare("before", "after")
    assert lines[0].startswith("REGRESSION a") and lines[0].endswith("bundle changed")
    assert lines[1].startswith("same       b") and "bundle changed" not in lines[1]
    assert lines[2].startswith("fixed      c") and "bundle changed" not in lines[2]
    assert lines[-1] == "2/3 pass → 2/3 pass; $0.400 → $0.500"


def test_compare_says_nothing_about_a_bundle_an_old_result_never_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(regress, "RESULTS_DIR", tmp_path)
    _result("before", [{"id": "a", "passed": True, "trials": [{"passed": True, "cost_usd": 0}]}],
            tmp_path)
    _result("after", [_case_result("a", True, "999")], tmp_path)
    assert "bundle changed" not in regress.compare("before", "after")[0]


def test_the_bundle_sha_drops_the_clock_line_only() -> None:
    same = regress.instructions_sha("Current date and time: Monday.\n\n# Rules\n\nno em dashes")
    later = regress.instructions_sha("Current date and time: Tuesday.\n\n# Rules\n\nno em dashes")
    edited = regress.instructions_sha("Current date and time: Monday.\n\n# Rules\n\nno dashes")
    assert same == later != edited and len(same) == 12


def test_cases_are_listed_with_their_source_line() -> None:
    cases = [regress.Case(id="short", agent="sage", source="one\n  line\n", prompt="p"),
             regress.Case(id="a-longer-id", agent="hunter", source="two", prompt="p")]
    lines = regress.case_lines(cases)
    assert lines == ["short        sage     one line", "a-longer-id  hunter   two"]


def test_k_overrides_each_cases_own_count() -> None:
    import inspect

    assert "k or case.k" in inspect.getsource(regress.run)
    assert inspect.signature(regress.run).parameters["k"].default is None
    assert "bundle_sha" in regress.Trial.__dataclass_fields__
