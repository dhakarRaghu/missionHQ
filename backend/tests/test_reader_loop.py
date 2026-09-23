"""Phase 9, the reader and value loop: a tap per concept, the signal the next
outline reads, the nightly bundle on its own branch, and the weekly numbers."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from hq import learning_pipeline as learning
from hq import lesson_kit, reader_export, signals, value
from hq import lesson_writer as lw
from hq.api import learning as learning_api
from hq.api import reader as reader_api
from hq.tools import learning_tools as lt

CONCEPTS = ('<ol class="concepts"><li id="c1"><b>A batch rebuilt every iteration'
            ' never makes a short request wait</b><span>predict tail latency</span></li>'
            '<li id="c2"><b>KV &amp; memory grow with <code>context</code></b><span>size it</span></li></ol>')
BODY = (CONCEPTS + '<h2 data-concept="c1">Why</h2><p>one</p>'
        '<h2 data-concept="c2">How much</h2><p>two</p><h2 data-kind="sources">Sources</h2>')


# --- the tap, inside the page ----------------------------------------------

def _scripts(page: str) -> str:
    return "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", page, re.DOTALL))


def test_a_page_with_concepts_carries_the_tap_and_it_can_only_post_to_its_parent() -> None:
    page = lesson_kit.wrap_page(BODY, title="Iteration-level scheduling")
    script = _scripts(page)

    assert page.count(lesson_kit.TAPS_MARKER) == 1
    assert "window.parent.postMessage({hq:'concept',concept:c,verdict:v},'*')" in script
    assert "'got_it','Got it'" in script and "'lost_me','Lost me'" in script
    # Nothing in the page can store or send: no network, no storage.
    for banned in ("fetch(", "XMLHttpRequest", "localStorage", "sessionStorage",
                   "indexedDB", "document.cookie", "sendBeacon", "WebSocket"):
        assert banned not in page, banned
    # The tap never becomes the reason the page check refuses a page.
    assert lt.page_script_problems(page) == ""


def test_a_page_without_a_concept_list_shows_no_tap() -> None:
    page = lesson_kit.wrap_page("<h2>Why</h2><p>body</p>", title="Old style")
    assert lesson_kit.TAPS_MARKER not in page
    assert "postMessage" not in page
    assert lesson_kit.with_taps(page) == page


def test_an_older_page_with_concepts_gets_the_tap_once_when_served() -> None:
    older = f"<!DOCTYPE html><html><head><title>x</title></head><body><main>{BODY}</main></body></html>"
    served = learning_api.harden_page(older)

    assert served.count(lesson_kit.TAPS_MARKER) == 1
    assert served.index(lesson_kit.TAPS_MARKER) < served.index("</body>")
    assert "Content-Security-Policy" in served
    assert lesson_kit.with_taps(served) == served
    # A page wrap_page wrote already has it; serving it adds nothing.
    fresh = lesson_kit.wrap_page(BODY, title="t")
    assert learning_api.harden_page(fresh).count(lesson_kit.TAPS_MARKER) == 1


# --- the receiver's endpoint ------------------------------------------------

@pytest.mark.parametrize("concept,verdict", [
    ("c1", "got_it"), ("c12", "lost_me"), ("c99", "got_it")])
def test_a_tap_is_accepted_only_in_its_one_shape(concept: str, verdict: str) -> None:
    assert signals.validate(concept, verdict) == (concept, verdict)


@pytest.mark.parametrize("concept,verdict", [
    ("c100", "got_it"), ("C1", "got_it"), ("c1 ", "got_it"), ("x1", "got_it"), ("", "got_it"),
    ("c1", "meh"), ("c1", "GOT_IT"), (1, "got_it"), ("c1", None),
    ("c1'); DROP TABLE hq.lessons;--", "got_it")])
def test_anything_else_from_the_page_is_refused(concept: Any, verdict: Any) -> None:
    with pytest.raises(signals.SignalRefused):
        signals.validate(concept, verdict)


def test_the_signal_endpoint_validates_then_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, tuple]] = []
    lesson = "0b8f3c5e-8f6a-4c0e-9a55-1b2c3d4e5f60"

    async def fetchone(sql: str, params: tuple = ()) -> dict[str, Any] | None:
        seen.append((sql, params))
        if params[-1] != lesson:
            return None
        return {"lesson_id": lesson, "concept": params[0], "verdict": params[1], "via": params[2]}

    monkeypatch.setattr(signals.db, "fetchone", fetchone)
    add = learning_api.add_concept_signal

    row = asyncio.run(add(lesson, learning_api.SignalBody(concept="c2", verdict="lost_me")))
    assert row == {"lesson_id": lesson, "concept": "c2", "verdict": "lost_me", "via": "console"}
    assert "INSERT INTO hq.concept_signals" in seen[0][0]
    assert "FROM hq.lessons WHERE id = %s" in seen[0][0]   # only a real lesson

    for bad_lesson, body, status in [
        (lesson, learning_api.SignalBody(concept="c2", verdict="maybe"), 400),
        (lesson, learning_api.SignalBody(concept="s2", verdict="got_it"), 400),
        ("not-a-uuid", learning_api.SignalBody(concept="c1", verdict="got_it"), 400),
        ("11111111-2222-3333-4444-555555555555",
         learning_api.SignalBody(concept="c1", verdict="got_it"), 404),
    ]:
        with pytest.raises(HTTPException) as err:
            asyncio.run(add(bad_lesson, body))
        assert err.value.status_code == status
    assert len(seen) == 2   # the refused shapes never reached the database


# --- the phone sends it back ------------------------------------------------

PHONE_FILE = "2026-09-22-inference-internals-phase-02b-decoding-context.html"
PHONE_LESSON = "0b8f3c5e-8f6a-4c0e-9a55-1b2c3d4e5f60"


class _FakeDb:
    """hq.db for one lesson, recording every statement."""

    def __init__(self, kind: str = "course") -> None:
        self.kind = kind
        self.seen: list[tuple[str, tuple]] = []

    async def fetchone(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        self.seen.append((sql, params))
        if "FROM hq.lessons WHERE html_path" in sql:
            return {"id": PHONE_LESSON} if params[2] == f"/{PHONE_FILE}" else None
        if sql.startswith("UPDATE hq.lessons"):
            if params[0] != PHONE_LESSON:
                return None
            return {"id": PHONE_LESSON, "title": "Decoding", "kind": self.kind,
                    "course_slug": "phase-02b" if self.kind == "course" else ""}
        if sql.startswith("UPDATE hq.course_phases"):
            return {"lesson_id": PHONE_LESSON, "title": "Decoding"}
        if "INSERT INTO hq.concept_signals" in sql:
            return {"lesson_id": params[-1], "concept": params[0], "verdict": params[1],
                    "via": params[2]}
        return None

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        self.seen.append((sql, params))
        return [{"id": PHONE_LESSON}]

    async def execute(self, sql: str, params: tuple = ()) -> None:
        self.seen.append((sql, params))


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> _FakeDb:
    fake = _FakeDb()
    for name in ("fetchone", "fetch", "execute"):
        monkeypatch.setattr(learning_api.db, name, getattr(fake, name))
    return fake


@pytest.mark.parametrize("file", [
    "../etc/passwd", "lessons/x.html", "x.htm", ".html", "a.b.html", "x.html ", "",
    "x.html?y", "%2e%2e.html", "a" * 201 + ".html", "x\\y.html"])
def test_the_phone_names_a_lesson_only_by_its_page_file(fake_db: _FakeDb, file: str) -> None:
    for call in (reader_api.reader_mark_read(reader_api.ReadBody(file=file[:220])),
                 reader_api.reader_signal(reader_api.PhoneSignalBody(
                     file=file[:220], concept="c1", verdict="got_it"))):
        with pytest.raises(HTTPException) as err:
            asyncio.run(call)
        assert err.value.status_code == 400
    assert fake_db.seen == []   # a refused name never reaches the database


def test_a_phone_tap_is_validated_then_stored_as_from_the_phone(fake_db: _FakeDb) -> None:
    body = reader_api.PhoneSignalBody
    row = asyncio.run(reader_api.reader_signal(
        body(file=PHONE_FILE, concept="c2", verdict="lost_me")))
    assert row == {"lesson_id": PHONE_LESSON, "concept": "c2", "verdict": "lost_me",
                   "via": "phone"}
    assert any("INSERT INTO hq.concept_signals" in sql for sql, _ in fake_db.seen)

    fake_db.seen.clear()
    for concept, verdict in [("c100", "got_it"), ("C1", "got_it"), ("c1", "meh"),
                             ("c1", "GOT_IT")]:
        with pytest.raises(HTTPException) as err:
            asyncio.run(reader_api.reader_signal(
                body(file=PHONE_FILE, concept=concept, verdict=verdict)))
        assert err.value.status_code == 400
    assert fake_db.seen == []

    with pytest.raises(HTTPException) as err:
        asyncio.run(reader_api.reader_signal(
            body(file="2026-01-01-nothing.html", concept="c1", verdict="got_it")))
    assert err.value.status_code == 404


def test_a_phone_read_goes_through_the_consoles_mark_read(
        fake_db: _FakeDb, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real = learning_api.mark_read

    async def spy(lesson_id: str) -> dict[str, Any] | None:
        calls.append(lesson_id)
        return await real(lesson_id)

    monkeypatch.setattr(learning_api, "mark_read", spy)

    out = asyncio.run(reader_api.reader_mark_read(reader_api.ReadBody(file=PHONE_FILE)))
    assert out == {"ok": True, "title": "Decoding"}
    asyncio.run(learning_api.mark_phase_read("inference-internals", "phase-02b"))
    asyncio.run(learning_api.mark_lesson_read("2026-09-22", "course"))
    assert calls == [PHONE_LESSON] * 3   # phone, course page, Learn page: one function

    with pytest.raises(HTTPException) as err:
        asyncio.run(reader_api.reader_mark_read(
            reader_api.ReadBody(file="2026-01-01-nothing.html")))
    assert err.value.status_code == 404


def test_reading_a_course_lesson_sets_the_lesson_and_its_phase(fake_db: _FakeDb) -> None:
    asyncio.run(reader_api.reader_mark_read(reader_api.ReadBody(file=PHONE_FILE)))
    writes = [(sql, params) for sql, params in fake_db.seen if sql.startswith("UPDATE")]
    assert writes[0][0].startswith("UPDATE hq.lessons SET read_at = coalesce(read_at, now())")
    assert writes[0][1] == (PHONE_LESSON,)
    assert writes[1][0].startswith("UPDATE hq.course_phases SET read_at")
    assert writes[1][1] == (PHONE_LESSON, "phase-02b")
    assert writes[1][0].endswith("WHERE lesson_id = %s::uuid OR slug = %s")

    fake_db.seen.clear()
    fake_db.kind = "topic"
    asyncio.run(reader_api.reader_mark_read(reader_api.ReadBody(file=PHONE_FILE)))
    assert not any("hq.course_phases" in sql for sql, _ in fake_db.seen)
    assert asyncio.run(learning_api.mark_read("not-a-uuid")) is None


def test_the_reader_endpoints_require_the_owner() -> None:
    from hq.api.deps import require_auth
    assert any(d.dependency is require_auth for d in reader_api.router.dependencies)


def test_the_current_answer_is_the_latest_tap() -> None:
    rows = [{"concept": "c1", "verdict": "lost_me"}, {"concept": "c2", "verdict": "got_it"},
            {"concept": "c1", "verdict": "got_it"}]
    assert signals.latest(rows) == {"c1": "got_it", "c2": "got_it"}


def test_the_migration_is_numbered_after_the_parallel_one() -> None:
    sql = (Path(__file__).parents[1] / "migrations" / "035_concept_signals.sql").read_text()
    assert "CREATE TABLE hq.concept_signals" in sql
    assert "CHECK (verdict IN ('got_it', 'lost_me'))" in sql
    assert "REFERENCES hq.lessons(id)" in sql


# --- the writer reads it ------------------------------------------------------

def test_a_concept_he_lost_is_named_for_the_next_outline_with_its_claim() -> None:
    claims = signals.concept_claims(lesson_kit.wrap_page(BODY, title="t"))
    assert claims["c2"] == "KV & memory grow with context"

    rows = [{"phase_title": "Phase 2A: scheduling", "concept": "c2", "html_path": "a.html"},
            {"phase_title": "Phase 2A: scheduling", "concept": "c3", "html_path": "a.html"}]
    pages: list[str] = []

    def claims_for(path: str) -> dict[str, str]:
        pages.append(path)
        return claims

    text = signals.lost_section(rows, claims_for)
    assert text.startswith(f"## {signals.LOST_HEADING}\n\n")
    assert "- Phase 2A: scheduling, c2: KV & memory grow with context" in text
    assert "- Phase 2A: scheduling, c3" in text
    assert pages == ["a.html"]     # one page read per lesson
    assert signals.lost_section([]) == ""
    many = [{"phase_title": "P", "concept": f"c{i}", "html_path": ""} for i in range(1, 30)]
    assert signals.lost_section(many).count("\n- ") == signals.LOST_ME_MAX


def test_a_signal_that_cannot_be_read_never_stops_a_lesson(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(course: str, slug: str) -> list[dict[str, Any]]:
        raise RuntimeError('relation "hq.concept_signals" does not exist')

    monkeypatch.setattr(signals, "lost_before", broken)
    assert asyncio.run(signals.lost_material("inference-internals", "phase-02b")) == ""


def test_the_course_outline_material_carries_what_lost_him(monkeypatch: pytest.MonkeyPatch) -> None:
    from hq.tools import review_tools

    async def note(slug: str) -> tuple[str, str]:
        return "quarantine/note.md", "the study note"

    async def sequence(course: str, slug: str) -> str:
        return "Earlier phases (known to him):\n- Phase 2A"

    async def nothing(slug: str) -> str:
        return ""

    asked: list[tuple[str, str]] = []

    async def lost(course: str, slug: str) -> str:
        asked.append((course, slug))
        return f"## {signals.LOST_HEADING}\n\n- Phase 2A, c2: KV grows with context"

    monkeypatch.setattr(lt, "read_course_source_text", lambda slug: "# His phase")
    monkeypatch.setattr(review_tools, "_study_note", note)
    monkeypatch.setattr(lw, "_course_sequence", sequence)
    monkeypatch.setattr(lw, "_articles_on", nothing)
    monkeypatch.setattr(signals, "lost_material", lost)
    payload = {"workflow": learning.WORKFLOW, "stage": learning.COURSE_WRITTEN_STAGE,
               "slug": "phase-02b", "course": "inference-internals", "title": "Phase 2B"}

    m = asyncio.run(lw.gather(payload))
    assert asked == [("inference-internals", "phase-02b")]
    assert signals.LOST_HEADING in m.prompt
    assert m.prompt.index(signals.LOST_HEADING) < m.prompt.index("## Hunter's study note")


# --- the nightly bundle on the reader branch ------------------------------------

def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    for key, val in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                     "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                     "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
                     "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(key, val)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    (work / "frontend" / "public" / "reader" / "lessons").mkdir(parents=True)
    (work / "frontend" / "app.tsx").write_text("export const app = 1;\n")
    (work / "frontend" / "public" / "reader" / "index.json").write_text("{}\n")
    (work / "frontend" / "public" / "reader" / "lessons" / "gone.html").write_text("old\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "app")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "origin", "main")
    # His own uncommitted work, which the publish must never pick up.
    (work / "frontend" / "app.tsx").write_text("export const app = 2; // half done\n")
    (work / "notes.md").write_text("private draft\n")
    return work, remote


def _bundle(root: Path, lessons: dict[str, str], built_at: str) -> Path:
    bundle = root / "bundle"
    if bundle.exists():
        import shutil
        shutil.rmtree(bundle)
    (bundle / "lessons").mkdir(parents=True)
    for name, text in lessons.items():
        (bundle / "lessons" / name).write_text(text)
    index = {"built_at": built_at, "courses": [], "articles": [{"file": n} for n in sorted(lessons)]}
    (bundle / "index.json").write_text(json.dumps(index))
    return bundle


def test_the_bundle_goes_to_the_reader_branch_only_when_it_changed(
        repo: tuple[Path, Path], tmp_path: Path) -> None:
    work, remote = repo
    head, status = _git(work, "rev-parse", "HEAD"), _git(work, "status", "--porcelain")
    index_before = (work / ".git" / "index").read_bytes()

    first = reader_export.publish_to_branch(
        _bundle(tmp_path, {"a.html": "<p>a</p>"}, "2026-09-23T03:00:00"), repo=work)
    assert first["error"] == "" and first["committed"] and first["pushed"]
    assert _git(remote, "rev-parse", "refs/heads/reader") == first["committed"]

    tree = _git(work, "ls-tree", "-r", "--name-only", "reader").splitlines()
    assert "frontend/public/reader/lessons/a.html" in tree
    assert "frontend/public/reader/lessons/gone.html" not in tree   # the bundle is replaced
    assert "frontend/app.tsx" in tree and "notes.md" not in tree
    assert _git(work, "show", "reader:frontend/app.tsx") == "export const app = 1;"  # pushed main, not his draft

    # Same lessons, a new built_at: no commit, no push.
    again = reader_export.publish_to_branch(
        _bundle(tmp_path, {"a.html": "<p>a</p>"}, "2026-09-24T03:00:00"), repo=work)
    assert again["error"] == "" and again["committed"] == "" and not again["pushed"]
    assert _git(work, "rev-parse", "reader") == first["committed"]

    # A changed lesson: exactly one new commit, on top of the last one.
    changed = reader_export.publish_to_branch(
        _bundle(tmp_path, {"a.html": "<p>a, rebuilt</p>", "b.html": "<p>b</p>"},
                "2026-09-25T03:00:00"), repo=work)
    assert changed["committed"] and changed["pushed"]
    assert _git(work, "rev-list", "--count", "reader") == "2"
    assert _git(work, "rev-parse", "reader^") == first["committed"]
    assert _git(remote, "rev-parse", "refs/heads/reader") == changed["committed"]

    # main, HEAD, his index and his working tree are exactly as they were.
    assert _git(work, "rev-parse", "HEAD") == head
    assert _git(work, "rev-parse", "main") == head
    assert _git(work, "symbolic-ref", "HEAD") == "refs/heads/main"
    assert (work / ".git" / "index").read_bytes() == index_before
    assert _git(work, "status", "--porcelain") == status
    assert _git(remote, "rev-parse", "refs/heads/main") == head


def test_a_push_that_fails_is_logged_and_retried_next_night(
        repo: tuple[Path, Path], tmp_path: Path) -> None:
    work, remote = repo
    _git(work, "remote", "set-url", "origin", str(tmp_path / "nowhere.git"))
    bundle = _bundle(tmp_path, {"a.html": "<p>a</p>"}, "2026-09-23T03:00:00")

    failed = reader_export.publish_to_branch(bundle, repo=work)   # must not raise
    assert failed["committed"] and not failed["pushed"] and "push" in failed["error"]

    _git(work, "remote", "set-url", "origin", str(remote))
    retried = reader_export.publish_to_branch(bundle, repo=work)
    assert retried["committed"] == "" and retried["pushed"] and retried["error"] == ""
    assert _git(remote, "rev-parse", "refs/heads/reader") == failed["committed"]


def test_the_fingerprint_ignores_only_built_at(tmp_path: Path) -> None:
    one = reader_export.fingerprint(_bundle(tmp_path / "1", {"a.html": "a"}, "t1"))
    two = reader_export.fingerprint(_bundle(tmp_path / "2", {"a.html": "a"}, "t2"))
    three = reader_export.fingerprint(_bundle(tmp_path / "3", {"a.html": "A"}, "t1"))
    assert one == two != three


def test_the_nightly_publish_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def build(target: Path | None = None) -> dict[str, Any]:
        raise ConnectionError("database is asleep")

    monkeypatch.setattr(reader_export, "build", build)
    out = asyncio.run(reader_export.publish_nightly())
    assert out["committed"] == "" and "asleep" in out["error"]


# --- the weekly value report ------------------------------------------------------

NOW = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)


def test_an_empty_week_is_zeros_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fetch(sql: str, params: Any = ()) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(value.db, "fetch", fetch)
    monkeypatch.setattr(value, "_read_ideas", lambda: None)
    r = asyncio.run(value.week_report(NOW))

    assert r["lessons"] == {"written": 0, "read": 0, "written_and_read": 0, "written_by_kind": {}}
    assert (r["taps"]["got_it"], r["taps"]["lost_me"]) == (0, 0)
    assert r["jobs"] == {"moved": 0, "updates": 0, "now": {}}
    assert r["spend"]["total_usd"] == 0 and r["cost_per_lesson_usd"] is None
    assert r["content"] == {"ideas": "not recorded", "drafted": 0, "posted": "not recorded"}
    assert "no lessons written" in value.format_report(r)


def test_a_schema_without_the_tables_still_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fetch(sql: str, params: Any = ()) -> list[dict[str, Any]]:
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(value.db, "fetch", fetch)
    monkeypatch.setattr(value, "_read_ideas", lambda: None)
    r = asyncio.run(value.week_report(NOW))
    assert r["lessons"]["written"] == 0 and r["taps"]["recorded"] is False
    assert "Concept taps: not recorded" in value.format_report(r)


def test_the_week_is_counted_from_its_rows() -> None:
    since = NOW - timedelta(days=7)
    day = timedelta(days=1)
    r = value.summarize(
        since=since, until=NOW,
        lessons=[{"kind": "course", "created_at": NOW - day, "read_at": NOW},
                 {"kind": "topic", "created_at": NOW - 2 * day, "read_at": None},
                 {"kind": "topic", "created_at": NOW - 20 * day, "read_at": NOW - day}],
        taps=[{"verdict": "got_it", "n": 5}, {"verdict": "lost_me", "n": 2}],
        job_events=[{"payload": {"job_id": "j1", "fields": ["status = %s"]}},
                    {"payload": {"job_id": "j1", "fields": ["status = %s", "notes = %s"]}},
                    {"payload": {"job_id": "j2", "fields": ["notes = %s"]}},
                    {"payload": {"job_id": "j3", "fields": ["status = %s"]}}],
        job_status={"j1": "applied", "j3": "shortlisted"},
        spend=[{"agent": "tutor", "cost": 3.0}, {"agent": "hunter", "cost": 1.5}],
        ideas=6, drafted=1)

    assert r["lessons"] == {"written": 2, "read": 2, "written_and_read": 1,
                            "written_by_kind": {"course": 1, "topic": 1}}
    assert r["taps"]["got_it"] == 5 and r["taps"]["lost_me"] == 2
    assert r["jobs"] == {"moved": 2, "updates": 4, "now": {"applied": 1, "shortlisted": 1}}
    assert r["spend"]["total_usd"] == 4.5 and r["cost_per_lesson_usd"] == 1.5
    text = value.format_report(r)
    assert "2 written, 2 read" in text and "5 got it, 2 lost me" in text
    assert "Jobs you moved: 2 (now applied 1, shortlisted 1)" in text
    assert "6 ideas, 1 drafted, posted not recorded" in text
    assert "$1.50 per lesson written" in text


def test_ideas_are_counted_in_the_batches_of_the_week() -> None:
    md = ("---\ntitle: ideas\n---\n# Content ideas\n\n"
          "## 2026-09-22 — tonight\n1. one\n2. two\n\n"
          "## 2026-09-10\n1. old\n\n"
          "## 2026-09-20\n1. three\n- not numbered\n")
    assert value.count_ideas(md, date(2026, 9, 16), date(2026, 9, 23)) == 3
    assert value.count_ideas(None, date(2026, 9, 16), date(2026, 9, 23)) is None
