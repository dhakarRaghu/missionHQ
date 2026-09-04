"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
import { exactTime, timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

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

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <NewChatForm onCreated={onSelect} />

      <div className="flex min-h-0 flex-1 flex-col gap-1.5">
        <h2 className="text-muted-foreground px-1 text-xs font-medium tracking-wide uppercase">
          Chats
        </h2>
        <div className="pane-scroll -mx-1 px-1">
          {sessions.isLoading ? (
            <div
              role="status"
              aria-busy="true"
              aria-label="Loading chats"
              className="flex flex-col gap-1"
            >
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : sessions.isError ? (
            <ErrorState
              message={sessions.error.message}
              onRetry={() => sessions.refetch()}
              retrying={sessions.isFetching}
            />
          ) : !sessions.data?.length ? (
            <EmptyState compact>No chats yet. Start one above.</EmptyState>
          ) : (
            <ul className="flex flex-col gap-1" aria-label="Chats">
              {sessions.data.map((session) => (
                <li key={session.id}>
                  <SessionRow
                    session={session}
                    active={session.id === activeId}
                    onSelect={() => onSelect(session.id)}
                    onDelete={() => remove.mutate(session.id)}
                    deleting={
                      remove.isPending && remove.variables === session.id
                    }
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
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
  onSelect,
  onDelete,
  deleting,
}: {
  session: ChatSession;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <div
      className={cn(
        "group hover:bg-muted/70 relative rounded-lg border border-transparent transition-colors",
        active && "bg-muted border-border",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        className="flex w-full flex-col items-start gap-1 px-2.5 py-2 text-left text-sm"
      >
        <span className="flex w-full items-center justify-between gap-2">
          <Badge variant="outline" className="font-normal">
            {session.agent}
          </Badge>
          <span
            className="text-muted-foreground text-xs whitespace-nowrap group-hover:invisible"
            title={exactTime(session.last_active)}
          >
            {timeAgo(session.last_active)}
          </span>
        </span>
        <span
          className={cn(
            "line-clamp-2 w-full text-xs leading-snug",
            session.preview
              ? "text-foreground"
              : "text-muted-foreground italic",
          )}
        >
          {session.preview ?? "New chat"}
        </span>
      </button>
      {/* Test chats pile up fast. Deleting one removes its history only; the
          runs it produced stay in Runs as the cost and audit record. */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            disabled={deleting}
            aria-label={`Delete this ${session.agent} chat`}
            onClick={onDelete}
            className="text-muted-foreground hover:text-status-danger absolute top-1 right-1 size-6 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          >
            <Trash2 className="size-3.5" aria-hidden />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Delete chat. Its runs are kept.</TooltipContent>
      </Tooltip>
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
