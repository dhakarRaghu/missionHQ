"use client";

import { useParams } from "next/navigation";

import { RunDetail } from "@/components/features/runs/run-detail";

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);

  return (
    <>
      <RunDetail id={id} />
    </>
  );
}
