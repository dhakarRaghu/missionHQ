#!/usr/bin/env python3
"""Mechanical audit of one or more study-phase documents.

WHAT IT CHECKS
    Counts and structure from the study skill's self-audit table:
      size, box-drawn diagrams, tagged code blocks, WRONG/RIGHT pairs,
      sentence-to-remember / trap / action per concept section,
      exercises and their numbering, checkpoint questions, <details> blocks,
      required closing sections, balanced code fences.
    Commands the exercises use:
      every `python <script> --flag` in the text is checked against the
      script's --help output, when --code-dir is given.
    Language:
      prose sentences over the word limit, em-dashes, semicolons, and words
      from the avoid list, outside code blocks, tables, and headings.

HOW TO RUN
    python audit_phase.py study-material/<topic>/<topic>-phase-06a-*.md
    python audit_phase.py --code-dir study-material/<topic>/code  <files...>
    python audit_phase.py --phase0 <phase-00 file>      # Phase 0 targets
    python audit_phase.py --self-test

EXIT CODE
    0 when every hard check passes. 1 otherwise. Language findings are
    warnings unless --strict is given.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BOX = re.compile(r"[┌┐└┘│─├┤┬┴┼►◄▲▼█▏]")
FENCE = re.compile(r"^```(\w*)\s*$")
AVOID = ["leverage", "bottleneck", "on-ramp", "canon", "altitude", "compounds",
         "plumbing", "flywheel", "simply", "easily", "silver bullet",
         "under the hood", "earns its place", "might as well"]
REQUIRED = [r"Hands-on lab", r"Check it yourself|Codebase anchor",
            r"Checkpoint", r"References", r"Cheatsheet"]


def split_blocks(text: str):
    """Yield (kind, lang, body, start_line). kind is 'code' or 'prose'."""
    lines = text.splitlines()
    out, buf, in_code, lang, start = [], [], False, "", 1
    for i, line in enumerate(lines, 1):
        m = FENCE.match(line)
        if m:
            out.append(("code" if in_code else "prose", lang, "\n".join(buf), start))
            buf, start = [], i + 1
            if in_code:
                in_code, lang = False, ""
            else:
                in_code, lang = True, m.group(1)
            continue
        buf.append(line)
    out.append(("code" if in_code else "prose", lang, "\n".join(buf), start))
    return out, in_code


def concept_sections(text: str):
    """Numbered concept sections: '## 6.1 — ...' up to the next '## '.

    Headings inside code fences are ignored. A markdown example inside a
    fence, such as a decision record, must not end a section early.
    """
    sections, current, in_code = [], None, False
    for line in text.splitlines():
        if FENCE.match(line):
            in_code = not in_code
        if not in_code and line.startswith("## "):
            if current is not None:
                sections.append("\n".join(current))
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        sections.append("\n".join(current))
    return [p for p in sections if re.match(r"## \d+\.\d+", p)]


def prose_lines(blocks):
    for kind, _, body, start in blocks:
        if kind != "prose":
            continue
        for off, line in enumerate(body.splitlines()):
            s = line.strip()
            if not s or s.startswith(("#", "|", "<", ">")):
                continue
            yield start + off, line


def check_flags(text: str, code_dir: Path | None):
    problems = []
    if not code_dir:
        return problems
    cmds = set(re.findall(r"python3? ((?:[\w./-]+/)?[\w-]+\.py)((?: --?[\w-]+(?:[ =][^\s`]+)?)*)", text))
    helps: dict[str, str] = {}
    for script, args in sorted(cmds):
        path = code_dir / script
        if not path.exists():
            problems.append(f"script not found: {script}")
            continue
        if script not in helps:
            r = subprocess.run([sys.executable, str(path), "--help"], cwd=code_dir,
                               capture_output=True, text=True, timeout=60)
            helps[script] = r.stdout + r.stderr
        for flag in re.findall(r"(--[\w-]+)", args):
            if flag not in helps[script]:
                problems.append(f"{script}: flag {flag} is not in --help")
    return problems


def audit(path: Path, code_dir: Path | None, phase0: bool, max_words: int):
    text = path.read_text()
    blocks, unbalanced = split_blocks(text)
    code = [(lang, body) for kind, lang, body, _ in blocks if kind == "code"]
    size = len(text)                      # characters, as the dashboard reports
    diagrams = sum(1 for lang, body in code if lang == "" and BOX.search(body))
    tagged = [lang for lang, _ in code if lang]
    sections = concept_sections(text)
    exercises = [int(n) for n in re.findall(r"\*\*E(\d+)\b", text)]
    ex_unique = sorted(set(exercises))
    try:
        cp = re.split(r"(?m)^## .*Checkpoint", text, maxsplit=1)[1].split("<details>")[0]
        checkpoints = len(re.findall(r"(?m)^\d+\. ", cp))
    except IndexError:
        checkpoints = 0

    hard: list[tuple[str, bool, str]] = []
    lo, hi = (8_000, 15_500) if phase0 else (30_000, 55_000)
    hard.append(("size", lo <= size <= hi, f"{size:,} characters, target {lo:,}-{hi:,}"))
    need_diag = 3 if phase0 else 8
    hard.append(("diagrams", diagrams >= need_diag, f"{diagrams}, need {need_diag}+"))
    if not phase0:
        hard.append(("tagged code blocks", len(tagged) >= 3, f"{tagged}, need 3+"))
        hard.append(("WRONG/RIGHT pairs", min(text.count("WRONG"), text.count("RIGHT")) >= 1,
                     f"WRONG {text.count('WRONG')}, RIGHT {text.count('RIGHT')}"))
        hard.append(("exercises", len(ex_unique) >= 4,
                     f"E{ex_unique[0] if ex_unique else '-'}..E{ex_unique[-1] if ex_unique else '-'}, {len(ex_unique)} total"))
        contiguous = ex_unique == list(range(ex_unique[0], ex_unique[-1] + 1)) if ex_unique else False
        hard.append(("exercise numbering contiguous", contiguous, str(ex_unique)))
        hard.append(("break-it exercises", len(re.findall(r"(?i)\*\*E\d+ \([^)]*break", text)) >= 1,
                     "at least one per part"))
    hard.append(("concept sections", len(sections) >= 1, f"{len(sections)} found"))
    for sec in sections:
        title = sec.splitlines()[0][:50]
        ok = ("sentence to remember" in sec and "**The trap:**" in sec
              and re.search(r"\*\*(Try this now|Verify|Verify your understanding|In your codebase):\*\*", sec))
        hard.append((f"closers in {title}", bool(ok), "remember + trap + action"))
    hard.append(("checkpoint questions", 5 <= checkpoints <= 8, f"{checkpoints}, target 5-7"))
    hard.append(("answer sketches", "<details>" in text and "</details>" in text, "one <details> block"))
    for req in REQUIRED:
        present = re.search(rf"(?m)^## .*({req})", text) is not None
        if phase0 and ("lab" in req or "Check it" in req):
            continue
        hard.append((f"section: {req}", present, ""))
    hard.append(("code fences balanced", not unbalanced, ""))
    for p in check_flags(text, code_dir):
        hard.append(("command flag", False, p))

    warnings = []
    for n, line in prose_lines(blocks):
        is_ref = bool(re.match(r"\s*- \*\*.*\*\* — https?://", line))
        if "—" in line and not is_ref:
            warnings.append(f"L{n} em-dash in prose: {line.strip()[:80]}")
        if ";" in line and "http" not in line and "`" not in line:
            warnings.append(f"L{n} semicolon in prose: {line.strip()[:80]}")
        for sent in re.split(r"(?<=[.!?])\s+", re.sub(r"`[^`]*`", "X", line)):
            words = len(sent.split())
            if words > max_words:
                warnings.append(f"L{n} {words}-word sentence: {sent.strip()[:80]}")
        low = line.lower()
        for w in AVOID:
            if re.search(rf"\b{re.escape(w)}\b", low):
                warnings.append(f"L{n} avoid-list word '{w}': {line.strip()[:80]}")
    return hard, warnings


def report(path, hard, warnings):
    print(f"\n=== {path}")
    bad = 0
    for name, ok, detail in hard:
        bad += not ok
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}  {detail}")
    if warnings:
        print(f"  language warnings: {len(warnings)}")
        for w in warnings[:40]:
            print(f"    {w}")
        if len(warnings) > 40:
            print(f"    ... {len(warnings) - 40} more")
    return bad


SAMPLE = """# Phase 9 — Sample

Intro.

```
┌──┐
│A │
└──┘
```

## 9.1 — Thing

Why this matters: it is a sample.

```python
print(1)
```

**The sentence to remember:** sample.

**The trap:** none.

**Try this now:** run `python demo.py --fast`.

## ✅ Checkpoint 9 — answer

1. **Q1.** one
2. **Q2.** two
3. **Q3.** three
4. **Q4.** four
5. **Q5.** five

<details>
<summary>Answer sketches</summary>
1. a
</details>

## References & Further Learning

- **Paper** — https://example.com
  Focus on: Table 1; it is the one.

## Cheatsheet

```
x
```
"""


def self_test():
    import tempfile
    d = Path(tempfile.mkdtemp())
    f = d / "sample.md"
    f.write_text(SAMPLE + "\nThis sentence has far too many words in it to pass the plain English check that the skill requires for every line of prose.\n")
    hard, warnings = audit(f, None, phase0=True, max_words=20)
    names = {n: ok for n, ok, _ in hard}
    checks = [
        ("finds the concept section closers", names.get("closers in ## 9.1 — Thing") is True),
        ("counts 5 checkpoint questions", names.get("checkpoint questions") is True),
        ("fences balanced", names.get("code fences balanced") is True),
        ("flags the long sentence", any("-word sentence" in w for w in warnings)),
        ("allows an em-dash in a reference entry", not any("em-dash" in w and "Paper" in w for w in warnings)),
        ("flags a semicolon in prose", any("semicolon" in w for w in warnings)),
        ("flags a missing lab only for non-phase-0",
         "section: Hands-on lab" not in names),
    ]
    h = d / "fenced.md"
    h.write_text(SAMPLE.replace("**The sentence to remember:** sample.",
                                "```markdown\n## Status\nAccepted.\n```\n\n**The sentence to remember:** sample."))
    hard3, _ = audit(h, None, phase0=True, max_words=20)
    checks.append(("ignores headings inside code fences",
                   {n: ok for n, ok, _ in hard3}.get("closers in ## 9.1 — Thing") is True))
    g = d / "broken.md"
    g.write_text(SAMPLE.replace("**The trap:** none.", "") + "\n```\nopen fence\n")
    hard2, _ = audit(g, None, phase0=True, max_words=20)
    n2 = {n: ok for n, ok, _ in hard2}
    checks.append(("detects a missing trap line", n2.get("closers in ## 9.1 — Thing") is False))
    checks.append(("detects an unbalanced fence", n2.get("code fences balanced") is False))
    bad = 0
    print("audit_phase self-test\n")
    for label, ok in checks:
        bad += not ok
        print(f"  [{'ok ' if ok else 'FAIL'}] {label}")
    print(f"\n{'all checks passed' if not bad else f'{bad} FAILED'}")
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--code-dir", type=Path, help="course code/ folder, to check command flags")
    ap.add_argument("--phase0", action="store_true", help="use Phase 0 targets")
    ap.add_argument("--max-words", type=int, default=32, help="sentence length that triggers a warning")
    ap.add_argument("--strict", action="store_true", help="treat language warnings as failures")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
    if not args.files:
        ap.error("give at least one file")
    total_bad = 0
    for f in args.files:
        phase0 = args.phase0 or "-phase-00-" in f.name
        hard, warnings = audit(f, args.code_dir, phase0, args.max_words)
        total_bad += report(f, hard, warnings)
        if args.strict:
            total_bad += len(warnings)
    print(f"\n{'ALL HARD CHECKS PASSED' if not total_bad else f'{total_bad} PROBLEM(S)'}")
    sys.exit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
