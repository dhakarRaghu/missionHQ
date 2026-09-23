"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Copy, FileText, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { Markdown } from "@/components/features/vault/markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { vaultApi, vaultKeys, type VaultFile, type VaultNode } from "@/lib/api/vault";
import { exactTime, timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

const IDEAS_PATH = "projects/content/ideas.md";
const DRAFTS_DIR = "projects/content/drafts";

/** One dated batch: the text under a `## <heading>` in ideas.md. */
export interface Batch {
  heading: string;
  body: string;
  /** ISO date from the heading, "" when it does not start with one. */
  date: string;
  /** The heading with its date and separator removed. */
  title: string;
  /** How many numbered ideas the batch contains. */
  count: number;
}

const HEADING_DATE_RE = /^(\d{4}-\d{2}-\d{2})\s*(?:[—–-]\s*)?(.*)$/;
const NUMBERED_IDEA_RE = /^\d+\.\s+\S/;

/**
 * Scout writes one dated `## ` block per run under a shared frontmatter and an
 * `# Content ideas` title. Splitting on the H2 is what makes "what did it come
 * up with tonight" one glance instead of a scroll through a file that only
 * grows.
 *
 * Sorted by the date IN THE HEADING, newest first, rather than by position.
 * The first version of this trusted file order and reversed it, on the
 * assumption that scout appends — it prepends, so the page put a "newest"
 * badge on the oldest batch and opened it by default. Reading the date is the
 * only ordering that survives scout changing its mind about where it writes.
 */
export function splitBatches(markdown: string): Batch[] {
  const body = markdown.replace(/^---\n[\s\S]*?\n---\n/, "");
  const batches: Batch[] = [];
  let heading = "";
  let lines: string[] = [];
  const flush = () => {
    const text = lines.join("\n").trim();
    if (!heading || !text) return;
    const match = HEADING_DATE_RE.exec(heading);
    batches.push({
      heading,
      body: text,
      date: match?.[1] ?? "",
      title: (match?.[2] ?? heading).trim() || heading,
      count: text.split("\n").filter((l) => NUMBERED_IDEA_RE.test(l.trim()))
        .length,
    });
  };
  for (const line of body.split("\n")) {
    if (line.startsWith("## ")) {
      flush();
      heading = line.slice(3).trim();
      lines = [];
    } else if (heading) {
      lines.push(line);
    }
  }
  flush();
  // An undated heading sorts last rather than jumping to the top on "".
  return batches.sort((a, b) => (b.date || "0").localeCompare(a.date || "0"));
}

/**
 * The same file with one `## ` section taken out, frontmatter and title kept.
 *
 * Removal rewrites the note rather than hiding the batch in this browser: the
 * vault is the source of truth, every write is one git commit, and a batch
 * the owner has judged dead should be gone for the librarian and the next
 * scout run too, not just gone from his screen. `git revert` is the undo.
 */
export function removeBatch(markdown: string, heading: string): string {
  const lines = markdown.split("\n");
  const out: string[] = [];
  let skipping = false;
  for (const line of lines) {
    if (line.startsWith("## ")) {
      skipping = line.slice(3).trim() === heading;
      if (skipping) continue;
    }
    if (!skipping) out.push(line);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd() + "\n";
}

function isFile(node: VaultNode): node is VaultFile {
  return node.kind === "file";
}

/** Every .md directly under projects/content/drafts, newest first. */
function findDrafts(root: VaultNode | undefined): VaultFile[] {
  if (!root) return [];
  const stack: VaultNode[] = [root];
  while (stack.length) {
    const node = stack.pop()!;
    if (node.kind === "folder") {
      if (node.path === DRAFTS_DIR) {
        return node.children
          .filter(isFile)
          .sort((a, b) => b.name.localeCompare(a.name));
      }
      stack.push(...node.children);
    }
  }
  return [];
}

/**
 * Copy one batch as markdown.
 *
 * The point of the page is to get an idea out of it: the opening line scout
 * wrote is the thing that goes into a post, and retyping it out of a rendered
 * blockquote loses the wording that made it worth ranking first.
 *
 * navigator.clipboard needs a secure context; on plain http://localhost it is
 * present, but a LAN address over http would not have it, so the failure is
 * reported rather than silently doing nothing.
 */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      size="sm"
      variant="ghost"
      className="text-muted-foreground h-7 shrink-0 px-2 text-xs"
      aria-label="Copy this batch as markdown"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          toast.error("Could not copy — this page needs a secure context.");
        }
      }}
    >
      {copied ? (
        <Check aria-hidden className="size-3" />
      ) : (
        <Copy aria-hidden className="size-3" />
      )}
      {copied ? "Copied" : "Copy"}
    </Button>
  );
}

/**
 * One vault note rendered as its dated batches, with copy and remove.
 *
 * Both of scout's deliverables have the same shape — a `## <date> — <title>`
 * block per evening — so both pages of this view are the same component
 * pointed at a different file. The differences are the words: what an
 * "item" is called, and what to say when there are none yet.
 */
function BatchSection({
  path,
  label,
  itemNoun,
  emptyHint,
  defaultOpen,
}: {
  path: string;
  label: string;
  itemNoun: string;
  emptyHint: string;
  /** How many of the newest batches start expanded. */
  defaultOpen: number;
}) {
  // Per-batch overrides on top of a default (newest N open). Keyed by heading,
  // not index, so a refetch that adds tonight's batch at the top does not
  // shift the owner's collapses onto the wrong cards. A map, not a single
  // index: comparing tonight against last night is the reason older batches
  // stay on the page at all.
  const [overrides, setOverrides] = useState<ReadonlyMap<string, boolean>>(
    new Map(),
  );
  const [confirming, setConfirming] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const note = useQuery({
    queryKey: vaultKeys.note(path),
    queryFn: () => vaultApi.note(path),
    retry: false,
  });
  const batches = useMemo(
    () => splitBatches(note.data?.content ?? ""),
    [note.data?.content],
  );

  const remove = useMutation({
    mutationFn: (heading: string) =>
      vaultApi.saveNote(path, removeBatch(note.data?.content ?? "", heading)),
    onSuccess: () => {
      toast("Removed", {
        description: "The vault keeps the history; git revert brings it back.",
      });
      setConfirming(null);
      queryClient.invalidateQueries({ queryKey: vaultKeys.all });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const missing = note.error instanceof ApiError && note.error.status === 404;
  const isExpanded = (heading: string, index: number) =>
    overrides.get(heading) ?? index < defaultOpen;
  const allClosed =
    batches.length > 0 && batches.every((b, i) => !isExpanded(b.heading, i));

  return (
    <section className="flex flex-col gap-3">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-medium">{label}</h2>
        <p className="text-muted-foreground text-xs">
          {batches.length
            ? `${batches.length} batch${batches.length === 1 ? "" : "es"}`
            : ""}
          {note.data ? (
            <>
              {batches.length ? " · " : ""}
              updated{" "}
              <span title={exactTime(note.data.mtime)}>
                {timeAgo(note.data.mtime)}
              </span>
            </>
          ) : null}
        </p>
        {batches.length > 1 ? (
          <Button
            size="sm"
            variant="ghost"
            className="text-muted-foreground ml-auto h-7 text-xs"
            onClick={() =>
              setOverrides(new Map(batches.map((b) => [b.heading, allClosed])))
            }
          >
            {allClosed ? "Expand all" : "Collapse all"}
          </Button>
        ) : null}
        <Button
          asChild
          size="sm"
          variant="ghost"
          className={cn(
            "text-muted-foreground h-7 text-xs",
            batches.length <= 1 && "ml-auto",
          )}
        >
          <a href={`/vault?path=${encodeURIComponent(path)}`}>Open in Memory</a>
        </Button>
      </header>

      {note.isLoading ? (
        <Skeleton className="h-40 w-full" aria-busy="true" />
      ) : note.isError && !missing ? (
        // A missing file is not a failure: scout has simply not run yet.
        // Anything else is, and gets a retry rather than a reassuring blank.
        <ErrorState
          message={note.error.message}
          onRetry={() => note.refetch()}
          retrying={note.isFetching}
        />
      ) : !batches.length ? (
        <p className="text-muted-foreground rounded-xl border border-dashed px-4 py-6 text-center text-xs">
          {emptyHint}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {batches.map((batch, index) => {
            const expanded = isExpanded(batch.heading, index);
            const isConfirming = confirming === batch.heading;
            return (
              <li key={batch.heading}>
                <article className="bg-card rounded-xl border">
                  <div className="flex items-center gap-2 px-4 py-3">
                    <button
                      type="button"
                      onClick={() =>
                        setOverrides((prev) =>
                          new Map(prev).set(batch.heading, !expanded),
                        )
                      }
                      aria-expanded={expanded}
                      className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    >
                      <ChevronDown
                        aria-hidden
                        className={cn(
                          "text-muted-foreground size-4 shrink-0 transition-transform",
                          !expanded && "-rotate-90",
                        )}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {batch.title}
                        </span>
                        <span className="text-muted-foreground block text-xs">
                          {batch.date || "undated"}
                          {batch.count > 0
                            ? ` · ${batch.count} ${itemNoun}${batch.count === 1 ? "" : "s"}`
                            : ""}
                        </span>
                      </span>
                    </button>
                    {index === 0 ? <Badge className="text-xs">newest</Badge> : null}
                    <CopyButton text={`## ${batch.heading}\n\n${batch.body}`} />
                    {/* Two presses, not a dialog. Removal rewrites a file, so a
                        stray click should not do it — but it is one git revert
                        away, so it does not deserve a modal either. */}
                    <Button
                      size="sm"
                      variant={isConfirming ? "destructive" : "ghost"}
                      className="h-7 shrink-0 px-2 text-xs"
                      disabled={remove.isPending}
                      aria-label={
                        isConfirming
                          ? `Confirm removing ${batch.title}`
                          : `Remove ${batch.title}`
                      }
                      onClick={() =>
                        isConfirming
                          ? remove.mutate(batch.heading)
                          : setConfirming(batch.heading)
                      }
                      onBlur={() =>
                        setConfirming((c) => (c === batch.heading ? null : c))
                      }
                    >
                      <Trash2 aria-hidden className="size-3" />
                      {isConfirming ? "Sure?" : "Remove"}
                    </Button>
                  </div>
                  {expanded ? (
                    <div className="border-t px-4 py-3">
                      <Markdown content={batch.body} />
                    </div>
                  ) : null}
                </article>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/**
 * What scout came up with, without opening the vault tree.
 *
 * Posts only. Scout's evening reading list used to sit on top of this page,
 * and on 2026-09-13 he said plainly that he does not want it here: "I don't
 * want to know reading content ... just give me Posts to publish." Reading is
 * what Learn and Courses are for, and a list he scrolls past every day to
 * reach the thing he came for is a list that makes him stop opening the page.
 * Scout still writes the file; nothing on this page reads it.
 */
export function IdeasView() {
  const tree = useQuery({ queryKey: vaultKeys.tree, queryFn: vaultApi.tree });
  const drafts = useMemo(() => findDrafts(tree.data?.root), [tree.data?.root]);

  return (
    <div className="flex min-h-full flex-col gap-8 pb-8">
      {drafts.length ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium">Drafts ready to read</h2>
          <ul className="flex flex-wrap gap-2">
            {drafts.map((draft) => (
              <li key={draft.path}>
                <Button asChild size="sm" variant="outline" className="h-7 text-xs">
                  <a href={`/vault?path=${encodeURIComponent(draft.path)}`}>
                    <FileText aria-hidden className="size-3" />
                    {draft.name.replace(/\.md$/, "")}
                  </a>
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <BatchSection
        path={IDEAS_PATH}
        label="Posts to publish"
        itemNoun="post"
        defaultOpen={1}
        emptyHint="Scout writes five paste-ready posts in your voice each evening. Nothing yet."
      />
    </div>
  );
}
