"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import type { Task, TaskStatus } from "@/lib/api/types";

// Grouped list rather than a drag board: task transitions are machine-driven
// through board.apply(), so a draggable card would imply a move the engine
// would ignore.
const GROUPS: TaskStatus[] = [
  "needs_approval",
  "running",
  "blocked",
  "backlog",
  "done",
  "failed",
];

export function TaskBoard() {
  const [openTask, setOpenTask] = useState<Task | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: qk.tasks(),
    queryFn: () => api.tasks(),
  });

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data?.length) return <EmptyState>No tasks yet.</EmptyState>;

  return (
    <>
      <div className="flex flex-col gap-6">
        {GROUPS.map((status) => {
          const tasks = data.filter((task) => task.status === status);
          if (!tasks.length) return null;
          return (
            <section key={status}>
              <div className="mb-2 flex items-center gap-2">
                <StatusBadge status={status} />
                <span className="text-muted-foreground text-xs">
                  {tasks.length}
                </span>
              </div>
              <ul className="divide-border divide-y rounded-lg border">
                {tasks.map((task) => (
                  <li key={task.id}>
                    <button
                      type="button"
                      onClick={() => setOpenTask(task)}
                      className="hover:bg-muted/50 flex w-full items-center justify-between gap-4 px-4 py-3 text-left transition-colors"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm">
                          {task.title}
                        </span>
                        <span className="text-muted-foreground text-xs">
                          {task.agent} · {task.source}
                        </span>
                      </span>
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {new Date(task.updated_at).toLocaleString()}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>

      <TaskDrawer task={openTask} onClose={() => setOpenTask(null)} />
    </>
  );
}

function TaskDrawer({
  task,
  onClose,
}: {
  task: Task | null;
  onClose: () => void;
}) {
  const { data: events } = useQuery({
    queryKey: qk.taskEvents(task?.id ?? ""),
    queryFn: () => api.taskEvents(task!.id),
    enabled: Boolean(task),
  });

  return (
    <Dialog open={Boolean(task)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="pr-6 text-base">{task?.title}</DialogTitle>
        </DialogHeader>
        {task ? (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2 text-sm">
              <StatusBadge status={task.status} />
              <span className="text-muted-foreground">
                {task.agent} · {task.source}
              </span>
            </div>
            {task.brief ? <p className="text-sm">{task.brief}</p> : null}
            <div>
              <p className="mb-2 text-sm font-medium">Event log</p>
              <ol className="border-border max-h-80 space-y-2 overflow-auto border-l pl-4 text-xs">
                {events?.map((event) => (
                  <li key={event.seq}>
                    <span className="font-medium">{event.event_type}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {event.actor} · {new Date(event.ts).toLocaleString()}
                    </span>
                    {Object.keys(event.data).length > 0 ? (
                      <pre className="bg-muted mt-1 overflow-auto rounded p-2">
                        {JSON.stringify(event.data, null, 2)}
                      </pre>
                    ) : null}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
