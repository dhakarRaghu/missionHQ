"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { qk } from "@/lib/api/client";
import type { HqEvent } from "@/lib/api/types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";
const FEED_MAX = 200;

/**
 * One EventSource for the whole console. Server events invalidate the query
 * keys they affect, so the server stays the single source of truth. The last
 * seen sequence number is replayed on reconnect, so no event is missed.
 */
export function useHqEvents() {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [feed, setFeed] = useState<HqEvent[]>([]);
  const lastSeq = useRef<number>(0);

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const invalidate = (type: string) => {
      if (type.startsWith("task.")) {
        queryClient.invalidateQueries({ queryKey: ["tasks"] });
        queryClient.invalidateQueries({ queryKey: ["task-events"] });
      }
      if (type.startsWith("run.")) {
        queryClient.invalidateQueries({ queryKey: qk.runs });
        queryClient.invalidateQueries({ queryKey: qk.costs });
        queryClient.invalidateQueries({ queryKey: qk.agents });
      }
      if (type.startsWith("ticket.") || type.startsWith("approval")) {
        queryClient.invalidateQueries({ queryKey: ["tickets"] });
        queryClient.invalidateQueries({ queryKey: ["tasks"] });
      }
    };

    const connect = () => {
      source = new EventSource(`${BASE}/events?since=${lastSeq.current}`);

      source.onopen = () => {
        setConnected(true);
        // A reconnect can miss events the replay ring dropped: resync reads.
        queryClient.invalidateQueries();
      };

      source.onmessage = (raw) => {
        try {
          const event = JSON.parse(raw.data) as HqEvent;
          lastSeq.current = Math.max(lastSeq.current, event.seq);
          setFeed((prev) => [event, ...prev].slice(0, FEED_MAX));
          invalidate(event.type);
        } catch {
          // keep-alive comments and malformed frames are ignored
        }
      };

      source.onerror = () => {
        setConnected(false);
        source?.close();
        retry = setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      if (retry) clearTimeout(retry);
      source?.close();
    };
  }, [queryClient]);

  return { connected, feed };
}
