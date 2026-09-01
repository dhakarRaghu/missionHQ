import { AgentList } from "@/components/features/agents/agent-list";
import { PageHeader } from "@/components/page-header";

export default function AgentsPage() {
  return (
    <>
      <PageHeader
        title="Agents"
        description="One folder per agent. Pause an agent here or from Telegram; both write the same control row."
      />
      <AgentList />
    </>
  );
}
