"""State injected as data, never inferred: the continuity block, the
owner-state block and the shortlist tool. Nothing here touches the database;
the readers are stood in for and the renderers are exercised on fixtures."""

from __future__ import annotations

import asyncio
import inspect
import types
from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic_ai import ModelRetry

from hq import continuity as ct
from hq import engine, owner_state, regress
from hq.tools import jobs_shortlist_tools as st
from hq.tools.registry import HQDeps

CLOUDFLARE = "b62d7768-1111-2222-3333-444444444444"
BJAK = "9fe6f9a9-1111-2222-3333-444444444444"
VISA = "03ec912c-1111-2222-3333-444444444444"
RIPPLING = "1ca7f387-1111-2222-3333-444444444444"
SEEN = datetime(2026, 9, 24, 5, 41, tzinfo=UTC)

NOTE_LABEL = """---
created: 2026-09-24
author: sage
---
# Daily note - 2026-09-24

The one thing you did not know: a cost dashboard can look fine while showing
about half your real spend. Langfuse issue 13807 records a run billed $0.522
that the dashboard showed as $0.238.

Needs you:
- Read and mark Phase 2B. It still gates both learning chains.
- Apply to Cloudflare, Software Engineer (the 9-scored LinkedIn role).
- Decide the YC-India board rotation. Six zero-result runs in a row.

Today:
- Hunter finished the Phase 3A study note.
"""

NOTE_HEADING = """# Daily note — 2026-09-22 (Tuesday)

## The one thing
**Ashby's job pages are JavaScript-gated, but the JSON API behind them is
open and complete.** Reading Sarvam AI's board today, hunter found the pages
blocked to a logged-out fetch.

## Needs you
- Apply to Cloudflare, Software Engineer, before the posting expires.
- Operator task b3be878b is sitting at needs_approval,
  waiting on you.
- Post the return post on X.

## Today
- Hunter filed the Sarvam dig.
"""

DECISIONS = """# Decisions

<!-- Written by the owner; every agent reads it. -->

## Decided

- Agents never apply, post, send or connect. He does.
- Where: India or India-remote. Any work mode.

## Open

- YC-India board rotation: six zero-result runs in a row. Stop daily and run weekly?
- Blind-agency applications (Jobgether): yes or no? (raised 2026-09-10)
"""


def _job(job_id: str, company: str, role: str, status: str, fit: int,
         pay: float | None, estimated: str | None) -> dict[str, Any]:
    return {"job_id": job_id, "company": company, "role": role, "status": status,
            "fit_score": fit, "pay_lakh": pay, "estimated": estimated, "last_seen": SEEN}


JOBS = [
    _job(CLOUDFLARE, "Cloudflare", "Software Engineer, AI Agents", "closed", 10, 35.0, "true"),
    _job(BJAK, "BJAK", "Applied AI Engineer", "seen", 10, None, None),
    _job(VISA, "Visa", "Software Engineer (0.5-2 years band)", "seen", 10, 30.0, "true"),
    _job(RIPPLING, "Rippling", "Software Engineer I", "shortlisted", 9, 28.0, "false"),
]


def _ledger(cloudflare: str = "closed") -> ct.Ledger:
    jobs = [dict(j, status=cloudflare) if j["company"] == "Cloudflare" else dict(j)
            for j in JOBS]
    open_, decided = ct.parse_decisions(DECISIONS)
    return ct.Ledger(
        jobs=jobs,
        tasks=[{"id": "b3be878b-0000-0000-0000-000000000000", "status": "done"}],
        lessons=[{"title": "Phase 2B — Decoding and context", "kind": "course", "read_at": None},
                 {"title": "Phase 2A — Scheduling and memory", "kind": "course",
                  "read_at": datetime(2026, 9, 22, tzinfo=UTC)}],
        open_decisions=open_, decided=decided,
    )


# --- parsing the vault ------------------------------------------------------------

def test_the_lead_is_read_from_both_note_shapes() -> None:
    assert ct.parse_lead(NOTE_LABEL) == (
        "a cost dashboard can look fine while showing about half your real spend.")
    assert ct.parse_lead(NOTE_HEADING).startswith("Ashby's job pages are JavaScript-gated")
    assert "**" not in ct.parse_lead(NOTE_HEADING)
    assert ct.parse_lead("# Empty\n") == ""


def test_needs_you_lines_are_read_from_both_shapes_and_wrapped_lines_join() -> None:
    assert ct.parse_needs_you(NOTE_LABEL) == [
        "Read and mark Phase 2B. It still gates both learning chains.",
        "Apply to Cloudflare, Software Engineer (the 9-scored LinkedIn role).",
        "Decide the YC-India board rotation. Six zero-result runs in a row.",
    ]
    lines = ct.parse_needs_you(NOTE_HEADING)
    assert len(lines) == 3
    assert lines[1] == "Operator task b3be878b is sitting at needs_approval, waiting on you."
    assert ct.parse_needs_you("# Note\n\nToday:\n- nothing\n") == []


def test_decisions_split_into_open_and_decided() -> None:
    open_, decided = ct.parse_decisions(DECISIONS)
    assert len(open_) == 2 and open_[0].startswith("YC-India")
    assert len(decided) == 2 and decided[0].startswith("Agents never apply")


def test_distinctive_tokens_skip_short_and_common_words() -> None:
    tokens = ct.proper_nouns("Where: India or India-remote. Any work mode.")
    assert "India" not in tokens and "India-remote" in tokens
    assert "Jobgether" in ct.proper_nouns("Blind-agency applications (Jobgether): yes or no?")
    assert "Optifye.ai" in ct.proper_nouns("Does the skip bend for Optifye.ai founding engineer?")


# --- a line against the ledger ---------------------------------------------------

def test_a_closed_job_is_marked_closed_and_an_open_one_shows_its_row() -> None:
    line = "Apply to Cloudflare, Software Engineer (the 9-scored LinkedIn role)."
    status, closed = ct.line_status(line, _ledger("closed"))
    assert status == "job Cloudflare CLOSED" and closed is True
    status, closed = ct.line_status(line, _ledger("seen"))
    assert status == "job Cloudflare seen 10/10, est 35 LPA, checked 09-24" and closed is False
    rendered = ct.render_needs([ct.Need("2026-09-24", line, *ct.line_status(line, _ledger()))])
    assert rendered == [f"- [closed] 09-24: “{line}” -> job Cloudflare CLOSED"]


def test_a_stated_pay_row_and_a_missing_one_read_differently() -> None:
    status, _ = ct.line_status("Apply to Rippling and BJAK.", _ledger())
    assert "job BJAK seen 10/10, no figure" in status
    assert "job Rippling shortlisted 9/10, stated 28 LPA" in status


def test_a_done_task_and_a_read_lesson_close_a_line_and_an_unread_one_keeps_it_open() -> None:
    status, closed = ct.line_status(
        "Operator task b3be878b is sitting at needs_approval, waiting on you.", _ledger())
    assert status == "task b3be878b done" and closed is True
    status, closed = ct.line_status("Read and mark Phase 2B.", _ledger())
    assert "lesson “Phase 2B — Decoding and context” unread" in status and closed is False
    status, closed = ct.line_status("Read and mark the Phase 2A lesson.", _ledger())
    assert "read 2026-09-22" in status and closed is True


def test_a_decision_line_shows_open_or_decided() -> None:
    status, closed = ct.line_status("Decide the YC-India board rotation.", _ledger())
    assert status.startswith("decision open: YC-India board rotation") and closed is False
    assert "decided:" not in status  # "India" alone must not tie it to "India or India-remote"
    status, closed = ct.line_status("Jobgether: yes or no?", _ledger())
    assert "decision open: Blind-agency applications (Jobgether)" in status


def test_a_line_the_ledger_does_not_know_says_so() -> None:
    status, closed = ct.line_status("Post the return post on X.", _ledger())
    assert status == ct.NOT_IN_LEDGER and closed is None
    rendered = ct.render_needs([ct.Need("2026-09-22", "Post the return post on X.", status, closed)])
    assert rendered[0].startswith("- [not in any ledger] 09-22:")


def test_a_line_naming_many_rows_keeps_the_closed_ones_and_counts_the_rest() -> None:
    jobs = [_job(f"{i:08x}-0000-0000-0000-000000000000", f"Company{i}", "SWE",
                 "closed" if i == 7 else "seen", 9, None, None) for i in range(8)]
    line = "Apply to " + ", ".join(f"Company{i}" for i in range(8)) + "."
    status, closed = ct.line_status(line, ct.Ledger(jobs=jobs))
    assert status.startswith("job Company7 CLOSED") and status.endswith("+3 more")
    assert closed is False


def test_repeated_needs_lines_collapse_into_one_that_names_every_night() -> None:
    line = "Decide the YC-India board rotation."
    status, closed = ct.line_status(line, _ledger())
    needs = [ct.Need(d, line, status, closed) for d in ("2026-09-20", "2026-09-24", "2026-09-22")]
    needs.append(ct.Need("2026-09-24", "Post the return post on X.", ct.NOT_IN_LEDGER, None))
    needs.append(ct.Need("2026-09-22", "Post the return post on X", ct.NOT_IN_LEDGER, None))
    out = ct.dedupe_needs(needs)
    assert [n.day for n in out] == ["2026-09-24", "2026-09-24"]
    assert out[0].also == ["2026-09-22", "2026-09-20"]
    assert out[1].also == ["2026-09-22"]
    assert ct.render_needs(out)[0].startswith("- [still open] 09-24 (also 09-22, 09-20):")


# --- decisions, counters, shortlist rows --------------------------------------------

def test_decisions_get_their_age_and_a_stale_one_gets_a_default_proposed() -> None:
    today = date(2026, 9, 25)
    aged, decided = ct.decisions_with_age(
        DECISIONS, today, added=lambda line: date(2026, 9, 23) if "YC-India" in line else None)
    assert aged == [(("YC-India board rotation: six zero-result runs in a row. Stop daily and run"
                      " weekly?"), 2),
                    ("Blind-agency applications (Jobgether): yes or no? (raised 2026-09-10)", 15)]
    lines = ct.render_decisions(aged + [("Relocation: yes or no?", None)])
    assert lines[0].endswith("(open 2 days)")
    assert lines[1].endswith("(open 15 days; propose a default)")
    assert lines[2].endswith("(age unknown)")
    assert len(decided) == 2


def test_counters_are_computed_by_code_and_say_not_recorded_or_not_readable() -> None:
    lines = ct.render_counters(ct.Counters(
        unread_by_kind={"course": 3, "topic": 1}, written=7, read=3,
        jobs_found=42, jobs_strong=18, jobs_applied=0, open_requests=None))
    assert lines[0] == ("- Days since he last published a post: not recorded (nothing records"
                        " a post going out)")
    assert lines[1] == "- Unread lessons: 4 (course 3, topic 1)"
    assert lines[2] == "- Last 7 days: lessons written 7, read 3"
    assert lines[3] == "- Last 7 days: jobs found 42, strong 18, applied 0"
    assert lines[4] == "- Open operator requests: not readable"
    assert "- Unread lessons: not readable" in ct.render_counters(ct.Counters())
    assert "- Unread lessons: 0" in ct.render_counters(ct.Counters(unread_by_kind={}))


def test_shortlist_rows_carry_status_score_pay_kind_and_last_check() -> None:
    head, *rows = ct.render_shortlist(JOBS[1:], bar=25.0)
    assert "apply" in head and "25 LPA" in head
    assert rows[0] == ("- 9fe6f9a9 BJAK, Applied AI Engineer: seen 10/10, no figure,"
                       " live-checked 2026-09-24")
    assert "estimated 30 LPA" in rows[1]
    assert "stated 28 LPA" in rows[2] and "shortlisted" in rows[2]
    assert ct.render_shortlist([], 25.0)[1] == "- no open rows in the ledger"


# --- the block -------------------------------------------------------------------------

def _needs() -> list[ct.Need]:
    ledger = _ledger()
    lines = [(d, ln) for d, text in (("2026-09-24", NOTE_LABEL), ("2026-09-22", NOTE_HEADING))
             for ln in ct.parse_needs_you(text)]
    return ct.dedupe_needs([ct.Need(d, ln, *ct.line_status(ln, ledger)) for d, ln in lines])


def test_the_block_stays_under_the_limit_and_never_cuts_a_status_line() -> None:
    decisions = [(f"Decision {i}: a long open question about something {i}", i) for i in range(40)]
    needs = _needs()
    text = ct.render_block(
        sections=ct.SECTIONS["daily-note"], lead=("2026-09-24", ct.parse_lead(NOTE_LABEL)),
        needs=needs, decisions=decisions, counters=ct.Counters(), owner="", limit=2_500)
    assert len(text) <= 2_500 and text.startswith(ct.HEADING)
    assert "Last note (2026-09-24) led with: “a cost dashboard" in text
    assert "Tonight leads with something else." in text
    for line in ct.render_needs(needs):
        assert line in text                      # every status line survives the cut
    assert "more not shown)" in text and "Decision 39" not in text
    assert "- Days since he last published a post: not recorded" in text


def test_the_owner_block_follows_whole_and_outside_the_limit() -> None:
    owner = owner_state.render(read=[{"title": f"Lesson {i}", "kind": "topic", "read_at": SEEN}
                                     for i in range(6)],
                               unread=[], moved=[], applied=[], answered=0)
    text = ct.render_block(sections=ct.SECTIONS["daily-posts"], lead=None,
                           counters=ct.Counters(), owner=owner, limit=700)
    head, _, tail = text.partition("\n\n" + owner_state.HEADING)
    assert len(head) <= 700 and tail            # the owner block is appended after the limit
    assert text.endswith(owner)
    assert "Last note: none found." in head


def test_each_skill_gets_its_own_sections() -> None:
    assert set(ct.SECTIONS) == {"daily-note", "consolidate", "job-shortlist", "daily-posts",
                                "weekly-review"}
    shortlist = ct.render_block(sections=ct.SECTIONS["job-shortlist"], shortlist=JOBS[1:],
                                counters=ct.Counters(), decisions=[])
    assert "Candidate rows" in shortlist and "Needs-you lines" not in shortlist
    assert "- no open rows in the ledger" in ct.render_block(
        sections=("shortlist",), shortlist=[], counters=None)


# --- the owner-state block ---------------------------------------------------------------

def test_owner_state_lists_only_the_ledger_and_says_none_or_not_readable() -> None:
    text = owner_state.render(
        read=[{"title": "The Bill and the Cache", "kind": "course",
               "read_at": datetime(2026, 9, 22, tzinfo=UTC)}],
        unread=[{"title": "Phase 2B — Decoding and context", "kind": "course",
                 "lesson_date": date(2026, 9, 22)}],
        moved=[{"company": "Adobe", "role": "MTS 1", "status": "referral", "ts": SEEN},
               {"company": "OpenAI", "role": "SWE", "status": "closed", "ts": SEEN}],
        applied=None, answered=0)
    assert text.startswith(owner_state.HEADING + "\n" + owner_state.RULE)
    assert "- Lessons he read (last 14 days): “The Bill and the Cache” (course, read 2026-09-22)" in text
    assert "not yet read: “Phase 2B — Decoding and context” (course, 2026-09-22)" in text
    assert "Adobe, MTS 1 -> referral (2026-09-24); 1 he closed" in text
    assert "- Roles he has applied to (board status applied): not readable" in text
    assert "- Posts he published: not recorded" in text
    assert "- Operator requests he answered himself: none recorded" in text
    empty = owner_state.render(read=[], unread=[], moved=[], applied=[], answered=None)
    assert "- Lessons he read (last 14 days): none" in empty
    assert "- Operator requests he answered himself: not readable" in empty


def test_owner_state_shortens_its_lists_and_never_cuts_a_name() -> None:
    read = [{"title": f"A lesson with a long enough title number {i}", "kind": "topic",
             "read_at": SEEN} for i in range(30)]
    moved = [{"company": f"Company number {i}", "role": "Software Engineer", "status": "referral",
              "ts": SEEN} for i in range(30)]
    text = owner_state.render(read=read, unread=read, moved=moved, applied=moved, answered=2,
                              limit=900)
    assert len(text) <= 900
    assert "and " in text and "more" in text
    assert not text.endswith("…")
    assert "- Posts he published: not recorded" in text
    assert "- Operator requests he answered himself: 2" in text
    for line in text.splitlines()[2:]:
        assert line.startswith("- ")                   # no line was cut into a fragment


# --- the shortlist tool ---------------------------------------------------------------------

def _rows() -> dict[str, dict[str, Any]]:
    return {j["job_id"][:8]: j for j in JOBS}


def test_apply_is_refused_for_estimated_missing_or_low_pay() -> None:
    assert "estimate" in (st.apply_problem(JOBS[2], 25.0) or "")
    assert "no pay figure" in (st.apply_problem(JOBS[1], 25.0) or "")
    assert "under the 30 LPA bar" in (st.apply_problem(JOBS[3], 30.0) or "")
    assert st.apply_problem(JOBS[3], 25.0) is None


def test_the_gate_names_the_row_it_refuses() -> None:
    picks: list[st.Pick] = [
        {"job_id": VISA[:8], "action": "apply", "next_step": "Apply on the posting."},
        {"job_id": CLOUDFLARE[:8], "action": "verify_pay", "next_step": "Check the posting."},
        {"job_id": RIPPLING[:8], "action": "apply", "next_step": "Apply on the careers page."},
        {"job_id": "deadbeef", "action": "referral", "next_step": "Ask."},
    ]
    problems = st.pick_problems(picks, _rows(), 25.0)
    assert any(p.startswith("Visa, Software Engineer") and "estimate" in p for p in problems)
    assert any(p.startswith("Cloudflare,") and "closed" in p for p in problems)
    assert any("deadbeef: no such row" in p for p in problems)
    assert not any("Rippling" in p for p in problems)
    assert st.pick_problems(picks[2:3], _rows(), 25.0) == []


def test_the_page_is_written_from_the_ledger_with_the_date_stamped_by_code() -> None:
    pick: st.Pick = {"job_id": RIPPLING[:8], "action": "apply",
                     "next_step": "Apply on the careers page today."}
    page = st.render_page("This week", [pick], _rows(), datetime(2026, 9, 25, tzinfo=UTC), 25.0)
    assert page.startswith("# This week\n\nWeek 2026-W39, written 2026-09-25 from the job ledger.")
    assert ("1. Rippling, Software Engineer I: 9/10, stated 28 LPA, status shortlisted,"
            " last live-checked 2026-09-24.") in page
    assert "Next (Apply): Apply on the careers page today." in page
    assert st.shortlist_path(date(2026, 9, 28)) == "projects/jobs/shortlist-2026-W40.md"


def _tool_ctx() -> Any:
    return types.SimpleNamespace(deps=HQDeps(agent="sage", run_id="run-1", vault_write_scopes=[]))


def _patch_tool(monkeypatch: pytest.MonkeyPatch, written: list[tuple[str, str]]) -> None:
    async def fetch(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        prefix = str(params[0]).rstrip("%")
        return [dict(j) for j in JOBS if j["job_id"].startswith(prefix)]

    async def write(path: str, content: str, *, actor: str) -> str:
        written.append((path, content))
        return path

    async def emit(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(st.db, "fetch", fetch)
    monkeypatch.setattr(st.memory, "write", write)
    monkeypatch.setattr(st, "emit", emit)
    monkeypatch.setattr(st, "_today", lambda: datetime(2026, 9, 25, 9, 0, tzinfo=UTC))


def test_file_shortlist_refuses_apply_on_estimated_pay_and_a_closed_row(monkeypatch) -> None:
    written: list[tuple[str, str]] = []
    _patch_tool(monkeypatch, written)
    tool = inspect.unwrap(st.file_shortlist)
    with pytest.raises(ModelRetry) as exc:
        asyncio.run(tool(_tool_ctx(), [
            {"job_id": VISA[:8], "action": "apply", "next_step": "Apply."},
            {"job_id": CLOUDFLARE, "action": "shortlist", "next_step": "Board it."},
        ], "Week 39"))
    text = str(exc.value)
    assert "Visa, Software Engineer (0.5-2 years band) (03ec912c): pay is an estimate" in text
    assert "Cloudflare, Software Engineer, AI Agents (b62d7768) is closed" in text
    assert written == []


def test_file_shortlist_writes_the_week_page_from_the_rows(monkeypatch) -> None:
    written: list[tuple[str, str]] = []
    _patch_tool(monkeypatch, written)
    tool = inspect.unwrap(st.file_shortlist)
    out = asyncio.run(tool(_tool_ctx(), [
        {"job_id": RIPPLING[:8], "action": "apply", "next_step": "Apply on the careers page."},
        {"job_id": BJAK[:8], "action": "verify_pay", "next_step": "Ask the pay range first."},
    ], "Week 39"))
    assert out == "filed 2 picks at projects/jobs/shortlist-2026-W39.md"
    path, content = written[0]
    assert path == "projects/jobs/shortlist-2026-W39.md"
    assert "author: sage" in content and "written 2026-09-25" in content
    assert "Rippling, Software Engineer I: 9/10, stated 28 LPA" in content
    assert "BJAK, Applied AI Engineer: 10/10, no figure" in content
    assert "Next (Verify pay): Ask the pay range first." in content


def test_sage_holds_the_tool_and_its_cron_slot_requires_it() -> None:
    from hq.loader import scan
    from hq.tools.registry import TOOL_REGISTRY

    sage = scan()["sage"]
    assert "file_shortlist" in sage.base_tool_names()
    assert next(e for e in sage.cron if e.skill == "job-shortlist").requires == "file_shortlist"
    assert "file_shortlist" in engine.ARTIFACT_TOOLS
    assert TOOL_REGISTRY["file_shortlist"].private
    skill = (sage.dir / "skills" / "job-shortlist" / "SKILL.md").read_text()
    assert "file_shortlist" in skill and "vault_write" not in skill.split("never by")[0]


# --- the brief every sage cron entry dispatches with ---------------------------------------

def _patch_readers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]] | None:
        if "GROUP BY kind" in sql:
            return [{"kind": "course", "n": 3}]
        if "FILTER (WHERE created_at" in sql:
            return [{"written": 7, "read": 3}]
        if "first_seen" in sql:
            return [{"found": 42, "strong": 18, "applied": 0}]
        if "operator_requests" in sql:
            return [{"n": 0}]
        if "FROM hq.tasks" in sql:
            return [{"id": "b3be878b-0000-0000-0000-000000000000", "status": "done"}]
        if "SELECT title, kind, read_at FROM hq.lessons" in sql:
            return [{"title": "Phase 2B — Decoding and context", "kind": "course", "read_at": None}]
        if "FROM hq.jobs" in sql:
            return [dict(j) for j in JOBS if "status = ANY" not in sql or j["status"] != "closed"]
        return None

    async def owner(now: datetime | None = None, days: int = 14) -> str:
        return owner_state.render(read=[], unread=[], moved=[], applied=[], answered=0)

    monkeypatch.setattr(ct, "_rows", rows)
    monkeypatch.setattr(ct, "_daily_notes",
                        lambda limit: [("2026-09-24", NOTE_LABEL), ("2026-09-22", NOTE_HEADING)])
    monkeypatch.setattr(ct, "_read_decisions", lambda: DECISIONS)
    monkeypatch.setattr(ct, "line_added_in_git", lambda line, rel_path=ct.DECISIONS_PATH: None)
    monkeypatch.setattr(ct.owner_state, "block", owner)
    monkeypatch.setattr(ct.memory, "today", lambda: date(2026, 9, 25))


@pytest.mark.parametrize("skill", sorted(ct.SECTIONS))
def test_every_sage_skill_brief_ends_with_the_block(monkeypatch, skill: str) -> None:
    _patch_readers(monkeypatch)
    step = inspect.unwrap(engine._cron_brief_step)
    brief = asyncio.run(step("sage", "Do the thing.", skill))
    assert brief.startswith("Do the thing.\n\n## The " + skill + " skill\n\n")
    assert brief.index(ct.HEADING) > brief.index(f"## The {skill} skill")
    block = brief[brief.index(ct.HEADING):]
    assert "Read it as fact; do not count or recall these yourself." in block
    assert "- Unread lessons: 3 (course 3)" in block
    sections = ct.SECTIONS[skill]
    assert ("Last note (2026-09-24) led with: “a cost dashboard" in block) == ("lead" in sections)
    assert ("- [closed] 09-24 (also 09-22): “Apply to Cloudflare" in block) == ("needs" in sections)
    assert ("- [not in any ledger] 09-22: “Post the return post on X.”" in block) == ("needs" in sections)
    assert ("task b3be878b done" in block) == ("needs" in sections)
    assert ("propose a default" in block) == ("decisions" in sections)   # raised 2026-09-10
    assert (owner_state.HEADING in block) == ("owner" in sections)
    assert ("Candidate rows" in block) == ("shortlist" in sections)
    if "shortlist" in sections:
        assert "b62d7768" not in block and "9fe6f9a9 BJAK" in block


def test_a_brief_without_a_skill_or_for_another_agent_carries_no_block(monkeypatch) -> None:
    _patch_readers(monkeypatch)
    step = inspect.unwrap(engine._cron_brief_step)
    assert asyncio.run(step("sage", "Write the note.")) == "Write the note."
    from hq.config import settings

    skill = min(p.name for p in (settings().agents_dir / "hunter" / "skills").iterdir())
    hunter = asyncio.run(step("hunter", "Hunt.", skill))
    assert ct.HEADING not in hunter and f"## The {skill} skill" in hunter


def test_a_block_that_cannot_be_built_does_not_stop_the_night(monkeypatch) -> None:
    async def boom(skill: str, now: datetime | None = None) -> str:
        raise RuntimeError("vault gone")

    assert asyncio.run(ct.for_skill("weekly-plan")) == ""    # no sections: no readers touched
    monkeypatch.setattr(ct, "build", boom)
    text = asyncio.run(ct.for_skill("daily-note"))
    assert text.startswith(ct.HEADING) and "could not be read" in text


# --- the regression set carries the block as data --------------------------------------------

def test_regression_cases_carry_a_canned_continuity_block() -> None:
    cases = {c.id: c for c in regress.load_cases("sage")}
    note = cases["sage-daily-note-does-not-lead-with-last-night"]
    assert note.skill == "daily-note" and note.continuity.startswith(ct.HEADING)
    shortlist = cases["sage-shortlist-no-apply-without-stated-pay"]
    assert shortlist.skill == "job-shortlist" and "estimated" in shortlist.continuity
    assert shortlist.expect.args_not_match["file_shortlist"]
    from hq import loader
    from hq.config import settings

    spec = loader.parse_job_md(settings().agents_dir / "sage")
    brief = regress._brief(note, spec)
    assert brief.endswith(note.continuity.strip())
    assert brief.index(ct.HEADING) > brief.index("## The daily-note skill")


def _skill_text(name: str) -> str:
    from hq.config import settings

    return (settings().agents_dir / "sage" / "skills" / name / "SKILL.md").read_text()


# --- the shortlist: a next step never says apply unless the action is apply -------------------

@pytest.mark.parametrize("action", ["verify_pay", "referral", "shortlist"])
def test_a_next_step_that_says_apply_is_refused_when_the_action_is_not(action: str) -> None:
    pick: st.Pick = {"job_id": BJAK[:8], "action": action,  # type: ignore[typeddict-item]
                     "next_step": "Check the posting for pay, then apply this week."}
    problems = st.pick_problems([pick], _rows(), 25.0)
    assert problems == [(f"BJAK, Applied AI Engineer (9fe6f9a9): the next step says apply but"
                         f" the action is {action}; say what to verify first")]
    ok: st.Pick = {"job_id": BJAK[:8], "action": action,  # type: ignore[typeddict-item]
                   "next_step": "Ask the recruiter for the pay band; the application form can wait."}
    assert st.pick_problems([ok], _rows(), 25.0) == []


def test_apply_in_the_next_step_of_an_apply_pick_is_fine() -> None:
    pick: st.Pick = {"job_id": RIPPLING[:8], "action": "apply",
                     "next_step": "Apply on the careers page today."}
    assert st.pick_problems([pick], _rows(), 25.0) == []


def test_file_shortlist_sends_back_a_verify_pay_pick_that_says_apply(monkeypatch) -> None:
    written: list[tuple[str, str]] = []
    _patch_tool(monkeypatch, written)
    tool = inspect.unwrap(st.file_shortlist)
    with pytest.raises(ModelRetry) as exc:
        asyncio.run(tool(_tool_ctx(), [
            {"job_id": VISA[:8], "action": "verify_pay",
             "next_step": "Before you apply, confirm the band on the posting."},
        ], "Week 39"))
    assert "the next step says apply but the action is verify_pay" in str(exc.value)
    assert written == []
    assert "code refuses one that tells him to apply" in " ".join(
        _skill_text("job-shortlist").split())


# --- the gates: what the next course phase and the next article wait on ----------------------

PHASE_3A = "Phase 3A — Prefix caching"
PHASE_2B = "Phase 2B — Decoding and context"


def _gated_ledger() -> ct.Ledger:
    ledger = _ledger()
    ledger.lessons = [
        {"title": PHASE_3A, "kind": "course", "read_at": None},
        {"title": PHASE_2B, "kind": "course", "read_at": None},
        {"title": "Phase 2A — Scheduling and memory", "kind": "course",
         "read_at": datetime(2026, 9, 22, tzinfo=UTC)},
    ]
    ledger.gates = ct.gate_roles(ct.Gate(PHASE_3A, "2026-09-24"),
                                 ct.Gate("Why the bill doubled", "2026-09-23"))
    return ledger


def test_the_gate_lines_name_the_newest_unread_lesson_or_nothing() -> None:
    lines = ct.render_gates(ct.Gate(PHASE_3A, "2026-09-24"),
                            ct.Gate("Why the bill doubled", "2026-09-23"))
    assert lines == [
        f"- The next course phase waits on: “{PHASE_3A}” (unread since 2026-09-24)",
        "- The next article waits on: “Why the bill doubled” (unread since 2026-09-23)"]
    assert ct.render_gates(ct.Gate(), ct.Gate()) == [
        "- The next course phase waits on: nothing: an unread lesson does not hold it",
        "- The next article waits on: nothing"]
    assert ct.render_gates(None, None) == [
        "- The next course phase waits on: not readable",
        "- The next article waits on: not readable"]
    failed = ct.render_gates(ct.Gate(PHASE_2B, "2026-09-22", failed=True), ct.Gate())[0]
    assert failed.endswith("(failed his review; his decision on the Courses page)")


def test_a_gate_row_is_read_the_way_the_engine_reads_it() -> None:
    # Since 2026-10-06 only a failed review holds the course; unread does not.
    assert "kind = 'course' AND review_status = 'failed'" in ct.COURSE_GATE_SQL
    assert "read_at IS NULL OR" not in ct.COURSE_GATE_SQL
    assert "ORDER BY lesson_date DESC LIMIT 1" in ct.COURSE_GATE_SQL
    assert not hasattr(ct, "TOPIC_GATE_SQL")
    assert ct._gate(None) is None and ct._gate([]) == ct.Gate()
    row = {"title": PHASE_2B, "lesson_date": date(2026, 9, 22), "review_status": "failed",
           "unread": False}
    assert ct._gate([row]) == ct.Gate(PHASE_2B, "2026-09-22", failed=True)
    # A failed lesson he has not read yet still needs his decision.
    unread = ct._gate([dict(row, unread=True)])
    assert unread is not None and unread.failed is True


def test_an_unread_lesson_that_is_not_the_gate_is_marked_so() -> None:
    ledger = _gated_ledger()
    line = "Read and mark Phase 2B. It still gates both learning chains."
    status, closed = ct.line_status(line, ledger)
    assert status == f"lesson “{PHASE_2B}” unread, not the gate" and closed is False
    assert ct.not_the_gate(line, ledger)
    need = ct.Need("2026-09-24", line, status, closed, not_gate=ct.not_the_gate(line, ledger))
    assert ct.render_needs([need]) == [
        f"- [unread, not the gate] 09-24: “{line}” -> lesson “{PHASE_2B}” unread, not the gate"]
    gate_line = "Read Phase 3A tonight."
    status, closed = ct.line_status(gate_line, ledger)
    assert status == f"lesson “{PHASE_3A}” unread, gates the next course phase"
    assert not ct.not_the_gate(gate_line, ledger)
    assert not ct.not_the_gate("Read Phase 2B and Phase 3A.", ledger)   # the gate keeps it open
    assert not ct.not_the_gate("Read and mark the Phase 2A lesson.", ledger)   # read: closed


def test_without_readable_gates_no_lesson_is_called_not_the_gate() -> None:
    ledger = _gated_ledger()
    ledger.gates = None
    status, _ = ct.line_status("Read and mark Phase 2B.", ledger)
    assert status == f"lesson “{PHASE_2B}” unread"
    assert ct.gate_roles(None, ct.Gate()) is None


def _patch_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_readers(monkeypatch)
    plain = ct._rows

    async def rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]] | None:
        if sql == ct.COURSE_GATE_SQL:
            return [{"title": PHASE_3A, "lesson_date": date(2026, 9, 24),
                     "review_status": "passed", "unread": True}]
        if "SELECT title, kind, read_at FROM hq.lessons" in sql:
            return [{"title": PHASE_3A, "kind": "course", "read_at": None},
                    {"title": PHASE_2B, "kind": "course", "read_at": None}]
        return await plain(sql, params)

    monkeypatch.setattr(ct, "_rows", rows)


@pytest.mark.parametrize("skill", sorted(ct.SECTIONS))
def test_the_gate_lines_reach_the_note_the_review_and_the_consolidation(
        monkeypatch, skill: str) -> None:
    _patch_gates(monkeypatch)
    block = asyncio.run(ct.build(skill, now=datetime(2026, 9, 25, 18, tzinfo=UTC)))
    course = f"- The next course phase waits on: “{PHASE_3A}” (unread since 2026-09-24)"
    wanted = skill in {"daily-note", "weekly-review", "consolidate"}
    assert (course in block) == wanted
    assert ("- The next article waits on: nothing" in block) == wanted
    assert ("- [unread, not the gate] 09-24: “Read and mark Phase 2B." in block) == (
        "needs" in ct.SECTIONS[skill])


def test_the_daily_note_skill_names_a_gate_only_from_the_gate_lines() -> None:
    skill = " ".join(_skill_text("daily-note").split())
    assert "The next course phase waits on" in skill and "The next article waits on" in skill
    assert "`[unread, not the gate]`" in skill
