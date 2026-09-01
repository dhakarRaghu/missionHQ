"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { EmptyState } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import type { Ticket } from "@/lib/api/types";

export function TicketList() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: qk.tickets("pending"),
    queryFn: () => api.tickets("pending"),
  });

  const resolve = useMutation({
    mutationFn: ({ id, verdict }: { id: string; verdict: "approved" | "denied" }) =>
      api.resolveTicket(id, verdict),
    onSuccess: (result, variables) => {
      // The same ticket may already have been resolved from Telegram.
      toast(
        result.resolved
          ? `Ticket ${variables.verdict}`
          : "Already resolved elsewhere",
      );
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (isLoading) {
    return <Skeleton className="h-28 w-full" />;
  }

  if (!data?.length) {
    return <EmptyState>Nothing is waiting on you. Agents run unattended until they need a decision.</EmptyState>;
  }

  return (
    <div className="flex flex-col gap-3">
      {data.map((ticket) => (
        <TicketCard
          key={ticket.id}
          ticket={ticket}
          pending={resolve.isPending}
          onResolve={(verdict) => resolve.mutate({ id: ticket.id, verdict })}
        />
      ))}
    </div>
  );
}

function TicketCard({
  ticket,
  pending,
  onResolve,
}: {
  ticket: Ticket;
  pending: boolean;
  onResolve: (verdict: "approved" | "denied") => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {ticket.tool_name}
          <span className="text-muted-foreground ml-2 text-xs font-normal">
            {ticket.action_class}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <pre className="bg-muted max-h-48 overflow-auto rounded-md p-3 text-xs">
          {JSON.stringify(ticket.tool_args, null, 2)}
        </pre>
        <div className="flex gap-2">
          <Button size="sm" disabled={pending} onClick={() => onResolve("approved")}>
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={() => onResolve("denied")}
          >
            Reject
          </Button>
          <span className="text-muted-foreground self-center text-xs">
            requested {new Date(ticket.created_at).toLocaleString()}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
