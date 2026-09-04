"use client";

import { useParams } from "next/navigation";

import { RunDetail } from "@/components/features/runs/run-detail";
import { PageHeader } from "@/components/page-header";

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);

  return (
    <>
      <PageHeader
        title="Run"
        description="Every step of one agent execution: tool calls, ledger verdicts, approvals and the final output."
      />
      <RunDetail id={id} />
    </>
  );
}
