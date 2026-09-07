"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, qk } from "@/lib/api/client";
import type { Verdict } from "@/lib/api/types";
import { exactTime, timeAgo } from "@/lib/time";
import { ticketHeadline } from "@/lib/tickets";

/**
 * An approval, answerable where it was raised.
 *
 * The Inbox and Telegram both show it too, but the run that raised it started
 * in this chat, so leaving the thread to answer and coming back is the long
 * way round. Resolving is the same call from all three places, and a second
 * answer anywhere is a visible no-op.
 */
export function ChatApprovals({ sessionId }: { sessionId: string }) {
  const queryClient = useQueryClient();
  const tickets = useQuery({
    queryKey: qk.chatTickets(sessionId),
    queryFn: () => api.chatTickets(sessionId),
  });

  const resolve = useMutation({
    mutationFn: ({ id, verdict }: { id: string; verdict: Verdict }) =>
      api.resolveTicket(id, verdict),
    onSuccess: (result, variables) => {
      toast(
        result.resolved
          ? `Ticket ${variables.verdict}`
          : (result.reason ?? "Already resolved elsewhere"),
      );
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: qk.chatTickets(sessionId) });
      queryClient.invalidateQueries({ queryKey: qk.chatMessages(sessionId) });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const rows = tickets.data ?? [];
  if (!rows.length) return null;

  return (
    <div className="flex flex-col gap-3">
      {rows.map((ticket) => {
        const text = ticketHeadline(ticket.tool_args);
        const pending =
          resolve.isPending && resolve.variables?.id === ticket.id;
        return (
          <div
            key={ticket.id}
            className="border-status-approval/50 bg-card rounded-2xl border-2 px-4 py-3"
          >
            <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
              {ticket.agent ? <Badge>{ticket.agent}</Badge> : null}
              wants to run {ticket.tool_name}
              <span
                className="text-muted-foreground ml-auto text-xs"
                title={exactTime(ticket.created_at)}
              >
                {timeAgo(ticket.created_at)}
              </span>
            </p>

            {text ? (
              <p className="text-muted-foreground border-border mt-2 border-l-2 pl-3 text-sm break-words whitespace-pre-wrap">
                {text.length > 700 ? `${text.slice(0, 700)}…` : text}
              </p>
            ) : null}

            <p className="text-muted-foreground mt-2 text-xs">
              The run is paused until you answer. Answering here, in Inbox, or
              on Telegram does the same thing.
            </p>

            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={pending}
                onClick={() =>
                  resolve.mutate({ id: ticket.id, verdict: "approved" })
                }
              >
                Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={pending}
                onClick={() =>
                  resolve.mutate({ id: ticket.id, verdict: "denied" })
                }
              >
                Reject
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
