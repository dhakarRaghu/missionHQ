"use client";

import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { useFeed, useSseStatus } from "@/hooks/use-hq-events";
import type { HqEvent, HqEventType } from "@/lib/api/types";
import { restartSse } from "@/lib/sse";
import { clockTime, exactTime } from "@/lib/time";

type Payload = Record<string, unknown>;

function text(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function short(value: unknown, max = 80): string {
  const s = text(value).replace(/\s+/g, " ").trim();
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function usd(value: unknown): string {
  const n = Number(value);
  return Number.isFinite(n) ? `$${n.toFixed(4)}` : "";
}

function ms(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return n < 1000 ? `${n}ms` : `${(n / 1000).toFixed(1)}s`;
}

/** " · "-joined, skipping empty parts. */
function join(...parts: (string | null | undefined | false)[]): string {
  return parts.filter(Boolean).join(" · ");
}

function ledgerVerdict(p: Payload): string {
  if (p.satisfied) return "satisfied";
  if (p.looping) return "looping";
  if (p.progress) return "progress";
  return "stalled";
}

/** One-line label per event kind. Payload keys follow the backend emitters. */
const LABELS: Record<HqEventType, (p: Payload, e: HqEvent) => string> = {
  "task.created": (p) => short(p.title, 120),
  "task.updated": (p) => join(text(p.event), text(p.status)),
  "run.started": (_p, e) => join(e.agent, "run started"),
  "run.finished": (p, e) =>
    join(e.agent, text(p.exit_status, text(p.outcome)), usd(p.cost_usd)),
  "run.failed": (p, e) => join(e.agent, "failed", short(p.error, 100)),
  "run.no_artifact": (p, e) =>
    join(e.agent, "no artifact", short(p.reason, 100)),
  "tool.called": (p, e) =>
    join(
      e.agent,
      text(p.tool),
      ms(p.duration_ms),
      p.ok === false ? join("error", short(p.error, 60)) : "ok",
    ),
  ledger: (p) => join(ledgerVerdict(p), short(p.reason, 100)),
  "ticket.created": (p) => join("approval requested", text(p.tool)),
  "ticket.resolved": (p) =>
    join(text(p.verdict), p.via ? `via ${text(p.via)}` : null),
  approval_resolved: (p) =>
    join(text(p.status, "resolved"), `ticket ${short(p.ticket_id, 8)}`),
  "guardrail.denied": (p) => join(text(p.tool), short(p.reason, 100)),
  notify: (p) => short(p.text, 120),
  notify_digested: (p) => join("held for digest", short(p.text, 100)),
  digest: (p) =>
    join(
      `digest ${text(p.date)}`.trim(),
      p.chars !== undefined ? `${text(p.chars)} chars` : null,
    ),
  "cron.caught_up": (p) => join("caught up", text(p.slot)),
  "cron.missed": (p) =>
    join(
      "missed",
      text(p.schedule),
      p.task_status ? `task ${text(p.task_status)}` : "no task created",
    ),
  "vault.reindexed": (p) => join(`${text(p.chunks, "0")} chunks`, text(p.via)),
  "fact.recorded": (p) => join(text(p.subject), text(p.provenance)),
  "fact.retired": (p) => join(text(p.subject), short(p.reason, 80)),
  "policy.added": (p) => short(p.rule, 120),
  injection_detected: (p) => join(short(p.url, 60), short(p.text, 80)),
  "owner.action": (p) => join(text(p.action), p.via ? `via ${text(p.via)}` : null),
  announce: (p) => short(p.text, 120),
};

export function feedLabel(event: HqEvent): string {
  const render = LABELS[event.type] as
    | ((p: Payload, e: HqEvent) => string)
    | undefined;
  const label = render ? render(event.payload ?? {}, event) : "";
  return label || event.type;
}

/** Where a row leads: the run when it has one, else the task on the board. */
export function feedHref(event: HqEvent): string | null {
  if (event.run_id) return `/runs/${encodeURIComponent(event.run_id)}`;
  if (event.task_id) return `/board?task=${encodeURIComponent(event.task_id)}`;
  return null;
}

export function LiveFeed() {
  const feed = useFeed();
  const status = useSseStatus();

  if (!feed.length) {
    if (status === "reconnecting") {
      return (
        <ErrorState
          message="The event stream dropped. The browser retries on its own; you can also reconnect now."
          onRetry={restartSse}
        />
      );
    }
    return (
      <EmptyState>
        {status === "connected"
          ? "Connected. Events will appear here as agents work."
          : "Connecting to the event stream…"}
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {status === "reconnecting" ? (
        <ErrorState
          message="The event stream dropped. Showing the last events received."
          onRetry={restartSse}
        />
      ) : null}
      <ol className="divide-border divide-y rounded-lg border">
        {feed.map((event) => {
          const href = feedHref(event);
          const row = <FeedRow event={event} linked={Boolean(href)} />;
          return (
            <li key={event.seq}>
              {href ? (
                <Link
                  href={href}
                  className="hover:bg-muted/50 flex items-start gap-3 px-4 py-3 transition-colors"
                >
                  {row}
                </Link>
              ) : (
                <div className="flex items-start gap-3 px-4 py-3">{row}</div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function FeedRow({ event, linked }: { event: HqEvent; linked: boolean }) {
  return (
    <>
      <Badge variant="outline" className="mt-0.5 shrink-0 font-normal">
        {event.type}
      </Badge>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">{feedLabel(event)}</p>
        <p className="text-muted-foreground text-xs" title={exactTime(event.ts)}>
          {event.agent ? `${event.agent} · ` : ""}
          {clockTime(event.ts)} · seq {event.seq}
          {linked ? (event.run_id ? " · view run" : " · open task") : ""}
        </p>
      </div>
    </>
  );
}
