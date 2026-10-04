"""The job-search ledger: record a verified role, and read back what is known.

One table, not two files. The reference project this borrows from keeps a
`seen-jobs.csv` for every role ever verified and a `job-tracker.csv` for the
ones worth acting on, and its own notes explain why: discovery memory has to
survive even for roles rejected today, or next week's search surfaces them
again. That reasoning is right. Two hand-edited CSVs are not, when the
database can dedupe and a dashboard can read it.

``record_job`` prefers the ATS provider's stable posting id. When a source has
no id, it falls back to company, role and location. The URL is deliberately not
part of the key because the same posting can move between an ATS and a careers
page.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from pydantic_ai import ModelRetry, RunContext

from hq import db, job_retention, outreach
from hq.config import settings
from hq.job_pipeline import exhausted_targets, sweep_brief
from hq.obs import emit
from hq.privacy import private_employer
from hq.safety import ActionClass, Trust
from hq.tools.registry import HQDeps, hq_tool

log = logging.getLogger(__name__)

BUCKETS = ("strong", "decent", "stretch")

# The lower bound of every "N years" figure in a free-text experience band.
# Group 1 is the floor: "0-3 years" -> 0, "3+ years" -> 3, "~4 yrs" -> 4.
# Only digits actually attached to a year word count, so "SDE2+ / ~4 yrs"
# reads as 4 and not as 2.
_YEAR_SPAN_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:(?:\+|-|–|—|to)\s*(?:\d+(?:\.\d+)?)?)?\s*\+?\s*"
    r"(?:yrs?\.?|years?)\b",
    re.IGNORECASE,
)


# Scope words that put a role above what the owner can take, whatever the
# posting says about years. The years ceiling cannot catch these: "Lead AI
# Engineer" and "Engineering Manager" often name no years bar at all, so
# min_years_required returns None and the role sails through. Three of the
# four roles the 2026-09-10 sweep recorded were exactly this shape.
#
# Word-bounded so "Leadership" and "Headcount" in a title do not match, and
# deliberately not including "senior" alone in a compound like "Senior-friendly
# team" — the title field is short and this is the whole of it.
#
# "Staff" but not "Member of Technical Staff": MTS is the ENTRY title at Adobe,
# Salesforce, Nutanix and others (MTS 1 is a new graduate), and on 2026-09-12
# this gate closed Adobe's "Member of Technical Staff 1" at 9/10. A senior MTS
# still closes on its other word — "Senior", "Principal", "Lead".
_SENIOR_TITLE_RE = re.compile(
    r"\b(?:senior|sr\.?|(?<!technical )staff|principal|lead|leads|manager|head|director"
    r"|architect|vp|chief|founding|distinguished)\b",
    re.IGNORECASE,
)

# A level number on an engineering title: "SDE II", "SDE-2", "Software
# Engineer III", "MTS 2". He is making a level-one switch, so level two is the
# wrong rung even when its stated years slip under the ceiling — Flipkart's
# "SDE II, 2.5 years" passed the years gate on 2026-09-12 and stayed open.
_LEVEL_TITLE_RE = re.compile(
    r"\b(?:sde|swe|engineer|developer|mts|staff)[\s-]*(?:ii|iii|iv|[2-9])\b",
    re.IGNORECASE,
)


def senior_title(role: str) -> str | None:
    """The scope word that makes a title too senior, or None.

    The candidate profile is explicit: "roles clearly requiring senior, staff,
    lead, principal, manager, or founding engineer scope are not targets".
    Enforced here rather than in a prompt, for the same reason as the years
    ceiling — it is a fact about the owner, not a judgement call."""
    match = _SENIOR_TITLE_RE.search(role) or _LEVEL_TITLE_RE.search(role)
    return match.group(0).lower() if match else None


def min_years_required(experience_band: str) -> float | None:
    """The floor of the experience a posting asks for, or None when it names no
    number. The floor, not the ceiling: "2-4 years" is open to a candidate with
    two, so what matters is the smallest figure the posting will accept."""
    floors = [float(m.group(1)) for m in _YEAR_SPAN_RE.finditer(experience_band)]
    return min(floors) if floors else None


# The wrong rung in the other direction. He is employed, so a programme for
# students or first-jobbers will not credit him and is not a move. Word-bounded
# so "Internal Tools Engineer" is not an internship.
_INTERN_TITLE_RE = re.compile(
    r"\b(?:intern|interns|internship|internships|trainee|trainees|fresher|freshers"
    r"|apprentice|apprenticeship)\b",
    re.IGNORECASE,
)


def intern_title(role: str) -> str | None:
    """The word that makes a title an internship or fresher programme, or None."""
    match = _INTERN_TITLE_RE.search(role)
    return match.group(0).lower() if match else None




# --- the fit score -----------------------------------------------------------
#
# The rubric that used to be forty lines of hunter's card, as code: the same
# posting always gets the same number, and every point is written down in
# ``fit_parts`` so the reason behind a score can be read on the row. The model
# may move the total by one, with a reason, and no further.

FIT_BASE = 5
FIT_ADJUST_LIMIT = 1
# A stated package under the bar is close to a disqualifier: 25 LPA is the
# reason for the move. The -3 alone can leave a perfect-title role at 6, so a
# stated low package also caps the score in the stretch band.
LOW_PAY_CAP = 4
# At or above this computed score a row must carry its pay and its band.
DIG_SCORE = 6

# Lanes from the candidate profile, most specific first: "AI Backend Engineer"
# is applied AI, "Solutions Engineer" is the customer-facing lane.
LANES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("applied_ai", re.compile(
        r"\b(?:applied ai|ai engineer|ai/ml|ml engineer|machine learning engineer|llm"
        r"|generative ai|genai|gen ai|ai backend|ai platform|ai software engineer"
        r"|ai developer|agent(?:ic)? (?:engineer|infrastructure|platform))\b",
        re.IGNORECASE)),
    ("forward_deployed", re.compile(
        r"\b(?:forward[- ]deployed|deployment engineer|implementation engineer"
        r"|integrations? engineer|solutions? engineer|sales engineer|customer engineer"
        r"|technical account engineer|developer experience|developer relations|devrel"
        r"|support engineer|field engineer)\b",
        re.IGNORECASE)),
    ("software", re.compile(
        r"\b(?:software engineer|software developer|software development engineer"
        r"|sde|swe|backend|back[- ]end|product engineer|full[- ]?stack|platform engineer"
        r"|member of technical staff|mts)\b",
        re.IGNORECASE)),
)

# His real stack, from the candidate profile's strengths: the terms that make a
# posting's stack "his". Matched on the stack field and the title only; a
# description says "go live" too often for "go" to mean Go there.
PROFILE_STACK = (
    "go", "golang", "grpc", "protobuf", "microservices", "kubernetes", "k8s", "helm",
    "postgres", "postgresql", "redis", "rag", "llm", "llms", "agents", "mcp",
    "typescript", "python", "docker", "aws", "websockets",
)

# A customer-facing or applied-AI domain, read from the title and the two
# briefs: the work he already does, which fewer candidates can do both halves of.
_DOMAIN_RE = re.compile(
    r"\b(?:forward[- ]deployed|customer[- ]facing|solutions|implementation|integrations?"
    r"|developer (?:experience|tools|tooling|platform)|devtools|payments?|fintech"
    r"|ai infrastructure|llms?|agents?|agentic|rag|generative ai|genai|applied ai"
    r"|voice ai|conversational ai|mcp)\b",
    re.IGNORECASE,
)
_EARLY_RE = re.compile(r"\b(?:associate|early[- ]career|entry[- ]level|junior|jr\.?)\b",
                       re.IGNORECASE)
_NEW_GRAD_RE = re.compile(r"\b(?:new[- ]grads?|recent graduates?|graduates? only|campus)\b",
                          re.IGNORECASE)

_INDIA_RE = re.compile(
    r"\b(?:india|indian|bengaluru|bangalore|mumbai|pune|hyderabad|chennai|delhi|new delhi"
    r"|ncr|gurgaon|gurugram|noida|kolkata|ahmedabad|jaipur|kochi|trivandrum"
    r"|thiruvananthapuram|coimbatore|indore|chandigarh|mysore|mysuru)\b",
    re.IGNORECASE,
)
_GLOBAL_REMOTE_RE = re.compile(
    r"\b(?:anywhere|worldwide|global|globally|apac|asia)\b", re.IGNORECASE)
_WORK_MODE_RE = re.compile(
    r"\b(?:remote|hybrid|on[- ]?site|in[- ]office|office|wfh|work from home|flexible)\b",
    re.IGNORECASE,
)
_RELOCATION_RE = re.compile(r"\breloc", re.IGNORECASE)


# --- pay ---------------------------------------------------------------------

_NUM = r"(\d+(?:\.\d+)?)"
_RANGE_SEP = r"\s*(?:-|–|—|to)\s*"
_LAKH_RE = re.compile(
    _NUM + r"\s*(?:l|lpa|lakhs?|lacs?|lac)?(?:" + _RANGE_SEP + r"(?:₹|rs\.?|inr)?\s*" + _NUM
    + r")?\s*(?:lpa|lakhs?|lacs?|lac|l)\b",
    re.IGNORECASE,
)
_CRORE_RE = re.compile(
    _NUM + r"(?:" + _RANGE_SEP + _NUM + r")?\s*(?:cr|crores?)\b", re.IGNORECASE)
_RUPEE_RE = re.compile(r"(?<![\d.])(\d{6,9})(?![\d.])")
_RUPEE_MARK_RE = re.compile(r"₹|\binr\b|\brs\.?\s|\brupees?\b|\bctc\b|per annum",
                            re.IGNORECASE)
_ESTIMATE_RE = re.compile(
    r"\b(?:est|estimated?|approx|approximately|around|likely|typical|expected|band"
    r"|going rate)\b|~|levels\.fyi|glassdoor|ambitionbox|6figr",
    re.IGNORECASE,
)
_FOREIGN_RE = re.compile(r"\$|\busd\b|€|\beur\b|£|\bgbp\b", re.IGNORECASE)


def parse_pay(text: str) -> tuple[float, float, bool] | None:
    """``(low, high, estimated)`` in lakhs per annum from free text, or None.

    Reads "₹24-48 LPA", "20-30L", "25 LPA", "est. 18-24 LPA", "1.2 Cr" and
    "₹18,00,000 - 24,00,000". ``estimated`` is true when the text marks the
    figure as an estimate or a salary-site band rather than the posting's own
    number. A dollar or euro figure is not read: it says nothing about Indian
    pay."""
    raw = (text or "").strip()
    if not raw:
        return None
    flat = re.sub(r"(?<=\d),(?=\d)", "", raw)
    figures: list[float] = []
    for m in _LAKH_RE.finditer(flat):
        figures += [float(g) for g in m.groups() if g]
    for m in _CRORE_RE.finditer(flat):
        figures += [float(g) * 100 for g in m.groups() if g]
    if not figures and not _FOREIGN_RE.search(flat) and _RUPEE_MARK_RE.search(flat):
        figures = [int(m.group(1)) / 100_000 for m in _RUPEE_RE.finditer(flat)]
    figures = [f for f in figures if 0 < f < 1000]
    if not figures:
        return None
    return min(figures), max(figures), bool(_ESTIMATE_RE.search(raw))


def job_lane(role: str) -> str:
    """Which of the profile's three lanes a title is in, or "" for none."""
    for lane, pattern in LANES:
        if pattern.search(role):
            return lane
    return ""


def _stack_overlap(stack: str, role: str) -> list[str]:
    words = {w.rstrip(".") for w in re.findall(r"[a-z0-9+#.]+", f"{stack} {role}".casefold())}
    return [term for term in PROFILE_STACK if term in words]


def _geography(location: str, remote_policy: str) -> tuple[int, str]:
    """Points and a label: India or India-remote is 0, elsewhere -1 or -2.

    Work mode is never penalised; a place he has not asked for is."""
    text = f"{location} {remote_policy}".strip()
    if not text:
        return 0, "not stated"
    if _INDIA_RE.search(text):
        return 0, "India"
    if re.search(r"\bremote\b", text, re.IGNORECASE) and _GLOBAL_REMOTE_RE.search(text):
        return 0, "remote, open to India"
    place = re.sub(r"[^A-Za-z]+", " ", _WORK_MODE_RE.sub(" ", text)).strip()
    if not place:
        return 0, "work mode only, place not stated"
    if _RELOCATION_RE.search(text):
        return -1, f"outside India, with relocation: {text[:60]}"
    return -2, f"outside India: {text[:60]}"


class Fit(NamedTuple):
    score: int
    parts: dict[str, Any]
    lane: str
    pay_lakh: float | None


def fit_score(
    role: str,
    *,
    experience_band: str = "",
    compensation: str = "",
    pay_signal: str = "",
    stack: str = "",
    location: str = "",
    remote_policy: str = "",
    company_brief: str = "",
    role_brief: str = "",
    adjust: int = 0,
    adjust_reason: str = "",
) -> Fit:
    """The 0-10 fit of one posting for the owner, computed, with its parts.

    Start at 5. +2 the title is in one of his lanes; +2 a years floor under
    two (or an explicitly early-career posting), +1 a floor of two to three;
    +1 the stack overlaps his; +1 a customer-facing or applied-AI domain; +1
    pay at or above the bar; -3 a STATED package under it (and the score is
    then capped at 4); -1/-2 a geography outside India. ``adjust`` moves it
    by at most one, and only with a reason. Clamped to 0-10.

    The gates (senior, level-two, intern, years ceiling) are not here: they
    close a row whatever it scores, and ``record_job`` applies both."""
    bar = settings().job_target_ctc_lakh
    parts: dict[str, Any] = {"base": FIT_BASE}
    score = FIT_BASE

    lane = job_lane(role)
    lane_points = 2 if lane else 0
    parts["lane"] = {"lane": lane or "none", "points": lane_points}
    score += lane_points

    floor = min_years_required(experience_band)
    both = f"{experience_band} {role}"
    if _NEW_GRAD_RE.search(both):
        years_points, years_note = 0, "new-grad posting; he is employed"
    elif floor is None:
        early = bool(_EARLY_RE.search(both))
        years_points = 2 if early else 0
        years_note = "early career" if early else "not stated"
    elif floor < 2:
        years_points, years_note = 2, f"floor {floor:g}"
    elif floor < 3:
        years_points, years_note = 1, f"floor {floor:g}, a stretch"
    else:
        years_points, years_note = 0, f"floor {floor:g}, over the ceiling"
    parts["years"] = {"floor": floor, "note": years_note, "points": years_points}
    score += years_points

    matched = _stack_overlap(stack, role)
    stack_points = 1 if matched else 0
    parts["stack"] = {"matched": matched, "points": stack_points}
    score += stack_points

    found = sorted({m.group(0).lower() for m in _DOMAIN_RE.finditer(
        f"{role} {role_brief} {company_brief}")})
    domain_points = 1 if (found or lane in ("applied_ai", "forward_deployed")) else 0
    parts["domain"] = {"matched": found or ([lane] if domain_points else []),
                       "points": domain_points}
    score += domain_points

    pay = parse_pay(compensation) or parse_pay(pay_signal)
    pay_lakh = pay[1] if pay else None
    capped = False
    if pay is None:
        pay_points, pay_note = 0, "no figure"
    elif pay[1] >= bar:
        pay_points, pay_note = 1, f"up to {pay[1]:g} LPA, at or above {bar:g}"
    elif pay[2]:
        pay_points, pay_note = 0, f"estimated up to {pay[1]:g} LPA, under {bar:g}"
    else:
        pay_points, pay_note = -3, f"stated up to {pay[1]:g} LPA, under {bar:g}"
        capped = True
    parts["pay"] = {"lakh": pay_lakh, "estimated": bool(pay and pay[2]),
                    "note": pay_note, "points": pay_points}
    score += pay_points

    geo_points, geo_note = _geography(location, remote_policy)
    parts["geography"] = {"note": geo_note, "points": geo_points}
    score += geo_points

    adjust = max(-FIT_ADJUST_LIMIT, min(FIT_ADJUST_LIMIT, int(adjust)))
    if adjust and adjust_reason.strip():
        parts["adjust"] = {"points": adjust, "reason": adjust_reason.strip()[:300]}
        score += adjust

    if capped and score > LOW_PAY_CAP:
        parts["capped"] = f"stated pay under {bar:g} LPA caps the score at {LOW_PAY_CAP}"
        score = LOW_PAY_CAP
    score = max(0, min(10, score))
    parts["total"] = score
    return Fit(score, parts, lane, pay_lakh)


# record_job keeps a `fit_score` argument for the model's own number, which
# shadows the function inside it.
fit_score_for = fit_score


def fit_summary(parts: Mapping[str, Any]) -> str:
    """The parts of a score that moved it, in one line, for the tool's answer."""
    bits = []
    for key in ("lane", "years", "stack", "domain", "pay", "geography", "adjust"):
        part = parts.get(key)
        if isinstance(part, dict) and part.get("points"):
            bits.append(f"{key} {part['points']:+d}")
    if parts.get("capped"):
        bits.append(str(parts["capped"]))
    return f"base {parts.get('base', FIT_BASE)}" + (", " + ", ".join(bits) if bits else "")


# --- sweep back-off and the sweep brief --------------------------------------
#
# A board that lists nothing tonight will list nothing tomorrow more often than
# not, and the rotation used to live in the model's memory. The events the
# board tools already write are the record: three empty runs in a row inside
# two weeks put a target on the skip list until one of them turns something up.

BACKOFF_DAYS = 14


async def exhausted_sweep_targets(days: int = BACKOFF_DAYS) -> list[str]:
    """Targets with three consecutive zero-result runs in the last ``days``."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await db.fetch(
        "SELECT kind, run_id::text AS run_id, ts, payload FROM hq.events"
        " WHERE kind IN ('job_board', 'discover_companies') AND ts >= %s"
        " ORDER BY ts, id",
        (since,),
    )
    return exhausted_targets(rows)


async def known_companies(limit: int = 30) -> list[str]:
    """Companies already in the ledger, most recently seen first."""
    rows = await db.fetch(
        "SELECT company FROM hq.jobs GROUP BY company ORDER BY max(last_seen) DESC LIMIT %s",
        (limit,),
    )
    return [str(r["company"]) for r in rows if not private_employer(str(r["company"]))]


async def build_sweep_brief(today: date | None = None) -> str:
    """The nightly sweep brief with the ledger and the back-off list filled in."""
    day = today or datetime.now(ZoneInfo(settings().cron_tz)).date()
    return sweep_brief(
        today=day,
        known_companies=await known_companies(),
        exhausted=await exhausted_sweep_targets(),
    )

STATUSES = (
    "seen",
    "shortlisted",
    "referral",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "closed",
)
LIST_LIMIT = 50


def _normal(value: str) -> str:
    return " ".join(value.casefold().split())


def _dedupe_key(
    company: str, role: str, location: str, provider: str, external_id: str
) -> str:
    """Stable board id when available; conservative content identity otherwise."""
    provider, external_id = _normal(provider), external_id.strip()
    if provider and external_id:
        return f"ats:{provider}:{external_id}"
    return outreach.fallback_key(company, role, location)


def _like(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def legacy_prefixes(company: str, role: str) -> list[str]:
    """Key prefixes this role may be stored under: the company as written
    (brackets kept, as before 2026-10-04) and as dedupe now folds it."""
    first = company.split("(")[0]
    return list(dict.fromkeys([f"fallback:{_normal(company)}|", f"fallback:{_normal(first)}|"]))


async def _resolve_key(key: str, company: str, role: str, location: str = "") -> str:
    """The key already in the ledger for this role, if any, else `key`."""
    if not key.startswith("fallback:"):
        return key
    rows = await db.fetch(
        "SELECT dedupe_key FROM hq.jobs WHERE dedupe_key = %s OR dedupe_key LIKE ANY(%s)"
        " ORDER BY first_seen",
        (key, [_like(p) for p in legacy_prefixes(company, role)]))
    for row in rows:
        found = str(row.get("dedupe_key") or "")
        if found and (found == key or outreach.same_posting(found, company, role, location)):
            if found.endswith("|") and location.strip() and found != key:
                # A row stored with no location takes the first location it is
                # seen with, so a second city is a second row, not a merge.
                moved = await db.fetch(
                    "UPDATE hq.jobs SET dedupe_key = %s WHERE dedupe_key = %s"
                    " AND NOT EXISTS (SELECT 1 FROM hq.jobs WHERE dedupe_key = %s)"
                    " RETURNING dedupe_key", (key, found, key))
                return key if moved else found
            return found
    return key


def strongest_band(new: str, prior: str) -> str:
    """The band to score and gate on: a read that saw no year figure never
    replaces one that did. A role closed on "5-10 years stated in posting" was
    re-read from a board feed with no description, and the row then said "no
    floor visible" beside its closed note and was rescored 10; the next run
    took the ledger for the mistake."""
    if min_years_required(new) is None and min_years_required(prior) is not None:
        return prior
    return new or prior


async def _strongest_band(key: str, band: str) -> str:
    row = await db.fetchone("SELECT experience_band FROM hq.jobs WHERE dedupe_key = %s", (key,))
    return strongest_band(band, str((row or {}).get("experience_band") or ""))


@hq_tool(action=ActionClass.VAULT_WRITE, trust=Trust.TOOL, owner_only=False)
async def record_job(
    ctx: RunContext[HQDeps],
    company: str,
    role: str,
    url: str,
    fit_score: int | None = None,
    why_fit: str = "",
    location: str = "",
    remote_policy: str = "",
    experience_band: str = "",
    compensation: str = "",
    stack: str = "",
    source: str = "",
    provider: str = "",
    external_id: str = "",
    next_step: str = "",
    referral: str = "",
    company_brief: str = "",
    pay_signal: str = "",
    role_brief: str = "",
    linkedin_url: str = "",
    fit_adjust: int = 0,
    adjust_reason: str = "",
) -> str:
    """Record one verified role in the job ledger, or update it if already known.

    Call this for every role you actually verified, including ones too weak to
    apply to. That is the point: a role written down once is never researched
    twice, and next week's search can skip it.

    The fit score is COMPUTED here from the fields you pass: the title's lane,
    the years floor in `experience_band`, the package in `compensation` or
    `pay_signal`, `stack`, `location`/`remote_policy` and the two briefs. The
    answer tells you the score and what moved it. `fit_score`, if you pass
    one, is kept for comparison only. `fit_adjust` (-1, 0 or +1) with an
    `adjust_reason` is the one judgement you add, for something the fields
    cannot show. `why_fit` is one sentence on why the role is or is not worth
    his time.

    A senior, lead, staff, principal, manager, founding or level-two title, an
    internship, trainee or fresher title, and a years floor at or above the
    ceiling are all filed closed automatically. Do not spend run budget on
    one: skip it at the board listing rather than opening its page.

    Always fill `experience_band` with what the posting actually asks for, and
    `compensation` with the package when the posting or a salary page names
    one. A role that scores 6 or better is refused until it has both a band
    and a package (`compensation` or `pay_signal`, "no public signal" counts).

    Verify the listing is real and open before recording it. A search result
    title is not verification.

    For a role that clears the gates and scores 6 or better, do the company
    dig BEFORE recording and fill these three:

    - `company_brief`: what they actually build, how big, what stage. One or
      two sentences from their own site or a funding announcement.
    - `pay_signal`: what the evidence says about money — a stated range, a
      Levels.fyi or Glassdoor band for that level and city, or the honest
      "no public signal". The owner is employed; a move has to pay.
    - `role_brief`: what the job is really day to day, past the title, from
      the posting's own responsibilities.

    `linkedin_url` is the LinkedIn job post when the role came from LinkedIn.
    It is the link on the owner's board — he applies from LinkedIn, not from
    the company's own portal — so pass it whenever you have it.

    Leave them empty for a weak fit rather than guessing. `researched_at` is
    stamped when any of the three is present, so the board can tell an
    unresearched role from a researched one with nothing to report.
    """
    company, role, url = company.strip(), role.strip(), url.strip()
    if not company or not role:
        raise ModelRetry("company and role are both required")
    if not url.startswith(("http://", "https://")):
        raise ModelRetry("url must be the full listing address, starting with https://")
    if private_employer(company):
        # Not a retry: no argument makes this company researchable.
        return (
            "not recorded: this company is one of the owner's own employers, and"
            " those are never researched or filed. Move on to the next company."
        )
    if fit_score is not None and not 0 <= int(fit_score) <= 10:
        raise ModelRetry("fit_score must be between 0 and 10, or left out")
    if not why_fit.strip():
        raise ModelRetry("why_fit is required: one sentence saying why this role fits or not")
    if linkedin_url.strip() and not linkedin_url.strip().startswith(("http://", "https://")):
        raise ModelRetry("linkedin_url must be the full https:// job post address, or empty")
    if int(fit_adjust) not in (-1, 0, 1):
        raise ModelRetry("fit_adjust is -1, 0 or +1; the rest of the score is computed")
    if fit_adjust and not adjust_reason.strip():
        raise ModelRetry("fit_adjust needs adjust_reason: one sentence the fields cannot show")

    key = await _resolve_key(_dedupe_key(company, role, location, provider, external_id),
                             company, role, location)
    gone = job_retention.removed_recently(key) or (
        job_retention.removed_matching(
            lambda k: outreach.same_posting(k, company, role, location))
        if key.startswith("fallback:") else None)
    if gone:
        return (f"not recorded: {company} — {role} was first found more than"
                f" {job_retention.KEEP_DAYS} days ago and removed from the board on"
                f" {gone['removed'][:10]}; it stays out for {job_retention.REMOVED_DAYS} days."
                " Move on to the next role.")
    experience_band = await _strongest_band(key, experience_band)
    fit = fit_score_for(
        role, experience_band=experience_band, compensation=compensation,
        pay_signal=pay_signal, stack=stack, location=location,
        remote_policy=remote_policy, company_brief=company_brief,
        role_brief=role_brief, adjust=int(fit_adjust), adjust_reason=adjust_reason,
    )
    parts = dict(fit.parts)
    if fit_score is not None:
        parts["model_score"] = int(fit_score)
    score = fit.score
    bucket = "strong" if score >= 8 else ("decent" if score >= DIG_SCORE else "stretch")

    # Seniority is a hard fact about the owner, not a preference to weigh, so
    # it is applied here rather than trusted to the prompt. The row is still
    # written: skipping it entirely would only mean rediscovering the same
    # posting next week and spending another run rejecting it.
    bar = settings().job_max_min_years
    floor = min_years_required(experience_band)
    over_bar = floor is not None and floor >= bar
    too_senior = senior_title(role)
    too_junior = intern_title(role)
    closed = bool(over_bar or too_senior or too_junior)
    status = "closed" if closed else "seen"
    if over_bar:
        note = (
            f"Closed on record: the posting asks for {floor:g}+ years and the"
            f" owner is early-career (bar is {bar:g})."
        )
    elif too_senior:
        note = (
            f"Closed on record: the title is {too_senior!r} scope, which the"
            " candidate profile excludes."
        )
    elif too_junior:
        note = (
            f"Closed on record: the title is an {too_junior!r} programme, and the"
            " owner is already employed."
        )
    else:
        note = ""
    # A role worth his time has to say what it pays and what it asks for, or
    # he has to open the posting himself to find out.
    if not closed and score >= DIG_SCORE:
        missing = []
        if not (compensation.strip() or pay_signal.strip()):
            missing.append("compensation or pay_signal (a figure, an estimate with its"
                           " basis, or \"no public signal\")")
        if not experience_band.strip():
            missing.append("experience_band (the years the posting asks for)")
        if missing:
            raise ModelRetry(
                f"this role scores {score}/10, so it needs " + " and ".join(missing)
                + ". Find them, then call record_job again"
            )
    # Stamped only when the dig actually produced something, so the board can
    # tell "not researched yet" from "researched, nothing to report".
    researched = (
        datetime.now(UTC)
        if any(v.strip() for v in (company_brief, pay_signal, role_brief))
        else None
    )
    rows = await db.fetch(
        """
        INSERT INTO hq.jobs (company, role, url, source, provider, external_id,
                             dedupe_key, location, remote_policy, experience_band,
                             compensation, stack, fit_score, fit_bucket, why_fit,
                             next_step, referral, status, notes,
                             company_brief, pay_signal, role_brief, researched_at,
                             linkedin_url, fit_parts, pay_lakh, lane, channel)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (dedupe_key) DO UPDATE SET
            -- A rediscovery refreshes facts but never overwrites a status the
            -- owner moved along.
            last_seen = now(), updated_at = now(),
            seen_count = hq.jobs.seen_count + 1,
            url = EXCLUDED.url,
            source = COALESCE(NULLIF(EXCLUDED.source, ''), hq.jobs.source),
            provider = COALESCE(NULLIF(EXCLUDED.provider, ''), hq.jobs.provider),
            external_id = COALESCE(NULLIF(EXCLUDED.external_id, ''), hq.jobs.external_id),
            location = COALESCE(NULLIF(EXCLUDED.location, ''), hq.jobs.location),
            remote_policy = COALESCE(NULLIF(EXCLUDED.remote_policy, ''), hq.jobs.remote_policy),
            experience_band = COALESCE(NULLIF(EXCLUDED.experience_band, ''), hq.jobs.experience_band),
            compensation = COALESCE(NULLIF(EXCLUDED.compensation, ''), hq.jobs.compensation),
            stack = COALESCE(NULLIF(EXCLUDED.stack, ''), hq.jobs.stack),
            fit_score = EXCLUDED.fit_score,
            fit_bucket = EXCLUDED.fit_bucket,
            why_fit = EXCLUDED.why_fit,
            next_step = COALESCE(NULLIF(EXCLUDED.next_step, ''), hq.jobs.next_step),
            referral = COALESCE(NULLIF(EXCLUDED.referral, ''), hq.jobs.referral),
            company_brief = COALESCE(NULLIF(EXCLUDED.company_brief, ''), hq.jobs.company_brief),
            pay_signal = COALESCE(NULLIF(EXCLUDED.pay_signal, ''), hq.jobs.pay_signal),
            role_brief = COALESCE(NULLIF(EXCLUDED.role_brief, ''), hq.jobs.role_brief),
            researched_at = COALESCE(EXCLUDED.researched_at, hq.jobs.researched_at),
            linkedin_url = COALESCE(NULLIF(EXCLUDED.linkedin_url, ''), hq.jobs.linkedin_url),
            fit_parts = EXCLUDED.fit_parts,
            pay_lakh = COALESCE(EXCLUDED.pay_lakh, hq.jobs.pay_lakh),
            lane = EXCLUDED.lane,
            channel = CASE WHEN hq.jobs.channel IN ('', 'other') THEN EXCLUDED.channel
                           ELSE hq.jobs.channel END
        RETURNING id::text, seen_count, status
        """,
        (
            company,
            role,
            url,
            source.strip()[:60],
            provider.strip().lower()[:40],
            external_id.strip()[:160],
            key,
            location.strip()[:120],
            remote_policy.strip()[:80],
            experience_band.strip()[:200],
            compensation.strip()[:120],
            stack.strip()[:200],
            score,
            bucket,
            why_fit.strip()[:500],
            next_step.strip()[:300],
            referral.strip()[:500],
            status,
            note,
            company_brief.strip()[:600],
            pay_signal.strip()[:300],
            role_brief.strip()[:600],
            researched,
            linkedin_url.strip()[:500],
            db.jsonb(parts),
            fit.pay_lakh,
            fit.lane,
            outreach.channel_of(source, provider, url),
        ),
    )
    row = rows[0]
    await emit(
        "job.recorded",
        run_id=ctx.deps.run_id,
        task_id=ctx.deps.task_id,
        agent=ctx.deps.agent,
        payload={
            "company": company,
            "role": role,
            "fit_score": score,
            "model_score": fit_score,
            "seen_count": row["seen_count"],
        },
    )
    again = f" (seen {row['seen_count']} times)" if row["seen_count"] > 1 else ""
    # Same order as the note above, so the reason hunter is told matches the
    # reason written on the row. A role can trip more than one gate.
    if closed and row["status"] == "closed":
        if over_bar:
            why = (f"the posting asks for {floor:g}+ years, over the owner's"
                   f" {bar:g}-year ceiling")
        elif too_senior:
            why = f"{too_senior!r} scope is above what the owner can take"
        else:
            why = f"{too_junior!r} programmes are below where the owner already is"
        return (
            f"recorded {company} — {role} as CLOSED{again}: {why}. It is in the"
            " ledger so it is not researched again. Do not look for a referral,"
            " do not report it as a candidate role, and do not spend more of"
            " this run on it."
        )
    differs = (
        f"; you proposed {fit_score}, the fields support {score}"
        if fit_score is not None and int(fit_score) != score else ""
    )
    return (
        f"recorded {company} — {role}: {score}/10 {bucket}{again},"
        f" status {row['status']} ({fit_summary(parts)}{differs})"
    )


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def list_jobs(
    ctx: RunContext[HQDeps], status: str = "", company: str = ""
) -> list[dict]:
    """Roles already in the ledger, newest first.

    Check this BEFORE researching a company, so you do not spend a run
    rediscovering something already recorded. Pass `company` to see what is
    known about one, or `status` to see a stage of the pipeline. Each row's
    `job_id` is what `file_shortlist` takes.
    """
    where: list[str] = ["true"]
    params: list[object] = []
    if status:
        if status not in STATUSES:
            raise ModelRetry(f"status must be one of {list(STATUSES)}")
        where.append("status = %s")
        params.append(status)
    if company.strip():
        where.append("company ILIKE %s")
        params.append(f"%{company.strip()}%")
    params.append(LIST_LIMIT)
    return await db.fetch(
        "SELECT id::text AS job_id, company, role, url, linkedin_url, source, provider,"
        " external_id, location, remote_policy, experience_band, compensation, pay_signal,"
        " pay_lakh::float8 AS pay_lakh, lane, stack, fit_score,"
        " fit_bucket, status, why_fit, next_step, referral, seen_count, last_seen"
        f" FROM hq.jobs WHERE {' AND '.join(where)}"
        " ORDER BY fit_score DESC, last_seen DESC LIMIT %s",
        tuple(params),
    )
