"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "@/components/error-state";
import { Marker } from "@/components/features/reader/playlist";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  isRead as isShelfItemRead,
  progressOf,
  shelfOf,
  type Shelf,
} from "@/lib/reader-shelves";
import { cn } from "@/lib/utils";
import { useConceptTaps } from "@/hooks/use-concept-taps";
import { useReaderSync } from "@/hooks/use-reader-sync";
import {
  byConcept,
  VERDICT_LABEL,
  type ConceptVerdict,
} from "@/lib/concept-taps";
import { loadTaps, pageSlug, readerApi, readerKeys, saveTap } from "@/lib/reader";
import {
  markedReadHere,
  READER_SYNC_URL,
  sendRead,
  sendTap,
  type SyncStatus,
} from "@/lib/reader-sync";

/**
 * One lesson on the phone.
 *
 * The frame contract is the console's, unchanged and non-negotiable:
 * `sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"` with
 * NO same-origin, fed through `srcDoc`. The page is model-written markup, and
 * on this origin it would be markup running inside the deployment. The export
 * already put the content policy and `<base target="_blank">` inside the
 * document, the same two walls the API endpoint adds, because here there is
 * no endpoint to add them.
 *
 * Never point the tab straight at `/reader/lessons/<slug>.html`. That file is
 * served from this origin, so opening it directly is exactly the same-origin
 * rendering the sandbox exists to prevent.
 *
 * "Got it" / "Lost me" under each concept arrive as messages from the frame,
 * checked by `useConceptTaps`, and are kept in THIS page's storage (the frame
 * has none). They, and "Mark read" under the lesson, also go to the backend
 * through `lib/reader-sync.ts`: no credential, only his tailnet identity, and
 * an outbox on this phone for whenever the backend is out of reach. The frame
 * itself never sends anything; this page does, from its own origin.
 */
export default function ReadLessonPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const file = `${slug}.html`;
  const page = useQuery({
    queryKey: readerKeys.page(slug),
    queryFn: () => readerApi.page(slug),
    staleTime: 60_000,
  });
  // The library's index (cached when he came from there) knows what was
  // already read at the last export.
  const index = useQuery({
    queryKey: readerKeys.index,
    queryFn: readerApi.index,
    staleTime: 60_000,
  });
  const frame = useRef<HTMLIFrameElement>(null);
  const [verdicts, setVerdicts] = useState<Record<string, ConceptVerdict>>(
    () => loadTaps(slug),
  );
  const [sync, setSync] = useState<SyncStatus | "saving" | null>(null);
  const [readHere, setReadHere] = useState(() => markedReadHere(file));
  const readAtExport = Boolean(
    index.data &&
      [
        ...index.data.courses.flatMap((c) => c.phases),
        ...index.data.articles,
      ].some((l) => l.file === file && l.read),
  );
  const isRead = readHere || readAtExport;

  const track = (sending: Promise<SyncStatus>) => {
    setSync("saving");
    void sending.then(setSync);
  };
  useReaderSync((waiting) => {
    if (waiting > 0) setSync((now) => now ?? "will sync");
  });
  useConceptTaps(frame, verdicts, ({ concept, verdict }) => {
    saveTap(slug, concept, verdict);
    setVerdicts((prev) => ({ ...prev, [concept]: verdict }));
    track(sendTap(file, concept, verdict));
  });
  const answered = Object.keys(verdicts).sort(byConcept);
  const shelf = index.data ? shelfOf(index.data, file) : null;
  const at = shelf ? shelf.items.findIndex((i) => i.file === file) : -1;
  const prev = shelf && at > 0 ? shelf.items[at - 1] : null;
  const next = shelf && at >= 0 && at < shelf.items.length - 1 ? shelf.items[at + 1] : null;

  return (
    <div className="flex h-dvh flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b px-2 py-2">
        <Link
          href={shelf ? `/read#${encodeURIComponent(shelf.key)}` : "/read"}
          className="hover:bg-accent text-muted-foreground flex shrink-0 items-center gap-1 rounded-md px-2 py-1.5 text-sm"
        >
          <ChevronLeft aria-hidden className="size-4" />
          Library
        </Link>
        {shelf ? (
          <p className="text-muted-foreground min-w-0 truncate px-1 text-xs lg:hidden">
            {shelf.title} · {at + 1} of {shelf.items.length}
          </p>
        ) : null}
        {page.data && answered.length ? (
          <p
            className="text-muted-foreground ml-auto truncate px-2 text-xs"
            title="Your answers, kept on this phone"
          >
            {answered
              .map((c) => `${c} ${VERDICT_LABEL[verdicts[c]].toLowerCase()}`)
              .join(" · ")}
          </p>
        ) : null}
      </div>

      <div className="reader-lesson flex-1">
        {shelf ? <PlaylistRail shelf={shelf} file={file} readHere={readHere} /> : <div className="hidden lg:block" />}
        <div className="flex min-h-0 flex-col lg:col-start-2">
          {page.isPending ? (
            <Skeleton className="m-4 flex-1" />
          ) : page.isError ? (
            <div className="p-4">
              <ErrorState
                message={(page.error as Error).message}
                onRetry={() => void page.refetch()}
                retrying={page.isRefetching}
              />
            </div>
          ) : (
            <>
              <iframe
                ref={frame}
                title="Lesson"
                srcDoc={page.data}
                sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
                className="bg-background w-full flex-1 border-0"
              />
              <div className="flex shrink-0 items-center gap-2 border-t px-3 py-2">
                {prev ? (
                  <Button asChild variant="ghost" size="sm">
                    <Link href={`/read/${pageSlug(prev.file)}`} title={prev.title}>
                      <ChevronLeft aria-hidden data-icon="inline-start" />
                      Previous
                    </Link>
                  </Button>
                ) : null}
                {next ? (
                  <Button asChild variant="ghost" size="sm">
                    <Link href={`/read/${pageSlug(next.file)}`} title={next.title}>
                      Next
                      <ChevronRight aria-hidden data-icon="inline-end" />
                    </Link>
                  </Button>
                ) : null}
                <span className="flex-1" />
                {sync ? (
                  <p
                    className="text-muted-foreground text-xs"
                    title={SYNC_HINT[sync]}
                    aria-live="polite"
                  >
                    {sync}
                  </p>
                ) : null}
                <Button
                  variant={isRead ? "outline" : "default"}
                  onClick={() => {
                    setReadHere(true);
                    track(sendRead(file));
                  }}
                >
                  {isRead ? <Check aria-hidden /> : null}
                  {isRead ? "Read" : "Mark read"}
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** The course this lesson belongs to, as a playlist beside it. Wide screens only. */
function PlaylistRail({ shelf, file, readHere }: { shelf: Shelf; file: string; readHere: boolean }) {
  const current = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    current.current?.scrollIntoView({ block: "nearest" });
  }, [file]);
  const { done, total, percent } = progressOf(shelf, readHere ? file : undefined);
  return (
    <aside className="hidden min-h-0 flex-col border-r lg:flex">
      <div className="shrink-0 space-y-2 border-b px-4 py-3">
        <p className="text-sm leading-snug font-semibold">{shelf.title}</p>
        <div className="flex items-center gap-2">
          <Progress value={percent} />
          <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
            {done}/{total}
          </span>
        </div>
      </div>
      <ol className="min-h-0 flex-1 overflow-y-auto py-1">
        {shelf.items.map((item) => {
          const here = item.file === file;
          return (
            <li key={item.file}>
              <Link
                ref={here ? current : undefined}
                href={`/read/${pageSlug(item.file)}`}
                aria-current={here ? "page" : undefined}
                className={cn(
                  "flex items-start gap-2.5 px-4 py-2.5 text-sm leading-snug transition-colors",
                  here ? "bg-accent font-medium" : "text-muted-foreground hover:bg-accent/50",
                )}
              >
                <Marker item={item} read={isShelfItemRead(item) || (here && readHere)} current={here} />
                <span className="min-w-0 pt-1">{item.title}</span>
              </Link>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

/** The longer word behind the tiny status, for a long-press or hover. */
const SYNC_HINT: Record<SyncStatus | "saving", string> = {
  saving: "Sending to Mission HQ",
  saved: "Mission HQ has it",
  "will sync": READER_SYNC_URL
    ? "Kept on this phone; sent once it can reach Mission HQ on your tailnet"
    : "Kept on this phone; this deployment has no sync address yet",
  refused: "Mission HQ has no lesson for this page, so it was not recorded",
};
