"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { AgentEditor } from "@/components/features/agents/agent-editor/agent-editor";
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
      <AgentEditor name={name} />
    </>
  );
}
