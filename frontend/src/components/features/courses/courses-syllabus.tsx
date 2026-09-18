"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";

import {
  courseTitle,
  phaseLabel,
  phaseState,
  phaseTitle,
  tidy,
} from "@/components/features/courses/course-format";
import { Markdown } from "@/components/features/vault/markdown";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { learningApi, learningKeys, type Course, type CoursePhase } from "@/lib/api/learning";
import { cn } from "@/lib/utils";

/**
 * Lower half of the left column: the course he picked, and where he is in it.
 *
 * The course switcher sits above it, capped and scrolling on its own, so the
 * phases keep the rest of the column. The course's reason is a short,
 * expandable summary rather than a paragraph that pushed the phases off the
 * screen, so the syllabus — the phases in order, with the question each one
 * answers — is what this half is mostly made of.
 */
export function CoursesSyllabus({
  course,
  phases,
  pending,
  error,
  onRetry,
  selected,
  onSelect,
}: {
  course: Course;
  phases: CoursePhase[];
  pending: boolean;
  error: string | null;
  onRetry: () => void;
  selected: string | null;
  onSelect: (slug: string) => void;
}) {
  const queryClient = useQueryClient();
  const activate = useMutation({
    mutationFn: () => learningApi.activateCourse(course.course),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: learningKeys.courses }),
  });
  const [more, setMore] = useState(false);

  const hours = Math.round(course.minutes / 60);
  const read = phases.filter((p) => phaseState(p) === "read").length;
  const planned = phases.filter((p) => phaseState(p) === "planned").length;
  const groups = groupParts(phases);
  const description = tidy(course.description);

  return (
    <section
      aria-label="Syllabus"
      className="flex min-h-0 flex-1 flex-col gap-3 border-t pt-2"
    >
      <header className="shrink-0 space-y-2">
        <div>
          <h2 className="text-base font-semibold leading-snug">{courseTitle(course)}</h2>
          <p className="mt-0.5 text-xs tabular-nums text-muted-foreground">
            {course.phases} phases · ~{hours}h reading · {course.taught} taught · {read} read
            {planned ? ` · ${planned} planned` : ""}
            {course.source === "platform" ? " · from your study platform" : ""}
          </p>
        </div>

        {description ? (
          <div className="text-xs leading-relaxed text-muted-foreground">
            <div className={cn(!more && "line-clamp-3")}>
              <Markdown content={description} />
            </div>
            <button
              type="button"
              onClick={() => setMore((open) => !open)}
              className="mt-0.5 cursor-pointer font-medium text-foreground underline-offset-2 hover:underline"
            >
              {more ? "Show less" : "Why this course"}
            </button>
          </div>
        ) : null}

        {course.active ? (
          <p className="rounded-md bg-muted/60 px-2 py-1.5 text-xs text-muted-foreground">
            Active. One phase a night, in order; the next waits until the last
            lesson is read.
          </p>
        ) : (
          <Button
            size="sm"
            variant="outline"
            className="w-full"
            disabled={activate.isPending}
            onClick={() => activate.mutate()}
          >
            Work this course next
          </Button>
        )}
      </header>

      {pending ? (
        <Skeleton className="min-h-0 flex-1" />
      ) : error ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : !phases.length ? (
        <EmptyState title="No phases" compact>
          This course has no phases yet. Hunter fills them in on the next sync.
        </EmptyState>
      ) : (
        <ol className="pane-scroll -mx-1 space-y-0.5 border-t pt-2">
          {groups.map((group) =>
            group.length === 1 ? (
              <li key={group[0].slug}>
                <PhaseLink
                  phase={group[0]}
                  selected={group[0].slug === selected}
                  onSelect={() => onSelect(group[0].slug)}
                />
              </li>
            ) : (
              // A phase the platform split into parts reads as one phase with
              // parts under it, not as two phases that happen to share a number.
              <li key={group[0].slug} className="py-1">
                <p className="px-2 text-[11px] font-medium text-muted-foreground">
                  Phase {group[0].phase_order} · {group.length} parts
                </p>
                <ol className="ml-3 space-y-0.5 border-l pl-1">
                  {group.map((phase) => (
                    <li key={phase.slug}>
                      <PhaseLink
                        phase={phase}
                        selected={phase.slug === selected}
                        onSelect={() => onSelect(phase.slug)}
                      />
                    </li>
                  ))}
                </ol>
              </li>
            ),
          )}
        </ol>
      )}
    </section>
  );
}

function PhaseLink({
  phase,
  selected,
  onSelect,
}: {
  phase: CoursePhase;
  selected: boolean;
  onSelect: () => void;
}) {
  const state = phaseState(phase);
  // A legacy article's title is not the module's; a platform phase keeps its own.
  const title =
    phase.source === "platform" || state === "pending" || state === "planned"
      ? phase.title
      : (phase.lesson_title ?? phase.title);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "flex w-full cursor-pointer gap-2 rounded-md px-2 py-2 text-left transition-colors",
        selected ? "bg-accent text-accent-foreground" : "hover:bg-muted",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-medium tabular-nums",
          state === "read" && "border-primary bg-primary text-primary-foreground",
          state === "unread" && "border-primary text-primary",
          state === "planned" && "border-dashed text-muted-foreground",
        )}
      >
        {state === "read" ? (
          <Check aria-label="read" className="size-3" />
        ) : (
          phaseLabel(phase)
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={cn(
            "line-clamp-2 text-sm leading-snug",
            state === "planned" && "text-muted-foreground",
          )}
        >
          {phaseTitle(title)}
        </span>
        {/* The question, not the summary: it is what the phase is for, and it
            is the line that tells him whether this is the one he wants. */}
        {phase.question ? (
          <span className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
            {phase.question}
          </span>
        ) : null}
        {state === "unread" ? (
          <span className="mt-0.5 block text-[11px] font-medium text-primary">
            ready · waiting for you to read it
          </span>
        ) : state === "planned" ? (
          <span className="mt-0.5 block text-[11px] text-muted-foreground">
            planned · not published yet
          </span>
        ) : null}
      </span>
    </button>
  );
}

/** Consecutive phases sharing an order number: the A and B parts. */
function groupParts(phases: CoursePhase[]): CoursePhase[][] {
  const out: CoursePhase[][] = [];
  for (const phase of phases) {
    const last = out[out.length - 1];
    if (last && last[0].phase_order === phase.phase_order) last.push(phase);
    else out.push([phase]);
  }
  return out;
}
