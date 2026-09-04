"use client";

import { useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { skipToken, useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Markdown } from "@/components/features/vault/markdown";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import type { Task, TaskEvent, TaskStatus } from "@/lib/api/types";
import { exactTime, timeAgo } from "@/lib/time";

// Read-only columns, not a drag board: every transition is written by
// board.apply() on the backend, so a draggable card would promise a move the
// engine ignores. The four live states are the board; done and failed are
// history and sit underneath it.
const LIVE: TaskStatus[] = ["needs_approval", "running", "blocked", "backlog"];
const FINISHED: TaskStatus[] = ["done", "failed"];
const FINISHED_LIMIT = 12;

/** Local calendar day, so "done today" matches the owner's clock. */
function isToday(iso: string): boolean {
  const then = new Date(iso);
  const now = new Date();
  return (
    then.getFullYear() === now.getFullYear() &&
    then.getMonth() === now.getMonth() &&
    then.getDate() === now.getDate()
  );
}

const COLUMN_HINT: Record<TaskStatus, string> = {
  needs_approval: "Waiting for your decision in Inbox.",
  running: "An agent is working on these now.",
  blocked: "Stopped and waiting. Open one to read why.",
  backlog: "Queued. An agent picks these up in order.",
  done: "Finished with an artifact.",
  failed: "Ended with an error.",
};

export function TaskBoard() {
  // The open task lives in the URL (?task=<id>) so the feed can deep-link to
  // it and the back button closes the drawer. The dialog always shows current
  // data because it looks the id up in the query result.
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const openTaskId = params.get("task");
  const setOpenTaskId = useCallback(
    (id: string | null) => {
      if (id) router.push(`${pathname}?task=${encodeURIComponent(id)}`);
      else router.replace(pathname);
    },
    [router, pathname],
  );

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: qk.tasks(),
    queryFn: () => api.tasks(),
  });

  if (isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Loading tasks"
        className="board-columns"
      >
        {LIVE.map((status) => (
          <Skeleton key={status} className="h-48 w-full" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <ErrorState
        message={error.message}
        onRetry={() => refetch()}
        retrying={isFetching}
      />
    );
  }
  if (!data?.length) {
    return (
      <EmptyState title="No tasks yet">
        Work shows up here across Needs approval, Running, Blocked and Backlog.
        Agents create their own tasks on a schedule; you can add one with New
        task.
      </EmptyState>
    );
  }

  const openTask = data.find((task) => task.id === openTaskId) ?? null;
  const finished = data
    .filter((task) => FINISHED.includes(task.status))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  const needsYou = data.filter((t) => t.status === "needs_approval").length;
  const inFlight = data.filter((t) => t.status === "running").length;
  const doneToday = data.filter(
    (t) => t.status === "done" && isToday(t.updated_at),
  ).length;

  return (
    <>
      <p className="text-muted-foreground mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span>
          <span className="text-foreground font-medium tabular-nums">
            {needsYou}
          </span>{" "}
          need you
        </span>
        <span>
          <span className="text-foreground font-medium tabular-nums">
            {inFlight}
          </span>{" "}
          in flight
        </span>
        <span>
          <span className="text-foreground font-medium tabular-nums">
            {doneToday}
          </span>{" "}
          done today
        </span>
      </p>

      <div className="board-columns">
        {LIVE.map((status) => (
          <Column
            key={status}
            status={status}
            tasks={data.filter((task) => task.status === status)}
            onOpen={setOpenTaskId}
          />
        ))}
      </div>

      <FinishedSection tasks={finished} onOpen={setOpenTaskId} />

      <TaskDrawer
        taskId={openTaskId}
        task={openTask}
        onClose={() => setOpenTaskId(null)}
      />
    </>
  );
}

/** One state of the pipeline, with its cards. */
function Column({
  status,
  tasks,
  onOpen,
}: {
  status: TaskStatus;
  tasks: Task[];
  onOpen: (id: string) => void;
}) {
  return (
    <section aria-label={status} className="flex min-w-0 flex-col gap-2">
      <div>
        <div className="flex items-center gap-2">
          <StatusBadge status={status} />
          <span className="text-muted-foreground text-xs tabular-nums">
            {tasks.length}
          </span>
        </div>
        <p className="text-muted-foreground mt-1 text-xs">
          {COLUMN_HINT[status]}
        </p>
      </div>

      {tasks.length ? (
        <ul className="flex flex-col gap-2">
          {tasks.map((task) => (
            <li key={task.id}>
              <TaskCard task={task} onOpen={() => onOpen(task.id)} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground rounded-lg border border-dashed px-3 py-4 text-center text-xs">
          Nothing here
        </p>
      )}
    </section>
  );
}

function TaskCard({ task, onOpen }: { task: Task; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="bg-card hover:border-ring/60 hover:bg-muted/40 flex w-full flex-col gap-1.5 rounded-lg border px-3 py-2.5 text-left transition-colors"
    >
      <span className="line-clamp-3 text-sm leading-snug">{task.title}</span>
      <span className="text-muted-foreground flex w-full items-center justify-between gap-2 text-xs">
        <span className="truncate">
          {task.agent} · {task.source}
        </span>
        <span className="whitespace-nowrap" title={exactTime(task.updated_at)}>
          {timeAgo(task.updated_at)}
        </span>
      </span>
    </button>
  );
}

/** Done and failed tasks, newest first. History, so a list and not a column. */
function FinishedSection({
  tasks,
  onOpen,
}: {
  tasks: Task[];
  onOpen: (id: string) => void;
}) {
  if (!tasks.length) return null;
  const shown = tasks.slice(0, FINISHED_LIMIT);

  return (
    <section aria-label="Finished" className="mt-8">
      <h2 className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
        Finished
        <span className="ml-2 tabular-nums">
          {shown.length < tasks.length
            ? `${shown.length} of ${tasks.length}`
            : tasks.length}
        </span>
      </h2>
      <ul className="divide-border divide-y rounded-lg border">
        {shown.map((task) => (
          <li key={task.id}>
            <button
              type="button"
              onClick={() => onOpen(task.id)}
              className="hover:bg-muted/50 flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors"
            >
              <StatusBadge status={task.status} />
              <span className="min-w-0 flex-1 truncate text-sm">
                {task.title}
              </span>
              <span className="text-muted-foreground hidden text-xs sm:inline">
                {task.agent}
              </span>
              <span
                className="text-muted-foreground shrink-0 text-xs whitespace-nowrap"
                title={exactTime(task.updated_at)}
              >
                {timeAgo(task.updated_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function TaskDrawer({
  taskId,
  task,
  onClose,
}: {
  /** From the URL; may name a task outside the loaded list. */
  taskId: string | null;
  task: Task | null;
  onClose: () => void;
}) {
  const events = useQuery({
    queryKey: qk.taskEvents(taskId ?? ""),
    queryFn: taskId ? () => api.taskEvents(taskId) : skipToken,
  });

  return (
    <Dialog open={Boolean(taskId)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="pr-6 text-base">
            {task?.title ?? "Task"}
          </DialogTitle>
          <DialogDescription>
            {task
              ? `${task.agent} · ${task.source} · full event log`
              : "This task is not in the latest 100. Its event log is below."}
          </DialogDescription>
        </DialogHeader>
        {taskId ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              {task ? <StatusBadge status={task.status} /> : null}
              {task?.run_id ? (
                <Button size="sm" variant="outline" asChild>
                  <Link href={`/runs/${encodeURIComponent(task.run_id)}`}>
                    View run
                  </Link>
                </Button>
              ) : null}
            </div>
            {task?.brief ? (
              <div>
                <p className="mb-1 text-sm font-medium">Brief</p>
                <p className="text-sm break-words whitespace-pre-wrap">
                  {task.brief}
                </p>
              </div>
            ) : null}
            <div>
              <p className="mb-2 text-sm font-medium">Event log</p>
              {events.isError ? (
                <ErrorState
                  message={events.error.message}
                  onRetry={() => events.refetch()}
                  retrying={events.isFetching}
                />
              ) : (
                <ol className="border-border max-h-[50svh] space-y-3 overflow-auto border-l pl-4 text-xs">
                  {events.data?.map((event) => (
                    <EventRow key={event.seq} event={event} />
                  ))}
                </ol>
              )}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

/** One task event. `output` (the agent's final answer) renders as markdown;
 * every other data key stays in a JSON block. */
function EventRow({ event }: { event: TaskEvent }) {
  const { output, ...rest } = event.data;
  const text = typeof output === "string" && output ? output : null;
  return (
    <li>
      <span className="font-medium">{event.event_type}</span>
      <span className="text-muted-foreground">
        {" "}
        · {event.actor} · {new Date(event.ts).toLocaleString()}
      </span>
      {text ? (
        <div className="bg-muted/40 mt-1 rounded border p-3">
          <Markdown content={text} />
        </div>
      ) : null}
      {Object.keys(rest).length > 0 ? (
        <pre className="bg-muted mt-1 overflow-auto rounded p-2">
          {JSON.stringify(rest, null, 2)}
        </pre>
      ) : null}
    </li>
  );
}
