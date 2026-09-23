"use client";

import { useQuery } from "@tanstack/react-query";

import { qk } from "@/lib/api/client";
import type { HqEvent, SseStatus } from "@/lib/api/types";

// Thin readers. The single EventSource in src/lib/sse.ts writes these keys.
const cacheOnly = {
  staleTime: Infinity,
  gcTime: Infinity,
  refetchInterval: false as const,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
};

/** Last 200 server events, newest first. */
export function useFeed() {
  const { data } = useQuery<HqEvent[]>({
    queryKey: qk.feed,
    initialData: [],
    ...cacheOnly,
  });
  return data;
}

/** Connection state of the console-wide event stream. */
export function useSseStatus() {
  const { data } = useQuery<SseStatus>({
    queryKey: qk.sseStatus,
    initialData: "connecting",
    ...cacheOnly,
  });
  return data;
}
