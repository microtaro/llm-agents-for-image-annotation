// The images by state, in one bar each for annotating and for training (definition 57; user
// 2026-10-27: "annotated n/N, used n/N" said as words is not seen at a glance, and how far the
// annotation came is a question before training). The parts' colours are DESIGN.md 6's meanings.
import type { PutLabel, StateCounts } from "@/api/types";
import { t } from "@/i18n";

export type BarKind = "annotation" | "training";

export interface BarPart {
  key: string;
  count: number;
  /** The colour's token: green success / used, ochre working, red failed, gray not. */
  color: "annotated" | "processing" | "failed" | "unprocessed";
}

/** A bar's parts, every image in one of them. */
export function barParts(counts: StateCounts, kind: BarKind): BarPart[] {
  if (kind === "annotation")
    return [
      { key: "done", count: counts.done, color: "annotated" },
      // Annotated by other criteria, not by this one's (definition 85.4).
      { key: "other", count: counts.other, color: "unprocessed" },
      { key: "running", count: counts.running, color: "processing" },
      { key: "failed", count: counts.failed, color: "failed" },
      { key: "stale", count: counts.stale, color: "unprocessed" },
      { key: "none", count: counts.none, color: "unprocessed" },
    ];
  return [
    { key: "used", count: counts.used, color: "annotated" },
    { key: "excluded", count: counts.excluded, color: "unprocessed" },
    {
      key: "unusable",
      count: counts.images - counts.used - counts.excluded,
      color: "unprocessed",
    },
  ];
}

/** The bar's one number, "annotated 4/50" or "used for training 4/50". */
export function barNumber(counts: StateCounts, kind: BarKind): string {
  return kind === "annotation"
    ? t("apply.fact.done", { done: counts.done, total: counts.images })
    : t("apply.fact.used", { used: counts.used, total: counts.images });
}

/** The attributes not filled, "lid not filled: 3 · colour not filled: 2" (definition 85.17):
 * said where the images are annotated, nothing when every one is filled. */
export function unfilledLine(unfilled: Record<string, number> | null | undefined): string {
  return Object.entries(unfilled ?? {})
    .filter(([, count]) => count > 0)
    .map(([name, count]) => t("apply.fact.unfilled", { name, count }))
    .join(t("text.dot"));
}

/** The parts in words, for the hover. */
export function barWords(counts: StateCounts, kind: BarKind): string {
  return barParts(counts, kind)
    .filter((p) => p.count)
    .map((p) => `${t(`state.${p.key}`)} ${p.count}`)
    .join(t("text.dot"));
}

/** What is put on the images in one line: the first three labels, how many more, and how each
 * is taken (once, when all are taken alike); the whole in labelsFull. */
/** The labels in a line with what information each holds (user 2026-10-28: "what version n puts
 * on" said nothing the plan chosen does not): its shape, the label it is in, its attributes; the
 * first three, the rest counted. Labels of one shape holding nothing more say it once at the end. */
export function labelsLine(labels: PutLabel[]): string {
  const plain = labels.every((l) => !l.parent && !l.attributes?.length);
  const one = plain && new Set(labels.map((l) => l.shape)).size === 1;
  const names = labels.slice(0, 3).map((l) => (one ? l.name : labelWords(l)));
  const more = labels.length > 3 ? t("put.more", { count: labels.length - 3 }) : "";
  const shape = one && labels.length ? t(`tree.shape.${labels[0].shape}`) : "";
  return names.join(t("put.join")) + more + shape;
}

export function labelsFull(labels: PutLabel[]): string {
  return labels.map(labelWords).join(t("book.summary.join"));
}

/** One label and what it holds, in the plan's words (its shape, "in" its parent, attributes). */
function labelWords(label: PutLabel): string {
  const parts = [
    t(`put.shape.${label.shape}`),
    label.parent ? t("tree.inside", { label: label.parent }) : "",
    label.attributes?.length
      ? t("put.attributes", { names: label.attributes.join(t("put.join")) })
      : "",
  ].filter(Boolean);
  return t("put.label", { name: label.name, holds: parts.join(t("put.join")) });
}
