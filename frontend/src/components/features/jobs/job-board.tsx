"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import { JOB_STATUSES, type Job, type JobStatus } from "@/lib/api/types";
import { timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

const ACTIVE_COLUMNS: { key: JobStatus; label: string; hint: string }[] = [
  {
    key: "seen",
    label: "Found",
    hint: "Verified and scored in the last two days. Strong fits stay; the rest close themselves.",
  },
  { key: "shortlisted", label: "Shortlisted", hint: "Worth applying to." },
  {
    key: "referral",
    label: "Referral",
    hint: "Waiting on a person. Operator looks one up when you shortlist.",
  },
  { key: "applied", label: "Applied", hint: "Sent. Waiting." },
];

/**
 * "interviewing" is deliberately absent. The owner tracks that himself, and a
 * column that is always empty costs the three that are not a quarter of the
 * width each. The status still exists in the API and in the ledger, so a row
 * already in it is not orphaned — it simply is not a stage of this board.
 */
const HIDDEN_STATUSES: ReadonlySet<string> = new Set(["interviewing"]);

const OUTCOME_COLUMNS: { key: JobStatus; label: string; hint: string }[] = [
  { key: "offer", label: "Offers", hint: "Offers will appear here." },
  { key: "rejected", label: "Rejected", hint: "Rejected roles stay searchable." },
  { key: "closed", label: "Closed", hint: "Expired or closed roles stay in the ledger." },
];

/**
 * The job search, as one board.
 *
 * Hunter writes every verified role here with a score and a reason, including
 * the weak ones, because a role written down once is never researched twice.
 * The owner moves it along; nothing else does. No agent can apply to anything.
 */
export function JobBoard() {
  const [bucket, setBucket] = useState<string>("all");
  const [statusView, setStatusView] = useState<"active" | "outcomes">("active");
  const jobs = useQuery({ queryKey: qk.jobs(), queryFn: () => api.jobs() });
  const columns = statusView === "active" ? ACTIVE_COLUMNS : OUTCOME_COLUMNS;

  const rows = useMemo(() => {
    const all = jobs.data ?? [];
    return bucket === "all" ? all : all.filter((j) => j.fit_bucket === bucket);
  }, [jobs.data, bucket]);

  if (jobs.isLoading) {
    return (
      <div
        className="board-columns"
        role="status"
        aria-busy="true"
        aria-label="Loading roles"
      >
        {ACTIVE_COLUMNS.map((c) => (
          <Skeleton key={c.key} className="h-64 w-full" />
        ))}
      </div>
    );
  }
  if (jobs.isError) {
    return (
      <ErrorState
        message={jobs.error.message}
        onRetry={() => jobs.refetch()}
        retrying={jobs.isFetching}
      />
    );
  }
  if (!(jobs.data ?? []).length) {
    return (
      <EmptyState title="No roles yet">
        Ask Sage to find roles matching your profile—no company or platform is
        required. Operator discovers them in your signed-in browser, then
        Hunter verifies, scores and deduplicates each original posting here.
      </EmptyState>
    );
  }

  const strong = (jobs.data ?? []).filter(
    (j) => j.fit_bucket === "strong",
  ).length;

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-muted-foreground text-sm">
          {jobs.data?.length} role{jobs.data?.length === 1 ? "" : "s"} tracked
          {strong > 0 ? `, ${strong} a strong fit` : ""}
        </p>
        <Select value={bucket} onValueChange={setBucket}>
          <SelectTrigger
            size="sm"
            className="ml-auto w-40"
            aria-label="Filter by fit"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Every fit</SelectItem>
            <SelectItem value="strong">Strong only</SelectItem>
            <SelectItem value="decent">Decent</SelectItem>
            <SelectItem value="stretch">Stretch</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={statusView}
          onValueChange={(value) => setStatusView(value as "active" | "outcomes")}
        >
          <SelectTrigger size="sm" className="w-40" aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="active">Active pipeline</SelectItem>
            <SelectItem value="outcomes">Outcomes</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="board-columns">
        {columns.map((column) => {
          const items = rows.filter((j) => j.status === column.key);
          return (
            <section key={column.key} className="flex min-w-0 flex-col gap-2">
              <header className="flex items-baseline gap-2">
                <h2 className="text-sm font-medium">{column.label}</h2>
                <span className="text-muted-foreground text-xs">
                  {items.length}
                </span>
              </header>
              {items.length === 0 ? (
                <p className="text-muted-foreground rounded-lg border border-dashed px-3 py-6 text-center text-xs">
                  {column.hint}
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {items.map((job) => (
                    <li key={job.id}>
                      <JobCard job={job} />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

const BUCKET_TONE: Record<Job["fit_bucket"], string> = {
  strong: "bg-status-done/15 text-status-done",
  decent: "bg-status-running/15 text-status-running",
  stretch: "bg-status-muted/20 text-muted-foreground",
};

function JobCard({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const move = useMutation({
    mutationFn: (status: JobStatus) => api.updateJob(job.id, { status }),
    onSuccess: (result, status) => {
      toast(
        `${job.company} moved to ${status}`,
        result.referral_task_id
          ? { description: "Operator is looking for a referral path in your signed-in browser." }
          : undefined,
      );
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <article className="bg-card flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={job.role}>
            {job.role}
          </p>
          <p
            className="text-muted-foreground truncate text-xs"
            title={job.company}
          >
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
          </p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-md px-1.5 py-0.5 text-xs font-medium tabular-nums",
            BUCKET_TONE[job.fit_bucket],
          )}
          title={`${job.fit_bucket} fit`}
        >
          {job.fit_score}
        </span>
      </div>

      {/* Every long field is clamped, with the full text on hover. A card is a
          thing you scan a column of; one that runs to twenty lines because the
          agent wrote a good paragraph pushes the next role off the screen, and
          the column stops being scannable at all. */}
      {job.why_fit ? (
        <p
          className="text-muted-foreground border-border line-clamp-3 border-l-2 pl-2 text-xs"
          title={job.why_fit}
        >
          {job.why_fit}
        </p>
      ) : null}

      {job.referral ? (
        <p className="line-clamp-2 text-xs" title={job.referral}>
          <span className="text-muted-foreground">Referral: </span>
          {job.referral}
        </p>
      ) : null}

      {job.next_step ? (
        <p className="line-clamp-2 text-xs" title={job.next_step}>
          <span className="text-muted-foreground">Next: </span>
          {job.next_step}
        </p>
      ) : null}

      {job.stack ? (
        <p className="text-muted-foreground truncate text-xs" title={job.stack}>
          {job.stack}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-1">
        {/* max-w keeps a verbose band ("early career explicitly welcomed")
            from taking a whole row to itself and pushing the rest to the next. */}
        {job.experience_band ? (
          <Badge
            variant="secondary"
            className="max-w-36 truncate text-xs"
            title={job.experience_band}
          >
            {job.experience_band}
          </Badge>
        ) : null}
        {job.remote_policy ? (
          <Badge
            variant="secondary"
            className="max-w-24 truncate text-xs"
            title={job.remote_policy}
          >
            {job.remote_policy}
          </Badge>
        ) : null}
        {/* Always rendered. A blank package is the thing worth chasing, so an
            unstated one has to be visible rather than simply absent. */}
        <Badge
          variant={job.compensation ? "secondary" : "outline"}
          className={cn(
            "max-w-36 truncate text-xs",
            !job.compensation && "text-muted-foreground",
          )}
          title={job.compensation || "No package on the posting — check Levels/Glassdoor"}
        >
          {job.compensation || "no package"}
        </Badge>
        {job.seen_count > 1 ? (
          <span className="text-muted-foreground text-xs">
            {job.seen_count}x
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          asChild
          size="sm"
          variant="outline"
          className="h-7 px-2 text-xs"
        >
          <a href={job.url} target="_blank" rel="noopener noreferrer">
            Open <ExternalLink aria-hidden className="size-3" />
          </a>
        </Button>
        {/* Moved down here off the badge row: with four columns the badges
            wrap, and a timestamp pushed onto its own line read as a field. */}
        <span
          className="text-muted-foreground order-last ml-auto text-xs"
          title={new Date(job.last_seen).toLocaleString()}
        >
          {timeAgo(job.last_seen)}
        </span>
        <Select
          value={job.status}
          onValueChange={(value) => move.mutate(value as JobStatus)}
          disabled={move.isPending}
        >
          <SelectTrigger
            size="sm"
            className="h-7 w-auto text-xs"
            aria-label={`Status of ${job.role} at ${job.company}`}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {JOB_STATUSES.filter((s) => !HIDDEN_STATUSES.has(s)).map((status) => (
              <SelectItem key={status} value={status}>
                {status}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </article>
  );
}
