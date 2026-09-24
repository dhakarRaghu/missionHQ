"""The weekly job shortlist, written by code from the ledger rows.

Sage used to write the shortlist page itself with `vault_write`, and the page
said "apply" for rows whose pay was an estimate from a salary site, or for a
row the ledger had closed. The rule was prose in a skill, and prose loses.

Here sage picks the rows and the action; code looks each row up, refuses
"apply" unless the row's pay is STATED (not estimated, not missing) and at or
above ``settings().job_target_ctc_lakh``, refuses a closed row outright, and
writes the page from the ledger: title, company, role, score, pay, status,
last live check, with the date stamped by code. The model's contribution is
the next step and the page title.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic_ai import ModelRetry, RunContext

from hq import db, memory
from hq.config import settings
from hq.continuity import CLOSED_JOB_STATUSES, pay_text
from hq.obs import emit
from hq.safety import ActionClass
from hq.tools.learning_tools import _today
from hq.tools.registry import HQDeps, hq_tool

SHORTLIST_DIR = "projects/jobs/"
PICKS_MIN, PICKS_MAX = 1, 5
ID_PREFIX_MIN = 8
NEXT_STEP_CHARS = 300
Action = Literal["apply", "referral", "verify_pay", "shortlist"]
ACTION_WORDS = {
    "apply": "Apply",
    "referral": "Ask for a referral",
    "verify_pay": "Verify pay",
    "shortlist": "Shortlist it on the board",
}


class Pick(TypedDict):
    job_id: str          # the row's id from list_jobs (the first 8 characters are enough)
    action: Action       # apply | referral | verify_pay | shortlist
    next_step: str       # the one thing he does, in one sentence


def shortlist_path(day: Any) -> str:
    return f"{SHORTLIST_DIR}shortlist-{day:%G-W%V}.md"


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "t", "1", "yes")
    return bool(value)


def _label(row: dict[str, Any]) -> str:
    return f"{row.get('company')}, {row.get('role')} ({str(row.get('job_id'))[:8]})"


def apply_problem(row: dict[str, Any], bar: float) -> str | None:
    """Why "apply" is refused for this row, or None. The row is a ledger row
    with ``pay_lakh`` and ``estimated`` (from ``fit_parts->pay``)."""
    pay = row.get("pay_lakh")
    if pay is None:
        return (f"{_label(row)}: no pay figure on the row, so the action is verify_pay,"
                " not apply")
    if _truthy(row.get("estimated")):
        return (f"{_label(row)}: pay is an estimate ({float(pay):g} LPA), not the posting's own"
                " figure, so the action is verify_pay, not apply")
    if float(pay) < bar:
        return (f"{_label(row)}: stated pay {float(pay):g} LPA is under the {bar:g} LPA bar;"
                " apply is not an action for it")
    return None


def pick_problems(picks: list[Pick], rows: dict[str, dict[str, Any]], bar: float) -> list[str]:
    """Every refusal for a set of picks against their ledger rows, keyed by
    the pick's job_id. Pure, so the gate is tested without a database."""
    problems: list[str] = []
    if not PICKS_MIN <= len(picks) <= PICKS_MAX:
        problems.append(f"{len(picks)} picks; the shortlist holds {PICKS_MIN} to {PICKS_MAX}")
    seen: set[str] = set()
    for pick in picks:
        row = rows.get(pick["job_id"])
        if row is None:
            problems.append(f"{pick['job_id']}: no such row in the ledger; use an id from list_jobs")
            continue
        rid = str(row.get("job_id"))
        if rid in seen:
            problems.append(f"{_label(row)} is picked twice")
        seen.add(rid)
        status = str(row.get("status") or "")
        if status in CLOSED_JOB_STATUSES:
            problems.append(f"{_label(row)} is {status}; a closed row is never revived")
            continue
        if status == "applied":
            problems.append(f"{_label(row)} is already applied; leave it out")
            continue
        if pick["action"] == "apply":
            problem = apply_problem(row, bar)
            if problem:
                problems.append(problem)
        if not pick.get("next_step", "").strip():
            problems.append(f"{_label(row)}: next_step is empty")
    return problems


def render_page(title: str, picks: list[Pick], rows: dict[str, dict[str, Any]],
                day: Any, bar: float) -> str:
    lines = [
        f"# {title.strip() or 'Job shortlist'}",
        "",
        (f"Week {day:%G-W%V}, written {day:%Y-%m-%d} from the job ledger. Score, pay and status"
         f" are the ledger's; only the next step is sage's. \"Apply\" appears only where the"
         f" posting states {bar:g} LPA or more. He acts; nothing here has been applied to."),
        "",
    ]
    for i, pick in enumerate(picks, 1):
        row = rows[pick["job_id"]]
        last = row.get("last_seen")
        checked = f", last live-checked {last:%Y-%m-%d}" if hasattr(last, "strftime") else ""
        lines.append(
            f"{i}. {row.get('company')}, {row.get('role')}: {row.get('fit_score')}/10,"
            f" {pay_text(row.get('pay_lakh'), row.get('estimated'))}, status {row.get('status')}"
            f"{checked}.")
        lines.append(f"   Next ({ACTION_WORDS[pick['action']]}): "
                     f"{' '.join(pick['next_step'].split())[:NEXT_STEP_CHARS]}")
    return "\n".join(lines) + "\n"


async def _rows_for(ids: list[str]) -> dict[str, dict[str, Any]]:
    """Ledger rows keyed by the id the model gave (full or a prefix)."""
    out: dict[str, dict[str, Any]] = {}
    for given in dict.fromkeys(ids):
        key = given.strip().lower()
        if len(key) < ID_PREFIX_MIN:
            continue
        found = await db.fetch(
            "SELECT id::text AS job_id, company, role, status, fit_score,"
            " pay_lakh::float8 AS pay_lakh, fit_parts->'pay'->>'estimated' AS estimated,"
            " last_seen FROM hq.jobs WHERE id::text LIKE %s LIMIT 2", (key + "%",))
        if len(found) == 1:
            out[given] = found[0]
    return out


@hq_tool(action=ActionClass.VAULT_WRITE)
async def file_shortlist(ctx: RunContext[HQDeps], picks: list[Pick], title: str = "") -> str:
    """File this week's job shortlist from the ledger rows you picked.

    Each pick is a row's `job_id` (from `list_jobs`), an `action` (apply,
    referral, verify_pay or shortlist) and the one `next_step` he takes. Code
    writes projects/jobs/shortlist-<ISO week>.md from the ledger: company,
    role, score, pay, status and the last live check come from the row, the
    date from code. "apply" is accepted only when the row's pay is stated by
    the posting and at or above the target; a closed row is refused. A
    refusal names the row: change that pick and call again.
    """
    day = _today()
    path = shortlist_path(day)
    if not memory.in_scope(path, ctx.deps.vault_write_scopes):
        raise ModelRetry(f"refused: agent {ctx.deps.agent} may not write {path}")
    rows = await _rows_for([p["job_id"] for p in picks])
    problems = pick_problems(picks, rows, settings().job_target_ctc_lakh)
    if problems:
        raise ModelRetry("; ".join(problems) + ". Fix the picks named and call file_shortlist again")
    content = memory.stamp_frontmatter(
        render_page(title, picks, rows, day, settings().job_target_ctc_lakh),
        author=ctx.deps.agent, provenance="agent")
    try:
        await memory.write(path, content, actor=ctx.deps.agent)
    except memory.WriteRefused as exc:
        raise ModelRetry(str(exc)) from None
    await emit("shortlist.filed", run_id=ctx.deps.run_id, agent=ctx.deps.agent,
               payload={"path": path, "picks": len(picks),
                        "apply": sum(1 for p in picks if p["action"] == "apply")})
    return f"filed {len(picks)} picks at {path}"
