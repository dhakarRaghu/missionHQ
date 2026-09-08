import { TicketList } from "@/components/features/inbox/ticket-list";
import { ValueWeekCard } from "@/components/features/inbox/value-week-card";

export default function InboxPage() {
  return (
    <>
      <ValueWeekCard />
      <TicketList />
    </>
  );
}
