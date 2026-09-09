import { Suspense } from "react";

import { RunsTabs } from "@/components/features/runs/runs-tabs";
import { CostSummary } from "@/components/features/runs/runs-table";
import { Skeleton } from "@/components/ui/skeleton";

export default function RunsPage() {
  return (
    <>
      <CostSummary />
      {/* useSearchParams (the ?tab= and ?run= state) needs a Suspense boundary. */}
      <Suspense
        fallback={
          <div role="status" aria-busy="true" aria-label="Loading runs">
            <Skeleton className="h-64 w-full" />
          </div>
        }
      >
        <RunsTabs />
      </Suspense>
    </>
  );
}
