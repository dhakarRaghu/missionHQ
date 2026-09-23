/**
 * Plain-English labels for the cron expressions in an agent's manifest.
 *
 * The console shows both: the sentence for reading, the expression for editing.
 * Only the shapes Mission HQ actually uses are translated. Anything else falls
 * back to the raw expression, which is always correct if less readable.
 */

const DAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

function isNumber(field: string): boolean {
  return /^\d+$/.test(field);
}

function atTime(minute: string, hour: string): string {
  return `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
}

/** "every day at 08:00", "every Monday at 09:00", or the raw expression. */
export function describeCron(expression: string): string {
  const parts = expression.trim().split(/\s+/);
  if (parts.length !== 5) return expression;
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  if (!isNumber(minute) || !isNumber(hour)) return expression;

  const time = atTime(minute, hour);
  if (month !== "*") return expression;

  if (dayOfMonth === "*" && dayOfWeek === "*") return `every day at ${time}`;
  if (dayOfMonth === "*" && isNumber(dayOfWeek)) {
    const day = DAYS[Number(dayOfWeek) % 7];
    return `every ${day} at ${time}`;
  }
  if (isNumber(dayOfMonth) && dayOfWeek === "*") {
    return `on day ${dayOfMonth} of each month at ${time}`;
  }
  return expression;
}
