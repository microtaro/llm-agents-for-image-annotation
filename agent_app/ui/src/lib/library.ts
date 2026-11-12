// The library's list: datasets whose name or purpose holds the words typed, newest, oldest or
// by name (user 2026-10-05: the library had little to do with many datasets).
import type { DatasetSummary } from "@/api/types";
import { t } from "@/i18n";

export type Order = "new" | "old" | "name" | "worked";

/** A dataset as people call it, its number and name, "#12" before it (definition 61). A decision
 * kept from before datasets had numbers (10-28) names a deleted one by its name alone. */
export function calledName(d: { number?: number | null; name: string }): string {
  return d.number == null
    ? t("dataset.called.unnumbered", { name: d.name })
    : t("dataset.called", { number: String(d.number), name: d.name });
}

export function arrange(datasets: DatasetSummary[], query: string, order: Order): DatasetSummary[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const found = datasets.filter((d) =>
    words.every((w) => `${d.name} ${d.purpose}`.toLowerCase().includes(w)),
  );
  return [...found].sort((a, b) =>
    order === "name"
      ? a.name.localeCompare(b.name, "ja")
      : order === "old"
        ? a.created_at.localeCompare(b.created_at)
        : order === "worked"
          ? // The card's "last work" (user 2026-10-28): the datasets worked on now first.
            b.last_at.localeCompare(a.last_at)
          : b.created_at.localeCompare(a.created_at),
  );
}

/** What taking in does (definition 60.3): a new dataset of a folder's images, images added to
 * the one chosen, a dataset made from the chosen ones' images, or a folder written out. */
export type ImportIntent = "images" | "add" | "from" | "written";

/** Taking in's first choice, by how many datasets are chosen: none a new one, one adding to it
 * (so datasets do not pile up, user 2026-10-15), several theirs together. */
export function firstIntent(chosen: number): ImportIntent {
  return chosen === 0 ? "images" : chosen === 1 ? "add" : "from";
}

/** Why an intent cannot be chosen with this many datasets chosen, or null. */
export function intentWhyNot(intent: ImportIntent, chosen: number): string | null {
  if (intent === "add" && chosen !== 1) return t("library.import.why.add");
  if (intent === "from" && chosen === 0) return t("library.why.some");
  return null;
}
