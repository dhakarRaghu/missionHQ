"use client";

import { use } from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "@/components/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { readerApi, readerKeys } from "@/lib/reader";

/**
 * One lesson on the phone.
 *
 * The frame contract is the console's, unchanged and non-negotiable:
 * `sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"` with
 * NO same-origin, fed through `srcDoc`. The page is model-written markup, and
 * on this origin it would be markup running inside the deployment. The export
 * already put the content policy and `<base target="_blank">` inside the
 * document, the same two walls the API endpoint adds, because here there is
 * no endpoint to add them.
 *
 * Never point the tab straight at `/reader/lessons/<slug>.html`. That file is
 * served from this origin, so opening it directly is exactly the same-origin
 * rendering the sandbox exists to prevent.
 */
export default function ReadLessonPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const page = useQuery({
    queryKey: readerKeys.page(slug),
    queryFn: () => readerApi.page(slug),
    staleTime: 60_000,
  });

  return (
    <div className="flex h-dvh flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b px-2 py-2">
        <Link
          href="/read"
          className="hover:bg-accent text-muted-foreground flex items-center gap-1 rounded-md px-2 py-1.5 text-sm"
        >
          <ChevronLeft aria-hidden className="size-4" />
          Library
        </Link>
      </div>

      {page.isPending ? (
        <Skeleton className="m-4 flex-1" />
      ) : page.isError ? (
        <div className="p-4">
          <ErrorState
            message={(page.error as Error).message}
            onRetry={() => void page.refetch()}
            retrying={page.isRefetching}
          />
        </div>
      ) : (
        <iframe
          title="Lesson"
          srcDoc={page.data}
          sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
          className="bg-background w-full flex-1 border-0"
        />
      )}
    </div>
  );
}
