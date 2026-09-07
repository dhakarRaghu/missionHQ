"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, FileText, Folder } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ancestorsOf, formatBytes } from "@/components/features/vault/format";
import type { VaultFile, VaultFolder, VaultNode } from "@/lib/api/vault";
import { cn } from "@/lib/utils";

/** Which folders the user toggled by hand. Folders above the selected note
 * are open by default; a manual toggle overrides that until the selection
 * changes to a note inside them. */
interface OpenState {
  selected: string | null;
  manual: Record<string, boolean>;
}

export function VaultTree({
  root,
  selected,
  onSelect,
}: {
  root: VaultFolder;
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  const [state, setState] = useState<OpenState>({ selected, manual: {} });
  const ancestors = new Set(selected ? ancestorsOf(selected) : []);

  // Derive-from-props: a new selection re-opens its ancestors (a deep link or
  // a search hit must always be visible) and keeps the other toggles.
  if (state.selected !== selected) {
    const manual = { ...state.manual };
    for (const path of ancestors) delete manual[path];
    setState({ selected, manual });
  }

  // A top-level folder with notes in it opens by default. Deeper folders stay
  // closed so the pane does not become a wall of paths.
  const openByDefault = (path: string) =>
    ancestors.has(path) ||
    (!path.includes("/") &&
      root.children.some(
        (node) =>
          node.path === path && node.kind === "folder" && node.file_count > 0,
      ));
  const isOpen = (path: string) => state.manual[path] ?? openByDefault(path);
  const toggle = (path: string) =>
    setState((prev) => ({
      ...prev,
      manual: {
        ...prev.manual,
        [path]: !(prev.manual[path] ?? openByDefault(path)),
      },
    }));

  if (!root.children.length) {
    return (
      <EmptyState compact title="The vault is empty">
        Agents write markdown notes here as they work.
      </EmptyState>
    );
  }

  return (
    <nav aria-label="Vault folders" className="flex flex-col gap-1">
      <h2 className="text-muted-foreground flex items-center justify-between px-2 text-xs font-medium tracking-wide uppercase">
        <span>Notes</span>
        <span className="tabular-nums">{root.file_count}</span>
      </h2>
      <ul role="tree" className="flex flex-col gap-0.5">
        {root.children.map((node) => (
          <TreeNode
            key={node.path}
            node={node}
            selected={selected}
            isOpen={isOpen}
            onToggle={toggle}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </nav>
  );
}

interface NodeProps {
  selected: string | null;
  isOpen: (path: string) => boolean;
  onToggle: (path: string) => void;
  onSelect: (path: string) => void;
}

function TreeNode({ node, ...rest }: NodeProps & { node: VaultNode }) {
  return node.kind === "folder" ? (
    <FolderNode node={node} {...rest} />
  ) : (
    <FileNode node={node} {...rest} />
  );
}

const ROW =
  "hover:bg-muted flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors";

function FolderNode({ node, ...rest }: NodeProps & { node: VaultFolder }) {
  const open = rest.isOpen(node.path);
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <li role="treeitem" aria-expanded={open} aria-selected={false}>
      <button
        type="button"
        onClick={() => rest.onToggle(node.path)}
        className={ROW}
      >
        <Chevron
          className="text-muted-foreground size-3.5 shrink-0"
          aria-hidden
        />
        <Folder
          className="text-muted-foreground size-3.5 shrink-0"
          aria-hidden
        />
        <span
          className={cn(
            "truncate",
            !node.file_count && "text-muted-foreground",
          )}
        >
          {node.name}
        </span>
        <span
          className="text-muted-foreground ml-auto text-xs tabular-nums"
          title={`${node.file_count} note${node.file_count === 1 ? "" : "s"}`}
        >
          {node.file_count}
        </span>
      </button>
      {open ? (
        node.children.length ? (
          // Nesting indents the level; no per-depth inline style needed.
          <ul
            role="group"
            className="ml-3.5 flex flex-col gap-0.5 border-l pl-1.5"
          >
            {node.children.map((child) => (
              <TreeNode key={child.path} node={child} {...rest} />
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground ml-3.5 border-l py-1 pl-4 text-xs">
            empty folder
          </p>
        )
      ) : null}
    </li>
  );
}

function FileNode({
  node,
  selected,
  onSelect,
}: NodeProps & { node: VaultFile }) {
  const active = selected === node.path;
  return (
    <li role="treeitem" aria-selected={active}>
      <button
        type="button"
        onClick={() => onSelect(node.path)}
        aria-current={active ? "true" : undefined}
        className={cn(ROW, active && "bg-muted font-medium")}
      >
        <FileText
          className="text-muted-foreground size-3.5 shrink-0"
          aria-hidden
        />
        <span className="truncate">{node.name}</span>
        <span className="text-muted-foreground ml-auto text-xs tabular-nums">
          {formatBytes(node.size)}
        </span>
      </button>
    </li>
  );
}
