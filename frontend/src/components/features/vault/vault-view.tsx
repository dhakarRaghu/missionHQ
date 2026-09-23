"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "@/components/error-state";
import { MemoryBlocks } from "@/components/features/vault/memory-blocks";
import { NoteView } from "@/components/features/vault/note-view";
import { VaultOverview } from "@/components/features/vault/vault-overview";
import { VaultSearch } from "@/components/features/vault/vault-search";
import { AgentNotebooks } from "@/components/features/vault/agent-notebooks";
import { VaultTree } from "@/components/features/vault/vault-tree";
import { Skeleton } from "@/components/ui/skeleton";
import { vaultApi, vaultKeys } from "@/lib/api/vault";

/** What each core block is for, in the owner's terms. */
const BLURBS: Record<string, string> = {
  "memory/user.md":
    "What the agents know about you: your goals, your audience, how you like things done. Every agent reads this before it works.",
  "memory/active_projects.md":
    "What you are working on now. Sage consolidates it every night from what changed that day.",
  "memory/rules.md":
    "Standing rules. Only you write here: an agent can propose a rule, but never mint one.",
};

function blurbFor(path: string): string | undefined {
  if (BLURBS[path]) return BLURBS[path];
  if (path.startsWith("memory/agents/")) {
    const name = path.slice("memory/agents/".length).replace(/\.md$/, "");
    return `${name}'s own notebook. It rewrites this at the end of every run, and no other agent reads it.`;
  }
  return undefined;
}

/**
 * Search on top, memory blocks and folder tree on the left, the selected
 * note on the right. The selection lives in the URL (?path=...) so a note
 * can be deep-linked and the back button moves between notes.
 */
export function VaultView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const selected = params.get("path");

  const select = useCallback(
    (path: string) => {
      if (path === selected) return;
      router.push(`${pathname}?path=${encodeURIComponent(path)}`);
    },
    [router, pathname, selected],
  );

  const tree = useQuery({ queryKey: vaultKeys.tree, queryFn: vaultApi.tree });

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <VaultSearch onSelect={select} />

      <div className="console-split pane-wide min-h-0 flex-1">
        <aside className="bg-card flex max-h-72 min-h-0 flex-col gap-5 overflow-y-auto rounded-xl border p-3 md:max-h-none">
          {tree.isLoading ? (
            <div role="status" aria-busy="true" aria-label="Loading folders">
              <Skeleton className="h-48 w-full" />
            </div>
          ) : tree.isError ? (
            <ErrorState
              message={tree.error.message}
              onRetry={() => tree.refetch()}
              retrying={tree.isFetching}
            />
          ) : tree.data ? (
            <>
              <MemoryBlocks
                blocks={tree.data.blocks}
                selected={selected}
                onSelect={select}
              />
              <AgentNotebooks
                root={tree.data.root}
                selected={selected}
                onSelect={select}
              />
              <VaultTree
                root={tree.data.root}
                selected={selected}
                onSelect={select}
              />
            </>
          ) : null}
        </aside>

        <section className="min-h-0 overflow-y-auto" aria-label="Note">
          {selected ? (
            <NoteView
              key={selected}
              path={selected}
              onSelect={select}
              block={
                tree.data?.blocks.find((row) => row.path === selected) ?? null
              }
              blurb={blurbFor(selected)}
            />
          ) : tree.data ? (
            <VaultOverview root={tree.data.root} onSelect={select} />
          ) : null}
        </section>
      </div>
    </div>
  );
}
