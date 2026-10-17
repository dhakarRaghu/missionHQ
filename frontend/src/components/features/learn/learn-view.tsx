"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  FileText,
  Maximize2,
  PanelsTopLeft,
  Plus,
  Send,
  X,
} from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { LessonPageFrame } from "@/components/features/learn/lesson-frame";
import { LessonVideo } from "@/components/features/learn/lesson-video";
import { Markdown } from "@/components/features/vault/markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  learningApi,
  learningKeys,
  SCORE_OUT_OF,
  type ArticleRelationship,
  type Lesson,
} from "@/lib/api/learning";
import { exactTime, timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

/** What each relationship to the course phase promises the article holds. */
const RELATIONSHIP_HINT: Record<ArticleRelationship, string> = {
  fails: "a real incident on the phase's mechanism",
  measures: "a benchmark or experiment, with its conditions",
  applies: "the mechanism in a real system",
  updates: "a default, version or practice that changed",
  challenges: "a counterexample or disagreement",
  extends: "an adjacent idea the course leaves out",
};

/** What a piece is, in one word, for the list and the header. */
const PIECE_LABEL: Record<string, string> = {
  spine_incident: "incident",
  spine_evidence: "evidence",
  paper: "paper",
  frontier: "new ground",
  revision: "revision",
  product_build: "product build",
  design_story: "design story",
  ai_latest: "AI latest",
};

function pieceLabel(lesson: Lesson): string {
  if (lesson.kind === "lab") return "lab card";
  if (lesson.kind === "review") return "week review";
  if (lesson.kind === "course") return "course";
  return PIECE_LABEL[lesson.article_kind ?? ""] ?? "";
}

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
  // A post for his own site. Tutor rewrites the lesson for a reader with none
  // of his context, the checks run, and a draft file lands in the site's
  // content folder. Publishing stays his: nothing is committed or pushed.
  const draftPost = useMutation({
    mutationFn: ({ lesson, section }: { lesson: Lesson; section: "writing" | "papershelf" }) =>
      learningApi.draftPost(lesson.lesson_date, section, lesson.kind),
  });
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
    // The weekday articles plus the weekend pieces. Course lessons stay on
    // the Courses page, beside the phase they teach.
    queryFn: () => learningApi.lessons(30, "topic,lab,review"),
  });
  // Articles their own checks flagged: a sentence the digest does not
  // support, or a page check the repairs did not clear. They stay off the
  // list above and wait here, so a flagged page is never today's reading.
  const held = useQuery({
    queryKey: [...learningKeys.lessons, "held"],
    queryFn: () => learningApi.lessons(30, "topic", true),
  });
  // Selection is by id, not by date. Two lessons a day now — the topic one
  // and a course phase — so the date stopped being unique and every click on
  // the second row silently resolved back to the first.
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<"page" | "text">("page");

  const list = lessons.data ?? [];
  const heldList = held.data ?? [];
  // The day's reading is the newest article. A lab card or week review is
  // a page he works or recalls from, reached from the drawer; on 2026-09-24
  // a week review written after the article opened by default and read as
  // "today's article", which it is not.
  const current =
    list.find((l) => l.id === selected) ??
    heldList.find((l) => l.id === selected) ??
    list.find((l) => l.kind === "topic") ??
    list[0];

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
            <Badge variant="outline" className="shrink-0 tabular-nums">
              {current.score}/{SCORE_OUT_OF[current.kind]}
            </Badge>
          ) : null}
          {current.relationship ? (
            <>
              <Badge
                variant="secondary"
                className="shrink-0"
                title={RELATIONSHIP_HINT[current.relationship]}
              >
                {current.relationship}
              </Badge>
              <Link
                href="/courses"
                className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                orbits {current.phase_title || current.phase_slug || "the course phase"}
              </Link>
            </>
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
            <Button
              size="sm"
              variant="ghost"
              disabled={draftPost.isPending}
              title={
                current.article_kind === "paper"
                  ? "Rewrite this as a paper note for your site, as a draft"
                  : "Rewrite this as an article for your site, as a draft"
              }
              onClick={() =>
                draftPost.mutate({
                  lesson: current,
                  section: current.article_kind === "paper" ? "papershelf" : "writing",
                })
              }
            >
              <Send aria-hidden className="size-3.5" />
              {draftPost.isPending ? "Preparing…" : "Draft a post"}
            </Button>
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

      <LessonVideo
        key={current.id}
        lessonMd={current.md_path}
        canMake={current.kind === "topic"}
      />

      {mode === "page" && current.html_path ? (
        <LessonPageFrame
          path={current.html_path}
          title={current.title}
          lessonId={current.id}
        />
      ) : (
        <LessonText path={current.md_path} />
      )}

      <footer className="flex shrink-0 flex-col gap-1">
        <Drawer label={`Earlier lessons and weekend pages (${list.length})`}>
          <LessonList
            lessons={list}
            currentId={current.id}
            onSelect={setSelected}
          />
        </Drawer>
        {heldList.length ? (
          <Drawer label={`Held: the checks flagged these (${heldList.length})`}>
            <p className="px-2 pt-1 text-xs text-muted-foreground">
              Each keeps a sentence its source does not support, or a page
              check the repairs did not clear. Read with care.
            </p>
            <LessonList
              lessons={heldList}
              currentId={current.id}
              onSelect={setSelected}
            />
          </Drawer>
        ) : null}
      </footer>
    </div>
  );
}

/** The rows of a drawer: one lesson each, the open one marked. */
function LessonList({
  lessons,
  currentId,
  onSelect,
}: {
  lessons: Lesson[];
  currentId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="space-y-0.5 pt-1">
      {lessons.map((lesson) => (
        <li key={lesson.id}>
          <button
            type="button"
            onClick={() => onSelect(lesson.id)}
            className={cn(
              "flex w-full cursor-pointer items-baseline gap-1.5 rounded px-2 py-1 text-left text-xs transition-colors",
              lesson.id === currentId
                ? "bg-accent text-accent-foreground"
                : "hover:bg-muted",
            )}
          >
            <span className="shrink-0 text-muted-foreground">
              {lesson.lesson_date}
            </span>
            {pieceLabel(lesson) ? (
              <Badge
                variant="outline"
                className="shrink-0 px-1 py-0 text-[10px]"
              >
                {pieceLabel(lesson)}
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
