"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import type { ChatSession } from "@/lib/api/types";
import { clockTime, exactTime, timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

/** Day buckets, so a long list reads as a history instead of a wall. */
const BUCKETS = ["Today", "Yesterday", "Earlier"] as const;
type Bucket = (typeof BUCKETS)[number];

function bucketOf(iso: string): Bucket {
  const then = new Date(iso);
  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  if (then.getTime() >= startOfToday) return "Today";
  if (then.getTime() >= startOfToday - 86_400_000) return "Yesterday";
  return "Earlier";
}

export function SessionList({
  sessions,
  activeId,
  onSelect,
  onDeleted,
}: {
  sessions: ReturnType<typeof useSessionsQuery>;
  activeId: string | null;
  onSelect: (id: string) => void;
  /** Called after a delete so the view can drop a stale selection. */
  onDeleted: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: api.deleteChatSession,
    onSuccess: (_result, id) => {
      onDeleted(id);
      queryClient.invalidateQueries({ queryKey: qk.chatSessions });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const grouped = useMemo(() => {
    const map = new Map<Bucket, ChatSession[]>();
    for (const session of sessions.data ?? []) {
      const key = bucketOf(session.last_active);
      map.set(key, [...(map.get(key) ?? []), session]);
    }
    return map;
  }, [sessions.data]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <NewChatForm onCreated={onSelect} />

      <div className="pane-scroll -mx-1 px-1">
        {sessions.isLoading ? (
          <div
            role="status"
            aria-busy="true"
            aria-label="Loading chats"
            className="flex flex-col gap-1"
          >
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
          </div>
        ) : sessions.isError ? (
          <ErrorState
            message={sessions.error.message}
            onRetry={() => sessions.refetch()}
            retrying={sessions.isFetching}
          />
        ) : !sessions.data?.length ? (
          <EmptyState compact title="No chats yet">
            Pick an agent above to start one.
          </EmptyState>
        ) : (
          BUCKETS.filter((bucket) => grouped.has(bucket)).map((bucket) => (
            <section key={bucket} className="mb-3 last:mb-0">
              <h3 className="text-muted-foreground bg-background/85 sticky top-0 z-10 px-1 py-1 text-xs font-medium backdrop-blur">
                {bucket}
              </h3>
              <ul className="flex flex-col gap-0.5" aria-label={bucket}>
                {(grouped.get(bucket) ?? []).map((session) => (
                  <li key={session.id}>
                    <SessionRow
                      session={session}
                      active={session.id === activeId}
                      sameDay={bucket === "Today"}
                      onSelect={() => onSelect(session.id)}
                      onDelete={() => remove.mutate(session.id)}
                      deleting={
                        remove.isPending && remove.variables === session.id
                      }
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </div>
  );
}

export function useSessionsQuery() {
  return useQuery({ queryKey: qk.chatSessions, queryFn: api.chatSessions });
}

function SessionRow({
  session,
  active,
  sameDay,
  onSelect,
  onDelete,
  deleting,
}: {
  session: ChatSession;
  active: boolean;
  /** Today's rows show a clock time; older ones show how long ago. */
  sameDay: boolean;
  onSelect: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <div
      className={cn(
        "group relative rounded-lg transition-colors",
        active ? "bg-muted" : "hover:bg-muted/60",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        className="flex w-full flex-col gap-0.5 px-2.5 py-2 pr-8 text-left"
      >
        <span
          className={cn(
            "line-clamp-2 text-sm leading-snug",
            session.preview ? "text-foreground" : "text-muted-foreground italic",
          )}
        >
          {session.preview ?? "New chat"}
        </span>
        <span className="text-muted-foreground flex items-center gap-1.5 text-xs">
          <span>{session.agent}</span>
          <span aria-hidden>·</span>
          <span title={exactTime(session.last_active)}>
            {sameDay
              ? clockTime(session.last_active)
              : timeAgo(session.last_active)}
          </span>
        </span>
      </button>
      {/* Test chats pile up fast. Deleting one removes its history only; the
          runs it produced stay in Runs as the cost and audit record. */}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        disabled={deleting}
        aria-label={`Delete this ${session.agent} chat`}
        title="Delete chat. Its runs are kept."
        onClick={onDelete}
        className="text-muted-foreground hover:text-status-danger absolute top-1.5 right-1 size-6 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
      >
        <Trash2 className="size-3.5" aria-hidden />
      </Button>
    </div>
  );
}

/** Agent picker plus a button that creates a session and selects it. */
function NewChatForm({ onCreated }: { onCreated: (id: string) => void }) {
  const queryClient = useQueryClient();
  const [agent, setAgent] = useState("");
  const agents = useQuery({ queryKey: qk.agents, queryFn: api.agents });

  const create = useMutation({
    mutationFn: api.createChatSession,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: qk.chatSessions });
      onCreated(result.session_id);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <form
      className="flex shrink-0 gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (agent && !create.isPending) create.mutate(agent);
      }}
    >
      <Select value={agent} onValueChange={setAgent}>
        <SelectTrigger
          aria-label="Agent for the new chat"
          className="min-w-0 flex-1"
        >
          <SelectValue
            placeholder={
              agents.isLoading
                ? "Loading agents…"
                : agents.isError
                  ? "Could not load agents"
                  : "New chat with…"
            }
          />
        </SelectTrigger>
        <SelectContent>
          {(agents.data ?? []).map((info) => (
            <SelectItem key={info.name} value={info.name}>
              {info.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        type="submit"
        size="icon"
        disabled={agent === "" || create.isPending}
        aria-label={agent ? `Start a chat with ${agent}` : "Pick an agent first"}
        title={agent ? `Start a chat with ${agent}` : "Pick an agent first"}
      >
        <Plus aria-hidden />
      </Button>
    </form>
  );
}
