"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, qk } from "@/lib/api/client";

/** Creates a task through POST /api/tasks and refreshes the board. */
export function NewTaskForm() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [agent, setAgent] = useState("");
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");

  const agents = useQuery({
    queryKey: qk.agents,
    queryFn: api.agents,
    enabled: open,
  });

  const create = useMutation({
    mutationFn: api.createTask,
    onSuccess: (task) => {
      toast(`Task created: ${task?.title ?? title}`);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setOpen(false);
      setTitle("");
      setBrief("");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const canSubmit = agent !== "" && title.trim() !== "" && !create.isPending;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">New task</Button>
      </DialogTrigger>
      <DialogContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!canSubmit) return;
            create.mutate({ agent, title: title.trim(), brief: brief.trim() });
          }}
        >
          <DialogHeader>
            <DialogTitle>New task</DialogTitle>
            <DialogDescription>
              The task lands in the backlog and the chosen agent picks it up.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-2">
            <Label htmlFor="new-task-agent">Agent</Label>
            <Select value={agent} onValueChange={setAgent}>
              <SelectTrigger id="new-task-agent" className="w-full">
                <SelectValue
                  placeholder={
                    agents.isLoading
                      ? "Loading agents…"
                      : agents.isError
                        ? "Could not load agents"
                        : "Choose an agent"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {(agents.data ?? []).map((info) => (
                  <SelectItem key={info.name} value={info.name}>
                    {info.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="new-task-title">Title</Label>
            <Input
              id="new-task-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
              maxLength={200}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="new-task-brief">Brief</Label>
            <Textarea
              id="new-task-brief"
              value={brief}
              onChange={(event) => setBrief(event.target.value)}
              placeholder="What should the agent do?"
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {create.isPending ? "Creating…" : "Create task"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
