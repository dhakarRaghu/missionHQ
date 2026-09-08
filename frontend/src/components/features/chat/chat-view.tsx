"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CornerDownRight, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ChatApprovals } from "@/components/features/chat/approval-card";
import { Composer } from "@/components/features/chat/composer";
import { InFlight } from "@/components/features/chat/in-flight";
import {
  SessionList,
  useSessionsQuery,
} from "@/components/features/chat/session-list";
import {
  type LocalTurn,
  Transcript,
} from "@/components/features/chat/transcript";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, qk } from "@/lib/api/client";
import type { ChatMessage, SendChatResult } from "@/lib/api/types";
import { startersFor } from "@/lib/chat-starters";

/**
 * Session list on the left, transcript plus composer on the right. Turns sent
 * from this browser live in `local` until the server transcript shows them
 * (the transcript is the source of truth; local rows only bridge the gap).
 */
export function ChatView() {
  const sessions = useSessionsQuery();
  const [selected, setSelected] = useState<string | null>(null);
  // Keyed by session so switching threads keeps in-flight turns (and the
  // composer lock) of the thread you left.
  const [sent, setSent] = useState<Record<string, LocalTurn[]>>({});
  const activeId = selected ?? sessions.data?.[0]?.id ?? null;
  const active = sessions.data?.find((s) => s.id === activeId) ?? null;

  return (
    <div className="console-split pane-narrow min-h-0 flex-1">
      <aside className="flex max-h-56 min-h-0 flex-col md:max-h-none">
        <SessionList
          sessions={sessions}
          activeId={activeId}
          onSelect={setSelected}
          onDeleted={(id) => {
            // Fall back to the newest remaining chat rather than an empty pane.
            if (activeId === id) setSelected(null);
            setSent((prev) => {
              const next = { ...prev };
              delete next[id];
              return next;
            });
          }}
        />
      </aside>
      <section className="bg-card flex min-h-0 flex-col rounded-xl border">
        {activeId ? (
          <Thread
            key={activeId}
            sessionId={activeId}
            agent={active?.agent ?? null}
            sent={sent[activeId] ?? EMPTY}
            setSent={(update) =>
              setSent((prev) => ({
                ...prev,
                [activeId]: update(prev[activeId] ?? EMPTY),
              }))
            }
          />
        ) : (
          <div className="p-4">
            <EmptyState>
              Pick a chat on the left, or start a new one.
            </EmptyState>
          </div>
        )}
      </section>
    </div>
  );
}

const EMPTY: LocalTurn[] = [];

function transcriptHasTurn(
  turn: LocalTurn,
  transcript: ChatMessage[],
): boolean {
  const newer = transcript.slice(turn.baseCount);
  const userIndex = newer.findIndex(
    (message) => message.role === "user" && message.text === turn.text,
  );
  return (
    userIndex >= 0 &&
    newer.slice(userIndex + 1).some((message) => message.role === "assistant")
  );
}

function Thread({
  sessionId,
  agent,
  sent,
  setSent: setLocal,
}: {
  sessionId: string;
  agent: string | null;
  sent: LocalTurn[];
  setSent: (update: (prev: LocalTurn[]) => LocalTurn[]) => void;
}) {
  const queryClient = useQueryClient();
  const messages = useQuery({
    queryKey: qk.chatMessages(sessionId),
    queryFn: () => api.chatMessages(sessionId),
  });
  const transcript = useMemo(() => messages.data ?? [], [messages.data]);

  // A turn is complete once the transcript holds its user message and the
  // reply (two more rows than when it was sent). Then its local row hides.
  const local = useMemo(
    () => sent.filter((turn) => !transcriptHasTurn(turn, transcript)),
    [sent, transcript],
  );

  const send = useMutation({
    mutationFn: ({
      id,
      text,
    }: {
      id: string;
      text: string;
      baseCount: number;
    }) => api.sendChatMessage(sessionId, { text, client_id: id }),
    onMutate: ({ id, baseCount }) => {
      // baseCount is stamped here, not when the message was typed. A queued
      // message waits while the transcript grows, and this number is how the
      // turn later recognises its own reply.
      setLocal((prev) =>
        prev.map((turn) =>
          turn.id === id && turn.state === "queued"
            ? { ...turn, state: "sending", baseCount }
            : turn,
        ),
      );
    },
    onSuccess: (result: SendChatResult, { id }) => {
      setLocal((prev) =>
        prev.map((turn) =>
          turn.id !== id
            ? turn
            : result.status === "done"
              ? {
                  ...turn,
                  state: "done",
                  reply: result.reply,
                  run: {
                    run_id: result.run_id,
                    cost_usd: result.cost_usd,
                    tools: result.tools,
                  },
                }
              : result.status === "failed"
                ? { ...turn, state: "error", error: result.reply }
                : { ...turn, state: "waiting" },
        ),
      );
      queryClient.invalidateQueries({ queryKey: qk.chatMessages(sessionId) });
      queryClient.invalidateQueries({ queryKey: qk.chatSessions });
    },
    onError: async (error: Error, { id, text, baseCount }) => {
      // A proxy can lose the response after the durable workflow finished.
      // Reconcile with the server before showing a failure or offering retry.
      let refreshed: ChatMessage[] | undefined;
      try {
        refreshed = (await messages.refetch()).data;
      } catch {
        // Keep the original send error; Retry below uses the same client id.
      }
      const submitted = sent.find((turn) => turn.id === id) ?? {
        id,
        text,
        baseCount,
        state: "error" as const,
      };
      if (refreshed && transcriptHasTurn(submitted, refreshed)) {
        setLocal((prev) => prev.filter((turn) => turn.id !== id));
        return;
      }
      toast.error(error.message);
      setLocal((prev) =>
        prev.map((turn) =>
          turn.id === id
            ? { ...turn, state: "error", error: error.message }
            : turn,
        ),
      );
    },
  });

  const busy = local.some(
    (turn) => turn.state === "sending" || turn.state === "waiting",
  );
  const queued = useMemo(
    () => local.filter((turn) => turn.state === "queued"),
    [local],
  );
  const visibleInTranscript = useMemo(
    () => local.filter((turn) => turn.state !== "queued"),
    [local],
  );

  // Every message starts queued, and the effect below starts whichever is
  // next once nothing else is running. The composer therefore never has to be
  // locked: type while a turn runs and the message waits its turn instead of
  // being refused. Only one turn runs at a time, and order is preserved.
  const onSend = (text: string) => {
    setLocal((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        text,
        // Replaced at send time; a queued turn has not been sent yet.
        baseCount: transcript.length,
        state: "queued",
      },
    ]);
  };

  // Fires the mutation only. The move from "queued" to "sending" happens in
  // the mutation's onMutate, so no state is set from inside an effect body.
  // A double fire is harmless: the client id makes the send idempotent, which
  // is the same property Retry relies on.
  const next = busy ? undefined : local.find((turn) => turn.state === "queued");
  const startTurn = send.mutate;
  const atSend = transcript.length;
  useEffect(() => {
    if (!next) return;
    startTurn({ id: next.id, text: next.text, baseCount: atSend });
  }, [next, atSend, startTurn]);

  const onRetry = (turn: LocalTurn) => {
    setLocal((prev) =>
      prev.map((row) =>
        row.id === turn.id
          ? { ...row, state: "sending", error: undefined }
          : row,
      ),
    );
    // Reusing the id is what makes a retry safe: DBOS returns the existing
    // workflow instead of starting a duplicate if the first POST got through.
    send.mutate({ id: turn.id, text: turn.text, baseCount: turn.baseCount });
  };

  return (
    <>
      <AgentSwitch sessionId={sessionId} agent={agent} disabled={busy} />
      {/* A starter queues like anything else typed; only Retry still waits,
          because retrying a turn while another one runs is ambiguous. */}
      <Transcript
        isLoading={messages.isLoading}
        isError={messages.isError}
        error={messages.error}
        isFetching={messages.isFetching}
        refetch={() => messages.refetch()}
        messages={transcript}
        local={visibleInTranscript}
        starters={startersFor(agent)}
        onStart={onSend}
        onRetry={busy ? undefined : onRetry}
      />
      <div className="shrink-0 border-t p-3">
        {/* Above the composer, in the order they block him: an approval is
            the thing standing between him and an answer, and below it the
            work already running that he does not need to chase. */}
        <div className="mb-3 flex flex-col gap-2 empty:mb-0">
          <ChatApprovals sessionId={sessionId} />
          <InFlight sessionId={sessionId} />
        </div>
        <QueuedMessages
          turns={queued}
          onRemove={(id) =>
            setLocal((prev) => prev.filter((turn) => turn.id !== id))
          }
        />
        <Composer disabled={messages.isLoading} busy={busy} onSend={onSend} />
      </div>
    </>
  );
}

/** Messages waiting behind the active turn, kept beside the composer so they
 * remain visible without looking like messages that have already been sent. */
function QueuedMessages({
  turns,
  onRemove,
}: {
  turns: LocalTurn[];
  onRemove: (id: string) => void;
}) {
  if (!turns.length) return null;

  return (
    <ul className="mb-2 flex flex-col gap-1.5" aria-label="Queued messages">
      {turns.map((turn, index) => (
        <li
          key={turn.id}
          className="bg-muted/40 flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2"
        >
          <CornerDownRight
            aria-hidden
            className="text-muted-foreground size-3.5 shrink-0"
          />
          <span className="min-w-0 flex-1 truncate text-sm">{turn.text}</span>
          <span className="text-muted-foreground shrink-0 text-xs">
            {index === 0 ? "Up next" : `Queued ${index + 1}`}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="text-muted-foreground hover:text-foreground shrink-0"
            aria-label={`Remove queued message: ${turn.text}`}
            title="Remove from queue"
            onClick={() => onRemove(turn.id)}
          >
            <Trash2 aria-hidden />
          </Button>
        </li>
      ))}
    </ul>
  );
}

/** Shows the session's agent and lets the owner switch it between turns. */
function AgentSwitch({
  sessionId,
  agent,
  disabled,
}: {
  sessionId: string;
  agent: string | null;
  disabled: boolean;
}) {
  const queryClient = useQueryClient();
  const agents = useQuery({ queryKey: qk.agents, queryFn: api.agents });
  const switchAgent = useMutation({
    mutationFn: (next: string) => api.setChatSessionAgent(sessionId, next),
    onSuccess: (result) => {
      toast(`Agent set to ${result.agent}`);
      queryClient.invalidateQueries({ queryKey: qk.chatSessions });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const info = agents.data?.find((row) => row.name === agent) ?? null;

  return (
    <div className="flex shrink-0 items-start gap-3 border-b px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{agent ?? "No agent"}</p>
        <p className="text-muted-foreground mt-0.5 truncate text-xs">
          {disabled
            ? "Working. You can send the next message when this turn finishes."
            : (info?.description ?? "")}
        </p>
      </div>
      <Select
        value={agent ?? ""}
        onValueChange={(next) => {
          if (next && next !== agent) switchAgent.mutate(next);
        }}
        disabled={disabled || switchAgent.isPending}
      >
        <SelectTrigger
          id={`agent-${sessionId}`}
          size="sm"
          aria-label="Switch the agent for this chat"
          className="w-36 shrink-0"
        >
          <SelectValue placeholder="Pick an agent" />
        </SelectTrigger>
        <SelectContent>
          {(agents.data ?? []).map((row) => (
            <SelectItem key={row.name} value={row.name}>
              {row.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
