"use client";

import { useMemo } from "react";

import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import type {
  LedgerPayload,
  RunDetail,
  RunEvent,
  Ticket,
  ToolCalledPayload,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Tone = NonNullable<React.ComponentProps<typeof Badge>["tone"]>;

/** One row of the vertical timeline. Events and tickets are merged by time. */
interface Step {
  key: string;
  ts: string;
  /** Sort key: event id, or the id of the event a ticket precedes. */
  order: number;
  /** Second sort key (epoch ms): orders tickets that no event follows. */
  tsMs: number;
  tone: Tone;
  title: string;
  badge?: { label: string; tone: Tone };
  body?: React.ReactNode;
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function usd(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? `$${n.toFixed(4)}` : "—";
}

function ms(value: number) {
  return value < 1000 ? `${value}ms` : `${(value / 1000).toFixed(1)}s`;
}

function ArgList({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args);
  if (!entries.length) {
    return <p className="text-muted-foreground text-xs">no arguments</p>;
  }
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
      {entries.map(([name, value]) => (
        <div key={name} className="contents">
          <dt className="text-muted-foreground font-mono">{name}</dt>
          <dd className="max-h-40 overflow-y-auto font-mono break-all whitespace-pre-wrap">
            {typeof value === "string" ? value : JSON.stringify(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const TICKET_TONE: Record<Ticket["status"], Tone> = {
  pending: "approval",
  approved: "success",
  denied: "danger",
  expired: "muted",
};

function ticketStep(ticket: Ticket, order: number): Step {
  return {
    key: `ticket-${ticket.id}`,
    ts: ticket.created_at,
    order,
    tsMs: Date.parse(ticket.created_at) || 0,
    tone: "approval",
    title: `Approval requested: ${ticket.tool_name}`,
    badge: { label: ticket.status, tone: TICKET_TONE[ticket.status] },
    body: (
      <>
        <ArgList args={ticket.tool_args} />
        {ticket.resolved_at ? (
          <p className="text-muted-foreground mt-1 text-xs">
            resolved via {ticket.resolved_via ?? "unknown"} at{" "}
            {new Date(ticket.resolved_at).toLocaleString()}
          </p>
        ) : null}
      </>
    ),
  };
}

function eventStep(event: RunEvent, tickets: Map<string, Ticket>): Step {
  const base = {
    key: `event-${event.id}`,
    ts: event.ts,
    order: event.id,
    tsMs: Date.parse(event.ts) || 0,
  };
  const p = event.payload;

  switch (event.kind) {
    case "run.started":
      return { ...base, tone: "running", title: "Run started" };

    case "tool.called": {
      const call = p as unknown as ToolCalledPayload;
      const args = call.args && typeof call.args === "object" ? call.args : {};
      return {
        ...base,
        tone: call.ok ? "muted" : "danger",
        title: `Tool: ${call.tool}`,
        badge: call.ok
          ? { label: ms(Number(call.duration_ms) || 0), tone: "muted" }
          : { label: "error", tone: "danger" },
        body: (
          <>
            <ArgList args={args} />
            {call.error ? (
              <p className="text-status-danger mt-1 text-xs break-words">
                {call.error}
              </p>
            ) : null}
            {typeof call.result === "string" && call.result ? (
              <details className="mt-1 text-xs">
                <summary className="text-muted-foreground cursor-pointer select-none">
                  show result
                </summary>
                <pre className="bg-muted mt-1 max-h-48 overflow-auto rounded p-2 font-mono break-all whitespace-pre-wrap">
                  {call.result}
                </pre>
              </details>
            ) : null}
          </>
        ),
      };
    }

    case "ledger": {
      const v = p as unknown as LedgerPayload;
      const verdict = v.satisfied
        ? { label: "satisfied", tone: "success" as Tone }
        : v.looping
          ? { label: "looping", tone: "danger" as Tone }
          : v.progress
            ? { label: "progress", tone: "running" as Tone }
            : { label: "stalled", tone: "blocked" as Tone };
      return {
        ...base,
        tone: verdict.tone,
        title: "Ledger verdict",
        badge: verdict,
        body: (
          <>
            <p className="text-sm">{str(v.reason)}</p>
            {v.next_instruction ? (
              <p className="text-muted-foreground mt-1 text-xs">
                Next: {v.next_instruction}
              </p>
            ) : null}
            {Number(v.stall) > 0 ? (
              <p className="text-muted-foreground mt-1 text-xs">
                stalled rounds: {Number(v.stall)}
              </p>
            ) : null}
          </>
        ),
      };
    }

    case "approval_resolved": {
      const ticketId = str(p.ticket_id);
      const status = str(p.status, "resolved") as Ticket["status"];
      const ticket = tickets.get(ticketId);
      return {
        ...base,
        tone: TICKET_TONE[status] ?? "muted",
        title: `Approval ${status}${ticket ? `: ${ticket.tool_name}` : ""}`,
        badge: { label: status, tone: TICKET_TONE[status] ?? "muted" },
        body: ticket ? undefined : (
          <p className="text-muted-foreground font-mono text-xs">{ticketId}</p>
        ),
      };
    }

    case "guardrail.denied":
      return {
        ...base,
        tone: "danger",
        title: `Guardrail denied: ${str(p.tool, "tool call")}`,
        badge: { label: str(p.via, "guardrail"), tone: "danger" },
        body: <p className="text-sm">{str(p.reason)}</p>,
      };

    case "run.finished": {
      const outcome = str(p.outcome, "done");
      const tone: Tone =
        outcome === "done" ? "success" : outcome === "blocked" ? "blocked" : "danger";
      return {
        ...base,
        tone,
        title: "Run finished",
        badge: { label: outcome, tone },
        body: (
          <p className="text-muted-foreground text-xs tabular-nums">
            cost {usd(p.cost_usd)}
          </p>
        ),
      };
    }

    case "run.failed":
      return {
        ...base,
        tone: "danger",
        title: "Run failed",
        badge: { label: "failed", tone: "danger" },
        body: (
          <p className="text-status-danger text-xs break-words">
            {str(p.error, "unknown error")}
          </p>
        ),
      };

    default:
      return {
        ...base,
        tone: "muted",
        title: event.kind,
        body: Object.keys(p).length ? (
          <pre className="text-muted-foreground max-h-40 overflow-auto font-mono text-xs whitespace-pre-wrap">
            {JSON.stringify(p, null, 2)}
          </pre>
        ) : undefined,
      };
  }
}

/** Merges hq.events rows and the run's tickets into one ordered list. */
export function buildSteps(events: RunEvent[], tickets: Ticket[]): Step[] {
  const byId = new Map(tickets.map((t) => [t.id, t]));
  const steps = events.map((event) => eventStep(event, byId));
  for (const ticket of tickets) {
    // Place the ticket right before the first event logged after it. Tickets
    // with no later event share the sentinel and fall back to created_at.
    const next = events.find((e) => e.ts >= ticket.created_at);
    steps.push(ticketStep(ticket, next ? next.id - 0.5 : Number.MAX_SAFE_INTEGER));
  }
  return steps.sort((a, b) => a.order - b.order || a.tsMs - b.tsMs);
}

/** "+12.4s" from the start of the run, or "" when it cannot be computed. */
function offset(ts: string, startedAt: string): string {
  const delta = Date.parse(ts) - Date.parse(startedAt);
  if (!Number.isFinite(delta) || delta < 0) return "";
  return delta < 1000 ? `+${delta}ms` : `+${(delta / 1000).toFixed(1)}s`;
}

export function RunTimeline({ detail }: { detail: RunDetail }) {
  const steps = useMemo(
    () => buildSteps(detail.events, detail.tickets),
    [detail.events, detail.tickets],
  );
  const startedAt = detail.run.started_at;

  if (!steps.length) {
    return <EmptyState>No steps recorded for this run yet.</EmptyState>;
  }

  return (
    <ol className="border-border relative ml-2 border-l pl-6" aria-label="Run steps">
      {steps.map((step) => (
        <li key={step.key} className="relative pb-6 last:pb-0">
          <span
            aria-hidden="true"
            className={cn(
              "bg-background absolute top-1.5 -left-[calc(1.5rem+5px)] size-2.5 rounded-full border-2",
              {
                running: "border-status-running",
                blocked: "border-status-blocked",
                approval: "border-status-approval",
                success: "border-status-success",
                danger: "border-status-danger",
                muted: "border-status-muted",
              }[step.tone],
            )}
          />
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium">{step.title}</p>
            {step.badge ? (
              <Badge variant="secondary" tone={step.badge.tone}>
                {step.badge.label}
              </Badge>
            ) : null}
            <time
              dateTime={step.ts}
              title={new Date(step.ts).toLocaleString()}
              className="text-muted-foreground ml-auto text-xs tabular-nums"
            >
              {offset(step.ts, startedAt) || new Date(step.ts).toLocaleTimeString()}
            </time>
          </div>
          {step.body ? <div className="mt-1.5">{step.body}</div> : null}
        </li>
      ))}
    </ol>
  );
}
