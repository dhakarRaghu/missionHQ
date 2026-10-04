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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, qk } from "@/lib/api/client";
import { JOB_STATUSES, type Job, type JobStatus, type PipelineDue } from "@/lib/api/types";
import { timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * The job search in three views: found, applied, closed.
 *
 * Hunter finds and scores roles; he applies, finds the people and writes
 * every message himself. Applied keeps the follow-up clock: 7 days with no
 * reply is a follow-up, and after two touches the role closes as ghosted.
 * No agent applies, drafts or sends.
 */
const VIEWS: { key: string; label: string; statuses: JobStatus[] }[] = [
  { key: "found", label: "Found", statuses: ["seen", "shortlisted", "referral"] },
  { key: "applied", label: "Applied", statuses: ["applied", "interviewing", "offer"] },
  { key: "closed", label: "Closed", statuses: ["rejected", "ghosted", "closed"] },
];

export function JobBoard() {
  const [view, setView] = useState("found");
  const jobs = useQuery({ queryKey: qk.jobs(), queryFn: () => api.jobs() });
  const due = useQuery({ queryKey: qk.pipelineDue(), queryFn: () => api.pipelineDue() });

  const byView = useMemo(() => {
    const out: Record<string, Job[]> = {};
    for (const v of VIEWS) out[v.key] = (jobs.data ?? []).filter((j) => v.statuses.includes(j.status));
    return out;
  }, [jobs.data]);

  if (jobs.isLoading) {
    return (
      <div className="job-grid" role="status" aria-busy="true" aria-label="Loading roles">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-48 w-full" />
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

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <DueToday due={due.data} onOpen={setView} />
      <Tabs value={view} onValueChange={setView}>
        <TabsList>
          {VIEWS.map((v) => (
            <TabsTrigger key={v.key} value={v.key} className="text-xs">
              {v.label}
              <span className="text-muted-foreground ml-1 tabular-nums">
                {byView[v.key]?.length ?? 0}
              </span>
            </TabsTrigger>
          ))}
        </TabsList>
        {VIEWS.map((v) => (
          <TabsContent key={v.key} value={v.key}>
            {v.key === "found" ? (
              <FoundView rows={byView.found ?? []} />
            ) : (
              <PipelineView rows={byView[v.key] ?? []} view={v.key} />
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

/** What waits on him today, by the follow-up clock. */
function DueToday({
  due,
  onOpen,
}: {
  due: PipelineDue | undefined;
  onOpen: (view: string) => void;
}) {
  const follow = due?.follow_ups ?? [];
  if (!follow.length) return null;
  return (
    <section className="bg-card flex flex-col gap-1 rounded-lg border p-3 text-xs" aria-label="Due today">
      <p className="text-sm font-medium">Due today</p>
      {follow.map((f) => (
        <button key={f.id} type="button" className="text-left hover:underline" onClick={() => onOpen("applied")}>
          Follow up with {f.company} on {f.role} (touch {f.touches + 1} of 2)
        </button>
      ))}
    </section>
  );
}

function FoundView({ rows: found }: { rows: Job[] }) {
  const [bucket, setBucket] = useState<string>("all");
  const rows = bucket === "all" ? found : found.filter((j) => j.fit_bucket === bucket);
  if (!found.length) {
    return (
      <EmptyState title="No roles found this week">
        Hunter adds the roles it verifies and scores here. Roles found more than
        a week ago are cleared from the board.
      </EmptyState>
    );
  }
  const strong = found.filter((j) => j.fit_bucket === "strong").length;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-muted-foreground text-sm">
          {found.length} role{found.length === 1 ? "" : "s"} found this week
          {strong > 0 ? `, ${strong} a strong fit` : ""}
        </p>
        <Select value={bucket} onValueChange={setBucket}>
          <SelectTrigger size="sm" className="ml-auto w-40" aria-label="Filter by fit">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Every fit</SelectItem>
            <SelectItem value="strong">Strong only</SelectItem>
            <SelectItem value="decent">Decent</SelectItem>
            <SelectItem value="stretch">Stretch</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {rows.length === 0 ? (
        <p className="text-muted-foreground rounded-lg border border-dashed px-3 py-6 text-center text-xs">
          No role this week has that fit.
        </p>
      ) : (
        <ul className="job-grid">
          {rows.map((job) => (
            <li key={job.id}>
              <JobCard job={job} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const EMPTY_VIEW: Record<string, string> = {
  applied: "Mark a role applied when you apply. A follow-up comes due after 7 days; after two touches with no reply, the role closes as ghosted. Interviews and offers stay here.",
  closed: "Rejected, ghosted and closed roles land here.",
};

function PipelineView({ rows, view }: { rows: Job[]; view: string }) {
  if (!rows.length) {
    return <p className="text-muted-foreground rounded-lg border border-dashed px-3 py-6 text-center text-xs">{EMPTY_VIEW[view]}</p>;
  }
  return (
    <ul className="job-grid">
      {rows.map((job) => (
        <li key={job.id}>
          <JobCard job={job} />
        </li>
      ))}
    </ul>
  );
}

const FIT_PART_ORDER = ["lane", "years", "stack", "domain", "pay", "geography", "adjust"];

/**
 * The score's reasons, on hover. The score is computed from the row's fields,
 * so each point it gained or lost is named rather than asserted.
 */
function fitTitle(job: Job): string {
  const parts = job.fit_parts ?? {};
  const moved = FIT_PART_ORDER.flatMap((key) => {
    const part = parts[key];
    if (!part || typeof part !== "object" || !part.points) return [];
    const sign = part.points > 0 ? "+" : "";
    const why = part.note ?? part.lane ?? part.reason ?? "";
    return [`${key} ${sign}${part.points}${why ? ` (${why})` : ""}`];
  });
  const head = `${job.fit_bucket} fit`;
  return moved.length ? `${head}: base 5, ${moved.join(", ")}` : head;
}

type PayPart = { lakh?: number | null; estimated?: boolean; note?: string };
type YearsPart = { floor?: number | null; note?: string };
type MatchPart = { matched?: string[] };

function part<T>(job: Job, key: string): T | undefined {
  const value = job.fit_parts?.[key];
  return value && typeof value === "object" ? (value as T) : undefined;
}

/** Pay as the score read it: stated, estimated, or unknown, never prose. */
function payChip(job: Job): { label: string; stated: boolean; known: boolean; title: string } {
  const pay = part<PayPart>(job, "pay");
  const title = job.compensation || job.pay_signal || pay?.note || "No package named anywhere";
  if (pay?.lakh) {
    return pay.estimated
      ? { label: `~${pay.lakh} LPA est.`, stated: false, known: true, title }
      : { label: `${pay.lakh} LPA`, stated: true, known: true, title };
  }
  return { label: "pay unknown", stated: false, known: false, title };
}

/** The experience floor the gate read, not the sentence it came from. */
function yearsChip(job: Job): string | null {
  const years = part<YearsPart>(job, "years");
  if (years?.floor !== undefined && years.floor !== null) {
    return years.floor === 0 ? "no years floor" : `${years.floor}+ yrs`;
  }
  if (years?.note === "early career") return "early career";
  return job.experience_band ? "years not stated" : null;
}

/** Why the score is what it is, in a few words: the parts that moved it. */
function fitReasons(job: Job): string {
  const out: string[] = [];
  const lane = part<{ lane?: string }>(job, "lane")?.lane;
  if (lane && lane !== "none") out.push(`${lane.replace("_", " ")} lane`);
  const years = part<YearsPart>(job, "years")?.note;
  if (years && years !== "not stated") out.push(years);
  const stack = part<MatchPart>(job, "stack")?.matched ?? [];
  if (stack.length) out.push(stack.slice(0, 2).join(", "));
  const domain = part<MatchPart>(job, "domain")?.matched ?? [];
  if (domain.length) out.push(domain[0]);
  const pay = payChip(job);
  out.push(pay.stated ? "pay stated" : pay.known ? "pay estimated" : "pay unknown");
  return out.join(" · ");
}

const BUCKET_TONE: Record<Job["fit_bucket"], string> = {
  strong: "bg-status-done/15 text-status-done",
  decent: "bg-status-running/15 text-status-running",
  stretch: "bg-status-muted/20 text-muted-foreground",
};

function JobCard({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  // qk.jobs() and qk.pipelineDue() share the "jobs" prefix.
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["jobs"] });
  const move = useMutation({
    mutationFn: (status: JobStatus) => api.updateJob(job.id, { status }),
    onSuccess: (_result, status) => {
      toast(`${job.company} moved to ${status}`);
      refresh();
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const followed = useMutation({
    mutationFn: () => api.jobFollowedUp(job.id),
    onSuccess: (r) => {
      toast(`Follow-up recorded (touch ${r.touches} of 2)`);
      refresh();
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const found = job.status === "seen" || job.status === "shortlisted" || job.status === "referral";

  return (
    <article className="bg-card flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm font-medium" title={job.role}>
            {job.role}
          </p>
          <p className="text-muted-foreground text-xs" title={job.company}>
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
          </p>
          {/* The score's reasons in words, so a 10 can be trusted or doubted
              at a glance; the full breakdown stays on the score's hover. */}
          <p className="text-muted-foreground mt-0.5 line-clamp-2 text-[11px]" title={fitTitle(job)}>
            {fitReasons(job)}
          </p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-md px-1.5 py-0.5 text-xs font-medium tabular-nums",
            BUCKET_TONE[job.fit_bucket],
          )}
          title={fitTitle(job)}
        >
          {job.fit_score}
        </span>
      </div>

      {/* Every long field is clamped, with the full text on hover. A card is a
          thing you scan a column of; one that runs to twenty lines because the
          agent wrote a good paragraph pushes the next role off the screen, and
          the column stops being scannable at all. */}
      {job.next_step ? (
        <p className="line-clamp-2 text-xs" title={job.next_step}>
          <span className="text-muted-foreground">Next: </span>
          {job.next_step}
        </p>
      ) : null}

      {job.why_fit ? (
        <p
          className="text-muted-foreground border-border line-clamp-3 border-l-2 pl-2 text-xs"
          title={job.why_fit}
        >
          {job.why_fit}
        </p>
      ) : null}

      {job.company_brief || job.role_brief || job.stack || job.referral ? (
        <details className="group text-xs">
          <summary className="text-muted-foreground hover:text-foreground cursor-pointer list-none select-none">
            <span className="group-open:hidden">More about the role</span>
            <span className="hidden group-open:inline">Less</span>
          </summary>
          <div className="mt-1.5 flex flex-col gap-1.5">
          {job.referral ? (
            <p className="line-clamp-3 text-xs" title={job.referral}>
              <span className="text-foreground font-medium">Referral: </span>
              {job.referral}
            </p>
          ) : null}
          {/* The company dig. He is employed, so "is this worth leaving for" is
              the real question and a title cannot answer it. Absent on a weak fit
              by design — hunter only digs at 6+. */}
          {job.company_brief ? (
            <p
              className="text-muted-foreground line-clamp-2 text-xs"
              title={job.company_brief}
            >
              <span className="text-foreground font-medium">Company: </span>
              {job.company_brief}
            </p>
          ) : null}

          {job.role_brief ? (
            <p
              className="text-muted-foreground line-clamp-2 text-xs"
              title={job.role_brief}
            >
              <span className="text-foreground font-medium">Day to day: </span>
              {job.role_brief}
            </p>
          ) : null}

          {job.stack ? (
            <p className="text-muted-foreground truncate text-xs" title={job.stack}>
              {job.stack}
            </p>
          ) : null}
          </div>
        </details>
      ) : null}

      <div className="flex flex-wrap items-center gap-1">
        {yearsChip(job) ? (
          <Badge variant="secondary" className="text-xs" title={job.experience_band}>
            {yearsChip(job)}
          </Badge>
        ) : null}
        {job.remote_policy ? (
          <Badge variant="secondary" className="text-xs" title={job.remote_policy}>
            {job.remote_policy}
          </Badge>
        ) : null}
        {/* Always rendered. A blank package is the thing worth chasing, so an
            unstated one has to be visible rather than simply absent. */}
        {(() => {
          const pay = payChip(job);
          return (
            <Badge
              variant={pay.known ? "secondary" : "outline"}
              tone={pay.stated ? "success" : undefined}
              className={cn("text-xs", !pay.known && "text-muted-foreground border-dashed")}
              title={pay.title}
            >
              {pay.label}
            </Badge>
          );
        })()}
        {job.channel ? (
          <Badge variant="outline" className="text-xs" title={job.source}>
            {job.channel}
          </Badge>
        ) : null}
        {job.seen_count > 1 ? (
          <span className="text-muted-foreground text-xs">
            {job.seen_count}x
          </span>
        ) : null}
      </div>

      {job.applied_at ? (
        <p className="text-xs">
          <span className="text-muted-foreground">Applied </span>
          <span title={new Date(job.applied_at).toLocaleString()}>{timeAgo(job.applied_at)}</span>
          {job.status === "applied" && job.followup_due ? (
            <span className="text-muted-foreground">
              {" · "}
              {job.touches >= 2
                ? `closes as ghosted on ${job.followup_due} if no reply`
                : `follow-up due ${job.followup_due} (touch ${job.touches + 1} of 2)`}
            </span>
          ) : null}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          asChild
          size="sm"
          variant="outline"
          className="h-7 px-2 text-xs"
        >
          {/* The LinkedIn post when there is one — the owner applies from
              LinkedIn, and asked for that link rather than the company's
              portal. A role hunter found straight on an ATS board has no
              LinkedIn post, so it keeps its original link. */}
          <a
            href={job.linkedin_url || job.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {job.linkedin_url ? "LinkedIn" : "Open"}
            <ExternalLink aria-hidden className="size-3" />
          </a>
        </Button>
        {found ? (
          <Button size="sm" className="h-7 px-2 text-xs"
            disabled={move.isPending} onClick={() => move.mutate("applied")}>
            Mark applied
          </Button>
        ) : null}
        {job.status === "applied" && job.touches < 2 ? (
          <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
            disabled={followed.isPending} onClick={() => followed.mutate()}>
            Followed up
          </Button>
        ) : null}
        {/* Off the badge row, so the time never reads as a field. */}
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
            {JOB_STATUSES.map((status) => (
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
