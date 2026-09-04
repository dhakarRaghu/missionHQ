"use client";

import { useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { RunDrawer } from "@/components/features/runs/run-drawer";
import { OutcomeBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, qk } from "@/lib/api/client";
import { exactTime, timeAgo } from "@/lib/time";

const RUNS_LIMIT = 50;

function usd(value: number) {
  return `$${value.toFixed(4)}`;
}

const LONG_RUN_MS = 30 * 60 * 1000;

function duration(start: string, end: string | null) {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  // A run that blocks on an approval keeps its clock running, so a very long
  // duration is usually the wait for you, not slow work.
  if (ms >= LONG_RUN_MS) {
    const hours = ms / 3_600_000;
    return `${hours.toFixed(1)}h`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

function shortId(id: string) {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

export function CostSummary() {
  const { data, isError, error, refetch, isFetching } = useQuery({
    queryKey: qk.costs,
    queryFn: api.costs,
  });
  if (isError) {
    return (
      <div className="mb-6">
        <ErrorState
          message={error.message}
          onRetry={() => refetch()}
          retrying={isFetching}
        />
      </div>
    );
  }
  if (!data) return null;

  const cap = data.daily_cap_usd;
  const pct = cap > 0 ? Math.min(100, (data.today_usd / cap) * 100) : 0;

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-sm font-medium">Spend today</p>
          <p className="text-sm tabular-nums">
            {usd(data.today_usd)}{" "}
            <span className="text-muted-foreground">
              {cap > 0 ? `of ${usd(cap)} cap` : "no daily cap"}
            </span>
          </p>
        </div>
        <Progress
          className="mt-3 h-2"
          value={pct}
          aria-label="Share of the daily cap spent"
        />
      </CardContent>
    </Card>
  );
}

export function RunsTable() {
  // The open run lives in the URL (?run=<id>) so the panel survives a refresh
  // and the back button closes it.
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const openRunId = params.get("run");
  const setOpenRunId = useCallback(
    (id: string | null) => {
      if (id) router.push(`${pathname}?run=${encodeURIComponent(id)}`);
      else router.replace(pathname);
    },
    [router, pathname],
  );

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: qk.runs(RUNS_LIMIT),
    queryFn: () => api.runs(RUNS_LIMIT),
  });

  if (isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading runs">
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
  if (!data?.length) {
    return (
      <EmptyState title="No runs yet">
        Every execution lands here with its model, tokens and real cost, whether
        it came from a schedule, the board, or a chat.
      </EmptyState>
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border">
        <Table aria-label="Agent runs">
          <TableHeader>
            <TableRow>
              <TableHead>Agent</TableHead>
              <TableHead>Task</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>Outcome</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead className="text-right">Duration</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Error</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((run) => (
              <TableRow
                key={run.id}
                // The whole row opens the panel. The link in the first cell
                // keeps the run reachable by keyboard and screen reader.
                onClick={() => setOpenRunId(run.id)}
                className="hover:bg-muted/50 cursor-pointer transition-colors"
              >
                <TableCell className="font-medium">
                  <Link
                    href={`/runs/${encodeURIComponent(run.id)}`}
                    className="hover:underline"
                    aria-label={`Open run ${run.id} by ${run.agent}`}
                  >
                    {run.agent}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs">
                  {run.task_id ? (
                    <span title={run.task_id}>{shortId(run.task_id)}</span>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {run.model}
                </TableCell>
                <TableCell>
                  <OutcomeBadge outcome={run.outcome} />
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {(run.input_tokens + run.output_tokens).toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {usd(run.cost_usd)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {duration(run.started_at, run.ended_at)}
                </TableCell>
                <TableCell
                  className="text-muted-foreground whitespace-nowrap"
                  title={exactTime(run.started_at)}
                >
                  {timeAgo(run.started_at)}
                </TableCell>
                <TableCell className="max-w-48">
                  {run.error ? (
                    <span
                      className="text-status-danger block truncate"
                      title={run.error}
                    >
                      {run.error}
                    </span>
                  ) : (
                    "—"
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <RunDrawer runId={openRunId} onClose={() => setOpenRunId(null)} />
    </>
  );
}
