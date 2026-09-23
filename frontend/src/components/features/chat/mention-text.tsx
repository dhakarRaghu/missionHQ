"use client";

import { Fragment } from "react";
import Link from "next/link";

// @name mentions an agent, #path links a vault note. Both are written as
// plain text in the message, so a Telegram reader sees the same characters
// the console renders as a chip.
const TOKEN_RE = /(@[a-z0-9_-]+|#[A-Za-z0-9._/-]+\.md)/g;

/** Renders a message's mentions and note links as chips. */
export function MentionText({ text }: { text: string }) {
  const parts = text.split(TOKEN_RE);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("@") && part.length > 1) {
          return (
            <Link
              key={i}
              href={`/agents/${encodeURIComponent(part.slice(1))}`}
              className="bg-status-running/10 text-status-running rounded px-1 font-medium"
            >
              {part}
            </Link>
          );
        }
        if (part.startsWith("#") && part.endsWith(".md")) {
          const path = part.slice(1);
          return (
            <Link
              key={i}
              href={`/vault?path=${encodeURIComponent(path)}`}
              className="bg-status-approval/10 text-status-approval rounded px-1 font-medium"
            >
              {part}
            </Link>
          );
        }
        return <Fragment key={i}>{part}</Fragment>;
      })}
    </>
  );
}
