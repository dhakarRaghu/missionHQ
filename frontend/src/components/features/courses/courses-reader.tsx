"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CircleDashed,
  ExternalLink,
  FlaskConical,
  Maximize2,
  Minimize2,
  RefreshCw,
  Sparkles,
  Target,
} from "lucide-react";

import {
  isPlanned,
  phaseLabel,
  phaseParts,
  phaseState,
  phaseTitle,
  readAt,
  tidy,
} from "@/components/features/courses/course-format";
import { splitCourse } from "@/components/features/courses/course-markdown";
import { LessonPageFrame } from "@/components/features/learn/lesson-frame";
import { Markdown } from "@/components/features/vault/markdown";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  learningApi,
  learningKeys,
  SCORE_OUT_OF,
  type CoursePhase,
} from "@/lib/api/learning";
import { cn } from "@/lib/utils";

/**
 * Centre pane: the phase he is reading, as a course.
 *
 * A published phase is the text he wrote with Claude, rendered natively —
 * sections, lab, checkpoint — with Mission HQ's additions in place under the
 * section each belongs to. It used to sit in a sandboxed frame like the daily
 * article, and "this is a proper course" was the complaint. The header stays
 * put above the scrolling text so the part switch and "Mark as read" are
 * always in reach.
 *
 * A planned phase has no text yet: the pane shows its spec and says how it
 * gets written. Old generated lessons for phases that never came from the
 * platform keep their frame.
 */
export function CoursesReader({
  course,
  phase,
  phases,
  onSelect,
  focus = false,
  onToggleFocus,
}: {
  course: string;
  phase: CoursePhase | undefined;
  phases: CoursePhase[];
  onSelect: (slug: string) => void;
  focus?: boolean;
  onToggleFocus?: () => void;
}) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: learningKeys.coursePhases(course) });
    void queryClient.invalidateQueries({ queryKey: learningKeys.courses });
  };
  // Both mutations take what they act on as a variable rather than closing
  // over the selected phase: one reader serves every phase, and without it
  // "studying now" stayed on screen after he moved to the next one.
  const teach = useMutation({
    mutationFn: (slug: string) => learningApi.teachPhase(course, slug),
    onSuccess: invalidate,
  });
  // The gate: the evening run will not start the next phase until this one
  // is marked read. Read is per phase now, so it works on any published
  // phase, including one Mission HQ has not added to yet.
  const markRead = useMutation({
    mutationFn: (slug: string) => learningApi.markPhaseRead(course, slug),
    onSuccess: () => {
      invalidate();
      void queryClient.invalidateQueries({ queryKey: learningKeys.lessons });
    },
  });
  const published = phase?.source === "platform";
  const content = useQuery({
    queryKey: learningKeys.phaseContent(course, phase?.slug ?? ""),
    queryFn: () => learningApi.phaseContent(course, phase?.slug ?? ""),
    // Only for the outline of a phase whose enhanced page is not built yet.
    // The original text itself is never shown here: he reads Mission HQ's
    // version, and the original stays on the study platform.
    enabled: Boolean(phase && published && !phase.lesson_html_path),
    staleTime: 5 * 60_000,
  });

  if (!phase) {
    return (
      <section className="reader-pane flex min-h-0 flex-col">
        <EmptyState title="Nothing selected">
          Pick a phase on the left and it opens here.
        </EmptyState>
      </section>
    );
  }

  const state = phaseState(phase);
  const planned = isPlanned(phase);
  const index = phases.findIndex((p) => p.slug === phase.slug);
  const next = index >= 0 ? phases[index + 1] : undefined;
  const parts = phaseParts(phases, phase);
  const teaching = teach.variables === phase.slug;
  const marking = markRead.isPending && markRead.variables === phase.slug;
  const doc = content.data;
  // The published title is the course's own; the row's may be stale until the
  // next sync. A legacy lesson's article title is not the module's, so it only
  // replaces it once the article exists.
  const title = doc?.title
    ? doc.title
    : !published && (state === "read" || state === "unread")
      ? (phase.lesson_title ?? phase.title)
      : phase.title;
  const minutes = doc?.minutes || phase.minutes;

  const readControl =
    state === "read" ? (
      <span
        className="flex items-center gap-1 text-xs font-medium text-primary"
        title={readAt(phase) ?? undefined}
      >
        <Check aria-hidden className="size-3.5" />
        Read
      </span>
    ) : planned ? null : (
      <Button
        size="sm"
        variant={state === "unread" ? "default" : "secondary"}
        disabled={marking}
        onClick={() => markRead.mutate(phase.slug)}
      >
        <Check aria-hidden className="size-3.5" />
        {marking ? "Marking…" : "Mark as read"}
      </Button>
    );

  const footer = (
    <div className="flex flex-wrap items-center gap-3">
      {readControl}
      {next ? (
        <Button
          variant="outline"
          className="ml-auto h-auto max-w-full py-2 whitespace-normal"
          onClick={() => onSelect(next.slug)}
        >
          <span className="text-left">
            <span className="block text-xs text-muted-foreground">
              Next · Phase {phaseLabel(next)}
            </span>
            <span className="block text-sm font-medium">{phaseTitle(next.title)}</span>
          </span>
          <ArrowRight aria-hidden className="size-4 shrink-0" />
        </Button>
      ) : (
        <span className="ml-auto text-xs text-muted-foreground">
          Last phase of the course.
        </span>
      )}
    </div>
  );

  return (
    <section
      aria-label={`Phase ${phaseLabel(phase)}`}
      className="reader-pane flex min-h-0 flex-col gap-2"
    >
      <header className="shrink-0 space-y-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-xs font-medium tabular-nums text-muted-foreground">
            Phase {phaseLabel(phase)}
          </span>
          {parts.length > 1 ? (
            <nav aria-label="Parts of this phase" className="flex gap-1">
              {parts.map((part) => {
                const current = part.slug === phase.slug;
                return (
                  <button
                    key={part.slug}
                    type="button"
                    onClick={() => onSelect(part.slug)}
                    aria-current={current ? "true" : undefined}
                    aria-label={`Part ${phaseLabel(part)}: ${phaseTitle(part.title)}`}
                    className={cn(
                      "flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium tabular-nums transition-colors",
                      current
                        ? "border-primary bg-primary text-primary-foreground"
                        : "hover:bg-muted",
                    )}
                  >
                    {phaseLabel(part)}
                    {readAt(part) ? <Check aria-label="read" className="size-3" /> : null}
                  </button>
                );
              })}
            </nav>
          ) : null}
          <span className="text-xs text-muted-foreground">~{minutes} min</span>
          {planned ? (
            <Badge variant="outline" className="gap-1 border-dashed">
              <CircleDashed aria-hidden />
              planned
            </Badge>
          ) : null}
          {phase.lesson_score ? (
            <Badge variant="outline" className="shrink-0 tabular-nums">
              {phase.lesson_score}/{SCORE_OUT_OF.course}
            </Badge>
          ) : null}
          {phase.status === "taught" ? <ReviewBadge phase={phase} /> : null}

          <div className="ml-auto flex shrink-0 flex-wrap items-center gap-1">
            {published && state === "pending" ? (
              <Button
                size="sm"
                variant="ghost"
                disabled={teach.isPending && teaching}
                onClick={() => teach.mutate(phase.slug)}
                title="Mission HQ researches this phase and builds the enhanced version you read here"
              >
                <RefreshCw aria-hidden className="size-3.5" />
                {teach.isPending && teaching ? "Starting…" : "Build enhanced version"}
              </Button>
            ) : null}
            {!published && !planned && state === "pending" ? (
              <Button
                size="sm"
                variant="secondary"
                disabled={teach.isPending && teaching}
                onClick={() => teach.mutate(phase.slug)}
              >
                {teach.isPending && teaching ? "Starting…" : "Teach this now"}
              </Button>
            ) : null}
            {readControl}
            {onToggleFocus ? (
              <Button
                size="sm"
                variant={focus ? "secondary" : "ghost"}
                onClick={onToggleFocus}
                aria-pressed={focus}
                title={focus ? "Back to the course (Esc)" : "Read this phase over the whole window"}
              >
                {focus ? (
                  <Minimize2 aria-hidden className="size-3.5" />
                ) : (
                  <Maximize2 aria-hidden className="size-3.5" />
                )}
                {focus ? "Exit full view" : "Full view"}
              </Button>
            ) : null}
            {published && (doc?.original_url || phase.url) ? (
              <Button size="sm" variant="ghost" asChild>
                <a href={doc?.original_url || phase.url} target="_blank" rel="noreferrer">
                  <ExternalLink aria-hidden className="size-3.5" />
                  <span className="max-sm:sr-only">Original on study platform</span>
                </a>
              </Button>
            ) : null}
            {!published && phase.lesson_html_path ? (
              // A new tab, not a lightbox: the lesson keeps its own sandboxed
              // frame there, so the diagrams get the whole screen without the
              // markup ever reaching this origin.
              <Button size="sm" variant="ghost" asChild>
                <a
                  href={`/learn-full?path=${encodeURIComponent(phase.lesson_html_path)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink aria-hidden className="size-3.5" />
                  Open page in a tab
                </a>
              </Button>
            ) : null}
          </div>
        </div>

        <h2 className="text-lg leading-tight font-semibold tracking-tight">
          {phaseTitle(title)}
        </h2>

        {state === "unread" ? (
          <p className="text-xs text-muted-foreground">
            The next phase waits until this one is marked read.
          </p>
        ) : null}
        {markRead.isError && markRead.variables === phase.slug ? (
          <p role="alert" className="text-xs text-destructive">
            Could not mark it read: {(markRead.error as Error).message}
          </p>
        ) : null}
        {teaching && teach.isError ? (
          <p role="alert" className="text-xs text-destructive">
            {(teach.error as Error).message}
          </p>
        ) : null}
        {teaching && teach.data && !teach.data.started ? (
          <p role="alert" className="text-xs text-destructive">{teach.data.reason}</p>
        ) : null}
        {teaching && teach.data?.started ? (
          <p className="text-xs text-muted-foreground">
            {published
              ? "Building the enhanced version — research first, then the page, section by section. It opens here when it is ready."
              : "Studying now — the lesson lands here when it is written."}
          </p>
        ) : null}
      </header>

      {planned ? (
        <>
          <PlannedNotice course={course} />
          <PhaseSpec phase={phase} />
        </>
      ) : published && phase.lesson_html_path ? (
        <LessonPageFrame
          key={phase.lesson_html_path}
          path={phase.lesson_html_path}
          title={phase.lesson_title ?? title}
        />
      ) : published ? (
        <NotBuilt
          phase={phase}
          outline={
            content.data?.content ? splitCourse(content.data.content).sections : []
          }
          loading={content.isPending}
          building={teaching && Boolean(teach.data?.started)}
          canBuild={state === "pending"}
          starting={teach.isPending && teaching}
          onBuild={() => teach.mutate(phase.slug)}
          footer={footer}
        />
      ) : phase.lesson_html_path ? (
        <LessonPageFrame
          path={phase.lesson_html_path}
          title={phase.lesson_title ?? phase.title}
        />
      ) : phase.lesson_md_path ? (
        // A lesson written but not rendered: the markdown is the whole lesson,
        // so it is read here rather than sending him to the vault for it.
        <LessonText path={phase.lesson_md_path} />
      ) : (
        <PhaseSpec phase={phase} />
      )}
    </section>
  );
}

/**
 * A published phase whose enhanced page does not exist yet.
 *
 * The original text is not shown: he reads Mission HQ's version, and the
 * original stays on the study platform. What the phase covers is listed, so
 * he can decide to build it now.
 */
function NotBuilt({
  phase,
  outline,
  loading,
  building,
  canBuild,
  starting,
  onBuild,
  footer,
}: {
  phase: CoursePhase;
  outline: { id: string; number: string; title: string }[];
  loading: boolean;
  building: boolean;
  canBuild: boolean;
  starting: boolean;
  onBuild: () => void;
  footer: React.ReactNode;
}) {
  return (
    <div className="pane-scroll rounded-md border px-5 py-6">
      <div className="mx-auto max-w-2xl space-y-6">
        <div className="space-y-2 rounded-lg border border-dashed p-4">
          <p className="flex items-center gap-2 font-medium">
            <Sparkles aria-hidden className="size-4 text-primary" />
            The enhanced version of this phase is not built yet
          </p>
          <p className="text-sm text-muted-foreground">
            Mission HQ researches past the phase, then builds the page you read
            here: the whole phase, visual and interactive, with what changed
            since, corrections and real incidents worked in. It is built on the
            evening run, or now.
          </p>
          {building ? (
            <p className="text-sm text-primary">
              Building now: research first, then the page, section by section.
              It opens here when it is ready.
            </p>
          ) : canBuild ? (
            <Button size="sm" onClick={onBuild} disabled={starting}>
              <RefreshCw aria-hidden className="size-3.5" />
              {starting ? "Starting…" : "Build enhanced version"}
            </Button>
          ) : null}
        </div>

        <section>
          <h3 className="text-sm font-semibold">What this phase covers</h3>
          {loading ? (
            <Skeleton className="mt-2 h-32 w-full" />
          ) : outline.length ? (
            <ol className="mt-2 space-y-1.5">
              {outline.map((section) => (
                <li key={section.id} className="flex gap-3 text-sm">
                  <span className="w-8 shrink-0 text-xs tabular-nums text-muted-foreground">
                    {section.number}
                  </span>
                  <span>{section.title}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">{phase.summary}</p>
          )}
        </section>

        <div className="border-t pt-5">{footer}</div>
      </div>
    </div>
  );
}

/** Mission HQ does not write course text; it says where the text comes from. */
function PlannedNotice({ course }: { course: string }) {
  return (
    <div className="flex shrink-0 gap-2 rounded-md border border-dashed px-3 py-2 text-sm">
      <CircleDashed aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <p>
        <span className="font-medium">Planned — not published yet.</span>{" "}
        <span className="text-muted-foreground">
          Generate it with Claude (<code className="rounded bg-muted px-1 font-mono text-xs">/study {course}</code>)
          and publish it. It appears here after the next sync, and Mission HQ
          adds to it from then on.
        </span>
      </p>
    </div>
  );
}

/**
 * The independent reviewer's verdict, after it ran the lab.
 *
 * The self-score beside it is tutor marking its own work; this is the check
 * that did not. A taught phase from before the reviewer existed has no status
 * at all and shows nothing rather than a review that never happened.
 */
function ReviewBadge({ phase }: { phase: CoursePhase }) {
  switch (phase.lesson_review_status) {
    case "passed":
      return (
        <Badge variant="secondary" className="shrink-0 tabular-nums">
          {phase.lesson_review_score != null
            ? `reviewed · ${phase.lesson_review_score}/${SCORE_OUT_OF.course}`
            : "reviewed"}
        </Badge>
      );
    case "revise":
      return (
        <Badge variant="outline" className="shrink-0">
          sent back for revision
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="destructive" className="shrink-0">
          failed review
        </Badge>
      );
    case "pending":
      return (
        <Badge variant="outline" className="shrink-0 text-muted-foreground">
          awaiting review
        </Badge>
      );
    default:
      return null;
  }
}

function LessonText({ path }: { path: string }) {
  const note = useQuery({
    queryKey: learningKeys.note(path),
    queryFn: () => learningApi.note(path),
  });

  if (note.isPending) return <Skeleton className="min-h-0 flex-1" />;
  if (note.isError) {
    return (
      <ErrorState
        message={(note.error as Error).message}
        onRetry={() => void note.refetch()}
      />
    );
  }
  return (
    <div className="pane-scroll rounded-md border px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <Markdown content={note.data.content} path={path} />
      </div>
    </div>
  );
}

/**
 * What a phase is before it is taught.
 *
 * The syllabus knows the question, the story, the ground and the exercise;
 * printing them is the difference between "Teach this now" being a guess and
 * being a decision. The spec's text is markdown, so it is rendered as such —
 * printed raw, the test-out list showed its dashes and a trailing "---".
 * Every field is optional; the backend fills them in over time.
 */
function PhaseSpec({ phase }: { phase: CoursePhase }) {
  const nothing =
    !phase.question &&
    !phase.summary &&
    !phase.sections?.length &&
    !phase.lab &&
    !phase.test_out;

  return (
    <div className="pane-scroll rounded-md border px-5 py-4">
      <div className="mx-auto max-w-3xl space-y-5">
        {nothing ? (
          <EmptyState title="No detail yet">
            The syllabus has no detail for this phase yet.
          </EmptyState>
        ) : null}

        {phase.question ? (
          <section>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              The question
            </p>
            <p className="mt-1 text-lg leading-snug font-medium">{phase.question}</p>
            {phase.difficulty ? (
              <Badge variant="outline" className="mt-2 text-[10px] uppercase">
                {phase.difficulty}
              </Badge>
            ) : null}
          </section>
        ) : null}

        {tidy(phase.summary) ? (
          <section className="text-sm leading-relaxed">
            <h3 className="mb-1 text-sm font-semibold">
              {phase.source === "local" ? "Why you are here" : "Summary"}
            </h3>
            <Markdown content={tidy(phase.summary)} />
          </section>
        ) : null}

        {phase.sections?.length ? (
          <section>
            <h3 className="text-sm font-semibold">What this phase covers</h3>
            <ol className="mt-2 space-y-2">
              {phase.sections.map((section, i) => {
                const [head, ...rest] = section.split(/:\s+/u);
                const detail = rest.join(": ");
                const number = /^(\d+\.\d+)\s*[—-]\s*/u.exec(head);
                const name = number ? head.slice(number[0].length) : head;
                return (
                  <li key={section} className="flex gap-3 text-sm">
                    <span className="w-8 shrink-0 pt-px text-xs tabular-nums text-muted-foreground">
                      {number ? number[1] : i + 1}
                    </span>
                    <span>
                      <span className="font-medium">{name}</span>
                      {detail ? (
                        <span className="text-muted-foreground">: {detail}</span>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ol>
          </section>
        ) : null}

        {tidy(phase.lab) ? (
          <SpecBlock title="Lab" icon={<FlaskConical aria-hidden className="size-3.5" />}>
            {tidy(phase.lab)}
          </SpecBlock>
        ) : null}
        {tidy(phase.test_out) ? (
          <SpecBlock title="Test out" icon={<Target aria-hidden className="size-3.5" />}>
            {tidy(phase.test_out)}
          </SpecBlock>
        ) : null}
      </div>
    </div>
  );
}

function SpecBlock({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: string;
}) {
  return (
    <section className="rounded-md border bg-muted/40 px-4 py-3">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold">
        {icon}
        {title}
      </h3>
      <div className="mt-1 text-sm leading-relaxed">
        <Markdown content={children} />
      </div>
    </section>
  );
}
