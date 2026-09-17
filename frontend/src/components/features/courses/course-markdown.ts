/**
 * The published phase, cut into the pieces the course reader shows.
 *
 * The /study skill writes one long markdown document per phase. react-markdown
 * renders it, but a document rendered in one go reads as an article: no
 * section to jump to, no place to put Mission HQ's additions, no exercise to
 * tick. So the text is split here first, with the same rule the backend's
 * `module_sections` uses — `## ` headings outside code fences — and each
 * section is split again into the blocks that get their own treatment.
 *
 * Pure functions, no React: the side panel parses the same text for its
 * contents list and the two must agree on every id.
 */

export interface CourseSection {
  /** DOM id, unique within the phase. */
  id: string;
  /** The heading text exactly as written — additions match on it. */
  heading: string;
  /** "3.1" when the heading is numbered. */
  number: string;
  /** The heading without its number, emoji or trailing "(subtitle)". */
  title: string;
  subtitle: string;
  kind: SectionKind;
  body: string;
  /** Ids of the task-list exercises in this section, in order. */
  exercises: string[];
}

export type SectionKind =
  | "concept"
  | "lab"
  | "check"
  | "checkpoint"
  | "references"
  | "cheatsheet"
  | "other";

export interface CourseDocumentParts {
  intro: string;
  sections: CourseSection[];
}

export type CourseBlock =
  | { type: "markdown"; text: string }
  | { type: "lead"; text: string }
  | { type: "keypoints"; points: { label: string; text: string }[] }
  | { type: "details"; summary: string; body: string };

const FENCE = /^\s*(```|~~~)/;
const RULE = /^\s*-{3,}\s*$/;

/**
 * Split a phase on its `## ` headings.
 *
 * The first `# ` line is dropped: the reader's header already shows the
 * title, and printing it twice pushed the outline below the fold.
 */
export function splitCourse(md: string): CourseDocumentParts {
  const lines = normaliseRules(md).split("\n");
  const intro: string[] = [];
  const raw: { heading: string; lines: string[] }[] = [];
  let fenced = false;
  let droppedTitle = false;

  for (const line of lines) {
    if (FENCE.test(line)) fenced = !fenced;
    if (!fenced && line.startsWith("## ")) {
      raw.push({ heading: line.slice(3).trim(), lines: [] });
      continue;
    }
    if (!raw.length) {
      if (!fenced && !droppedTitle && /^#\s+/.test(line)) {
        droppedTitle = true;
        continue;
      }
      intro.push(line);
    } else {
      raw[raw.length - 1].lines.push(line);
    }
  }

  const used = new Set<string>();
  const sections = raw.map(({ heading, lines: body }) => {
    const id = uniqueId(`sec-${slugify(heading) || "section"}`, used);
    const text = trimRules(body.join("\n"));
    return {
      id,
      heading,
      ...parseHeading(heading),
      kind: sectionKind(heading),
      body: text,
      exercises: exerciseIds(id, text),
    };
  });
  return { intro: trimRules(intro.join("\n")), sections };
}

/**
 * A `---` directly under a paragraph is a setext heading in markdown, not a
 * rule: "**Try this now:** …" followed by `---` rendered as a giant h2. The
 * skill writes rules that way, so a blank line goes in front of every one.
 */
function normaliseRules(md: string): string {
  const out: string[] = [];
  let fenced = false;
  for (const line of md.replace(/\r\n?/g, "\n").split("\n")) {
    if (FENCE.test(line)) fenced = !fenced;
    if (!fenced && RULE.test(line) && out.length && out[out.length - 1].trim()) {
      out.push("");
    }
    out.push(line);
  }
  return out.join("\n");
}

/** Rules between parts separate sections; the reader draws its own. */
function trimRules(text: string): string {
  const lines = text.split("\n");
  while (lines.length && (!lines[0].trim() || RULE.test(lines[0]))) lines.shift();
  while (
    lines.length &&
    (!lines[lines.length - 1].trim() || RULE.test(lines[lines.length - 1]))
  ) {
    lines.pop();
  }
  return lines.join("\n");
}

const EMOJI = /^(?:\p{Extended_Pictographic}|️|‍|\s)+/u;

function parseHeading(heading: string) {
  let rest = heading.replace(EMOJI, "");
  const numbered = /^(\d+\.\d+[a-z]?)\s*[—–-]\s*/u.exec(rest);
  const number = numbered ? numbered[1] : "";
  if (numbered) rest = rest.slice(numbered[0].length);
  // "Implicit prefix caching (automatic, invisible, and easy to lose)": the
  // parenthesis is the plain-English subtitle, so it gets its own line.
  const paren = /^(.+?)\s*\(([^()]+)\)\s*$/u.exec(rest);
  return paren
    ? { number, title: paren[1], subtitle: paren[2] }
    : { number, title: rest.trim(), subtitle: "" };
}

function sectionKind(heading: string): SectionKind {
  const h = heading.toLowerCase();
  if (/^\d+\.\d+/.test(heading)) return "concept";
  if (heading.includes("🧪") || /\blabs?\b|hands-on/.test(h)) return "lab";
  if (heading.includes("✅") || h.includes("checkpoint")) return "checkpoint";
  if (heading.includes("🔍") || heading.includes("🏢") || h.includes("check it yourself")) {
    return "check";
  }
  if (h.startsWith("references") || h.startsWith("sources")) return "references";
  if (h.startsWith("cheatsheet")) return "cheatsheet";
  return "other";
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

function uniqueId(base: string, used: Set<string>): string {
  let id = base;
  for (let n = 2; used.has(id); n++) id = `${base}-${n}`;
  used.add(id);
  return id;
}

// --- exercises -------------------------------------------------------------

const TASK = /^\s*[-*+]\s+\[[ xX]\]\s+(.*)$/;

/**
 * The id a ticked exercise is stored under.
 *
 * "E4" when the item starts with one, which survives the author rewording
 * the line; otherwise the item's first letters. The renderer derives the same
 * key from the rendered text, so markdown punctuation and link targets are
 * dropped here before normalising.
 */
export function exerciseKey(sectionId: string, text: string): string {
  const plain = text
    .replace(/\]\([^)]*\)/g, "]")
    .replace(/[*_`[\]]/g, "")
    .trim();
  const label = /^(E\d+[a-z]?)\b/i.exec(plain);
  const key = label
    ? label[1].toUpperCase()
    : plain.toLowerCase().replace(/[^a-z0-9]+/g, "").slice(0, 48);
  return `${sectionId}:${key}`;
}

function exerciseIds(sectionId: string, body: string): string[] {
  const out: string[] = [];
  let fenced = false;
  for (const line of body.split("\n")) {
    if (FENCE.test(line)) fenced = !fenced;
    const task = fenced ? null : TASK.exec(line);
    if (task) out.push(exerciseKey(sectionId, task[1]));
  }
  return out;
}

// --- blocks ----------------------------------------------------------------

const KEY_LABELS = [
  "The sentence to remember",
  "The trap",
  "Try this now",
  "Verify",
  "Verify your understanding",
  "In your codebase",
];
const KEY_POINT = new RegExp(`^\\*\\*(${KEY_LABELS.join("|")}):\\*\\*\\s*`);

/**
 * One section as blocks: prose, the "Why this matters" lead, the closing key
 * points, and `<details>` answer sketches.
 *
 * react-markdown does not render raw HTML, and must not — the text comes from
 * a network service — so `<details>` is lifted out here and drawn as a real
 * element with its inner markdown rendered normally.
 */
export function splitBlocks(body: string): CourseBlock[] {
  const blocks: CourseBlock[] = [];
  for (const chunk of splitDetails(body)) {
    if (chunk.type === "details") blocks.push(chunk);
    else blocks.push(...proseBlocks(chunk.text));
  }
  return blocks;
}

function splitDetails(
  body: string,
): ({ type: "markdown"; text: string } | { type: "details"; summary: string; body: string })[] {
  const out: (
    | { type: "markdown"; text: string }
    | { type: "details"; summary: string; body: string }
  )[] = [];
  let prose: string[] = [];
  let inner: string[] = [];
  let depth = 0;
  let fenced = false;

  const flushProse = () => {
    if (prose.join("").trim()) out.push({ type: "markdown", text: prose.join("\n") });
    prose = [];
  };

  for (const line of body.split("\n")) {
    if (FENCE.test(line)) fenced = !fenced;
    const opens = !fenced && /^\s*<details\b[^>]*>/i.test(line);
    const closes = !fenced && /<\/details>\s*$/i.test(line);

    if (depth === 0 && opens) {
      flushProse();
      depth = 1;
      inner = [line.replace(/^\s*<details\b[^>]*>/i, "")];
      if (closes) {
        depth = 0;
        out.push(detailsBlock(inner.join("\n")));
      }
      continue;
    }
    if (depth > 0) {
      if (opens) depth++;
      if (closes) depth--;
      if (depth === 0) {
        inner.push(line.replace(/<\/details>\s*$/i, ""));
        out.push(detailsBlock(inner.join("\n")));
      } else {
        inner.push(line);
      }
      continue;
    }
    prose.push(line);
  }
  // An unclosed block is shown as a block anyway rather than lost.
  if (depth > 0) out.push(detailsBlock(inner.join("\n")));
  flushProse();
  return out;
}

function detailsBlock(raw: string) {
  const summary = /<summary\b[^>]*>([\s\S]*?)<\/summary>/i.exec(raw);
  const body = summary ? raw.replace(summary[0], "") : raw;
  return {
    type: "details" as const,
    summary: summary ? stripTags(summary[1]).trim() || "Show" : "Show",
    body: body.trim(),
  };
}

function stripTags(text: string): string {
  return text.replace(/<[^>]*>/g, "");
}

/** Paragraph-level pass: a lead up top, key points grouped at the end. */
function proseBlocks(text: string): CourseBlock[] {
  const out: CourseBlock[] = [];
  let md: string[] = [];
  let points: { label: string; text: string }[] = [];
  let first = true;

  const flushMd = () => {
    if (md.join("").trim()) out.push({ type: "markdown", text: md.join("\n\n") });
    md = [];
  };
  const flushPoints = () => {
    if (points.length) out.push({ type: "keypoints", points });
    points = [];
  };

  for (const para of paragraphs(text)) {
    const key = KEY_POINT.exec(para);
    if (key) {
      flushMd();
      points.push({ label: key[1], text: para.slice(key[0].length) });
    } else if (first && /^Why this matters:/i.test(para)) {
      out.push({ type: "lead", text: para.replace(/^Why this matters:\s*/i, "") });
    } else {
      flushPoints();
      md.push(para);
    }
    first = false;
  }
  flushMd();
  flushPoints();
  return out;
}

/**
 * Blank-line separated paragraphs. A blank line inside a code fence is not a
 * break; a loose list does split, but consecutive prose paragraphs are joined
 * back into one markdown block, so the list renders whole.
 */
function paragraphs(text: string): string[] {
  const out: string[] = [];
  let current: string[] = [];
  let fenced = false;
  for (const line of text.split("\n")) {
    if (FENCE.test(line)) fenced = !fenced;
    if (!fenced && !line.trim()) {
      if (current.length) out.push(current.join("\n"));
      current = [];
      continue;
    }
    current.push(line);
  }
  if (current.length) out.push(current.join("\n"));
  return out;
}

// --- sources ---------------------------------------------------------------

export interface SourceLink {
  url: string;
  title: string;
  group: string;
}

/** Every link in the references section, titled by its bold lead-in. */
export function extractSources(body: string): SourceLink[] {
  const out: SourceLink[] = [];
  const seen = new Set<string>();
  let group = "";
  let fenced = false;
  for (const line of body.split("\n")) {
    if (FENCE.test(line)) fenced = !fenced;
    if (fenced) continue;
    const heading = /^#{3,6}\s+(.+)$/.exec(line);
    if (heading) {
      group = heading[1].trim();
      continue;
    }
    const links = [...line.matchAll(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g)];
    const found = links.length
      ? links.map((m) => ({ url: m[2], title: m[1] }))
      : [...line.matchAll(/https?:\/\/[^\s)>\]]+/g)].map((m) => ({
          url: m[0].replace(/[.,;:]+$/, ""),
          title: /\*\*(.+?)\*\*/.exec(line)?.[1] ?? "",
        }));
    for (const link of found) {
      if (seen.has(link.url)) continue;
      seen.add(link.url);
      out.push({ url: link.url, title: link.title || hostOf(link.url), group });
    }
  }
  return out;
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
