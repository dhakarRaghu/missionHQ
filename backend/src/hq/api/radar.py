"""The Radar page: what was collected, the ideas that wait, the project.

One read gives the page everything, so the page asks once. Every action he
takes here is his own and is recorded as one: choosing an idea, declining
one with his reason, ending a project, adding a problem he met.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hq import db, engagement, radar_ideas, radar_problems
from hq.api.deps import require_auth

router = APIRouter(prefix="/radar", dependencies=[Depends(require_auth)])

PROBLEMS_SHOWN = 30
IDEA_COLUMNS = ("d.id, d.problem_id, d.brief, d.title, d.question, d.build, d.measure,"
                " d.baseline, d.workload, d.rig, d.learn, d.hard_because, d.first_step,"
                " d.scores, d.score, d.status, d.reason, d.created_at")


class Decline(BaseModel):
    reason: str = Field(default="", max_length=500)


class Finish(BaseModel):
    status: Literal["built", "shared", "stopped"]
    result: str = Field(default="", max_length=2000)
    surprise: str = Field(default="", max_length=2000)
    share_url: str = Field(default="", max_length=500)
    problems: list[Annotated[str, Field(max_length=600)]] = Field(
        default_factory=list, max_length=8)


class OwnProblem(BaseModel):
    statement: str = Field(min_length=10, max_length=600)
    area: str = Field(default="", max_length=40)


async def _collection() -> dict[str, Any]:
    kinds = await db.fetch(
        "SELECT kind, count(*) AS items, count(DISTINCT domain) AS sites,"
        " count(*) FILTER (WHERE extracted_at IS NULL) AS unread"
        " FROM hq.radar_items GROUP BY kind ORDER BY items DESC")
    totals = await db.fetchone(
        "SELECT count(*) AS items, count(DISTINCT domain) AS sites, max(fetched_at) AS newest,"
        " count(*) FILTER (WHERE verdict = 'problem') AS problems,"
        " count(*) FILTER (WHERE verdict = 'none') AS none,"
        " count(*) FILTER (WHERE verdict = 'refused') AS refused,"
        " count(*) FILTER (WHERE extracted_at IS NULL) AS unread FROM hq.radar_items")
    return {"kinds": kinds, **(totals or {})}


PROBLEM_SQL = ("SELECT p.id, p.statement, p.area, p.origin, p.status, p.last_seen,"
               " count(e.id) AS evidence, count(DISTINCT e.domain) AS domains,"
               f" {radar_ideas.STRONG_SQL} AS strong FROM hq.problems p"
               " LEFT JOIN hq.problem_evidence e ON e.problem_id = p.id"
               " LEFT JOIN hq.radar_items i ON i.id = e.item_id")


async def _problems() -> dict[str, Any]:
    """The open problems, the ones an idea can be written for first, and how
    many there are of each, because the list is cut and the counts are not."""
    r = radar_ideas.rules()
    rows = await db.fetch(
        f"SELECT q.*, (q.origin = 'owner' OR q.domains >= %s OR q.strong) AS enough"
        f" FROM ({PROBLEM_SQL} WHERE p.status = 'open' GROUP BY p.id) q"
        " ORDER BY (q.origin = 'owner') DESC, q.domains DESC, q.strong DESC, q.evidence DESC,"
        " q.last_seen DESC", (r.min_domains, *radar_ideas.strong_params(r)))
    return {"open": len(rows), "enough": sum(1 for row in rows if row["enough"]),
            "shown": rows[:PROBLEMS_SHOWN]}


async def _with_problem(idea: dict[str, Any]) -> dict[str, Any]:
    r = radar_ideas.rules()
    problem = await db.fetchone(f"{PROBLEM_SQL} WHERE p.id = %s GROUP BY p.id",
                                (*radar_ideas.strong_params(r), idea["problem_id"]))
    return {**idea, "problem": problem,
            "evidence": await radar_ideas.evidence_of(idea["problem_id"])}


async def _ideas() -> dict[str, Any]:
    """The newest brief: its proposals in full, and what the gate dropped
    with the reason, so he can see the gate work."""
    day = await radar_ideas.last_brief()
    if day is None:
        return {"brief": None, "written": 0, "proposed": [], "dropped": [], "ranked_out": [], "declined": []}
    # Every idea of the newest brief, whatever became of it.
    rows = await db.fetch(
        f"SELECT {IDEA_COLUMNS} FROM hq.ideas d WHERE d.brief = %s"
        " ORDER BY d.score DESC, d.id", (day,))
    waiting = await db.fetch(
        f"SELECT {IDEA_COLUMNS} FROM hq.ideas d WHERE d.status = 'proposed' AND d.brief < %s"
        " ORDER BY d.score DESC, d.id", (day,))
    proposed = [r for r in [*rows, *waiting] if r["status"] == "proposed"]
    return {
        "brief": day.isoformat(),
        "written": len(rows),
        "proposed": [await _with_problem(r) for r in proposed],
        "dropped": [{k: r[k] for k in ("id", "title", "question", "reason", "score")}
                    for r in rows if r["status"] == "dropped"
                    and not r["reason"].startswith(radar_ideas.RANKED_OUT)],
        "ranked_out": [{k: r[k] for k in ("id", "title", "question", "reason", "score")}
                       for r in rows if r["status"] == "dropped"
                       and r["reason"].startswith(radar_ideas.RANKED_OUT)],
        "declined": [{k: r[k] for k in ("id", "title", "question", "reason", "score")}
                     for r in rows if r["status"] == "declined"],
    }


async def _projects() -> dict[str, Any]:
    # The idea's columns keep their names; the project's own are prefixed.
    rows = await db.fetch(
        "SELECT p.id AS project_id, p.status AS project_status, p.started_at, p.due_at,"
        f" p.finished_at, p.result, p.surprise, p.share_url, {IDEA_COLUMNS}"
        " FROM hq.projects p JOIN hq.ideas d ON d.id = p.idea_id"
        " ORDER BY p.started_at DESC LIMIT 30")
    running = next((r for r in rows if r["project_status"] == "building"), None)
    if running:
        running = await _with_problem(running)
    return {"running": running, "past": [r for r in rows if r["project_status"] != "building"]}


@router.get("", operation_id="getRadar")
async def get_radar() -> dict[str, Any]:
    collection, problems, ideas, projects = await asyncio.gather(
        _collection(), _problems(), _ideas(), _projects())
    r = radar_ideas.rules()
    return {
        "collection": collection, "problems": problems, "ideas": ideas, "projects": projects,
        "rules": {"every_days": r.every_days, "ideas": r.ideas, "min_domains": r.min_domains,
                  "strong": {"comments": r.strong_comments, "reactions": r.strong_reactions,
                             "points": r.strong_points},
                  "project_days": r.project_days, "needs_you_min": r.needs_you_min,
                  "needs_you": list(r.needs_you), "one_session": list(r.one_session),
                  "rig": dict(r.rig)},
    }


@router.get("/problems/{problem_id}", operation_id="getRadarProblem")
async def get_problem(problem_id: int) -> dict[str, Any]:
    problem = await db.fetchone(
        "SELECT id, statement, area, origin, status, created_at, last_seen"
        " FROM hq.problems WHERE id = %s", (problem_id,))
    if problem is None:
        raise HTTPException(404, "there is no such problem")
    return {**problem, "evidence": await radar_ideas.evidence_of(problem_id, 20)}


async def _done() -> dict[str, Any]:
    await engagement.record_owner_action("web", "radar")
    return await get_radar()


@router.post("/ideas/{idea_id}/choose", operation_id="chooseRadarIdea")
async def choose_idea(idea_id: int) -> dict[str, Any]:
    try:
        await radar_ideas.choose(idea_id)
    except radar_ideas.Refused as exc:
        raise HTTPException(409, str(exc)) from exc
    return await _done()


@router.post("/ideas/{idea_id}/decline", operation_id="declineRadarIdea")
async def decline_idea(idea_id: int, body: Decline) -> dict[str, Any]:
    try:
        await radar_ideas.decline(idea_id, body.reason)
    except radar_ideas.Refused as exc:
        raise HTTPException(409, str(exc)) from exc
    return await _done()


@router.post("/projects/{project_id}/finish", operation_id="finishRadarProject")
async def finish_project(project_id: int, body: Finish) -> dict[str, Any]:
    try:
        await radar_ideas.finish(project_id, status=body.status, result=body.result,
                                 surprise=body.surprise, share_url=body.share_url,
                                 problems=body.problems)
    except (radar_ideas.Refused, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return await _done()


@router.post("/problems", operation_id="addRadarProblem")
async def add_problem(body: OwnProblem) -> dict[str, Any]:
    try:
        await radar_problems.add_own(body.statement, body.area)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return await _done()


@router.post("/problems/{problem_id}/dismiss", operation_id="dismissRadarProblem")
async def dismiss_problem(problem_id: int) -> dict[str, Any]:
    try:
        await radar_ideas.dismiss(problem_id)
    except radar_ideas.Refused as exc:
        raise HTTPException(409, str(exc)) from exc
    return await _done()
