"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { AgentEditor } from "@/components/features/agents/agent-editor/agent-editor";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";

export default function AgentConfigPage() {
  const params = useParams<{ name: string }>();
  const name = decodeURIComponent(params.name);

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-3 -ml-2 self-start">
        <Link href={`/agents/${encodeURIComponent(name)}`}>
          <ArrowLeft aria-hidden />
          Back to {name}
        </Link>
      </Button>
      <PageHeader
        title={`Configure ${name}`}
        description="Edit agents/<name>/job.md and policy.md. A saved job.md loads after a restart; policy.md applies on the next run."
      />
      <AgentEditor name={name} />
    </>
  );
}
