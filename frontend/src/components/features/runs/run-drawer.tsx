"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { RunDetail } from "@/components/features/runs/run-detail";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

/**
 * A run in a right-hand panel, so reading one does not lose the list you were
 * scanning. The standalone page at /runs/<id> still exists for a shared link,
 * and the panel offers it as "Open full page".
 */
export function RunDrawer({
  runId,
  onClose,
}: {
  runId: string | null;
  onClose: () => void;
}) {
  return (
    <Sheet open={Boolean(runId)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 p-0 sm:max-w-3xl"
      >
        <SheetHeader className="shrink-0 border-b pr-12">
          <SheetTitle>Run</SheetTitle>
          <SheetDescription className="flex items-center gap-2">
            <span className="font-mono text-xs break-all">{runId}</span>
          </SheetDescription>
          {runId ? (
            <Button
              variant="outline"
              size="sm"
              asChild
              className="mt-2 self-start"
            >
              <Link href={`/runs/${encodeURIComponent(runId)}`}>
                <ExternalLink aria-hidden />
                Open full page
              </Link>
            </Button>
          ) : null}
        </SheetHeader>
        <div className="pane-scroll p-4">
          {runId ? <RunDetail key={runId} id={runId} variant="drawer" /> : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
