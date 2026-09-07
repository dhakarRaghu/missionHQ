"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useFeed } from "@/hooks/use-hq-events";
import { feedHref, feedLabel } from "@/components/features/feed/live-feed";
import { api, qk } from "@/lib/api/client";
import type { Task } from "@/lib/api/types";
import { describeCron } from "@/lib/cron";
import { clockTime, exactTime } from "@/lib/time";

const FEED_ROWS = 6;
const subscribeToHydration = () => () => {};

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 5) return "Still up";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function isToday(iso: string): boolean {
  const then = new Date(iso);
  const now = new Date();
  return (
    then.getFullYear() === now.getFullYear() &&
    then.getMonth() === now.getMonth() &&
    then.getDate() === now.getDate()
  );
}

/**
 * The one screen that answers "what is my system doing" without reading four
 * other views: what needs a decision, what the numbers are today, what is
 * scheduled, and what just happened.
 */
export function HomeView() {
  const hydrated = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false,
  );
  const tickets = useQuery({
    queryKey: qk.tickets("pending"),
    queryFn: () => api.tickets("pending"),
  });
  const tasks = useQuery({ queryKey: qk.tasks(), queryFn: () => api.tasks() });
  const costs = useQuery({ queryKey: qk.costs, queryFn: api.costs });
  const agents = useQuery({ queryKey: qk.agents, queryFn: api.agents });

  const pending = tickets.data ?? [];
  const all: Task[] = tasks.data ?? [];

  const localDate = hydrated
    ? new Date().toLocaleDateString(undefined, {
        weekday: "long",
        day: "numeric",
        month: "long",
      })
    : "";

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{greeting()}</h1>
        <p className="text-muted-foreground mt-1 min-h-5 text-sm">
          {localDate}
        </p>
      </div>

      <DecisionsCard
        count={pending.length}
        loading={tickets.isLoading}
        error={tickets.isError ? tickets.error.message : null}
        onRetry={() => tickets.refetch()}
      />

      <section aria-label="Today at a glance">
        <h2 className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
          Today at a glance
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            value={all.filter((t) => t.status === "done" && isToday(t.updated_at)).length}
            label="Tasks done today"
            loading={tasks.isLoading}
          />
          <Stat
            value={all.filter((t) => t.status === "running").length}
            label="Running now"
            loading={tasks.isLoading}
          />
          <Stat
            value={all.filter((t) => t.status === "blocked").length}
            label="Blocked"
            loading={tasks.isLoading}
            href="/board"
          />
          <Stat
            value={
              costs.data ? `$${costs.data.today_usd.toFixed(4)}` : "—"
            }
            label={
              costs.data
                ? `Spent today, cap $${costs.data.daily_cap_usd.toFixed(2)}`
                : "Spent today"
            }
            loading={costs.isLoading}
            href="/runs"
          />
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <ScheduleCard
          agents={agents.data ?? []}
          loading={agents.isLoading}
          error={agents.isError ? agents.error.message : null}
        />
        <ActivityCard />
      </div>
    </div>
  );
}

function Stat({
  value,
  label,
  loading,
  href,
}: {
  value: number | string;
  label: string;
  loading: boolean;
  href?: string;
}) {
  const body = (
    <Card className="h-full">
      <CardContent className="pt-6">
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
        )}
        <p className="text-muted-foreground mt-1 text-sm">{label}</p>
      </CardContent>
    </Card>
  );
  return href ? (
    <Link href={href} className="rounded-xl transition-opacity hover:opacity-80">
      {body}
    </Link>
  ) : (
    body
  );
}

/** The one thing on this page that can be blocking real work. */
function DecisionsCard({
  count,
  loading,
  error,
  onRetry,
}: {
  count: number;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (loading) return <Skeleton className="h-24 w-full" />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;

  if (!count) {
    return (
      <EmptyState title="You are all caught up">
        Nothing needs your decision. When an agent is about to do something
        outward, it stops and waits for you here.
      </EmptyState>
    );
  }

  return (
    <Card className="border-status-approval/50">
      <CardContent className="flex flex-wrap items-center gap-4 pt-6">
        <p className="text-3xl font-semibold tabular-nums">{count}</p>
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {count === 1 ? "decision is" : "decisions are"} waiting on you
          </p>
          <p className="text-muted-foreground text-sm">
            Each one has an agent paused behind it. Answering unblocks the run.
          </p>
        </div>
        <Button asChild>
          <Link href="/inbox">
            Open Inbox
            <ArrowRight aria-hidden />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

/** Every cron line across every agent, in one plain-English list. */
function ScheduleCard({
  agents,
  loading,
  error,
}: {
  agents: { name: string; paused: boolean; cron: { schedule: string }[] }[];
  loading: boolean;
  error: string | null;
}) {
  const rows = agents.flatMap((agent) =>
    agent.cron.map((entry) => ({
      agent: agent.name,
      paused: agent.paused,
      schedule: entry.schedule,
    })),
  );

  return (
    <Card>
      <CardContent className="pt-6">
        <h2 className="text-sm font-medium">What runs on its own</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          These fire without you. A schedule cannot run while this machine is
          asleep.
        </p>
        <div className="mt-3">
          {loading ? (
            <Skeleton className="h-24 w-full" />
          ) : error ? (
            <p className="text-muted-foreground text-sm">
              Schedules unavailable: {error}
            </p>
          ) : !rows.length ? (
            <p className="text-muted-foreground text-sm">
              No agent has a schedule.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {rows.map((row) => (
                <li
                  key={`${row.agent}-${row.schedule}`}
                  className="flex items-baseline justify-between gap-3 text-sm"
                >
                  <span className="flex items-center gap-2">
                    <Badge variant="outline" className="font-normal">
                      {row.agent}
                    </Badge>
                    {row.paused ? (
                      <Badge variant="secondary" tone="blocked">
                        paused
                      </Badge>
                    ) : null}
                  </span>
                  <span className="text-muted-foreground text-right">
                    {describeCron(row.schedule)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Button variant="ghost" size="sm" asChild className="mt-3 -ml-2">
          <Link href="/agents">
            All agents
            <ArrowRight aria-hidden />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

/** The newest events from the live stream, in the same words as the feed. */
function ActivityCard() {
  const feed = useFeed().slice(0, FEED_ROWS);

  return (
    <Card>
      <CardContent className="pt-6">
        <h2 className="text-sm font-medium">Just happened</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          The newest events, as they arrive.
        </p>
        <div className="mt-3">
          {!feed.length ? (
            <p className="text-muted-foreground text-sm">
              Nothing yet in this session. Events appear the moment an agent
              acts.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {feed.map((event) => {
                const href = feedHref(event);
                const label = (
                  <>
                    <span className="min-w-0 flex-1 truncate">
                      {feedLabel(event)}
                    </span>
                    <span
                      className="text-muted-foreground shrink-0 text-xs whitespace-nowrap"
                      title={exactTime(event.ts)}
                    >
                      {clockTime(event.ts)}
                    </span>
                  </>
                );
                return (
                  <li key={event.seq} className="flex items-baseline gap-3 text-sm">
                    {href ? (
                      <Link
                        href={href}
                        className="hover:bg-muted/50 -mx-2 flex min-w-0 flex-1 items-baseline gap-3 rounded px-2 py-0.5 transition-colors"
                      >
                        {label}
                      </Link>
                    ) : (
                      <span className="flex min-w-0 flex-1 items-baseline gap-3 px-0 py-0.5">
                        {label}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <Button variant="ghost" size="sm" asChild className="mt-3 -ml-2">
          <Link href="/feed">
            Live feed
            <ArrowRight aria-hidden />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
