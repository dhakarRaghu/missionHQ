"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  ChevronRight,
  Coins,
  Gauge,
  NotebookText,
  Radio,
  Search,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, qk } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type Group = "agents" | "connections" | "workspace";

interface Row {
  group: Group;
  href: string;
  title: string;
  blurb: string;
  Icon: typeof Bot;
  /** Live value shown on the right, e.g. "6 loaded". */
  status?: string;
}

const GROUP_LABEL: Record<Group, string> = {
  agents: "Agent management",
  connections: "Connections",
  workspace: "Workspace",
};

const FILTERS: { value: Group | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "agents", label: "Agents" },
  { value: "connections", label: "Connections" },
  { value: "workspace", label: "Workspace" },
];

/**
 * One place that answers "where do I change this".
 *
 * Nothing is configured here. Every row is a link to the page that owns the
 * setting, because each of those pages already writes to a single source of
 * truth (a manifest, models.yaml, the env file). A second editor here would
 * make two.
 */
export function SettingsView() {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<Group | "all">("all");

  const agents = useQuery({ queryKey: qk.agents, queryFn: api.agents });
  const health = useQuery({ queryKey: qk.health, queryFn: api.health });
  const costs = useQuery({ queryKey: qk.costs, queryFn: api.costs });

  const loaded = agents.data?.length ?? 0;
  const paused = (agents.data ?? []).filter((row) => row.paused).length;

  const rows: Row[] = [
    {
      group: "agents",
      href: "/agents",
      title: "Agents",
      blurb: "What each one does, its schedule, its caps, and its manifest.",
      Icon: Bot,
      status: loaded
        ? `${loaded} loaded${paused ? `, ${paused} paused` : ""}`
        : undefined,
    },
    {
      group: "agents",
      href: "/tools",
      title: "Tools",
      blurb:
        "Everything agents can do, and which ones stop for your approval.",
      Icon: Wrench,
    },
    {
      group: "agents",
      href: "/vault",
      title: "Memory",
      blurb:
        "The blocks every agent reads before a run, and each agent's own notebook.",
      Icon: NotebookText,
    },
    {
      group: "connections",
      href: "/runs?tab=feed",
      title: "Event stream",
      blurb:
        "The live connection this console uses. A drop means pages stop updating.",
      Icon: Radio,
      status: health.data ? (health.data.ok ? "backend up" : "backend down") : undefined,
    },
    {
      group: "workspace",
      href: "/runs",
      title: "Spend and caps",
      blurb:
        "Every run with its real cost, against the daily cap set in the env file.",
      Icon: Coins,
      status: costs.data
        ? `$${costs.data.today_usd.toFixed(4)} of $${costs.data.daily_cap_usd.toFixed(2)} today`
        : undefined,
    },
    {
      group: "workspace",
      href: "/home",
      title: "Value week",
      blurb:
        "Whether you act on at least half of what the system sends you over seven days.",
      Icon: Gauge,
    },
  ];

  const needle = query.trim().toLowerCase();
  const shown = rows.filter(
    (row) =>
      (group === "all" || row.group === group) &&
      (!needle ||
        row.title.toLowerCase().includes(needle) ||
        row.blurb.toLowerCase().includes(needle)),
  );

  const groups = (["agents", "connections", "workspace"] as Group[]).filter(
    (key) => shown.some((row) => row.group === key),
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="relative">
        <Search
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          aria-hidden
        />
        <Input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find a setting"
          aria-label="Find a setting"
          className="h-9 pl-9"
        />
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter">
        {FILTERS.map((filter) => (
          <Button
            key={filter.value}
            type="button"
            size="sm"
            variant={group === filter.value ? "default" : "outline"}
            onClick={() => setGroup(filter.value)}
          >
            {filter.label}
          </Button>
        ))}
      </div>

      {!shown.length ? (
        <p className="text-muted-foreground text-sm">
          Nothing matches “{query}”.
        </p>
      ) : (
        groups.map((key) => (
          <section key={key} aria-label={GROUP_LABEL[key]}>
            <h2 className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
              {GROUP_LABEL[key]}
            </h2>
            <Card>
              <CardContent className="divide-border flex flex-col divide-y p-0">
                {shown
                  .filter((row) => row.group === key)
                  .map(({ href, title, blurb, Icon, status }) => (
                    <Link
                      key={href}
                      href={href}
                      className="hover:bg-muted/50 flex items-center gap-4 px-5 py-4 transition-colors first:rounded-t-xl last:rounded-b-xl"
                    >
                      <span className="bg-muted flex size-9 shrink-0 items-center justify-center rounded-lg">
                        <Icon className="size-4" aria-hidden />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium">
                          {title}
                        </span>
                        <span className="text-muted-foreground block text-sm">
                          {blurb}
                        </span>
                      </span>
                      {status ? (
                        <Badge variant="outline" className="hidden font-normal sm:inline-flex">
                          {status}
                        </Badge>
                      ) : null}
                      <ChevronRight
                        className={cn("text-muted-foreground size-4 shrink-0")}
                        aria-hidden
                      />
                    </Link>
                  ))}
              </CardContent>
            </Card>
          </section>
        ))
      )}

      <p className="text-muted-foreground max-w-prose text-sm">
        Secrets live in <span className="font-mono">backend/.env</span> and are
        never shown or edited here: the gateway key, the Telegram token, and the
        token this browser signs in with. Model choices live in{" "}
        <span className="font-mono">backend/models.yaml</span>.
      </p>
    </div>
  );
}
