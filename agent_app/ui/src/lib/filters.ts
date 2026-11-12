// The gallery's filters: each image falls in one group of the stage looked at, and the chips
// show how many are in each (the current screen's "filter" row, per stage).
import type { GalleryItem, StageName } from "@/api/types";

/** The group of an image in a stage (its key in the dictionary: filter.<group>). */
export function groupOf(item: GalleryItem, stage: StageName): string {
  const kind = item.badge.kind;
  if (stage === "production") {
    // By the badge, the state of what is looked at (user 2026-10-14: annotating with AI, left
    // out of training is not a group).
    if (kind === "excluded") return "excluded";
    // Made by other criteria and not checked: to run again or check (85.6).
    if (item.badge.other) return "other";
    // Annotated, an attribute of the plan not filled (85.17): to fix by hand or run again.
    if (item.badge.unfilled?.length) return "unfilled";
    if (item.badge.newer) return "newer";
    if (item.badge.succeeded) return "succeeded";
    if (item.badge.waiting) return "unfinished";
    return kind; // result, failed, interrupted, stale, not_in_run, no_result
  }
  return "all";
}

/** Each group of the stage with its count, in the order first seen. */
/** The groups' fixed order on the chips, so a chip stays where it was learned (Astra
 * 2026-10-06: by first seen, "passed" and "failed" swapped places between datasets). */
const ORDER = [
  "result",
  "newer",
  "other",
  "unfilled",
  "succeeded",
  "failed",
  "interrupted",
  "unfinished",
  "stale",
  "none",
  "not_in_run",
  "no_result",
  "excluded",
];

export function groupCounts(items: GalleryItem[], stage: StageName): [string, number][] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const group = groupOf(item, stage);
    counts.set(group, (counts.get(group) ?? 0) + 1);
  }
  const at = (group: string) => (ORDER.includes(group) ? ORDER.indexOf(group) : ORDER.length);
  return [...counts.entries()].sort((a, b) => at(a[0]) - at(b[0]));
}
