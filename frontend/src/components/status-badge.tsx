import { Badge } from "@/components/ui/badge";
import type { RunOutcome, TaskStatus } from "@/lib/api/types";

type Tone = NonNullable<React.ComponentProps<typeof Badge>["tone"]>;

const TONE: Record<TaskStatus, Tone> = {
  backlog: "muted",
  running: "running",
  blocked: "blocked",
  needs_approval: "approval",
  done: "success",
  failed: "danger",
};

const LABEL: Record<TaskStatus, string> = {
  backlog: "backlog",
  running: "running",
  blocked: "blocked",
  needs_approval: "needs approval",
  done: "done",
  failed: "failed",
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <Badge variant="secondary" tone={TONE[status]}>
      {LABEL[status]}
    </Badge>
  );
}

const OUTCOME_TONE: Record<RunOutcome, Tone> = {
  done: "success",
  blocked: "blocked",
  failed: "danger",
};

export function OutcomeBadge({ outcome }: { outcome: RunOutcome | null }) {
  if (!outcome) {
    return (
      <Badge variant="secondary" tone="running">
        running
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" tone={OUTCOME_TONE[outcome]}>
      {outcome}
    </Badge>
  );
}
