"""Small operator commands: ``uv run python -m hq.cli <command>``.

    models   list what the gateway serves and check models.yaml against it
    ask      run one agent once from the terminal (no Telegram, no board)

    evals export <agent> [--limit N]   build/merge evals/<agent>.yaml from finished runs
    evals run <agent> [--live] [--all] score the golden set (stored refs; --live re-runs)
    evals history <agent>              recent eval scores for the agent
    reindex                            rebuild the vault full-text index
    board-check                        replay task_events and report tasks whose stored status differs (exit 1 if any)
    prompt-check <agent|all>           zero-tool judge audits an agent's instruction corpus (exit 1 on a high contradiction)
    vault-health [--merge-plan]        dry-run vault maintenance report: duplicates, orphans, unsourced, stale, future-dated
"""

from __future__ import annotations

import asyncio
import sys

import hq.dbos_app  # noqa: F401 — construct DBOS before decorated imports
from hq import llm


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
        agent = loader.build_agent(spec, DBOSDurability(models=llm.registry().all_instances()))
        deps = HQDeps(agent=agent_name, vault_write_scopes=spec.vault_write_scopes())
        outcome = await runner.execute(agent, spec, prompt=prompt, deps=deps)
        print(outcome.output)
        print(
            f"\n[{outcome.outcome}] {outcome.input_tokens} in / {outcome.output_tokens} out"
            f" = ${outcome.cost_usd:.6f} on {llm.registry().canonical(spec.model)}",
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


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__)
        raise SystemExit(0)
    if args[0] == "reindex":
        raise SystemExit(asyncio.run(cmd_reindex()))
    if args[0] == "board-check":
        raise SystemExit(asyncio.run(cmd_board_check()))
    if args[0] == "prompt-check" and len(args) == 2:
        raise SystemExit(asyncio.run(cmd_prompt_check(args[1])))
    if args[0] == "vault-health":
        raise SystemExit(asyncio.run(cmd_vault_health(args[1:])))
    if args[0] == "models":
        raise SystemExit(asyncio.run(cmd_models()))
    if args[0] == "ask" and len(args) >= 3:
        raise SystemExit(asyncio.run(cmd_ask(args[1], " ".join(args[2:]))))
    if args[0] == "evals" and len(args) >= 3:
        raise SystemExit(asyncio.run(cmd_evals(args[1], args[2], args[3:])))
    print(__doc__)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
