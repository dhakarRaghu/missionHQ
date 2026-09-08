import { Suspense } from "react";

import { CostSummary, RunsTable } from "@/components/features/runs/runs-table";
import { Skeleton } from "@/components/ui/skeleton";

export default function RunsPage() {
  return (
    <>
      <CostSummary />
      {/* useSearchParams (the ?run= panel) needs a Suspense boundary. */}
      <Suspense
        fallback={
          <div role="status" aria-busy="true" aria-label="Loading runs">
            <Skeleton className="h-64 w-full" />
          </div>
        }
      >
        <RunsTable />
      </Suspense>
    </>
  );
}
