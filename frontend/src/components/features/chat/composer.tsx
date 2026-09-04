"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SendHorizonal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, qk } from "@/lib/api/client";
import { vaultApi, vaultKeys } from "@/lib/api/vault";
import { cn } from "@/lib/utils";

const MAX_HEIGHT_PX = 200;
const SUGGESTION_LIMIT = 6;

/** The word being typed at the caret, when it opens with @ or #. */
function activeToken(text: string, caret: number) {
  const upto = text.slice(0, caret);
  const match = /(^|\s)([@#])([A-Za-z0-9._/-]*)$/.exec(upto);
  if (!match) return null;
  return {
    kind: match[2] as "@" | "#",
    query: match[3],
    start: caret - match[3].length - 1,
  };
}

/**
 * Enter sends, Shift+Enter inserts a newline, the box grows with the text.
 *
 * Typing @ offers the agents and # offers vault notes. Both insert plain text,
 * so the same message read in Telegram is still readable; the console renders
 * them as chips.
 */
export function Composer({
  disabled,
  onSend,
}: {
  disabled: boolean;
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const [caret, setCaret] = useState(0);
  const [highlight, setHighlight] = useState(0);
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && text.trim() !== "";

  const token = activeToken(text, caret);
  const agents = useQuery({
    queryKey: qk.agents,
    queryFn: api.agents,
    enabled: token?.kind === "@",
  });
  const notes = useQuery({
    queryKey: vaultKeys.search(token?.query ?? "", SUGGESTION_LIMIT),
    queryFn: () => vaultApi.search(token?.query ?? "", SUGGESTION_LIMIT),
    enabled: token?.kind === "#" && (token?.query.length ?? 0) > 1,
  });

  const options = useMemo(() => {
    if (!token) return [];
    if (token.kind === "@") {
      return (agents.data ?? [])
        .map((agent) => agent.name)
        .filter((name) => name.startsWith(token.query.toLowerCase()))
        .slice(0, SUGGESTION_LIMIT);
    }
    return (notes.data ?? []).map((hit) => hit.path).slice(0, SUGGESTION_LIMIT);
  }, [token, agents.data, notes.data]);

  // Grow with the content up to a cap, then scroll inside the box.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [text]);

  // Return focus to the box when the previous turn finishes.
  useEffect(() => {
    if (!disabled) ref.current?.focus();
  }, [disabled]);

  const accept = (value: string) => {
    if (!token) return;
    const next = `${text.slice(0, token.start)}${token.kind}${value} ${text.slice(caret)}`;
    setText(next);
    setHighlight(0);
    const at = token.start + value.length + 2;
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(at, at);
      setCaret(at);
    });
  };

  const submit = () => {
    if (!canSend) return;
    onSend(text.trim());
    setText("");
    setCaret(0);
  };

  const open = options.length > 0;

  return (
    <form
      className="relative flex flex-col gap-1.5"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      {open ? (
        <ul
          role="listbox"
          aria-label={token?.kind === "@" ? "Agents" : "Notes"}
          className="bg-popover absolute bottom-full z-10 mb-2 max-h-56 w-full max-w-md overflow-y-auto rounded-lg border p-1 shadow-md"
        >
          {options.map((option, index) => (
            <li key={option}>
              <button
                type="button"
                role="option"
                aria-selected={index === highlight}
                onMouseDown={(event) => {
                  event.preventDefault();
                  accept(option);
                }}
                className={cn(
                  "w-full truncate rounded px-2 py-1.5 text-left text-sm",
                  index === highlight ? "bg-muted" : "hover:bg-muted/60",
                )}
              >
                {token?.kind}
                {option}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex items-end gap-2">
        <Textarea
          ref={ref}
          aria-label="Message"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setCaret(event.target.selectionStart ?? 0);
            setHighlight(0);
          }}
          onSelect={(event) =>
            setCaret(event.currentTarget.selectionStart ?? 0)
          }
          onKeyDown={(event) => {
            if (open) {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setHighlight((i) => (i + 1) % options.length);
                return;
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setHighlight((i) => (i - 1 + options.length) % options.length);
                return;
              }
              if (event.key === "Enter" || event.key === "Tab") {
                event.preventDefault();
                accept(options[highlight]);
                return;
              }
              if (event.key === "Escape") {
                event.preventDefault();
                setCaret(-1);
                return;
              }
            }
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder={
            disabled
              ? "Waiting for the agent…"
              : "Message the agent. Use @ to name one, # to link a note"
          }
          disabled={disabled}
          rows={1}
          className="min-h-9 resize-none"
        />
        <Button type="submit" disabled={!canSend} aria-label="Send message">
          <SendHorizonal aria-hidden />
          <span className="hidden sm:inline">Send</span>
        </Button>
      </div>
      <p className="text-muted-foreground px-1 text-xs">
        Enter sends. Shift and Enter start a new line.{" "}
        <span className="font-mono">@</span> names an agent,{" "}
        <span className="font-mono">#</span> links a note.
      </p>
    </form>
  );
}
