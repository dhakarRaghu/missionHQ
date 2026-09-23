import { Suspense } from "react";

import { VaultView } from "@/components/features/vault/vault-view";
import { Skeleton } from "@/components/ui/skeleton";

export default function VaultPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {/* useSearchParams (the ?path= deep link) needs a Suspense boundary. */}
      <Suspense
        fallback={
          <div role="status" aria-busy="true" aria-label="Loading vault">
            <Skeleton className="h-48 w-full" />
          </div>
        }
      >
        <VaultView />
      </Suspense>
    </div>
  );
}
