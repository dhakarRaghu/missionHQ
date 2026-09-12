import { getJson, queryString, sendJson } from "@/lib/api/request";

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
  /** Tutor's own score out of 60. */
  score: number;
  /** The article urls the lesson was built from. */
  sources: string[];
  created_at: string;
}

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

export const learningKeys = {
  all: ["learning"] as const,
  lessons: ["learning", "lessons"] as const,
  page: (path: string) => ["learning", "page", path] as const,
  note: (path: string) => ["learning", "note", path] as const,
  requests: ["learning", "requests"] as const,
  readings: (status: string) => ["learning", "readings", status] as const,
};

export const learningApi = {
  lessons: (limit = 30) =>
    getJson<Lesson[]>(`/learning/lessons${queryString({ limit })}`),
  page: (path: string) =>
    getJson<LessonPage>(`/learning/page${queryString({ path })}`),
  note: (path: string) =>
    getJson<LessonNote>(`/learning/note${queryString({ path })}`),
  requests: () => getJson<LearningRequest[]>("/learning/requests"),
  addRequest: (text: string) =>
    sendJson<{ id: string }>("POST", "/learning/requests", { text }),
  dropRequest: (id: string) =>
    sendJson<{ ok: boolean }>("POST", `/learning/requests/${id}/drop`),
  readings: (status = "", limit = 50) =>
    getJson<Reading[]>(`/learning/readings${queryString({ status, limit })}`),
};
