#!/usr/bin/env python3
"""Publish study-phase documents to the learning dashboard and verify them.

WHAT IT DOES
    1. PATCH /api/courses with the course's currentPhase and outline.
       With --create, POST /api/courses instead (first phase of a new course).
    2. For each document: DELETE /api/study?slug=..., then POST /api/study.
       The dashboard returns 500 when POSTing an existing slug, and its PATCH
       accepts only {slug, progress, status}. Delete-then-post is the update.
    3. GET every document of the course and compare the SHA-256 of the live
       content with the local file.

    The table of contents is built from '## ' headings OUTSIDE code fences.
    A fenced markdown example must never add entries.

CONFIGURATION
    Dashboard URL: --url, or STUDY_DASHBOARD_URL, or _index.json "dashboardUrl".
    Per-document metadata: a JSON file given with --meta, shaped as
      {"<slug>": {"title": "...", "summary": "...", "tags": [...],
                  "estimatedMinutes": 150}}
    A document with no metadata entry keeps the metadata already on the
    dashboard. A new document with no entry gets a title from its H1.

HOW TO RUN
    python push_dashboard.py --course study-material/<topic> --files <a.md> <b.md> --meta meta.json
    python push_dashboard.py --course study-material/<topic> --verify-only
    python push_dashboard.py --self-test

WHAT YOU SHOULD SEE
    PATCH /api/courses -> 200
    DELETE <slug> -> 200, POST <slug> -> 201
    <slug>  54,674 chars  MATCH  7 sections
    11/11 live and byte-identical
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

FENCE = re.compile(r"^```")


def anchor(title: str) -> str:
    a = re.sub(r"[^\w\s-]", "", title.lower())
    return re.sub(r"\s+", "-", a.strip()).strip("-")


def sections_for(text: str) -> list[dict]:
    out, in_code = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^##\s+(?!#)(.*)$", line)
        if m:
            raw = m.group(1).strip()
            label = re.sub(r"^[^\w\d]+", "", raw).strip()
            out.append({"title": re.sub(r"\s*\(.*?\)\s*$", "", label)[:60],
                        "anchor": anchor(raw)})
    return out


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def req(self, method: str, path: str, payload=None) -> tuple[int, str]:
        data = json.dumps(payload).encode() if payload is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=90) as resp:
                return resp.status, resp.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace")[:300]
        except Exception as e:  # noqa: BLE001
            return 0, f"{type(e).__name__}: {e}"

    def get_doc(self, slug: str) -> dict | None:
        st, body = self.req("GET", f"/api/study?slug={slug}")
        if st != 200:
            return None
        try:
            d = json.loads(body)
        except json.JSONDecodeError:
            return None
        rec = d[0] if isinstance(d, list) and d else d.get("data", d) if isinstance(d, dict) else None
        return rec if isinstance(rec, dict) and rec.get("content") is not None else None


def resolve_url(arg: str | None, course_dir: Path) -> str | None:
    if arg:
        return arg
    if os.environ.get("STUDY_DASHBOARD_URL"):
        return os.environ["STUDY_DASHBOARD_URL"]
    idx = course_dir.parent / "_index.json"
    if idx.exists():
        return json.loads(idx.read_text()).get("dashboardUrl")
    return None


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def verify(client: Client, course_dir: Path, topic: str) -> int:
    files = sorted(course_dir.glob(f"{topic}-phase-*.md")) + sorted(course_dir.glob(f"{topic}-review-*.md"))
    ok = 0
    print("\nverify:")
    for f in files:
        rec = client.get_doc(f.stem)
        if rec is None:
            print(f"  {f.stem:<52} MISSING")
            continue
        live = rec.get("content", "")
        same = sha(live) == sha(f.read_text())
        want = len(sections_for(f.read_text()))
        got = len(rec.get("sections") or [])
        ok += same and want == got
        flag = "MATCH" if same else "DIFF "
        toc = f"{got} sections" + ("" if want == got else f" (expected {want})")
        print(f"  {f.stem:<52} {len(live):>7,} chars  {flag}  {toc}")
    print(f"{ok}/{len(files)} live and byte-identical, with the expected table of contents")
    return len(files) - ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course", type=Path, help="course folder containing course.json")
    ap.add_argument("--files", nargs="*", type=Path, default=[], help="documents to (re)publish")
    ap.add_argument("--meta", type=Path, help="JSON file of per-slug metadata")
    ap.add_argument("--url", help="dashboard base URL")
    ap.add_argument("--create", action="store_true", help="POST the course record instead of PATCH")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--pause", type=float, default=1.4, help="seconds between writes")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        self_test()
    if not args.course:
        ap.error("--course is required")

    course = json.loads((args.course / "course.json").read_text())
    topic = course["topic"]
    url = resolve_url(args.url, args.course)
    if not url:
        print("No dashboard URL configured. Material is saved locally only.")
        sys.exit(0)
    client = Client(url)

    if not args.verify_only:
        if args.create:
            body = {k: course.get(k) for k in ("topic", "title", "totalPhases", "currentPhase", "outline")}
            body["config"] = {"language": course.get("language"), "anchors": course.get("anchors", [])}
            st, resp = client.req("POST", "/api/courses", body)
            print("POST /api/courses ->", st, resp[:100] if st >= 300 else "")
        else:
            st, resp = client.req("PATCH", "/api/courses", {
                "topic": topic, "currentPhase": course["currentPhase"], "outline": course["outline"]})
            print("PATCH /api/courses ->", st, resp[:100] if st >= 300 else "")
        if st >= 300 or st == 0:
            print("dashboard push failed, material saved locally")
            sys.exit(1)

        meta = json.loads(args.meta.read_text()) if args.meta else {}
        for f in args.files:
            slug = f.stem
            text = f.read_text()
            old = client.get_doc(slug) or {}
            m = meta.get(slug, {})
            h1 = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), slug)
            body = {
                "title": m.get("title") or old.get("title") or h1,
                "slug": slug,
                "category": m.get("category") or old.get("category") or topic,
                "difficulty": m.get("difficulty") or old.get("difficulty") or "advanced",
                "estimatedMinutes": m.get("estimatedMinutes") or old.get("estimatedMinutes") or 120,
                "tags": m.get("tags") or old.get("tags") or [topic],
                "summary": m.get("summary") or old.get("summary") or h1,
                "content": text,
                "sections": sections_for(text),
                "source": "study-skill",
                "filePath": f"study-material/{topic}/{f.name}",
            }
            if old:
                st, _ = client.req("DELETE", f"/api/study?slug={slug}")
                print(f"  DELETE {slug} -> {st}")
            st, resp = client.req("POST", "/api/study", body)
            print(f"  POST   {slug} -> {st} {resp[:100] if st >= 300 else ''}")
            time.sleep(args.pause)

    sys.exit(1 if verify(client, args.course, topic) else 0)


def self_test() -> None:
    text = "# T\n\n## 1.1 — Alpha (sub)\n\n```markdown\n## Status\n```\n\n## 🧪 Hands-on lab\n"
    secs = sections_for(text)
    checks = [
        ("ignores headings inside code fences", [s["title"] for s in secs] == ["1.1 — Alpha", "Hands-on lab"]),
        ("anchor matches the dashboard's slug rule",
         anchor("6.1 — Capacity planning (how many replicas, from your own numbers)")
         == "61-capacity-planning-how-many-replicas-from-your-own-numbers"),
        ("sections are objects, not strings", all(isinstance(s, dict) for s in secs)),
        ("hash differs on one changed byte", sha("a") != sha("b")),
    ]
    bad = 0
    print("push_dashboard self-test (no network)\n")
    for label, ok in checks:
        bad += not ok
        print(f"  [{'ok ' if ok else 'FAIL'}] {label}")
    print(f"\n{'all checks passed' if not bad else f'{bad} FAILED'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
