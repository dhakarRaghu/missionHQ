"use client";

import Link from "next/link";
import { Check, ChevronRight, FileText } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { pageSlug } from "@/lib/reader";
import { dayOf, phaseLabel, progressOf, type Shelf, type ShelfItem } from "@/lib/reader-shelves";
import { cn } from "@/lib/utils";

/** The round marker at the start of a row: phase number, article icon, or a tick. */
export function Marker({ item, read, current = false }: { item: ShelfItem; read: boolean; current?: boolean }) {
  const label = phaseLabel(item);
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-medium tabular-nums",
        read && "bg-primary text-primary-foreground border-primary",
        !read && current && "border-primary text-foreground",
        !read && !current && "text-muted-foreground",
      )}
    >
      {read ? <Check className="size-3.5" /> : label ?? <FileText className="size-3.5" />}
    </span>
  );
}

function meta(item: ShelfItem) {
  const minutes = "minutes" in item && item.minutes ? `${item.minutes} min` : "";
  const topic = "topic" in item ? item.topic : "";
  return [minutes, topic, dayOf(item.date)].filter(Boolean).join(" · ");
}

/** One lesson in the library's playlist. The whole row is the tap target. */
export function PlaylistRow({ item, read, next }: { item: ShelfItem; read: boolean; next: boolean }) {
  const label = phaseLabel(item);
  return (
    <Link
      href={`/read/${pageSlug(item.file)}`}
      className="hover:bg-accent/50 active:bg-accent flex items-start gap-3 px-3 py-3.5 transition-colors sm:px-4"
    >
      <Marker item={item} read={read} current={next} />
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-snug font-medium">
          {label ? <span className="text-muted-foreground mr-1.5 font-normal">Phase {label}</span> : null}
          {item.title}
        </p>
        {item.one_liner ? (
          <p className="text-muted-foreground mt-1 line-clamp-2 text-sm">{item.one_liner}</p>
        ) : null}
        <p className="text-muted-foreground mt-1.5 text-xs">
          {next ? <span className="text-foreground mr-1.5 font-medium">Up next</span> : null}
          {meta(item)}
        </p>
      </div>
      <ChevronRight aria-hidden className="text-muted-foreground mt-1 size-4 shrink-0" />
    </Link>
  );
}

/** A shelf in the side column: its name and how much of it is read. */
export function ShelfButton({
  shelf,
  active,
  onSelect,
}: {
  shelf: Shelf;
  active: boolean;
  onSelect: () => void;
}) {
  const { done, total, percent } = progressOf(shelf);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={cn(
        "w-full rounded-lg px-3 py-2.5 text-left transition-colors",
        active ? "bg-accent" : "hover:bg-accent/50",
      )}
    >
      <span className="block text-sm leading-snug font-medium">{shelf.title}</span>
      <span className="text-muted-foreground mt-1 block text-xs tabular-nums">
        {shelf.kind === "course" ? `${done} of ${total} read` : `${total} articles · ${done} read`}
      </span>
      {shelf.kind === "course" ? <Progress value={percent} className="mt-2" /> : null}
    </button>
  );
}
