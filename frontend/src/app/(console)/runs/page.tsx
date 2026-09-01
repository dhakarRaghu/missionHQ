import { CostSummary, RunsTable } from "@/components/features/runs/runs-table";
import { PageHeader } from "@/components/page-header";

export default function RunsPage() {
  return (
    <>
      <PageHeader
        title="Runs"
        description="Every agent execution with its model, outcome, tokens and real cost."
      />
      <CostSummary />
      <RunsTable />
    </>
  );
}
