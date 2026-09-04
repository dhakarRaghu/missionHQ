"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { CostChart } from "@/components/features/agents/cost-chart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import { type EvalScore, evalKeys, evalsApi } from "@/lib/api/evals";
import type { AgentDraft } from "@/lib/api/types";
import { guideFor } from "@/lib/agent-guide";
import { describeCron } from "@/lib/cron";

/** After an activate the backend exits in 2 s and launchd restarts it. */
const REFETCH_AFTER_MS = 8000;

/** "Eval: 0.73 (8/11) · 2 Sep 2026", or why there is no score. */
function evalLine(
  row: EvalScore | undefined,
  state: { isPending: boolean; isError: boolean },
) {
  if (row) {
    const date = new Date(row.ts).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
    return `Eval: ${row.score.toFixed(2)} (${row.passed}/${row.cases}) · ${date}`;
  }
  if (state.isPending) return "Eval: loading…";
  if (state.isError) return "Eval: unavailable";
  return "no evals yet";
}

export function AgentList() {
  const queryClient = useQueryClient();
  const agents = useQuery({ queryKey: qk.agents, queryFn: api.agents });
  // Weekly spend per agent comes from /api/costs. Optional data.
  const costs = useQuery({ queryKey: qk.costs, queryFn: api.costs });
  const weekByAgent = useMemo(
    () =>
      new Map((costs.data?.week_by_agent ?? []).map((row) => [row.agent, row])),
    [costs.data],
  );
  // Latest eval score per agent from /api/evals/latest. Optional data.
  const evals = useQuery({ queryKey: evalKeys.latest, queryFn: evalsApi.latest });
  const evalByAgent = useMemo(
    () => new Map((evals.data ?? []).map((row) => [row.agent, row])),
    [evals.data],
  );

  const togglePause = useMutation({
    mutationFn: ({ name, paused }: { name: string; paused: boolean }) =>
      api.setAgentPaused(name, paused),
    onSuccess: (result) => {
      toast(`${result.agent} ${result.paused ? "paused" : "resumed"}`);
      queryClient.invalidateQueries({ queryKey: qk.agents });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (agents.isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading agents">
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (agents.isError) {
    return (
      <ErrorState
        message={agents.error.message}
        onRetry={() => agents.refetch()}
        retrying={agents.isFetching}
      />
    );
  }
  if (!agents.data?.length) {
    return (
      <EmptyState title="No agents loaded">
        Each agent is a folder under agents/ with a job.md manifest. If you
        expected one here, its manifest failed to parse.
      </EmptyState>
    );
  }

  return (
    <>
      <CostChart />
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {agents.data.map((agent) => {
          const week = weekByAgent.get(agent.name);
          const pending =
            togglePause.isPending && togglePause.variables?.name === agent.name;
          return (
            <Card key={agent.name}>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center justify-between text-base">
                  <Link
                    href={`/agents/${encodeURIComponent(agent.name)}`}
                    className="underline-offset-4 hover:underline"
                  >
                    {agent.name}
                  </Link>
                  {agent.paused ? (
                    <Badge variant="secondary" tone="blocked">
                      paused
                    </Badge>
                  ) : null}
                </CardTitle>
                <p className="text-muted-foreground text-sm">
                  {agent.description}
                </p>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                <AgentGuide name={agent.name} />

                <details>
                  <summary className="text-muted-foreground cursor-pointer text-xs select-none">
                    Tools it holds ({agent.tools.length})
                  </summary>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {agent.tools.map((tool) => (
                      <Badge
                        key={tool}
                        variant="outline"
                        className="font-normal"
                      >
                        {tool}
                      </Badge>
                    ))}
                  </div>
                </details>

                <dl className="text-muted-foreground grid grid-cols-2 gap-1 text-xs">
                  <dt>Model role</dt>
                  <dd className="text-foreground text-right">{agent.model}</dd>
                  <dt>Spend today</dt>
                  <dd className="text-foreground text-right tabular-nums">
                    ${agent.spend_today_usd.toFixed(4)} / $
                    {agent.daily_cap_usd.toFixed(2)}
                  </dd>
                  <dt>This week</dt>
                  <dd className="text-foreground text-right tabular-nums">
                    {week
                      ? `$${week.usd.toFixed(4)} · ${week.runs} run${week.runs === 1 ? "" : "s"}`
                      : costs.isError
                        ? "unavailable"
                        : "$0.0000 · 0 runs"}
                  </dd>
                  <dt>Per-run cap</dt>
                  <dd className="text-foreground text-right tabular-nums">
                    ${agent.caps.cost_per_run_usd.toFixed(2)} ·{" "}
                    {agent.caps.tool_calls} tool calls
                  </dd>
                  <dt>Vault writes</dt>
                  <dd className="text-foreground text-right break-all">
                    {agent.vault_write_scopes.length
                      ? agent.vault_write_scopes.join(", ")
                      : "none"}
                  </dd>
                </dl>

                <CronList cron={agent.cron} />

                <p className="text-muted-foreground text-xs tabular-nums">
                  {evalLine(evalByAgent.get(agent.name), evals)}
                </p>

                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={pending}
                    aria-label={`${agent.paused ? "Resume" : "Pause"} ${agent.name}`}
                    onClick={() =>
                      togglePause.mutate({
                        name: agent.name,
                        paused: !agent.paused,
                      })
                    }
                  >
                    {agent.paused ? "Resume" : "Pause"}
                  </Button>
                  <Button size="sm" variant="ghost" asChild>
                    <Link href={`/agents/${encodeURIComponent(agent.name)}`}>
                      Open
                    </Link>
                  </Button>
                  <Button size="sm" variant="ghost" asChild>
                    <Link
                      href={`/agents/${encodeURIComponent(agent.name)}/config`}
                    >
                      Configure
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <DraftsSection />
    </>
  );
}

/** What this agent is for and how to get value from it. */
function AgentGuide({ name }: { name: string }) {
  const guide = guideFor(name);
  if (!guide) return null;
  return (
    <div className="flex flex-col gap-2">
      <p>{guide.does}</p>
      <div>
        <p className="text-muted-foreground text-xs">How to use it</p>
        <ul className="mt-1 flex list-disc flex-col gap-0.5 pl-4 text-sm">
          {guide.use.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
      <p className="text-muted-foreground text-xs">
        Writes to <span className="font-mono">{guide.output}</span>
      </p>
    </div>
  );
}

/** Each schedule with its prompt behind a disclosure (prompts are long). */
function CronList({ cron }: { cron: { schedule: string; prompt: string }[] }) {
  if (!cron.length) {
    return <p className="text-muted-foreground text-xs">No schedules.</p>;
  }
  return (
    <ul className="flex flex-col gap-1 text-xs">
      {cron.map((entry, i) => (
        <li key={`${entry.schedule}-${i}`}>
          <details>
            <summary className="cursor-pointer select-none">
              <span className="text-muted-foreground">Runs </span>
              <span>{describeCron(entry.schedule)}</span>
              <code className="bg-muted text-muted-foreground ml-1.5 rounded px-1 font-mono">
                {entry.schedule}
              </code>
            </summary>
            <p className="text-muted-foreground mt-1 break-words whitespace-pre-wrap">
              {entry.prompt}
            </p>
          </details>
        </li>
      ))}
    </ul>
  );
}

/** Agent folders whose job.md says status: draft (written by the factory
 * agent). Activate flips them to active and restarts the backend. */
function DraftsSection() {
  const drafts = useQuery({
    queryKey: qk.agentDrafts,
    queryFn: api.agentDrafts,
  });

  if (drafts.isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading drafts" className="mt-6">
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }
  if (drafts.isError) {
    return (
      <p role="alert" className="text-muted-foreground mt-6 text-sm">
        Drafts unavailable: {drafts.error.message}
      </p>
    );
  }
  if (!drafts.data?.length) return null;

  return (
    <section aria-label="Drafts" className="mt-6">
      <h2 className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
        Drafts
      </h2>
      <div className="grid gap-4 md:grid-cols-2">
        {drafts.data.map((draft) => (
          <Card key={draft.name}>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between text-base">
                <Link
                  href={`/agents/${encodeURIComponent(draft.name)}`}
                  className="underline-offset-4 hover:underline"
                >
                  {draft.name}
                </Link>
                <Badge variant="secondary" tone="muted">
                  draft
                </Badge>
              </CardTitle>
              <p className="text-muted-foreground text-sm">{draft.description}</p>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <div className="flex flex-wrap gap-1">
                {draft.tools.map((tool) => (
                  <Badge key={tool} variant="outline" className="font-normal">
                    {tool}
                  </Badge>
                ))}
              </div>
              <dl className="text-muted-foreground grid grid-cols-2 gap-1 text-xs">
                <dt>Model role</dt>
                <dd className="text-foreground text-right">{draft.model}</dd>
                <dt>Schedules</dt>
                <dd className="text-foreground text-right">
                  {draft.cron.length
                    ? draft.cron.map((c) => c.schedule).join(", ")
                    : "none"}
                </dd>
              </dl>
              <div className="flex items-center gap-2">
                <ActivateDialog draft={draft} />
                <Button size="sm" variant="ghost" asChild>
                  <Link href={`/agents/${encodeURIComponent(draft.name)}`}>
                    Edit config
                  </Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

/** POST /api/agents/{name}/activate behind a confirm: it restarts the backend. */
function ActivateDialog({ draft }: { draft: AgentDraft }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const activate = useMutation({
    mutationFn: () => api.activateAgent(draft.name),
    onSuccess: (result) => {
      toast(result.message || `${result.activated} activated; restarting`);
      setOpen(false);
      window.setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: qk.agents });
        queryClient.invalidateQueries({ queryKey: qk.health });
      }, REFETCH_AFTER_MS);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" aria-label={`Activate ${draft.name}`}>
          Activate
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Activate {draft.name} and restart?</DialogTitle>
          <DialogDescription>
            The draft is validated again and its job.md set to active. Agents
            load only at startup, so the backend exits in 2 seconds and launchd
            starts it again with {draft.name} loaded. The console is
            unavailable for a few seconds; running jobs recover on their own.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter showCloseButton>
          <Button
            type="button"
            variant="destructive"
            disabled={activate.isPending}
            onClick={() => activate.mutate()}
          >
            {activate.isPending ? "Activating…" : "Activate and restart"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
