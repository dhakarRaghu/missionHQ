"""Alternative ways to run one agent turn.

The default runtime is the in-process Pydantic AI loop in ``runner.execute``:
Mission HQ owns every step, so every tool call passes the registry's gates.

A second runtime hands the turn to an external agent CLI instead. That buys
one thing the in-process loop cannot have — a browser the owner is signed into,
through an extension — and costs the per-step control. The trade is made safe
by three rules, enforced in ``codex_cli`` and the runner:

* the external process may only READ (browser tools, nothing else),
* Mission HQ writes the result to the vault itself, through the same gates,
* every such run opens an approval ticket before it starts.
"""
