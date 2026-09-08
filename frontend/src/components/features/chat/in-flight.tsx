"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, qk } from "@/lib/api/client";
import { timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

const LABEL: Record<string, string> = {
  backlog: "queued",
  running: "working",
  needs_approval: "waiting on you",
  blocked: "blocked",
};

/**
 * Work this chat handed to another agent, still in flight.
 *
 * Delegation is asynchronous: between "I have asked scout" and the result
 * arriving there is nothing on screen, so a slow run and a lost one look the
 * same and the owner asks again. This is the strip that tells them apart.
 * It empties itself, because a finished task posts its result as a message.
 *
 * Each row can also be stopped. A run takes minutes, and without this the only
 * way out of one you did not want is to wait for it to finish.
 */
export function InFlight({ sessionId }: { sessionId: string }) {
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelTask(id),
    onSuccess: (result) => {
      toast(
        result.cancelled ? "Stopped" : (result.reason ?? "Already finished"),
      );
      queryClient.invalidateQueries({ queryKey: qk.chatTasks(sessionId) });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const tasks = useQuery({
    queryKey: qk.chatTasks(sessionId),
    queryFn: () => api.chatTasks(sessionId),
    // Cheap, and the answer changes without an event of its own.
    refetchInterval: 15_000,
  });

  const rows = tasks.data ?? [];
  if (!rows.length) return null;

  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map((task) => (
        <li key={task.id} className="flex items-center gap-1.5">
          <Link
            href={`/board?task=${encodeURIComponent(task.id)}`}
            className="bg-muted/40 hover:bg-muted flex items-center gap-2 rounded-lg px-3 py-2 text-xs transition-colors"
          >
            <span
              aria-hidden
              className={cn(
                "size-1.5 shrink-0 rounded-full",
                task.status === "running" &&
                  "bg-status-running motion-safe:animate-pulse",
                task.status === "needs_approval" && "bg-status-approval",
                task.status === "blocked" && "bg-status-blocked",
                task.status === "backlog" && "bg-status-muted",
              )}
            />
            <span className="font-medium">{task.agent}</span>
            <span className="text-muted-foreground">
              {LABEL[task.status] ?? task.status}
            </span>
            <span className="text-muted-foreground min-w-0 flex-1 truncate">
              {task.title}
            </span>
            <span className="text-muted-foreground shrink-0 whitespace-nowrap">
              {timeAgo(task.updated_at)}
            </span>
          </Link>
          <Button
            size="sm"
            variant="ghost"
            className="text-muted-foreground hover:text-foreground h-7 shrink-0 px-2 text-xs"
            aria-label={`Stop ${task.agent}: ${task.title}`}
            disabled={cancel.isPending && cancel.variables === task.id}
            onClick={() => cancel.mutate(task.id)}
          >
            Stop
          </Button>
        </li>
      ))}
    </ul>
  );
}
