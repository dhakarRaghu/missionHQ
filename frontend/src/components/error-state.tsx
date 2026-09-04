"use client";

import { Button } from "@/components/ui/button";

export function ErrorState({
  message,
  onRetry,
  retrying = false,
}: {
  message: string;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  return (
    <div
      role="alert"
      className="border-status-danger/40 bg-status-danger/5 flex flex-col items-start gap-3 rounded-lg border p-6 text-sm"
    >
      <p className="font-medium">Could not load data</p>
      <p className="text-muted-foreground break-words">{message}</p>
      {onRetry ? (
        <Button size="sm" variant="outline" onClick={onRetry} disabled={retrying}>
          {retrying ? "Retrying…" : "Retry"}
        </Button>
      ) : null}
    </div>
  );
}
