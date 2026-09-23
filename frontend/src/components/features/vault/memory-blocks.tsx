"use client";

import { Progress } from "@/components/ui/progress";
import { commitActor, type MemoryBlock } from "@/lib/api/vault";
import { cn } from "@/lib/utils";

const WARN_PCT = 75;
const FULL_PCT = 90;

/** Fill bars for the core memory blocks (chars / cap). Clicking one opens it. */
export function MemoryBlocks({
  blocks,
  selected,
  onSelect,
}: {
  blocks: MemoryBlock[];
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  if (!blocks.length) return null;
  return (
    <section aria-label="Memory blocks" className="flex flex-col gap-1">
      <h2 className="text-muted-foreground px-2 text-xs font-medium tracking-wide uppercase">
        Memory blocks
      </h2>
      <ul className="flex flex-col gap-0.5">
        {blocks.map((block) => {
          const active = selected === block.path;
          const actor = block.last_commit
            ? commitActor(block.last_commit.message)
            : null;
          const tone =
            block.pct >= FULL_PCT
              ? "[&_[data-slot=progress-indicator]]:bg-status-danger"
              : block.pct >= WARN_PCT
                ? "[&_[data-slot=progress-indicator]]:bg-status-blocked"
                : null;
          return (
            <li key={block.path}>
              <button
                type="button"
                onClick={() => onSelect(block.path)}
                aria-current={active ? "true" : undefined}
                className={cn(
                  "hover:bg-muted w-full rounded-md px-2 py-1.5 text-left text-sm",
                  active && "bg-muted font-medium",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-baseline gap-1.5">
                    <span className="truncate">
                      {block.path.replace(/^memory\//, "")}
                    </span>
                    {actor ? (
                      <span
                        className="text-muted-foreground shrink-0 text-xs"
                        title={`Last written by ${actor}`}
                      >
                        {actor}
                      </span>
                    ) : null}
                  </span>
                  <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                    {block.chars}/{block.cap}
                  </span>
                </div>
                <Progress
                  value={Math.min(100, block.pct)}
                  aria-label={`${block.path} ${block.pct}% full`}
                  className={cn("mt-1.5", tone)}
                />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
