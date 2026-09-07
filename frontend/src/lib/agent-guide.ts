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
    does: "Your second brain. It keeps the daily note, the weekly review, and the memory blocks the other agents read before every run.",
    use: [
      "Ask it anything. It answers what is its own and hands the rest over.",
      "Ask it what happened: “What did the agents do in the last 24 hours?”",
      "Ask it what to deal with: “What is the most important open loop in my vault?”",
      "Leave it alone. It writes a note at 21:00 daily and a review on Sunday at 20:00.",
    ],
    output: "daily/<date>.md, the weekly review, and memory/ blocks.",
  },
  hunter: {
    does: "Reads the web and writes what it found. It is the only agent with web access, and it can write nowhere except quarantine.",
    use: [
      "Give it one precise question, not a topic: “What changed in X this month?”",
      "Read the quarantine note it writes, then tell sage to promote or drop it.",
      "Scout creates work for it automatically when it needs fresh research.",
    ],
    output: "quarantine/<date>-<slug>.md, with its sources and a confidence level.",
  },
  scout: {
    does: "Content for YouTube and Twitter. It turns hunter's research into ideas, outlines and drafts, and never posts anything without your approval.",
    use: [
      "Ask for ideas: “Five video ideas from the newest quarantine notes, ranked.”",
      "Ask for a draft, then edit it. It writes in short, plain sentences.",
      "Anything meant to be published becomes an approval in your Inbox first.",
    ],
    output: "projects/content/ideas.md and projects/content/drafts/.",
  },
  librarian: {
    does: "Nightly housekeeping for memory. It merges the day's notes into the memory blocks without letting them grow past their caps.",
    use: [
      "Nothing. It runs at 02:00 and its work shows up as one git commit you can revert.",
      "Ask it what is close to full: “What is in my memory blocks right now?”",
    ],
    output: "memory/user.md and memory/active_projects.md.",
  },
};

export function guideFor(name: string): AgentGuide | null {
  return GUIDE[name] ?? null;
}
