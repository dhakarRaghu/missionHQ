"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  formatTime,
  mediaApi,
  mediaKeys,
  mediaUrl,
  type Video,
} from "@/lib/api/media";
import { hasRemoteApi } from "@/lib/auth";
import { cn } from "@/lib/utils";

const YOUTUBE_ORIGIN = "https://www.youtube-nocookie.com";

/**
 * One course video: the player, its captions, its chapters, and the field
 * that links it to a private YouTube upload.
 *
 * Two sources. The videos stay on this machine, in the backend's media
 * folder, and the native `<video controls>` plays them: the backend answers
 * Range requests, so seeking jumps straight to the byte it needs, and
 * `preload="metadata"` reads only the head of a file that can be 1 GB and
 * shows the first frame. There is no poster image: the owner is the only
 * viewer. When he uploads a video to YouTube as a private video and pastes
 * its link here, the YouTube embed plays instead (youtube-nocookie), and the
 * chapters seek it through the IFrame API's postMessage commands.
 *
 * The local URLs are signed, because a `<video>` cannot send the
 * Authorization header. They are kept from the first render: a list refetch
 * signs new ones every hour, and swapping the `src` of a playing video
 * restarts it. A link that has expired fails to load; "Reload" signs fresh
 * ones and returns to the same second.
 *
 * Callers give it `key={video.id}`, so switching videos starts a new player.
 */
export function VideoPanel({
  video,
  size = "compact",
  className,
}: {
  video: Video;
  /** "compact" sits above a lesson; "large" is the video library. */
  size?: "compact" | "large";
  className?: string;
}) {
  const player = useRef<HTMLVideoElement>(null);
  const embed = useRef<HTMLIFrameElement>(null);
  const resumeAt = useRef(0);
  const queryClient = useQueryClient();
  const [urls, setUrls] = useState(video.urls);
  const [failed, setFailed] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [active, setActive] = useState(0);

  const youtubeId = video.youtube_id;
  const chapters = video.chapters;
  const height = size === "large" ? "max-h-[62vh]" : "max-h-[44vh]";

  /** One command to the YouTube player inside the embed. */
  const command = (func: string, args: unknown[] = []) => {
    embed.current?.contentWindow?.postMessage(
      JSON.stringify({ event: "command", func, args }),
      YOUTUBE_ORIGIN,
    );
  };

  const seek = (index: number) => {
    const seconds = chapters[index].t;
    setActive(index);
    if (youtubeId) {
      command("seekTo", [seconds, true]);
      command("playVideo");
      return;
    }
    const el = player.current;
    if (!el) return;
    el.currentTime = seconds;
    // Autoplay rules may refuse play() before he has pressed anything;
    // the seek has still happened, so there is nothing to report.
    void el.play().catch(() => undefined);
  };

  const onTime = () => {
    const el = player.current;
    if (!el) return;
    resumeAt.current = el.currentTime;
    let index = 0;
    for (let i = 0; i < chapters.length; i += 1) {
      if (chapters[i].t <= el.currentTime) index = i;
    }
    if (index !== active) setActive(index);
  };

  // Sign the links again and load the same second. Within the same hour the
  // backend signs the same URL, so an unchanged source is loaded again by hand.
  const reload = async () => {
    setReloading(true);
    await queryClient.refetchQueries({ queryKey: mediaKeys.all });
    const fresh = queryClient
      .getQueriesData<Video[]>({ queryKey: mediaKeys.all })
      .flatMap(([, rows]) => rows ?? [])
      .find((row) => row.id === video.id);
    setReloading(false);
    setFailed(false);
    if (fresh && fresh.urls.video !== urls.video) setUrls(fresh.urls);
    else player.current?.load();
  };

  let screen: React.ReactNode;
  if (youtubeId) {
    screen = (
      <iframe
        ref={embed}
        title={video.title}
        src={`${YOUTUBE_ORIGIN}/embed/${encodeURIComponent(youtubeId)}?enablejsapi=1&rel=0`}
        allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
        allowFullScreen
        // YouTube refuses to play an embed that sends no referrer.
        referrerPolicy="strict-origin-when-cross-origin"
        // allow-same-origin here is YouTube's own origin, not the console's:
        // the frame is cross-origin, so it still cannot reach this page, its
        // token or its storage. Unrelated to the lesson frame and its rules.
        sandbox="allow-scripts allow-same-origin allow-presentation allow-popups allow-popups-to-escape-sandbox"
        className={cn("aspect-video w-full rounded-md border bg-muted", height)}
      />
    );
  } else if (video.available && urls.video) {
    screen = (
      <>
        <video
          key={urls.video}
          ref={player}
          controls
          preload="metadata"
          playsInline
          // A remote API is another origin, and a caption track from another
          // origin loads only in CORS mode. Same origin needs nothing.
          crossOrigin={hasRemoteApi() ? "anonymous" : undefined}
          // On the element, not a <source> child: an error on a <source>
          // never reaches the video's own error handler.
          src={mediaUrl(urls.video)}
          onTimeUpdate={onTime}
          onLoadedMetadata={() => {
            const el = player.current;
            if (el && resumeAt.current > 0) el.currentTime = resumeAt.current;
          }}
          onError={() => setFailed(true)}
          className={cn("aspect-video w-full rounded-md border bg-muted", height)}
        >
          {urls.captions ? (
            <track
              kind="captions"
              src={mediaUrl(urls.captions)}
              srcLang="en"
              label="English"
              default
            />
          ) : null}
        </video>
        {failed ? (
          <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-destructive">
            <span>
              The video did not load. Its link may have expired, or the
              backend is not reachable.
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void reload()}
              disabled={reloading}
            >
              <RefreshCw aria-hidden className="size-3.5" />
              {reloading ? "Reloading…" : "Reload"}
            </Button>
          </div>
        ) : null}
      </>
    );
  } else {
    screen = (
      <p className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
        The file for this video is not on this machine. The list comes from
        git; the video files live in the backend&apos;s media folder.
      </p>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex flex-col gap-3 lg:flex-row">
        <div className="min-w-0 space-y-1 lg:flex-1">{screen}</div>

        {chapters.length ? (
          <nav
            aria-label="Chapters"
            className={cn("shrink-0 overflow-y-auto overscroll-contain lg:w-64", height)}
          >
            <ol className="space-y-0.5">
              {chapters.map((chapter, i) => (
                <li key={`${chapter.t}-${chapter.title}`}>
                  <button
                    type="button"
                    onClick={() => seek(i)}
                    aria-current={i === active ? "true" : undefined}
                    className={cn(
                      "flex w-full cursor-pointer gap-2 rounded-md px-2 py-1 text-left text-sm transition-colors",
                      i === active ? "bg-accent text-accent-foreground" : "hover:bg-muted",
                    )}
                  >
                    <span className="w-11 shrink-0 pt-px text-xs tabular-nums text-muted-foreground">
                      {formatTime(chapter.t)}
                    </span>
                    <span className="min-w-0 leading-snug">{chapter.title}</span>
                  </button>
                </li>
              ))}
            </ol>
          </nav>
        ) : null}
      </div>

      <YoutubeLink key={youtubeId ?? ""} video={video} />
    </div>
  );
}

/**
 * The owner's link from this video to its private YouTube upload. Saving a
 * URL or an id makes the panel play the embed; "Use the local file" clears it.
 */
function YoutubeLink({ video }: { video: Video }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState(video.youtube_id ?? "");
  const save = useMutation({
    mutationFn: (value: string | null) => mediaApi.setYoutubeId(video.id, value),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: mediaKeys.all }),
  });
  const inputId = `youtube-${video.id}`;

  return (
    <form
      className="flex flex-wrap items-center gap-1.5"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(text.trim() || null);
      }}
    >
      <label htmlFor={inputId} className="text-xs text-muted-foreground">
        YouTube link
      </label>
      <Input
        id={inputId}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="URL or id of a private upload"
        className="h-7 max-w-72 min-w-40 flex-1 text-xs md:text-xs"
      />
      <Button
        type="submit"
        size="sm"
        variant="outline"
        disabled={save.isPending || text.trim() === (video.youtube_id ?? "")}
      >
        {save.isPending ? "Saving…" : "Save"}
      </Button>
      {video.youtube_id ? (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={save.isPending}
          onClick={() => save.mutate(null)}
        >
          Use the local file
        </Button>
      ) : null}
      {save.isError ? (
        <span role="alert" className="text-xs text-destructive">
          {(save.error as Error).message}
        </span>
      ) : null}
    </form>
  );
}
