"use client";

import { EmptyState } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { useHqEvents } from "@/hooks/use-hq-events";

export function LiveFeed() {
  const { feed, connected } = useHqEvents();

  if (!feed.length) {
    return (
      <EmptyState>
        {connected
          ? "Connected. Events will appear here as agents work."
          : "Reconnecting to the event stream…"}
      </EmptyState>
    );
  }

  return (
    <ol className="divide-border divide-y rounded-lg border">
      {feed.map((event) => (
        <li key={event.seq} className="flex items-start gap-3 px-4 py-3">
          <Badge variant="outline" className="mt-0.5 shrink-0 font-normal">
            {event.type}
          </Badge>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm">
              {String(event.payload.title ?? event.payload.event ?? event.payload.outcome ?? "—")}
            </p>
            <p className="text-muted-foreground text-xs">
              {event.agent ? `${event.agent} · ` : ""}
              {new Date(event.ts).toLocaleTimeString()} · seq {event.seq}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
