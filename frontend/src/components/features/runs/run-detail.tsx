"use client";

import Link from "next/link";
import { skipToken, useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { RunTimeline } from "@/components/features/runs/run-timeline";
import { Markdown } from "@/components/features/vault/markdown";
import { OutcomeBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, qk } from "@/lib/api/client";
import type { RunDetail as RunDetailData, TaskEvent } from "@/lib/api/types";

function usd(value: number) {
  return `$${value.toFixed(4)}`;
}

function duration(start: string, end: string | null) {
  if (!end) return "still running";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  );
}

function RunHeader({ detail }: { detail: RunDetailData }) {
  const { run } = detail;
  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold">{run.agent}</h2>
          <OutcomeBadge outcome={run.outcome} />
          {run.task_title ? (
            <p className="text-muted-foreground text-sm">
              Task: <span className="text-foreground">{run.task_title}</span>
            </p>
          ) : (
            <p className="text-muted-foreground text-sm">Chat run</p>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-4">
          <Field label="Model">{run.model || "—"}</Field>
          <Field label="Cost">
            <span className="tabular-nums">{usd(run.cost_usd)}</span>
          </Field>
          <Field label="Tokens">
            <span className="tabular-nums">
              {(run.input_tokens + run.output_tokens).toLocaleString()}
            </span>
            <span className="text-muted-foreground text-xs">
              {" "}
              ({run.input_tokens.toLocaleString()} in /{" "}
              {run.output_tokens.toLocaleString()} out)
            </span>
          </Field>
          <Field label="Duration">
            <span className="tabular-nums">
              {duration(run.started_at, run.ended_at)}
            </span>
          </Field>
          <Field label="Started">
            <time dateTime={run.started_at}>
              {new Date(run.started_at).toLocaleString()}
            </time>
          </Field>
          {run.error ? (
            <Field label="Error" className="col-span-2 md:col-span-4">
              <span className="text-status-danger break-words">{run.error}</span>
            </Field>
          ) : null}
        </dl>

        {/* Identifiers and counters: needed when something goes wrong, not
            when reading a healthy run. Kept quiet and on one line. */}
        <p className="text-muted-foreground mt-4 border-t pt-3 font-mono text-xs break-all">
          run {run.id}
          {run.job_hash ? ` · job ${run.job_hash}` : ""}
          {run.stall_count > 0
            ? ` · ${run.stall_count} stalled round${run.stall_count === 1 ? "" : "s"}`
            : ""}
        </p>
      </CardContent>
    </Card>
  );
}

/** The final answer of the run: the task's run_* event output for task runs,
 * the assistant's reply for chat runs, otherwise the run error. */
function latestOutput(events: TaskEvent[] | undefined): string | null {
  if (!events) return null;
  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i];
    if (event.event_type.startsWith("run_")) {
      const output = event.data.output;
      return typeof output === "string" && output ? output : null;
    }
  }
  return null;
}

function RunOutput({ detail }: { detail: RunDetailData }) {
  const { run, transcript } = detail;
  const taskId = run.task_id;
  const taskEvents = useQuery({
    queryKey: qk.taskEvents(taskId ?? ""),
    queryFn: taskId ? () => api.taskEvents(taskId) : skipToken,
  });

  if (taskId && taskEvents.isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading output">
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (taskId && taskEvents.isError) {
    return (
      <ErrorState
        message={taskEvents.error.message}
        onRetry={() => taskEvents.refetch()}
        retrying={taskEvents.isFetching}
      />
    );
  }

  const fromTask = latestOutput(taskEvents.data);
  const reply = transcript
    ? [...transcript].reverse().find((m) => m.role === "assistant")?.text
    : undefined;
  const text = fromTask ?? reply ?? null;

  if (!text && !run.error) {
    return (
      <EmptyState>
        {run.ended_at
          ? `No output stored for this run${
              detail.transcript_reason ? ` (${detail.transcript_reason})` : ""
            }.`
          : "The run has not finished yet."}
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {transcript?.length ? (
        <section aria-label="Conversation round" className="flex flex-col gap-2">
          {transcript.map((m, i) => (
            <div
              key={`${m.role}-${i}`}
              className="bg-muted/40 rounded-lg border px-3 py-2 text-sm"
            >
              <p className="text-muted-foreground mb-1 text-xs capitalize">
                {m.role}
              </p>
              {m.role === "assistant" ? (
                <Markdown content={m.text} />
              ) : (
                <p className="whitespace-pre-wrap">{m.text}</p>
              )}
            </div>
          ))}
        </section>
      ) : text ? (
        <div className="rounded-lg border p-4">
          <Markdown content={text} />
        </div>
      ) : null}
      {run.error ? (
        <p className="text-status-danger text-sm break-words">
          <span className="font-medium">Error: </span>
          {run.error}
        </p>
      ) : null}
    </div>
  );
}

export function RunDetail({
  id,
  variant = "page",
}: {
  id: string;
  /** "drawer" drops the back link and the page-level spacing. */
  variant?: "page" | "drawer";
}) {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: qk.runDetail(id),
    queryFn: () => api.runDetail(id),
  });

  if (isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading run">
        <Skeleton className="mb-6 h-40 w-full" />
        <Skeleton className="h-64 w-full" />
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
  if (!data) return <EmptyState>Run not found.</EmptyState>;

  return (
    <>
      {variant === "page" ? (
        <Button
          variant="ghost"
          size="sm"
          asChild
          className="mb-3 -ml-2 self-start"
        >
          <Link href="/runs">
            <ArrowLeft aria-hidden />
            All runs
          </Link>
        </Button>
      ) : null}
      <RunHeader detail={data} />
      <Tabs defaultValue="output">
        <TabsList>
          <TabsTrigger value="output">Output</TabsTrigger>
          <TabsTrigger value="steps">
            Steps ({data.events.length + data.tickets.length})
          </TabsTrigger>
        </TabsList>
        <TabsContent value="output" className="pt-4">
          <RunOutput detail={data} />
        </TabsContent>
        <TabsContent value="steps" className="pt-4">
          <RunTimeline detail={data} />
        </TabsContent>
      </Tabs>
    </>
  );
}
