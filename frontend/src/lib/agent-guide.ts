/**
 * What each agent is for, in the owner's words.
 *
 * The manifest already carries a one-line description, a tool list and a
 * schedule. None of that answers "what do I ask it, and what comes back", so
 * the console carries a short guide next to each agent. Text only: the manifest
 * stays the single source of truth for behaviour.
 */
export interface AgentGuide {
  /** One sentence: the job. */
  does: string;
  /** How the owner gets value from it, in order. */
  use: string[];
  /** Where its output lands, in the owner's terms. */
  output: string;
}

const GUIDE: Record<string, AgentGuide> = {
  sage: {
    does: "Your coordinator and memory. It decides who does what, writes the daily note and the Sunday review, proposes a Monday job shortlist and Wednesday content ideas, and keeps the memory every agent reads short and true.",
    use: [
      "Ask it anything. It answers what is its own and hands the rest over.",
      "Ask it what happened: “What did the agents do in the last 24 hours?”",
      "Ask it which roles to act on: “What is on this week's shortlist?”",
      "Leave it alone. It writes a note at 22:30 daily, proposes memory changes for you at 23:30, and reviews the week on Sunday at 20:00.",
    ],
    output: "daily/<date>.md, the weekly review, projects/jobs/shortlist-<week>.md, projects/content/ideas.md and memory/ blocks.",
  },
  hunter: {
    does: "Reads the web and writes what it found. It verifies job leads with a person to reach, and writes the study notes lessons are built from. It can write nowhere except quarantine.",
    use: [
      "Give it one precise question, not a topic: “Who could refer me at this company, and what do we share?”",
      "Read the quarantine note it writes, then tell sage to act on it or drop it.",
      "The nightly sweep and the learning run create its work automatically.",
    ],
    output: "Roles on the Jobs board, and quarantine/<date>-<slug>.md with its sources.",
  },
  tutor: {
    does: "Your teacher. It plans the concepts worth knowing, writes a lesson one section at a time, and checks every sentence against the study note before you read it.",
    use: [
      "Read the lesson in Learn or on your phone, and tap Got it or Lost me on each concept.",
      "A new phase starts once you have read the last one.",
      "Ask sage for a post from a lesson; tutor drafts it for your site and never publishes.",
    ],
    output: "learning/lessons/<date>-<slug>.html, on your phone at /read.",
  },
  operator: {
    does: "Reads pages only your signed-in browser can open (LinkedIn, X, your analytics), read-only, under one written contract.",
    use: [
      "Ask sage for it with the exact pages you want read.",
      "Approve the run once; it never clicks anything that sends, posts or applies.",
    ],
    output: "A quarantine note with the URL of every source, or leads handed to hunter.",
  },
};

export function guideFor(name: string): AgentGuide | null {
  return GUIDE[name] ?? null;
}
