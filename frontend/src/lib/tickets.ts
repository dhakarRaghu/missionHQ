/**
 * Reading an approval, shared by the three places one can be answered.
 *
 * The board, the chat thread and Telegram all show the same ticket. Telegram
 * formats it in `hq/channels/cards.py`; these two helpers are the web side of
 * the same idea. A decision usually turns on one value, not on the whole
 * argument set, so show that value and keep the rest available underneath.
 */

/** Argument keys that hold the value a decision turns on, most specific first. */
const HEADLINE_KEYS = ["text", "path", "rule", "title", "query", "url"];

/** The one value to read before deciding, or null when no key matches. */
export function ticketHeadline(
  args: Record<string, unknown> | null | undefined,
): string | null {
  for (const key of HEADLINE_KEYS) {
    const value = args?.[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

/** The arguments the headline did not already show, as `key: value` lines.
 * Empty when the headline covered everything worth reading. */
export function ticketDetails(
  args: Record<string, unknown> | null | undefined,
): { key: string; value: string }[] {
  const shown = HEADLINE_KEYS.find(
    (key) => typeof args?.[key] === "string" && (args[key] as string).trim(),
  );
  return Object.entries(args ?? {})
    .filter(([key]) => key !== shown)
    .map(([key, value]) => ({
      key,
      value: typeof value === "string" ? value : JSON.stringify(value),
    }));
}
