"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Clapperboard, RotateCcw } from "lucide-react";

import { VideoJobSheet } from "@/components/features/courses/video-job-sheet";
import { JobStateBadge, useVideoJobs } from "@/components/features/courses/video-jobs";
import { Button } from "@/components/ui/button";
import { mediaApi, mediaKeys, type VideoJobState } from "@/lib/api/media";

/** The states in which the lesson's video can be asked for again. */
const STOPPED: readonly VideoJobState[] = ["failed", "script_ready"];

/**
 * "Generate video" for one lesson (a course phase or an article).
 *
 * Nothing makes a video by itself, so this button is how one starts. While a
 * job for the lesson exists, its state is a chip that opens the job. A
 * stopped job keeps its chip and gets "Generate again" beside it; when its
 * script passed every check, that builds the same script again ("Build
 * again"), which takes a render, not hours of writing. With a video already
 * made (`hasVideo`), only a job in progress is shown.
 */
export function GenerateVideo({
  lessonMd,
  mode,
  hasVideo = false,
}: {
  lessonMd: string;
  mode: "course" | "article";
  hasVideo?: boolean;
}) {
  const queryClient = useQueryClient();
  const [openJob, setOpenJob] = useState<string | null>(null);
  const make = useMutation({
    mutationFn: () => mediaApi.makeVideo(lessonMd, mode),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: mediaKeys.jobs });
      if (data.started && data.video_id) setOpenJob(data.video_id);
    },
  });
  // The job file is written when the task starts, not when it is queued, so
  // after a first press the list is polled until the job appears.
  const started = make.data?.started ? make.data.video_id : undefined;
  const jobs = useVideoJobs({ expecting: Boolean(started) });

  // Nothing is offered until the jobs are known: a button that flashes and
  // turns into a state chip misleads.
  if (!jobs.isSuccess) return null;
  const job = jobs.data.find((j) => j.lesson_md === lessonMd && j.state !== "built");
  const jobId = job?.id ?? started;
  if (hasVideo && !job) return null;

  const stopped = job ? STOPPED.includes(job.state) : false;
  const offer = !hasVideo && (job ? stopped : !started);
  const label = job ? (job.can_rebuild ? "Build again" : "Generate again") : "Generate video";
  const title = !job
    ? `Make a narrated video of this ${mode === "article" ? "article" : "phase"}: the script is written, reviewed, voiced and rendered on its own.`
    : job.can_rebuild
      ? "The script passed every check; build the video from it again."
      : "Write the script again from the lesson, then build the video.";

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        {jobId ? (
          <button
            type="button"
            onClick={() => setOpenJob(jobId)}
            title="Open the video job"
            className="flex cursor-pointer items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs transition-colors hover:bg-muted"
          >
            <Clapperboard aria-hidden className="size-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Video</span>
            {job ? (
              <JobStateBadge state={job.state} />
            ) : (
              <span className="text-muted-foreground">· queued</span>
            )}
          </button>
        ) : null}
        {offer ? (
          <Button
            size="sm"
            variant={job ? "secondary" : "outline"}
            disabled={make.isPending}
            onClick={() => make.mutate()}
            title={title}
          >
            {job ? (
              <RotateCcw aria-hidden className="size-3.5" />
            ) : (
              <Clapperboard aria-hidden className="size-3.5" />
            )}
            {make.isPending ? "Starting…" : label}
          </Button>
        ) : null}
      </div>
      {make.isError ? (
        <p role="alert" className="text-xs text-destructive">
          Could not start the video: {(make.error as Error).message}
        </p>
      ) : make.data && !make.data.started ? (
        <p className="text-xs text-muted-foreground">{make.data.reason}</p>
      ) : null}
      <VideoJobSheet jobId={openJob} onClose={() => setOpenJob(null)} />
    </div>
  );
}
