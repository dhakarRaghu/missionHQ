"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

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
 */
export function InFlight({ sessionId }: { sessionId: string }) {
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
        <li key={task.id}>
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
        </li>
      ))}
    </ul>
  );
}
