"use client";

import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/page-header";
import { OutcomeBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
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

function usd(value: string | number) {
  return `$${Number(value).toFixed(4)}`;
}

function duration(start: string, end: string | null) {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

export function CostSummary() {
  const { data } = useQuery({ queryKey: qk.costs, queryFn: api.costs });
  if (!data) return null;
  const pct = Math.min(100, (data.today_usd / data.daily_cap_usd) * 100);
  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="flex items-baseline justify-between">
          <p className="text-sm font-medium">Spend today</p>
          <p className="text-sm tabular-nums">
            {usd(data.today_usd)}{" "}
            <span className="text-muted-foreground">
              of {usd(data.daily_cap_usd)} cap
            </span>
          </p>
        </div>
        <div className="bg-muted mt-3 h-2 overflow-hidden rounded-full">
          <div
            className="bg-primary h-full rounded-full transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </CardContent>
    </Card>
  );
}

export function RunsTable() {
  const { data, isLoading } = useQuery({ queryKey: qk.runs, queryFn: () => api.runs() });

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data?.length) return <EmptyState>No runs recorded yet.</EmptyState>;

  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Agent</TableHead>
            <TableHead>Model</TableHead>
            <TableHead>Outcome</TableHead>
            <TableHead className="text-right">Tokens</TableHead>
            <TableHead className="text-right">Cost</TableHead>
            <TableHead className="text-right">Duration</TableHead>
            <TableHead>Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((run) => (
            <TableRow key={run.id}>
              <TableCell className="font-medium">{run.agent}</TableCell>
              <TableCell className="text-muted-foreground">{run.model}</TableCell>
              <TableCell>
                <OutcomeBadge outcome={run.outcome} />
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {run.input_tokens + run.output_tokens}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {usd(run.cost_usd)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {duration(run.started_at, run.ended_at)}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {new Date(run.started_at).toLocaleString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
