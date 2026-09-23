/**
 * First questions to offer in an empty chat.
 *
 * A blank box next to an agent whose abilities are not written down anywhere
 * is the reason chat feels useless. These are real questions the agent can
 * answer with the tools it holds, so the first turn always works.
 */
const BY_AGENT: Record<string, string[]> = {
  sage: [
    "What did the agents do in the last 24 hours?",
    "What is the most important open loop in my vault right now?",
    "Summarise this week from my daily notes.",
  ],
  hunter: [
    "Research what changed in self-hosted agent frameworks this month and file a quarantine note.",
    "Find two reputable sources on evaluating LLM agents and summarise the disagreement between them.",
  ],
  scout: [
    "Give me five video ideas from the newest quarantine notes, ranked, with the hook for each.",
    "Draft a short post about what I built this week, in my plain voice.",
  ],
  librarian: [
    "What is in my memory blocks right now, and what is close to its cap?",
    "Which notes look like duplicates of each other?",
  ],
  planner: [
    "What should I work on this week, based on the board and my last seven daily notes?",
  ],
  factory: [
    "Create an agent that reads my daily notes every Friday and writes a one-page review of what I learned.",
  ],
};

const FALLBACK = [
  "What can you do, and which tools do you hold?",
  "What did you do most recently?",
];

export function startersFor(agent: string | null): string[] {
  if (!agent) return FALLBACK;
  return BY_AGENT[agent] ?? FALLBACK;
}
