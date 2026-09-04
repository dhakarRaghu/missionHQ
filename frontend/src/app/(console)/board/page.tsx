import { Suspense } from "react";

import { NewTaskForm } from "@/components/features/board/new-task-form";
import { TaskBoard } from "@/components/features/board/task-board";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

export default function BoardPage() {
  return (
    <>
      <PageHeader
        title="Board"
        description="Every task, grouped by state. Open one to read its full event log."
        action={<NewTaskForm />}
      />
      {/* useSearchParams (the ?task= deep link) needs a Suspense boundary. */}
      <Suspense
        fallback={
          <div role="status" aria-busy="true" aria-label="Loading tasks">
            <Skeleton className="h-64 w-full" />
          </div>
        }
      >
        <TaskBoard />
      </Suspense>
    </>
  );
}
