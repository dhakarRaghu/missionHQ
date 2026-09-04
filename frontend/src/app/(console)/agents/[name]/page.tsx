"use client";

import { useParams } from "next/navigation";

import { AgentProfile } from "@/components/features/agents/agent-profile";

export default function AgentPage() {
  const params = useParams<{ name: string }>();
  return <AgentProfile name={decodeURIComponent(params.name)} />;
}
