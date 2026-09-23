// Small formatters shared by the vault components.

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Folders above a vault path: "a/b/c.md" -> ["a", "a/b"]. */
export function ancestorsOf(path: string): string[] {
  const parts = path.split("/");
  const out: string[] = [];
  for (let i = 1; i < parts.length; i++) out.push(parts.slice(0, i).join("/"));
  return out;
}

/**
 * Turn a markdown link into a vault path, or null when it is external, an
 * anchor, or not a markdown file. Relative links resolve against the folder
 * of the note that contains them.
 */
export function resolveVaultLink(href: string, fromPath: string): string | null {
  if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("#")) return null;
  const clean = href.split("#")[0].split("?")[0];
  if (!clean.toLowerCase().endsWith(".md")) return null;
  const base = clean.startsWith("/")
    ? []
    : fromPath.split("/").slice(0, -1);
  const out = [...base];
  for (const seg of clean.split("/")) {
    if (seg === "" || seg === ".") continue;
    if (seg === "..") {
      if (!out.length) return null;
      out.pop();
      continue;
    }
    out.push(seg);
  }
  return out.length ? decodeURIComponent(out.join("/")) : null;
}
