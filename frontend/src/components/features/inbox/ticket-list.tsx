"use client";

import { Fragment, useMemo } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import type { Ticket, Verdict } from "@/lib/api/types";
import { ticketDetails, ticketHeadline } from "@/lib/tickets";
import { exactTime, timeAgo } from "@/lib/time";

/** Backend filter for the "Recently resolved" section (comma list). */
const RESOLVED_STATUS = "approved,denied";
const RESOLVED_LIMIT = 10;

function runHref(ticket: Ticket) {
  return ticket.run_id ? `/runs/${encodeURIComponent(ticket.run_id)}` : null;
}

export function TicketList() {
  const queryClient = useQueryClient();
  const tickets = useQuery({
    queryKey: qk.tickets("pending"),
    queryFn: () => api.tickets("pending"),
  });
  const resolved = useQuery({
    queryKey: qk.tickets(RESOLVED_STATUS),
    queryFn: () => api.tickets(RESOLVED_STATUS, RESOLVED_LIMIT),
  });
  // Tickets carry only task_id; join the title client-side. Optional data.
  const tasks = useQuery({ queryKey: qk.tasks(), queryFn: () => api.tasks() });
  const titleByTask = useMemo(
    () => new Map((tasks.data ?? []).map((task) => [task.id, task.title])),
    [tasks.data],
  );

  const resolve = useMutation({
    mutationFn: ({ id, verdict }: { id: string; verdict: Verdict }) =>
      api.resolveTicket(id, verdict),
    onSuccess: (result, variables) => {
      // The same ticket may already have been resolved from Telegram.
      toast(
        result.resolved
          ? `Ticket ${variables.verdict}`
          : (result.reason ?? "Already resolved elsewhere"),
      );
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (tickets.isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading tickets">
        <Skeleton className="h-28 w-full" />
      </div>
    );
  }

  if (tickets.isError) {
    return (
      <ErrorState
        message={tickets.error.message}
        onRetry={() => tickets.refetch()}
        retrying={tickets.isFetching}
      />
    );
  }

  const pendingCount = tickets.data?.length ?? 0;

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-muted-foreground px-1 text-xs font-medium tracking-wide uppercase">
        {pendingCount
          ? `Waiting on you (${pendingCount})`
          : "Waiting on you"}
      </h2>
      {tickets.data?.length ? (
        tickets.data.map((ticket) => (
          <TicketCard
            key={ticket.id}
            ticket={ticket}
            taskTitle={
              ticket.task_id ? titleByTask.get(ticket.task_id) : undefined
            }
            pending={resolve.isPending && resolve.variables?.id === ticket.id}
            onResolve={(verdict) => resolve.mutate({ id: ticket.id, verdict })}
          />
        ))
      ) : (
        <EmptyState title="You are all caught up">
          Nothing needs your decision right now. When an agent is about to do
          something outward, it stops and lands here for your call.
        </EmptyState>
      )}

      <ResolvedSection
        tickets={resolved.data}
        isLoading={resolved.isLoading}
        error={resolved.isError ? resolved.error.message : null}
        titleByTask={titleByTask}
      />
    </div>
  );
}

function TicketCard({
  ticket,
  taskTitle,
  pending,
  onResolve,
}: {
  ticket: Ticket;
  taskTitle?: string;
  pending: boolean;
  onResolve: (verdict: Verdict) => void;
}) {
  const href = runHref(ticket);
  return (
    <Card className="border-status-approval/40">
      <CardHeader className="pb-3">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {ticket.agent ? <Badge>{ticket.agent}</Badge> : null}
          {ticket.tool_name}
          <span className="text-muted-foreground text-xs font-normal">
            {ticket.action_class}
          </span>
        </CardTitle>
        {taskTitle ? (
          <p className="text-muted-foreground truncate text-sm">
            Task: {taskTitle}
          </p>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* The same reading the chat thread and the board card give this
            ticket: the one value the decision turns on, then the rest as
            key: value lines. Raw JSON stays one click away for the case the
            headline misses. Three surfaces, one rendering. */}
        <TicketArgs args={ticket.tool_args} />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            disabled={pending}
            aria-label={`Approve ${ticket.tool_name}`}
            onClick={() => onResolve("approved")}
          >
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={pending}
            aria-label={`Reject ${ticket.tool_name}`}
            onClick={() => onResolve("denied")}
          >
            Reject
          </Button>
          {href ? (
            <Button size="sm" variant="ghost" asChild>
              <Link href={href}>View run</Link>
            </Button>
          ) : null}
          <span
            className="text-muted-foreground self-center text-xs"
            title={exactTime(ticket.created_at)}
          >
            requested {timeAgo(ticket.created_at)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function TicketArgs({ args }: { args: Record<string, unknown> | null | undefined }) {
  const headline = ticketHeadline(args);
  const details = ticketDetails(args);
  if (!headline && !details.length) return null;
  return (
    <div className="flex flex-col gap-2">
      {headline ? (
        <p className="border-border max-h-40 overflow-auto border-l-2 pl-3 text-sm break-words whitespace-pre-wrap">
          {headline}
        </p>
      ) : null}
      {details.length ? (
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
          {details.map((row) => (
            <Fragment key={row.key}>
              <dt className="text-muted-foreground font-mono">{row.key}</dt>
              <dd className="truncate" title={row.value}>
                {row.value}
              </dd>
            </Fragment>
          ))}
        </dl>
      ) : null}
      <details className="text-xs">
        <summary className="text-muted-foreground cursor-pointer">raw arguments</summary>
        <pre className="bg-muted mt-2 max-h-48 overflow-auto rounded-md p-3">
          {JSON.stringify(args, null, 2)}
        </pre>
      </details>
    </div>
  );
}

/** The last approved or denied tickets, with verdict and how it was decided. */
function ResolvedSection({
  tickets,
  isLoading,
  error,
  titleByTask,
}: {
  tickets: Ticket[] | undefined;
  isLoading: boolean;
  error: string | null;
  titleByTask: Map<string, string>;
}) {
  return (
    <section aria-label="Recently resolved" className="mt-3">
      <h2 className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
        Recently resolved
      </h2>
      {isLoading ? (
        <div role="status" aria-busy="true" aria-label="Loading resolved tickets">
          <Skeleton className="h-20 w-full" />
        </div>
      ) : error ? (
        <p role="alert" className="text-muted-foreground text-sm">
          Resolved tickets unavailable: {error}
        </p>
      ) : !tickets?.length ? (
        <p className="text-muted-foreground text-sm">No decisions yet.</p>
      ) : (
        <ul className="divide-border divide-y rounded-lg border">
          {tickets.map((ticket) => {
            const href = runHref(ticket);
            const title = ticket.task_id
              ? titleByTask.get(ticket.task_id)
              : undefined;
            return (
              <li
                key={ticket.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm"
              >
                <Badge
                  variant="secondary"
                  tone={ticket.status === "approved" ? "success" : "danger"}
                >
                  {ticket.status}
                </Badge>
                {ticket.agent ? (
                  <Badge variant="outline" className="font-normal">
                    {ticket.agent}
                  </Badge>
                ) : null}
                <span className="font-medium">{ticket.tool_name}</span>
                {title ? (
                  <span className="text-muted-foreground min-w-0 flex-1 truncate">
                    {title}
                  </span>
                ) : null}
                <span className="text-muted-foreground ml-auto text-xs">
                  via {ticket.resolved_via ?? "unknown"}
                  {ticket.resolved_at ? ` · ${timeAgo(ticket.resolved_at)}` : ""}
                </span>
                {href ? (
                  <Link
                    href={href}
                    className="hover:text-foreground text-muted-foreground text-xs underline underline-offset-4"
                  >
                    view run
                  </Link>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
