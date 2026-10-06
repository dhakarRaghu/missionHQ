"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Clapperboard } from "lucide-react";

import {
  courseTitle,
  onPath,
  plannedPhasesText,
  statusTone,
} from "@/components/features/courses/course-format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  Course,
  Curriculum,
  CurriculumModule,
} from "@/lib/api/learning";
import { mediaApi, mediaKeys } from "@/lib/api/media";
import { cn } from "@/lib/utils";

/**
 * Top of the left column: everything he can open, as a list that grows.
 *
 * It used to be a row of cards across the top with a "More courses" menu
 * beside it. Eight path courses and eleven platform courses later the row
 * scrolled sideways, the menu covered the cards, and the phases were pushed
 * below the fold. A column takes one more course without changing shape.
 *
 * Three groups, in the order he uses them: the path he is working through,
 * the applied-AI curriculum behind it (mostly still a plan), and the platform
 * courses, which are reference and stay closed until he asks for them. Above
 * them, one row opens the videos made from the courses.
 */
export function CourseNav({
  courses,
  current,
  curriculum,
  pending,
  error,
  onRetry,
  openModule,
  videosOpen,
  onPickCourse,
  onOpenModule,
  onOpenVideos,
}: {
  courses: Course[];
  current: Course;
  curriculum: Curriculum | undefined;
  pending: boolean;
  error: string | null;
  onRetry: () => void;
  /** The module shown in the centre, when he opened one that has no course. */
  openModule: CurriculumModule | null;
  /** The video library is in the centre pane. */
  videosOpen: boolean;
  onPickCourse: (course: string) => void;
  onOpenModule: (module: CurriculumModule) => void;
  onOpenVideos: () => void;
}) {
  const path = courses.filter(onPath);
  const others = courses.filter((c) => !onPath(c));
  const modules = curriculum?.modules ?? [];
  // The same key as the library's list, so opening it costs no second fetch.
  const videos = useQuery({
    queryKey: mediaKeys.videos({ kind: "course,youtube" }),
    queryFn: () => mediaApi.videos({ kind: "course,youtube" }),
    staleTime: 10 * 60_000,
  });
  const reading = !openModule && !videosOpen;

  const [open, setOpen] = useState<Record<GroupName, boolean>>({
    path: true,
    curriculum: true,
    // Reference, not the plan: it stays closed until he opens it.
    platform: false,
  });
  const toggle = (name: GroupName) =>
    setOpen((was) => ({ ...was, [name]: !was[name] }));

  return (
    <nav aria-label="Courses" className="courses-switcher -mx-1 px-1">
      <button
        type="button"
        onClick={onOpenVideos}
        aria-current={videosOpen ? "true" : undefined}
        className={cn(
          "mb-1 flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-xs font-semibold transition-colors",
          videosOpen ? "bg-accent text-accent-foreground" : "hover:bg-muted",
        )}
      >
        <Clapperboard aria-hidden className="size-3.5 shrink-0" />
        <span className="min-w-0 flex-1 truncate">Videos</span>
        {videos.data ? (
          <span className="shrink-0 tabular-nums text-muted-foreground">
            {videos.data.length}
          </span>
        ) : null}
      </button>
      <Group
        name="path"
        title="Your path"
        count={path.length}
        open={open.path}
        onToggle={toggle}
      >
        <ol className="space-y-0.5">
          {path.map((course) => (
            <li key={course.course}>
              <CourseRow
                course={course}
                step={course.course_order}
                selected={reading && course.course === current.course}
                onSelect={() => onPickCourse(course.course)}
              />
            </li>
          ))}
        </ol>
      </Group>

      <Group
        name="curriculum"
        title="Applied-AI curriculum"
        count={modules.length}
        open={open.curriculum}
        onToggle={toggle}
      >
        {pending ? (
          <Skeleton className="h-24 w-full" />
        ) : error ? (
          <div role="alert" className="px-2 py-1 text-xs text-destructive">
            <p className="break-words">Could not load the curriculum: {error}</p>
            <Button
              size="sm"
              variant="outline"
              className="mt-1"
              onClick={onRetry}
            >
              Retry
            </Button>
          </div>
        ) : !modules.length ? (
          <p className="px-2 py-1 text-xs text-muted-foreground">
            The curriculum file is not in the repo yet.
          </p>
        ) : (
          <>
            {curriculum ? <Counts curriculum={curriculum} /> : null}
            {byLayer(modules).map(([layer, group]) => (
              <section key={layer} aria-label={layer} className="mt-1.5">
                <h4 className="px-2 text-[11px] font-medium text-muted-foreground">
                  {layer}
                </h4>
                <ol className="space-y-0.5">
                  {group.map((module) => (
                    <li key={module.number}>
                      <ModuleRow
                        module={module}
                        selected={
                          module.number === openModule?.number ||
                          (reading &&
                            Boolean(module.topic) &&
                            module.topic === current.course)
                        }
                        onSelect={() =>
                          module.topic
                            ? onPickCourse(module.topic)
                            : onOpenModule(module)
                        }
                      />
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </>
        )}
      </Group>

      {others.length ? (
        <Group
          name="platform"
          title="Platform courses"
          count={others.length}
          open={open.platform}
          onToggle={toggle}
        >
          <ol className="space-y-0.5">
            {others.map((course) => (
              <li key={course.course}>
                <CourseRow
                  course={course}
                  selected={reading && course.course === current.course}
                  onSelect={() => onPickCourse(course.course)}
                />
              </li>
            ))}
          </ol>
        </Group>
      ) : null}
    </nav>
  );
}

type GroupName = "path" | "curriculum" | "platform";

/** A heading that opens and closes its list, with how many rows are in it. */
function Group({
  name,
  title,
  count,
  open,
  onToggle,
  children,
}: {
  name: GroupName;
  title: string;
  count: number;
  open: boolean;
  onToggle: (name: GroupName) => void;
  children: React.ReactNode;
}) {
  const id = `course-group-${name}`;
  return (
    <section className="pb-1">
      <h3>
        <button
          type="button"
          onClick={() => onToggle(name)}
          aria-expanded={open}
          aria-controls={id}
          className="flex w-full cursor-pointer items-center gap-1 rounded-md px-2 py-1.5 text-left text-xs font-semibold hover:bg-muted"
        >
          {open ? (
            <ChevronDown aria-hidden className="size-3.5 shrink-0" />
          ) : (
            <ChevronRight aria-hidden className="size-3.5 shrink-0" />
          )}
          <span className="min-w-0 flex-1 truncate">{title}</span>
          <span className="shrink-0 tabular-nums text-muted-foreground">
            {count}
          </span>
        </button>
      </h3>
      <div id={id} hidden={!open}>
        {children}
      </div>
    </section>
  );
}

/** How many modules stand at each status, as one line. */
function Counts({ curriculum }: { curriculum: Curriculum }) {
  const counts = curriculum.counts;
  const parts = (
    ["complete", "ready", "partial", "not started"] as const
  ).map((status) => `${counts[status] ?? 0} ${status}`);
  return (
    <p className="px-2 pb-1 text-[11px] text-muted-foreground">
      {parts.join(" · ")}
    </p>
  );
}

/** One course: its name, how far through it he is, and whether it is the one
 * the evening run is working on. */
function CourseRow({
  course,
  step,
  selected,
  onSelect,
}: {
  course: Course;
  /** Its place on the path, printed only for the path courses. */
  step?: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const pct = course.phases
    ? Math.round((course.taught / course.phases) * 100)
    : 0;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "flex w-full cursor-pointer gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
        selected ? "bg-accent text-accent-foreground" : "hover:bg-muted",
      )}
    >
      {step ? (
        <span className="mt-0.5 w-4 shrink-0 text-[11px] tabular-nums text-muted-foreground">
          {step}
        </span>
      ) : null}
      <span className="min-w-0 flex-1">
        <span className="flex items-start gap-2">
          <span className="line-clamp-2 min-w-0 flex-1 text-sm leading-snug break-words">
            {courseTitle(course)}
          </span>
          <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
            {course.taught}/{course.phases}
          </span>
        </span>
        {course.active ? (
          <span className="mt-0.5 flex items-center gap-1 text-[11px] font-medium text-primary">
            <span aria-hidden className="size-1.5 rounded-full bg-primary" />
            active
          </span>
        ) : null}
        <Progress
          value={pct}
          className="mt-1 h-0.5"
          aria-label={`${pct}% of the phases taught`}
        />
      </span>
    </button>
  );
}

/** One module of the plan. It opens its course when one exists, and its own
 * panel when it does not, so a module that is still a plan is still a place
 * he can go and read what is missing. */
function ModuleRow({
  module,
  selected,
  onSelect,
}: {
  module: CurriculumModule;
  selected: boolean;
  onSelect: () => void;
}) {
  const built = Boolean(module.topic);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "flex w-full cursor-pointer gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
        selected ? "bg-accent text-accent-foreground" : "hover:bg-muted",
      )}
    >
      <span className="mt-0.5 w-5 shrink-0 text-[11px] tabular-nums text-muted-foreground">
        {module.number}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={cn(
            "line-clamp-2 text-sm leading-snug break-words",
            !built && "text-muted-foreground",
          )}
        >
          {module.title}
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-muted-foreground">
          <Badge
            variant="secondary"
            tone={statusTone(module.status)}
            className="h-4 px-1.5"
          >
            {module.status}
          </Badge>
          {module.core_order ? <span>core {module.core_order} of 8</span> : null}
          {/* A module whose course exists carries its progress as well as the
              plan, so the two readings of "where is this" sit together. */}
          {built && module.phases ? (
            <span className="tabular-nums">
              {module.taught ?? 0}/{module.phases} taught
            </span>
          ) : null}
          <span>{plannedPhasesText(module)}</span>
        </span>
      </span>
    </button>
  );
}

/** The modules in their layers, in the order the layers first appear. */
function byLayer(modules: CurriculumModule[]): [string, CurriculumModule[]][] {
  const out = new Map<string, CurriculumModule[]>();
  // Not named `module`: a variable of that name is reserved in this app.
  for (const row of modules) {
    const group = out.get(row.layer);
    if (group) group.push(row);
    else out.set(row.layer, [row]);
  }
  return [...out.entries()];
}
