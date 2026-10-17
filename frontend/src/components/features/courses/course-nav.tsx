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
 * Two groups: the path he is working through, and the other courses, which
 * are reference and stay closed until he asks for them. Above them, one row
 * opens the videos made from the courses.
 *
 * Each course is listed once. Step 2 of the path, Applied AI, is the 21
 * modules of the applied-AI curriculum, each a course of its own on the
 * platform. Until 2026-10-17 the same courses showed three times: as a
 * curriculum module, as an untitled platform course, and, for inference
 * internals (module 1), as path step 3. The old five-phase spec behind step 2
 * (`learning/courses/02-applied-ai/course.md`) is no longer listed: the
 * modules are that course now.
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
  const modules = curriculum?.modules ?? [];
  const topics = new Set(modules.map((m) => m.topic).filter(Boolean));
  // A curriculum course is reached through its module, never on its own row.
  const own = courses.filter((c) => !topics.has(c.course));
  const path = own.filter(onPath);
  const others = own.filter((c) => !onPath(c));
  // The path slot the modules take. Without its spec row they go last.
  const slot = path.findIndex((c) => c.course === APPLIED_AI_COURSE);
  const steps: PathStep[] = path
    .filter((c) => c.course !== APPLIED_AI_COURSE)
    .map((course) => ({ kind: "course", course }));
  steps.splice(slot < 0 ? steps.length : slot, 0, {
    kind: "applied",
    title: slot < 0 ? "Applied AI" : courseTitle(path[slot]),
  });
  const inApplied = topics.has(current.course);
  // The same key as the library's list, so opening it costs no second fetch.
  const videos = useQuery({
    queryKey: mediaKeys.videos({ kind: "course,youtube" }),
    queryFn: () => mediaApi.videos({ kind: "course,youtube" }),
    staleTime: 10 * 60_000,
  });
  const reading = !openModule && !videosOpen;

  // Undefined until he clicks: the modules arrive after the courses, so the
  // default for Applied AI is worked out on each render, not once.
  const [clicked, setClicked] = useState<Partial<Record<GroupName, boolean>>>({});
  const open: Record<GroupName, boolean> = {
    path: clicked.path ?? true,
    // Open while he is reading one of its modules, which is most of the time.
    applied: clicked.applied ?? inApplied,
    // Reference, not the plan: it stays closed until he opens it.
    others: clicked.others ?? false,
  };
  const toggle = (name: GroupName) =>
    setClicked((was) => ({ ...was, [name]: !open[name] }));

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
        count={steps.length}
        open={open.path}
        onToggle={toggle}
      >
        <ol className="space-y-0.5">
          {steps.map((step, index) =>
            step.kind === "course" ? (
              <li key={step.course.course}>
                <CourseRow
                  course={step.course}
                  step={index + 1}
                  selected={reading && step.course.course === current.course}
                  onSelect={() => onPickCourse(step.course.course)}
                />
              </li>
            ) : (
              <li key="applied">
                <AppliedRow
                  step={index + 1}
                  title={step.title}
                  modules={modules}
                  active={courses.some((c) => c.active && topics.has(c.course))}
                  open={open.applied}
                  onToggle={() => toggle("applied")}
                />
                <div id="course-group-applied" hidden={!open.applied} className="pl-4">
                  {pending ? (
                    <Skeleton className="h-24 w-full" />
                  ) : error ? (
                    <div role="alert" className="px-2 py-1 text-xs text-destructive">
                      <p className="break-words">Could not load the modules: {error}</p>
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
                    byLayer(modules).map(([layer, group]) => (
                      <section key={layer} aria-label={layer} className="mt-1.5">
                        <h4 className="px-2 text-[11px] font-medium text-muted-foreground">
                          {layer}
                        </h4>
                        <ol className="space-y-0.5">
                          {group.map((module) => (
                            <li key={module.number}>
                              <ModuleRow
                                module={module}
                                active={courses.some(
                                  (c) => c.active && c.course === module.topic,
                                )}
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
                    ))
                  )}
                </div>
              </li>
            ),
          )}
        </ol>
      </Group>

      {others.length ? (
        <Group
          name="others"
          title="Other courses"
          count={others.length}
          open={open.others}
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

type GroupName = "path" | "applied" | "others";

/** The path course whose place the curriculum modules take. */
const APPLIED_AI_COURSE = "elite-applied-ai";

type PathStep =
  | { kind: "course"; course: Course }
  | { kind: "applied"; title: string };

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

/**
 * Step 2 of the path: one row for the 21 modules, with how far through them
 * he is. It opens and closes the modules under it; each module opens its own
 * course.
 */
function AppliedRow({
  step,
  title,
  modules,
  active,
  open,
  onToggle,
}: {
  step: number;
  title: string;
  modules: CurriculumModule[];
  active: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const built = modules.filter((m) => m.topic);
  const phases = built.reduce((sum, m) => sum + (m.phases ?? 0), 0);
  const taught = built.reduce((sum, m) => sum + (m.taught ?? 0), 0);
  const pct = phases ? Math.round((taught / phases) * 100) : 0;
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls="course-group-applied"
      className="flex w-full cursor-pointer gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted"
    >
      <span className="mt-0.5 w-4 shrink-0 text-[11px] tabular-nums text-muted-foreground">
        {step}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-start gap-2">
          <span className="line-clamp-2 min-w-0 flex-1 text-sm leading-snug break-words">
            {title}
          </span>
          <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
            {taught}/{phases}
          </span>
          {open ? (
            <ChevronDown aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          ) : (
            <ChevronRight aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          )}
        </span>
        <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span>{built.length} modules</span>
          {active ? (
            <span className="flex items-center gap-1 font-medium text-primary">
              <span aria-hidden className="size-1.5 rounded-full bg-primary" />
              active
            </span>
          ) : null}
        </span>
        <Progress
          value={pct}
          className="mt-1 h-0.5"
          aria-label={`${pct}% of the module phases taught`}
        />
      </span>
    </button>
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
  active,
  selected,
  onSelect,
}: {
  module: CurriculumModule;
  /** Its course is the one the evening run is working on. */
  active: boolean;
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
        <span className="flex items-start gap-2">
          <span
            className={cn(
              "line-clamp-2 min-w-0 flex-1 text-sm leading-snug break-words",
              !built && "text-muted-foreground",
            )}
          >
            {module.title}
          </span>
          {built && module.phases ? (
            <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
              {module.taught ?? 0}/{module.phases}
            </span>
          ) : null}
        </span>
        {/* A built module reads like a course row. The plan details are only
            worth a line while the module has no course behind it. */}
        {active || module.core_order || !built ? (
          <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-muted-foreground">
            {active ? (
              <span className="flex items-center gap-1 font-medium text-primary">
                <span aria-hidden className="size-1.5 rounded-full bg-primary" />
                active
              </span>
            ) : null}
            {built ? null : (
              <>
                <Badge
                  variant="secondary"
                  tone={statusTone(module.status)}
                  className="h-4 px-1.5"
                >
                  {module.status}
                </Badge>
                <span>{plannedPhasesText(module)}</span>
              </>
            )}
            {module.core_order ? <span>core {module.core_order} of 8</span> : null}
          </span>
        ) : null}
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
