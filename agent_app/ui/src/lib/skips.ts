// Why files were not taken in, in words, the one place the screen's taking in and the talk's
// line of a dataset made say it (definition 76).
import { t } from "@/i18n";

/** How many of each reason, each said by its word of the dictionary (skip.<reason>). */
export function skipText(skipped: { reason: string }[]): string {
  const counts = new Map<string, number>();
  for (const s of skipped) counts.set(s.reason, (counts.get(s.reason) ?? 0) + 1);
  return [...counts]
    .map(([reason, count]) => t("picker.reason", { reason: t(`skip.${reason}`), count }))
    .join(" · ");
}
