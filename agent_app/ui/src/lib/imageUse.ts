// Whether an image is used for training (the mark on its card, the box in the loupe and the
// table). Leaving out keeps the image and its results; it can be put back.
import { api } from "@/api/client";
import type { GalleryItem } from "@/api/types";
import { invalidate } from "./useApi";

/** The one mark at a card's top left (types design 17.1, user 2026-10-13): nothing run yet
 * (none), run and not used for training (ran, ✓), used for training (adopted, circled ✓), or
 * running (◐). */
export type UseMark = "none" | "ran" | "adopted" | "running";

export function markOf(item: GalleryItem): UseMark {
  const kind = item.badge.kind;
  if (item.badge.waiting) return "running";
  if (kind === "result") return "adopted";
  if (kind === "excluded") return item.badge.ran ? "ran" : "none";
  if (item.badge.succeeded) return "ran";
  return "none";
}

export async function setUsed(datasetId: string, imageId: string, used: boolean) {
  await api(`/v1/datasets/${datasetId}/images/${imageId}/${used ? "include" : "exclude"}`, {
    body: {},
  });
  invalidate(datasetId);
}

/** setUsed for one dataset (a person's own tick on a card, a table row or the loupe). */
export function useSetUsed(datasetId: string) {
  return (imageId: string, used: boolean) => setUsed(datasetId, imageId, used);
}
