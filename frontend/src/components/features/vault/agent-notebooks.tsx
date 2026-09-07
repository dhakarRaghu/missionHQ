"use client";

import type { VaultFile, VaultFolder, VaultNode } from "@/lib/api/vault";
import { exactTime, timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

const DIR = "memory/agents/";

function filesUnder(node: VaultNode, prefix: string, out: VaultFile[] = []) {
  if (node.kind === "file") {
    if (node.path.startsWith(prefix)) out.push(node);
    return out;
  }
  for (const child of node.children) filesUnder(child, prefix, out);
  return out;
}

/**
 * Each agent's own notebook, listed apart from the shared memory blocks.
 *
 * These are private working memory: an agent rewrites its own at the end of
 * every run and no other agent reads it. Grouping them separately makes the
 * difference visible, and makes a stale one easy to spot by its date.
 */
export function AgentNotebooks({
  root,
  selected,
  onSelect,
}: {
  root: VaultFolder;
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  const files = filesUnder(root, DIR).sort((a, b) =>
    a.name.localeCompare(b.name),
  );
  if (!files.length) return null;

  return (
    <section aria-label="Agent notebooks" className="flex flex-col gap-1">
      <h2 className="text-muted-foreground px-2 text-xs font-medium tracking-wide uppercase">
        Agent notebooks
      </h2>
      <ul className="flex flex-col gap-0.5">
        {files.map((file) => {
          const active = selected === file.path;
          return (
            <li key={file.path}>
              <button
                type="button"
                onClick={() => onSelect(file.path)}
                aria-current={active ? "true" : undefined}
                className={cn(
                  "hover:bg-muted flex w-full items-baseline justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                  active && "bg-muted font-medium",
                )}
              >
                <span className="truncate">{file.name.replace(/\.md$/, "")}</span>
                <span
                  className="text-muted-foreground shrink-0 text-xs whitespace-nowrap"
                  title={exactTime(file.mtime)}
                >
                  {timeAgo(file.mtime)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
