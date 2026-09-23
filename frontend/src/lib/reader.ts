/**
 * The phone reader's data layer: static files, no API.
 *
 * `backend/src/hq/reader_export.py` writes `public/reader/` on his machine and
 * he commits it. Everything here therefore reads the deployment's own files.
 * Nothing in this module may call `/api`: the point of the reader is that it
 * works when the Mac that runs the backend is asleep.
 */

import {
  CONCEPT_RE,
  isConceptVerdict,
  type ConceptVerdict,
} from "@/lib/concept-taps";

export type ReaderLesson = {
  /** Page file name, without `.html` — also the URL segment under /read. */
  file: string;
  title: string;
  one_liner: string;
  date: string | null;
  read: boolean;
};

export type ReaderPhase = ReaderLesson & {
  slug: string;
  minutes: number | null;
};

export type ReaderArticle = ReaderLesson & {
  topic: string;
  kind: string;
};

export type ReaderCourse = {
  slug: string;
  title: string;
  phases: ReaderPhase[];
};

export type ReaderIndex = {
  built_at: string;
  courses: ReaderCourse[];
  articles: ReaderArticle[];
};

export const readerKeys = {
  index: ["reader", "index"] as const,
  page: (file: string) => ["reader", "page", file] as const,
};

/** Strip the extension so a file name can be a URL segment, and back again. */
export const pageSlug = (file: string) => file.replace(/\.html$/u, "");

async function readFile(path: string, as: "json" | "text") {
  // `cache: "no-store"`: a push replaces these files, and a phone that kept
  // yesterday's copy would show a lesson he has already had rebuilt.
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? "That lesson is not in this deployment. Run `hq.cli export-reader`, commit and push."
        : `Could not load ${path} (${response.status})`,
    );
  }
  return as === "json" ? response.json() : response.text();
}

export const readerApi = {
  index: () => readFile("/reader/index.json", "json") as Promise<ReaderIndex>,
  page: (slug: string) =>
    readFile(
      `/reader/lessons/${encodeURIComponent(slug)}.html`,
      "text",
    ) as Promise<string>,
};

/**
 * "Got it" / "Lost me" on the phone.
 *
 * The phone holds no credential for the backend, by design, so a tap stays
 * here: in this page's own storage (the lesson frame has none), one key per
 * lesson file and concept. Storage can be missing or refuse (private mode, a
 * full quota), so every access is guarded and a failure only means the
 * answer is not remembered. The console records taps for the next outline.
 */
const TAP_PREFIX = "hq:tap:";

type StoredTap = { verdict: ConceptVerdict; at: string };

export function loadTaps(file: string): Record<string, ConceptVerdict> {
  const out: Record<string, ConceptVerdict> = {};
  try {
    const store = window.localStorage;
    const prefix = `${TAP_PREFIX}${file}:`;
    for (let i = 0; i < store.length; i++) {
      const key = store.key(i);
      if (!key?.startsWith(prefix)) continue;
      const concept = key.slice(prefix.length);
      if (!CONCEPT_RE.test(concept)) continue;
      const stored = JSON.parse(store.getItem(key) ?? "null") as Partial<StoredTap> | null;
      if (stored && isConceptVerdict(stored.verdict)) out[concept] = stored.verdict;
    }
  } catch {
    // No storage here (or on the server): the answers are simply not remembered.
  }
  return out;
}

export function saveTap(file: string, concept: string, verdict: ConceptVerdict) {
  try {
    const value: StoredTap = { verdict, at: new Date().toISOString() };
    window.localStorage.setItem(`${TAP_PREFIX}${file}:${concept}`, JSON.stringify(value));
  } catch {
    // As above: shown for this visit, not kept.
  }
}
