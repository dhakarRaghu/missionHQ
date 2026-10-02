"""Small operator commands: ``uv run python -m hq.cli <command>``.

    health   one score for whether the machine is working, and the trend
    models   list what the gateway serves and check models.yaml against it
    ask      run one agent once from the terminal (no Telegram, no board)

    evals export <agent> [--limit N]   build/merge evals/<agent>.yaml from finished runs
    evals run <agent> [--live] [--all] score the golden set (stored refs; --live re-runs)
    evals history <agent>              recent eval scores for the agent
    reindex                            rebuild the vault full-text index
    radar collect [--dry-run] [--only KIND]  read the radar's sources once and store what is new
    radar status                       what the radar has collected, by kind
    radar read [--limit N]             name the problem in each unread item (model calls)
    radar problems                     the open problems, most sites first
    radar brief [--force]              propose project ideas when the brief is due (model calls)
    sync-courses                       pull published course phases from the study platform (run after /study publishes)
    import-course <topic>              copy a platform course written elsewhere into learning/study-material/ (owner's deliberate step)
    board-check                        replay task_events and report tasks whose stored status differs (exit 1 if any)
    prompt-check <agent|all>           zero-tool judge audits an agent's instruction corpus (exit 1 on a high contradiction)
    vault-health [--merge-plan]        dry-run vault maintenance report: duplicates, orphans, unsourced, stale, future-dated
    export-reader                      write the phone reader bundle into frontend/public/reader
    publish-reader                     what the nightly does: build the bundle and commit+push it to the `reader` branch (only when it changed)
    value-week                         the weekly value report: lessons written vs read, taps, jobs moved, ideas, spend
    operator-answer <task> <file> [via]  attach an answer read by hand in a signed-in browser to a waiting operator task and queue it
"""

from __future__ import annotations

import asyncio
import sys

import hq.dbos_app  # noqa: F401 — construct DBOS before decorated imports
from hq import llm


async def cmd_radar(what: str, flags: list[str]) -> int:
    """`radar collect [--dry-run] [--only github|hn|arxiv|feed]` reads every
    source once; `radar status` says what the table holds."""
    from hq import db, radar

    if what == "status":
        await db.open_pool()
        try:
            rows = await db.fetch(
                "SELECT kind, count(*) n, count(DISTINCT domain) sites,"
                " count(*) FILTER (WHERE extracted_at IS NULL) unread,"
                " max(fetched_at) newest FROM hq.radar_items GROUP BY kind ORDER BY n DESC")
        finally:
            await db.close_pool()
        for r in rows:
            print(f"  {r['kind']:<9} {r['n']:>5} items  {r['sites']:>3} sites"
                  f"  {r['unread']:>5} unread  newest {r['newest']:%Y-%m-%d %H:%M}")
        print(f"{sum(r['n'] for r in rows)} items" if rows else "nothing collected yet")
        return 0
    if what in {"read", "problems", "brief"}:
        from hq import radar_ideas, radar_problems

        await db.open_pool()
        try:
            if what == "read":
                limit = (int(flags[flags.index("--limit") + 1]) if "--limit" in flags[:-1]
                         else radar_problems.RUN_ITEMS)
                print(radar_problems.summary(await radar_problems.read_new(limit)))
                grouped = await radar_problems.group_near()
                print(f"radar: {grouped.asked} near pairs judged, {grouped.merged} merged,"
                      f" {grouped.different} different, {grouped.failed} failed")
            elif what == "brief":
                print(await radar_ideas.brief_and_report(force="--force" in flags))
            else:
                rows = await db.fetch(
                    "SELECT p.id, p.statement, p.origin, count(e.id) n,"
                    " count(DISTINCT e.domain) sites FROM hq.problems p"
                    " LEFT JOIN hq.problem_evidence e ON e.problem_id = p.id"
                    " WHERE p.status = 'open' GROUP BY p.id"
                    " ORDER BY sites DESC, n DESC, p.id LIMIT 40")
                for r in rows:
                    print(f"  {r['id']:>5}  {r['sites']:>2} sites  {r['n']:>2} quotes"
                          f"  {r['origin']:<5}  {r['statement'][:110]}")
                print(f"{len(rows)} shown" if rows else "no open problem yet")
        finally:
            await db.close_pool()
        return 0
    if what != "collect":
        print(__doc__)
        return 2
    dry = "--dry-run" in flags
    only = flags[flags.index("--only") + 1] if "--only" in flags[:-1] else ""
    if not dry:
        await db.open_pool()
    try:
        tallies = await radar.collect(dry_run=dry, only=only)
    finally:
        if not dry:
            await db.close_pool()
    for t in sorted(tallies, key=lambda t: (bool(t.error), -t.kept, t.source)):
        line = f"  {t.source:<44} found {t.found:>4}  kept {t.kept:>4}  new {t.new:>4}"
        print(line + (f"  ! {t.error}" if t.error else ""))
    print(radar.summary(tallies) + ("  (dry run: nothing stored)" if dry else ""))
    return 0


async def cmd_models() -> int:
    served = await llm.gateway_models()
    print(f"gateway serves {len(served)} models:\n")
    for m in sorted(served, key=lambda x: x["id"]):
        ctx = f"{m['context']:,}" if m["context"] else "?"
        print(f"  {m['id']:<32} context {ctx}")

    reg = llm.registry()
    print("\nmodels.yaml:")
    for name, entry in reg.entries.items():
        role = next((r for r, target in reg.roles.items() if target == name), "")
        mark = "" if entry.model_id in {m["id"] for m in served} else "  <-- NOT SERVED"
        print(f"  {name:<14} -> {entry.model_id:<26}{f'({role})' if role else '':<10}{mark}")

    missing = await llm.verify_against_gateway()
    return 1 if missing else 0


async def cmd_ask(agent_name: str, prompt: str) -> int:
    """One agent, one prompt, straight to stdout. The fastest way to see whether
    an agent's instructions actually produce something worth reading."""
    from pydantic_ai.durable_exec.dbos import DBOSDurability

    from hq import db, loader, runner
    from hq.tools.registry import HQDeps

    await db.open_pool()
    try:
        specs = loader.scan()
        if agent_name not in specs:
            print(f"unknown agent {agent_name!r}; have: {sorted(specs)}", file=sys.stderr)
            return 2
        spec = specs[agent_name]
        deps = HQDeps(agent=agent_name, vault_write_scopes=spec.vault_write_scopes())
        if spec.runtime in loader.EXTERNAL_RUNTIMES:
            # An agent on an external runtime is a different program. Running
            # it through the in-process loop used to silently work, on the
            # house model, with none of its tools, and it answered from its
            # notebook as if it had really tried. The answer looked plausible
            # and was worthless, which is worse than a failure.
            #
            # No approval gate here: the board's gate exists because cron and
            # Telegram start runs the owner is not watching. He typed this one.
            outcome = await runner.execute_external(spec, prompt=prompt, deps=deps)
        else:
            agent = loader.build_agent(
                spec, DBOSDurability(models=llm.registry().all_instances()))
            outcome = await runner.execute(agent, spec, prompt=prompt, deps=deps)
        print(outcome.output)
        print(
            f"\n[{outcome.outcome}] {outcome.input_tokens} in / {outcome.output_tokens} out"
            f" = ${outcome.cost_usd:.6f} on "
            + (spec.runtime if spec.runtime in loader.EXTERNAL_RUNTIMES
               else llm.registry().canonical(spec.model)),
            file=sys.stderr,
        )
        return 0 if outcome.outcome == "done" else 1
    finally:
        await db.close_pool()


async def cmd_evals(sub: str, agent_name: str, flags: list[str]) -> int:
    """``evals export|run|history <agent>``. Compact tables on stdout."""
    from hq import db, evals

    await db.open_pool()
    try:
        if sub == "export":
            limit = int(flags[flags.index("--limit") + 1]) if "--limit" in flags else 40
            counts = await evals.export_cases(agent_name, limit=limit)
            print(
                f"{evals.dataset_file(agent_name)}: {counts['total']} cases"
                f" ({counts['added']} added, {counts['existing']} kept,"
                f" {counts['skipped']} skipped for empty output)"
            )
            return 0
        if sub == "run":
            row = await evals.run_eval(
                agent_name, live="--live" in flags, all_cases="--all" in flags,
            )
            print(f"{'case':<38} {'pass':<5} {'judge':<6} failed checks / reason")
            for d in row["details"]:
                failed = [k for k, v in d["checks"].items() if not v]
                print(
                    f"{d['id'][:36]:<38} {'ok' if d['passed'] else 'FAIL':<5}"
                    f" {d['judge_score'] or '-'!s:<6} {', '.join(failed) or d['judge_reason'][:60]}"
                )
            print(
                f"\n[eval #{row['id']}] {agent_name} {row['dataset']}: {row['passed']}/{row['cases']}"
                f" score {float(row['score']):.3f}, cost ${float(row['cost_usd']):.6f}"
            )
            return 0 if row["passed"] == row["cases"] else 1
        if sub == "history":
            rows = await evals.history(agent_name)
            print(f"{'ts':<20} {'dataset':<22} {'job':<10} {'passed':<8} {'score':<6} cost_usd")
            for r in rows:
                print(
                    f"{r['ts']:%Y-%m-%d %H:%M:%S}  {r['dataset'][:22]:<22} {r['job_hash'][:10]:<10}"
                    f" {f'{r['passed']}/{r['cases']}':<8} {float(r['score']):<6.3f} {float(r['cost_usd']):.6f}"
                )
            if not rows:
                print("(no eval runs yet)")
            return 0
        print(__doc__, file=sys.stderr)
        return 2
    finally:
        await db.close_pool()


async def cmd_reindex() -> int:
    from hq import db, memory

    await db.open_pool()
    try:
        n = await memory.reindex_all()
        print(f"indexed {n} chunks")
        return 0
    finally:
        await db.close_pool()


async def cmd_sync_courses() -> int:
    """After /study publishes a phase: pull it in so it replaces its plan row."""
    import inspect
    from types import SimpleNamespace

    from hq import db
    from hq.tools import learning_tools

    await db.open_pool()
    try:
        # The tool body, without the agent machinery around it.
        sync = inspect.unwrap(learning_tools.sync_courses)
        deps = SimpleNamespace(run_id=None, task_id=None, agent="owner")
        print(await sync(SimpleNamespace(deps=deps)))
        return 0
    finally:
        await db.close_pool()


async def cmd_import_course(topic: str) -> int:
    """Copy one course from the study platform into the repo, as its source.

    Tutor builds enhanced pages from the repo copy, never from the platform,
    because the platform accepts writes without authentication. Importing is
    therefore a step the owner takes on purpose, for a course he knows is his.
    """
    import json

    import httpx

    from hq.config import settings

    base = settings().study_api_base.rstrip("/")
    async with httpx.AsyncClient(timeout=60) as client:
        items = (await client.get(f"{base}/api/study")).json()
    folder = settings().learning_dir / "study-material" / topic
    folder.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in items if isinstance(items, list) else []:
        slug = str(item.get("slug") or "")
        if slug.startswith(f"{topic}-phase-") and isinstance(item.get("content"), str):
            (folder / f"{slug}.md").write_text(item["content"])
            count += 1
    (folder / "course.json").write_text(json.dumps(
        {"topic": topic, "importedFrom": base, "phases": count}, indent=2))
    print(f"imported {count} phases of {topic} into {folder}")
    return 0 if count else 1


async def cmd_export_reader() -> int:
    """Write the phone reader bundle, for him to commit and push.

    The console needs this machine: its backend, its Postgres, its files. The
    bundle needs none of them, which is the whole point of it.
    """
    from hq import db, reader_export

    await db.open_pool()
    try:
        made = await reader_export.build()
        print(f"{made['phases']} phase(s) across {made['courses']} course(s)"
              f" and {made['articles']} article(s)")
        print(f"{made['pages']} page(s), {made['bytes'] / 1_000_000:.1f} MB -> {made['dir']}")
        print("commit frontend/public/reader and push; Vercel serves it at /read")
        return 0
    finally:
        await db.close_pool()


async def cmd_publish_reader() -> int:
    """The nightly publish, by hand: bundle to the `reader` branch, pushed."""
    from hq import db, reader_export

    await db.open_pool()
    try:
        result = await reader_export.publish_nightly()
        if result.get("error"):
            print(f"not published: {result['error']}")
            return 1
        if result.get("committed"):
            print(f"committed {result['committed'][:12]} on {result['branch']}")
        else:
            print(f"no change in the library; {result['branch']} left as it was")
        print("pushed" if result.get("pushed") else "nothing to push")
        return 0
    finally:
        await db.close_pool()


async def cmd_value_week() -> int:
    from hq import db, value

    await db.open_pool()
    try:
        print(value.format_report(await value.week_report()))
        return 0
    finally:
        await db.close_pool()


async def cmd_operator_answer(task_ref: str, path: str, via: str) -> int:
    """Attach a browser answer read by hand to one waiting operator task and
    put it back in the queue. The task's own run then files it exactly as a
    runtime's output: the same checks, the same hand-offs to hunter."""
    import json
    from pathlib import Path

    from hq import board, db

    text = Path(path).read_text().strip()
    if not text:
        print("operator-answer: the answer file is empty", file=sys.stderr)
        return 2
    await db.open_pool()
    try:
        rows = await db.fetch(
            "SELECT id::text, status, title FROM hq.tasks WHERE agent = 'operator'"
            " AND id::text LIKE %s", (task_ref.strip() + "%",))
        if len(rows) != 1:
            print(f"operator-answer: {len(rows)} operator tasks match {task_ref!r}", file=sys.stderr)
            return 2
        task = rows[0]
        if task["status"] not in {"blocked", "backlog"}:
            print(f"operator-answer: the task is {task['status']}; only a blocked or queued"
                  " task takes an answer", file=sys.stderr)
            return 2
        await db.execute(
            "UPDATE hq.tasks SET payload = coalesce(payload, '{}'::jsonb) || %s::jsonb"
            " WHERE id = %s",
            (json.dumps({"browser_answer": text, "answered_via": via}), task["id"]))
        if task["status"] == "blocked":
            await board.apply(task["id"], "answered_by_hand", actor="owner", status="backlog",
                              data={"via": via, "chars": len(text)})
        print(f"operator-answer: {task['title'][:70]} ({task['id'][:8]}) queued with"
              f" {len(text)} characters read via {via}")
        return 0
    finally:
        await db.close_pool()


async def cmd_board_check() -> int:
    """Event-sourcing audit: derive every task's status from hq.task_events and
    compare with the hq.tasks projection. Read-only."""
    from hq import board, db

    await db.open_pool()
    try:
        mismatches = await board.verify_projections()
        if not mismatches:
            print("board-check: all task projections match their event logs")
            return 0
        print(f"{'task_id':<38} {'stored':<16} derived")
        for m in mismatches:
            print(f"{m['task_id']:<38} {m['stored']:<16} {m['derived']}")
        print(f"\nboard-check: {len(mismatches)} mismatch(es)", file=sys.stderr)
        return 1
    finally:
        await db.close_pool()


async def cmd_prompt_check(target: str) -> int:
    """Audit one agent's instruction corpus (or every agent) with a separate
    zero-tool judge. Read-only; costs one cheap-model call per agent."""
    from hq import promptcheck

    names = sorted(promptcheck.agent_dirs()) if target == "all" else [target]
    if target != "all" and target not in promptcheck.agent_dirs():
        print(f"unknown agent {target!r}; have: {sorted(promptcheck.agent_dirs())}", file=sys.stderr)
        return 2
    failed = 0
    total_cost = 0.0
    for name in names:
        result = await promptcheck.check_agent(name)
        print(promptcheck.format_result(result))
        print()
        total_cost += result["cost_usd"]
        if promptcheck.has_high(result):
            failed += 1
    print(
        f"prompt-check: {len(names)} agent(s), {failed} with high-severity contradictions,"
        f" ${total_cost:.6f}",
        file=sys.stderr,
    )
    return 1 if failed else 0


async def cmd_vault_health(flags: list[str]) -> int:
    """Dry-run maintenance report over the vault and its index. Never writes."""
    from hq import db, vault_health

    await db.open_pool()
    try:
        rep = await vault_health.report()
        notes = vault_health.read_notes() if "--merge-plan" in flags else None
        print(vault_health.format_report(
            rep, with_merge_plan="--merge-plan" in flags, notes=notes,
        ))
        return 0
    finally:
        await db.close_pool()


async def cmd_health() -> int:
    """One score for whether the machine is working, and the trend since last run.

    Seven commands already report pieces of this, and none of them answered
    "is Mission HQ healthy". A 74% run-success rate stayed invisible for a week
    because nothing added the pieces up. Every input here is already recorded
    and no model is called, so this is free to run as often as you like.
    """
    import json
    import subprocess
    from datetime import UTC, datetime

    from hq import db, vault_health
    from hq.config import BACKEND_DIR, REPO_DIR

    await db.open_pool()
    try:

        def grade(value: float, clean: float, warn: float, poor: float) -> int:
            """10 / 7 / 4 / 0 for a metric where higher is better."""
            for threshold, score in ((clean, 10), (warn, 7), (poor, 4)):
                if value >= threshold:
                    return score
            return 0

        def passes(cmd: list[str], cwd) -> bool:
            try:
                done = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=240, check=False)
                return done.returncode == 0
            except (OSError, subprocess.SubprocessError):
                return False

        rows: list[tuple[str, float, int, str]] = []

        runs = await db.fetch(
            "SELECT count(*) FILTER (WHERE outcome = 'done') AS done, count(*) AS total"
            " FROM hq.runs WHERE started_at > now() - interval '7 days'"
            # Neither a run the owner stopped on purpose, nor one closed by
            # the watchdog because its process went away, is a failed run.
            "   AND coalesce(outcome, '') NOT IN ('cancelled', 'abandoned')"
        )
        done, total = runs[0]["done"] or 0, runs[0]["total"] or 0
        pct = (done / total * 100) if total else 100.0
        rows.append(("runs (7d)", 0.30, grade(pct, 95, 85, 75), f"{done}/{total} done = {pct:.0f}%"))

        rep = await vault_health.report()
        found = sum(int(v) for k, v in rep["counts"].items() if k != "memory_blocks_over_80pct")
        rows.append(("vault", 0.25, grade(-found, -5, -20, -50), f"{found} finding(s)"))

        blocked = await db.fetch(
            "SELECT count(*) AS n FROM hq.tasks WHERE status IN ('blocked', 'needs_approval')"
        )
        waiting = blocked[0]["n"]
        rows.append(("waiting on you", 0.15, grade(-waiting, 0, -3, -8), f"{waiting} task(s) stuck"))

        rows.append(("types", 0.10, 10 if passes(["npx", "tsc", "--noEmit"], REPO_DIR / "frontend") else 0, "tsc"))
        rows.append(("lint", 0.10, 10 if passes([".venv/bin/ruff", "check", "src/hq/"], BACKEND_DIR) else 0, "ruff"))

        drift = await db.fetch(
            "SELECT count(*) AS n FROM hq.runs WHERE outcome = 'no_artifact'"
            " AND started_at > now() - interval '7 days'"
        )
        rows.append(("artifacts", 0.10, 10 if drift[0]["n"] == 0 else 4,
                     f"{drift[0]['n']} run(s) claimed done with nothing written"))

        composite = sum(weight * score for _, weight, score, _ in rows)

        # Not scored: it is a budget, not a fault. But it belongs on the one
        # screen you check, because the free tier stops dead and a quiet month
        # looks exactly like a working one until you need a search.
        from hq.tools.brightdata import usage as bd_usage

        credits = await bd_usage()

        prev = await db.fetch("SELECT value FROM hq.control WHERE key = 'health_last'")
        trend = ""
        if prev:
            # psycopg gives jsonb back as a dict, not a string. Passing it to
            # json.loads raised on every run after the first, which the first
            # run could not show because there was nothing to compare against.
            stored = prev[0]["value"]
            if isinstance(stored, (str, bytes, bytearray)):
                stored = json.loads(stored)
            before = float(stored["score"])
            delta = composite - before
            way = "up" if delta > 0.05 else ("down" if delta < -0.05 else "level")
            trend = f"  ({way} from {before:.1f})"

        print(f"\nMission HQ health: {composite:.1f}/10{trend}\n")
        for label, weight, score, detail in rows:
            bar = "#" * score + "." * (10 - score)
            print(f"  {label:<15} {bar}  {score:>2}/10  {int(weight * 100):>2}%   {detail}")
        weakest = min(rows, key=lambda r: r[2])
        if weakest[2] < 10:
            print(f"\n  weakest: {weakest[0]} — {weakest[3]}")
        print(
            f"\n  search credits   {credits['today']}/{credits['day_cap']} today,"
            f" {credits['month']}/{credits['month_cap']} this month"
        )
        print()

        await db.execute(
            "INSERT INTO hq.control (key, value) VALUES ('health_last', %s::jsonb)"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (json.dumps({"score": round(composite, 2), "at": datetime.now(UTC).isoformat()}),),
        )
        return 0 if composite >= 7 else 1
    finally:
        await db.close_pool()


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__)
        raise SystemExit(0)
    if args[0] == "reindex":
        raise SystemExit(asyncio.run(cmd_reindex()))
    if args[0] == "health":
        raise SystemExit(asyncio.run(cmd_health()))
    if args[0] == "import-course" and len(args) == 2:
        raise SystemExit(asyncio.run(cmd_import_course(args[1])))
    if args[0] == "sync-courses":
        raise SystemExit(asyncio.run(cmd_sync_courses()))
    if args[0] == "export-reader":
        raise SystemExit(asyncio.run(cmd_export_reader()))
    if args[0] == "publish-reader":
        raise SystemExit(asyncio.run(cmd_publish_reader()))
    if args[0] == "value-week":
        raise SystemExit(asyncio.run(cmd_value_week()))
    if args[0] == "operator-answer" and len(args) in {3, 4}:
        via = args[3] if len(args) == 4 else "a Claude session's browser"
        raise SystemExit(asyncio.run(cmd_operator_answer(args[1], args[2], via)))
    if args[0] == "board-check":
        raise SystemExit(asyncio.run(cmd_board_check()))
    if args[0] == "prompt-check" and len(args) == 2:
        raise SystemExit(asyncio.run(cmd_prompt_check(args[1])))
    if args[0] == "vault-health":
        raise SystemExit(asyncio.run(cmd_vault_health(args[1:])))
    if args[0] == "radar" and len(args) >= 2:
        raise SystemExit(asyncio.run(cmd_radar(args[1], args[2:])))
    if args[0] == "models":
        raise SystemExit(asyncio.run(cmd_models()))
    if args[0] == "ask" and len(args) >= 3:
        raise SystemExit(asyncio.run(cmd_ask(args[1], " ".join(args[2:]))))
    if args[0] == "regress" and len(args) >= 2:
        from hq import regress

        raise SystemExit(regress.main(args[1:]))
    if args[0] == "evals" and len(args) >= 3:
        raise SystemExit(asyncio.run(cmd_evals(args[1], args[2], args[3:])))
    print(__doc__)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
