"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, X } from "lucide-react";

import { GenerateVideo } from "@/components/features/courses/generate-video";
import { VideoPanel } from "@/components/features/learn/video-panel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  formatDuration,
  lessonVideoComplete,
  mediaApi,
  mediaKeys,
  partLabel,
  sortVideos,
  type Video,
} from "@/lib/api/media";
import { cn } from "@/lib/utils";

/**
 * The videos made from one phase, above its lesson.
 *
 * Closed, it is one row: the course video (or its parts, about ten minutes
 * each, when the lesson is told as a series) and the phase's short YouTube
 * episodes. The lesson frame keeps the height, because the lesson is still
 * the thing he reads. Opening a video puts the player above the lesson, and
 * the same row switches between the videos. The frame itself is not touched:
 * its sandbox and policy stay as they are, and the video comes from the
 * console's API or a YouTube embed.
 *
 * Most phases have no video, and then this renders nothing. An empty state
 * on every such phase would be noise, not information. The exception is a
 * phase with a written lesson and no course video: it gets "Generate video"
 * (`GenerateVideo`), the only way a video is made, which also shows the
 * job's state while it is made and "Generate again" when it stopped.
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
  const courseVideos = list.filter((v) => v.kind === "course");
  const episodes = list.filter((v) => v.kind === "youtube");
  const current = list.find((v) => v.id === playing);

  const generate = lessonMd ? (
    <GenerateVideo
      lessonMd={lessonMd}
      mode="course"
      hasVideo={lessonVideoComplete(courseVideos)}
    />
  ) : null;

  if (!list.length) {
    if (!generate) return null;
    return (
      <section aria-label="Video for this phase" className="shrink-0">
        {generate}
      </section>
    );
  }

  return (
    <section aria-label="Videos for this phase" className="shrink-0 space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {courseVideos.map((video) => (
          <Button
            key={video.id}
            size="sm"
            variant={current?.id === video.id ? "default" : "secondary"}
            onClick={() => setPlaying(video.id)}
            title={video.title}
          >
            <Play aria-hidden className="size-3.5" />
            {partLabel(video) ? `Part ${video.part}` : "Watch the course video"}
            <span className="tabular-nums opacity-80">
              · {formatDuration(video.duration_s)}
            </span>
          </Button>
        ))}
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
        {generate}
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
            {partLabel(current) ? `${partLabel(current)} · ` : ""}
            {current.title}
          </p>
          <VideoPanel key={current.id} video={current} />
        </div>
      ) : null}
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
