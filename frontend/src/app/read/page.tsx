"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  pageSlug,
  readerApi,
  readerKeys,
  type ReaderArticle,
  type ReaderPhase,
} from "@/lib/reader";
import { markedReadHere } from "@/lib/reader-sync";
import { useReaderSync } from "@/hooks/use-reader-sync";

/**
 * The library, built for a phone.
 *
 * Deliberately outside the `(console)` group, like `/learn-full`: it keeps the
 * root layout and loses the shell, the sidebar and — the part that matters —
 * the auth guard, which would otherwise send a phone to a login page for a
 * backend it cannot reach. `providers.tsx` exempts this path by name.
 *
 * It reads `public/reader`, which he exports and pushes. So this page has no
 * Teach button and no live feed: those need the backend. The two things he
 * does while reading, "Mark read" and a tap per concept, live on the lesson
 * page and reach the backend through `lib/reader-sync.ts` when the phone is
 * on his tailnet; loading this page sends whatever was kept meanwhile. A
 * lesson he marked read here shows as read before the next export says so.
 */
export default function ReadPage() {
  useReaderSync();
  const index = useQuery({
    queryKey: readerKeys.index,
    queryFn: readerApi.index,
    staleTime: 60_000,
  });

  if (index.isPending) {
    return (
      <Shell>
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </Shell>
    );
  }

  if (index.isError) {
    return (
      <Shell>
        <ErrorState
          message={(index.error as Error).message}
          onRetry={() => void index.refetch()}
          retrying={index.isRefetching}
        />
      </Shell>
    );
  }

  const { courses, articles, built_at: builtAt } = index.data;
  const nothing = courses.length === 0 && articles.length === 0;

  return (
    <Shell>
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Reading</h1>
        <p className="text-muted-foreground text-xs">
          {nothing ? "Nothing exported yet" : `Updated ${dayOf(builtAt)}`}
        </p>
      </header>

      {nothing ? (
        <EmptyState title="No lessons in this deployment">
          Run <code>uv run python -m hq.cli export-reader</code> on the machine
          that holds the library, then commit and push.
        </EmptyState>
      ) : null}

      {courses.map((course) => (
        <section key={course.slug} className="space-y-3">
          <h2 className="text-base font-semibold">{course.title}</h2>
          <ul className="space-y-2">
            {course.phases.map((phase) => (
              <li key={phase.slug}>
                <Row lesson={phase} meta={phaseMeta(phase)} />
              </li>
            ))}
          </ul>
        </section>
      ))}

      {articles.length ? (
        <section className="space-y-3">
          <h2 className="text-base font-semibold">Articles</h2>
          <ul className="space-y-2">
            {articles.map((article) => (
              <li key={article.file}>
                <Row lesson={article} meta={articleMeta(article)} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </Shell>
  );
}

/** One column, thumb-width, with room under the last row on a phone. */
function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-2xl space-y-8 px-4 py-6 pb-16">
      {children}
    </main>
  );
}

/**
 * A tap target, not a link in a paragraph. The whole card is the hit area
 * because this is read one-handed, walking.
 */
function Row({
  lesson,
  meta,
}: {
  lesson: { file: string; title: string; one_liner: string; read: boolean };
  meta: string;
}) {
  return (
    <Link
      href={`/read/${pageSlug(lesson.file)}`}
      className="hover:bg-accent/50 active:bg-accent block rounded-lg border p-4 transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm leading-snug font-medium">{lesson.title}</p>
        {lesson.read || markedReadHere(lesson.file) ? (
          <Badge variant="outline" className="shrink-0 text-[10px]">
            Read
          </Badge>
        ) : null}
      </div>
      {lesson.one_liner ? (
        <p className="text-muted-foreground mt-1 line-clamp-2 text-sm">
          {lesson.one_liner}
        </p>
      ) : null}
      {meta ? (
        <p className="text-muted-foreground mt-2 text-xs">{meta}</p>
      ) : null}
    </Link>
  );
}

function phaseMeta(phase: ReaderPhase) {
  return [phase.minutes ? `${phase.minutes} min` : "", dayOf(phase.date)]
    .filter(Boolean)
    .join(" · ");
}

function articleMeta(article: ReaderArticle) {
  return [article.topic, dayOf(article.date)].filter(Boolean).join(" · ");
}

/** A date he can place, with no time: nothing here changes within a day. */
function dayOf(value: string | null) {
  if (!value) return "";
  const when = new Date(value);
  return Number.isNaN(when.getTime())
    ? ""
    : when.toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      });
}
