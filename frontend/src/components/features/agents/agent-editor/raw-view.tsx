/** Read-only job.md and policy.md exactly as they are on disk. */
export function RawView({
  jobMd,
  policyMd,
}: {
  jobMd: string;
  policyMd: string;
}) {
  return (
    <div className="flex flex-col gap-6">
      <RawFile name="job.md" content={jobMd} />
      <RawFile name="policy.md" content={policyMd} />
    </div>
  );
}

function RawFile({ name, content }: { name: string; content: string }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="font-mono text-sm font-medium">{name}</h3>
      {content ? (
        <pre className="bg-muted overflow-x-auto rounded-lg p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
          {content}
        </pre>
      ) : (
        <p className="text-muted-foreground text-xs">
          File is missing or empty.
        </p>
      )}
    </section>
  );
}
