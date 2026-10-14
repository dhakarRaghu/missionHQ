#!/usr/bin/env python3
"""v2.py: a version 1 example turned into version 2 (the story order), to prove the v2 templates.

    python3 examples/v2.py examples/ep12/ep12 examples/ep12-v2/ep12-v2
    python3 examples/v2.py examples/stress/stress examples/stress-v2/stress-v2

Reads <in>.narration.json and <in>.spec.json and writes <out>.narration.json and <out>.spec.json.
In each concept: the lines run s, q, t, p, m, n, then the claim (k) as the takeaway, then h; the three
key points (r) go. The think step keeps first and misses, at the first and last `t` line, and loses
`real`. The words are the v1 example's, so this proves layout and timing, not narration.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ORDER = "sqtpmnkh"


def letter(key: str) -> str:
    m = re.match(r"^([a-z]+?)(?=\d)", key)
    return m.group(1) if m else ""


def main(src: str, dst: str) -> None:
    narration = json.loads(Path(f"{src}.narration.json").read_text())
    spec = json.loads(Path(f"{src}.spec.json").read_text())
    for beat_id, beat in narration["beats"].items():
        if not re.fullmatch(r"c\d+", beat_id):
            continue
        lines = [ln for ln in beat["lines"] if letter(ln["key"]) in ORDER]
        beat["lines"] = sorted(lines, key=lambda ln: ORDER.index(letter(ln["key"])))
        q = [ln for ln in beat["lines"] if letter(ln["key"]) == "q"]
        for ln in q:  # the v1 fixed phrase goes; the question itself stays
            for field in ("text", "say"):
                if field in ln:
                    ln[field] = re.sub(r"\s*Let's think it through\.?$", "", ln[field]).rstrip()
        if q and not q[-1]["text"].endswith("?"):
            q[-1]["text"] = q[-1]["text"].rstrip(" .") + "?"
    for beat in spec["beats"]:
        if beat.get("kind") != "concept":
            continue
        lines = narration["beats"][beat["id"]]["lines"]
        t_keys = [ln["key"] for ln in lines if letter(ln["key"]) == "t"]
        by_name = {s["step"]: s for s in beat["steps"]}
        think = {k: v for k, v in by_name["think"].items() if k in ("step", "first", "misses")}
        think.update(first_at=t_keys[0], misses_at=t_keys[-1])
        steps = [by_name["situation"], think]
        if "picture" in by_name:
            steps.append(by_name["picture"])
        steps.append(by_name["mechanism"])
        if "number" in by_name:
            steps.append(by_name["number"])
        steps.append({"step": "takeaway"})
        if "bridge" in by_name:
            steps.append(by_name["bridge"])
        beat["steps"] = steps
    spec["version"] = 2
    spec["id"] = Path(dst).name[:80]
    if spec.get("next"):
        spec["next"]["label"] = "Next part"
    out = Path(dst)
    out.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{dst}.narration.json").write_text(json.dumps(narration, ensure_ascii=False, indent=2) + "\n")
    Path(f"{dst}.spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
