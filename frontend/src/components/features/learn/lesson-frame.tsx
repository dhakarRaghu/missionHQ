"use client";

import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorState } from "@/components/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useConceptTaps } from "@/hooks/use-concept-taps";
import { learningApi, learningKeys } from "@/lib/api/learning";
import type { ConceptTap, ConceptVerdict } from "@/lib/concept-taps";

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
 *
 * With a `lessonId`, the page's "Got it" / "Lost me" taps come out of the
 * frame as messages (`@/lib/concept-taps` checks them) and are written to the
 * backend here, where the next outline of the course reads them. The frame
 * itself still reaches nothing.
 */
export function LessonPageFrame({
  path,
  title,
  lessonId,
  className = "min-h-0 w-full flex-1 rounded-md border bg-background",
}: {
  path: string;
  title: string;
  lessonId?: string | null;
  className?: string;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const queryClient = useQueryClient();
  const page = useQuery({
    queryKey: learningKeys.page(path),
    queryFn: () => learningApi.page(path),
  });
  const stored = useQuery({
    queryKey: learningKeys.signals(lessonId ?? ""),
    queryFn: () => learningApi.signals(lessonId ?? ""),
    enabled: Boolean(lessonId),
  });
  // What he tapped in this view, shown at once rather than after the round
  // trip. Tagged with the lesson, because Learn swaps lessons in place.
  const [tapped, setTapped] = useState<{
    lesson: string;
    verdicts: Record<string, ConceptVerdict>;
  }>({ lesson: "", verdicts: {} });
  const save = useMutation({
    mutationFn: ({ lesson, tap }: { lesson: string; tap: ConceptTap }) =>
      learningApi.addSignal(lesson, tap.concept, tap.verdict),
    onSettled: (_data, _error, { lesson }) =>
      queryClient.invalidateQueries({ queryKey: learningKeys.signals(lesson) }),
  });

  const verdicts = useMemo(
    () => ({
      ...(stored.data?.verdicts ?? {}),
      ...(tapped.lesson === lessonId ? tapped.verdicts : {}),
    }),
    [stored.data, tapped, lessonId],
  );
  useConceptTaps(frame, verdicts, (tap) => {
    if (!lessonId) return;
    setTapped((prev) => ({
      lesson: lessonId,
      verdicts: {
        ...(prev.lesson === lessonId ? prev.verdicts : {}),
        [tap.concept]: tap.verdict,
      },
    }));
    save.mutate({ lesson: lessonId, tap });
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
    <>
      <iframe
        ref={frame}
        title={`${title} (lesson page)`}
        srcDoc={page.data.html}
        sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
        className={className}
      />
      {save.isError ? (
        <p role="alert" className="shrink-0 text-xs text-destructive">
          That answer was not saved: {(save.error as Error).message}
        </p>
      ) : null}
    </>
  );
}
