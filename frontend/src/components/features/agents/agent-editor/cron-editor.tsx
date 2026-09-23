"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { CronEntry } from "@/lib/api/agents-admin";
import { describeCron } from "@/lib/cron";

/** Schedule + prompt rows. Each fires a task for the agent on the cron line. */
export function CronEditor({
  cron,
  onChange,
}: {
  cron: CronEntry[];
  onChange: (cron: CronEntry[]) => void;
}) {
  const update = (i: number, patch: Partial<CronEntry>) =>
    onChange(cron.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const remove = (i: number) => onChange(cron.filter((_, j) => j !== i));

  return (
    <div className="flex flex-col gap-2">
      <Label>Schedules</Label>
      <p className="text-muted-foreground text-xs">
        Five-field cron lines in the backend CRON_TZ. Minimum interval 1 hour.
        The prompt becomes the task title the agent receives.
      </p>
      {cron.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          No schedules. The agent runs only from chat, the board, or subtasks.
        </p>
      ) : null}
      {cron.map((entry, i) => (
        <div key={i} className="flex flex-col gap-2 rounded-lg border p-3">
          <div className="flex items-center gap-2">
            <Input
              value={entry.schedule}
              placeholder="0 8 * * *"
              aria-label={`Schedule ${i + 1}`}
              className="max-w-48 font-mono"
              onChange={(e) => update(i, { schedule: e.target.value })}
            />
            {/* Live reading of the expression, so a wrong field is obvious
                before the config is saved. */}
            <span
              role="status"
              className="text-muted-foreground min-w-0 flex-1 truncate text-xs"
            >
              {entry.schedule.trim()
                ? describeCron(entry.schedule) === entry.schedule.trim()
                  ? "not a shape this console can read back"
                  : describeCron(entry.schedule)
                : ""}
            </span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label={`Remove schedule ${i + 1}`}
              onClick={() => remove(i)}
            >
              Remove
            </Button>
          </div>
          <Textarea
            value={entry.prompt}
            placeholder="What the agent should do when this fires"
            aria-label={`Prompt ${i + 1}`}
            onChange={(e) => update(i, { prompt: e.target.value })}
          />
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="self-start"
        onClick={() => onChange([...cron, { schedule: "", prompt: "" }])}
      >
        Add schedule
      </Button>
    </div>
  );
}
