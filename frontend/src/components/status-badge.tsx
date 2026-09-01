import { Badge } from "@/components/ui/badge";
import type { TaskStatus } from "@/lib/api/types";

const VARIANT: Record<TaskStatus, string> = {
  backlog: "bg-muted text-muted-foreground",
  running: "bg-blue-500/15 text-blue-700 dark:text-blue-300",
  blocked: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  needs_approval: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
  done: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  failed: "bg-red-500/15 text-red-700 dark:text-red-300",
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
    <Badge variant="secondary" className={VARIANT[status]}>
      {LABEL[status]}
    </Badge>
  );
}

export function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) {
    return <Badge variant="secondary">running</Badge>;
  }
  const tone =
    outcome === "done"
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
      : outcome === "blocked"
        ? "bg-amber-500/15 text-amber-700 dark:text-amber-300"
        : "bg-red-500/15 text-red-700 dark:text-red-300";
  return (
    <Badge variant="secondary" className={tone}>
      {outcome}
    </Badge>
  );
}
