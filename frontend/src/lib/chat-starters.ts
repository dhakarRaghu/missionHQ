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
    "Which roles should I act on this week, and what is the next step for each?",
    "Give me three post ideas from what I learned this week.",
  ],
  hunter: [
    "Who could refer me at Cloudflare for the SWE L1 role, and what do we share?",
    "Find two independent sources on chunked prefill and say where they disagree.",
  ],
  tutor: [
    "Which concepts did the last lesson teach, and what did it leave out?",
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
