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
import {
  JOB_STATUSES,
  REFERRAL_STATUSES,
  type Job,
  type JobStatus,
  type Referral,
  type ReferralStatus,
} from "@/lib/api/types";
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
    hint: "People you can ask, read off the company's own page. Shortlist a role and operator goes looking.",
  },
  { key: "applied", label: "Applied", hint: "Sent. Waiting." },
];

/**
 * Interviews sit with the outcomes rather than in the active pipeline: the
 * active view keeps its four columns at a quarter width each, and a role in
 * interview is past everything an agent does for it. Every status is a choice
 * on every card, so a role can be moved to any stage from either view.
 */
const OUTCOME_COLUMNS: { key: JobStatus; label: string; hint: string }[] = [
  { key: "interviewing", label: "Interviewing", hint: "Roles you are interviewing for." },
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
          <SelectTrigger size="sm" className="w-52" aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="active">Active pipeline</SelectItem>
            <SelectItem value="outcomes">Interviews and outcomes</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="board-columns">
        {columns.map((column) =>
          // The referral column is the odd one out: it holds people, not
          // roles. "Who can I ask?" is a different question from "which job is
          // at which stage", and answering it with a job card meant the answer
          // — a name — was a clause inside a sentence on the back of a card.
          column.key === "referral" ? (
            <ReferralColumn key={column.key} column={column} />
          ) : (
            <BoardColumn
              key={column.key}
              column={column}
              items={rows.filter((j) => j.status === column.key)}
            />
          ),
        )}
      </div>
    </div>
  );
}

type Column = { key: JobStatus; label: string; hint: string };

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

/** A column of roles. */
function BoardColumn({ column, items }: { column: Column; items: Job[] }) {
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <ColumnHeader label={column.label} count={items.length} />
      {items.length === 0 ? (
        <ColumnEmpty>{column.hint}</ColumnEmpty>
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
}

function ColumnHeader({ label, count }: { label: string; count: number }) {
  return (
    <header className="flex items-baseline gap-2">
      <h2 className="text-sm font-medium">{label}</h2>
      <span className="text-muted-foreground text-xs tabular-nums">{count}</span>
    </header>
  );
}

function ColumnEmpty({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-muted-foreground rounded-lg border border-dashed px-3 py-6 text-center text-xs">
      {children}
    </p>
  );
}

/** How usable a person is, which is the only order worth showing them in. */
const DEGREE_LABEL: Record<Referral["degree"], string> = {
  "1st": "1st — knows you",
  "2nd": "2nd",
  "3rd": "3rd",
  none: "no connection",
  persona: "who to look for",
  unknown: "unverified",
};

/**
 * The people to ask, not the roles waiting on them.
 *
 * Operator reads one company's own people page and returns names; this is
 * where they land. Ordered by degree server-side, because a 1st-degree
 * connection who already knows the owner is worth every other lead put
 * together, and burying them under a newer 3rd-degree find would waste the
 * only thing that makes a referral better than a cold application.
 */
function ReferralColumn({ column }: { column: Column }) {
  const referrals = useQuery({
    queryKey: qk.referrals(),
    queryFn: () => api.referrals(),
  });
  const rows = (referrals.data ?? []).filter((r) => r.status !== "dismissed");

  return (
    <section className="flex min-w-0 flex-col gap-2">
      <ColumnHeader label={column.label} count={rows.length} />
      {referrals.isError ? (
        <ColumnEmpty>Could not load people. Retry from the page.</ColumnEmpty>
      ) : rows.length === 0 ? (
        <ColumnEmpty>{column.hint}</ColumnEmpty>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((person) => (
            <li key={person.id}>
              <ReferralCard person={person} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ReferralCard({ person }: { person: Referral }) {
  const queryClient = useQueryClient();
  const move = useMutation({
    mutationFn: (status: ReferralStatus) =>
      api.updateReferral(person.id, { status }),
    onSuccess: (_result, status) => {
      toast(`${person.name} marked ${status}`);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const isPersona = person.degree === "persona";

  return (
    <article className="bg-card flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={person.name}>
            {person.name}
          </p>
          {person.headline ? (
            <p
              className="text-muted-foreground line-clamp-2 text-xs"
              title={person.headline}
            >
              {person.headline}
            </p>
          ) : null}
        </div>
        <Badge
          variant={person.degree === "1st" ? "default" : "secondary"}
          className="max-w-28 shrink-0 truncate text-xs"
          title={DEGREE_LABEL[person.degree]}
        >
          {DEGREE_LABEL[person.degree]}
        </Badge>
      </div>

      {/* Which role this person is for. Without it a name is just a name. */}
      <p className="text-muted-foreground truncate text-xs" title={person.job_role}>
        for {person.job_role} @ {person.company}
      </p>

      {person.shared_ground ? (
        <p
          className="border-border line-clamp-3 border-l-2 pl-2 text-xs"
          title={person.shared_ground}
        >
          <span className="text-muted-foreground">Open with: </span>
          {person.shared_ground}
        </p>
      ) : null}

      {person.why_them ? (
        <p className="text-muted-foreground line-clamp-2 text-xs" title={person.why_them}>
          {person.why_them}
        </p>
      ) : null}

      {person.mutuals ? (
        <p className="text-muted-foreground truncate text-xs" title={person.mutuals}>
          {person.mutuals}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-1.5">
        {person.profile_url ? (
          <Button asChild size="sm" variant="outline" className="h-7 px-2 text-xs">
            <a href={person.profile_url} target="_blank" rel="noopener noreferrer">
              Profile <ExternalLink aria-hidden className="size-3" />
            </a>
          </Button>
        ) : null}
        <Button asChild size="sm" variant="ghost" className="h-7 px-2 text-xs">
          <a href={person.job_url} target="_blank" rel="noopener noreferrer">
            Role <ExternalLink aria-hidden className="size-3" />
          </a>
        </Button>
        {/* A persona is not a person, so there is nobody to mark as asked. */}
        {isPersona ? null : (
          <Select
            value={person.status}
            onValueChange={(value) => move.mutate(value as ReferralStatus)}
            disabled={move.isPending}
          >
            <SelectTrigger
              size="sm"
              className="h-7 w-auto text-xs"
              aria-label={`Status of ${person.name}`}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {REFERRAL_STATUSES.map((status) => (
                <SelectItem key={status} value={status}>
                  {status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>
    </article>
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
          {/* The score's reasons in words, so a 10 can be trusted or doubted
              at a glance; the full breakdown stays on the score's hover. */}
          <p className="text-muted-foreground mt-0.5 truncate text-[11px]" title={fitTitle(job)}>
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
          className="text-muted-foreground border-border line-clamp-2 border-l-2 pl-2 text-xs"
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
        {/* max-w keeps a verbose band ("early career explicitly welcomed")
            from taking a whole row to itself and pushing the rest to the next. */}
        {yearsChip(job) ? (
          <Badge variant="secondary" className="text-xs" title={job.experience_band}>
            {yearsChip(job)}
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
