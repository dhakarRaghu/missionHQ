"use client";

import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";

import {
  isActive,
  jobMinutes,
  JobStateBadge,
} from "@/components/features/courses/video-jobs";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import {
  EDITOR_BAR,
  EDITOR_CRITERIA,
  mediaApi,
  mediaKeys,
  type EditorCriterion,
  type FactRow,
  type Narration,
  type VideoJob,
  type VideoJobDetail,
  type VideoReview,
} from "@/lib/api/media";
import { exactTime } from "@/lib/time";
import { cn } from "@/lib/utils";

/** The detail is read again this often while a task works on the job. */
const DETAIL_POLL_MS = 30_000;

/**
 * One video job in a right-hand panel, as runs open on the Runs page, so
 * the list he came from stays where it was.
 *
 * Top to bottom: what the video asks and the case it follows, a "make it
 * again" for a job that stopped, then the evidence: the contact sheet, the
 * notes and lesson mismatches, the
 * editor's scores, the facts the checker could not support, the code checks
 * still open, and last the narration itself, beat by beat.
 */
export function VideoJobSheet({
  jobId,
  onClose,
}: {
  jobId: string | null;
  onClose: () => void;
}) {
  return (
    <Sheet open={Boolean(jobId)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-3xl">
        {jobId ? <JobDetail key={jobId} id={jobId} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function JobDetail({ id }: { id: string }) {
  const detail = useQuery({
    queryKey: mediaKeys.job(id),
    queryFn: () => mediaApi.job(id),
    // Right after "Make video" the task is queued and the job file does not
    // exist yet: the 404 is expected, so it is not retried, it is polled.
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
    refetchInterval: (query) => {
      const state = query.state.data?.job.state;
      const missing =
        query.state.error instanceof ApiError && query.state.error.status === 404;
      return missing || (state && isActive(state)) ? DETAIL_POLL_MS : false;
    },
  });

  const job = detail.data?.job;
  return (
    <>
      <SheetHeader className="shrink-0 border-b pr-12">
        <SheetTitle className="leading-snug">
          {job?.title || detail.data?.plan?.title || id}
        </SheetTitle>
        <SheetDescription asChild>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            {job ? <JobStateBadge state={job.state} /> : null}
            {job ? <span>{minutesText(job, detail.data?.review ?? null)}</span> : null}
            {job?.updated ? <span>updated {exactTime(job.updated)}</span> : null}
            <span className="font-mono break-all">{job?.lesson_md ?? id}</span>
          </div>
        </SheetDescription>
      </SheetHeader>
      <div className="pane-scroll p-4">
        {detail.isPending ? (
          <Skeleton className="h-64 w-full" />
        ) : detail.isError ? (
          detail.error instanceof ApiError && detail.error.status === 404 ? (
            <p className="text-sm text-muted-foreground">
              The script task is queued. The job appears here when it starts
              writing; this panel checks again every 30 seconds.
            </p>
          ) : (
            <ErrorState
              message={(detail.error as Error).message}
              onRetry={() => void detail.refetch()}
            />
          )
        ) : (
          <JobBody detail={detail.data} />
        )}
      </div>
    </>
  );
}

/** "about 24 min" from the script, or the built length. */
function minutesText(job: VideoJob, review: VideoReview | null): string {
  return jobMinutes({ duration_s: job.duration_s, minutes: review?.minutes }) || "length not known yet";
}

function JobBody({ detail }: { detail: VideoJobDetail }) {
  const { job, plan, narration, review } = detail;
  return (
    <div className="space-y-6">
      {plan ? (
        <section className="space-y-2">
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              The question
            </p>
            <p className="mt-0.5 font-medium leading-snug">{plan.question}</p>
          </div>
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              The running case
            </p>
            <p className="mt-0.5 text-sm leading-relaxed">{plan.running_case}</p>
          </div>
        </section>
      ) : null}

      <JobActions job={job} />

      {detail.has_sheet ? <ContactSheet id={job.id} updated={job.updated} /> : null}

      <TextList title="Notes from the writer and the build" items={job.report} />
      <TextList title="Lesson mismatches" items={job.mismatches} />

      {review ? (
        <>
          <EditorScores scores={review.editor.scores} />
          <TextList
            title="Editor, whole video"
            items={review.editor.whole_video}
          />
          <EditorFindings review={review} />
          <Facts facts={review.facts} />
          <TextList title="Still open (code checks)" items={review.remaining} />
        </>
      ) : job.state === "writing" ? (
        <p className="text-sm text-muted-foreground">
          The reviews appear here when the script is written and checked.
        </p>
      ) : null}

      {narration ? <NarrationBeats narration={narration} /> : null}
    </div>
  );
}

/**
 * No approval step: a video goes from script to render by itself. A job
 * that stopped (a fact still wrong after its repair rounds, a code check
 * still open, a failed render) can be started again from the same lesson.
 */
function JobActions({ job }: { job: VideoJob }) {
  const queryClient = useQueryClient();
  const again = useMutation({
    mutationFn: () => mediaApi.makeVideo(job.lesson_md, job.mode === "article" ? "article" : "course"),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: mediaKeys.jobs }),
  });
  if (job.state !== "failed") return null;
  return (
    <section aria-label="Try again" className="space-y-2 rounded-md border p-3">
      <p className="text-sm text-muted-foreground">
        This video stopped. The reasons are in the notes below.
      </p>
      <Button size="sm" variant="secondary" disabled={again.isPending} onClick={() => again.mutate()}>
        <RotateCcw aria-hidden className="size-3.5" />
        {again.isPending ? "Starting…" : "Make it again"}
      </Button>
      <Outcome mutation={again} started="Started. The script is being written again." />
    </section>
  );
}

function Outcome({
  mutation,
  started,
}: {
  mutation: {
    isError: boolean;
    error: Error | null;
    data: { started: boolean; reason?: string } | undefined;
  };
  started: string;
}) {
  if (mutation.isError) {
    return (
      <p role="alert" className="text-xs text-destructive">
        {mutation.error?.message}
      </p>
    );
  }
  if (!mutation.data) return null;
  return mutation.data.started ? (
    <p className="text-xs text-muted-foreground">{started}</p>
  ) : (
    <p role="alert" className="text-xs text-destructive">
      {mutation.data.reason ?? "Nothing started."}
    </p>
  );
}

/**
 * The stills of every scene on one JPEG. The API serves it behind the
 * Authorization header, which an `<img>` cannot send, so it is read as a blob
 * and shown through an object URL. The URL is made and revoked in one effect
 * and set on the element directly, so a remount in development makes a new
 * one instead of showing a revoked one.
 */
function ContactSheet({ id, updated }: { id: string; updated: string }) {
  const sheet = useQuery({
    queryKey: mediaKeys.jobSheet(id, updated),
    queryFn: () => mediaApi.jobSheet(id),
    staleTime: Infinity,
  });
  const img = useRef<HTMLImageElement>(null);
  useEffect(() => {
    if (!sheet.data || !img.current) return;
    const url = URL.createObjectURL(sheet.data);
    img.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [sheet.data]);

  return (
    <section className="space-y-1.5">
      <h3 className="text-sm font-semibold">Contact sheet</h3>
      {sheet.isPending ? (
        <Skeleton className="aspect-video w-full" />
      ) : sheet.isError ? (
        <ErrorState
          message={(sheet.error as Error).message}
          onRetry={() => void sheet.refetch()}
        />
      ) : (
        // A blob URL made at run time: next/image has nothing to optimise.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          ref={img}
          alt="Stills of every scene in the video"
          className="w-full rounded-md border"
        />
      )}
    </section>
  );
}

function TextList({ title, items }: { title: string; items: string[] | undefined }) {
  if (!items?.length) return null;
  return (
    <section>
      <h3 className="text-sm font-semibold">
        {title} <span className="font-normal text-muted-foreground">· {items.length}</span>
      </h3>
      <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed">
        {items.map((item, i) => (
          <li key={i} className="break-words">
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

const CRITERION_LABEL: Record<EditorCriterion, string> = {
  answers_question: "Answers",
  connected: "Connected",
  thinks_aloud: "Thinks aloud",
  defined: "Defined",
  spoken: "Spoken",
  numbers: "Numbers",
  transfer: "Transfer",
};

/** Beat × the seven criteria. A score under the bar carries the warning token. */
function EditorScores({ scores }: { scores: VideoReview["editor"]["scores"] }) {
  if (!scores.length) return null;
  return (
    <section>
      <h3 className="text-sm font-semibold">Editor scores</h3>
      <p className="text-xs text-muted-foreground">
        1 to 5. Under {EDITOR_BAR} is marked: that sent the beat back to the writer.
      </p>
      <Table className="mt-1.5 text-xs">
        <TableHeader>
          <TableRow>
            <TableHead className="h-8">Beat</TableHead>
            {EDITOR_CRITERIA.map((c) => (
              <TableHead key={c} className="h-8 text-center">
                {CRITERION_LABEL[c]}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {scores.map((score) => (
            <TableRow key={score.beat}>
              <TableCell className="py-1 font-mono">{score.beat}</TableCell>
              {EDITOR_CRITERIA.map((c) => {
                const low = score[c] < EDITOR_BAR;
                return (
                  <TableCell
                    key={c}
                    className={cn(
                      "py-1 text-center tabular-nums",
                      low && "bg-status-blocked/15 font-semibold text-status-blocked",
                    )}
                  >
                    {score[c]}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}

function EditorFindings({ review }: { review: VideoReview }) {
  const findings = review.editor.findings;
  if (!findings.length) return null;
  return (
    <section>
      <h3 className="text-sm font-semibold">
        Editor findings{" "}
        <span className="font-normal text-muted-foreground">· {findings.length}</span>
      </h3>
      <ul className="mt-1.5 space-y-2 text-sm">
        {findings.map((f, i) => (
          <li key={i} className="space-y-0.5 rounded-md border px-3 py-2">
            <p className="text-xs text-muted-foreground">
              <span className="font-mono">{f.beat}</span> · {f.criterion}
            </p>
            <p className="italic">“{f.quote}”</p>
            <p>{f.problem}</p>
            <p className="text-muted-foreground">{f.instruction}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

const WRONG: FactRow["verdict"][] = ["contradicted", "unsupported"];

/**
 * The fact check. The lines it could not support come first, each with the
 * correction; the supported ones and the examples are counted and folded.
 */
function Facts({ facts }: { facts: FactRow[] }) {
  if (!facts.length) return null;
  const wrong = facts.filter((f) => WRONG.includes(f.verdict));
  const rest = facts.filter((f) => !WRONG.includes(f.verdict));
  return (
    <section className="space-y-1.5">
      <h3 className="text-sm font-semibold">
        Fact check{" "}
        <span className="font-normal text-muted-foreground">
          · {facts.length} lines, {wrong.length} flagged
        </span>
      </h3>
      {wrong.length ? (
        <ul className="space-y-2 text-sm">
          {wrong.map((f) => (
            <li key={`${f.beat}.${f.key}`} className="space-y-0.5 rounded-md border px-3 py-2">
              <p className="flex items-center gap-2 text-xs">
                <span className="font-mono">
                  {f.beat}.{f.key}
                </span>
                <Badge variant="secondary" tone="danger">
                  {f.verdict}
                </Badge>
              </p>
              {f.correction ? <p>{f.correction}</p> : null}
              {f.material_quote ? (
                <p className="text-xs text-muted-foreground">Material: “{f.material_quote}”</p>
              ) : null}
              {f.arithmetic ? (
                <p className="text-xs text-muted-foreground">Arithmetic: {f.arithmetic}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {rest.length ? (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-muted-foreground">
            {rest.length} supported or example lines
          </summary>
          <ul className="mt-1 space-y-1 pl-1">
            {rest.map((f) => (
              <li key={`${f.beat}.${f.key}`} className="text-xs">
                <span className="font-mono">
                  {f.beat}.{f.key}
                </span>{" "}
                <span className="text-muted-foreground">{f.verdict}</span>
                {f.material_quote ? (
                  <span className="text-muted-foreground"> · “{f.material_quote}”</span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

/**
 * The narration as he would hear it, beat by beat. The caption text is the
 * line; when the voice says it differently (numbers spelled out, symbols
 * read aloud), the spoken form sits under it, muted, and on hover.
 */
function NarrationBeats({ narration }: { narration: Narration }) {
  const beats = Object.entries(narration.beats ?? {});
  if (!beats.length) return null;
  return (
    <section className="space-y-4">
      <h3 className="text-sm font-semibold">Narration</h3>
      {beats.map(([beat, { chapter, lines }]) => (
        <div key={beat} className="space-y-1.5">
          <h4 className="flex items-baseline gap-2 text-sm font-medium">
            <span className="font-mono text-xs text-muted-foreground">{beat}</span>
            {chapter ?? null}
          </h4>
          <ol className="space-y-1.5 border-l pl-3 text-sm leading-relaxed">
            {lines.map((line) => {
              const differs = Boolean(line.say) && line.say !== line.text;
              return (
                <li key={line.key} title={differs ? `Said: ${line.say}` : undefined}>
                  <span className="mr-2 font-mono text-[11px] text-muted-foreground">
                    {line.key}
                  </span>
                  {line.text}
                  {differs ? (
                    <span className="block text-xs text-muted-foreground">
                      said: {line.say}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </div>
      ))}
    </section>
  );
}
