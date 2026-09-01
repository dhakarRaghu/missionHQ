export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? (
          <p className="text-muted-foreground mt-1 text-sm">{description}</p>
        ) : null}
      </div>
      {action}
    </header>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-muted-foreground rounded-lg border border-dashed p-10 text-center text-sm">
      {children}
    </div>
  );
}
