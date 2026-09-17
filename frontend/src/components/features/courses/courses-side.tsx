"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, PanelRightClose, PanelRightOpen } from "lucide-react";

import { splitCourse } from "@/components/features/courses/course-markdown";
import { Markdown } from "@/components/features/vault/markdown";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  learningApi,
  learningKeys,
  type CoursePhase,
} from "@/lib/api/learning";

/**
 * Right pane: what is inside the phase, and where he is in it.
 *
 * Shown for planned phases and older generated lessons. A published phase is
 * read as its enhanced page, which carries its own contents rail, so this
 * panel is not shown beside it.
 *
 * It collapses to a strip because on a 13-inch screen the reading pane wants
 * every column it can get.
 */
export function CoursesSide({
  phase,
  open,
  onToggle,
}: {
  phase: CoursePhase | undefined;
  open: boolean;
  onToggle: () => void;
}) {
  if (!open) {
    return (
      <aside className="side-pane flex min-h-0 flex-col items-center rounded-md border py-1">
        <Button
          size="icon"
          variant="ghost"
          onClick={onToggle}
          aria-label="Show what is in this phase"
        >
          <PanelRightOpen aria-hidden className="size-4" />
        </Button>
      </aside>
    );
  }

  return (
    <aside
      aria-label="In this phase"
      className="side-pane flex min-h-0 flex-col rounded-md border p-2"
    >
      <div className="flex shrink-0 items-center gap-1">
        <span className="text-xs font-medium text-muted-foreground">In this phase</span>
        <Button
          size="icon"
          variant="ghost"
          className="ml-auto"
          onClick={onToggle}
          aria-label="Hide what is in this phase"
        >
          <PanelRightClose aria-hidden className="size-4" />
        </Button>
      </div>

      {!phase ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Pick a phase to see what is in it.
        </p>
      ) : (
        <LegacyPanels key={phase.slug} phase={phase} />
      )}
    </aside>
  );
}

function LegacyPanels({ phase }: { phase: CoursePhase }) {
  const path = phase.lesson_md_path ?? "";
  const note = useQuery({
    queryKey: learningKeys.note(path),
    queryFn: () => learningApi.note(path),
    enabled: Boolean(path),
  });
  const sections = useMemo(
    () =>
      splitCourse(note.data?.content ?? "").sections.map((section) => ({
        title: section.heading,
        body: section.body,
      })),
    [note.data?.content],
  );

  const headings = sections.map((section) => section.title);
  const lab = pick(sections, /^labs?\b/i) || phase.lab || "";
  const checkpoint = pick(sections, /^checkpoint/i) || phase.test_out || "";
  const sources = pick(sections, /^(sources|where the claims came from)/i);
  // The phase's own outline stands in until the lesson is written.
  const outline = headings.length ? headings : (phase.sections ?? []);
  // The reviewer writes one finding per line, "location → problem → fix".
  // A leading list marker is dropped so a bulleted note does not bullet twice.
  const findings = (phase.lesson_review_notes ?? "")
    .split("\n")
    .map((line) => line.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, "").trim())
    .filter(Boolean);

  const body = (content: React.ReactNode) => {
    if (path && note.isPending) return <Skeleton className="h-24 w-full" />;
    if (path && note.isError) {
      return (
        <ErrorState
          message={(note.error as Error).message}
          onRetry={() => void note.refetch()}
        />
      );
    }
    return content;
  };

  return (
    <Tabs defaultValue="outline" className="mt-1 min-h-0 flex-1">
      {/* Five tabs in a narrow pane: xs text and tight padding keep them on
          one row. */}
      <TabsList variant="line" className="w-full shrink-0">
        <TabsTrigger value="outline" className="px-1 text-xs">Outline</TabsTrigger>
        <TabsTrigger value="lab" className="px-1 text-xs">Lab</TabsTrigger>
        <TabsTrigger value="checkpoint" className="px-1 text-xs">Check</TabsTrigger>
        <TabsTrigger value="sources" className="px-1 text-xs">Sources</TabsTrigger>
        <TabsTrigger value="review" className="px-1 text-xs">Review</TabsTrigger>
      </TabsList>

      <TabsContent value="outline" className="pane-scroll">
        {body(
          outline.length ? (
            // Headings, not links: an old lesson is in a sandboxed frame, so
            // nothing here can scroll it to one of them.
            <ol className="space-y-1.5 text-xs">
              {outline.map((title, i) => (
                <li key={`${i}-${title}`} className="flex gap-1.5">
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {i + 1}
                  </span>
                  <span>{title}</span>
                </li>
              ))}
            </ol>
          ) : (
            <Nothing>This lesson has no headings yet.</Nothing>
          ),
        )}
      </TabsContent>

      <TabsContent value="lab" className="pane-scroll">
        {body(
          lab ? (
            <div className="text-xs">
              <Markdown content={lab} path={path} />
            </div>
          ) : (
            <Nothing>No lab in this phase.</Nothing>
          ),
        )}
      </TabsContent>

      <TabsContent value="checkpoint" className="pane-scroll">
        {body(
          checkpoint ? (
            <div className="text-xs">
              <Markdown content={checkpoint} path={path} />
            </div>
          ) : (
            <Nothing>No checkpoint in this phase.</Nothing>
          ),
        )}
      </TabsContent>

      <TabsContent value="sources" className="pane-scroll">
        {body(
          sources ? (
            <div className="text-xs">
              <Markdown content={sources} path={path} />
            </div>
          ) : (
            <Nothing>The lesson lists no sources.</Nothing>
          ),
        )}
      </TabsContent>

      {/* Not wrapped in `body`: the findings come with the phase row, not the
          lesson markdown, so they do not wait on the note query. */}
      <TabsContent value="review" className="pane-scroll">
        {findings.length ? (
          <ul className="list-disc space-y-1.5 pl-4 text-xs">
            {findings.map((finding, i) => (
              <li key={`${i}-${finding}`}>{finding}</li>
            ))}
          </ul>
        ) : (
          <Nothing>No review findings recorded yet.</Nothing>
        )}
      </TabsContent>

      <a
        className="mt-1 inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        href={phase.url}
        rel="noreferrer"
        target="_blank"
      >
        original module
        <ExternalLink aria-hidden className="size-3" />
      </a>
    </Tabs>
  );
}

function Nothing({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

function pick(
  sections: { title: string; body: string }[],
  match: RegExp,
): string {
  return sections.find((section) => match.test(section.title))?.body.trim() ?? "";
}
