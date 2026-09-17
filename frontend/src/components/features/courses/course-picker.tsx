"use client";

import { courseTitle, onPath } from "@/components/features/courses/course-format";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Course } from "@/lib/api/learning";
import { cn } from "@/lib/utils";

/**
 * The path across the top: seven courses in the order he works them.
 *
 * They used to be a small scrolled list above the syllabus, which pushed the
 * phases below the fold and cut the course names off. On a row, the path
 * reads as a path — where he is, what comes next — and the phases get the
 * whole left pane. Platform courses that are not on the path go in a menu:
 * they are reference, not the plan.
 */
export function CoursePicker({
  courses,
  current,
  onPick,
}: {
  courses: Course[];
  current: Course;
  onPick: (course: string) => void;
}) {
  const path = courses.filter(onPath);
  const others = courses.filter((c) => !onPath(c));
  const otherSelected = !onPath(current);

  return (
    <nav aria-label="Courses" className="flex shrink-0 items-stretch gap-2">
      <ol className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1">
        {path.map((course) => {
          const selected = course.course === current.course;
          const pct = course.phases
            ? Math.round((course.taught / course.phases) * 100)
            : 0;
          return (
            <li key={course.course} className="min-w-40 flex-1">
              <button
                type="button"
                onClick={() => onPick(course.course)}
                aria-current={selected ? "true" : undefined}
                className={cn(
                  "flex h-full w-full cursor-pointer flex-col gap-1 rounded-md border px-2.5 py-2 text-left transition-colors",
                  selected
                    ? "border-primary bg-accent text-accent-foreground"
                    : "hover:bg-muted",
                )}
              >
                <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <span className="tabular-nums">{course.course_order}</span>
                  {course.active ? (
                    <span className="flex items-center gap-1 font-medium text-primary">
                      <span aria-hidden className="size-1.5 rounded-full bg-primary" />
                      active
                    </span>
                  ) : null}
                  <span className="ml-auto tabular-nums">
                    {course.taught}/{course.phases}
                  </span>
                </span>
                <span className="line-clamp-2 text-sm font-medium leading-snug">
                  {courseTitle(course)}
                </span>
                <span
                  className="mt-auto block h-1 w-full overflow-hidden rounded bg-muted"
                  role="progressbar"
                  aria-label={`${pct}% taught`}
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <span className="block h-full bg-primary" style={{ width: `${pct}%` }} />
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {others.length ? (
        <Select
          value={otherSelected ? current.course : ""}
          onValueChange={onPick}
        >
          <SelectTrigger
            aria-label="Other courses"
            className={cn(
              "w-44 shrink-0 self-stretch data-[size=default]:h-auto",
              otherSelected && "border-primary bg-accent",
            )}
          >
            <SelectValue placeholder="More courses" />
          </SelectTrigger>
          <SelectContent>
            {others.map((course) => (
              <SelectItem key={course.course} value={course.course}>
                {courseTitle(course)} · {course.taught}/{course.phases}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
    </nav>
  );
}
