import { ChatView } from "@/components/features/chat/chat-view";
import { PageHeader } from "@/components/page-header";

export default function ChatPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <PageHeader
        title="Chat"
        description="Talk to an agent directly. Each turn is a durable run; approvals go through the Inbox."
      />
      <ChatView />
    </div>
  );
}
