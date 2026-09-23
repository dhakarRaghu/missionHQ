import type { ValidationResult as ValidationResultData } from "@/lib/api/agents-admin";

function lineClass(line: string) {
  if (line.startsWith("+++") || line.startsWith("---")) return "font-medium";
  if (line.startsWith("@@")) return "text-muted-foreground";
  if (line.startsWith("+")) return "text-status-success";
  if (line.startsWith("-")) return "text-status-danger";
  return "";
}

/** Read-only unified diff, one coloured line per row. */
export function DiffView({ diff }: { diff: string }) {
  if (!diff) {
    return (
      <p className="text-muted-foreground text-xs">No change to job.md.</p>
    );
  }
  return (
    <pre className="bg-muted overflow-x-auto rounded-lg p-3 font-mono text-xs leading-relaxed">
      {diff.split("\n").map((line, i) => (
        <div key={i} className={lineClass(line)}>
          {line || " "}
        </div>
      ))}
    </pre>
  );
}

/** Errors, warnings and the diff from validate or save. */
export function ValidationResult({ result }: { result: ValidationResultData }) {
  return (
    <div className="flex flex-col gap-3 text-sm" role="status">
      <p className="font-medium">
        {result.ok ? "Validation passed" : "Validation failed"}
      </p>
      {result.errors.length ? (
        <ul className="text-status-danger list-disc pl-5">
          {result.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      ) : null}
      {result.warnings.length ? (
        <ul className="text-status-approval list-disc pl-5">
          {result.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
      <DiffView diff={result.diff} />
    </div>
  );
}
