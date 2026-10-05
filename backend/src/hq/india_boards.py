"""Indian job sites: Cutshort, Wellfound and Hirist.

On 2026-10-05 the nightly sweep read about 400 rows a week from Hacker News,
YC, Himalayas and known company boards, and almost all of them closed: North
America only, a years floor of 3 or more, or a senior title. In one browser
pass the same day, these three sites gave 8 level-one roles in India that no
other source had. Each page is read the way the browser reads it: the JSON a
page carries (`__NEXT_DATA__`) or the API the page itself calls. robots.txt
on 2026-10-05 allowed every path used here: Cutshort's /jobs/ and /job/
pages, Wellfound's /role/l/ and /jobs/<id> pages, and Hirist's API. Naukri
was left out: its robots.txt disallows Claude-User and other AI agents.

A listed posting is not always a live one. A Hirist posting from 2025-06-20
still had status 1 ("open") on 2026-10-05. So every row carries a verdict
from the site's own fields and the posting's age: closed when the site says
so or the page is gone, stale when it is older than STALE_DAYS, else open.
Every row also carries what the site says about the company, and flags for
a staffing repost or a services firm.

Everything read here is web text: cut by the callers and never an
instruction.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from hq import yc_directory as yc

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      " (KHTML, like Gecko) Chrome/129.0 Safari/537.36")
SOURCES = ("cutshort", "wellfound", "hirist")
# A posting older than this is stale: still listed, hiring most likely done.
STALE_DAYS = 45
CONCURRENCY = 3

CUTSHORT_PAGES = (
    "backend-developer-jobs-in-bangalore-bengaluru",
    "fullstack-developer-jobs-in-bangalore-bengaluru",
    "startup-jobs-in-bangalore-bengaluru",
    "product-based-company-jobs",
    "datascience-jobs",
    "backend-developer-jobs",
    "remote-jobs",
)
WELLFOUND_PAGES = (
    "software-engineer/india",
    "backend-engineer/bangalore",
    "artificial-intelligence-engineer/bangalore",
    "machine-learning-engineer/bangalore",
    "full-stack-engineer/bangalore",
    "software-engineer/remote",
)
# Hirist's categories, read at 0-2 years: backend, emerging tech and AI, data.
HIRIST_CATEGORIES = (1, 14, 15)
HIRIST_API = "https://gladiator.hirist.tech/job"
_HIRIST_HEADERS = {"Origin": "https://www.hirist.tech", "Referer": "https://www.hirist.tech/"}

_NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
_LD_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
# A company name or poster domain that is a recruiter, not the employer.
_STAFFING_RE = re.compile(
    r"staffing|recruit|placement|manpower|talent\s*(?:acquisition|solutions|hub)"
    r"|consultan(?:cy|ts)|\bhr\b|outsourc|hiring\s*partner"
    r"|staffnix|jobgether|crossing hurdles|devsunite|hiring",
    re.IGNORECASE)
# The first part of "Exotel - Integration Engineer I" is the company; the
# first part of "Data Engineer - Supply Chain Analytics" is a job title.
_ROLE_WORD_RE = re.compile(
    r"\b(?:engineer|developer|analyst|manager|designer|architect|lead|consultant"
    r"|scientist|specialist|executive|intern|administrator|tester|programmer|sde|sre)s?\b",
    re.IGNORECASE)
_WF_SIZE = {"SIZE_1_10": "1-10", "SIZE_11_50": "11-50", "SIZE_51_200": "51-200",
            "SIZE_201_500": "201-500", "SIZE_501_1000": "501-1000",
            "SIZE_1001_5000": "1001-5000", "SIZE_5001_PLUS": "5000+"}


def next_data(page: str) -> dict[str, Any] | None:
    """The JSON a Next.js page carries, or None."""
    m = _NEXT_RE.search(page)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", str(value or ""))).strip()[:limit]


def _iso(value: Any) -> str:
    """An ISO time from an ISO string or epoch seconds or milliseconds."""
    if isinstance(value, (int, float)) and value > 0:
        secs = value / 1000 if value > 10**11 else value
        return datetime.fromtimestamp(secs, UTC).isoformat()[:19]
    return str(value or "")[:19]


def age_days(posted: str, now: datetime | None = None) -> float | None:
    try:
        when = datetime.fromisoformat(str(posted)[:19]).replace(tzinfo=UTC)
    except ValueError:
        return None
    return ((now or datetime.now(UTC)) - when).total_seconds() / 86400


def verdict(open_flag: bool | None, posted: str, now: datetime | None = None,
            active: bool = False) -> tuple[str, str]:
    """("open" | "stale" | "closed" | "unknown", why).

    The site's own closed flag wins; then age, because a site can keep a
    filled posting listed as open for months. `active` is a site's mark that
    the company is processing applications now (Wellfound's "Actively
    Hiring"): it keeps a posting open up to twice STALE_DAYS."""
    if open_flag is False:
        return "closed", "the site marks the posting closed"
    days = age_days(posted, now)
    if days is not None and days > STALE_DAYS:
        if active and days <= 2 * STALE_DAYS:
            return "open", f"posted {days:.0f} days ago; the company is marked Actively Hiring"
        return "stale", f"posted {days:.0f} days ago; hiring is most likely done"
    if open_flag is None and days is None:
        return "unknown", "no status and no date on the posting"
    return "open", f"posted {days:.0f} days ago" if days is not None else "listed as open"


def staffing(*names: str) -> bool:
    return any(_STAFFING_RE.search(n or "") for n in names)


# Cutshort's startup and remote pages list sales, design and support roles
# too: a Retail Sales Consultant was recorded from one on 2026-10-05.
_TECH_TITLE_RE = re.compile(
    r"engineer|developer|\bsde\b|\bsre\b|programmer|scientist|\bml\b|\bai\b|machine learning"
    r"|data|backend|back-end|frontend|full[\s-]?stack|devops|platform|software|technical|forward deployed",
    re.IGNORECASE)
_SERVICES_NAME_RE = re.compile(r"consulting|technologies\s+pvt|infotech|it\s+services|softech",
                               re.IGNORECASE)


def tech_title(title: str) -> bool:
    return bool(_TECH_TITLE_RE.search(title or ""))


def _row(**kw: Any) -> dict[str, Any]:
    state, why = verdict(kw.pop("open_flag"), kw["posted"], kw.pop("now", None),
                         kw.pop("active", False))
    kw["posting"], kw["posting_note"] = state, why
    kw["flags"] = [f for f in kw.get("flags") or [] if f]
    return kw


# --- Cutshort -----------------------------------------------------------------

def cutshort_rows(data: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    """Rows from a Cutshort listing page's JSON."""
    try:
        query = data["props"]["pageProps"]["dehydratedState"]["queries"][0]
        jobs = query["state"]["data"]["data"]["pageData"]["jobs"]
    except (KeyError, IndexError, TypeError):
        return []
    rows = []
    for j in jobs or []:
        if not isinstance(j, dict) or not j.get("headline"):
            continue
        co = j.get("companyDetails") or {}
        facts = j.get("jobFactSummary") or {}
        exp = j.get("expRange") or {}
        name = str(co.get("name") or facts.get("companyName") or "")
        kind = str(co.get("type") or "")
        bits = [kind, f"{co['size']} people" if co.get("size") else "",
                str(co.get("stage") or ""), f"founded {co['founded']}" if co.get("founded") else "",
                str((co.get("links") or {}).get("website") or "")]
        remote = str(j.get("remoteType") or "")
        mode = {"remote_only": "remote", "remote_okay": "remote or onsite"}.get(remote, "")
        rows.append(_row(
            source="cutshort",
            external_id=str(j.get("_id") or ""),
            company=name[:80],
            title=str(j["headline"])[:200],
            location=str(j.get("locationsText") or ", ".join(j.get("locations") or []))[:200],
            remote_policy=mode,
            url=str(j.get("publicUrl") or ""),
            posted=_iso(facts.get("postedDate")),
            experience=f"{exp.get('min')}-{exp.get('max')} years" if exp.get("max") else "",
            compensation=str(j.get("salaryRangeText") or "")[:80],
            company_facts="; ".join(b for b in bits if b)[:240],
            flags=["staffing repost: posted for a client" if j.get("hiringForClient")
                   or co.get("hiringForClient") or staffing(name) else "",
                   "services firm" if kind == "Services" else ""],
            description=_text(j.get("sanitizedComment"), 800),
            open_flag=None, now=now,
        ))
    return rows


# --- Wellfound ------------------------------------------------------------------

def wellfound_rows(data: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    """Rows from a Wellfound role page's JSON (its Apollo cache)."""
    try:
        cache = data["props"]["pageProps"]["apolloState"]["data"]
    except (KeyError, TypeError):
        return []
    rows = []
    for key, co in cache.items():
        if not key.startswith("StartupResult:") or not isinstance(co, dict):
            continue
        badges = [str((cache.get(b.get("__ref"), {}) or {}).get("label") or "")
                  for b in co.get("badges") or [] if isinstance(b, dict)]
        hiring = "Actively Hiring" in badges
        facts = "; ".join(x for x in (
            f"{_WF_SIZE.get(str(co.get('companySize')), co.get('companySize') or '')} people"
            if co.get("companySize") else "",
            str(co.get("highConcept") or ""), ", ".join(b for b in badges if b)) if x)
        for ref in co.get("highlightedJobListings") or []:
            j = cache.get(ref.get("__ref")) if isinstance(ref, dict) else None
            if not isinstance(j, dict) or not j.get("title"):
                continue
            remote = (j.get("remoteConfig") or {}).get("kind") or ""
            places = list(dict.fromkeys(j.get("locationNames") or []))
            accepted = j.get("acceptedRemoteLocationNames") or []
            low = j.get("yearsExperienceMin")
            rows.append(_row(
                source="wellfound",
                external_id=str(j.get("id") or ""),
                company=str(co.get("name") or "")[:80],
                title=str(j["title"])[:200],
                location=", ".join(places + [f"Remote: {a}" for a in accepted])[:200]
                or ("Remote" if j.get("remote") else ""),
                remote_policy=("remote" if j.get("remote") or remote == "REMOTE_ONLY"
                           else "hybrid" if remote == "HYBRID" else ""),
                url=f"https://wellfound.com/jobs/{j.get('id')}-{j.get('slug') or ''}",
                posted=_iso(j.get("liveStartAt")),
                experience=f"{low}+ years" if low is not None else "",
                compensation=str(j.get("compensation") or "")[:80],
                company_facts=facts[:240],
                flags=["" if hiring else "not marked Actively Hiring",
                       "staffing repost" if staffing(str(co.get("name") or "")) else ""],
                description=_text(j.get("description"), 800),
                open_flag=None, now=now, active=hiring,
            ))
    return rows


# --- Hirist -----------------------------------------------------------------------

def hirist_rows(items: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Rows from Hirist's category API."""
    rows = []
    for j in items or []:
        if not isinstance(j, dict) or not j.get("title"):
            continue
        co = j.get("companyData") or {}
        ab = co.get("ambitionBoxInfo") or {}
        name = str(co.get("companyName") or "")
        title = str(j["title"]).strip()
        # "Exotel - Integration Engineer I": the company leads the title. A
        # title with no company in it is often a recruiter's posting.
        lead = title.split(" - ", 1)[0].strip() if " - " in title else ""
        if _ROLE_WORD_RE.search(lead):
            lead = ""
        pay = "" if j.get("hideSal") or not j.get("maxSal") else (
            f"{j.get('minSal')}-{j.get('maxSal')} LPA")
        rating = (f"AmbitionBox {ab['aggregateRatingOneDecimal']} from"
                  f" {ab.get('reviewsCount')} reviews") if ab.get("aggregateRatingOneDecimal") else ""
        places = ", ".join(str(p.get("name")) for p in j.get("locations") or j.get("location") or []
                           if isinstance(p, dict))
        rows.append(_row(
            source="hirist",
            external_id=str(j.get("id") or ""),
            company=(lead or name)[:80],
            title=title[:200],
            location=places[:200],
            remote_policy="remote" if j.get("workFromHome") else "",
            url=f"https://www.hirist.tech/j/{j.get('id')}",
            posted=_iso(j.get("createdTimeMs") or j.get("createdTime")),
            experience=f"{j.get('min')}-{j.get('max')} years" if j.get("max") is not None else "",
            compensation=pay,
            company_facts="; ".join(x for x in (name if name != lead else "", rating) if x)[:240],
            flags=["company kept confidential" if j.get("confidential") else "",
                   "staffing repost" if staffing(name, lead) else "",
                   "services firm" if _SERVICES_NAME_RE.search(f"{name} {lead}") else "",
                   "no company named in the title" if not lead else ""],
            description=", ".join(str(t.get("name")) for t in j.get("tags") or []
                                  if isinstance(t, dict))[:800],
            open_flag=None if j.get("status") is None else j.get("status") == 1, now=now,
        ))
    return rows


# --- reading the sites ----------------------------------------------------------

async def _page(client: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
    resp = await client.get(url)
    resp.raise_for_status()
    return next_data(resp.text)


async def read_source(client: httpx.AsyncClient, source: str) -> tuple[list[dict[str, Any]], int]:
    """Every row of one site's pages, one row per posting, and how many
    pages answered. A page that fails is skipped, not fatal."""
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(target: Any) -> list[dict[str, Any]] | None:
        async with gate:
            try:
                if source == "cutshort":
                    data = await _page(client, f"https://cutshort.io/jobs/{target}")
                    return cutshort_rows(data or {})
                if source == "wellfound":
                    data = await _page(client, f"https://wellfound.com/role/l/{target}")
                    return wellfound_rows(data or {})
                resp = await client.get(f"{HIRIST_API}/category/", headers=_HIRIST_HEADERS, params={
                    "minexp": 0, "maxexp": 2, "page": 0, "industry": "",
                    "categoryId": target, "size": 50})
                resp.raise_for_status()
                return hirist_rows(resp.json().get("data") or [])
            except (httpx.HTTPError, ValueError):
                return None

    targets = {"cutshort": CUTSHORT_PAGES, "wellfound": WELLFOUND_PAGES,
               "hirist": HIRIST_CATEGORIES}[source]
    results = await asyncio.gather(*(one(t) for t in targets))
    seen: dict[str, dict[str, Any]] = {}
    for rows in results:
        for row in rows or []:
            # Cutshort and Hirist list Indian jobs only, so a "Remote only",
            # "Work From Home" or "Hybrid" row there is open to India too.
            # Wellfound's remote page is worldwide: its rows are read.
            row["open_to_india"] = source != "wellfound" or yc.open_to_india(row["location"])
            seen.setdefault(row["url"] or row["external_id"], row)
    return list(seen.values()), sum(r is not None for r in results)


# --- one posting, checked again ---------------------------------------------------

def _hirist_id(url: str) -> str:
    m = re.search(r"-(\d{5,})/?$|/j/(\d{5,})/?$", urlparse(url).path)
    return (m.group(1) or m.group(2)) if m else ""


async def posting_status(client: httpx.AsyncClient, url: str,
                         now: datetime | None = None) -> dict[str, Any]:
    """Is this Cutshort, Wellfound or Hirist posting still hiring?

    Reads the posting itself: a page that is gone is closed; the site's own
    flag (Cutshort's jobValid, Hirist's status) comes next; then the age."""
    host = urlparse(url).netloc.lower()
    out: dict[str, Any] = {"url": url}
    if host.endswith("hirist.tech"):
        jid = _hirist_id(url)
        if not jid:
            return {**out, "posting": "unknown", "note": "no Hirist job id in the url"}
        resp = await client.get(f"{HIRIST_API}/detail", params={"jobcode": jid},
                                headers=_HIRIST_HEADERS)
        resp.raise_for_status()
        d = (resp.json() or {}).get("data") or {}
        if not d.get("id"):
            return {**out, "posting": "closed", "note": "Hirist has no such job"}
        row = hirist_rows([d], now)[0]
        domain = str(d.get("creatorDomainName") or "")
        out.update(posted=row["posted"], company=row["company"], company_facts=row["company_facts"],
                   applicants=d.get("applyCount"), posted_by_domain=domain,
                   flags=row["flags"] + (["posted by a recruiter domain"] if staffing(domain) else []))
        state, why = row["posting"], row["posting_note"]
    else:
        resp = await client.get(url)
        if resp.status_code in (404, 410):
            return {**out, "posting": "closed", "note": f"the page is gone (HTTP {resp.status_code})"}
        resp.raise_for_status()
        page = resp.text
        posted, valid_through = "", ""
        for block in _LD_RE.findall(page):
            try:
                ld = json.loads(block)
            except ValueError:
                continue
            for item in ld if isinstance(ld, list) else [ld]:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    posted = str(item.get("datePosted") or "")[:19]
                    valid_through = str(item.get("validThrough") or "")[:19]
        open_flag: bool | None = None
        if host.endswith("cutshort.io"):
            data = next_data(page) or {}
            try:
                page_data = data["props"]["pageProps"]["dehydratedState"]["queries"][0][
                    "state"]["data"]["data"]["pageData"]
                open_flag = bool(page_data.get("jobValid"))
            except (KeyError, IndexError, TypeError):
                pass
        elif host.endswith("wellfound.com"):
            out["actively_hiring"] = "Actively Hiring" in page
        active = bool(out.get("actively_hiring"))
        if valid_through and (age_days(valid_through, now) or 0) > 0:
            open_flag = False
        out.update(posted=posted, valid_through=valid_through)
        state, why = verdict(open_flag, posted, now, active)
    return {**out, "posting": state, "note": why}
