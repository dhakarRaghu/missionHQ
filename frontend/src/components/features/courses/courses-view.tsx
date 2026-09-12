"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Check, Circle, ExternalLink } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { learningApi, learningKeys, type Course, type CoursePhase } from "@/lib/api/learning";
import { cn } from "@/lib/utils";

/**
 * His own study material, one course at a time.
 *
 * This used to be a drawer under the daily lesson, which buried fifteen
 * courses in a strip at the bottom of a page about something else. It is its
 * own view now.
 *
 * "One at a time" is the rule, not a preference: exactly one course is active,
 * the evening run only touches that one, and the rest sit still until he
 * switches. Tutor teaches one phase a night, and will not start the next
 * while the last lesson is unread.
 */
export function CoursesView() {
  const courses = useQuery({
    queryKey: learningKeys.courses,
    queryFn: () => learningApi.courses(),
  });
  const [selected, setSelected] = useState<string | null>(null);

  const all = courses.data ?? [];
  const active = all.find((c) => c.active);
  const current = all.find((c) => c.course === selected) ?? active ?? all[0];

  if (courses.isPending) {
    return (
      <div className="console-split h-full">
        <Skeleton className="pane-narrow h-full" />
        <Skeleton className="pane-wide h-full" />
      </div>
    );
  }
  if (courses.isError) {
    return (
      <ErrorState
        message={(courses.error as Error).message}
        onRetry={() => void courses.refetch()}
      />
    );
  }
  if (!current) {
    return (
      <EmptyState title="No courses yet">
        Hunter syncs your study platform before each evening run. Once it has,
        your courses and their phases appear here.
      </EmptyState>
    );
  }

  return (
    <div className="console-split h-full">
      <nav aria-label="Courses" className="pane-narrow pane-scroll">
        <ul className="space-y-1">
          {all.map((course) => (
            <li key={course.course}>
              <button
                type="button"
                onClick={() => setSelected(course.course)}
                className={cn(
                  "w-full cursor-pointer rounded-md px-2.5 py-2 text-left transition-colors",
                  course.course === current.course
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-muted",
                )}
              >
                <span className="flex items-baseline gap-1.5">
                  <span className="truncate text-sm font-medium capitalize">
                    {course.course.replace(/-/g, " ")}
                  </span>
                  {course.active ? (
                    <Badge variant="secondary" className="shrink-0 px-1 py-0 text-[10px]">
                      active
                    </Badge>
                  ) : null}
                  <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
                    {course.taught}/{course.phases}
                  </span>
                </span>
                <ProgressBar taught={course.taught} phases={course.phases} />
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <section className="pane-wide pane-scroll">
        <CourseDetail course={current} />
      </section>
    </div>
  );
}

function ProgressBar({ taught, phases }: { taught: number; phases: number }) {
  const pct = phases ? Math.round((taught / phases) * 100) : 0;
  return (
    <span
      className="mt-1.5 block h-1 w-full overflow-hidden rounded bg-muted"
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span className="block h-full bg-primary" style={{ width: `${pct}%` }} />
    </span>
  );
}

function CourseDetail({ course }: { course: Course }) {
  const queryClient = useQueryClient();
  const phases = useQuery({
    queryKey: learningKeys.coursePhases(course.course),
    queryFn: () => learningApi.coursePhases(course.course),
  });
  const activate = useMutation({
    mutationFn: () => learningApi.activateCourse(course.course),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: learningKeys.courses }),
  });

  const hours = Math.round(course.minutes / 60);

  return (
    <>
      <header className="mb-3">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="text-lg font-semibold capitalize">
            {course.course.replace(/-/g, " ")}
          </h2>
          {course.active ? (
            <Badge variant="secondary">active</Badge>
          ) : (
            <Button
              size="sm"
              variant="outline"
              disabled={activate.isPending}
              onClick={() => activate.mutate()}
            >
              Work this course next
            </Button>
          )}
          <span className="ml-auto text-sm text-muted-foreground">
            {course.phases} phases · ~{hours}h · {course.taught}/{course.phases} done
          </span>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {course.active
            ? "One phase a night, in order. The next will not start while the last lesson is unread."
            : "Not the active course. Make it active and the evening run moves here."}
        </p>
      </header>

      {phases.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : phases.isError ? (
        <ErrorState
          message={(phases.error as Error).message}
          onRetry={() => void phases.refetch()}
        />
      ) : (
        <ol className="space-y-1.5">
          {(phases.data ?? []).map((phase) => (
            <PhaseRow key={phase.slug} phase={phase} course={course.course} />
          ))}
        </ol>
      )}
    </>
  );
}

/**
 * One phase, one row — whether or not it has been taught.
 *
 * A taught phase shows the ARTICLE, not the module: its title, its takeaway,
 * its score, Read, and Mark as read. The module is demoted to the "original
 * module" link beside them, because the written version is the one to read.
 *
 * These two used to be separate lists — a reading list above the phases —
 * which printed every taught phase twice under two slightly different titles.
 *
 * Mark as read lives here and nowhere else. Learn shows topic lessons only,
 * and marking a course article read is what lets the evening run start the
 * next phase, so the button has to sit on the phase it unblocks.
 */
function PhaseRow({ phase, course }: { phase: CoursePhase; course: string }) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    void queryClient.invalidateQueries({
      queryKey: learningKeys.coursePhases(course),
    });
  const teach = useMutation({
    mutationFn: () => learningApi.teachPhase(course, phase.slug),
    onSuccess: invalidate,
  });
  const markRead = useMutation({
    mutationFn: () => learningApi.markRead(phase.lesson_date ?? "", "course"),
    onSuccess: invalidate,
  });

  const taught = phase.status === "taught" && !!phase.lesson_html_path;
  const unread = taught && !phase.lesson_read_at;

  return (
    <li
      className={cn(
        "rounded-md border px-3 py-2",
        taught ? "bg-muted/40" : undefined,
      )}
    >
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="w-5 shrink-0 text-xs tabular-nums text-muted-foreground">
          {phase.phase_order}
        </span>
        <span className="text-sm font-medium">
          {taught ? (phase.lesson_title ?? phase.title) : phase.title}
        </span>
        {taught ? null : phase.difficulty ? (
          <Badge variant="outline" className="shrink-0 text-[10px] uppercase">
            {phase.difficulty}
          </Badge>
        ) : null}
        <span className="ml-auto flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          {taught && phase.lesson_score ? (
            <span className="tabular-nums">{phase.lesson_score}/60</span>
          ) : null}
          ~{phase.minutes}m
          {taught ? (
            <Check aria-label="taught" className="size-3.5" />
          ) : (
            <Circle aria-label="not taught yet" className="size-3" />
          )}
        </span>
      </div>

      {/* The article's takeaway replaces the module summary once it exists:
          the summary describes what he was going to read, the takeaway says
          what the written version actually landed on. */}
      {(taught ? phase.lesson_one_liner : phase.summary) ? (
        <p
          className={cn(
            "mt-0.5 pl-7 text-xs text-muted-foreground",
            taught ? undefined : "line-clamp-2",
          )}
        >
          {taught ? phase.lesson_one_liner : phase.summary}
        </p>
      ) : null}

      <div className="mt-1.5 flex flex-wrap items-center gap-2 pl-7">
        {taught ? (
          <>
            <Button size="sm" asChild>
              <a
                href={`/learn-full?path=${encodeURIComponent(phase.lesson_html_path ?? "")}`}
                target="_blank"
                rel="noreferrer"
              >
                <BookOpen aria-hidden className="size-3.5" />
                Read
              </a>
            </Button>
            {unread ? (
              <Button
                size="sm"
                variant="outline"
                disabled={markRead.isPending}
                onClick={() => markRead.mutate()}
              >
                <Check aria-hidden className="size-3.5" />
                Mark as read
              </Button>
            ) : (
              <Badge variant="secondary" className="gap-1">
                <Check aria-hidden className="size-3" />
                read
              </Badge>
            )}
            {unread ? (
              <span className="text-xs text-muted-foreground">
                the next phase waits until this is marked read
              </span>
            ) : null}
          </>
        ) : phase.status === "pending" ? (
          <Button
            size="sm"
            variant="outline"
            disabled={teach.isPending}
            onClick={() => teach.mutate()}
          >
            {teach.isPending ? "Starting…" : "Teach this now"}
          </Button>
        ) : null}
        <a
          className="inline-flex items-center gap-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          href={phase.url}
          rel="noreferrer"
          target="_blank"
        >
          original module
          <ExternalLink aria-hidden className="size-3" />
        </a>
        {teach.data && !teach.data.started ? (
          <span className="text-xs text-destructive">{teach.data.reason}</span>
        ) : null}
        {teach.data?.started ? (
          <span className="text-xs text-muted-foreground">
            studying now — the article lands here when it is written
          </span>
        ) : null}
      </div>
    </li>
  );
}
