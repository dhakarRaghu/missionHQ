import { TicketList } from "@/components/features/inbox/ticket-list";
import { ValueWeekCard } from "@/components/features/inbox/value-week-card";
import { PageHeader } from "@/components/page-header";

export default function InboxPage() {
  return (
    <>
      <PageHeader
        title="Inbox"
        description="Decisions waiting on you. Approving here and approving from Telegram resolve the same ticket."
      />
      <ValueWeekCard />
      <TicketList />
    </>
  );
}
