"""Y Combinator's company directory and job postings, read the way the
ycombinator.com/companies page reads them.

The old source, api.ycombinator.com/v0.1, returns 20 companies a page with
no hiring field, and discover_companies read only the first page: for
India that was the same 20 of 12 pages every night, hiring or not. The
directory page instead queries YC's own search index (Algolia) with a
read-only key it publishes in the page, and that index filters by hiring,
region, batch and industry, 1,000 rows a page. On 2026-10-03 it held 6,269
companies, 1,489 hiring, 54 of them hiring in India. The approach comes
from github.com/adityajha2005/yc-outreach (MIT).

Each company's own page carries a JSON blob with its founders (LinkedIn
and X) and its job postings: title, location, salary range, equity,
minimum experience, skills and age. In a sample of the 20 newest companies
hiring in India, 98 of 103 postings stated a salary. A posting there is the
company's own listing, so it is a source, not only a lead.

Everything read here is web text: escaped and cut by the callers, and never
an instruction.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

DIRECTORY_URL = "https://www.ycombinator.com/companies"
INDEX = "YCCompany_production"
# A browser user agent: the directory page answers a bare client with a
# challenge page that has no search key in it.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      " (KHTML, like Gecko) Chrome/128 Safari/537.36")
PAGE_TTL_S = 6 * 3600       # a company page is read at most once in six hours
PAGE_CONCURRENCY = 6
_KEY_RE = re.compile(r'window\.AlgoliaOpts = \{"app":"(\w+)","key":"([^"]+)"')
_DATA_RE = re.compile(r'data-page="([^"]*)"')
_SLUG_RE = re.compile(r"^[a-z0-9-]{1,100}$")
_AGE_RE = re.compile(r"(?:less than|about|over|almost)?\s*(a|an|\d+)\s*"
                     r"(minute|hour|day|week|month|year)s?", re.IGNORECASE)
_AGE_DAYS = {"minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}
_US_RE = re.compile(r"(?:,\s*|\()US\b|\(US\)")
_IN_RE = re.compile(r"(?:,\s*|\()IN\b")
_SEASON = {"W": "Winter", "S": "Summer", "F": "Fall", "X": "Spring"}

_key: tuple[str, str] | None = None
_pages: dict[str, tuple[float, dict[str, Any] | None]] = {}


class DirectoryError(RuntimeError):
    """YC's directory could not be read."""


def batch_name(batch: str) -> str:
    """"W25" -> "Winter 2025"; a full name is returned as it is."""
    b = batch.strip()
    m = re.fullmatch(r"([WSFX])(\d{2})", b, re.IGNORECASE)
    return f"{_SEASON[m.group(1).upper()]} 20{m.group(2)}" if m else b


def regions_for(location: str) -> list[str]:
    """The index's regions for a pipe-separated place filter. India and
    remote by default: where his roles are."""
    want = location.casefold()
    out = []
    if not want or any(w in want for w in ("india", "bengaluru", "bangalore")):
        out.append("India")
    if not want or any(w in want for w in ("remote", "worldwide", "anywhere", "apac")):
        out.append("Remote")
    return out or ["India", "Remote"]


# Some postings name only the city: Cardboard's "Backend Engineer" says "Bengaluru".
_INDIAN_CITIES = ("bengaluru", "bangalore", "gurugram", "gurgaon", "hyderabad", "mumbai",
                  "pune", "delhi", "noida", "chennai", "kolkata", "ahmedabad", "jaipur")
_OPEN_WORDS = {"in", "india", "global", "worldwide", "anywhere", "apac", "asia"}
_REMOTE_RE = re.compile(r"remote(?:\s*\(([^)]*)\))?", re.IGNORECASE)


def open_to_india(place: str) -> bool:
    """Whether someone in India can take the role: an Indian location, or
    remote with no country or with India among its countries. A YC company
    in the "Remote" region often hires remote in the US or EU only
    ("San Francisco, CA, US / Remote (US)")."""
    low = place.casefold()
    if _IN_RE.search(place) or "india" in low or any(c in low for c in _INDIAN_CITIES):
        return True
    for m in _REMOTE_RE.finditer(place):
        where = set(re.findall(r"[a-z]+", (m.group(1) or "").casefold()))
        if not where or where & _OPEN_WORDS:
            return True
    return False


_PAY_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([KkMmLl](?![a-z]))?")


def rupee_lakhs(salary: str) -> str:
    """YC's rupee salary in the lakh form the ledger reads, the original kept.

    "₹800K - ₹1.2M INR" -> "₹8-12 LPA (YC: ₹800K - ₹1.2M INR)". A figure with
    no unit under 1,000 ("₹5 - ₹6 INR") can only be lakhs, and it is the
    employer's own number, so it counts as stated. On 2026-10-03 it was
    marked approx, and a stated ₹5-6 LPA scored 7 because the ledger
    penalises only stated pay. Not rupees: returned as it is."""
    raw = salary.strip()
    if not raw or not ("₹" in raw or "inr" in raw.casefold()) or re.search(r"[$€£]", raw):
        return raw
    lakhs = []
    for m in _PAY_NUM_RE.finditer(raw.replace(",", "")):
        v, unit = float(m.group(1)), (m.group(2) or "").upper()
        if unit == "K":
            lakhs.append(v / 100)
        elif unit == "M":
            lakhs.append(v * 10)
        elif unit == "L":
            lakhs.append(v)
        elif v >= 100_000:
            lakhs.append(v / 100_000)
        elif v < 1000:
            lakhs.append(v)
    if not lakhs:
        return raw
    lo, hi = min(lakhs), max(lakhs)
    band = f"{lo:g}-{hi:g}" if hi > lo else f"{lo:g}"
    return f"₹{band} LPA (YC: {raw})"


def posted_from_age(age: str, now: datetime | None = None) -> str:
    """"about 2 months" -> an ISO date about two months back, or "". The
    pages say how old a posting is, not when it was made."""
    m = _AGE_RE.search(age or "")
    if not m:
        return ""
    n = 1 if m.group(1).lower() in ("a", "an") else int(m.group(1))
    days = n * _AGE_DAYS[m.group(2).lower()]
    return ((now or datetime.now(UTC)) - timedelta(days=days)).isoformat()[:19]


async def _search_key(client: httpx.AsyncClient) -> tuple[str, str]:
    global _key
    if _key is None:
        resp = await client.get(DIRECTORY_URL, headers={"User-Agent": UA})
        m = _KEY_RE.search(resp.text if resp.status_code < 400 else "")
        if not m:
            raise DirectoryError("the YC directory page did not carry its search key")
        _key = (m.group(1), m.group(2))
    return _key


async def search(client: httpx.AsyncClient, facet_filters: list[list[str]],
                 hits_per_page: int = 1000, max_pages: int = 3) -> list[dict[str, Any]]:
    """Every company matching the filters (AND across lists, OR within one)."""
    global _key
    app, key = await _search_key(client)
    hits: list[dict[str, Any]] = []
    for page in range(max_pages):
        params = urlencode({"hitsPerPage": hits_per_page, "page": page,
                            "facetFilters": json.dumps(facet_filters)})
        resp = await client.post(
            f"https://{app}-dsn.algolia.net/1/indexes/{INDEX}/query",
            content=json.dumps({"params": params}),
            headers={"X-Algolia-Application-Id": app, "X-Algolia-API-Key": key,
                     "User-Agent": UA})
        if resp.status_code in (401, 403):
            _key = None                 # the published key rotated; read it again next time
            raise DirectoryError(f"YC's search refused the key (HTTP {resp.status_code})")
        resp.raise_for_status()
        body = resp.json()
        hits += body.get("hits") or []
        if page + 1 >= int(body.get("nbPages") or 0):
            break
    return hits


async def hiring_companies(client: httpx.AsyncClient, regions: list[str], *,
                           hiring: bool = True, industry: str = "",
                           batch: str = "") -> list[dict[str, Any]]:
    """Companies in any of `regions`, newest launch first."""
    filters: list[list[str]] = [[f"regions:{r}" for r in regions]]
    if hiring:
        filters.append(["isHiring:true"])
    if industry.strip():
        filters.append([f"industries:{industry.strip()}"])
    if batch.strip():
        filters.append([f"batch:{batch_name(batch)}"])
    hits = await search(client, filters)
    hits.sort(key=lambda h: h.get("launched_at") or 0, reverse=True)
    return hits


async def company_page(client: httpx.AsyncClient, slug: str) -> dict[str, Any] | None:
    """The JSON a company's YC page carries (company, founders, jobPostings),
    cached for PAGE_TTL_S. None when the page cannot be read."""
    if not _SLUG_RE.match(slug or ""):
        return None
    cached = _pages.get(slug)
    if cached and time.monotonic() - cached[0] < PAGE_TTL_S:
        return cached[1]
    props: dict[str, Any] | None = None
    try:
        resp = await client.get(f"{DIRECTORY_URL}/{slug}", headers={"User-Agent": UA})
        m = _DATA_RE.search(resp.text if resp.status_code < 400 else "")
        if m:
            props = json.loads(html.unescape(m.group(1))).get("props") or None
    except (httpx.HTTPError, ValueError):
        props = None
    _pages[slug] = (time.monotonic(), props)
    return props


async def company_pages(client: httpx.AsyncClient,
                        slugs: list[str]) -> list[tuple[str, dict[str, Any] | None]]:
    gate = asyncio.Semaphore(PAGE_CONCURRENCY)

    async def one(slug: str) -> tuple[str, dict[str, Any] | None]:
        async with gate:
            return slug, await company_page(client, slug)
    return list(await asyncio.gather(*(one(s) for s in slugs)))


def people(props: dict[str, Any]) -> list[dict[str, str]]:
    """The active founders, with what a referral needs: name, title, links.
    YC knows whether a founder has an email; it does not publish it, and
    nothing here guesses one."""
    out = []
    for f in (props.get("company") or {}).get("founders") or []:
        if not isinstance(f, dict) or f.get("is_active") is False or not f.get("full_name"):
            continue
        out.append({"name": str(f.get("full_name"))[:80], "title": str(f.get("title") or "")[:80],
                    "linkedin": str(f.get("linkedin_url") or ""),
                    "x": str(f.get("twitter_url") or "")})
    return out[:6]


def job_rows(props: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    """A company's YC job postings in the shape job_feed returns."""
    company = props.get("company") or {}
    founders = people(props)
    rows = []
    for j in props.get("jobPostings") or []:
        if not isinstance(j, dict) or not j.get("title"):
            continue
        place = str(j.get("location") or "")
        india = open_to_india(place)
        if india and "india" not in place.casefold():
            place += " (India)"         # "Gurugram, HR, IN" must match a filter for India
        pay = rupee_lakhs(str(j.get("salaryRange") or ""))
        if j.get("equityRange"):
            pay = f"{pay} + {j['equityRange']} equity".strip(" +")
        team = " / ".join(str(x) for x in (j.get("prettyRole"), j.get("roleSpecificType")) if x)
        skills = ", ".join(str(s) for s in (j.get("skills") or [])[:12])
        rows.append({
            "external_id": str(j.get("id") or ""),
            "company": str(j.get("companyName") or company.get("name") or "")[:80],
            "title": str(j.get("title"))[:200],
            "team": team[:80],
            "role_family": str(j.get("role") or ""),
            "location": place[:200],
            "remote_policy": "remote" if "remote" in place.casefold() else "",
            "open_to_india": india,
            "url": "https://www.ycombinator.com" + str(j.get("url") or ""),
            "posted": posted_from_age(str(j.get("createdAt") or ""), now),
            "age": str(j.get("createdAt") or ""),
            "experience": str(j.get("minExperience") or ""),
            "compensation": pay[:80],
            # YC's visa field is about US work visas: on an India seat it
            # read "US citizen/visa only" and looked like a bar to him.
            "visa": str(j.get("visa") or "") if _US_RE.search(place) else "",
            "batch": str(j.get("companyBatchName") or company.get("batch") or ""),
            "team_size": company.get("team_size"),
            "description": (f"{company.get('one_liner') or ''}"
                            + (f" Skills: {skills}." if skills else ""))[:800],
            "people": founders,
        })
    return rows
