"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { EmptyState } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qk } from "@/lib/api/client";

export function AgentList() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: qk.agents, queryFn: api.agents });

  const togglePause = useMutation({
    mutationFn: ({ name, paused }: { name: string; paused: boolean }) =>
      api.setAgentPaused(name, paused),
    onSuccess: (result) => {
      toast(`${result.agent} ${result.paused ? "paused" : "resumed"}`);
      queryClient.invalidateQueries({ queryKey: qk.agents });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (isLoading) return <Skeleton className="h-48 w-full" />;
  if (!data?.length) return <EmptyState>No agents loaded.</EmptyState>;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {data.map((agent) => (
        <Card key={agent.name}>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between text-base">
              <span>{agent.name}</span>
              {agent.paused ? (
                <Badge variant="secondary" className="bg-amber-500/15 text-amber-700 dark:text-amber-300">
                  paused
                </Badge>
              ) : null}
            </CardTitle>
            <p className="text-muted-foreground text-sm">{agent.description}</p>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <div className="flex flex-wrap gap-1">
              {agent.tools.map((tool) => (
                <Badge key={tool} variant="outline" className="font-normal">
                  {tool}
                </Badge>
              ))}
            </div>

            <dl className="text-muted-foreground grid grid-cols-2 gap-1 text-xs">
              <dt>Model role</dt>
              <dd className="text-foreground text-right">{agent.model}</dd>
              <dt>Spend today</dt>
              <dd className="text-foreground text-right tabular-nums">
                ${agent.spend_today_usd.toFixed(4)} / ${agent.daily_cap_usd.toFixed(2)}
              </dd>
              <dt>Schedules</dt>
              <dd className="text-foreground text-right">
                {agent.cron.length ? agent.cron.map((c) => c.schedule).join(", ") : "none"}
              </dd>
            </dl>

            <Button
              size="sm"
              variant="outline"
              className="self-start"
              disabled={togglePause.isPending}
              onClick={() =>
                togglePause.mutate({ name: agent.name, paused: !agent.paused })
              }
            >
              {agent.paused ? "Resume" : "Pause"}
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
