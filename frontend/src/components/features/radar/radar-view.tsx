"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ChevronDown,
  ExternalLink,
  Hammer,
  Plus,
  Quote,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  radarApi,
  radarKeys,
  type FinishBody,
  type Radar,
  type RadarEvidence,
  type RadarIdea,
  type RadarLeftOut,
  type RadarProblem,
  type RadarProject,
  type RadarRules,
} from "@/lib/api/radar";
import { useSseStatus } from "@/hooks/use-hq-events";
import { qk } from "@/lib/api/client";
import { exactTime, timeAgo } from "@/lib/time";
import { cn } from "@/lib/utils";

const DAY_MS = 86_400_000;

/**
 * Every action answers with the whole page, so the answer is written into
 * the cache and the page never shows a state the server does not have.
 */
function useRadarAction<T>(call: (input: T) => Promise<Radar>, done: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: call,
    // A read that is on its way would arrive after the answer and put the
    // old page back.
    onMutate: () => queryClient.cancelQueries({ queryKey: radarKeys.page }),
    onSuccess: (page) => {
      queryClient.setQueryData(radarKeys.page, page);
      queryClient.invalidateQueries({ queryKey: qk.today });
      toast(done);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * The path from what strangers wrote to what he builds, with the count at
 * each step. It is the answer to "where do these ideas come from": each
 * number is smaller than the one before it, and the page says why.
 */
function Pipeline({ page }: { page: Radar }) {
  const { collection, problems, ideas, projects, rules } = page;
  const steps = [
    {
      label: "Collected",
      value: collection.items ?? 0,
      note: `items from ${collection.sites ?? 0} sites`,
    },
    {
      label: "Report a problem",
      value: collection.problems ?? 0,
      note: collection.unread
        ? `${collection.unread} not read yet`
        : `${collection.none ?? 0} report none`,
    },
    {
      label: "Open problems",
      value: problems.open,
      note: `${problems.enough} strong enough for an idea`,
    },
    {
      label: "Ideas written",
      value: ideas.written,
      note: `in the last brief, ${ideas.dropped.length} dropped by the gate`,
    },
    {
      label: "Proposed",
      value: ideas.proposed.length,
      note: ideas.ranked_out.length
        ? `${ideas.ranked_out.length} more passed and ranked lower`
        : projects.running
          ? "one is being built"
          : "pick one",
    },
  ];
  return (
    <section aria-label="From collection to proposal" className="flex flex-col gap-2">
      <ol className="grid grid-cols-2 gap-2 xl:grid-cols-5">
        {steps.map((step, index) => (
          <li key={step.label} className="flex items-center gap-2">
            <div className="bg-card h-full flex-1 rounded-xl border px-3 py-2">
              <p className="text-muted-foreground text-xs">
                {index + 1}. {step.label}
              </p>
              <p className="text-xl font-semibold tabular-nums">{step.value}</p>
              <p className="text-muted-foreground text-xs">{step.note}</p>
            </div>
            {index < steps.length - 1 ? (
              <ArrowRight
                aria-hidden
                className="text-muted-foreground hidden size-4 shrink-0 xl:block"
              />
            ) : null}
          </li>
        ))}
      </ol>
      <p className="text-muted-foreground text-xs">
        {collection.newest ? (
          <>
            Last collected{" "}
            <span title={exactTime(collection.newest)}>{timeAgo(collection.newest)}</span>
            {" · "}
          </>
        ) : null}
        {ideas.brief ? `Last brief ${ideas.brief} · ` : ""}
        One brief every {rules.every_days} days, {rules.ideas} ideas at most.
      </p>
    </section>
  );
}

/** One quote and where it was said. The link opens the place itself. */
function EvidenceList({ evidence }: { evidence: RadarEvidence[] }) {
  if (!evidence.length) {
    return (
      <p className="text-muted-foreground text-xs">
        You met this problem yourself. It has no quotes.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {evidence.map((item) => (
        <li key={item.url} className="bg-muted/40 rounded-lg border px-3 py-2">
          <p className="flex gap-2 text-sm leading-6">
            <Quote aria-hidden className="text-muted-foreground mt-1 size-3 shrink-0" />
            <span>{item.quote}</span>
          </p>
          <p className="text-muted-foreground mt-1 flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="outline" className="text-xs">
              {item.kind}
            </Badge>
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer noopener"
              className="hover:text-foreground inline-flex min-w-0 items-center gap-1 underline-offset-2 hover:underline"
            >
              <span className="truncate">{item.domain}</span>
              <ExternalLink aria-hidden className="size-3 shrink-0" />
            </a>
            {item.published_at ? (
              <span title={exactTime(item.published_at)}>{timeAgo(item.published_at)}</span>
            ) : null}
          </p>
        </li>
      ))}
    </ul>
  );
}

function Field({ label, children }: { label: string; children: string }) {
  if (!children) return null;
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-muted-foreground text-xs font-medium">{label}</dt>
      <dd className="text-sm leading-6">{children}</dd>
    </div>
  );
}

/** The properties the judge says hold, by the words in radar.yaml. */
function NeedsYou({ idea, rules }: { idea: RadarIdea | RadarProject; rules: RadarRules }) {
  const held = (idea.scores?.needs_you ?? [])
    .filter((n) => n >= 1 && n <= rules.needs_you.length)
    .map((n) => rules.needs_you[n - 1]);
  if (!held.length) return null;
  return (
    <div className="flex flex-col gap-1">
      <p className="text-muted-foreground text-xs font-medium">
        Why an assistant cannot finish it alone: {held.length} of{" "}
        {rules.needs_you.length} properties hold, the gate asks for{" "}
        {rules.needs_you_min}
      </p>
      <ul className="text-sm leading-6">
        {held.map((line) => (
          <li key={line} className="flex gap-2">
            <span aria-hidden className="text-muted-foreground">
              ·
            </span>
            <span>{line}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Marks({ idea }: { idea: RadarIdea | RadarProject }) {
  const marks = [
    ["Learning", idea.scores?.learning],
    ["Fits your machines", idea.scores?.fits_rig],
    ["Sound measurement", idea.scores?.measurable],
  ] as const;
  return (
    <div className="flex flex-wrap gap-2">
      {marks.map(([label, value]) =>
        value === undefined ? null : (
          <Badge key={label} variant="secondary" className="text-xs tabular-nums">
            {label} {value}/5
          </Badge>
        ),
      )}
    </div>
  );
}

function IdeaBody({
  idea,
  rules,
}: {
  idea: RadarIdea | RadarProject;
  rules: RadarRules;
}) {
  return (
    <div className="flex flex-col gap-4">
      <dl className="grid gap-4 md:grid-cols-2">
        <Field label="What you build">{idea.build}</Field>
        <Field label="What you measure">{idea.measure}</Field>
        <Field label="Compared with">{idea.baseline}</Field>
        <Field label="Inputs">{idea.workload}</Field>
        <Field label="Where it runs">{idea.rig}</Field>
        <Field label="What you understand at the end">{idea.learn}</Field>
        <Field label="Why it needs you">{idea.hard_because}</Field>
        <Field label="First evening">{idea.first_step}</Field>
      </dl>
      <NeedsYou idea={idea} rules={rules} />
      <Marks idea={idea} />
      {idea.scores?.why ? (
        <p className="text-muted-foreground text-xs leading-5">
          The judge: {idea.scores.why}
        </p>
      ) : null}
      {idea.problem ? (
        <div className="flex flex-col gap-2 border-t pt-3">
          <p className="text-muted-foreground text-xs font-medium">
            The problem behind it · {idea.problem.domains} site
            {idea.problem.domains === 1 ? "" : "s"} · {idea.problem.evidence} quote
            {idea.problem.evidence === 1 ? "" : "s"}
          </p>
          <p className="text-sm leading-6">{idea.problem.statement}</p>
          <EvidenceList evidence={idea.evidence ?? []} />
        </div>
      ) : null}
    </div>
  );
}

function IdeaCard({
  idea,
  rules,
  rank,
  blocked,
}: {
  idea: RadarIdea;
  rules: RadarRules;
  rank: number;
  /** A project is running, so no other can start. */
  blocked: boolean;
}) {
  const [open, setOpen] = useState(rank === 0);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const choose = useRadarAction(
    (id: number) => radarApi.choose(id),
    "Started. Two weeks from today.",
  );
  const decline = useRadarAction(
    (id: number) => radarApi.decline(id, reason),
    "Declined. The next brief is told why.",
  );
  return (
    <article className="bg-card rounded-xl border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start gap-2 px-4 py-3 text-left"
      >
        <ChevronDown
          aria-hidden
          className={cn(
            "text-muted-foreground mt-1 size-4 shrink-0 transition-transform",
            !open && "-rotate-90",
          )}
        />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{idea.title}</span>
          <span className="text-muted-foreground mt-1 block text-sm leading-6">
            {idea.question}
          </span>
        </span>
        {rank === 0 ? <Badge className="text-xs">best</Badge> : null}
      </button>
      {open ? (
        <div className="flex flex-col gap-4 border-t px-4 py-4">
          <IdeaBody idea={idea} rules={rules} />
          <div className="flex flex-wrap items-center gap-2 border-t pt-3">
            <Button
              size="sm"
              disabled={blocked || choose.isPending}
              onClick={() => choose.mutate(idea.id)}
            >
              <Hammer aria-hidden className="size-3" />
              Build this one
            </Button>
            {declining ? (
              <>
                <Input
                  autoFocus
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Why not? Too easy, not interesting, no hardware"
                  aria-label="Why you decline this idea"
                  className="h-8 min-w-48 flex-1 text-sm"
                  maxLength={500}
                />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={decline.isPending || reason.trim().length < 3}
                  onClick={() => decline.mutate(idea.id)}
                >
                  Decline
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDeclining(false)}>
                  Cancel
                </Button>
              </>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setDeclining(true)}>
                Not this one
              </Button>
            )}
            {blocked ? (
              <p className="text-muted-foreground text-xs">
                One project runs at a time. End the running one first.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </article>
  );
}

/** The running project: how long is left, and the form that ends it. */
function RunningProject({ project, rules }: { project: RadarProject; rules: RadarRules }) {
  const [ending, setEnding] = useState(false);
  const [showIdea, setShowIdea] = useState(false);
  const [result, setResult] = useState("");
  const [surprise, setSurprise] = useState("");
  const [link, setLink] = useState("");
  const [met, setMet] = useState("");
  const finish = useRadarAction(
    (body: FinishBody) => radarApi.finish(project.project_id, body),
    "Saved. The problems you met are candidates for a later brief.",
  );
  const start = new Date(project.started_at).getTime();
  const due = new Date(project.due_at).getTime();
  // The clock is read once per render; the page refetches every minute.
  const now = new Date().getTime();
  const total = Math.max(due - start, DAY_MS);
  const spent = Math.min(Math.max(now - start, 0), total);
  const daysLeft = Math.ceil((due - now) / DAY_MS);
  const send = (status: FinishBody["status"]) =>
    finish.mutate({
      status,
      result,
      surprise,
      share_url: link,
      problems: met
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length >= 10)
        .map((line) => line.slice(0, 600))
        .slice(0, 8),
    });
  return (
    <section aria-label="The project you are building" className="flex flex-col gap-3">
      <h2 className="text-sm font-medium">You are building</h2>
      <article className="bg-card flex flex-col gap-4 rounded-xl border px-4 py-4">
        <div className="flex flex-col gap-1">
          <p className="text-base font-medium">{project.title}</p>
          <p className="text-muted-foreground text-sm leading-6">{project.question}</p>
        </div>
        <div className="flex flex-col gap-1">
          <Progress value={(spent / total) * 100} aria-label="Time used" />
          <p className="text-muted-foreground text-xs">
            Started{" "}
            <span title={exactTime(project.started_at)}>{timeAgo(project.started_at)}</span>
            {" · "}
            {daysLeft > 0
              ? `${daysLeft} day${daysLeft === 1 ? "" : "s"} left`
              : "the two weeks are over"}
          </p>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="text-muted-foreground h-7 self-start px-2 text-xs"
          onClick={() => setShowIdea((v) => !v)}
          aria-expanded={showIdea}
        >
          <ChevronDown
            aria-hidden
            className={cn("size-3 transition-transform", !showIdea && "-rotate-90")}
          />
          The plan and the problem behind it
        </Button>
        {showIdea ? <IdeaBody idea={project} rules={rules} /> : null}
        {ending ? (
          <div className="flex flex-col gap-3 border-t pt-3">
            <label className="flex flex-col gap-1 text-xs font-medium">
              What you measured
              <Textarea
                value={result}
                onChange={(e) => setResult(e.target.value)}
                placeholder="The number, the machine, how many runs, the spread"
                maxLength={2000}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium">
              What you did not expect
              <Textarea
                value={surprise}
                onChange={(e) => setSurprise(e.target.value)}
                maxLength={2000}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium">
              Problems you met on the way, one per line
              <Textarea
                value={met}
                onChange={(e) => setMet(e.target.value)}
                placeholder="Each line becomes a problem of your own for a later brief"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium">
              Where you shared it
              <Input
                value={link}
                onChange={(e) => setLink(e.target.value)}
                placeholder="https://"
                maxLength={500}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={finish.isPending || !result.trim() || !link.trim()}
                onClick={() => send("shared")}
              >
                Built and shared
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={finish.isPending || !result.trim()}
                onClick={() => send("built")}
              >
                Built, not shared yet
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={finish.isPending}
                onClick={() => send("stopped")}
              >
                Stop the project
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEnding(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <Button size="sm" className="self-start" onClick={() => setEnding(true)}>
            End the project
          </Button>
        )}
      </article>
    </section>
  );
}

function LeftOut({ title, rows }: { title: string; rows: RadarLeftOut[] }) {
  const [open, setOpen] = useState(false);
  if (!rows.length) return null;
  return (
    <section className="flex flex-col gap-2">
      <Button
        size="sm"
        variant="ghost"
        className="text-muted-foreground h-7 self-start px-2 text-xs"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <ChevronDown
          aria-hidden
          className={cn("size-3 transition-transform", !open && "-rotate-90")}
        />
        {title} · {rows.length}
      </Button>
      {open ? (
        <ul className="flex flex-col gap-2">
          {rows.map((row) => (
            <li key={row.id} className="rounded-lg border border-dashed px-3 py-2">
              <p className="text-sm">{row.title}</p>
              <p className="text-muted-foreground mt-1 text-xs leading-5">
                {row.reason || "No reason was stored."}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function ProblemRow({ problem }: { problem: RadarProblem }) {
  const [open, setOpen] = useState(false);
  const detail = useQuery({
    queryKey: radarKeys.problem(problem.id),
    queryFn: () => radarApi.problem(problem.id),
    enabled: open,
  });
  const dismiss = useRadarAction(
    (id: number) => radarApi.dismiss(id),
    "Dismissed. It will not come back under other words.",
  );
  const enough = Boolean(problem.enough);
  const [confirming, setConfirming] = useState(false);
  return (
    <li className="bg-card rounded-lg border">
      <div className="flex items-start gap-2 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-start gap-2 text-left"
        >
          <ChevronDown
            aria-hidden
            className={cn(
              "text-muted-foreground mt-1 size-4 shrink-0 transition-transform",
              !open && "-rotate-90",
            )}
          />
          <span className="min-w-0 flex-1">
            <span className="block text-sm leading-6">{problem.statement}</span>
            <span className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
              {problem.origin === "owner" ? (
                <Badge className="text-xs">yours</Badge>
              ) : (
                <Badge variant={enough ? "secondary" : "outline"} className="text-xs">
                  {problem.domains} site{problem.domains === 1 ? "" : "s"}
                </Badge>
              )}
              {problem.strong ? (
                <Badge variant="secondary" className="text-xs">
                  loud report
                </Badge>
              ) : null}
              {problem.area ? <span>{problem.area}</span> : null}
              {!enough ? <span>not enough behind it for an idea yet</span> : null}
            </span>
          </span>
        </button>
        <Button
          size="sm"
          className={cn("h-7 shrink-0 px-2 text-xs", !confirming && "text-muted-foreground")}
          disabled={dismiss.isPending}
          variant={confirming ? "destructive" : "ghost"}
          aria-label={confirming ? "Confirm dismissing this problem" : "Dismiss this problem"}
          onClick={() => (confirming ? dismiss.mutate(problem.id) : setConfirming(true))}
          onBlur={() => setConfirming(false)}
        >
          <X aria-hidden className="size-3" />
          {confirming ? "Sure?" : "Dismiss"}
        </Button>
      </div>
      {open ? (
        <div className="border-t px-3 py-3">
          {detail.isLoading ? (
            <Skeleton className="h-16 w-full" aria-busy="true" />
          ) : detail.isError ? (
            <ErrorState message={detail.error.message} onRetry={() => detail.refetch()} />
          ) : (
            <EvidenceList evidence={detail.data?.evidence ?? []} />
          )}
        </div>
      ) : null}
    </li>
  );
}

function Problems({ page }: { page: Radar }) {
  const [text, setText] = useState("");
  const add = useRadarAction(
    (statement: string) => radarApi.addProblem(statement),
    "Added. Your own problem needs no second site.",
  );
  return (
    <section aria-label="Open problems" className="flex flex-col gap-3">
      <header className="flex flex-col gap-1">
        <h2 className="text-sm font-medium">Open problems</h2>
        <p className="text-muted-foreground text-xs">
          {page.problems.open} open, {page.problems.shown.length} shown, most
          sites first. An idea is written for a problem with{" "}
          {page.rules.min_domains} sites behind it, for one loud report, or for
          one you add yourself.
        </p>
      </header>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(text.trim(), { onSuccess: () => setText("") });
        }}
      >
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="A problem you met while building or reading"
          aria-label="A problem of your own"
          className="h-8 min-w-48 flex-1 text-sm"
          maxLength={600}
        />
        <Button
          type="submit"
          size="sm"
          variant="outline"
          disabled={add.isPending || text.trim().length < 10}
        >
          <Plus aria-hidden className="size-3" />
          Add
        </Button>
      </form>
      {page.problems.shown.length ? (
        <ul className="flex flex-col gap-2">
          {page.problems.shown.map((problem) => (
            <ProblemRow key={problem.id} problem={problem} />
          ))}
        </ul>
      ) : (
        <EmptyState title="No open problem yet" compact>
          The radar collects every morning at 06:30 and reads what it collected
          at 06:45.
        </EmptyState>
      )}
    </section>
  );
}

/** A built project that is not shared yet: the link is what is missing. */
function ShareLink({ project }: { project: RadarProject }) {
  const [link, setLink] = useState("");
  const share = useRadarAction(
    (url: string) =>
      radarApi.finish(project.project_id, {
        status: "shared",
        result: project.result,
        surprise: "",
        share_url: url,
        problems: [],
      }),
    "Marked as shared.",
  );
  return (
    <form
      className="mt-2 flex flex-wrap gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        share.mutate(link.trim());
      }}
    >
      <Input
        value={link}
        onChange={(e) => setLink(e.target.value)}
        placeholder="https:// where you shared it"
        aria-label="Where you shared this project"
        className="h-8 min-w-48 flex-1 text-sm"
        maxLength={500}
      />
      <Button
        type="submit"
        size="sm"
        variant="outline"
        disabled={share.isPending || !/^https?:\/\//.test(link.trim())}
      >
        Mark as shared
      </Button>
    </form>
  );
}

function PastProjects({ rows }: { rows: RadarProject[] }) {
  if (!rows.length) return null;
  return (
    <section aria-label="Projects you ended" className="flex flex-col gap-3">
      <h2 className="text-sm font-medium">Projects you ended</h2>
      <ul className="flex flex-col gap-2">
        {rows.map((row) => (
          <li key={row.project_id} className="bg-card rounded-lg border px-3 py-2">
            <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
              {row.title}
              <Badge
                variant={row.project_status === "stopped" ? "outline" : "secondary"}
                className="text-xs"
              >
                {row.project_status}
              </Badge>
            </p>
            {row.result ? <p className="mt-1 text-sm leading-6">{row.result}</p> : null}
            {row.surprise ? (
              <p className="text-muted-foreground mt-1 text-sm leading-6">
                Not expected: {row.surprise}
              </p>
            ) : null}
            <p className="text-muted-foreground mt-1 flex flex-wrap gap-2 text-xs">
              <span title={exactTime(row.finished_at)}>{timeAgo(row.finished_at)}</span>
              {row.share_url ? (
                <a
                  href={row.share_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="hover:text-foreground inline-flex items-center gap-1 hover:underline"
                >
                  shared <ExternalLink aria-hidden className="size-3" />
                </a>
              ) : null}
            </p>
            {row.project_status === "built" ? <ShareLink project={row} /> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Where project ideas come from when nobody hands him one.
 *
 * In the order he acts on it: the project he is building, then the ideas
 * that wait for a choice, then what stands behind them. The gate's drops are
 * on the page with their reasons, because a gate he cannot see is a gate he
 * cannot correct in radar.yaml.
 */
export function RadarView() {
  // The stream says when the radar collected, read or wrote a brief. The
  // page polls only while the stream is not connected.
  const stream = useSseStatus();
  const radar = useQuery({
    queryKey: radarKeys.page,
    queryFn: radarApi.page,
    refetchInterval: stream === "connected" ? false : 60_000,
  });

  if (radar.isLoading) {
    return (
      <div className="flex min-h-full flex-col gap-4 pb-8" aria-busy="true">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (radar.isError || !radar.data) {
    return (
      <ErrorState
        message={radar.error?.message ?? "The radar did not answer."}
        onRetry={() => radar.refetch()}
        retrying={radar.isFetching}
      />
    );
  }
  const page = radar.data;
  const { ideas, projects, rules } = page;
  return (
    <div className="flex min-h-full flex-col gap-8 pb-8">
      <Pipeline page={page} />

      {projects.running ? (
        <RunningProject project={projects.running} rules={rules} />
      ) : null}

      <section aria-label="Ideas that wait for a choice" className="flex flex-col gap-3">
        <header className="flex flex-col gap-1">
          <h2 className="text-sm font-medium">
            {projects.running ? "Other ideas that wait" : "Pick one to build"}
          </h2>
          <p className="text-muted-foreground text-xs">
            Each idea passed the gate: a coding assistant cannot finish it alone
            in one session, it fits your machines, and it ends in a number.
          </p>
        </header>
        {ideas.proposed.length ? (
          <ul className="flex flex-col gap-3">
            {ideas.proposed.map((idea, index) => (
              <li key={idea.id}>
                <IdeaCard
                  idea={idea}
                  rules={rules}
                  rank={index}
                  blocked={Boolean(projects.running)}
                />
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No idea waits">
            {ideas.brief
              ? `The brief of ${ideas.brief} has no idea left. The next one is written ${rules.every_days} days after it.`
              : `The first brief is written on a Sunday, from problems that ${rules.min_domains} sites report or that one loud report states.`}
          </EmptyState>
        )}
        <LeftOut title="Passed the gate and ranked lower" rows={ideas.ranked_out} />
        <LeftOut title="Dropped by the gate, with the reason" rows={ideas.dropped} />
        <LeftOut title="Declined by you" rows={ideas.declined} />
      </section>

      <Problems page={page} />
      <PastProjects rows={projects.past} />
    </div>
  );
}
