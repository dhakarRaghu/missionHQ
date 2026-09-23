"use client";

import { useMemo } from "react";
import { ShieldQuestion } from "lucide-react";

import { formatBytes } from "@/components/features/vault/format";
import { Card, CardContent } from "@/components/ui/card";
import type { VaultFile, VaultFolder, VaultNode } from "@/lib/api/vault";
import { exactTime, timeAgo } from "@/lib/time";

const RECENT_LIMIT = 8;
const QUARANTINE = "quarantine/";

/** Every file in the tree, in one flat list. */
function flatten(node: VaultNode, out: VaultFile[] = []): VaultFile[] {
  if (node.kind === "file") {
    out.push(node);
    return out;
  }
  for (const child of node.children) flatten(child, out);
  return out;
}

function splitPath(path: string) {
  const cut = path.lastIndexOf("/");
  return cut < 0
    ? { folder: "", name: path }
    : { folder: path.slice(0, cut + 1), name: path.slice(cut + 1) };
}

/**
 * What the Vault shows before a note is picked.
 *
 * "Pick a note on the left" told the owner nothing. The three questions this
 * page actually answers are: what needs my decision, what changed since I last
 * looked, and how full is the memory the agents read every run.
 */
export function VaultOverview({
  root,
  onSelect,
}: {
  root: VaultFolder;
  onSelect: (path: string) => void;
}) {
  const files = useMemo(() => flatten(root), [root]);

  const quarantine = useMemo(
    () =>
      files
        .filter((file) => file.path.startsWith(QUARANTINE))
        .sort((a, b) => b.mtime.localeCompare(a.mtime)),
    [files],
  );

  const recent = useMemo(
    () =>
      [...files]
        .sort((a, b) => b.mtime.localeCompare(a.mtime))
        .slice(0, RECENT_LIMIT),
    [files],
  );

  if (!files.length) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm">
          <p className="font-medium">The vault is empty.</p>
          <p className="text-muted-foreground mt-1">
            Agents write notes here as they work. Sage writes a daily note every
            evening; hunter files research under quarantine.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {quarantine.length ? (
        <Card className="border-status-approval/40">
          <CardContent className="pt-6">
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <ShieldQuestion className="size-4" aria-hidden />
              Waiting for your review
              <span className="text-muted-foreground tabular-nums">
                {quarantine.length}
              </span>
            </h2>
            <p className="text-muted-foreground mt-1 text-sm">
              Research written from web pages. It stays out of the main vault
              until you read it, so nothing an agent found online can become a
              fact the other agents trust. Open one, then tell sage in chat to
              promote or drop it.
            </p>
            <ul className="mt-3 flex flex-col gap-1">
              {quarantine.map((file) => (
                <li key={file.path}>
                  <NoteRow file={file} onSelect={onSelect} />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <h2 className="text-sm font-medium">Changed recently</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            The newest {Math.min(RECENT_LIMIT, files.length)} of {files.length}{" "}
            notes. Every write is one git commit, so each note keeps its history.
          </p>
          <ul className="mt-3 flex flex-col gap-1">
            {recent.map((file) => (
              <li key={file.path}>
                <NoteRow file={file} onSelect={onSelect} showSize />
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function NoteRow({
  file,
  onSelect,
  showSize = false,
}: {
  file: VaultFile;
  onSelect: (path: string) => void;
  showSize?: boolean;
}) {
  const { folder, name } = splitPath(file.path);
  return (
    <button
      type="button"
      onClick={() => onSelect(file.path)}
      className="hover:bg-muted/60 flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors"
    >
      <span className="min-w-0 flex-1 truncate font-mono text-xs">
        <span className="text-muted-foreground">{folder}</span>
        <span className="text-foreground">{name}</span>
      </span>
      {showSize ? (
        <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
          {formatBytes(file.size)}
        </span>
      ) : null}
      <span
        className="text-muted-foreground shrink-0 text-xs whitespace-nowrap"
        title={exactTime(file.mtime)}
      >
        {timeAgo(file.mtime)}
      </span>
    </button>
  );
}
