"use client";

import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";

import { ErrorState } from "@/components/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { learningApi, learningKeys } from "@/lib/api/learning";

/**
 * One lesson, the whole window, in its own tab.
 *
 * Deliberately outside the `(console)` route group: the root layout carries
 * the providers, the console layout carries the shell, so a page here keeps
 * the authenticated client and loses the sidebar. That is the entire trick.
 *
 * The frame contract is the same as on the Learn page and is not negotiable:
 * `sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"` with
 * NO same-origin. The obvious shortcut for "open it in a tab" — building a
 * `blob:` or `data:` URL from the HTML and pointing the tab at it — is the
 * one thing that must never happen: a blob URL inherits THIS origin, which
 * would hand model-generated markup, written from pages nobody vetted, the
 * console's token and its storage. A chrome-less route rendering the same
 * sandboxed frame gives the full screen without giving away the origin.
 */
export default function LearnFullPage() {
  return (
    <Suspense fallback={<Skeleton className="h-dvh w-full" />}>
      <FullLesson />
    </Suspense>
  );
}

function FullLesson() {
  const path = useSearchParams().get("path") ?? "";
  const page = useQuery({
    queryKey: learningKeys.page(path),
    queryFn: () => learningApi.page(path),
    enabled: Boolean(path),
  });

  if (!path) {
    return (
      <div className="p-6">
        <ErrorState message="No lesson given. Open this from the Learn page." />
      </div>
    );
  }
  if (page.isPending) return <Skeleton className="h-dvh w-full" />;
  if (page.isError) {
    return (
      <div className="p-6">
        <ErrorState
          message={(page.error as Error).message}
          onRetry={() => void page.refetch()}
        />
      </div>
    );
  }

  return (
    <iframe
      title="Lesson"
      srcDoc={page.data.html}
      sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
      className="h-dvh w-full border-0 bg-background"
    />
  );
}
