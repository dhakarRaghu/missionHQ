#!/usr/bin/env python3
"""Fetch every URL in one or more markdown files and report its HTTP status.

WHY
    The study skill cites only URLs that were fetched in the same session.
    A search result is not a source, and links rot.

HOW TO RUN
    python check_urls.py <file.md> [<file.md> ...]
    python check_urls.py --workers 8 study-material/<topic>/*.md

WHAT YOU SHOULD SEE
    One line per unique URL: status code, final URL if redirected, source file.
    Exit code 0 when every URL returns 2xx. 1 otherwise.

NOTES
    Some publishers return 403 to scripts and load fine in a browser, for
    example usenix.org and parts of ACM and IEEE. The script marks those as
    BLOCKED. Open them in a browser, and say in the material that you did.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL = re.compile(r"https?://[^\s)<>\"'`\]]+")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
SKIP = ("example.com", "localhost", "127.0.0.1", "0.0.0.0")


def clean(u: str) -> str:
    return u.rstrip(".,;:")


def fetch(url: str, timeout: int) -> tuple[int, str]:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.geturl()
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 400, 404, 501):
                continue          # many servers reject HEAD; retry with GET
            return e.code, url
        except Exception as e:     # noqa: BLE001 - report any network failure
            if method == "HEAD":
                continue
            return 0, f"{type(e).__name__}: {e}"
    return 0, url


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args()

    where: dict[str, str] = {}
    for f in args.files:
        text = f.read_text()
        for m in URL.finditer(text):
            u = clean(m.group(0))
            if any(s in u for s in SKIP) or "<" in u:
                continue
            where.setdefault(u, f.name)

    with ThreadPoolExecutor(args.workers) as ex:
        results = dict(zip(where, ex.map(lambda u: fetch(u, args.timeout), where)))

    bad = 0
    for u in sorted(results):
        code, final = results[u]
        if 200 <= code < 300:
            tag = "OK     "
        elif code == 403:
            tag = "BLOCKED"
            bad += 1
        else:
            tag = "FAIL   "
            bad += 1
        extra = f"  -> {final}" if final and final != u and 200 <= code < 300 else ""
        extra = extra if not extra or final.rstrip("/") != u.rstrip("/") else ""
        err = f"  {final}" if code == 0 else ""
        print(f"{tag} {code:>3}  {u}{extra}{err}   [{where[u]}]")
    print(f"\n{len(results) - bad}/{len(results)} URLs returned 2xx")
    redirected = [u for u, (c, f) in results.items() if 200 <= c < 300 and f.rstrip("/") != u.rstrip("/")]
    if redirected:
        print(f"{len(redirected)} redirected. Cite the destination URL instead.")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
