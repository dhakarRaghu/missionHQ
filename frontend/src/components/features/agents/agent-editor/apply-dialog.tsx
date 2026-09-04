"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { agentAdminApi } from "@/lib/api/agents-admin";
import { qk } from "@/lib/api/client";

/** How long after the restart reply we refetch (backend exits after 2 s,
 * launchd brings it back; a few seconds is usually enough). */
const REFETCH_AFTER_MS = 8000;

/**
 * "Apply & restart": POST /api/agents/{name}/apply behind a confirm dialog.
 * Enabled only after a save that changed job.md.
 */
export function ApplyDialog({
  name,
  enabled,
  onApplied,
}: {
  name: string;
  enabled: boolean;
  onApplied: () => void;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const apply = useMutation({
    mutationFn: () => agentAdminApi.apply(name),
    onSuccess: (result) => {
      toast(result.message || "Restart scheduled");
      setOpen(false);
      onApplied();
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
        <Button type="button" variant="destructive" disabled={!enabled}>
          Apply &amp; restart
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Restart the backend?</DialogTitle>
          <DialogDescription>
            Restarts the backend; running jobs recover on their own. The process
            exits in 2 seconds and launchd starts it again with the saved job.md
            loaded. The console is unavailable for a few seconds.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter showCloseButton>
          <Button
            type="button"
            variant="destructive"
            disabled={apply.isPending}
            onClick={() => apply.mutate()}
          >
            {apply.isPending ? "Scheduling…" : "Restart now"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
