"""Small operator commands: ``uv run python -m hq.cli <command>``.

    models   list what the gateway serves and check models.yaml against it
    ask      run one agent once from the terminal (no Telegram, no board)
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


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__)
        raise SystemExit(0)
    if args[0] == "models":
        raise SystemExit(asyncio.run(cmd_models()))
    if args[0] == "ask" and len(args) >= 3:
        raise SystemExit(asyncio.run(cmd_ask(args[1], " ".join(args[2:]))))
    print(__doc__)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
