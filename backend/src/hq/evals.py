"""Lightweight agent-eval harness. The run log is the dataset.

Flow:
1. ``export_cases`` turns finished runs (hq.runs + hq.tasks + the run_* task
   event) into a golden set at ``evals/<agent>.yaml``. The owner curates that
   file by deleting bad cases; ids are run ids, so re-export never duplicates.
2. ``run_eval`` scores every case. Deterministic checks run first (named
   booleans); one cheap LLM judge grades 1-5. A case passes only when ALL
   checks pass. Score = passed / cases. One hq.eval_runs row per eval.
3. ``history`` / ``latest_scores`` read the rows back for the CLI and REST.

Built on pydantic-evals ``Dataset`` / ``Case`` / ``Evaluator``. The judge is a
custom ``Evaluator`` on a Pydantic AI agent (role ``cheap``, zero tools)
rather than the stock ``LLMJudge``: the stock one has no fixed 1-5 rubric and
does not expose token usage, and we need both for the score and the cost row.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from hq import db, llm
from hq.config import BACKEND_DIR

log = logging.getLogger(__name__)

EVALS_DIR = BACKEND_DIR / "evals"
JUDGE_MODEL = "cheap"           # registry role for the judge
JUDGE_PASS_SCORE = 3            # rubric 1-5; >= this passes
LIVE_CASE_CAP = 10              # live re-runs are expensive; --all lifts this
MAX_OUTPUT_CHARS = 4000
JUDGE_PROMPT_CHARS = 3000       # prompt/output slice shown to the judge

SECRET_RE = re.compile(r"sk-[A-Za-z0-9]{8,}")
HTML_TAG_RE = re.compile(
    r"</?(html|head|body|div|span|p|a|br|hr|script|style|table|thead|tbody|tr|td|th|"
    r"ul|ol|li|h[1-6]|img|b|i|u|strong|em|pre|code|form|input|button|iframe)\b[^>]*>",
    re.IGNORECASE,
)
MD_PATH_RE = re.compile(r"[\w./\\-]+\.md\b")


# --- dataset --------------------------------------------------------------------

class EvalCase(BaseModel):
    """One golden case as stored in evals/<agent>.yaml."""
    id: str
    prompt: str
    reference: str = ""
    tags: list[str] = []


class EvalInput(BaseModel):
    """What the task callable receives per case."""
    id: str
    prompt: str


class JudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    reason: str


def dataset_file(agent: str) -> Path:
    return EVALS_DIR / f"{agent}.yaml"


def load_cases(path: Path) -> list[EvalCase]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or []
    if not isinstance(raw, list):
        raise TypeError(f"{path}: expected a top-level list of cases")
    return [EvalCase.model_validate(item) for item in raw]


def save_cases(path: Path, cases: list[EvalCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [c.model_dump() for c in cases]
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))


async def export_cases(agent: str, limit: int = 40) -> dict[str, int]:
    """Build/merge the golden set for ``agent`` from finished runs.

    Reference = the ``output`` field of the latest ``run_*`` task event for the
    task (the engine stores the first 500 chars there). Runs whose task has no
    such event are skipped. Returns counts: existing, added, total, skipped.
    """
    rows = await db.fetch(
        "SELECT r.id::text AS id, t.title, t.brief, t.source, r.started_at,"
        " (SELECT e.data->>'output' FROM hq.task_events e"
        "   WHERE e.task_id = t.id AND e.event_type IN ('run_done', 'run_blocked', 'run_failed')"
        "   ORDER BY e.seq DESC LIMIT 1) AS reference"
        " FROM hq.runs r JOIN hq.tasks t ON t.id = r.task_id"
        " WHERE r.agent = %s AND r.outcome = 'done'"
        " ORDER BY r.started_at DESC LIMIT %s",
        (agent, limit),
    )
    path = dataset_file(agent)
    existing = load_cases(path)
    known = {c.id for c in existing}
    added: list[EvalCase] = []
    skipped = 0
    for row in rows:
        if row["id"] in known:
            continue
        reference = (row["reference"] or "").strip()
        if not reference:
            skipped += 1
            continue
        prompt = row["title"] + ("\n\n" + row["brief"] if row["brief"] else "")
        added.append(EvalCase(
            id=row["id"], prompt=prompt, reference=reference,
            tags=[f"source:{row['source']}"],
        ))
    added.reverse()  # oldest first, so the file reads chronologically
    if added or not path.exists():
        save_cases(path, existing + added)
    return {
        "existing": len(existing), "added": len(added),
        "total": len(existing) + len(added), "skipped": skipped,
    }


# --- checks ----------------------------------------------------------------------

def deterministic_checks(output: str, tags: list[str]) -> dict[str, bool]:
    """Named boolean checks. Cheap, exact, and they outnumber the judge."""
    text = output or ""
    checks = {
        "non_empty": bool(text.strip()),
        "under_4000_chars": len(text) <= MAX_OUTPUT_CHARS,
        "no_leaked_secrets": SECRET_RE.search(text) is None,
        "no_html_tags": HTML_TAG_RE.search(text) is None,
    }
    if "vault-write" in tags:
        checks["vault_write_mentions_md_path"] = MD_PATH_RE.search(text) is not None
    return checks


@dataclass
class DeterministicChecks(Evaluator[EvalInput, str, dict[str, Any]]):
    def evaluate(self, ctx: EvaluatorContext[EvalInput, str, dict[str, Any]]) -> dict[str, bool]:
        tags = list((ctx.metadata or {}).get("tags", []))
        return deterministic_checks(ctx.output, tags)


JUDGE_INSTRUCTIONS = """\
You grade one answer written by an autonomous agent. You never act; you judge.
You receive the request the agent got and the answer it produced.

Rubric, score 1-5:
- faithful to prompt: the answer does what the request asked, nothing else.
- concrete: specific facts, names, paths, numbers; no vague promises.
- no filler: no preamble, no restating the request, no padding.

5 = all three fully met. 3 = mostly met with small lapses. 1 = off-topic,
empty, or mostly filler. Return the score and one plain sentence of reason.
"""

_judge_agent: Agent[None, JudgeVerdict] | None = None


def judge_agent() -> Agent[None, JudgeVerdict]:
    """Zero-tool judge on the cheap model. Built once, lazily."""
    global _judge_agent
    if _judge_agent is None:
        _judge_agent = Agent[None, JudgeVerdict](
            llm.registry().resolve(JUDGE_MODEL),
            name="hq-eval-judge",
            output_type=JudgeVerdict,
            instructions=JUDGE_INSTRUCTIONS,
        )
    return _judge_agent


@dataclass
class TokenTally:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class RubricJudge(Evaluator[EvalInput, str, dict[str, Any]]):
    """LLM judge: 1-5 on "faithful to prompt, concrete, no filler"; pass >= 3.
    Token usage is tallied so the eval row can carry a real cost."""
    tally: TokenTally = field(default_factory=TokenTally, repr=False)

    async def evaluate(
        self, ctx: EvaluatorContext[EvalInput, str, dict[str, Any]]
    ) -> dict[str, bool | int | str]:
        text = (
            f"Request:\n{ctx.inputs.prompt[:JUDGE_PROMPT_CHARS]}\n\n"
            f"Answer:\n{(ctx.output or '')[:JUDGE_PROMPT_CHARS]}"
        )
        try:
            res = await judge_agent().run(text)
        except Exception as exc:  # noqa: BLE001 — a judge outage fails the case, not the eval
            log.warning("judge failed for case %s: %s", ctx.name, exc)
            return {"judge": False, "judge_score": 0, "judge_reason": f"judge error: {str(exc)[:200]}"}
        self.tally.input_tokens += res.usage.input_tokens or 0
        self.tally.output_tokens += res.usage.output_tokens or 0
        verdict = res.output
        return {
            "judge": verdict.score >= JUDGE_PASS_SCORE,
            "judge_score": verdict.score,
            "judge_reason": verdict.reason[:300],
        }


# --- running -----------------------------------------------------------------------

@dataclass
class EvalResult:
    agent: str
    dataset: str
    job_hash: str
    cases: int
    passed: int
    score: float
    details: list[dict[str, Any]]
    cost_usd: float


async def _live_task_factory(agent_name: str):
    """Build the real agent once and return a task callable that re-runs a
    prompt through it. Costs of these runs are added to the eval row."""
    from pydantic_ai.durable_exec.dbos import DBOSDurability

    from hq import loader, runner
    from hq.tools.registry import HQDeps

    specs = loader.scan()
    if agent_name not in specs:
        raise KeyError(f"unknown agent {agent_name!r}; have: {sorted(specs)}")
    spec = specs[agent_name]
    agent = loader.build_agent(spec, DBOSDurability(models=llm.registry().all_instances()))
    tally = TokenTally()
    spent: list[float] = [0.0]

    async def task(inputs: EvalInput) -> str:
        deps = HQDeps(agent=agent_name, vault_write_scopes=spec.vault_write_scopes())
        outcome = await runner.execute(agent, spec, prompt=inputs.prompt, deps=deps)
        tally.input_tokens += outcome.input_tokens
        tally.output_tokens += outcome.output_tokens
        spent[0] += outcome.cost_usd
        if outcome.outcome != "done":
            return f"[{outcome.outcome}] {outcome.output}"
        return outcome.output

    return task, spec.job_hash, spent


async def evaluate_cases(
    agent: str, cases: list[EvalCase], *, dataset: str, live: bool = False,
    job_hash: str = "",
) -> EvalResult:
    """Score ``cases``. Stored mode judges the reference text; live mode
    re-runs each prompt through the real agent first."""
    references = {c.id: c.reference for c in cases}
    live_spent: list[float] = [0.0]
    if live:
        task, job_hash, live_spent = await _live_task_factory(agent)
    else:
        async def task(inputs: EvalInput) -> str:
            return references[inputs.id]

    judge = RubricJudge()
    ds = Dataset[EvalInput, str, dict[str, Any]](
        name=f"{agent}:{dataset}",
        cases=[
            Case(
                name=c.id, inputs=EvalInput(id=c.id, prompt=c.prompt),
                expected_output=c.reference, metadata={"tags": c.tags},
            )
            for c in cases
        ],
        evaluators=[DeterministicChecks(), judge],
    )
    report = await ds.evaluate(task, max_concurrency=1 if live else 4, progress=False)

    details: list[dict[str, Any]] = []
    passed = 0
    for rc in report.cases:
        checks = {name: bool(r.value) for name, r in rc.assertions.items()}
        if rc.evaluator_failures:  # an evaluator raised: the case cannot pass
            checks["evaluator_error"] = False
        ok = bool(checks) and all(checks.values())
        passed += ok
        details.append({
            "id": rc.name,
            "passed": ok,
            "checks": checks,
            "judge_score": int(rc.scores["judge_score"].value) if "judge_score" in rc.scores else None,
            "judge_reason": str(rc.labels["judge_reason"].value) if "judge_reason" in rc.labels else "",
            "output_chars": len(rc.output or ""),
            "output_head": (rc.output or "")[:200],
        })
    for fc in report.failures:  # the task itself raised (live mode only)
        details.append({
            "id": fc.name, "passed": False, "checks": {"task_ran": False},
            "judge_score": None, "judge_reason": f"task error: {fc.error_message[:200]}",
            "output_chars": 0, "output_head": "",
        })

    total = len(details)
    judge_cost = llm.registry().cost_usd(JUDGE_MODEL, judge.tally.input_tokens, judge.tally.output_tokens)
    return EvalResult(
        agent=agent, dataset=dataset, job_hash=job_hash, cases=total, passed=passed,
        score=round(passed / total, 3) if total else 0.0,
        details=details, cost_usd=round(judge_cost + live_spent[0], 6),
    )


async def run_eval(
    agent: str, dataset_path: Path | str | None = None, *, live: bool = False,
    all_cases: bool = False,
) -> dict[str, Any]:
    """Score one agent against its golden set and record one hq.eval_runs row.

    Default: judge the STORED reference outputs (cheap; tests the judge and the
    deterministic checks over history). ``live=True`` re-runs each prompt
    through the real agent and judges the new output; capped at
    ``LIVE_CASE_CAP`` cases unless ``all_cases``. Returns the inserted row.
    """
    path = Path(dataset_path) if dataset_path else dataset_file(agent)
    cases = load_cases(path)
    if not cases:
        raise ValueError(f"no cases in {path}; run `evals export {agent}` first")
    if live and not all_cases and len(cases) > LIVE_CASE_CAP:
        cases = cases[-LIVE_CASE_CAP:]  # newest cases, the file is chronological

    job_hash = ""
    if not live:
        from hq import loader

        try:
            spec = loader.scan().get(agent)
            job_hash = spec.job_hash if spec else ""
        except Exception as exc:  # noqa: BLE001 — a bad agents dir must not block a stored eval
            log.warning("could not read agent specs for job_hash: %s", exc)

    result = await evaluate_cases(
        agent, cases, dataset=f"{path.name}{':live' if live else ''}", live=live,
        job_hash=job_hash,
    )
    row = await db.fetchone(
        "INSERT INTO hq.eval_runs (agent, dataset, job_hash, cases, passed, score, details, cost_usd)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        " RETURNING id, ts, agent, dataset, job_hash, cases, passed, score, details, cost_usd",
        (result.agent, result.dataset, result.job_hash, result.cases, result.passed,
         result.score, db.jsonb(result.details), result.cost_usd),
    )
    assert row is not None
    return row


# --- reading back ------------------------------------------------------------------

async def history(agent: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Recent eval_runs rows, newest first. ``agent=None`` returns all agents."""
    cols = "id, ts, agent, dataset, job_hash, cases, passed, score, details, cost_usd"
    if agent:
        return await db.fetch(
            f"SELECT {cols} FROM hq.eval_runs WHERE agent = %s ORDER BY ts DESC LIMIT %s",
            (agent, limit),
        )
    return await db.fetch(f"SELECT {cols} FROM hq.eval_runs ORDER BY ts DESC LIMIT %s", (limit,))


async def latest_scores() -> list[dict[str, Any]]:
    """One row per agent: its most recent eval."""
    return await db.fetch(
        "SELECT DISTINCT ON (agent) agent, score, cases, passed, ts, dataset, job_hash, cost_usd"
        " FROM hq.eval_runs ORDER BY agent, ts DESC"
    )
