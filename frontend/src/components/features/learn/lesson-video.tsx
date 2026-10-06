"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clapperboard, Play, X } from "lucide-react";

import { VideoJobSheet } from "@/components/features/courses/video-job-sheet";
import { JobStateBadge, useVideoJobs } from "@/components/features/courses/video-jobs";
import { VideoPanel } from "@/components/features/learn/video-panel";
import { Button } from "@/components/ui/button";
import { formatDuration, mediaApi, mediaKeys } from "@/lib/api/media";

const FILTER = { kind: "article" };

/**
 * The video made from one Learn article, above the article.
 *
 * The same row as a course phase's videos, for one video: closed, it is one
 * button, and opening it puts the player above the page. The video is found
 * by the lesson file it was made from (`source_lesson`), because an article
 * has no phase of its own.
 *
 * An article with no video shows the job while one is being made. With no
 * job, an article (`canMake`) gets "Make video"; the nightly backfill makes
 * the same video without it. A lab card or a week review gets no video, so
 * for those this renders nothing.
 */
export function LessonVideo({ lessonMd, canMake }: { lessonMd: string; canMake: boolean }) {
  const videos = useQuery({
    queryKey: mediaKeys.videos(FILTER),
    queryFn: () => mediaApi.videos(FILTER),
    staleTime: 10 * 60_000,
  });
  const [open, setOpen] = useState(false);
  const [openJob, setOpenJob] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const make = useMutation({
    mutationFn: () => mediaApi.makeVideo(lessonMd, "article"),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: mediaKeys.jobs });
      if (data.video_id) setOpenJob(data.video_id);
    },
  });
  const started = make.data?.video_id;
  const jobs = useVideoJobs({ enabled: canMake, expecting: Boolean(started) });

  const video = videos.data?.find((v) => v.source_lesson === lessonMd);
  const job = jobs.data?.find((j) => j.lesson_md === lessonMd && j.state !== "built");
  const jobId = video ? undefined : (job?.id ?? started);
  const sheet = <VideoJobSheet jobId={openJob} onClose={() => setOpenJob(null)} />;

  if (video) {
    return (
      <section aria-label="Video of this article" className="shrink-0 space-y-2">
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={open ? "default" : "secondary"}
            onClick={() => setOpen(true)}
            title={video.title}
          >
            <Play aria-hidden className="size-3.5" />
            Watch the video
            <span className="tabular-nums opacity-80">
              · {formatDuration(video.duration_s)}
            </span>
          </Button>
          {open ? (
            <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setOpen(false)}>
              <X aria-hidden className="size-3.5" />
              Close video
            </Button>
          ) : null}
        </div>
        {open ? <VideoPanel key={video.id} video={video} /> : null}
      </section>
    );
  }

  // Nothing is offered until both lists are known: a "Make video" that
  // flashes and turns into a state chip misleads.
  if (!canMake || !videos.isSuccess || !jobs.isSuccess) return null;
  return (
    <section aria-label="Video of this article" className="shrink-0 space-y-1">
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
      ) : (
        <Button
          size="sm"
          variant="outline"
          disabled={make.isPending}
          onClick={() => make.mutate()}
          title="Make a narrated video of this article. It is written, reviewed and built on its own."
        >
          <Clapperboard aria-hidden className="size-3.5" />
          {make.isPending ? "Starting…" : "Make video"}
        </Button>
      )}
      {make.isError ? (
        <p role="alert" className="text-xs text-destructive">
          Could not start the video: {(make.error as Error).message}
        </p>
      ) : make.data && !make.data.started ? (
        <p className="text-xs text-muted-foreground">{make.data.reason}</p>
      ) : null}
      {sheet}
    </section>
  );
}
