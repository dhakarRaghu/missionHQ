"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { engagementApi, engagementKeys } from "@/lib/api/engagement";
import type { ValueWeekDay, ValueWeekStatus } from "@/lib/api/engagement";
import { cn } from "@/lib/utils";

const WEEK_DAYS = 7;
const OK_RATE = 0.5;

/**
 * The plan's kill metric: over 7 days, does the owner act on at least half of
 * what Mission HQ sends? Sits above the ticket list because the tickets are
 * the main thing being measured.
 */
export function ValueWeekCard() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: engagementKeys.status,
    queryFn: engagementApi.status,
  });

  const start = useMutation({
    mutationFn: engagementApi.start,
    onSuccess: (data) => {
      queryClient.setQueryData(engagementKeys.status, data);
      queryClient.invalidateQueries({ queryKey: engagementKeys.status });
      toast(`Value week started ${data.start ?? ""}`.trim());
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (status.isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading value week">
        <Skeleton className="mb-6 h-28 w-full" />
      </div>
    );
  }

  if (status.isError) {
    return (
      <div className="mb-6">
        <ErrorState
          message={status.error.message}
          onRetry={() => status.refetch()}
          retrying={status.isFetching}
        />
      </div>
    );
  }

  if (!status.data) return null;

  return (
    <Card className="mb-6">
      <CardHeader className="pb-3">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          Value week
          <VerdictBadge status={status.data} />
        </CardTitle>
        <p className="text-muted-foreground text-sm">
          {status.data.start
            ? `Day ${status.data.day} of ${WEEK_DAYS}. If you act on less than half of what the system sends, stop building and fix output quality.`
            : "Not started. Run the system for 7 days and measure whether you act on what it sends."}
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {status.data.start ? (
          <RateSection status={status.data} />
        ) : (
          <div>
            <Button
              size="sm"
              disabled={start.isPending}
              onClick={() => start.mutate()}
            >
              {start.isPending ? "Starting…" : "Start value week"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function VerdictBadge({ status }: { status: ValueWeekStatus }) {
  if (!status.start) {
    return (
      <Badge variant="secondary" tone="muted">
        not started
      </Badge>
    );
  }
  if (!status.active) {
    return (
      <Badge variant="secondary" tone="muted">
        finished
      </Badge>
    );
  }
  return (
    <Badge
      variant="secondary"
      tone={status.verdict === "on track" ? "success" : "blocked"}
    >
      {status.verdict}
    </Badge>
  );
}

function RateSection({ status }: { status: ValueWeekStatus }) {
  const pct = Math.round(status.response_rate * 100);
  const ok = status.response_rate >= OK_RATE;
  return (
    <>
      <div className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between gap-4">
          <p className="text-sm font-medium">Response rate</p>
          <p className="text-sm tabular-nums">
            {status.acted} acted{" "}
            <span className="text-muted-foreground">of {status.sent} sent</span>
            <span className="ml-2 font-medium">{pct}%</span>
          </p>
        </div>
        <Progress
          className={cn(
            "h-2",
            ok
              ? "[&>[data-slot=progress-indicator]]:bg-status-success"
              : "[&>[data-slot=progress-indicator]]:bg-status-blocked",
          )}
          value={pct}
          aria-label="Share of sent items the owner acted on"
        />
        <p className="text-muted-foreground text-xs">
          Target: at least 50%.
          {status.sent < 5 ? " Fewer than 5 items sent, so the verdict is not yet meaningful." : ""}
        </p>
      </div>
      <DayStrip days={status.per_day} />
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
        <Stat label="Started" value={status.start ?? "–"} />
        <Stat label="Days left" value={String(status.days_left)} />
        <Stat label="Vault recalls" value={String(status.recall_queries ?? 0)} />
        <Stat label="Your questions" value={String(status.owner_questions ?? 0)} />
        <Stat label="Sent" value={String(status.sent)} />
        <Stat
          label="Pending over 24h"
          value={String(status.tickets_pending_over_24h)}
          warn={status.tickets_pending_over_24h > 0}
        />
      </dl>
    </>
  );
}

/** Seven cells, one per day of the week: "acted/sent". Days not reached
 * yet are dashed. Tone: nothing sent = muted, at least half acted on =
 * success, otherwise blocked. */
function DayStrip({ days }: { days: ValueWeekDay[] }) {
  const cells = Array.from({ length: WEEK_DAYS }, (_, i) => days[i] ?? null);
  return (
    <ol
      aria-label="Sent and acted per day"
      className="grid grid-cols-7 gap-1"
    >
      {cells.map((day, i) => {
        const tone = !day
          ? "border-dashed text-muted-foreground"
          : day.sent === 0
            ? "bg-muted text-muted-foreground"
            : day.acted / day.sent >= OK_RATE
              ? "bg-status-success/15 text-status-success"
              : "bg-status-blocked/15 text-status-blocked";
        const label = day
          ? `${day.date}: ${day.acted} acted of ${day.sent} sent`
          : `Day ${i + 1}: not yet`;
        return (
          <li
            key={day?.date ?? `day-${i}`}
            title={label}
            aria-label={label}
            className={cn(
              "flex flex-col items-center rounded-md border px-1 py-1 text-xs tabular-nums",
              tone,
            )}
          >
            <span className="font-medium">
              {day ? `${day.acted}/${day.sent}` : "–"}
            </span>
            <span className="text-muted-foreground text-[10px]">D{i + 1}</span>
          </li>
        );
      })}
    </ol>
  );
}

function Stat({
  label,
  value,
  warn = false,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className={cn("tabular-nums", warn && "text-status-blocked")}>
        {value}
      </dd>
    </div>
  );
}
