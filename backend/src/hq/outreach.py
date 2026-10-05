"""The job pipeline past "found": the rules, as code.

On 2026-10-04 the ledger held 138 roles ever found and none had reached
applied, interviewing or offer. He gets offers through referrals and by
writing to founders himself (Gem's 2026 benchmark of 165M applicants: a
referral converts about 11x an inbound application). He finds the people
and writes every message himself; the pipeline finds roles, keeps the
follow-up clock on his applications, and never writes or sends anything.

The method comes from github.com/harshkas4na/job-ops (its outreach, network
and outcome skills), adapted: no tailored resumes, no message drafts, no referral finding, no
email integration, no autonomous submit. Everything here is pure, so it is tested without a
database or a model.
"""

from __future__ import annotations

import re

# --- where a role was found -----------------------------------------------------

CHANNELS = ("linkedin", "yc", "hn", "himalayas", "remotive", "remoteok",
            "cutshort", "wellfound", "hirist", "ats", "company_site", "other")
ATS_PROVIDERS = ("greenhouse", "lever", "ashby", "workable", "recruitee",
                 "smartrecruiters", "workday", "icims", "jobvite", "bamboohr")
_CHANNEL_RULES = (
    ("linkedin", re.compile(r"linkedin", re.IGNORECASE)),
    # HN before YC: an HN link is news.ycombinator.com.
    ("hn", re.compile(r"\bhn\b|hacker ?news|news\.ycombinator", re.IGNORECASE)),
    ("yc", re.compile(r"\byc\b|(?<!news\.)ycombinator|y combinator|work ?at ?a ?startup",
                      re.IGNORECASE)),
    ("himalayas", re.compile(r"himalayas", re.IGNORECASE)),
    ("remotive", re.compile(r"remotive", re.IGNORECASE)),
    ("remoteok", re.compile(r"remote ?ok", re.IGNORECASE)),
    ("cutshort", re.compile(r"cutshort", re.IGNORECASE)),
    ("wellfound", re.compile(r"wellfound|angel\.co", re.IGNORECASE)),
    ("hirist", re.compile(r"hirist", re.IGNORECASE)),
)


def channel_of(source: str, provider: str = "", url: str = "") -> str:
    """One of CHANNELS for a recorded role. `source` was free text written by
    a model ("Board sweep 2026-10-02: ashby/cardboard read", "HN", "Y"), so
    the channel is derived here, from the source, the url and the provider,
    in that order of trust."""
    text = f"{source} {url}"
    for name, pattern in _CHANNEL_RULES:
        if pattern.search(text):
            return name
    if provider.strip().lower() in ATS_PROVIDERS or any(p in text.lower() for p in ATS_PROVIDERS):
        return "ats"
    if re.search(r"board|job_board", source, re.IGNORECASE):
        return "ats"
    if url.startswith("http"):
        return "company_site"
    return "other"


# --- one role, one row ------------------------------------------------------------

_PARENS = re.compile(r"\s*\([^)]*\)")


def company_key(company: str) -> str:
    """The company as dedupe sees it: case and spaces folded, and a note in
    brackets dropped. "Clera (getclera.com)" and "Clera" are one company;
    "Cardboard (YC W26)" and "Cardboard" too."""
    return " ".join(_PARENS.sub("", company).casefold().split())


def role_key(role: str) -> str:
    return " ".join(role.casefold().split())


def fallback_key(company: str, role: str, location: str = "") -> str:
    """Identity for a role with no board id: company, role and location."""
    return f"fallback:{company_key(company)}|{role_key(role)}|{' '.join(location.casefold().split())}"


def same_posting(key: str, company: str, role: str, location: str) -> bool:
    """Whether a stored fallback key is this role. Bengaluru and London are
    two postings; but a location on one side and none on the other is one
    posting read twice, which became two rows (Clera, Flexibits and
    CareerJumpship on 2026-10-04). Company brackets are ignored on both."""
    if not key.startswith("fallback:"):
        return False
    try:
        k_company, k_role, k_location = key[len("fallback:"):].split("|", 2)
    except ValueError:
        return False
    if company_key(k_company) != company_key(company) or role_key(k_role) != role_key(role):
        return False
    here = " ".join(location.casefold().split())
    return not k_location or not here or k_location == here


# --- the follow-up clock ------------------------------------------------------------

FOLLOW_UP_DAYS = 7      # an application with no reply is followed up after this
MAX_TOUCHES = 2         # the application, and one follow-up; then it is ghosted
