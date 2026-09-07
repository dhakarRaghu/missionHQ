"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, Copy } from "lucide-react";

import { ErrorState } from "@/components/error-state";
import { MentionText } from "@/components/features/chat/mention-text";
import { Markdown } from "@/components/features/vault/markdown";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChatMessage, ChatRole } from "@/lib/api/types";
import { clockTime, exactTime } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * A turn the user sent from this browser that the server transcript does not
 * show yet. "done" carries the reply until the refetched transcript includes
 * it; "waiting" means the run outlived the HTTP wait (usually an approval).
 */
export interface LocalTurn {
  id: string;
  text: string;
  /** Transcript length when the turn was sent. Used to detect its arrival. */
  baseCount: number;
  state: "sending" | "waiting" | "done" | "error";
  reply?: string;
  error?: string;
  /** Run linkage returned with a "done" reply. */
  run?: RunLink | null;
}

/** Cost, tool count and run id of the run behind one assistant turn. */
export interface RunLink {
  run_id?: string | null;
  cost_usd?: number | null;
  tools?: string[] | null;
}

export function Transcript({
  isLoading,
  isError,
  error,
  isFetching,
  refetch,
  messages,
  local,
  starters = [],
  onStart,
  onRetry,
}: {
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  isFetching: boolean;
  refetch: () => void;
  messages: ChatMessage[];
  local: LocalTurn[];
  /** Suggested first questions, shown only while the thread is empty. */
  starters?: string[];
  onStart?: (text: string) => void;
  /** Retry a transport failure with the original durable client id. */
  onRetry?: (turn: LocalTurn) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const count = messages.length + local.length;
  // Scroll to the newest turn. Smooth once the thread is on screen, instant on
  // the first paint so opening a chat does not animate through its history.
  const first = useRef(true);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({
      top: el.scrollHeight,
      behavior: first.current ? "auto" : "smooth",
    });
    first.current = false;
  }, [count, local]);

  if (isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Loading transcript"
        className="flex flex-1 flex-col gap-3 p-4"
      >
        <Skeleton className="h-12 w-2/3 self-end" />
        <Skeleton className="h-24 w-4/5" />
      </div>
    );
  }
  if (isError) {
    return (
      <div className="p-4">
        <ErrorState
          message={error?.message ?? "Unknown error"}
          onRetry={refetch}
          retrying={isFetching}
        />
      </div>
    );
  }
  if (!count) {
    return (
      <div className="pane-scroll flex flex-col justify-center p-6">
        <div className="mx-auto w-full max-w-lg">
          <p className="text-sm font-medium">Start the conversation</p>
          <p className="text-muted-foreground mt-1 text-sm">
            Each turn is a real run, so the agent can read your memory and use
            its tools. A reply usually takes 20 to 60 seconds.
          </p>
          {starters.length && onStart ? (
            <>
              <p className="text-muted-foreground mt-5 text-xs font-medium tracking-wide uppercase">
                Try one of these
              </p>
              <ul className="mt-2 flex flex-col gap-2">
                {starters.map((text) => (
                  <li key={text}>
                    <button
                      type="button"
                      onClick={() => onStart(text)}
                      className="bg-card hover:border-ring/60 hover:bg-muted/40 w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors"
                    >
                      {text}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="pane-scroll flex flex-col" aria-live="polite">
      {/* mt-auto pins a short thread to the bottom, next to the composer. */}
      <div className="mt-auto flex flex-col gap-4 p-4">
        {messages.map((message, index) => (
          <Bubble
            key={`${index}-${message.ts ?? ""}`}
            role={message.role}
            text={message.text}
            ts={message.ts}
            run={message.role === "assistant" ? message : null}
          />
        ))}
        {local.map((turn) => (
          <LocalTurnRows key={turn.id} turn={turn} onRetry={onRetry} />
        ))}
      </div>
    </div>
  );
}

function LocalTurnRows({
  turn,
  onRetry,
}: {
  turn: LocalTurn;
  onRetry?: (turn: LocalTurn) => void;
}) {
  return (
    <>
      <Bubble role="user" text={turn.text} ts={null} />
      {turn.state === "sending" ? (
        <Thinking />
      ) : turn.state === "waiting" ? (
        <StatusRow>
          Still working. If approval is needed, it will appear in Inbox. The
          reply will appear here when the run finishes.
        </StatusRow>
      ) : turn.state === "error" ? (
        <StatusRow tone="danger">
          <span>{turn.error ?? "Send failed"}</span>
          {onRetry ? (
            <Button
              type="button"
              variant="outline"
              size="xs"
              onClick={() => onRetry(turn)}
            >
              Retry
            </Button>
          ) : null}
        </StatusRow>
      ) : turn.reply ? (
        <Bubble role="assistant" text={turn.reply} ts={null} run={turn.run} />
      ) : null}
    </>
  );
}

/**
 * Placeholder in the assistant's own bubble while a turn runs. A run takes
 * tens of seconds, so the indicator has to be visible, not a line of grey text.
 */
function Thinking() {
  return (
    <div className="flex flex-col items-start gap-1">
      <div className="bg-muted flex items-center gap-2 rounded-2xl rounded-bl-sm px-4 py-3">
        <span className="flex gap-1" aria-hidden>
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="bg-muted-foreground/70 size-1.5 rounded-full motion-safe:animate-bounce"
              style={{ animationDelay: `${i * 140}ms` }}
            />
          ))}
        </span>
        <span role="status" className="text-muted-foreground text-xs">
          Thinking. A turn usually takes 20 to 60 seconds.
        </span>
      </div>
    </div>
  );
}

function StatusRow({
  children,
  tone = "muted",
}: {
  children: React.ReactNode;
  tone?: "muted" | "danger";
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-xs",
        tone === "danger"
          ? "border-status-danger/40 bg-status-danger/5 text-status-danger"
          : "text-muted-foreground border-dashed",
      )}
    >
      {children}
    </div>
  );
}

/** Copies the reply text. Confirms in place so no toast is needed. */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be refused; the text stays selectable either way.
    }
  };

  const Icon = copied ? Check : Copy;
  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? "Copied" : "Copy reply"}
      className="text-muted-foreground hover:text-foreground rounded p-1 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
    >
      <Icon className="size-3.5" aria-hidden />
    </button>
  );
}

/** "$0.0012 · 3 tools · view run" for an assistant turn with a matched run. */
function RunMeta({ run }: { run: RunLink }) {
  const parts: React.ReactNode[] = [];
  if (typeof run.cost_usd === "number") {
    parts.push(
      <span key="cost" className="tabular-nums">
        ${run.cost_usd.toFixed(4)}
      </span>,
    );
  }
  if (run.tools?.length) {
    parts.push(
      <span key="tools" className="font-mono">
        {run.tools.join(", ")}
      </span>,
    );
  }
  if (run.run_id) {
    parts.push(
      <Link
        key="run"
        href={`/runs/${encodeURIComponent(run.run_id)}`}
        className="hover:text-foreground underline underline-offset-4"
      >
        view run
      </Link>,
    );
  }
  if (!parts.length) return null;
  return (
    <>
      {parts.map((part, i) => (
        <span key={i}>
          {" · "}
          {part}
        </span>
      ))}
    </>
  );
}

function Bubble({
  role,
  text,
  ts,
  run,
}: {
  role: ChatRole;
  text: string;
  ts: string | null;
  run?: RunLink | null;
  /** Agent name, used for the avatar letter on assistant turns. */
  agent?: string | null;
}) {
  const mine = role === "user";
  return (
    <div className={cn("group flex gap-3", mine && "flex-row-reverse")}>
      <span
        aria-hidden
        className={cn(
          "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg text-xs font-medium",
          mine
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground",
        )}
      >
        {mine ? "You" : "HQ"}
      </span>

      <div className={cn("flex min-w-0 flex-col gap-1", mine && "items-end")}>
        <div
          className={cn(
            "max-w-[min(46rem,100%)] px-4 py-3 text-sm",
            mine
              ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm break-words whitespace-pre-wrap"
              : "bg-card rounded-2xl rounded-tl-sm border",
          )}
        >
          {/* Agents answer in markdown: paths, lists and emphasis are common.
              Your own text is shown as typed, with mentions and note links
              rendered as chips. */}
          {mine ? <MentionText text={text} /> : <Markdown content={text} />}
        </div>
        <span className="text-muted-foreground flex items-center gap-1 px-1 text-xs">
          <span title={exactTime(ts)}>{ts ? clockTime(ts) : ""}</span>
          {!mine && run ? <RunMeta run={run} /> : null}
          {!mine ? <CopyButton text={text} /> : null}
        </span>
      </div>
    </div>
  );
}
