"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Pause, Play, Settings2 } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { OutcomeBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import type { Run, Task } from "@/lib/api/types";
import { guideFor } from "@/lib/agent-guide";
import { describeCron } from "@/lib/cron";
import { exactTime, timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

const TIMELINE_ROWS = 8;
const RUNS_SCANNED = 50;

/**
 * One agent, answered in the order the owner asks: is it working, what has it
 * actually done, and what is it allowed to do. Configuration is a separate
 * page, because reading an agent and editing one are different jobs.
 */
export function AgentProfile({ name }: { name: string }) {
  const queryClient = useQueryClient();
  const agents = useQuery({ queryKey: qk.agents, queryFn: api.agents });
  const runs = useQuery({
    queryKey: qk.runs(RUNS_SCANNED),
    queryFn: () => api.runs(RUNS_SCANNED),
  });
  const tasks = useQuery({ queryKey: qk.tasks(), queryFn: () => api.tasks() });

  const agent = agents.data?.find((row) => row.name === name) ?? null;
  const mine = useMemo(
    () => (runs.data ?? []).filter((run: Run) => run.agent === name),
    [runs.data, name],
  );
  const openTask = (tasks.data ?? []).find(
    (task: Task) => task.agent === name && task.status === "running",
  );

  const togglePause = useMutation({
    mutationFn: (paused: boolean) => api.setAgentPaused(name, paused),
    onSuccess: (result) => {
      toast(`${result.agent} ${result.paused ? "paused" : "resumed"}`);
      queryClient.invalidateQueries({ queryKey: qk.agents });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (agents.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (agents.isError) {
    return (
      <ErrorState
        message={agents.error.message}
        onRetry={() => agents.refetch()}
        retrying={agents.isFetching}
      />
    );
  }
  if (!agent) {
    return (
      <ErrorState message={`No agent named ${name} is loaded.`} />
    );
  }

  const done = mine.filter((run) => run.outcome === "done").length;
  const failed = mine.filter((run) => run.outcome === "failed").length;
  const finished = mine.filter((run) => run.outcome !== null).length;
  const success = finished ? Math.round((done / finished) * 100) : null;
  const guide = guideFor(name);
  const state = agent.paused ? "paused" : openTask ? "working" : "idle";

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{agent.name}</h1>
          <Badge
            variant="secondary"
            tone={
              state === "working"
                ? "success"
                : state === "paused"
                  ? "blocked"
                  : "muted"
            }
          >
            {state}
          </Badge>
          <Badge variant="outline" className="font-normal">
            {agent.model}
          </Badge>
        </div>
        <p className="text-muted-foreground max-w-prose text-sm">
          {guide?.does ?? agent.description}
        </p>

        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <Link href="/chat">
              <MessageSquare aria-hidden />
              Message {agent.name}
            </Link>
          </Button>
          <Button
            variant="outline"
            disabled={togglePause.isPending}
            onClick={() => togglePause.mutate(!agent.paused)}
          >
            {agent.paused ? <Play aria-hidden /> : <Pause aria-hidden />}
            {agent.paused ? "Resume" : "Pause"}
          </Button>
          <Button variant="outline" asChild>
            <Link href={`/agents/${encodeURIComponent(name)}/config`}>
              <Settings2 aria-hidden />
              Configure
            </Link>
          </Button>
        </div>
      </header>

      <Card>
        <CardContent className="grid grid-cols-2 gap-y-4 pt-6 md:grid-cols-5">
          <Stat value={done} label="Completed" />
          <Stat value={openTask ? 1 : 0} label="In flight" />
          <Stat value={failed} label="Failed" tone={failed ? "danger" : undefined} />
          <Stat
            value={`$${agent.spend_today_usd.toFixed(4)}`}
            label="Spent today"
          />
          <Stat
            value={success === null ? "—" : `${success}%`}
            label="Success"
            tone={success !== null && success < 80 ? "blocked" : undefined}
          />
        </CardContent>
      </Card>

      <Card className={cn(openTask && "border-status-running/50")}>
        <CardContent className="pt-6">
          <p className="text-muted-foreground flex items-center gap-2 text-xs font-medium tracking-wide uppercase">
            {openTask ? (
              <span
                aria-hidden
                className="bg-status-running size-1.5 rounded-full motion-safe:animate-pulse"
              />
            ) : null}
            Working on now
          </p>
          <p className="mt-1.5 text-sm">
            {openTask ? (
              <Link
                href={`/board?task=${encodeURIComponent(openTask.id)}`}
                className="font-medium underline-offset-4 hover:underline"
              >
                {openTask.title}
              </Link>
            ) : agent.paused ? (
              "Paused. It will not start a run until you resume it."
            ) : (
              "Nothing right now. It runs on its schedule, or when you ask."
            )}
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Timeline
          runs={mine.slice(0, TIMELINE_ROWS)}
          loading={runs.isLoading}
          error={runs.isError ? runs.error.message : null}
        />

        <div className="flex flex-col gap-4">
          <Panel title="Runs on its own">
            {agent.cron.length ? (
              <ul className="flex flex-col gap-1 text-sm">
                {agent.cron.map((entry, i) => (
                  <li key={`${entry.schedule}-${i}`} title={entry.schedule}>
                    {describeCron(entry.schedule)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-sm">
                No schedule. It runs when you ask, or when another agent creates
                a task for it.
              </p>
            )}
          </Panel>

          <Panel title="Tools it holds">
            <div className="flex flex-wrap gap-1">
              {agent.tools.map((tool) => (
                <Badge key={tool} variant="outline" className="font-normal">
                  {tool}
                </Badge>
              ))}
            </div>
          </Panel>

          <Panel title="Where it writes">
            <p className="font-mono text-xs break-all">
              {guide?.output ??
                (agent.vault_write_scopes.length
                  ? agent.vault_write_scopes.join(", ")
                  : "nowhere")}
            </p>
          </Panel>

          {guide ? (
            <Panel title="How to use it">
              <ul className="flex list-disc flex-col gap-1 pl-4 text-sm">
                {guide.use.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </Panel>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Stat({
  value,
  label,
  tone,
}: {
  value: number | string;
  label: string;
  tone?: "danger" | "blocked";
}) {
  return (
    <div>
      <p
        className={cn(
          "text-2xl font-semibold tabular-nums",
          tone === "danger" && "text-status-danger",
          tone === "blocked" && "text-status-blocked",
        )}
      >
        {value}
      </p>
      <p className="text-muted-foreground mt-0.5 text-sm">{label}</p>
    </div>
  );
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          {title}
        </p>
        <div className="mt-2">{children}</div>
      </CardContent>
    </Card>
  );
}

/** What this agent actually did, newest first, each row opening its run. */
function Timeline({
  runs,
  loading,
  error,
}: {
  runs: Run[];
  loading: boolean;
  error: string | null;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          What it has done
        </p>
        <div className="mt-3">
          {loading ? (
            <Skeleton className="h-40 w-full" />
          ) : error ? (
            <p className="text-muted-foreground text-sm">
              Runs unavailable: {error}
            </p>
          ) : !runs.length ? (
            <p className="text-muted-foreground text-sm">
              No runs yet. The first one appears here the moment it works.
            </p>
          ) : (
            <ol className="border-border flex flex-col gap-4 border-l pl-4">
              {runs.map((run) => (
                <li key={run.id} className="relative">
                  <span
                    aria-hidden
                    className={cn(
                      "bg-background absolute top-1.5 -left-[calc(1rem+5px)] size-2.5 rounded-full border-2",
                      run.outcome === "done" && "border-status-success",
                      run.outcome === "failed" && "border-status-danger",
                      run.outcome === "blocked" && "border-status-blocked",
                      run.outcome === null && "border-status-running",
                    )}
                  />
                  <Link
                    href={`/runs?run=${encodeURIComponent(run.id)}`}
                    className="hover:bg-muted/50 -mx-2 block rounded-md px-2 py-1 transition-colors"
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <OutcomeBadge outcome={run.outcome} />
                      <span className="text-muted-foreground text-xs tabular-nums">
                        ${run.cost_usd.toFixed(4)}
                      </span>
                      <span
                        className="text-muted-foreground ml-auto text-xs whitespace-nowrap"
                        title={exactTime(run.started_at)}
                      >
                        {timeAgo(run.started_at)}
                      </span>
                    </span>
                    {run.error ? (
                      <span className="text-status-danger mt-0.5 block text-sm">
                        {run.error}
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
