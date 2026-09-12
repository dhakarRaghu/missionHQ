"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, FileText, Maximize2, PanelsTopLeft, Plus, X } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Markdown } from "@/components/features/vault/markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { learningApi, learningKeys } from "@/lib/api/learning";
import { exactTime, timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * One lesson a day, given the whole window.
 *
 * The first version put the lesson in a `.console-split` right pane, so a
 * single-card list took a third of the width and the lesson read through a
 * letterbox. The lesson IS this page: everything else — picking an older day,
 * asking for a subject, the source links — collapses into one slim row.
 *
 * The page renders in a frame with `sandbox="allow-scripts"` and no
 * same-origin: tutor writes that HTML from digests of pages nobody vetted,
 * and this console holds the token that can start agents. `allow-popups` is
 * there so a source link opens a real tab — without it the link either does
 * nothing or, as happened on 2026-09-12, navigates the frame itself and the
 * live site appears inside the console.
 */
export function LearnView() {
  const queryClient = useQueryClient();
  const markRead = useMutation({
    mutationFn: (l: { lesson_date: string; kind: string }) =>
      learningApi.markRead(l.lesson_date, l.kind),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: learningKeys.lessons }),
  });
  // Topic lessons only. A course phase's article lives on the Courses page,
  // next to the phase it teaches — two different things that happened to
  // share a page because they were both "today's lesson".
  const lessons = useQuery({
    queryKey: [...learningKeys.lessons, "topic"],
    queryFn: () => learningApi.lessons(30, "topic"),
  });
  // Selection is by id, not by date. Two lessons a day now — the topic one
  // and a course phase — so the date stopped being unique and every click on
  // the second row silently resolved back to the first.
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<"page" | "text">("page");

  const list = lessons.data ?? [];
  const current = list.find((l) => l.id === selected) ?? list[0];

  if (lessons.isPending) {
    return (
      <div className="flex h-full flex-col gap-2">
        <Skeleton className="h-10 shrink-0" />
        <Skeleton className="min-h-0 flex-1" />
      </div>
    );
  }
  if (lessons.isError) {
    return (
      <ErrorState
        message={(lessons.error as Error).message}
        onRetry={() => void lessons.refetch()}
      />
    );
  }
  if (!current) {
    return (
      <div className="flex h-full flex-col gap-3">
        <AskBox />
        <EmptyState title="No lessons yet">
          Every morning the system reads the best few articles in full and
          writes you one lesson from them. Ask for a subject above and the next
          run starts with it.
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-2">
      <header className="shrink-0">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <h2 className="text-base font-semibold leading-tight">
            {current.title}
          </h2>
          {current.kind === "course" ? (
            <Badge variant="secondary" className="shrink-0">
              course
            </Badge>
          ) : null}
          {current.score ? (
            <Badge variant="outline" className="shrink-0">
              {current.score}/60
            </Badge>
          ) : null}
          <span
            className="text-xs text-muted-foreground"
            title={exactTime(current.created_at)}
          >
            {timeAgo(current.created_at)}
          </span>
          <div className="ml-auto flex shrink-0 gap-1">
            <Button
              size="sm"
              variant={mode === "page" ? "secondary" : "ghost"}
              disabled={!current.html_path}
              onClick={() => setMode("page")}
            >
              <PanelsTopLeft aria-hidden className="size-3.5" />
              Page
            </Button>
            <Button
              size="sm"
              variant={mode === "text" ? "secondary" : "ghost"}
              onClick={() => setMode("text")}
            >
              <FileText aria-hidden className="size-3.5" />
              Text
            </Button>
            {current.read_at ? (
              <span className="flex items-center gap-1 self-center text-xs text-muted-foreground">
                <Check aria-hidden className="size-3.5" />
                read
              </span>
            ) : (
              // The gate he asked for: the evening run will not start the next
              // phase of a course until the last one is marked read, so
              // lessons cannot pile up unread.
              <Button
                size="sm"
                variant="secondary"
                disabled={markRead.isPending}
                onClick={() =>
                  markRead.mutate({
                    lesson_date: current.lesson_date,
                    kind: current.kind,
                  })
                }
              >
                <Check aria-hidden className="size-3.5" />
                Mark as read
              </Button>
            )}
            {current.html_path ? (
              // A new tab, not a lightbox: the lesson keeps its own sandboxed
              // frame there, so the diagrams get the whole screen without the
              // markup ever reaching this origin.
              <Button size="sm" variant="ghost" asChild>
                <a
                  href={`/learn-full?path=${encodeURIComponent(current.html_path)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Maximize2 aria-hidden className="size-3.5" />
                  Full view
                </a>
              </Button>
            ) : null}
          </div>
        </div>
        {current.one_liner ? (
          <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
            {current.one_liner}
          </p>
        ) : null}
        <div className="mt-1.5">
          <AskBox />
        </div>
      </header>

      {mode === "page" && current.html_path ? (
        <LessonPageFrame path={current.html_path} title={current.title} />
      ) : (
        <LessonText path={current.md_path} />
      )}

      <footer className="shrink-0">
        <Drawer label={`Earlier topic lessons (${list.length})`}>
          <ul className="space-y-0.5 pt-1">
            {list.map((lesson) => (
              <li key={lesson.id}>
                <button
                  type="button"
                  onClick={() => setSelected(lesson.id)}
                  className={cn(
                    "flex w-full cursor-pointer items-baseline gap-1.5 rounded px-2 py-1 text-left text-xs transition-colors",
                    lesson.id === current.id
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-muted",
                  )}
                >
                  <span className="shrink-0 text-muted-foreground">
                    {lesson.lesson_date}
                  </span>
                  {lesson.kind === "course" ? (
                    <Badge
                      variant="outline"
                      className="shrink-0 px-1 py-0 text-[10px]"
                    >
                      course
                    </Badge>
                  ) : null}
                  <span className="truncate">{lesson.title}</span>
                  {lesson.read_at ? (
                    <Check aria-label="read" className="ml-auto size-3 shrink-0" />
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </Drawer>
      </footer>
    </div>
  );
}

/** A collapsed row that opens in place. Keeps the lesson the tallest thing here. */
function Drawer({
  label,
  children,
  defaultOpen = false,
}: {
  label: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details open={defaultOpen} className="group rounded-md border px-2 py-1">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-xs font-medium text-muted-foreground">
        <ChevronDown
          aria-hidden
          className="size-3 transition-transform group-open:rotate-180"
        />
        {label}
      </summary>
      {children}
    </details>
  );
}

/**
 * What he wants to learn next, in his own words.
 *
 * The roster says who publishes and `interests.md` says which subjects count.
 * Neither lets him say "go find me something on this, this week" — so this
 * does, and the morning scan serves these before it works through the roster.
 */
function AskBox() {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const asks = useQuery({
    queryKey: learningKeys.requests,
    queryFn: () => learningApi.requests(),
  });
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: learningKeys.requests });
  const add = useMutation({
    mutationFn: (value: string) => learningApi.addRequest(value),
    onSuccess: () => {
      setText("");
      void invalidate();
    },
  });
  const drop = useMutation({
    mutationFn: (id: string) => learningApi.dropRequest(id),
    onSuccess: () => void invalidate(),
  });

  const open = asks.data ?? [];
  const submit = () => {
    const value = text.trim();
    if (value.length >= 3) add.mutate(value);
  };

  return (
    <Drawer
      label={
        open.length
          ? `What do you want to learn? (${open.length} queued)`
          : "What do you want to learn?"
      }
    >
      <div className="flex gap-1 pt-1">
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="e.g. how agents recover mid-tool-call"
          aria-label="What do you want to learn next"
          className="h-8"
        />
        <Button
          size="icon"
          variant="secondary"
          className="size-8 shrink-0"
          onClick={submit}
          disabled={text.trim().length < 3 || add.isPending}
          aria-label="Add"
        >
          <Plus aria-hidden className="size-4" />
        </Button>
      </div>
      {add.isError ? (
        <p className="mt-1 text-xs text-destructive">
          {(add.error as Error).message}
        </p>
      ) : null}
      {open.length ? (
        <ul className="mt-1 space-y-0.5">
          {open.map((ask) => (
            <li
              key={ask.id}
              className="flex items-start gap-1 rounded bg-muted/50 px-2 py-1"
            >
              <span className="flex-1 text-xs">{ask.text}</span>
              <button
                type="button"
                onClick={() => drop.mutate(ask.id)}
                aria-label={`Remove: ${ask.text}`}
                className="text-muted-foreground hover:text-foreground"
              >
                <X aria-hidden className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="mt-1 text-xs text-muted-foreground">
        Served first, before the roster, on the next morning run.
      </p>
    </Drawer>
  );
}

/** The lesson's own page, in a frame that can run scripts and reach nothing. */
function LessonPageFrame({ path, title }: { path: string; title: string }) {
  const page = useQuery({
    queryKey: learningKeys.page(path),
    queryFn: () => learningApi.page(path),
  });

  if (page.isPending) return <Skeleton className="min-h-0 flex-1" />;
  if (page.isError) {
    return (
      <ErrorState
        message={(page.error as Error).message}
        onRetry={() => void page.refetch()}
      />
    );
  }
  return (
    <iframe
      title={`${title} (lesson page)`}
      srcDoc={page.data.html}
      // No same-origin: this markup is generated from unvetted pages. Popups
      // are allowed only so a source link opens a real tab instead of
      // replacing the lesson with the live site.
      sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
      className="min-h-0 w-full flex-1 rounded-md border bg-background"
    />
  );
}

function LessonText({ path }: { path: string }) {
  const note = useQuery({
    queryKey: learningKeys.note(path),
    queryFn: () => learningApi.note(path),
    enabled: Boolean(path),
  });

  if (!path) {
    return (
      <p className="text-sm text-muted-foreground">
        This lesson has no markdown note.
      </p>
    );
  }
  if (note.isPending) return <Skeleton className="min-h-0 flex-1" />;
  if (note.isError) {
    return (
      <ErrorState
        message={(note.error as Error).message}
        onRetry={() => void note.refetch()}
      />
    );
  }
  return (
    <div className="pane-scroll min-h-0 flex-1 rounded-md border px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <Markdown content={note.data.content} path={path} />
      </div>
    </div>
  );
}

// The sources used to be repeated here as a drawer. The lesson page already
// ends with them, under "Read in full for this" — printing the same four
// links again in the console was the console talking over the lesson.
