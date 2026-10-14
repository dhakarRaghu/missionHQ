"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, X } from "lucide-react";

import { GenerateVideo } from "@/components/features/courses/generate-video";
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
 * An article with no video (`canMake`) gets "Generate video", the only way
 * one is made, which then shows the job while it is made and "Generate
 * again" when it stopped. A lab card or a week review gets no video, so for
 * those this renders nothing.
 */
export function LessonVideo({ lessonMd, canMake }: { lessonMd: string; canMake: boolean }) {
  const videos = useQuery({
    queryKey: mediaKeys.videos(FILTER),
    queryFn: () => mediaApi.videos(FILTER),
    staleTime: 10 * 60_000,
  });
  const [open, setOpen] = useState(false);

  const video = videos.data?.find((v) => v.source_lesson === lessonMd);

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

  // Nothing is offered until the video list is known: a "Generate video"
  // that flashes and turns into a player misleads.
  if (!canMake || !videos.isSuccess) return null;
  return (
    <section aria-label="Video of this article" className="shrink-0">
      <GenerateVideo lessonMd={lessonMd} mode="article" />
    </section>
  );
}
