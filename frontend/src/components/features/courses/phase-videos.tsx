"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clapperboard, Play, X } from "lucide-react";

import { VideoJobSheet } from "@/components/features/courses/video-job-sheet";
import { JobStateBadge, useVideoJobs } from "@/components/features/courses/video-jobs";
import { VideoPanel } from "@/components/features/learn/video-panel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  formatDuration,
  mediaApi,
  mediaKeys,
  sortVideos,
  type Video,
} from "@/lib/api/media";
import { cn } from "@/lib/utils";

/**
 * The videos made from one phase, above its lesson.
 *
 * Closed, it is one row: the course video and the phase's short YouTube
 * episodes. The lesson frame keeps the height, because the lesson is still
 * the thing he reads. Opening a video puts the player above the lesson, and
 * the same row switches between the videos. The frame itself is not touched:
 * its sandbox and policy stay as they are, and the video comes from the
 * console's API or a YouTube embed.
 *
 * Most phases have no video, and then this renders nothing. An empty state
 * on every such phase would be noise, not information. The exception is a
 * phase with a written lesson and no course video: it gets one small button.
 * While a job for the lesson exists, the button is the job's state and opens
 * it; with no job, it is "Make video", which starts the script and opens the
 * job. Videos are made on their own after a lesson is written, so the button
 * is for a lesson from before that, or one whose job was removed.
 */
export function PhaseVideos({
  course,
  phaseSlug,
  lessonMd,
}: {
  course: string;
  phaseSlug: string;
  /** The phase's lesson (`learning/lessons/*.md`), when one is written. */
  lessonMd?: string | null;
}) {
  const filter = { course, phase: phaseSlug, kind: "course,youtube" };
  const videos = useQuery({
    queryKey: mediaKeys.videos(filter),
    queryFn: () => mediaApi.videos(filter),
    // The manifest changes when a video is added, not while he reads.
    staleTime: 10 * 60_000,
  });
  const [playing, setPlaying] = useState<string | null>(null);
  const [openJob, setOpenJob] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const make = useMutation({
    mutationFn: (path: string) => mediaApi.makeVideo(path),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: mediaKeys.jobs });
      if (data.video_id) setOpenJob(data.video_id);
    },
  });
  // The job file is written when the script task starts, not when it is
  // queued, so after "Make video" the list is polled until it appears.
  const started = make.data?.video_id;
  const jobs = useVideoJobs({ enabled: Boolean(lessonMd), expecting: Boolean(started) });

  if (videos.isPending) return <Skeleton className="h-8 w-full shrink-0" />;
  if (videos.isError) {
    return (
      <div role="alert" className="flex shrink-0 items-center gap-2 text-xs text-destructive">
        <span>Could not load the videos for this phase: {(videos.error as Error).message}</span>
        <Button size="sm" variant="outline" onClick={() => void videos.refetch()}>
          Retry
        </Button>
      </div>
    );
  }
  const list = sortVideos(videos.data);
  const courseVideo = list.find((v) => v.kind === "course");
  const episodes = list.filter((v) => v.kind === "youtube");
  const current = list.find((v) => v.id === playing);

  // The lesson's job, if one exists. A built job is a video in the list, so
  // only one still on its way is shown. Nothing is offered until the jobs are
  // known: a "Make video" that flashes and turns into a state chip misleads.
  const job = lessonMd
    ? jobs.data?.find((j) => j.lesson_md === lessonMd && j.state !== "built")
    : undefined;
  const canMake =
    Boolean(lessonMd) && !courseVideo && jobs.isSuccess && !job && !started;
  const jobId = job?.id ?? (courseVideo ? undefined : started);
  const jobControl = jobId ? (
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
  ) : canMake && lessonMd ? (
    <Button
      size="sm"
      variant="outline"
      disabled={make.isPending}
      onClick={() => make.mutate(lessonMd)}
      title="Write a narrated video of this lesson. You review the script before it is built."
    >
      <Clapperboard aria-hidden className="size-3.5" />
      {make.isPending ? "Starting…" : "Make video"}
    </Button>
  ) : null;
  const makeNote = make.isError ? (
    <p role="alert" className="text-xs text-destructive">
      Could not start the video: {(make.error as Error).message}
    </p>
  ) : make.data && !make.data.started ? (
    <p className="text-xs text-muted-foreground">{make.data.reason}</p>
  ) : null;
  const sheet = <VideoJobSheet jobId={openJob} onClose={() => setOpenJob(null)} />;

  if (!list.length) {
    if (!jobControl && !makeNote && !openJob) return null;
    return (
      <section aria-label="Video for this phase" className="shrink-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">{jobControl}</div>
        {makeNote}
        {sheet}
      </section>
    );
  }

  return (
    <section aria-label="Videos for this phase" className="shrink-0 space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {courseVideo ? (
          <Button
            size="sm"
            variant={current?.id === courseVideo.id ? "default" : "secondary"}
            onClick={() => setPlaying(courseVideo.id)}
            title={courseVideo.title}
          >
            <Play aria-hidden className="size-3.5" />
            Watch the course video
            <span className="tabular-nums opacity-80">
              · {formatDuration(courseVideo.duration_s)}
            </span>
          </Button>
        ) : null}
        {episodes.length ? (
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">
              Short episodes on this phase:
            </span>
            {episodes.map((episode) => (
              <EpisodeChip
                key={episode.id}
                episode={episode}
                current={episode.id === current?.id}
                onPlay={() => setPlaying(episode.id)}
              />
            ))}
          </div>
        ) : null}
        {jobControl}
        {current ? (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => setPlaying(null)}
          >
            <X aria-hidden className="size-3.5" />
            Close video
          </Button>
        ) : null}
      </div>

      {current ? (
        <div className="space-y-1">
          <p className="text-sm font-medium">
            {current.number ? `#${current.number} · ` : ""}
            {current.title}
          </p>
          <VideoPanel key={current.id} video={current} />
        </div>
      ) : null}
      {makeNote}
      {sheet}
    </section>
  );
}

function EpisodeChip({
  episode,
  current,
  onPlay,
}: {
  episode: Video;
  current: boolean;
  onPlay: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPlay}
      aria-current={current ? "true" : undefined}
      title={`#${episode.number} · ${episode.title} (${formatDuration(episode.duration_s)})`}
      className={cn(
        "flex max-w-64 cursor-pointer items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors",
        current ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
      )}
    >
      <span className="shrink-0 font-medium tabular-nums">#{episode.number}</span>
      <span className="truncate">{episode.title}</span>
    </button>
  );
}
