"use client";

import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";

import { courseTitle } from "@/components/features/courses/course-format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Course } from "@/lib/api/learning";
import {
  ACTIVE_JOB_STATES,
  mediaApi,
  mediaKeys,
  partLabel,
  type VideoJobRow,
  type VideoJobState,
} from "@/lib/api/media";
import { exactTime, timeAgo } from "@/lib/time";

/** How often the list is read while a task works on a job. */
const JOB_POLL_MS = 30_000;

/**
 * Every video job, newest first.
 *
 * A job lives in a file on the backend, and writing that file sends no event
 * on the stream, so the list polls every 30 seconds while a task is working
 * on one (writing, approved, building). When no job moves, it stops. When a
 * job reaches "built", the video manifest has a new entry, so the library's
 * list is read again.
 */
export function useVideoJobs({
  enabled = true,
  expecting = false,
}: {
  enabled?: boolean;
  /** A job was just started and its file may not exist yet: poll anyway. */
  expecting?: boolean;
} = {}) {
  const queryClient = useQueryClient();
  const jobs = useQuery({
    queryKey: mediaKeys.jobs,
    queryFn: () => mediaApi.jobs(),
    enabled,
    refetchInterval: (query) =>
      expecting || query.state.data?.some((job) => isActive(job.state))
        ? JOB_POLL_MS
        : false,
  });

  const built = jobs.data
    ?.filter((job) => job.state === "built")
    .map((job) => job.id)
    .join(",");
  const seen = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (built === undefined) return;
    if (seen.current !== undefined && seen.current !== built) {
      void queryClient.invalidateQueries({ queryKey: ["media", "videos"] });
    }
    seen.current = built;
  }, [built, queryClient]);

  return jobs;
}

export function isActive(state: VideoJobState): boolean {
  return ACTIVE_JOB_STATES.includes(state);
}

const STATE_LABEL: Record<VideoJobState, string> = {
  queued: "queued",
  writing: "writing script",
  script_ready: "script only",
  approved: "approved, queued",
  building: "building",
  built: "built",
  failed: "failed",
};

const STATE_TONE: Record<
  VideoJobState,
  "running" | "approval" | "success" | "danger" | "muted"
> = {
  queued: "running",
  writing: "running",
  script_ready: "muted",
  approved: "running",
  building: "running",
  built: "success",
  failed: "danger",
};

/** The job's state as a chip. "Failed" is the one that waits for him. */
export function JobStateBadge({ state }: { state: VideoJobState }) {
  return (
    <Badge variant="secondary" tone={STATE_TONE[state]} className="shrink-0">
      {STATE_LABEL[state]}
    </Badge>
  );
}

/** "about 24 min", from the script while it is a script, from the file once built. */
export function jobMinutes(job: {
  duration_s: number;
  minutes?: number;
}): string {
  if (job.duration_s > 0) return `${Math.round(job.duration_s / 60)} min`;
  if (job.minutes) return `about ${Math.round(job.minutes)} min`;
  return "";
}

/**
 * Top of the video library: the videos still on their way, and the stopped
 * ones.
 *
 * One row per job that is not built. A built job is a video in the library
 * below, so it is not listed twice. Clicking a row opens the job, with its
 * notes and, for a stopped one, "Generate again".
 */
export function VideosBeingMade({
  courses,
  onOpenJob,
}: {
  courses: Course[];
  onOpenJob: (id: string) => void;
}) {
  const jobs = useVideoJobs();

  let body: React.ReactNode;
  if (jobs.isPending) {
    body = <Skeleton className="mt-1 h-10 w-full" />;
  } else if (jobs.isError) {
    body = (
      <div role="alert" className="mt-1 flex items-center gap-2 px-1.5 text-xs text-destructive">
        <span className="min-w-0 break-words">
          Could not load the video jobs: {(jobs.error as Error).message}
        </span>
        <Button size="sm" variant="outline" onClick={() => void jobs.refetch()}>
          Retry
        </Button>
      </div>
    );
  } else {
    const waiting = jobs.data.filter((job) => job.state !== "built");
    body = waiting.length ? (
      <ol className="mt-1 space-y-0.5">
        {waiting.map((job) => (
          <li key={job.id}>
            <JobRow job={job} courses={courses} onOpen={() => onOpenJob(job.id)} />
          </li>
        ))}
      </ol>
    ) : (
      <p className="mt-1 px-1.5 text-xs text-muted-foreground">
        Nothing is being made. Videos are made only when you ask: press
        “Generate video” on a phase or an article.
      </p>
    );
  }

  return (
    <section aria-label="Being made">
      <h3 className="px-1.5 text-xs font-medium text-muted-foreground">Being made</h3>
      {body}
    </section>
  );
}

function JobRow({
  job,
  courses,
  onOpen,
}: {
  job: VideoJobRow;
  courses: Course[];
  onOpen: () => void;
}) {
  const course = courses.find((c) => c.course === job.course);
  const meta = [
    course ? courseTitle(course) : job.course,
    job.part === 0 && job.parts ? `${job.parts} parts` : partLabel(job),
    jobMinutes(job),
  ].filter(Boolean);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full cursor-pointer items-center gap-3 rounded-md p-1.5 text-left transition-colors hover:bg-muted"
    >
      <JobStateBadge state={job.state} />
      <span className="min-w-0 flex-1">
        <span className="line-clamp-1 text-sm leading-snug font-medium">
          {job.title || job.id}
        </span>
        {meta.length ? (
          <span className="block truncate text-xs text-muted-foreground">
            {meta.join(" · ")}
          </span>
        ) : null}
      </span>
      <span
        className="shrink-0 text-xs text-muted-foreground"
        title={exactTime(job.updated)}
      >
        {timeAgo(job.updated)}
      </span>
      <ChevronRight aria-hidden className="size-4 shrink-0 text-muted-foreground" />
    </button>
  );
}
