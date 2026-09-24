"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  Briefcase,
  FileCheck,
  type LucideIcon,
  Scale,
  Send,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState } from "@/components/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useFeed } from "@/hooks/use-hq-events";
import { feedHref, feedLabel } from "@/components/features/feed/live-feed";
import { TicketList } from "@/components/features/inbox/ticket-list";
import { ValueWeekCard } from "@/components/features/inbox/value-week-card";
import { api, qk } from "@/lib/api/client";
import type { NeedKind, SlotStatus, Today, TodayNeed } from "@/lib/api/types";
import { clockTime, exactTime } from "@/lib/time";

const FEED_ROWS = 5;
const subscribeToHydration = () => () => {};

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 5) return "Still up";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/**
 * The first screen of his day, in the order he acts on it: what needs him,
 * whether last night ran, and how the week is going.
 *
 * It used to count approval tickets only, so it said "all caught up" on a
 * morning with six unread lessons, open decisions, memory proposals and four
 * posts waiting, over a list of approvals from weeks before. The needs and
 * the night now come from one server call that reads the same ledger as
 * sage's nightly note, so the page and the note agree.
 */
export function HomeView() {
  const hydrated = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false,
  );
  const today = useQuery({ queryKey: qk.today, queryFn: api.today, staleTime: 30_000 });
  const costs = useQuery({ queryKey: qk.costs, queryFn: api.costs });

  const localDate = hydrated
    ? new Date().toLocaleDateString(undefined, {
        weekday: "long",
        day: "numeric",
        month: "long",
      })
    : "";
  const needs = today.data?.needs ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{greeting()}</h1>
        <p className="text-muted-foreground mt-1 min-h-5 text-sm">
          {localDate}
          {today.data
            ? needs.length
              ? ` · ${needs.length} thing${needs.length === 1 ? "" : "s"} need you`
              : " · nothing needs you"
            : null}
        </p>
      </div>

      <TicketList pendingOnly />

      <NeedsCard
        needs={needs}
        loading={today.isLoading}
        error={today.isError ? today.error.message : null}
        onRetry={() => today.refetch()}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <NightCard night={today.data?.night} loading={today.isLoading} />
        <WeekCard
          week={today.data?.week}
          spentToday={costs.data?.today_usd}
          cap={costs.data?.daily_cap_usd}
          loading={today.isLoading}
        />
      </div>

      <ActivityCard />

      {/* The kill metric lives with the decisions it measures. Last, because
          it is read weekly and the needs above are read now. */}
      <ValueWeekCard />
    </div>
  );
}

const NEED_ICON: Record<NeedKind, LucideIcon> = {
  read: BookOpen,
  decide: Scale,
  review: FileCheck,
  post: Send,
  apply: Briefcase,
  fix: Wrench,
};

/** What needs him, most blocking first: each row says what, why, and where. */
function NeedsCard({
  needs,
  loading,
  error,
  onRetry,
}: {
  needs: TodayNeed[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  return (
    <section aria-label="What needs you" className="flex flex-col gap-2">
      <h2 className="text-muted-foreground px-1 text-xs font-medium tracking-wide uppercase">
        Needs you
      </h2>
      {loading ? (
        <Skeleton className="h-40 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : !needs.length ? (
        <Card>
          <CardContent className="text-muted-foreground py-6 text-center text-sm">
            Nothing needs you. Tonight&apos;s runs start on their own.
          </CardContent>
        </Card>
      ) : (
        <Card className="py-0">
          <ul className="divide-y">
            {needs.map((need) => {
              const Icon = NEED_ICON[need.kind] ?? ArrowRight;
              return (
                <li key={need.key}>
                  <Link
                    href={need.href}
                    className="hover:bg-muted/40 flex items-center gap-3 px-4 py-3 transition-colors"
                  >
                    <span className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-full">
                      <Icon aria-hidden className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{need.title}</span>
                      <span className="text-muted-foreground line-clamp-2 text-xs sm:line-clamp-1">
                        {need.detail}
                      </span>
                    </span>
                    <span className="text-primary hidden shrink-0 items-center gap-1 text-xs font-medium sm:flex">
                      {need.action}
                      <ArrowRight aria-hidden className="size-3" />
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </section>
  );
}

const SLOT_TONE: Partial<Record<SlotStatus, "success" | "danger" | "running" | "muted" | "blocked">> = {
  done: "success",
  started: "success",
  held: "muted",
  running: "running",
  backlog: "running",
  needs_approval: "blocked",
  due: "muted",
  blocked: "danger",
  failed: "danger",
  missed: "danger",
};

const SLOT_WORD: Partial<Record<SlotStatus, string>> = {
  held: "waiting on you",
  started: "started",
  backlog: "queued",
  needs_approval: "needs approval",
  due: "not yet",
};

/**
 * Every scheduled slot of the past day with what became of it. Before this
 * page had it, the only sign that a whole evening died while the laptop
 * slept was four alarms on his phone at 1 a.m.
 */
function NightCard({
  night,
  loading,
}: {
  night: Today["night"] | undefined;
  loading: boolean;
}) {
  const slots = night?.slots ?? [];
  const failed = slots.filter((s) => ["blocked", "failed", "missed"].includes(s.status)).length;
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-medium">Last 24 hours of schedules</h2>
          {slots.length ? (
            <span className="text-muted-foreground text-xs">
              {failed ? `${failed} of ${slots.length} did not finish` : `all ${slots.length} ran`}
            </span>
          ) : null}
        </div>
        {night?.cut_runs ? (
          <p className="bg-status-blocked/10 text-status-blocked mt-3 rounded-md px-3 py-2 text-xs">
            {night.cut_runs} run{night.cut_runs === 1 ? " was" : "s were"} cut mid-way, most
            likely while this Mac slept. Schedules cannot run on a sleeping machine.
          </p>
        ) : null}
        <div className="mt-3">
          {loading ? (
            <Skeleton className="h-40 w-full" />
          ) : !slots.length ? (
            <p className="text-muted-foreground text-sm">Nothing was scheduled in the past day.</p>
          ) : (
            <ol className="flex flex-col">
              {slots.map((slot) => (
                <li key={`${slot.at}-${slot.label}`} className="flex items-start gap-3 py-1.5 text-sm">
                  <span className="text-muted-foreground w-11 shrink-0 pt-0.5 text-xs tabular-nums">
                    {clockTime(slot.at)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{slot.label}</span>
                    {slot.status === "held" && slot.detail ? (
                      <span className="text-muted-foreground line-clamp-1 text-xs">
                        {slot.detail.replace(/^not starting[^:]*:\s*/, "")}
                      </span>
                    ) : null}
                  </span>
                  <Badge variant="secondary" tone={SLOT_TONE[slot.status]} className="shrink-0">
                    {SLOT_WORD[slot.status] ?? slot.status}
                  </Badge>
                  {slot.task_id ? (
                    <Link
                      href={`/board?task=${slot.task_id}`}
                      className="text-muted-foreground hover:text-foreground shrink-0 text-xs underline-offset-2 hover:underline"
                    >
                      open
                    </Link>
                  ) : (
                    <span className="w-8 shrink-0" />
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/** The week in numbers that say whether any of this is being used. */
function WeekCard({
  week,
  spentToday,
  cap,
  loading,
}: {
  week: Today["week"] | undefined;
  spentToday: number | undefined;
  cap: number | undefined;
  loading: boolean;
}) {
  const n = (v: number | null | undefined) => (v === null || v === undefined ? "—" : String(v));
  const rows: { label: string; value: string; hint?: string; href?: string }[] = [
    { label: "Lessons read / written", value: `${n(week?.lessons_read)} / ${n(week?.lessons_written)}`, href: "/learn" },
    { label: "Unread now", value: n(week?.unread), href: "/learn" },
    { label: "Posts filed", value: n(week?.posts_filed), hint: "posted: not recorded", href: "/ideas" },
    { label: "Roles found / strong", value: `${n(week?.jobs_found)} / ${n(week?.jobs_strong)}`, href: "/jobs" },
    { label: "Applied", value: n(week?.jobs_applied), href: "/jobs" },
    {
      label: "Spend, 7 days",
      value: week?.spend_usd === null || week?.spend_usd === undefined ? "—" : `$${week.spend_usd.toFixed(2)}`,
      hint: spentToday !== undefined && cap !== undefined ? `$${spentToday.toFixed(2)} today of $${cap.toFixed(0)}` : undefined,
      href: "/runs",
    },
  ];
  return (
    <Card>
      <CardContent className="pt-6">
        <h2 className="text-sm font-medium">This week</h2>
        {loading ? (
          <Skeleton className="mt-3 h-40 w-full" />
        ) : (
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
            {rows.map((row) => (
              <Link key={row.label} href={row.href ?? "#"} className="hover:bg-muted/40 -mx-2 rounded-md px-2 py-1">
                <dt className="text-muted-foreground text-xs">{row.label}</dt>
                <dd className="text-lg font-semibold tabular-nums">{row.value}</dd>
                {row.hint ? <dd className="text-muted-foreground text-xs">{row.hint}</dd> : null}
              </Link>
            ))}
          </dl>
        )}
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
          <Link href="/runs?tab=feed">
            Live feed
            <ArrowRight aria-hidden />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
