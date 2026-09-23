"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { LiveFeed } from "@/components/features/feed/live-feed";
import { RunsTable } from "@/components/features/runs/runs-table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Tab = "runs" | "feed";

function asTab(value: string | null): Tab {
  return value === "feed" ? "feed" : "runs";
}

/**
 * Runs and the live feed, one page.
 *
 * They are the same story at two resolutions: a run is a row with its cost
 * and outcome; the feed is every event inside those runs as they happen.
 * Reading one to understand the other meant two views and a lot of back
 * button. The tab lives in the URL (?tab=feed) so Home's "Live feed" link
 * and a refresh both land on the right one, and the run drawer's own ?run=
 * parameter is preserved across a tab switch.
 */
export function RunsTabs() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = asTab(params.get("tab"));

  const setTab = useCallback(
    (value: string) => {
      const next = new URLSearchParams(params.toString());
      if (asTab(value) === "runs") next.delete("tab");
      else next.set("tab", "feed");
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : pathname);
    },
    [router, pathname, params],
  );

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList aria-label="Runs or live feed">
        <TabsTrigger value="runs">Runs</TabsTrigger>
        <TabsTrigger value="feed">Live feed</TabsTrigger>
      </TabsList>
      <TabsContent value="runs" className="mt-4">
        <RunsTable />
      </TabsContent>
      <TabsContent value="feed" className="mt-4">
        <LiveFeed />
      </TabsContent>
    </Tabs>
  );
}
