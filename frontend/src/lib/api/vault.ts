import { getJson, queryString, sendJson } from "@/lib/api/request";

// Client, types and query keys for the read-only Vault view (GET /api/vault/*).

export interface VaultFile {
  name: string;
  /** Vault-relative posix path, e.g. "memory/user.md". */
  path: string;
  kind: "file";
  size: number;
  mtime: string;
}

export interface VaultFolder {
  name: string;
  /** "" for the vault root. */
  path: string;
  kind: "folder";
  mtime: string;
  /** Files in this folder and every folder below it. */
  file_count: number;
  /** Folders first, then files; each group sorted by name. */
  children: VaultNode[];
}

export type VaultNode = VaultFile | VaultFolder;

/** Fill level of one core memory block (memory.block_status). */
export interface MemoryBlock {
  path: string;
  chars: number;
  cap: number;
  pct: number;
  /** Newest commit touching the block; null when it has no history. The
   * subject starts with the actor: "librarian: memory/user.md". */
  last_commit: VaultCommit | null;
}

export interface VaultTree {
  root: VaultFolder;
  blocks: MemoryBlock[];
}

export interface VaultCommit {
  hash: string;
  ts: string;
  message: string;
}

export interface VaultNote {
  path: string;
  content: string;
  size: number;
  mtime: string;
  /** Newest first, at most 5. Empty when the file has no history. */
  git: VaultCommit[];
}

/** GET /api/vault/note/diff: what one commit changed in one note. */
export interface VaultNoteDiff {
  path: string;
  hash: string;
  /** Unified diff text; empty when the commit did not touch the note. */
  diff: string;
}

/** Actor prefix of a vault commit subject ("librarian: memory/user.md"). */
export function commitActor(message: string): string | null {
  const idx = message.indexOf(":");
  if (idx <= 0) return null;
  const actor = message.slice(0, idx).trim();
  return actor && !actor.includes(" ") ? actor : null;
}

/** One search hit. `heading` and `rank` are absent on the grep fallback the
 * backend uses until the index is filled. Matches in `snippet` are wrapped in
 * `**`. */
export interface VaultSearchHit {
  path: string;
  heading?: string;
  snippet: string;
  rank?: number;
}

export const SEARCH_LIMIT = 10;

export const vaultKeys = {
  all: ["vault"] as const,
  tree: ["vault", "tree"] as const,
  note: (path: string) => ["vault", "note", path] as const,
  noteDiff: (path: string, hash: string) =>
    ["vault", "note", path, "diff", hash] as const,
  search: (q: string, limit: number) => ["vault", "search", q, limit] as const,
};

export const vaultApi = {
  /** Save one note as the owner (PUT /api/vault/note). */
  saveNote: (path: string, content: string) =>
    sendJson<VaultNote>("PUT", `/vault/note${queryString({ path })}`, {
      content,
    }),
  tree: () => getJson<VaultTree>("/vault/tree"),
  note: (path: string) =>
    getJson<VaultNote>(`/vault/note${queryString({ path })}`),
  /** operation_id getVaultNoteDiff */
  noteDiff: (path: string, hash: string) =>
    getJson<VaultNoteDiff>(`/vault/note/diff${queryString({ path, hash })}`),
  search: (q: string, limit = SEARCH_LIMIT) =>
    getJson<VaultSearchHit[]>(`/vault/search${queryString({ q, limit })}`),
};
