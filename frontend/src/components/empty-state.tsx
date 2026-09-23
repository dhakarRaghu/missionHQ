/**
 * Placeholder for a list or pane with nothing in it yet.
 *
 * An empty console is the first thing a new owner sees, so an empty state
 * teaches rather than apologises: what this place is for, one sentence on what
 * will appear here, and where to go next when there is somewhere to go.
 */
export function EmptyState({
  title,
  children,
  action,
  compact = false,
}: {
  /** Short noun phrase, e.g. "Nothing waiting on you". */
  title?: string;
  /** One sentence explaining what will show up here. */
  children: React.ReactNode;
  action?: React.ReactNode;
  /** Tighter padding for a placeholder inside a narrow side pane. */
  compact?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border border-dashed text-center ${
        compact ? "px-3 py-6" : "px-6 py-10"
      }`}
    >
      {title ? <p className="text-sm font-medium">{title}</p> : null}
      <p
        className={`text-muted-foreground mx-auto max-w-sm text-sm ${
          title ? "mt-1" : ""
        }`}
      >
        {children}
      </p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}
