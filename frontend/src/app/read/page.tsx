"use client";

import { useState } from "react";
import Link from "next/link";
import { Play } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PlaylistRow, ShelfButton } from "@/components/features/reader/playlist";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { pageSlug, readerApi, readerKeys } from "@/lib/reader";
import {
  dayOf,
  isRead,
  monthOf,
  phaseLabel,
  progressOf,
  shelvesOf,
  totalTime,
  type Shelf,
  type ShelfItem,
} from "@/lib/reader-shelves";
import { cn } from "@/lib/utils";
import { useReaderSync } from "@/hooks/use-reader-sync";

/**
 * The library: courses as playlists, plus the articles.
 *
 * Deliberately outside the `(console)` group, like `/learn-full`: it keeps the
 * root layout and loses the shell, the sidebar and — the part that matters —
 * the auth guard, which would otherwise send a phone to a login page for a
 * backend it cannot reach. `providers.tsx` exempts this path by name.
 *
 * It reads `public/reader`, which the build makes from `learning/lessons`.
 * So this page has no Teach button and no live feed: those need the backend.
 *
 * Layout: a side column lists the shelves (each course with its progress,
 * then Articles); the main column is the picked shelf as a numbered
 * playlist. On a phone the shelves become a row of chips. The picked shelf
 * is the URL hash, so "Library" on a lesson page comes back to it.
 */
export default function ReadPage() {
  useReaderSync();
  const index = useQuery({
    queryKey: readerKeys.index,
    queryFn: readerApi.index,
    staleTime: 60_000,
  });
  const [picked, setPicked] = useState(() =>
    typeof window === "undefined" ? "" : decodeURIComponent(window.location.hash.slice(1)),
  );

  if (index.isPending) {
    return (
      <Shell>
        <div className="reader-library">
          <div className="space-y-3">
            <Skeleton className="h-8 w-32" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
          <div className="space-y-3">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
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

  const shelves = shelvesOf(index.data);
  if (!shelves.length) {
    return (
      <Shell>
        <EmptyState title="No lessons in this deployment">
          Push lesson pages to <code>learning/lessons</code> on main. The
          build runs <code>npm run reader</code> and ships them.
        </EmptyState>
      </Shell>
    );
  }

  const shelf = shelves.find((s) => s.key === picked) ?? shelves[0];
  const pick = (key: string) => {
    setPicked(key);
    window.history.replaceState(null, "", `#${encodeURIComponent(key)}`);
    window.scrollTo({ top: 0 });
  };
  const courses = shelves.filter((s) => s.kind === "course");
  const articles = shelves.find((s) => s.kind === "articles");
  const updated = `Updated ${dayOf(index.data.built_at)}`;

  return (
    <Shell>
      <div className="reader-library">
        {/* Side column, wide screens. */}
        <nav aria-label="Library" className="hidden space-y-6 md:sticky md:top-6 md:block">
          <header className="px-3">
            <h1 className="text-xl font-semibold tracking-tight">Reading</h1>
            <p className="text-muted-foreground text-xs">{updated}</p>
          </header>
          <div className="space-y-1">
            <p className="text-muted-foreground px-3 pb-1 text-[11px] font-medium tracking-wider uppercase">
              Courses
            </p>
            {courses.map((s) => (
              <ShelfButton key={s.key} shelf={s} active={s.key === shelf.key} onSelect={() => pick(s.key)} />
            ))}
          </div>
          {articles ? (
            <div className="space-y-1">
              <p className="text-muted-foreground px-3 pb-1 text-[11px] font-medium tracking-wider uppercase">
                More
              </p>
              <ShelfButton shelf={articles} active={articles.key === shelf.key} onSelect={() => pick(articles.key)} />
            </div>
          ) : null}
        </nav>

        {/* Header and shelf chips, phones. */}
        <div className="space-y-3 md:hidden">
          <header>
            <h1 className="text-xl font-semibold tracking-tight">Reading</h1>
            <p className="text-muted-foreground text-xs">{updated}</p>
          </header>
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
            {shelves.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => pick(s.key)}
                aria-current={s.key === shelf.key ? "true" : undefined}
                className={cn(
                  "shrink-0 rounded-full border px-3 py-1.5 text-sm whitespace-nowrap transition-colors",
                  s.key === shelf.key
                    ? "bg-primary text-primary-foreground border-primary"
                    : "hover:bg-accent/50",
                )}
              >
                {s.title}
              </button>
            ))}
          </div>
        </div>

        <ShelfView shelf={shelf} />
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto w-full max-w-5xl px-4 py-6 pb-16 md:px-6 md:py-10">{children}</main>;
}

function ShelfView({ shelf }: { shelf: Shelf }) {
  const { done, total, percent } = progressOf(shelf);
  const next = shelf.items.find((i) => !isRead(i)) ?? null;

  if (shelf.kind === "articles") {
    const months = new Map<string, ShelfItem[]>();
    for (const item of shelf.items) {
      const month = monthOf(item.date);
      months.set(month, [...(months.get(month) ?? []), item]);
    }
    return (
      <section className="min-w-0 space-y-6">
        <header className="space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">Articles</h2>
          <p className="text-muted-foreground text-sm tabular-nums">
            {total} articles · {done} read
          </p>
        </header>
        {[...months].map(([month, items]) => (
          <div key={month} className="space-y-2">
            <h3 className="text-muted-foreground text-xs font-medium tracking-wider uppercase">{month}</h3>
            <ol className="divide-y overflow-hidden rounded-lg border">
              {items.map((item) => (
                <li key={item.file}>
                  <PlaylistRow item={item} read={isRead(item)} next={false} />
                </li>
              ))}
            </ol>
          </div>
        ))}
      </section>
    );
  }

  const time = totalTime(shelf);
  const nextLabel = next ? phaseLabel(next) : null;
  return (
    <section className="min-w-0 space-y-5">
      <header className="space-y-3">
        <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
          Course · {total} phases{time ? ` · ${time}` : ""}
        </p>
        <h2 className="text-2xl leading-tight font-semibold tracking-tight text-balance">{shelf.title}</h2>
        <div className="flex max-w-sm items-center gap-3">
          <Progress value={percent} />
          <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
            {done} of {total} read
          </span>
        </div>
        {next ? (
          <Button asChild size="lg" className="max-w-full">
            <Link href={`/read/${pageSlug(next.file)}`}>
              <Play aria-hidden data-icon="inline-start" />
              <span className="truncate">
                {done ? "Continue" : "Start"}
                {nextLabel ? ` with phase ${nextLabel}` : ""}
              </span>
            </Link>
          </Button>
        ) : (
          <p className="text-muted-foreground text-sm">Every phase is read.</p>
        )}
      </header>
      <ol className="divide-y overflow-hidden rounded-lg border">
        {shelf.items.map((item) => (
          <li key={item.file}>
            <PlaylistRow item={item} read={isRead(item)} next={item.file === next?.file} />
          </li>
        ))}
      </ol>
    </section>
  );
}
