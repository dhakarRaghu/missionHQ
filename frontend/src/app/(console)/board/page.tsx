import { TaskBoard } from "@/components/features/board/task-board";
import { PageHeader } from "@/components/page-header";

export default function BoardPage() {
  return (
    <>
      <PageHeader
        title="Board"
        description="Every task, grouped by state. Open one to read its full event log."
      />
      <TaskBoard />
    </>
  );
}
