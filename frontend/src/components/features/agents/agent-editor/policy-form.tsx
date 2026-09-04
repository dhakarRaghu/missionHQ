"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { agentAdminApi, agentAdminKeys } from "@/lib/api/agents-admin";

/** policy.md editor. Saved through PUT /api/agents/{name}/policy; no restart. */
export function PolicyForm({
  name,
  initial,
}: {
  name: string;
  initial: string;
}) {
  const queryClient = useQueryClient();
  const [policy, setPolicy] = useState(initial);

  const save = useMutation({
    mutationFn: () => agentAdminApi.updatePolicy(name, policy),
    onSuccess: (result) => {
      toast(result.message || "Policy saved");
      queryClient.invalidateQueries({ queryKey: agentAdminKeys.config(name) });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const dirty = policy !== initial;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <Label htmlFor="agent-policy">policy.md</Label>
        <p className="text-muted-foreground text-xs">
          Owner-approved standing rules. Applies on the next run, no restart:
          the agent re-reads policy.md every time it starts.
        </p>
        <Textarea
          id="agent-policy"
          value={policy}
          className="min-h-64 font-mono text-xs"
          onChange={(e) => setPolicy(e.target.value)}
        />
      </div>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? "Saving…" : "Save policy"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={!dirty || save.isPending}
          onClick={() => setPolicy(initial)}
        >
          Reset
        </Button>
      </div>
    </div>
  );
}
