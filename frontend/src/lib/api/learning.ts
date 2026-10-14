import { getJson, queryString, sendJson } from "@/lib/api/request";
import type { ConceptVerdict } from "@/lib/concept-taps";

// Client, types and query keys for the daily learning journey
// (GET /api/learning/*). Tutor writes one lesson a morning from the articles
// hunter read in full; these are what the Learn view reads back.

export interface Lesson {
  id: string;
  /** YYYY-MM-DD. One lesson per day, so this is its identity. */
  lesson_date: string;
  title: string;
  /** The line he reads on his phone before deciding to open it. */
  one_liner: string;
  topic: string;
  /** Vault path of the markdown lesson. */
  md_path: string;
  /** Vault path of the self-contained page with the diagram. May be empty. */
  html_path: string;
  /** Tutor's own score: out of 90 for a topic article, 130 for a course
   * lesson. The label printed the wrong denominator twice ("69/60"), so use
   * `SCORE_OUT_OF` rather than writing a number next to it. */
  score: number;
  /** The article urls the lesson was built from. */
  sources: string[];
  created_at: string;
  /** "topic" is the daily open-web lesson; "course" is a phase of his own
   * study material. Two a day, so the date alone no longer identifies one. */
  kind: "topic" | "course" | "lab" | "review";
  /** Which day an article came from: spine_incident, spine_evidence, paper,
   * frontier or revision. Empty on course lessons and older rows. */
  article_kind?: string;
  /** The phase slug, when this is a course lesson. */
  course_slug: string;
  /** Until this is set, the evening run will not start the next phase. */
  read_at: string | null;
  /** A daily article orbits the active course phase. The slug of that phase,
   * or "" when the article was written before articles orbited one. Optional
   * because older rows predate the field. */
  phase_slug?: string;
  /** How the article stands to that phase, or "" when it has none. */
  relationship?: ArticleRelationship | "";
  phase_title?: string | null;
  phase_course?: string | null;
  review_status?: ReviewStatus;
  review_score?: number | null;
}

/** What an independent reviewer made of a lesson after running its lab. */
export type ReviewStatus = "pending" | "passed" | "flagged" | "failed" | "none";

/** How a daily article relates to the course phase it orbits. */
export type ArticleRelationship =
  | "fails"
  | "measures"
  | "applies"
  | "updates"
  | "challenges"
  | "extends";

/** Self-score denominators. A course lesson is scored out of 130 and a topic
 * article out of 90; both were once printed as /80. */
export const SCORE_OUT_OF: Record<Lesson["kind"], number> = {
  course: 130,
  topic: 90,
  // The weekend pieces are not scored against a rubric; they carry a topic
  // article's denominator when tutor scores one at all.
  lab: 90,
  review: 90,
};

/** One lesson page as markup, with a Content-Security-Policy already injected
 * by the API. It is rendered inside a sandboxed frame and never in this
 * origin: tutor generates it from web-derived digests, so it is untrusted. */
export interface LessonPage {
  path: string;
  html: string;
}

export interface Reading {
  url: string;
  title: string;
  author: string;
  source: string;
  topic: string;
  why: string;
  score: number;
  status: "found" | "queued" | "digested" | "taught" | "skipped";
  digest_path: string;
  lesson_id: string | null;
  first_seen: string;
  last_seen: string;
}

/** The markdown of one lesson. Lessons live in the repo under
 * `learning/lessons/`, not the vault, so the console reads them from the
 * learning API — the vault is the agents' memory layer and he should never
 * have to open it to read his own lesson. */
export interface LessonNote {
  path: string;
  content: string;
}

/** Something he asked to learn about, typed into the Learn page. The next
 * morning run serves these before it works through the roster. */
export interface LearningRequest {
  id: string;
  text: string;
  status: "open" | "served" | "dropped";
  created_at: string;
  served_at: string | null;
}

/** One of his own courses on the study platform, and how far tutor has got
 * through it. Phases are taught one a day, gated on the last being read. */
export interface Course {
  course: string;
  phases: number;
  taught: number;
  minutes: number;
  next_title: string | null;
  /** Exactly one course is active; the daily article orbits that one. */
  active: boolean;
  /** What the course is for, in a line. Optional: the backend adds these two
   * later, so every reader must cope with them being absent. */
  description?: string;
  /** Where the syllabus came from — his study platform, or written here. */
  source?: "platform" | "local";
  /** The course's own name, and its place on his path (999 = not on it). */
  title?: string;
  course_order?: number;
}

/** Where a curriculum module stands: whether the research behind it exists,
 * and whether it is ready to be turned into a course. */
export type CurriculumStatus = "complete" | "ready" | "partial" | "not started";

/**
 * One module of the applied-AI curriculum — the plan, not the courses.
 *
 * Most of the twenty-two modules have no course yet. The page shows all of
 * them so the plan is visible as a plan, and a module whose course exists
 * carries its `topic`, which is how the two are linked.
 */
export interface CurriculumModule {
  /** 1 to 22, and the order the modules are listed in. */
  number: number;
  /** Model, Knowledge, Agents, Evals, Infrastructure, Security or Product. */
  layer: string;
  title: string;
  status: CurriculumStatus;
  /** The research file under `_curriculum/`, or "brief below" when the only
   * brief is the block in the README. */
  research: string;
  /** A plan, not a number: "7", "3 to 4", "to be sized". */
  planned_phases: string;
  /** Its place on the core path of eight, or 0 when it is not on it. */
  core_order: number;
  /** The published course, or "" when no course exists for the module yet. */
  topic: string;
  /** Only sent when `topic` names a course that exists. */
  phases?: number;
  taught?: number;
  read?: number;
}

/** The whole curriculum, with how many modules stand at each status. */
export interface Curriculum {
  modules: CurriculumModule[];
  counts: Record<CurriculumStatus, number>;
}

/** One phase of a course, as it appears on his study platform. */
export interface CoursePhase {
  slug: string;
  phase_order: number;
  title: string;
  summary: string;
  difficulty: string;
  minutes: number;
  status: "pending" | "taught" | "skipped";
  /** The original module on his own study platform. */
  url: string;
  lesson_id: string | null;
  /** The article written for this phase — deeper than the original, with the
   * corrections and the production failure. This is the one to read. */
  lesson_html_path: string | null;
  lesson_md_path: string | null;
  /** The article's own title and takeaway, which are not the module's. */
  lesson_title: string | null;
  lesson_one_liner: string | null;
  lesson_date: string | null;
  lesson_score: number | null;
  lesson_read_at: string | null;
  /** Read is a fact about the phase: a published phase can be read before
   * Mission HQ has added anything to it. Prefer this over `lesson_read_at`;
   * optional because older API builds do not send it. */
  read_at?: string | null;
  /** The phase's spec, as the syllabus states it: the question the phase
   * answers, the ground it covers, the exercise and the way out of it.
   * Optional — the backend adds these later, so render only what is there. */
  question?: string;
  /** Written here as a spec, or a module on his study platform. */
  source?: "platform" | "local";
  sections?: string[];
  lab?: string;
  test_out?: string;
  /** The independent reviewer's verdict on the phase's lesson, after it ran
   * the lab. Null until the phase is taught. Optional for older rows. */
  lesson_review_status?: ReviewStatus | null;
  lesson_review_score?: number | null;
  /** One finding per line, "location → problem → fix". */
  lesson_review_notes?: string | null;
}

/** A phase's original text, as written with Claude. What he reads is the
 * enhanced page Mission HQ builds from it (the lesson's html_path); this is
 * shown until that exists. A planned (local) phase has `published: false`. */
export interface PhaseContent {
  slug: string;
  source: "platform" | "local";
  published: boolean;
  title?: string;
  summary?: string;
  minutes?: number;
  tags?: string[];
  /** The full published markdown. */
  content: string;
  /** The phase on the study platform. */
  original_url: string;
}

export const learningKeys = {
  all: ["learning"] as const,
  lessons: ["learning", "lessons"] as const,
  page: (path: string) => ["learning", "page", path] as const,
  note: (path: string) => ["learning", "note", path] as const,
  requests: ["learning", "requests"] as const,
  courses: ["learning", "courses"] as const,
  curriculum: ["learning", "curriculum"] as const,
  coursePhases: (course: string) =>
    ["learning", "courses", course] as const,
  phaseContent: (course: string, slug: string) =>
    ["learning", "phase-content", course, slug] as const,
  readings: (status: string) => ["learning", "readings", status] as const,
  signals: (lessonId: string) => ["learning", "signals", lessonId] as const,
};

/** Every "Got it" / "Lost me" tap on one lesson, and his current answer per
 * concept (the latest tap wins). */
export interface LessonSignals {
  lesson_id: string;
  verdicts: Record<string, ConceptVerdict>;
  taps: { concept: string; verdict: ConceptVerdict; at: string; via: string }[];
}

export const learningApi = {
  lessons: (limit = 30, kind = "") =>
    getJson<Lesson[]>(`/learning/lessons${queryString({ limit, kind })}`),
  page: (path: string) =>
    getJson<LessonPage>(`/learning/page${queryString({ path })}`),
  note: (path: string) =>
    getJson<LessonNote>(`/learning/note${queryString({ path })}`),
  /** Prepare a lesson as a post for his own site. Writes a draft file there
   * and nothing else: no commit, no push, no publish. */
  draftPost: (lessonDate: string, section: "writing" | "papershelf", kind: string) =>
    sendJson<{ started: boolean; reason?: string; task_id?: string; title?: string }>(
      "POST",
      `/learning/lessons/${lessonDate}/post${queryString({ section, kind })}`,
    ),
  markRead: (lessonDate: string, kind: string) =>
    sendJson<{ ok: boolean; title: string }>(
      "POST",
      `/learning/lessons/${lessonDate}/read${queryString({ kind })}`,
    ),
  courses: () => getJson<Course[]>("/learning/courses"),
  /** The applied-AI plan behind the courses: 22 modules, most without a
   * course yet. Read from the repo, so it changes only when a research run
   * writes to it. */
  curriculum: () => getJson<Curriculum>("/learning/curriculum"),
  coursePhases: (course: string) =>
    getJson<CoursePhase[]>(`/learning/courses/${encodeURIComponent(course)}`),
  teachPhase: (course: string, slug: string) =>
    sendJson<{ started: boolean; reason?: string; title?: string }>(
      "POST",
      `/learning/courses/${encodeURIComponent(course)}/phases/${encodeURIComponent(slug)}/teach`,
    ),
  phaseContent: (course: string, slug: string) =>
    getJson<PhaseContent>(
      `/learning/courses/${encodeURIComponent(course)}/phases/${encodeURIComponent(slug)}/content`,
    ),
  /** Marks the phase read, which unlocks the next one for the evening run. */
  markPhaseRead: (course: string, slug: string) =>
    sendJson<{ ok: boolean; title: string }>(
      "POST",
      `/learning/courses/${encodeURIComponent(course)}/phases/${encodeURIComponent(slug)}/read`,
    ),
  activateCourse: (course: string) =>
    sendJson<{ active: string }>(
      "POST",
      `/learning/courses/${encodeURIComponent(course)}/activate`,
    ),
  requests: () => getJson<LearningRequest[]>("/learning/requests"),
  addRequest: (text: string) =>
    sendJson<{ id: string }>("POST", "/learning/requests", { text }),
  dropRequest: (id: string) =>
    sendJson<{ ok: boolean }>("POST", `/learning/requests/${id}/drop`),
  readings: (status = "", limit = 50) =>
    getJson<Reading[]>(`/learning/readings${queryString({ status, limit })}`),
  signals: (lessonId: string) =>
    getJson<LessonSignals>(`/learning/lessons/${encodeURIComponent(lessonId)}/signals`),
  /** One tap from the lesson page. The next outline of the course reads the
   * "lost me" answers. */
  addSignal: (lessonId: string, concept: string, verdict: ConceptVerdict) =>
    sendJson<{ concept: string; verdict: ConceptVerdict }>(
      "POST",
      `/learning/lessons/${encodeURIComponent(lessonId)}/signals`,
      { concept, verdict },
    ),
};
