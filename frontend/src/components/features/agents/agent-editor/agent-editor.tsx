"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "@/components/error-state";
import { JobForm } from "@/components/features/agents/agent-editor/job-form";
import { PolicyForm } from "@/components/features/agents/agent-editor/policy-form";
import { RawView } from "@/components/features/agents/agent-editor/raw-view";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  type AgentConfig,
  type ValidationResult,
  agentAdminApi,
  agentAdminKeys,
} from "@/lib/api/agents-admin";
import { describeCron } from "@/lib/cron";

type Tone = NonNullable<React.ComponentProps<typeof Badge>["tone"]>;

const STATUS_TONE: Record<string, Tone> = {
  active: "success",
  paused: "blocked",
  draft: "muted",
};

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  );
}

function Header({
  config,
  restartPending,
}: {
  config: AgentConfig;
  restartPending: boolean;
}) {
  const last = config.git[0];
  const needsRestart =
    restartPending || (!config.loaded && config.status !== "draft");
  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold">{config.name}</h2>
          <Badge
            variant="secondary"
            tone={STATUS_TONE[config.status] ?? "muted"}
          >
            {config.status}
          </Badge>
          {needsRestart ? (
            <Badge variant="secondary" tone="approval">
              {restartPending
                ? "saved, needs restart"
                : "not loaded, needs restart"}
            </Badge>
          ) : config.loaded ? (
            <Badge variant="secondary" tone="running">
              loaded
            </Badge>
          ) : (
            <Badge variant="secondary" tone="muted">
              not loaded
            </Badge>
          )}
          {config.parse_error ? (
            <Badge variant="secondary" tone="danger">
              job.md does not parse
            </Badge>
          ) : null}
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-4">
          <Field label="Model">{config.model || "—"}</Field>
          <Field label="Vault write scopes">
            {config.memory_refs.length ? (
              <span className="font-mono text-xs">
                {config.memory_refs.join(", ")}
              </span>
            ) : (
              "none"
            )}
          </Field>
          <Field label="Last commit">
            {last ? (
              <>
                <span className="font-mono text-xs">{last.hash}</span>{" "}
                <span className="text-muted-foreground text-xs">
                  {new Date(last.ts).toLocaleString()}
                </span>
                <span className="block truncate" title={last.message}>
                  {last.message}
                </span>
              </>
            ) : (
              <span className="text-muted-foreground">uncommitted</span>
            )}
          </Field>
          <Field label="Schedules">
            {config.cron.length ? (
              <ul>
                {config.cron.map((entry, i) => (
                  <li key={`${entry.schedule}-${i}`} title={entry.schedule}>
                    {describeCron(entry.schedule)}
                  </li>
                ))}
              </ul>
            ) : (
              "none"
            )}
          </Field>
        </dl>
        {config.parse_error ? (
          <p className="text-status-danger mt-3 text-xs">
            On-disk job.md: {config.parse_error}. Fix it in the Job tab and
            save.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Loads /api/agents/{name}/config and renders the header plus the three tabs. */
export function AgentEditor({ name }: { name: string }) {
  const config = useQuery({
    queryKey: agentAdminKeys.config(name),
    queryFn: () => agentAdminApi.config(name),
  });
  // Lives here (not in JobForm) so it survives the form remount after a save.
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [restartPending, setRestartPending] = useState(false);

  if (config.isPending) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading agent config">
        <Skeleton className="mb-6 h-32 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  if (config.isError) {
    return (
      <ErrorState
        message={config.error.message}
        onRetry={() => config.refetch()}
        retrying={config.isFetching}
      />
    );
  }

  const data = config.data;
  return (
    <>
      <Header config={data} restartPending={restartPending} />
      <Tabs defaultValue="job">
        <TabsList>
          <TabsTrigger value="job">Job</TabsTrigger>
          <TabsTrigger value="policy">Policy</TabsTrigger>
          <TabsTrigger value="raw">Raw</TabsTrigger>
        </TabsList>
        <TabsContent value="job" className="pt-4">
          <JobForm
            key={data.job_md_raw}
            name={name}
            config={data}
            result={result}
            onResult={setResult}
            restartPending={restartPending}
            onRestartPending={setRestartPending}
          />
        </TabsContent>
        <TabsContent value="policy" className="pt-4">
          <PolicyForm
            key={data.policy_md_raw}
            name={name}
            initial={data.policy_md_raw}
          />
        </TabsContent>
        <TabsContent value="raw" className="pt-4">
          <RawView jobMd={data.job_md_raw} policyMd={data.policy_md_raw} />
        </TabsContent>
      </Tabs>
    </>
  );
}
