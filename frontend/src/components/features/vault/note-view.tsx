"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import {
  formatBytes,
  formatDateTime,
} from "@/components/features/vault/format";
import { Markdown } from "@/components/features/vault/markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { type MemoryBlock, vaultApi, vaultKeys } from "@/lib/api/vault";
import { exactTime, timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

/** The selected note: header (path, size, mtime, last commits) and body. */
export function NoteView({
  path,
  onSelect,
  block,
  blurb,
}: {
  path: string;
  onSelect: (path: string) => void;
  /** Fill status when this note is a capped memory block. */
  block?: MemoryBlock | null;
  /** One sentence on what this note is for, shown under its name. */
  blurb?: string;
}) {
  const note = useQuery({
    queryKey: vaultKeys.note(path),
    queryFn: () => vaultApi.note(path),
  });
  // Commit whose diff is open; clicking the same hash again closes it.
  const [openHash, setOpenHash] = useState<string | null>(null);

  if (note.isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Loading note"
        className="flex flex-col gap-4"
      >
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (note.isError) {
    return (
      <ErrorState
        message={note.error.message}
        onRetry={() => note.refetch()}
        retrying={note.isFetching}
      />
    );
  }
  if (!note.data) return null;
  const { data } = note;

  const folder = data.path.includes("/")
    ? data.path.slice(0, data.path.lastIndexOf("/") + 1)
    : "";
  const name = data.path.slice(folder.length);

  return (
    <article className="flex flex-col gap-4">
      <Card>
        <CardContent className="pt-6">
          <h2 className="font-mono text-sm break-all">
            <span className="text-muted-foreground">{folder}</span>
            <span className="font-medium">{name}</span>
          </h2>
          {blurb ? (
            <p className="text-muted-foreground mt-1.5 max-w-prose text-sm">
              {blurb}
            </p>
          ) : null}
          <p className="text-muted-foreground mt-1.5 text-xs">
            <span title={exactTime(data.mtime)}>
              edited {timeAgo(data.mtime)}
            </span>
            {" · "}
            <span className="tabular-nums">{formatBytes(data.size)}</span>
            {" · "}
            <span>
              {data.git.length} recent commit{data.git.length === 1 ? "" : "s"}
            </span>
          </p>
          <dl className="mt-4">
            <div>
              <dt className="text-muted-foreground text-xs">
                Change history
              </dt>
              <dd className="mt-1 text-sm">
                {data.git.length ? (
                  <ol className="flex flex-col gap-1">
                    {data.git.map((commit) => (
                      <li key={commit.hash}>
                        <button
                          type="button"
                          aria-expanded={openHash === commit.hash}
                          onClick={() =>
                            setOpenHash((prev) =>
                              prev === commit.hash ? null : commit.hash,
                            )
                          }
                          className="hover:bg-muted flex w-full flex-wrap items-baseline gap-x-2 rounded px-1 text-left"
                        >
                          <code className="bg-muted rounded px-1 font-mono text-xs">
                            {commit.hash}
                          </code>
                          <span
                            className="text-muted-foreground text-xs tabular-nums"
                            title={exactTime(commit.ts)}
                          >
                            {formatDateTime(commit.ts)}
                          </span>
                          <span className="break-words">{commit.message}</span>
                          <span className="text-muted-foreground ml-auto text-xs">
                            {openHash === commit.hash ? "hide diff" : "show diff"}
                          </span>
                        </button>
                        {openHash === commit.hash ? (
                          <CommitDiff path={data.path} hash={commit.hash} />
                        ) : null}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <span className="text-muted-foreground">no commits yet</span>
                )}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <NoteBody
        path={data.path}
        content={data.content}
        block={block}
        onSelect={onSelect}
      />
    </article>
  );
}

/**
 * The note itself, with an editor.
 *
 * The vault is the memory every agent reads before it works, so the owner has
 * to be able to correct it in place. Saving goes through the same write path
 * an agent uses: one git commit, and a memory block's size cap still applies.
 */
function NoteBody({
  path,
  content,
  block,
  onSelect,
}: {
  path: string;
  content: string;
  block?: MemoryBlock | null;
  onSelect: (path: string) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(content);
  const isMarkdown = path.toLowerCase().endsWith(".md");
  const dirty = draft !== content;

  const save = useMutation({
    mutationFn: () => vaultApi.saveNote(path, draft),
    onSuccess: () => {
      toast("Saved");
      queryClient.invalidateQueries({ queryKey: vaultKeys.note(path) });
      queryClient.invalidateQueries({ queryKey: vaultKeys.tree });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const over = block ? draft.length > block.cap : false;

  if (!isMarkdown) {
    return (
      <Card>
        <CardContent className="pt-6">
          <pre className="bg-muted overflow-x-auto rounded-lg p-3 font-mono text-xs">
            {content}
          </pre>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <Tabs defaultValue="read">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <TabsList>
              <TabsTrigger value="read">Read</TabsTrigger>
              <TabsTrigger value="write">Write</TabsTrigger>
            </TabsList>
            {block ? (
              <div className="flex min-w-40 items-center gap-2">
                <Progress
                  value={Math.min(100, (draft.length / block.cap) * 100)}
                  aria-label={`${path} fill level`}
                  className={
                    over
                      ? "[&_[data-slot=progress-indicator]]:bg-status-danger"
                      : undefined
                  }
                />
                <span
                  className={`shrink-0 text-xs tabular-nums ${
                    over ? "text-status-danger" : "text-muted-foreground"
                  }`}
                >
                  {draft.length.toLocaleString()} /{" "}
                  {block.cap.toLocaleString()}
                </span>
              </div>
            ) : null}
          </div>

          <TabsContent value="read" className="pt-4">
            {content.trim() ? (
              <Markdown content={content} path={path} onSelect={onSelect} />
            ) : (
              <EmptyState title="This note is empty">
                Open the Write tab to fill it in, or leave it to the agent that
                owns it.
              </EmptyState>
            )}
          </TabsContent>

          <TabsContent value="write" className="flex flex-col gap-3 pt-4">
            <Textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              aria-label={`Content of ${path}`}
              spellCheck={false}
              className="min-h-96 font-mono text-xs"
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                disabled={!dirty || over || save.isPending}
                onClick={() => save.mutate()}
              >
                {save.isPending ? "Saving…" : "Save"}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={!dirty || save.isPending}
                onClick={() => setDraft(content)}
              >
                Discard changes
              </Button>
              <p className="text-muted-foreground text-xs">
                {over
                  ? "Over the cap. Trim it before saving."
                  : dirty
                    ? "Saving writes the file and makes one git commit."
                    : "No changes yet."}
              </p>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

/** Line tone of a unified diff: added, removed, hunk header, or context. */
function diffLineClass(line: string): string | null {
  if (line.startsWith("+++") || line.startsWith("---")) return "font-medium";
  if (line.startsWith("+")) return "text-status-success";
  if (line.startsWith("-")) return "text-status-danger";
  if (line.startsWith("@@")) return "text-muted-foreground";
  return null;
}

/** What one commit changed in this note (GET /api/vault/note/diff). */
function CommitDiff({ path, hash }: { path: string; hash: string }) {
  const diff = useQuery({
    queryKey: vaultKeys.noteDiff(path, hash),
    queryFn: () => vaultApi.noteDiff(path, hash),
  });

  if (diff.isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading diff" className="mt-2">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (diff.isError) {
    return (
      <div className="mt-2">
        <ErrorState
          message={diff.error.message}
          onRetry={() => diff.refetch()}
          retrying={diff.isFetching}
        />
      </div>
    );
  }
  const text = diff.data?.diff ?? "";
  if (!text.trim()) {
    return (
      <p className="text-muted-foreground mt-2 text-xs">
        This commit did not change the note&apos;s content.
      </p>
    );
  }
  return (
    <pre
      aria-label={`Diff of ${hash}`}
      className="bg-muted mt-2 max-h-96 overflow-auto rounded-md p-3 font-mono text-xs"
    >
      {text.split("\n").map((line, i) => (
        <div key={i} className={cn("whitespace-pre", diffLineClass(line))}>
          {line || " "}
        </div>
      ))}
    </pre>
  );
}
