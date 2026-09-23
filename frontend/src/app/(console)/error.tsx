"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/error-state";

// Client error boundary for every console view. `reset` re-renders the segment.
export default function ConsoleError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <ErrorState
      message={error.message || "Something went wrong while rendering this view."}
      onRetry={reset}
    />
  );
}
