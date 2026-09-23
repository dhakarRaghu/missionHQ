"use client";

import { useEffect, useRef } from "react";

import { flushOutbox } from "@/lib/reader-sync";

/**
 * Send whatever the phone kept while it could not reach the backend: once when
 * a reader page loads, and again each time the browser comes back online.
 * `onFlushed` receives how many events are still waiting.
 */
export function useReaderSync(onFlushed?: (waiting: number) => void) {
  const onFlushedRef = useRef(onFlushed);
  useEffect(() => {
    onFlushedRef.current = onFlushed;
  });

  useEffect(() => {
    let live = true;
    const flush = () => {
      void flushOutbox().then((waiting) => {
        if (live) onFlushedRef.current?.(waiting);
      });
    };
    flush();
    window.addEventListener("online", flush);
    return () => {
      live = false;
      window.removeEventListener("online", flush);
    };
  }, []);
}
