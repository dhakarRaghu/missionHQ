/**
 * The reader index as shelves: one per course, plus one for articles.
 *
 * A shelf is what the library lists in its side column and what a lesson
 * page shows as its playlist, so both pages read it from here.
 */

import type {
  ReaderArticle,
  ReaderIndex,
  ReaderLesson,
  ReaderPhase,
} from "@/lib/reader";
import { markedReadHere } from "@/lib/reader-sync";

export type ShelfItem = ReaderPhase | ReaderArticle;

export type Shelf = {
  /** Course slug, or `ARTICLES` for the articles shelf. Also the URL hash. */
  key: string;
  title: string;
  kind: "course" | "articles";
  items: ShelfItem[];
};

export const ARTICLES = "articles";

export function shelvesOf(index: ReaderIndex): Shelf[] {
  const courses: Shelf[] = index.courses.map((course) => ({
    key: course.slug,
    title: course.title,
    kind: "course",
    items: course.phases,
  }));
  return index.articles.length
    ? [...courses, { key: ARTICLES, title: "Articles", kind: "articles", items: index.articles }]
    : courses;
}

/** The shelf a lesson file sits on, or null when the index has no such file. */
export function shelfOf(index: ReaderIndex, file: string): Shelf | null {
  return shelvesOf(index).find((s) => s.items.some((i) => i.file === file)) ?? null;
}

/** Read at the last build, or marked read on this device since. */
export function isRead(lesson: ReaderLesson): boolean {
  return lesson.read || markedReadHere(lesson.file);
}

export function progressOf(shelf: Shelf, extraRead?: string) {
  const done = shelf.items.filter((i) => isRead(i) || i.file === extraRead).length;
  return { done, total: shelf.items.length, percent: shelf.items.length ? (done / shelf.items.length) * 100 : 0 };
}

/** "2A" for `…-phase-02a-…`, or null for an article. */
export function phaseLabel(item: ShelfItem): string | null {
  if (!("slug" in item)) return null;
  const m = item.slug.match(/-phase-(\d+)([a-z]?)-/u);
  return m ? `${Number(m[1])}${m[2].toUpperCase()}` : null;
}

/** Total reading time of a shelf, as "9 h 40 min", or "" when unknown. */
export function totalTime(shelf: Shelf): string {
  const minutes = shelf.items.reduce((sum, i) => sum + ("minutes" in i ? (i.minutes ?? 0) : 0), 0);
  if (!minutes) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return [h ? `${h} h` : "", m ? `${m} min` : ""].filter(Boolean).join(" ");
}

/** A date he can place, with no time: nothing here changes within a day. */
export function dayOf(value: string | null) {
  if (!value) return "";
  const when = new Date(value);
  return Number.isNaN(when.getTime())
    ? ""
    : when.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function monthOf(value: string | null) {
  if (!value) return "Undated";
  const when = new Date(value);
  return Number.isNaN(when.getTime())
    ? "Undated"
    : when.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}
