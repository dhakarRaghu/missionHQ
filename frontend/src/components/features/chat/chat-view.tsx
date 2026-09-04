"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Composer } from "@/components/features/chat/composer";
import {
  SessionList,
  useSessionsQuery,
} from "@/components/features/chat/session-list";
import {
  type LocalTurn,
  Transcript,
} from "@/components/features/chat/transcript";
import { EmptyState } from "@/components/empty-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, qk } from "@/lib/api/client";
import type { SendChatResult } from "@/lib/api/types";
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
    () =>
      sent.filter(
        (turn) =>
          turn.state === "error" || transcript.length < turn.baseCount + 2,
      ),
    [sent, transcript.length],
  );

  const send = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      api.sendChatMessage(sessionId, { text, client_id: id }),
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
    onError: (error: Error, { id }) => {
      toast.error(error.message);
      setLocal((prev) =>
        prev.map((turn) =>
          turn.id === id ? { ...turn, state: "error", error: error.message } : turn,
        ),
      );
    },
  });

  const busy = local.some(
    (turn) => turn.state === "sending" || turn.state === "waiting",
  );

  const onSend = (text: string) => {
    const id = crypto.randomUUID();
    setLocal((prev) => [
      ...prev,
      { id, text, baseCount: transcript.length, state: "sending" },
    ]);
    send.mutate({ id, text });
  };

  return (
    <>
      <AgentSwitch sessionId={sessionId} agent={agent} disabled={busy} />
      <Transcript
        isLoading={messages.isLoading}
        isError={messages.isError}
        error={messages.error}
        isFetching={messages.isFetching}
        refetch={() => messages.refetch()}
        messages={transcript}
        local={local}
        starters={startersFor(agent)}
        onStart={busy ? undefined : onSend}
      />
      <div className="shrink-0 border-t p-3">
        <Composer disabled={busy || messages.isLoading} onSend={onSend} />
      </div>
    </>
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
