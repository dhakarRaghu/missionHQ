"use client";

import { useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { resolveVaultLink } from "@/components/features/vault/format";

/**
 * Renders GFM markdown.
 *
 * In the vault (`onSelect` given), a link to another .md file opens that note
 * in place instead of a new tab, so following a reference keeps you in the
 * Memory view. Other callers (the board drawer, a run's output) omit
 * `onSelect` and get plain links.
 */
export function Markdown({
  content,
  path = "",
  onSelect,
}: {
  content: string;
  /** Path of the note being rendered; relative links resolve against it. */
  path?: string;
  onSelect?: (path: string) => void;
}) {
  const link = useMemo<Components["a"]>(
    () =>
      function Anchor({ children, href }) {
        const target = href && onSelect ? resolveVaultLink(href, path) : null;
        if (target && onSelect) {
          return (
            <button
              type="button"
              onClick={() => onSelect(target)}
              className="text-primary underline underline-offset-2"
            >
              {children}
            </button>
          );
        }
        return (
          <a
            className="text-primary underline underline-offset-2"
            href={href}
            rel="noreferrer"
            target="_blank"
          >
            {children}
          </a>
        );
      },
    [path, onSelect],
  );

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => <h1 className="mb-3 text-xl font-semibold">{children}</h1>,
        h2: ({ children }) => <h2 className="mt-5 mb-2 text-lg font-semibold">{children}</h2>,
        h3: ({ children }) => <h3 className="mt-4 mb-2 font-semibold">{children}</h3>,
        p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
        ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
        blockquote: ({ children }) => (
          <blockquote className="border-border text-muted-foreground my-3 border-l-2 pl-3">
            {children}
          </blockquote>
        ),
        a: link,
        code: ({ children, className }) => (
          <code className={`${className ?? ""} bg-muted rounded px-1 py-0.5 font-mono text-xs`}>
            {children}
          </code>
        ),
        pre: ({ children }) => (
          <pre className="bg-muted my-3 overflow-x-auto rounded-lg p-3 text-xs">
            {children}
          </pre>
        ),
        table: ({ children }) => (
          <div className="my-3 overflow-x-auto">
            <table className="w-full border-collapse text-sm">{children}</table>
          </div>
        ),
        th: ({ children }) => <th className="border-border border px-2 py-1 text-left">{children}</th>,
        td: ({ children }) => <td className="border-border border px-2 py-1 align-top">{children}</td>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
