"use client";

import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "@/components/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { learningApi, learningKeys } from "@/lib/api/learning";

/**
 * A lesson's own page, in a frame that can run scripts and reach nothing.
 *
 * One component, two callers (Learn and Courses), because the sandbox string
 * is the contract and a second copy of it is a second chance to drop half of
 * it. `sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"`
 * with NO same-origin: tutor writes this markup from digests of pages nobody
 * vetted, and the console holds the token that can start agents. The popup
 * flags pair with the `<base target="_blank">` the API injects — on 2026-09-12
 * a source link without them navigated the frame itself and the live site
 * appeared inside the console.
 *
 * The HTML is fetched as text through `/api/learning/page` and handed over as
 * `srcDoc`. Never a `blob:` or `data:` URL: those inherit THIS origin.
 */
export function LessonPageFrame({
  path,
  title,
  className = "min-h-0 w-full flex-1 rounded-md border bg-background",
}: {
  path: string;
  title: string;
  className?: string;
}) {
  const page = useQuery({
    queryKey: learningKeys.page(path),
    queryFn: () => learningApi.page(path),
  });

  if (page.isPending) return <Skeleton className="min-h-0 flex-1" />;
  if (page.isError) {
    return (
      <ErrorState
        message={(page.error as Error).message}
        onRetry={() => void page.refetch()}
      />
    );
  }
  return (
    <iframe
      title={`${title} (lesson page)`}
      srcDoc={page.data.html}
      sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
      className={className}
    />
  );
}
