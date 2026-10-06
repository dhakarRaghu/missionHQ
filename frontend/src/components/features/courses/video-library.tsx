"use client";

import { useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, Play } from "lucide-react";

import { courseTitle, slugPhaseLabel } from "@/components/features/courses/course-format";
import { VideoJobSheet } from "@/components/features/courses/video-job-sheet";
import { VideosBeingMade } from "@/components/features/courses/video-jobs";
import { VideoPanel } from "@/components/features/learn/video-panel";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Course } from "@/lib/api/learning";
import {
  formatDuration,
  mediaApi,
  mediaKeys,
  sortVideos,
  type Video,
} from "@/lib/api/media";
import { cn } from "@/lib/utils";

/**
 * Centre pane: every video, by course.
 *
 * Each course lists its long course videos in phase order, then its YouTube
 * playlist in episode order. Picking one plays it at the top of the pane;
 * "Open the phase" goes to the lesson it was made from.
 *
 * Above the library, "Being made" lists the videos still on their way, and a
 * row opens that job in a right-hand panel. /courses?view=videos&job=<id>
 * opens one job directly.
 */
export function VideoLibrary({
  courses,
  onBack,
  onOpenPhase,
}: {
  courses: Course[];
  onBack: () => void;
  onOpenPhase: (course: string, slug: string) => void;
}) {
  const filter = { kind: "course,youtube" };
  const videos = useQuery({
    queryKey: mediaKeys.videos(filter),
    queryFn: () => mediaApi.videos(filter),
    staleTime: 10 * 60_000,
  });
  const [playing, setPlaying] = useState<string | null>(null);
  const params = useSearchParams();
  const [openJob, setOpenJob] = useState<string | null>(() => params.get("job"));
  const pane = useRef<HTMLDivElement>(null);

  const list = sortVideos(videos.data ?? []);
  const current = list.find((v) => v.id === playing);
  const play = (id: string) => {
    setPlaying(id);
    pane.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <section aria-label="Videos" className="reader-pane flex min-h-0 flex-col gap-3">
      <header className="flex shrink-0 flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          Videos{videos.data ? ` · ${videos.data.length}` : ""}
        </span>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onBack}>
          <ArrowLeft aria-hidden className="size-3.5" />
          Back to the course
        </Button>
      </header>

      <div ref={pane} className="pane-scroll space-y-6 border-t pt-3">
        <VideosBeingMade courses={courses} onOpenJob={setOpenJob} />

        {videos.isPending ? (
          <Skeleton className="h-48 w-full" />
        ) : videos.isError ? (
          <ErrorState
            message={(videos.error as Error).message}
            onRetry={() => void videos.refetch()}
          />
        ) : !list.length ? (
          <EmptyState title="No videos yet">
            A video appears here when its build finishes, or once it is added
            to learning/videos/index.json and its file is in the backend&apos;s
            media folder.
          </EmptyState>
        ) : (
          <>
            {current ? (
              <div className="space-y-2">
                <div className="flex flex-wrap items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium leading-snug">
                      {current.number ? `#${current.number} · ` : ""}
                      {current.title}
                    </p>
                    <p className="text-xs text-muted-foreground">{meta(current)}</p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onOpenPhase(current.course, current.phase_slug)}
                  >
                    <BookOpen aria-hidden className="size-3.5" />
                    Open the phase
                  </Button>
                </div>
                <VideoPanel key={current.id} video={current} size="large" />
              </div>
            ) : null}

            {byCourse(list).map(([key, group]) => {
              const course = courses.find((c) => c.course === key);
              const long = group.filter((v) => v.kind === "course");
              const episodes = group.filter((v) => v.kind === "youtube");
              return (
                <section key={key} aria-label={course ? courseTitle(course) : key} className="space-y-3">
                  <h3 className="text-sm font-semibold">{course ? courseTitle(course) : key}</h3>
                  {long.length ? (
                    <VideoList
                      title="Course videos"
                      videos={long}
                      playing={playing}
                      onPlay={play}
                    />
                  ) : null}
                  {episodes.length ? (
                    <VideoList
                      title="YouTube playlist"
                      videos={episodes}
                      playing={playing}
                      onPlay={play}
                    />
                  ) : null}
                </section>
              );
            })}
          </>
        )}
      </div>

      <VideoJobSheet jobId={openJob} onClose={() => setOpenJob(null)} />
    </section>
  );
}

function VideoList({
  title,
  videos,
  playing,
  onPlay,
}: {
  title: string;
  videos: Video[];
  playing: string | null;
  onPlay: (id: string) => void;
}) {
  return (
    <div>
      <h4 className="px-1.5 text-xs font-medium text-muted-foreground">{title}</h4>
      <ol className="mt-1 grid gap-1 md:grid-cols-2">
        {videos.map((video) => (
          <li key={video.id}>
            <button
              type="button"
              onClick={() => onPlay(video.id)}
              aria-current={video.id === playing ? "true" : undefined}
              className={cn(
                "flex w-full cursor-pointer gap-3 rounded-md p-1.5 text-left transition-colors",
                video.id === playing ? "bg-accent text-accent-foreground" : "hover:bg-muted",
              )}
            >
              <Play aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1">
                <span className="line-clamp-2 text-sm leading-snug font-medium">
                  {video.number ? `#${video.number} · ` : ""}
                  {video.title}
                </span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  {meta(video)}
                </span>
                {video.available ? null : (
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    File not on this machine
                  </span>
                )}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** "Phase 2A, 2B · 28 min · 14 chapters" */
function meta(video: Video): string {
  const labels = video.phase_slugs
    .map((slug) => slugPhaseLabel(slug))
    .filter((label): label is string => Boolean(label));
  const parts = [
    labels.length ? `Phase ${labels.join(", ")}` : "",
    formatDuration(video.duration_s),
    video.chapters.length ? `${video.chapters.length} chapters` : "",
  ];
  return parts.filter(Boolean).join(" · ");
}

/** The videos grouped by course, in the order each course first appears. */
function byCourse(videos: Video[]): [string, Video[]][] {
  const out = new Map<string, Video[]>();
  for (const video of videos) {
    const group = out.get(video.course);
    if (group) group.push(video);
    else out.set(video.course, [video]);
  }
  return [...out.entries()];
}
