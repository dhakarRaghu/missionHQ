"""Posts for his site: measured the way a stranger reads, picked from what he
read, read once by a model that is not the writer. Nothing here calls a
model; the writer's two steps are faked."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from hq import lesson_writer as lw
from hq import runner
from hq import site_posts as sp
from hq.config import settings
from hq.tools import learning_tools as lt
from hq.tools.registry import HQDeps

# --- a post that passes, built so each test can break one thing -----------------

IN_SHORT = ("**In short:** Sticky routing doubled throughput on long prompts, from 16,000 to"
            " 46,000 input tokens a second on 10 servers. It gave nothing on short prompts,"
            " because there was no cached prefix to reuse.")
SITUATION = ("Your agent sends turn 37 of a session and the prompt is 99% the same as turn 36."
             " The load balancer sends it to a server that has never seen the session, so that"
             " server reads all 100,000 tokens again before it can answer.")


def _sentence(n: int) -> str:
    kinds = (
        f"Run {n} sent {n * 40} requests to the server that already held the cached prefix.",
        f"The prompt was read once, so the first token came {n % 7 + 2} seconds sooner.",
        (f"With round robin the same run reached {n * 11} tokens a second, because each"
         " server read the whole prompt again."),
    )
    return kinds[n % 3]


def _section(heading: str, first: int, count: int = 12) -> str:
    sentences = [_sentence(first + i) for i in range(count)]
    paragraphs = [" ".join(sentences[i:i + 3]) for i in range(0, count, 3)]
    return f"## {heading}\n\n" + "\n\n".join(paragraphs)


LIMITS = ("## Where this stops working\n\n"
          "The result does not hold when the shared prefix is short. With a 250 token prefix"
          " the router found nothing to reuse and both setups reached 7,000 tokens a second."
          " I did not check what happens when a server restarts and loses its cache.")
TABLE = ("| Setup | Requests at the knee | Input tokens a second |\n|---|---|---|\n"
         "| Sticky routing | 60 | 46,000 |\n| Round robin | 30 | 16,000 |")
TAKEAWAY = ("Check the length of your shared prefix before you change the router. A prefix of"
            " 70,000 tokens repays sticky routing, and a prefix of 250 tokens does not.")


def good(**swap: str) -> str:
    parts = {
        "in_short": IN_SHORT,
        "situation": SITUATION,
        "one": _section("A cold server reads the whole prompt again", 1),
        "two": _section("Sticky routing keeps a session on the server that has it", 11),
        "table": TABLE,
        "three": _section("The gain depends on how long the shared prefix is", 21),
        "four": _section("A queue threshold decides when to leave the warm server", 31),
        "limits": LIMITS,
        "takeaway": TAKEAWAY,
    }
    parts.update(swap)
    return "\n\n".join(p for p in parts.values() if p)


def test_a_well_shaped_post_passes_every_measured_check() -> None:
    post = good()
    assert sp.reader_problems(post, "brief") == []
    m = sp.measure(post)
    low, high = sp.SHAPES["brief"].words
    assert low <= m.words <= high
    assert m.in_short.startswith("Sticky routing doubled") and m.tables == 1 and m.has_limits
    assert len(m.headings) == 5 and "median" in m.line()


@pytest.mark.parametrize(("swap", "says"), [
    ({"in_short": ""}, "does not open with the result"),
    ({"in_short": "**In short:** It is faster."}, '"In short" block is'),
    ({"situation": "In this post I look at how routing works for agents that send long"
                   " prompts to a group of servers."}, "talks about the post"),
    ({"situation": "Have you ever wondered where your requests land? Most people have not"
                   " looked at it."}, "talks about the post"),
    ({"situation": "Where does turn 37 of your session land?"}, "opens on a question alone"),
    ({"limits": ""}, "no section says where this stops working"),
    ({"takeaway": TAKEAWAY + " Let me know what you think."}, "closes by asking"),
    ({"takeaway": TAKEAWAY.replace("Check", "Check — first —")}, "em dash"),
    ({"takeaway": TAKEAWAY + " We should leverage that."}, '"leverage" (say "use")'),
    ({"takeaway": TAKEAWAY + " The router is the bottleneck."},
     '"bottleneck" (say "the slowest step")'),
    ({"takeaway": TAKEAWAY + " It is worth noting that caches differ."}, "phrases a reader skips"),
    ({"one": _section("Introduction", 1)}, "name a place in the post"),
    ({"three": _section("The takeaway", 21)}, "name a place in the post"),
    ({"in_short": "**In short:** Sticky routing doubled throughput. It went from 16,000 to"
                  " 46,000 tokens. That was on 10 servers. Short prompts gained nothing."
                  " The prefix was too short."}, '"In short" block has 5 sentences'),
    ({"takeaway": TAKEAWAY + " Throughput alone is a vanity metric."}, "phrases a reader skips"),
    ({"takeaway": TAKEAWAY + " We leveraged both."}, '"leverage" (say "use")'),
    ({"one": _section("Leverage the cache on every server", 1)}, '"leverage" (say "use")'),
    ({"limits": LIMITS.replace("Where this stops working", "You cannot skip the first run")},
     "no section says where this stops working"),
    ({"in_short": "# Sticky routing pays\n\n" + IN_SHORT}, "starts with a title line"),
])
def test_each_thing_that_makes_a_reader_leave_is_named(swap: dict[str, str], says: str) -> None:
    problems = sp.reader_problems(good(**swap), "brief")
    assert any(says in p for p in problems), problems


def test_the_rhythm_of_the_sentences_is_measured() -> None:
    choppy = " ".join(["It was slow.", "We looked.", "Nothing showed.", "We tried again."] * 5)
    problems = sp.reader_problems(good(two=f"## The servers were slow under load\n\n{choppy}"),
                                  "brief")
    assert any("5 words or fewer" in p for p in problems)
    long = " ".join(
        ["The router, which had been configured months earlier by someone who no longer"
         " worked on the system and had left no notes about why the threshold was set to"
         f" {n} requests, kept sending every session to the same server until it failed."
         for n in range(40, 58)])
    problems = sp.reader_problems(good(two=f"## The router kept one server busy\n\n{long}"),
                                  "brief")
    assert any("30 words or more" in p for p in problems)


def test_headings_are_what_a_scanning_reader_lands_on() -> None:
    flat = good().replace("## ", "")
    assert any("no headings" in p for p in sp.reader_problems(flat, "brief"))
    one_long = good(two="", three="", four="",
                    one=_section("A cold server reads the whole prompt again", 1, count=36))
    problems = sp.reader_problems(one_long, "brief")
    assert any("without a heading" in p for p in problems)


def test_the_two_lines_seen_before_the_click_are_held_short() -> None:
    assert sp.headline_problems("Sticky routing pays on long prompts",
                                "When one server per session doubles throughput",
                                "inference") == []
    long_title = "Green dashboards, broken model: the failures your throughput charts cannot see"
    found = sp.headline_problems(long_title, "word " * 40, "cooking")
    assert any("the title is 78 characters" in p for p in found)
    assert any("the summary is" in p for p in found)
    assert any("category must be one of" in p for p in found)
    assert any('"leverage"' in p for p in sp.headline_problems("How to leverage a cache", "S"))


@pytest.mark.parametrize("heading", [
    "Where this stops working", "When not to use it", "What I did not check", "Limits",
    "Caveats", "When this fails", "What this does not tell you", "What I didn’t test",
    "Where this doesn’t hold", "What BM25 cannot do",
])
def test_a_section_on_the_limits_is_found_by_its_heading(heading: str) -> None:
    post = good(limits=LIMITS.replace("Where this stops working", heading))
    assert sp.measure(post).has_limits and sp.reader_problems(post, "brief") == []


@pytest.mark.parametrize("heading", [
    "You cannot skip the first stage", "Rate limits of the API",
    "Round robin doesn't work for long prompts",
    "A reranker cannot recover a chunk that was never retrieved",
])
def test_a_claim_with_cannot_in_it_is_not_the_section_on_limits(heading: str) -> None:
    assert not sp.measure(f"## {heading}\n\nSome text here.").has_limits


def test_the_opening_block_is_found_in_the_ways_it_is_written() -> None:
    body = good(in_short="")
    text = "Sticky routing doubled throughput on long prompts, " + "word " * 22
    for mark in ("**In short:** ", "**In short**: ", "__In short:__ ", "> **In short:** ",
                 "In short: ", "**In short:**\n\n"):
        m = sp.measure(mark + text.strip() + "\n\n" + body)
        assert m.in_short.startswith("Sticky routing doubled"), mark
        assert m.first_paragraph.startswith("Your agent sends turn 37"), mark
    crlf = ('---\ntitle: "T"\n---\n' + good()).replace("\n", "\r\n")
    assert sp.measure(crlf).in_short.startswith("Sticky routing doubled")


def test_sentences_lists_and_code_are_told_apart() -> None:
    assert len(sp.sentences_of("We compared A vs. B on the cluster. It works e.g. with"
                               " Redis. See Fig. 3 for the result.")) == 3
    assert len(sp.sentences_of("it works. then it fails. iOS is fine. vLLM is fast."
                               " p99 rose.")) == 5
    assert len(sp.sentences_of("Recall was 0.62 at v2.31.0. The next run (on 10"
                               " servers) was faster.")) == 2
    base = sp.measure(good())
    bullets = good() + "\n\n" + "\n".join(f"- Short item {n}." for n in range(8))
    assert sp.reader_problems(bullets, "brief") == []
    open_list = good() + "\n\n" + "\n".join(
        f"- item number {n} with no period at the end of the line" for n in range(12))
    assert sp.measure(open_list).long_share == base.long_share
    assert sp.measure(open_list).words > base.words       # list words still count
    indented = good() + "\n\n1. Run it:\n\n    ```python\n    print(123456)\n    ```\n"
    assert sp.measure(indented).code_blocks == 1
    unclosed = sp.measure(good() + "\n\n```python\nprint(123456)\nx = 9999\n")
    assert unclosed.code_blocks == 1 and unclosed.words == base.words
    numbers = sp._NUMBER_RE.findall("gpt-4 on an H100 at p99 with Llama-3 gave 42 tokens"
                                    " in 3.5 ms")
    assert numbers == ["42", "3.5"]
    in_table = ("## The result\n\nThe run is in the table.\n\n| Setup | Tokens |\n|---|---|\n"
                "| Sticky | 46,000 |\n| Round robin | 16,000 |")
    assert sp.measure(in_table).numbers_per_1000 > 0


def test_words_are_found_in_their_inflections_and_not_inside_other_words() -> None:
    for text, want in (("We leveraged it", ("leverage",)), ("two bottlenecks", ("bottleneck",)),
                       ("the canonical form", ()), ("a compound index", ()),
                       ("an on ramp", ("on-ramp",))):
        assert sp.found_in(text, sp._PLAIN_PATTERNS) == want, text
    for text, want in (("we delved in", ("delve",)), ("a deep-dive", ("deep dive",)),
                       ("game changers", ("game changer",)), ("the delivery", ()),
                       ("going to the store again", ())):
        assert sp.found_in(text, sp._STOCK_PATTERNS) == want, text
    subscribed = good(takeaway=TAKEAWAY + " Clients that subscribe to the topic get it.")
    assert sp.reader_problems(subscribed, "brief") == []
    encrypt = good(situation="Let's Encrypt issued 3 certificates for the 10 servers, and"
                             " the router used them for every session.")
    assert sp.reader_problems(encrypt, "brief") == []


def test_a_lab_shows_the_thing_measured_and_every_post_carries_numbers() -> None:
    assert sp.reader_problems(good(), "lab") == []
    assert any("no table and no code block" in p
               for p in sp.reader_problems(good(table=""), "lab"))
    wordy = good().replace("1", "one").replace("2", "two").replace("3", "three")
    for digit, word in zip("4567890", ("four", "five", "six", "seven", "eight", "nine", "no"),
                           strict=True):
        wordy = wordy.replace(digit, word)
    assert any("numbers per 1,000 words" in p for p in sp.reader_problems(wordy, "brief"))


def test_length_is_held_to_the_shape() -> None:
    short = good(two="", three="", four="")
    assert any("has lost the" in p for p in sp.reader_problems(short, "brief"))
    assert any("an explainer post runs 1500 to 3500" in p
               for p in sp.reader_problems(good(), "explainer"))
    long = good(extra=_section("One more run under the same load gave the same result", 41,
                               count=45))
    assert any("almost no extra time" in p for p in sp.reader_problems(long, "brief"))


NOTE = ("A reranker cannot recover a chunk that was never retrieved. It only reorders the 20"
        " chunks that the first stage returned. So a first stage with 50% recall leaves half of"
        " the answers out of reach. I measured this on 120 questions from my own notes. Recall"
        " at 20 was 0.62, and the answer rate was 0.48 before reranking. The reranker moved"
        " the answer rate to 0.55, which is a small gain. Hybrid search in the first stage"
        " moved recall to 0.81 with the same reranker. The answer rate then reached 0.71,"
        " because more of the right chunks were there to reorder. Measure first-stage recall"
        " before you add a reranker.")


def test_a_note_is_one_piece_read_in_a_minute() -> None:
    assert sp.reader_problems(NOTE, "note") == []
    headed = "## What I found\n\n" + NOTE
    assert any("a note has no headings" in p for p in sp.reader_problems(headed, "note"))
    assert any("has lost the" in p for p in sp.reader_problems("Too short to keep.", "note"))


def test_code_tables_and_frontmatter_are_counted_and_left_out_of_the_prose() -> None:
    post = ('---\ntitle: "T"\ntags: [a, b]\n---\n\n' + good(
        table=TABLE + "\n\n```python\nprint(123456)  # 99 88 77\n```"))
    m = sp.measure(post)
    plain = sp.measure(good())
    assert m.code_blocks == 1 and m.tables == 1
    assert m.words == plain.words and m.sentences == plain.sentences
    assert m.numbers_per_1000 == pytest.approx(plain.numbers_per_1000)


def test_a_section_names_a_folder_on_his_site_and_a_shape() -> None:
    assert sp.SITE_FOLDER["writing"] == "blog" == sp.SHAPES["brief"].section
    assert sp.shape_for("writing").name == "explainer"
    assert sp.shape_for("notes").name == "note" and sp.shape_for("papershelf").name == "paper"
    assert sp.shape_for("writing", "lab").name == "lab"
    with pytest.raises(ValueError, match="shape must be one of"):
        sp.shape_for("writing", "essay")
    from hq.learning_pipeline import POST_SECTIONS, post_brief, post_payload

    assert set(POST_SECTIONS) <= set(sp.SITE_FOLDER)
    payload = post_payload({"md_path": "learning/lessons/x.md", "title": "T"}, "writing")
    assert payload["shape"] == "explainer"
    brief = post_brief(payload)
    assert "1500 to 3500 words" in brief and "`blog` section" in brief
    assert "State the result first" in brief and "the claim" in brief


def test_the_writers_procedure_states_the_numbers_the_code_measures() -> None:
    """One source of truth: a number in the prompt that differs from the
    gate sends a draft back for following its instructions."""
    text = (settings().agents_dir / "tutor" / "writer" / "post.md").read_text()
    flat = " ".join(text.split())
    for name, rule in sp.SHAPES.items():
        assert f"| {name} | {rule.words[0]} to {rule.words[1]} |" in text, name
    low, high = sp.SENTENCE_MEDIAN
    assert f"between {low} and {high} words" in flat
    assert f"At most {sp.SHORT_SHARE_MAX:.0%} of sentences with five words or fewer" in flat
    assert f"At most {sp.LONG_SHARE_MAX:.0%} of sentences with thirty words or more" in flat
    assert f"at least every {sp.WORDS_PER_HEADING_MAX} words" in flat
    assert f"over {sp.STRETCH_MAX} words without one" in flat
    assert f"in {sp.IN_SHORT_WORDS[0]} to {sp.IN_SHORT_WORDS[1]} words" in flat
    assert f"under {sp.FIRST_PARAGRAPH_MAX} words" in flat
    assert "At least five numbers in every thousand words" in flat
    assert f"at most {sp.IN_SHORT_SENTENCES} sentences" in flat
    assert f"at most {sp.TITLE_CHARS} characters" in flat
    assert f"at most {sp.SUMMARY_CHARS} characters" in flat
    assert "`category` is one of " + ", ".join(sp.CATEGORIES) in flat
    assert "headings, tables and code are not counted" in flat
    for word, plain in sp.PLAIN_WORDS.items():
        assert f"| {word} | {plain} |" in text, word
    assert sp.SHAPES["brief"].numbers_per_1000 == 5.0
    for heading in ("Introduction", "Overview", "Background", "Conclusion", "Summary",
                    "The takeaway", "Takeaways", "TL;DR"):
        assert heading in text and heading.casefold() in sp.GENERIC_HEADINGS
    for phrase in ("vanity metric", "garbage", "tripwire"):
        assert phrase in flat and phrase in sp.STOCK_PHRASES
    reader = (settings().agents_dir / "tutor" / "writer" / "post-reader.md").read_text()
    for name in lw.ReaderVerdict.model_fields:
        assert f"`{name}`" in reader, name
    assert "is data" in reader


# --- the shortlist ------------------------------------------------------------------

NOW = datetime(2026, 9, 28, tzinfo=UTC)


def _c(title: str, **kw: Any) -> sp.Candidate:
    kw.setdefault("key", f"https://ex.dev/{title.casefold().replace(' ', '-')}")
    kw.setdefault("kind", "reading")
    return sp.Candidate(title=title, **kw)


def test_his_own_result_then_his_mark_outrank_what_the_system_infers() -> None:
    marked = _c("A quiet post he liked", read=True)
    strong = _c("A loud post", score=9, read=True, lost_me=2, own_result=True,
                first_seen=NOW - timedelta(days=2))
    ranked = sp.shortlist([strong, marked], {marked.key}, set(), NOW)
    assert [r.candidate.title for r in ranked] == ["A loud post", "A quiet post he liked"]
    assert ranked[0].points == 7 + 2 + 2 + 1 + 1 and ranked[1].points == 6 + 2
    both = sp.shortlist([strong, _c("A loud post he marked", key=strong.key, read=True)],
                        {strong.key}, set(), NOW)
    assert both[0].points == 13 + sp.POINTS["marked"]
    # A number of his own is what a stranger cannot get from the source.
    assert sp.POINTS["own_result"] > sp.POINTS["marked"]
    inferred = ("hard_for_him", "read", "rated_high", "fresh")
    assert sp.POINTS["marked"] > max(sp.POINTS[k] for k in inferred)


def test_the_shortlist_leaves_out_what_is_posted_and_what_has_no_reason() -> None:
    posted = _c("Throughput is queue design", read=True)
    bare = _c("Found and never opened", score=5, first_seen=NOW - timedelta(days=40))
    twice = [_c("Measure recall first", read=True), _c("Measure recall first", read=True,
                                                         key="learning/lessons/recall.md")]
    many = [_c(f"Post number {n}", read=True, score=n) for n in range(9)]
    ranked = sp.shortlist([posted, bare, *twice, *many], set(),
                          {"throughput-is-queue-design"}, NOW)
    titles = [r.candidate.title for r in ranked]
    assert len(ranked) == sp.SHORTLIST_SIZE
    assert "Throughput is queue design" not in titles and "Found and never opened" not in titles
    assert titles.count("Measure recall first") <= 1
    assert titles[0] == "Post number 8"  # rated 8 or more adds a point


def test_the_shortlist_reads_as_five_lines_with_reasons() -> None:
    ranked = sp.shortlist(
        [_c("Sticky routing pays on long prompts", read=True, own_result=True,
            why="Three projects measured  the same\nthing.")], set(), set(), NOW)
    text = sp.shortlist_markdown(ranked, sp.iso_week(NOW))
    assert text.startswith("## 2026-W40")
    assert "After reading this, you can ___." in text and "Pick two" in text
    assert "you have your own result for it; you read it" in text
    assert "What it adds: Three projects measured the same thing." in text
    empty = sp.shortlist_markdown([], "2026-W40")
    assert sp.WORTH_SHARING_PATH in empty and "Pick two" not in empty


def test_what_he_marks_is_read_from_a_plain_file(tmp_path: Path) -> None:
    text = ("# Worth sharing\n\n"
            "https://vllm.ai/blog/anatomy. changed how I think about queues\n"
            "- learning/lessons/2026-09-12-throughput-is-queue-design.md\n"
            "just a thought, no link\n")
    assert sp.marks(text) == {"https://vllm.ai/blog/anatomy",
                              "learning/lessons/2026-09-12-throughput-is-queue-design.md"}
    site = tmp_path / "portfolio"
    (site / "content" / "blog").mkdir(parents=True)
    (site / "content" / "notes").mkdir()
    (site / "content" / "blog" / "sticky-routing.md").write_text("x")
    (site / "content" / "notes" / "recall-first.md").write_text("x")
    assert sp.posted_titles(site) == {"sticky-routing", "recall-first"}
    assert sp.posted_titles(tmp_path / "nowhere") == set()


# --- saving, and the read by a stranger ---------------------------------------------


async def _no_emit(*a: Any, **k: Any) -> None:
    return None


def _site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    site = tmp_path / "portfolio"
    site.mkdir()
    monkeypatch.setattr(settings(), "portfolio_dir", site)
    monkeypatch.setattr(lt, "emit", _no_emit)
    return site


def test_a_post_lands_in_the_folder_his_site_reads(tmp_path: Path, monkeypatch) -> None:
    site = _site(tmp_path, monkeypatch)
    saved = asyncio.run(lt.save_post(
        "writing", "sticky-routing", "Sticky routing pays on long prompts",
        "When keeping a session on one server doubles throughput, and when it does not",
        "inference, routing, caching", good(), shape="brief"))
    path = site / "content" / "blog" / "sticky-routing.md"
    assert saved["path"] == str(path) and path.is_file()
    text = path.read_text()
    assert "section: blog" in text and "draft: true" in text and "category:" not in text
    assert "learning/lessons" not in text        # his site carries no private path
    assert text.split("---\n", 2)[2].lstrip().startswith("**In short:**")

    asyncio.run(lt.save_post("notes", "recall-first", "Measure recall before a reranker",
                             "A reranker cannot recover what was never retrieved",
                             "retrieval, evals", NOTE, category="Retrieval"))
    note = (site / "content" / "notes" / "recall-first.md").read_text()
    assert "section: notes" in note and "category: retrieval" in note
    assert {"sticky-routing", "sticky-routing-pays-on-long-prompts",
            "recall-first"} <= sp.posted_titles(site)


def test_a_draft_may_be_written_again_and_a_published_post_may_not(
        tmp_path: Path, monkeypatch) -> None:
    site = _site(tmp_path, monkeypatch)
    args = ("writing", "sticky-routing", "Sticky routing pays", "One line", "a, b", good())
    asyncio.run(lt.save_post(*args, shape="brief"))
    asyncio.run(lt.save_post(*args, shape="brief"))      # still a draft: written again
    path = site / "content" / "blog" / "sticky-routing.md"
    path.write_text(path.read_text().replace("draft: true", "draft: false") + "\nMy edit.\n")
    with pytest.raises(lt.LessonRefused, match="a published post already has the slug"):
        asyncio.run(lt.save_post(*args, shape="brief"))
    assert "My edit." in path.read_text()


def test_a_post_a_reader_would_leave_is_not_written(tmp_path: Path, monkeypatch) -> None:
    site = _site(tmp_path, monkeypatch)
    with pytest.raises(lt.LessonRefused, match="a reader would leave this post"):
        asyncio.run(lt.save_post("writing", "x", "T", "S", "a, b", good(in_short=""), shape="brief"))
    with pytest.raises(lt.LessonRefused, match="the title is 8[0-9] characters"):
        asyncio.run(lt.save_post("writing", "x", "A title that runs on and on " * 3, "S",
                                 "a, b", good(), shape="brief"))
    leak = good(takeaway=TAKEAWAY + " The lesson behind this post has the script.")
    with pytest.raises(lt.LessonRefused, match="private notes"):
        asyncio.run(lt.save_post("writing", "x", "T", "S", "a, b", leak, shape="brief"))
    with pytest.raises(lt.LessonRefused, match="1 tag"):
        asyncio.run(lt.save_post("writing", "x", "T", "S", "only", good(), shape="brief"))
    with pytest.raises(lt.LessonRefused, match="the slug"):
        asyncio.run(lt.save_post("writing", "!!!", "T", "S", "a, b", good(), shape="brief"))
    with pytest.raises(lt.LessonRefused, match="shape must be one of"):
        asyncio.run(lt.save_post("writing", "x", "T", "S", "a, b", good(), shape="essay"))
    assert not (site / "content").exists()


def test_what_a_stranger_says_goes_back_to_the_writer() -> None:
    fine = lw.ReaderVerdict(gets="when sticky routing pays", takeaway="check the prefix length",
                            matches_claim=True, would_finish=True)
    assert lw.reader_notes(fine) == []
    lost = lw.ReaderVerdict(
        gets="not sure", takeaway="routing is hard", matches_claim=False, would_finish=False,
        left_because="the second section repeats the first",
        lost_at=[f'"Place {n}": term used before it is explained' for n in range(8)])
    notes = lw.reader_notes(lost)
    assert "would have left before the end: the second section repeats" in notes[0]
    assert '"routing is hard", which is not the claim' in notes[1]
    assert len([n for n in notes if "lost the thread at" in n]) == lw.READER_LOST
    few = fine.model_copy(update={"unexplained": ["GPU", "KV cache"]})
    assert lw.reader_notes(few) == []
    many = fine.model_copy(update={"unexplained": ["KV cache", "FP8", "TP4", "TTFT"]})
    sent_back = ("these terms are used without saying what they are: KV cache, FP8, TP4,"
                 " TTFT. Explain each in the sentence that first uses it, and make room by"
                 " removing a finding the claim does not need")
    assert lw.reader_notes(many) == [sent_back]


def _draft(markdown: str, claim: str = "tell from the prefix length whether sticky routing"
                                       " will pay") -> dict[str, Any]:
    return {"slug": "sticky-routing", "title": "Sticky routing pays on long prompts",
            "summary": "When keeping a session on one server doubles throughput",
            "tags": ["inference", "routing", "caching"], "category": "inference",
            "claim": claim, "markdown": markdown}


def _run_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drafts: list[dict[str, Any]],
              verdicts: list[Any]) -> tuple[Any, list[str], Path]:
    site = _site(tmp_path, monkeypatch)
    learning = tmp_path / "learning"
    (learning / "lessons").mkdir(parents=True)
    (learning / "lessons" / "x.md").write_text("# The lesson\n\nSticky routing, measured.")
    monkeypatch.setattr(settings(), "learning_dir", learning)
    prompts: list[str] = []

    async def post_step(model: str, instructions: str, prompt: str) -> dict[str, Any]:
        prompts.append(prompt)
        return drafts[min(len(prompts), len(drafts)) - 1]

    async def reader_step(title: str, summary: str, markdown: str, claim: str) -> dict[str, Any]:
        verdict = verdicts.pop(0)
        if isinstance(verdict, Exception):
            raise verdict
        return verdict

    monkeypatch.setattr(lw, "_post_step", post_step)
    monkeypatch.setattr(lw, "_post_reader_step", reader_step)
    monkeypatch.setattr(lw.assemble, "assemble",
                        lambda kind, spec, **kw: type("Bundle", (), {"text": "the procedure"})())
    monkeypatch.setattr(runner, "emit_step", _no_emit)
    spec = type("Spec", (), {"model": "teacher", "name": "tutor"})()
    task = {"payload": {"stage": "post_draft", "section": "writing", "shape": "brief",
                        "md_path": "learning/lessons/x.md"},
            "brief": "## This task\n\nShape: brief."}
    outcome = asyncio.run(lw.write_post(
        task, spec, HQDeps(agent="tutor", task_id="t-1", run_id=None)))  # type: ignore[arg-type]
    return outcome, prompts, site


FINISHED = {"gets": "when sticky routing pays", "lost_at": [], "takeaway": "check the prefix",
            "unexplained": [], "matches_claim": True, "would_finish": True, "left_because": ""}
LEFT = {"gets": "unclear", "lost_at": ['"Run 3 sent": no condition'], "takeaway": "routing",
        "unexplained": [], "matches_claim": False, "would_finish": False,
        "left_because": "it repeats itself"}
ONE_NOTE = {**FINISHED, "lost_at": ['"Run 9 sent": the step before it is missing']}


def test_a_post_is_measured_then_read_then_saved(tmp_path: Path, monkeypatch) -> None:
    outcome, prompts, site = _run_post(
        tmp_path, monkeypatch, [_draft(good(in_short="")), _draft(good())], [dict(FINISHED)])
    assert outcome.outcome == "done" and len(prompts) == 2
    assert "does not open with the result" in prompts[1]
    # A new call remembers nothing: the draft that was sent back goes with it.
    assert "## Your previous draft" in prompts[1] and "Your agent sends turn 37" in prompts[1]
    assert "Claim: tell from the prefix length" in outcome.output
    assert "A reader still said" not in outcome.output
    saved = (site / "content" / "blog" / "sticky-routing.md").read_text()
    assert "category: inference" in saved and "section: blog" in saved


def test_the_readers_notes_send_a_measured_draft_back_once_more(
        tmp_path: Path, monkeypatch) -> None:
    outcome, prompts, site = _run_post(
        tmp_path, monkeypatch, [_draft(good())], [dict(LEFT), dict(FINISHED)])
    assert outcome.outcome == "done" and len(prompts) == 2
    assert "a reader would have left before the end: it repeats itself" in prompts[1]
    assert (site / "content" / "blog" / "sticky-routing.md").is_file()


def test_a_draft_that_passed_the_measures_is_kept_with_what_the_reader_said(
        tmp_path: Path, monkeypatch) -> None:
    outcome, prompts, site = _run_post(
        tmp_path, monkeypatch, [_draft(good())], [dict(LEFT) for _ in range(lw.POST_ATTEMPTS)])
    assert outcome.outcome == "done" and len(prompts) == lw.POST_ATTEMPTS
    assert "A reader still said:" in outcome.output and "it repeats itself" in outcome.output
    assert (site / "content" / "blog" / "sticky-routing.md").is_file()


def test_a_post_that_never_passes_the_measures_is_not_written(
        tmp_path: Path, monkeypatch) -> None:
    outcome, prompts, site = _run_post(
        tmp_path, monkeypatch,
        [_draft(good(one=_section("Introduction", 1), takeaway=TAKEAWAY + " Thoughts?"))], [])
    assert outcome.outcome == "failed" and len(prompts) == lw.POST_ATTEMPTS
    assert "name a place in the post" in (outcome.error or "")
    assert "closes by asking" in (outcome.error or "")
    assert not (site / "content").exists()


def test_material_that_cannot_carry_a_claim_is_a_quiet_day(tmp_path: Path, monkeypatch) -> None:
    empty = _draft(good(), claim="")
    empty["summary"] = "The lesson has no result a stranger could use"
    outcome, prompts, site = _run_post(tmp_path, monkeypatch, [empty], [])
    assert outcome.outcome == "done" and len(prompts) == 1
    assert outcome.declined == "The lesson has no result a stranger could use"
    assert not (site / "content").exists()


def test_a_draft_is_sent_back_for_its_fields_not_lost_to_them(
        tmp_path: Path, monkeypatch) -> None:
    """One tag, a quote in the title, a slug with no letters: each is named
    and the writer gets another try, before any reader is asked."""
    bad = [dict(_draft(good()), tags=["routing"]),
           dict(_draft(good()), title='Why "sticky" routing pays'),
           dict(_draft(good()), slug="!!!")]
    outcome, prompts, site = _run_post(tmp_path, monkeypatch, [*bad[:2], _draft(good())],
                                       [dict(FINISHED)])
    assert outcome.outcome == "done" and len(prompts) == 3
    assert "1 tag(s); give two to eight" in prompts[1]
    assert "no double quotes" in prompts[2]
    assert (site / "content" / "blog" / "sticky-routing.md").is_file()
    assert lt.post_field_problems("!!!", "T", "S", ["a", "b"])[0].startswith("the slug")
    assert lt.post_field_problems("ok-slug", "T", "S", ["a", "b"]) == []


def test_a_kept_draft_survives_a_later_draft_with_no_claim(
        tmp_path: Path, monkeypatch) -> None:
    outcome, prompts, site = _run_post(
        tmp_path, monkeypatch, [_draft(good()), _draft(good(), claim="")], [dict(LEFT)])
    assert outcome.outcome == "done" and not outcome.declined and len(prompts) == 2
    assert "A reader still said:" in outcome.output
    assert (site / "content" / "blog" / "sticky-routing.md").is_file()


def test_a_draft_that_passed_is_not_lost_when_its_reader_fails(
        tmp_path: Path, monkeypatch) -> None:
    outcome, prompts, site = _run_post(
        tmp_path, monkeypatch, [_draft(good())], [TimeoutError("the gateway went quiet")])
    assert outcome.outcome == "done" and len(prompts) == 1
    assert "no reader read it: TimeoutError" in outcome.output
    assert (site / "content" / "blog" / "sticky-routing.md").is_file()


def test_the_draft_saved_is_the_one_its_reader_objected_to_least(
        tmp_path: Path, monkeypatch) -> None:
    first = _draft(good())
    second = dict(_draft(good(takeaway=TAKEAWAY + " Measure it on your own traffic first.")))
    outcome, prompts, site = _run_post(
        tmp_path, monkeypatch, [first, second, _draft(good(limits=""))],
        [dict(ONE_NOTE), dict(LEFT)])
    assert outcome.outcome == "done" and len(prompts) == lw.POST_ATTEMPTS
    saved = (site / "content" / "blog" / "sticky-routing.md").read_text()
    assert "Measure it on your own traffic first." not in saved
    assert "the step before it is missing" in outcome.output
    assert lw._better([], None) and lw._better(["a"], (lw.PostDraft(**first), ["a", "b"]))
    assert not lw._better(["a", "b"], (lw.PostDraft(**first), ["a"]))


def test_a_shape_nobody_defined_blocks_the_run_before_any_model_is_asked(
        tmp_path: Path, monkeypatch) -> None:
    site = _site(tmp_path, monkeypatch)
    learning = tmp_path / "learning"
    (learning / "lessons").mkdir(parents=True)
    (learning / "lessons" / "x.md").write_text("# The lesson")
    monkeypatch.setattr(settings(), "learning_dir", learning)
    spec = type("Spec", (), {"model": "teacher", "name": "tutor"})()
    task = {"payload": {"section": "writing", "shape": "essay",
                        "md_path": "learning/lessons/x.md"}, "brief": ""}
    outcome = asyncio.run(lw.write_post(
        task, spec, HQDeps(agent="tutor", task_id=None, run_id=None)))  # type: ignore[arg-type]
    assert outcome.outcome == "blocked" and "shape must be one of" in (outcome.error or "")
    assert not (site / "content").exists()


def test_what_is_already_posted_leaves_the_shortlist(tmp_path: Path, monkeypatch) -> None:
    site = _site(tmp_path, monkeypatch)
    asyncio.run(lt.save_post("writing", "sticky", "Sticky routing pays on long prompts",
                             "One line", "a, b", good(), "learning/lessons/x.md", shape="brief"))
    lesson = _c("Sticky routing pays on long prompts", key="learning/lessons/x.md", read=True)
    renamed = _c("A lesson whose post got another title", key="learning/lessons/y.md",
                 read=True)
    other = _c("Measure recall first", read=True)
    by_title = sp.shortlist([lesson, renamed, other], set(), sp.posted_titles(site), NOW)
    assert [r.candidate.title for r in by_title] == [
        "A lesson whose post got another title", "Measure recall first"]
    by_source = sp.shortlist([lesson, renamed, other], set(),
                             sp.posted_titles(site) | {"learning/lessons/y.md"}, NOW)
    assert [r.candidate.title for r in by_source] == ["Measure recall first"]
    nameless = [_c("\u30eb\u30fc\u30c6\u30a3\u30f3\u30b0", key="https://ex.dev/a", read=True),
                _c("\u30ad\u30e3\u30c3\u30b7\u30e5", key="https://ex.dev/b", read=True)]
    assert len(sp.shortlist(nameless, set(), set(), NOW)) == 2
    # The database may hand back a time with no zone; it is read as UTC.
    naive = sp.score(_c("T", read=True, first_seen=datetime(2026, 9, 27)),  # noqa: DTZ001
                     set(), datetime(2026, 9, 28))  # noqa: DTZ001
    assert "fresh" in naive.reasons


def test_sentences_that_speak_as_him_are_listed_for_his_check() -> None:
    post = ("**In short:** The score fell to 0.0099.\n\n"
            "I did not open the pull requests. The index i counts the layers.\n\n"
            "- We ran it on my laptop.\n\n```python\nI = my = 1\n```\n")
    assert sp.first_person(post) == [
        "I did not open the pull requests.", "We ran it on my laptop."]


def test_the_reader_quotes_sentences_with_no_verb() -> None:
    verdict = lw.ReaderVerdict(
        gets="g", takeaway="t", matches_claim=True, would_finish=True,
        fragments=["Tokens per second normal, latency normal."])
    notes = lw.reader_notes(verdict)
    assert len(notes) == 1
    assert '"Tokens per second normal, latency normal."' in notes[0]


def test_the_opening_block_starts_with_the_finding() -> None:
    post = good().replace(
        "**In short:**", "**In short:** I read a post about this.", 1)
    problems = "\n".join(sp.reader_problems(post, "brief"))
    assert "starts with the author" in problems
    assert "starts with the author" not in "\n".join(sp.reader_problems(good(), "brief"))


def test_a_reader_says_which_promise_was_not_kept_and_which_section_is_extra() -> None:
    verdict = lw.ReaderVerdict(
        gets="g", takeaway="t", matches_claim=True, would_finish=True,
        not_delivered=["recall per segment: the code gives every question one segment"],
        off_claim=["An agent with retries changes what you should measure"],
        figures=["lies gently", "burn weeks"], unclear_source=["the post says"])
    notes = "\n".join(lw.reader_notes(verdict))
    assert "promises what the post does not give: recall per segment" in notes
    assert 'does not need the section "An agent with retries' in notes
    assert '"lies gently" | "burn weeks"' in notes
    assert 'whose words or number these are: "the post says"' in notes


def test_code_nobody_ran_is_told_to_him_not_hidden() -> None:
    code = "```python\nprint(1)\n```\n"
    assert sp.unrun_code("Text.\n\n" + code + "\nThis script has not been run.\n")
    assert not sp.unrun_code("Text.\n\n" + code + "\nIt printed 1 on my laptop.\n")
    assert not sp.unrun_code("This was not tested.\n")
    assert sp.first_person('He wrote [Why Grep Beat Embeddings in Our Agent](http://x.y).') == []


def test_a_quotation_that_is_not_in_the_post_is_dropped() -> None:
    post = "**In short:** x.\n\nThe synthetic eval lies gently. Tokens normal, latency normal.\n"
    verdict = lw.ReaderVerdict(
        gets="g", takeaway="t", matches_claim=True, would_finish=True,
        figures=["lies gently", "burn weeks"],
        fragments=['That is it, none found. Actually: "No." (not present).',
                   "Tokens normal, latency normal."])
    notes = "\n".join(lw.reader_notes(verdict, post))
    assert '"lies gently"' in notes and "burn weeks" not in notes
    assert "Tokens normal" in notes and "none found" not in notes


def test_numbers_the_material_does_not_hold_are_listed_for_him() -> None:
    source = "Recall of 70% can sit on 5% for one segment. At 60% and 5 tries it is 99%."
    post = ("**In short:** x.\n\nA system with 95% on simple questions and 5% on others"
            " averages 70%. With r = 0.6 it is 1 - 0.4^5, about 99%.\n\n"
            "```\n1 - 0.01024\n```\n\n[a link](https://x.y/2025/01/24/z)\n")
    assert sp.numbers_not_in(post, source) == ["95", "0.4"]
    assert sp.first_person("He titled it *Why Grep Beat Embeddings in Our Agent*.") == []


# --- field notes: what he did, in his words ------------------------------------

FIELD_NOTE = """---
project: mission-hq
---

## What I did

At work I moved long chat sessions to sticky routing on a support chatbot.

## The number

Throughput went from 16,000 to 46,000 input tokens a second on 10 servers.

## What surprised me

Short prompts gained nothing.

## What I would do differently

I would measure the shared prefix length before changing the router.
"""
SITUATION_AS_HIM = ("At work I moved long chat sessions to sticky routing, because turn 37 of a"
                    " session is 99% the same as turn 36. Before that, each server read all"
                    " 100,000 tokens again before it could answer.")


THIRD_PERSON_LIMITS = LIMITS.replace("I did not check", "Nobody checked")


def test_a_field_note_is_read_into_its_parts() -> None:
    note = sp.read_field_note(FIELD_NOTE)
    assert note.project == "mission-hq" and note.has_number
    assert note.parts["did"].startswith("At work I moved")
    assert note.parts["view"].startswith("I would measure")
    assert sp.field_note_problems(note) == []


def test_a_note_left_as_the_template_cannot_carry_a_post() -> None:
    note = sp.read_field_note(sp.FIELD_NOTE_TEMPLATE)
    assert note.parts == {} and note.project == ""
    problems = sp.field_note_problems(note)
    assert len(problems) == 2 and "What I did" in problems[0] and "retelling" in problems[1]
    no_number = sp.read_field_note("## What I did\n\nI moved the router.\n\n## The number\n\nfast")
    assert sp.field_note_problems(no_number) == [
        ('fill in "The number" with a result you measured; without a number of your own'
         " the post is a retelling of the source")]


def test_a_field_note_path_stays_in_its_folder() -> None:
    assert sp.field_note_path("sticky-routing") == f"{sp.FIELD_NOTES_DIR}/sticky-routing.md"
    assert sp.field_note_path(f"{sp.FIELD_NOTES_DIR}/a-b.md") == f"{sp.FIELD_NOTES_DIR}/a-b.md"
    for bad in ("../secrets", "memory/core.md", "Sticky Routing", ""):
        with pytest.raises(ValueError):
            sp.field_note_path(bad)


def test_his_own_result_outranks_what_he_marked(tmp_path: Path) -> None:
    folder = tmp_path / sp.FIELD_NOTES_DIR
    folder.mkdir(parents=True)
    (folder / "sticky-routing.md").write_text(FIELD_NOTE)
    (folder / "empty.md").write_text(sp.FIELD_NOTE_TEMPLATE)
    notes = sp.field_note_candidates(tmp_path)
    assert [c.key for c in notes] == [f"{sp.FIELD_NOTES_DIR}/sticky-routing.md"]
    assert notes[0].own_result and notes[0].kind == "field_note"
    article = sp.Candidate(key="https://a.example/post", title="An article", kind="reading",
                           read=True)
    ranked = sp.shortlist([article, *notes], {"https://a.example/post"}, set())
    assert ranked[0].candidate.kind == "field_note"
    assert set(ranked[0].reasons) >= {"own_result", "his_words"}


def test_the_field_note_command_writes_the_template_once(tmp_path: Path, capsys) -> None:
    assert sp._new_field_note(["sticky-routing"], vault=tmp_path) == 0
    path = tmp_path / sp.FIELD_NOTES_DIR / "sticky-routing.md"
    assert path.read_text() == sp.FIELD_NOTE_TEMPLATE
    assert sp._new_field_note(["sticky-routing"], vault=tmp_path) == 1
    assert sp._new_field_note(["../x"], vault=tmp_path) == 2


def _run_note_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, note: str,
                   drafts: list[dict[str, Any]]) -> tuple[Any, list[str], Path]:
    site = _site(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    (vault / sp.FIELD_NOTES_DIR).mkdir(parents=True)
    (vault / sp.FIELD_NOTES_DIR / "sticky-routing.md").write_text(note)
    monkeypatch.setattr(settings(), "vault_dir", vault)
    prompts: list[str] = []

    async def post_step(model: str, instructions: str, prompt: str) -> dict[str, Any]:
        prompts.append(prompt)
        return drafts[min(len(prompts), len(drafts)) - 1]

    async def reader_step(*a: Any) -> dict[str, Any]:
        return dict(FINISHED)

    monkeypatch.setattr(lw, "_post_step", post_step)
    monkeypatch.setattr(lw, "_post_reader_step", reader_step)
    monkeypatch.setattr(lw.assemble, "assemble",
                        lambda kind, spec, **kw: type("Bundle", (), {"text": "the procedure"})())
    monkeypatch.setattr(runner, "emit_step", _no_emit)
    spec = type("Spec", (), {"model": "teacher", "name": "tutor"})()
    task = {"payload": {"stage": "post_draft", "section": "writing", "shape": "lab",
                        "field_note": "sticky-routing"},
            "brief": "## This task\n\nShape: lab."}
    outcome = asyncio.run(lw.write_post(
        task, spec, HQDeps(agent="tutor", task_id="t-1", run_id=None)))  # type: ignore[arg-type]
    return outcome, prompts, site


def test_a_post_from_a_field_note_must_say_what_he_did(tmp_path: Path, monkeypatch) -> None:
    outcome, prompts, site = _run_note_post(
        tmp_path, monkeypatch, FIELD_NOTE,
        [_draft(good(limits=THIRD_PERSON_LIMITS)),
         _draft(good(situation=SITUATION_AS_HIM, limits=THIRD_PERSON_LIMITS))])
    assert outcome.outcome == "done" and len(prompts) == 2
    assert "## His field note" in prompts[0] and "At work I moved" in prompts[0]
    assert "## The lesson" not in prompts[0]
    assert "the post never says what he did" in prompts[1]
    saved = (site / "content" / "blog" / "sticky-routing.md").read_text()
    assert "project: mission-hq" in saved and "At work I moved" in saved


def test_an_unfilled_field_note_blocks_before_any_model_is_asked(
        tmp_path: Path, monkeypatch) -> None:
    outcome, prompts, site = _run_note_post(
        tmp_path, monkeypatch, sp.FIELD_NOTE_TEMPLATE, [_draft(good())])
    assert outcome.outcome == "blocked" and prompts == []
    assert "What I did" in (outcome.error or "")
    assert not (site / "content").exists()


def test_a_project_that_is_not_a_slug_is_refused(tmp_path: Path, monkeypatch) -> None:
    _site(tmp_path, monkeypatch)
    with pytest.raises(lt.LessonRefused, match="project must be a slug"):
        asyncio.run(lt.save_post("writing", "sticky-routing", "Sticky routing pays",
                                 "When keeping a session on one server doubles throughput",
                                 "inference, routing", good(), project="Mission HQ!", shape="brief"))


def test_a_topic_readers_look_for_is_ranked_up() -> None:
    topics = sp.demand_topics("# Topics\n\n- KV cache: people ask about it\n- RAG\n\nnot a line")
    assert topics == ["kv cache", "rag"]
    cache = _c("How the KV cache fills up", read=True)
    storage = _c("Object storage costs", read=True)       # "rag" is not in "storage"
    assert sp.in_demand(cache, topics) == "kv cache" and sp.in_demand(storage, topics) == ""
    ranked = sp.shortlist([storage, cache], set(), set(), NOW, topics=topics)
    assert ranked[0].candidate is cache and "in_demand" in ranked[0].reasons
    assert "readers look for this topic now" in sp.shortlist_markdown(ranked, "2026-W40")


def test_a_blog_post_is_an_explainer_unless_the_task_names_another_shape() -> None:
    assert sp.shape_for("writing").name == "explainer"
    assert sp.shape_for("blog", "lab").name == "lab"
    assert not sp.SHAPES["explainer"].in_short
