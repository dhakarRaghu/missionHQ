"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import type { DailyCost } from "@/lib/api/types";

const DAYS = 14;
/** Colour tokens from globals.css, cycled per agent. */
const SERIES_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-7)",
  "var(--chart-8)",
];

/** One chart row: {date, total, <agent>: usd, ...}. */
type Row = { date: string; total: number } & Record<string, number | string>;

/** Date strings are CRON_TZ calendar days from the backend. Arithmetic on
 * them is done in UTC so no local timezone shift can change the day. */
function addDays(date: string, days: number) {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function todayLocal() {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function shapeRows(rows: DailyCost[], days = DAYS) {
  const agents = Array.from(new Set(rows.map((r) => r.agent))).sort();
  const last = rows.reduce((max, r) => (r.date > max ? r.date : max), todayLocal());
  const first = addDays(last, -(days - 1));
  const byDate = new Map<string, Row>();
  for (let d = first; d <= last; d = addDays(d, 1)) {
    const row: Row = { date: d, total: 0 };
    for (const agent of agents) row[agent] = 0;
    byDate.set(d, row);
  }
  for (const r of rows) {
    const row = byDate.get(r.date);
    if (!row) continue;
    row[r.agent] = Number(row[r.agent] ?? 0) + r.usd;
    row.total += r.usd;
  }
  return { agents, rows: Array.from(byDate.values()) };
}

function chartConfig(agents: string[]): ChartConfig {
  const config: ChartConfig = {};
  // Slot order is the sorted agent list, so an agent keeps its colour when
  // another agent has no spend on a given day.
  agents.forEach((agent, i) => {
    config[agent] = {
      label: agent,
      color: SERIES_COLORS[i % SERIES_COLORS.length],
    };
  });
  return config;
}

function usd(value: number) {
  return `$${value.toFixed(value >= 1 ? 2 : 4)}`;
}

function shortDate(date: string) {
  return date.slice(5).replace("-", "/");
}

/** Per-agent totals over the window, in slot colour order. */
function SeriesTotals({
  agents,
  rows,
  config,
}: {
  agents: string[];
  rows: Row[];
  config: ChartConfig;
}) {
  const totals = agents
    .map((agent) => ({
      agent,
      usd: rows.reduce((sum, row) => sum + Number(row[agent] ?? 0), 0),
    }))
    .sort((a, b) => b.usd - a.usd);

  return (
    <ul
      aria-label={`Spend per agent over the last ${DAYS} days`}
      className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs"
    >
      {totals.map((row) => (
        <li key={row.agent} className="flex items-center gap-1.5">
          {/* The --color-<agent> variables ChartContainer injects are scoped
              to the chart element, so read the token from the config instead. */}
          <span
            aria-hidden
            className="size-2.5 shrink-0 rounded-[2px]"
            style={{ background: config[row.agent]?.color }}
          />
          <span>{config[row.agent]?.label ?? row.agent}</span>
          <span className="text-muted-foreground tabular-nums">
            {usd(row.usd)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** 14-day stacked spend per agent. Sits above the agent
 * cards; an error here is shown in place and never hides the agents. */
export function CostChart() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: qk.dailyCosts(DAYS),
    queryFn: () => api.dailyCosts(DAYS),
  });
  const shaped = useMemo(() => (data ? shapeRows(data) : null), [data]);
  const config = useMemo(
    () => chartConfig(shaped?.agents ?? []),
    [shaped?.agents],
  );
  const total = data?.reduce((sum, r) => sum + r.usd, 0) ?? 0;

  return (
    <Card className="mb-6">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-baseline justify-between text-base">
          <span>Spend, last {DAYS} days</span>
          {data ? (
            <span className="text-muted-foreground text-sm font-normal tabular-nums">
              {usd(total)} total
            </span>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div role="status" aria-busy="true" aria-label="Loading spend chart">
            <Skeleton className="h-44 w-full" />
          </div>
        ) : isError ? (
          <p role="alert" className="text-muted-foreground text-sm">
            Spend chart unavailable: {error.message}
          </p>
        ) : !shaped || !shaped.agents.length ? (
          <p className="text-muted-foreground text-sm">No runs in the last {DAYS} days.</p>
        ) : (
          <>
            <ChartContainer config={config} className="h-44 w-full">
              <BarChart data={shaped.rows} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} />
                <XAxis
                  dataKey="date"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={6}
                  tickFormatter={shortDate}
                  minTickGap={16}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  width={56}
                  tickFormatter={(v: number) => usd(v)}
                />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      labelFormatter={(label) => String(label)}
                      formatter={(value, name) => (
                        <div className="flex w-full items-center justify-between gap-3">
                          <span>{config[String(name)]?.label ?? name}</span>
                          <span className="font-mono tabular-nums">
                            {usd(Number(value))}
                          </span>
                        </div>
                      )}
                    />
                  }
                />
                {shaped.agents.map((agent) => (
                  <Bar
                    key={agent}
                    dataKey={agent}
                    stackId="usd"
                    fill={`var(--color-${agent})`}
                    // A 2px surface-coloured edge separates touching segments,
                    // so a stack of six agents stays readable.
                    stroke="var(--card)"
                    strokeWidth={2}
                    radius={0}
                    isAnimationActive={false}
                  />
                ))}
              </BarChart>
            </ChartContainer>
            {/* Doubles as the legend and as the readable alternative to the
                chart: three of the light-mode series sit below 3:1 against a
                white card, so the numbers must also exist as text. */}
            <SeriesTotals
              agents={shaped.agents}
              rows={shaped.rows}
              config={config}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}
