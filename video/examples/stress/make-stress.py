#!/usr/bin/env python3
"""Writes stress.narration.json and stress.spec.json: every text field at its maximum length, every panel
kind in a full-width box and in a mechanism's narrow side box, and ten concept beats (a long video).
Run from video/:  python3 examples/stress/make-stress.py"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "WMW Measured $8,888 GPU-hours at 100% load with W4A16 on H100 MW "

def fill(n, seed=0):
    s = (BASE[seed % len(BASE):] + BASE * 20)
    s = s[:n].rstrip()
    while len(s) < n:
        s += "M"
    return s

KINDS = ["chips", "flow", "stats", "bars", "table", "equation", "compare", "prompt"]
LIMITS = {"caption": 90, "note": 120}

def panel(kind, keys, seed):
    """keys: the line keys to spread over the elements, in order."""
    def k(i, n):
        return keys[min(len(keys) - 1, i * len(keys) // n)]
    p = {"kind": kind, "caption": fill(90, seed), "note": fill(120, seed + 3)}
    if kind == "chips":
        p["items"] = [{"text": fill(64, seed + i), "tone": ["ink", "ok", "bad", "warn", "info", "accent"][i], "at": k(i, 6)} for i in range(6)]
    elif kind == "flow":
        p["nodes"] = [{"label": fill(22, seed + i), "sub": fill(36, seed + i + 1), "tone": ["ink", "info", "warn", "ok", "bad"][i], "at": k(i, 5)} for i in range(5)]
    elif kind == "stats":
        p["items"] = [{"value": fill(14, seed + i), "label": fill(40, seed + i), "tone": ["ink", "bad", "ok"][i], "at": k(i, 3)} for i in range(3)]
    elif kind == "bars":
        p["items"] = [{"label": fill(28, seed + i), "value": [100, 1, 50, 75, 3, 99][i], "display": fill(16, seed + i), "tone": ["ink", "ok", "bad", "warn", "info", "accent"][i], "at": k(i, 6)} for i in range(6)]
    elif kind == "table":
        p["columns"] = [fill(18, seed + j) for j in range(4)]
        p["rows"] = [{"cells": [fill(22, seed + i + j) for j in range(4)], "tone": ["ink", "ok", "bad", "ink", "warn", "info"][i], "at": k(i, 6)} for i in range(6)]
    elif kind == "equation":
        p["lines"] = [{"text": fill(48, seed + i), "tone": ["ink", "accent", "ink", "bad", "ok"][i], "at": k(i, 5)} for i in range(5)]
    elif kind == "compare":
        p["left"] = {"title": fill(28, seed), "items": [fill(40, seed + i) for i in range(4)]}
        p["right"] = {"title": fill(28, seed + 1), "items": [fill(40, seed + i + 2) for i in range(4)]}
        p["at_left"] = keys[0]
        p["at_right"] = keys[-1]
    elif kind == "prompt":
        p["title"] = fill(40, seed)
        p["lines"] = [{"text": fill(56, seed + i), "tone": ["ink", "ink", "bad", "ok", "ink", "accent", "info", "warn"][i], "at": k(i, 8)} for i in range(8)]
    return p

def line(key, n=150, seed=0):
    return {"key": key, "text": fill(n, seed)}

narr = {"engine": "kokoro", "voice": "af_heart", "speed": 0.94, "fadeTailS": 0.3, "leadinS": 0.3, "holdS": 1.8, "gapS": 0.8, "beats": {}}
spec = {"version": 1, "id": "stress-max-lengths", "mode": "course", "series": fill(40), "number": 99,
        "title": fill(70), "label": fill(40, 5), "next": {"number": 100, "title": fill(60, 7)}, "site": fill(40, 9), "beats": []}

# cold: two panel steps, the second with three panels
narr["beats"]["cold"] = {"chapter": fill(60), "lines": [line(f"co{i}", 160, i) for i in range(6)]}
spec["beats"].append({"id": "cold", "kind": "cold", "heading": fill(60), "steps": [
    {"step": "panel", "panel": panel("prompt", ["co0", "co1"], 1)},
    {"step": "panel", "panels": [panel("table", ["co2"], 2), panel("compare", ["co3", "co4"], 3), panel("flow", ["co5"], 4)]},
]})
narr["beats"]["title"] = {"lines": [line("t0", 70), line("t1", 220, 3)]}
spec["beats"].append({"id": "title", "kind": "title", "mark": spec["title"][10:50]})

N = 10
for c in range(1, N + 1):
    lines = [line("k0", 230, c)]
    lines += [line("s0", 180, c), line("s1", 180, c + 1)]
    lines += [line("p0", 180, c), line("p1", 180, c + 2)]
    lines += [line("q0", 230, c), line("q1", 230, c + 1)]
    lines += [line(f"t{i}", 160, c + i) for i in (1, 2, 3)]
    lines += [line(f"m{i}", 160, c + i) for i in range(1, 7)]
    lines += [line("n0", 180, c), line("n1", 180, c + 1), line("n2", 180, c + 2)]
    lines += [{"key": "r0", "text": "Remember: " + fill(200, c)}, {"key": "r1", "text": "The trap: " + fill(200, c + 1)}, {"key": "r2", "text": "Try this: " + fill(200, c + 2)}]
    lines += [line("h0", 160, c), line("h1", 160, c + 1)]
    narr["beats"][f"c{c}"] = {"chapter": fill(60, c), "cueLeadS": 0.25, "preDelayS": 0.3, "lines": lines}
    k = lambda off: KINDS[(c - 1 + off) % 8]
    claim = lines[0]["text"]
    vis = lambda name, keys, off: ({"panels": [panel(k(off), keys[:1], c), panel(k(off + 4), keys[1:], c + 1)]} if c > 8 else {"panel": panel(k(off), keys, c)})
    number = {"step": "number", "source": {"text": fill(160, c)}}
    number.update({"panels": [panel(k(3), ["n0"], c), panel(k(5), ["n1"], c), panel(k(6), ["n2"], c)]} if c in (2, 9) else {"panel": panel(k(3), ["n0", "n1", "n2"], c)})
    spec["beats"].append({"id": f"c{c}", "kind": "concept", "heading": fill(60, c), "count": fill(12, c), "mark": claim[20:60],
        "steps": [
            {"step": "claim"},
            {"step": "situation", **vis("situation", ["s0", "s1"], 1)},
            {"step": "picture", **vis("picture", ["p0", "p1"], 2)},
            {"step": "think", "first": fill(70, c), "misses": fill(70, c + 1), "real": fill(90, c + 2)},
            {"step": "mechanism", "items": [{"text": fill(48, c + i), "at": f"m{i}"} for i in range(1, 7)], "side": panel(k(0), [f"m{i}" for i in range(1, 7)], c)},
            number,
            {"step": "keypoints"},
            {"step": "bridge", "label": fill(40, c), **vis("bridge", ["h0", "h1"], 4)},
        ]})

narr["beats"]["payoff"] = {"chapter": fill(60, 2), "lines": [line(f"y{i}", 160, i) for i in range(6)]}
spec["beats"].append({"id": "payoff", "kind": "payoff", "heading": fill(60, 2), "steps": [
    {"step": "panel", "panels": [panel("stats", ["y0"], 1), panel("bars", ["y1", "y2"], 2)]},
    {"step": "panel", "panel": panel("chips", ["y3", "y4", "y5"], 3)},
]})
narr["beats"]["recap"] = {"chapter": "Recap", "lines": [line("r0", 60)] + [line(f"r{i}", 200, i) for i in range(1, N + 1)]}
spec["beats"].append({"id": "recap", "kind": "recap", "heading": fill(60, 4)})
narr["beats"]["end"] = {"holdS": 9, "lines": [line("x0", 120)]}
spec["beats"].append({"id": "end", "kind": "end"})

json.dump(narr, open(os.path.join(HERE, "stress.narration.json"), "w"), indent=1)
json.dump(spec, open(os.path.join(HERE, "stress.spec.json"), "w"), indent=1)
print("wrote stress.narration.json and stress.spec.json")
