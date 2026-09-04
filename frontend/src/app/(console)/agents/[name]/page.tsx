"use client";

import { useParams } from "next/navigation";

import { AgentEditor } from "@/components/features/agents/agent-editor/agent-editor";
import { PageHeader } from "@/components/page-header";

export default function AgentConfigPage() {
  const params = useParams<{ name: string }>();
  const name = decodeURIComponent(params.name);

  return (
    <>
      <PageHeader
        title={name}
        description="Edit agents/<name>/job.md and policy.md. A saved job.md loads after a restart; policy.md applies on the next run."
      />
      <AgentEditor name={name} />
    </>
  );
}
