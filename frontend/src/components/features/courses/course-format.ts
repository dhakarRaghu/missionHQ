import type { Course, CoursePhase } from "@/lib/api/learning";

/** Courses without a place on the path sort last with this order. */
export const OFF_PATH = 999;

/** The course's own name; the slug only when the backend has none. */
export function courseTitle(course: Course): string {
  if (course.title) return course.title;
  const words = course.course.replace(/^elite-/, "").replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function onPath(course: Course): boolean {
  return (course.course_order ?? OFF_PATH) < OFF_PATH;
}

/**
 * "3A", not "3": the platform splits long phases into A and B parts, and the
 * number alone printed two different phases as the same one.
 */
export function phaseLabel(phase: CoursePhase): string {
  const match = /-phase-0*(\d+)([a-z]?)(?:-|$)/.exec(phase.slug);
  return match ? `${match[1]}${match[2].toUpperCase()}` : String(phase.phase_order);
}

/** The title without the course name the platform repeats in every phase. */
export function phaseTitle(title: string): string {
  return title.replace(/^.*?\bPhase\s+\w+\s*[:—-]\s*/u, "") || title;
}

/** Spec text ends with a markdown rule the parser keeps; it renders as noise. */
export function tidy(text: string | undefined | null): string {
  return (text ?? "").replace(/\n\s*-{3,}\s*$/u, "").trim();
}

/**
 * A phase is in one of five states, and "unread" is the one that matters: a
 * taught phase he has not marked read holds the whole course.
 *
 * "planned" is a phase written here as a spec and not yet published — there
 * is nothing to read until he generates it with Claude. "waiting" is
 * everything else — skipped, or taught while the article is still being
 * written — and offers no button.
 */
export type PhaseState = "planned" | "pending" | "unread" | "read" | "waiting";

/** Phase-level read first; older rows only carry the lesson's. */
export function readAt(phase: CoursePhase): string | null {
  return phase.read_at ?? phase.lesson_read_at ?? null;
}

/** A spec with no text behind it yet. A local phase that already has an old
 * generated lesson is still readable, so it is not "planned". */
export function isPlanned(phase: CoursePhase): boolean {
  return (
    phase.source === "local" && !phase.lesson_html_path && !phase.lesson_md_path
  );
}

export function phaseState(phase: CoursePhase): PhaseState {
  if (readAt(phase)) return "read";
  if (isPlanned(phase)) return "planned";
  if (
    phase.status === "taught" &&
    (phase.source === "platform" || phase.lesson_html_path)
  ) {
    return "unread";
  }
  return phase.status === "pending" ? "pending" : "waiting";
}

/** The A and B parts of a split phase share its order number. */
export function phaseParts(list: CoursePhase[], phase: CoursePhase): CoursePhase[] {
  return list.filter((p) => p.phase_order === phase.phase_order);
}
