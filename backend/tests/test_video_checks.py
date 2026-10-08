"""Rules of the video pipeline that two checks once disagreed on (2026-10-08)."""

from __future__ import annotations

from hq.video import checks, script
from hq.video.models import Line

LONG = " ".join(["word"] * 30) + "."


def test_a_long_key_point_is_shortened_not_split() -> None:
    # "split it" made a fourth r line, which the key-point rule refused.
    found = checks.line_problems("c1", Line(key="r0", text=f"Remember: {LONG}"))
    assert any("keep it one r0 line" in p for p in found)
    assert not any("split it" in p for p in found)


def test_a_long_line_elsewhere_is_still_split() -> None:
    found = checks.line_problems("c1", Line(key="s0", text=LONG))
    assert any("split it" in p for p in found)


def test_mechanism_items_point_at_the_step_lines() -> None:
    lines = [
        Line(key="m0", text="Step 1. The block is evicted."),
        Line(key="m0b", text="It moves down to host memory."),
        Line(key="m1", text="Step 2. The request comes back."),
    ]
    beat = {"steps": [{"step": "mechanism",
                       "items": [{"text": "evict", "at": "m0b"}, {"text": "reload", "at": "x"}]}]}
    script._pin_mechanism(beat, lines)
    assert [i["at"] for i in beat["steps"][0]["items"]] == ["m0", "m1"]


def test_a_wrong_item_count_is_left_for_check_spec() -> None:
    lines = [Line(key="m0", text="Step 1. One."), Line(key="m1", text="Step 2. Two.")]
    beat = {"steps": [{"step": "mechanism", "items": [{"text": "only", "at": "m1"}]}]}
    script._pin_mechanism(beat, lines)
    assert beat["steps"][0]["items"][0]["at"] == "m1"
