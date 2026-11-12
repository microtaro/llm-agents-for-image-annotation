// The settings' numbers as typed (step 12, found 2026-10-05 by Sol: an emptied field was saved
// as 0): what is wrong with each, so Save waits until every number is right.
export type Problem = "empty" | "whole" | "range" | null;

/** Only money may have decimals (the yen rate, the cost limit per image); every other setting
 * is a whole number. */
const DECIMAL = ["usd_to_jpy", "run_budget_per_image_usd"];

export function problemOf(key: string, text: string, [min, max]: [number, number]): Problem {
  if (text.trim() === "") return "empty";
  const value = Number(text);
  if (!Number.isFinite(value)) return "empty";
  if (!DECIMAL.includes(key) && !Number.isInteger(value)) return "whole";
  if (value < min || value > max) return "range";
  return null;
}
