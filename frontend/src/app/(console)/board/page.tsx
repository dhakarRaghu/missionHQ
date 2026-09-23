import { Suspense } from "react";

import { NewTaskForm } from "@/components/features/board/new-task-form";
import { TaskBoard } from "@/components/features/board/task-board";
import { Skeleton } from "@/components/ui/skeleton";

export default function BoardPage() {
  return (
    <>
      {/* The shell's top bar already names the page, so only the action is
          left here. It sits on its own row rather than in a header block:
          on a 13-inch screen the title and its sentence cost most of a
          column of tasks and repeated what the sidebar said. */}
      <div className="mb-3 flex justify-end">
        <NewTaskForm />
      </div>
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
