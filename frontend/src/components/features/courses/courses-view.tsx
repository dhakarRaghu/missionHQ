"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { phaseState } from "@/components/features/courses/course-format";
import { CourseModulePanel } from "@/components/features/courses/course-module";
import { CourseNav } from "@/components/features/courses/course-nav";
import { CoursesReader } from "@/components/features/courses/courses-reader";
import { CoursesSide } from "@/components/features/courses/courses-side";
import { CoursesSyllabus } from "@/components/features/courses/courses-syllabus";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  learningApi,
  learningKeys,
  type Course,
  type CoursePhase,
  type Curriculum,
  type CurriculumModule,
} from "@/lib/api/learning";
import { cn } from "@/lib/utils";

/**
 * His own study material, one course at a time — as a place to read, not a
 * list of links.
 *
 * The first version printed every phase as a row with a Read button, so the
 * course arrived as fifteen articles: "courses are only shown in article form,
 * they are not article". A course is worked through in order, so the view is a
 * workspace — where he is on the left, the phase he is reading in the middle,
 * what is in it on the right — and the lesson itself gets the width.
 *
 * "One at a time" is the rule, not a preference: exactly one course is active,
 * the evening run only touches that one, and the rest sit still until he
 * switches. Tutor teaches one phase a night, and will not start the next while
 * the last lesson is unread.
 *
 * The left column carries both halves of "where am I": the switcher over
 * every course and every module of the plan, and under it the syllabus of the
 * one he picked. The switcher is capped so it can never push the phases off
 * the screen, however many courses there are.
 */
export function CoursesView() {
  const courses = useQuery({
    queryKey: learningKeys.courses,
    queryFn: () => learningApi.courses(),
  });
  // The plan behind the courses. It is read from a file in the repo, so it
  // changes about once a research run: stale time keeps it out of the way.
  const curriculum = useQuery({
    queryKey: learningKeys.curriculum,
    queryFn: () => learningApi.curriculum(),
    staleTime: 5 * 60_000,
  });
  const [selected, setSelected] = useState<string | null>(null);
  // A module with no course takes the centre pane instead of the reader.
  const [openModule, setOpenModule] = useState<CurriculumModule | null>(null);

  const all = courses.data ?? [];
  const active = all.find((c) => c.active);
  const current = all.find((c) => c.course === selected) ?? active ?? all[0];

  if (courses.isPending) {
    return (
      <div className="console-workspace h-full" data-side="open">
        <Skeleton className="h-full" />
        <Skeleton className="h-full" />
        <Skeleton className="h-full" />
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
    <CourseWorkspace
      courses={all}
      course={current}
      curriculum={curriculum.data}
      curriculumPending={curriculum.isPending}
      curriculumError={
        curriculum.isError ? (curriculum.error as Error).message : null
      }
      onRetryCurriculum={() => void curriculum.refetch()}
      openModule={openModule}
      // Picking a course closes the module panel: he asked for a course, so
      // the reader is what he should be looking at.
      onPickCourse={(course) => {
        setSelected(course);
        setOpenModule(null);
      }}
      onOpenModule={setOpenModule}
      onCloseModule={() => setOpenModule(null)}
    />
  );
}

function CourseWorkspace({
  courses,
  course,
  curriculum,
  curriculumPending,
  curriculumError,
  onRetryCurriculum,
  openModule,
  onPickCourse,
  onOpenModule,
  onCloseModule,
}: {
  courses: Course[];
  course: Course;
  curriculum: Curriculum | undefined;
  curriculumPending: boolean;
  curriculumError: string | null;
  onRetryCurriculum: () => void;
  openModule: CurriculumModule | null;
  onPickCourse: (course: string) => void;
  onOpenModule: (module: CurriculumModule) => void;
  onCloseModule: () => void;
}) {
  const phases = useQuery({
    queryKey: learningKeys.coursePhases(course.course),
    queryFn: () => learningApi.coursePhases(course.course),
  });
  // Which phase he is reading, and which course that answer belongs to. The
  // workspace is not remounted on a switch any more, because the switcher
  // lives inside it and would lose its open groups and its scroll position,
  // so the phase is read back here instead.
  const [picked, setPicked] = useState<{ course: string; slug: string | null }>(
    () => ({ course: course.course, slug: rememberedPhase(course.course) }),
  );
  const [sideOpen, setSideOpen] = useState(true);
  // Full view: the phase over the whole window, for reading a long course
  // with wide diagrams. The syllabus and the app around it step aside; the
  // contents panel stays, collapsible, because it is how he moves around.
  const [focus, setFocus] = useState(false);
  useEffect(() => {
    if (!focus) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFocus(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus]);

  if (picked.course !== course.course) {
    setPicked({ course: course.course, slug: rememberedPhase(course.course) });
  }

  const list = phases.data ?? [];
  const current = list.find((p) => p.slug === picked.slug) ?? whereHeIs(list);
  // A published phase is read as its enhanced page, which carries its own
  // contents rail inside its frame, so the side panel steps aside. A module
  // panel has no phase behind it at all, so it steps aside too.
  const pageOnScreen = Boolean(openModule) || current?.source === "platform";

  const select = (slug: string) => {
    setPicked({ course: course.course, slug });
    rememberPhase(course.course, slug);
  };

  return (
    <div
      className={cn(
        "console-workspace h-full min-h-0",
        focus && "fixed inset-0 z-50 bg-background p-3 md:p-5",
      )}
      data-side={pageOnScreen ? "none" : sideOpen ? "open" : "closed"}
      data-focus={focus ? "on" : undefined}
      role={focus ? "dialog" : undefined}
      aria-modal={focus ? true : undefined}
      aria-label={focus ? "Full view" : undefined}
    >
      {focus ? null : (
        <div className="courses-nav">
          <CourseNav
            courses={courses}
            current={course}
            curriculum={curriculum}
            pending={curriculumPending}
            error={curriculumError}
            onRetry={onRetryCurriculum}
            openModule={openModule}
            onPickCourse={onPickCourse}
            onOpenModule={onOpenModule}
          />
          <CoursesSyllabus
            course={course}
            phases={list}
            pending={phases.isPending}
            error={phases.isError ? (phases.error as Error).message : null}
            onRetry={() => void phases.refetch()}
            selected={current?.slug ?? null}
            onSelect={select}
          />
        </div>
      )}
      {openModule ? (
        <CourseModulePanel module={openModule} onBack={onCloseModule} />
      ) : (
        <CoursesReader
          course={course.course}
          phase={current}
          phases={list}
          onSelect={select}
          focus={focus}
          onToggleFocus={() => setFocus((on) => !on)}
        />
      )}
      {pageOnScreen ? null : (
        <CoursesSide
          phase={current}
          open={sideOpen}
          onToggle={() => setSideOpen((open) => !open)}
        />
      )}
    </div>
  );
}

/**
 * The phase he is on, when he has not picked one.
 *
 * The taught phase waiting to be marked read comes first: that is the one the
 * gate is holding the course on. Then the first published phase he has not
 * read, then the next planned one, then the end of a finished course.
 */
function whereHeIs(list: CoursePhase[]): CoursePhase | undefined {
  return (
    list.find((p) => phaseState(p) === "unread") ??
    list.find((p) => phaseState(p) === "pending") ??
    list.find((p) => phaseState(p) === "planned") ??
    list[list.length - 1]
  );
}

// Which phase he was reading, per course, so leaving the view and coming back
// lands where he stopped rather than at the top of the syllabus. Storage
// throws in a private window and when the quota is full, and a course he can
// no longer see must not break the page, so every access is guarded.
const PHASE_KEY = "missionhq.courses.phase";

function readMap(): Record<string, string> {
  try {
    if (typeof window === "undefined") return {};
    const raw = window.localStorage.getItem(PHASE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object"
      ? (parsed as Record<string, string>)
      : {};
  } catch {
    return {};
  }
}

function rememberedPhase(course: string): string | null {
  return readMap()[course] ?? null;
}

function rememberPhase(course: string, slug: string) {
  try {
    if (typeof window === "undefined") return;
    const next = { ...readMap(), [course]: slug };
    window.localStorage.setItem(PHASE_KEY, JSON.stringify(next));
  } catch {
    // Not worth telling him about: the selection still holds for this visit.
  }
}
