import { LiveFeed } from "@/components/features/feed/live-feed";
import { PageHeader } from "@/components/page-header";

export default function FeedPage() {
  return (
    <>
      <PageHeader
        title="Live feed"
        description="Server-sent events as they happen. Reconnects resume from the last sequence number."
      />
      <LiveFeed />
    </>
  );
}
