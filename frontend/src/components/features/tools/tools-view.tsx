"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, ShieldAlert } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";
import {
  type ToolCatalogEntry,
  agentAdminApi,
  agentAdminKeys,
} from "@/lib/api/agents-admin";

/** What an action class means for the owner, in one sentence. */
const ACTION_GROUPS: { key: string; title: string; blurb: string }[] = [
  {
    key: "NOTIFY",
    title: "Talk to you",
    blurb:
      "Sends you a message. Free to use, but capped so agents cannot flood you.",
  },
  {
    key: "READ",
    title: "Read things",
    blurb:
      "Reads the vault, the board or a web page. No approval needed, because nothing changes.",
  },
  {
    key: "VAULT_WRITE",
    title: "Write to the vault",
    blurb:
      "Writes a note. Each agent is limited to the folders named in its manifest, and every write is one git commit.",
  },
  {
    key: "EXTERNAL_WRITE",
    title: "Act outside",
    blurb:
      "Does something the world can see. Always stops for your approval first.",
  },
  {
    key: "SPEND",
    title: "Spend money",
    blurb: "Costs you something. Always stops for your approval first.",
  },
];

/**
 * Every tool the backend registers, grouped by what it is allowed to do, with
 * the agents that hold each one.
 *
 * The registry is the real permission model, so this page is the answer to
 * "what can my agents actually do". It is read-only on purpose: a tool is
 * granted in an agent's manifest, not toggled globally, so granting one here
 * would create a second source of truth.
 */
export function ToolsView() {
  const catalog = useQuery({
    queryKey: agentAdminKeys.toolsCatalog,
    queryFn: agentAdminApi.toolsCatalog,
  });
  const agents = useQuery({ queryKey: qk.agents, queryFn: api.agents });

  // Which agents hold each tool. A scoped grant ("vault_write:daily/**")
  // counts as holding the base tool.
  const holders = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const agent of agents.data ?? []) {
      for (const grant of agent.tools) {
        const base = grant.split(":")[0];
        map.set(base, [...(map.get(base) ?? []), agent.name]);
      }
    }
    return map;
  }, [agents.data]);

  if (catalog.isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading tools">
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (catalog.isError) {
    return (
      <ErrorState
        message={catalog.error.message}
        onRetry={() => catalog.refetch()}
        retrying={catalog.isFetching}
      />
    );
  }
  if (!catalog.data?.length) {
    return (
      <EmptyState title="No tools registered">
        Tools are Python functions marked with the @hq_tool decorator. If this
        is empty, the backend loaded none of them.
      </EmptyState>
    );
  }

  const byAction = new Map<string, ToolCatalogEntry[]>();
  for (const tool of catalog.data) {
    byAction.set(tool.action, [...(byAction.get(tool.action) ?? []), tool]);
  }
  const known = new Set(ACTION_GROUPS.map((group) => group.key));
  const other = catalog.data.filter((tool) => !known.has(tool.action));

  return (
    <div className="flex flex-col gap-6">
      {ACTION_GROUPS.map((group) => {
        const tools = byAction.get(group.key) ?? [];
        if (!tools.length) return null;
        return (
          <section key={group.key} aria-label={group.title}>
            <div className="mb-2 flex flex-wrap items-baseline gap-2">
              <h2 className="text-sm font-semibold">{group.title}</h2>
              <span className="text-muted-foreground text-xs tabular-nums">
                {tools.length} tool{tools.length === 1 ? "" : "s"}
              </span>
            </div>
            <p className="text-muted-foreground mb-3 max-w-prose text-sm">
              {group.blurb}
            </p>
            <div className="flex flex-col gap-2">
              {tools.map((tool) => (
                <ToolRow
                  key={tool.name}
                  tool={tool}
                  agents={holders.get(tool.name) ?? []}
                />
              ))}
            </div>
          </section>
        );
      })}

      {other.length ? (
        <section aria-label="Other">
          <h2 className="mb-2 text-sm font-semibold">Other</h2>
          <div className="flex flex-col gap-2">
            {other.map((tool) => (
              <ToolRow
                key={tool.name}
                tool={tool}
                agents={holders.get(tool.name) ?? []}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function ToolRow({
  tool,
  agents,
}: {
  tool: ToolCatalogEntry;
  agents: string[];
}) {
  const gated = tool.grantable === "no";
  const Icon = gated ? ShieldAlert : ShieldCheck;
  return (
    <Card>
      <CardContent className="flex flex-wrap items-start gap-x-4 gap-y-2 py-4">
        <Icon
          className={
            gated ? "text-status-approval mt-0.5 size-4" : "text-muted-foreground mt-0.5 size-4"
          }
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <p className="font-mono text-sm">{tool.name}</p>
          {tool.description ? (
            <p className="text-muted-foreground mt-0.5 text-sm">
              {tool.description}
            </p>
          ) : null}
          <p className="text-muted-foreground mt-1.5 text-xs">
            {gated
              ? "Every call stops for your approval."
              : "Runs without asking."}{" "}
            Content trust: {tool.trust.toLowerCase()}.
          </p>
        </div>
        <div className="flex max-w-64 flex-wrap justify-end gap-1">
          {agents.length ? (
            agents.map((name) => (
              <Badge key={name} variant="outline" className="font-normal" asChild>
                <Link href={`/agents/${encodeURIComponent(name)}`}>{name}</Link>
              </Badge>
            ))
          ) : (
            <span className="text-muted-foreground text-xs">no agent holds it</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
