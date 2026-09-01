"""Executes one agent run inside a DBOS workflow, including the approval loop.

Flow: agent.run -> if DeferredToolRequests, open tickets + notify owner, block on
DBOS.recv('approval') until every ticket is resolved, resume with the verdicts.
The ticket table is the source of truth; the DBOS message is only the wake-up.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import DeferredToolRequests, DeferredToolResults
from pydantic_ai.usage import UsageLimits

from hq import board, llm
from hq.dbos_app import DBOS
from hq.loader import AgentSpec
from hq.obs import emit
from hq.tools.registry import HQDeps

APPROVAL_TOPIC = "approval"
APPROVAL_TIMEOUT_S = 86400  # 24h; recv default of 60s is a trap
MAX_RESUME_ROUNDS = 5       # hard stop against approval/answer loops


@dataclass
class RunOutcome:
    output: str
    outcome: str            # done | blocked | failed
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None = None
    messages_json: bytes | None = None


async def execute(
    agent, spec: AgentSpec, *, prompt: str, deps: HQDeps,
    message_history=None,
) -> RunOutcome:
    usage_limits = UsageLimits(tool_calls_limit=spec.caps.tool_calls)
    total_in = total_out = 0
    result = None
    rounds = 0
    deferred_results: DeferredToolResults | None = None

    while rounds < MAX_RESUME_ROUNDS:
        rounds += 1
        kwargs: dict = {"deps": deps, "usage_limits": usage_limits}
        if result is not None:
            kwargs["message_history"] = result.all_messages()
        elif message_history is not None:
            kwargs["message_history"] = message_history
        if deferred_results is not None:
            kwargs["deferred_tool_results"] = deferred_results
            deferred_results = None
            result = await agent.run(deps=kwargs.pop("deps"), **kwargs)
        else:
            result = await agent.run(prompt if rounds == 1 else None, **kwargs)

        usage = result.usage
        total_in += usage.input_tokens or 0
        total_out += usage.output_tokens or 0

        if not isinstance(result.output, DeferredToolRequests):
            cost = llm.registry().cost_usd(spec.model, total_in, total_out)
            return RunOutcome(
                output=str(result.output), outcome="done",
                input_tokens=total_in, output_tokens=total_out, cost_usd=cost,
                messages_json=result.all_messages_json(),
            )

        verdicts = await _await_approvals(result.output, spec, deps)
        if verdicts is None:
            cost = llm.registry().cost_usd(spec.model, total_in, total_out)
            return RunOutcome(
                output="approval timed out", outcome="blocked",
                input_tokens=total_in, output_tokens=total_out, cost_usd=cost,
                error="approval ticket expired after 24h",
            )
        deferred_results = DeferredToolResults(approvals=verdicts)

    cost = llm.registry().cost_usd(spec.model, total_in, total_out)
    return RunOutcome(
        output="stopped: too many approval rounds", outcome="failed",
        input_tokens=total_in, output_tokens=total_out, cost_usd=cost,
        error=f"exceeded {MAX_RESUME_ROUNDS} resume rounds",
    )


async def _await_approvals(
    requests: DeferredToolRequests, spec: AgentSpec, deps: HQDeps
) -> dict[str, bool] | None:
    """Open one ticket per approval-needing tool call; block until all resolve.
    Returns {tool_call_id: approved} or None on timeout."""
    wf_id = DBOS.workflow_id
    pending: dict[str, str] = {}  # ticket_id -> tool_call_id
    for call in requests.approvals:
        ticket_id = await board.create_ticket(
            task_id=deps.task_id, run_id=deps.run_id, wf_id=wf_id,
            tool_name=call.tool_name, tool_args=call.args_as_dict(),
            tool_call_id=call.tool_call_id, action_class="external_write",
        )
        pending[ticket_id] = call.tool_call_id
        await board.queue_outbound(
            {
                "kind": "confirm", "ticket_id": ticket_id,
                "summary": f"{spec.name} wants to run {call.tool_name}",
                "args": call.args_as_dict(),
            },
            idempotency_key=f"ticket:{ticket_id}",
        )
    if deps.task_id:
        await board.apply(deps.task_id, "approval_requested", status="needs_approval",
                          data={"tickets": list(pending)})

    verdicts: dict[str, bool] = {}
    while pending:
        msg = await DBOS.recv_async(APPROVAL_TOPIC, timeout_seconds=APPROVAL_TIMEOUT_S)
        if msg is None:  # timeout
            for ticket_id in list(pending):
                await board.resolve_ticket(ticket_id, "expired", via="timeout")
            return None
        # message format: "<ticket_id>:<approved|denied>"
        ticket_id, _, verdict = str(msg).partition(":")
        call_id = pending.pop(ticket_id, None)
        if call_id is not None:
            verdicts[call_id] = verdict == "approved"
            await emit("approval_resolved", task_id=deps.task_id, run_id=deps.run_id,
                       payload={"ticket_id": ticket_id, "approved": verdict == "approved"})
    if deps.task_id:
        await board.apply(deps.task_id, "approval_resolved", status="running")
    return verdicts
