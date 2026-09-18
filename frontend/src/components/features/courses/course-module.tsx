"use client";

import { ArrowLeft } from "lucide-react";

import {
  briefIsInReadme,
  moduleNextStep,
  researchPath,
  statusTone,
} from "@/components/features/courses/course-format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { CurriculumModule } from "@/lib/api/learning";

/**
 * Centre pane for a module that has no course yet.
 *
 * Twelve of the twenty-two modules have no research and none of the ready
 * ones have been generated, so most of the plan cannot be read. Opening one
 * used to do nothing. It now says what the module is, where its research sits
 * in the repo, and the one step that turns it into a course, which is what he
 * needs when he picks the next thing to study.
 */
export function CourseModulePanel({
  module,
  onBack,
}: {
  module: CurriculumModule;
  onBack: () => void;
}) {
  const path = researchPath(module);
  const facts: { label: string; value: string }[] = [
    { label: "Layer", value: module.layer },
    {
      label: "Core path",
      value: module.core_order
        ? `number ${module.core_order} of the eight to do first`
        : "not on the core path of eight",
    },
    { label: "Planned phases", value: module.planned_phases || "to be sized" },
  ];

  return (
    <section
      aria-label={`Curriculum module ${module.number}`}
      className="reader-pane flex min-h-0 flex-col gap-3"
    >
      <header className="shrink-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium tabular-nums text-muted-foreground">
            Curriculum module {module.number}
          </span>
          <Badge variant="secondary" tone={statusTone(module.status)}>
            {module.status}
          </Badge>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={onBack}
          >
            <ArrowLeft aria-hidden className="size-3.5" />
            Back to the course
          </Button>
        </div>
        <h2 className="text-lg leading-tight font-semibold tracking-tight">
          {module.title}
        </h2>
        <p className="text-xs text-muted-foreground">
          This module has no course yet, so there is nothing to read here.
        </p>
      </header>

      <div className="pane-scroll space-y-4 border-t pt-3">
        <dl className="grid gap-3 sm:grid-cols-3">
          {facts.map((fact) => (
            <div key={fact.label}>
              <dt className="text-xs text-muted-foreground">{fact.label}</dt>
              <dd className="text-sm">{fact.value}</dd>
            </div>
          ))}
        </dl>

        <div>
          <p className="text-xs text-muted-foreground">Research file</p>
          <p className="mt-0.5 font-mono text-xs break-all">{path}</p>
          {briefIsInReadme(module) ? (
            <p className="mt-1 text-xs text-muted-foreground">
              There is no dossier for this module. The brief is the block for
              module {module.number} inside that README.
            </p>
          ) : null}
        </div>

        <div className="rounded-md border bg-muted/40 p-3">
          <p className="text-xs font-medium">What to do next</p>
          <p className="mt-1 text-sm">{moduleNextStep(module)}</p>
        </div>
      </div>
    </section>
  );
}
