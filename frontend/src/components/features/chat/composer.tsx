"use client";

import { useEffect, useRef, useState } from "react";
import { SendHorizonal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const MAX_HEIGHT_PX = 200;

/** Enter sends, Shift+Enter inserts a newline. The box grows with the text. */
export function Composer({
  disabled,
  onSend,
}: {
  disabled: boolean;
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && text.trim() !== "";

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

  const submit = () => {
    if (!canSend) return;
    onSend(text.trim());
    setText("");
  };

  return (
    <form
      className="flex flex-col gap-1.5"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="flex items-end gap-2">
        <Textarea
          ref={ref}
          aria-label="Message"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder={
            disabled ? "Waiting for the agent…" : "Message the agent"
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
        Enter sends. Shift and Enter start a new line.
      </p>
    </form>
  );
}
