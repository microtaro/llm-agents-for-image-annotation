// The images on the gallery's screen now, in its order: the filter chip of the stage, and in
// the table the images of the found rows. The loupe steps through the same images (Astra
// 2026-10-06: "next" went past the filter, "pick the shown" picked all 20 while 7 showed).
import type { GalleryItem, PutLabel, StageName } from "@/api/types";
import { groupOf } from "./filters";
import { annotated } from "./selection";
import { attributeColumns, buildRows, findRows, type Mode, sortRows } from "./table";

/** How the gallery orders its images (user 2026-10-28, as the library's "order"): as taken in
 * (old, the server's order), its reverse, by name, or by when each image's annotation now was
 * made, the newest first (the images with none after, as taken in). */
export type ImageOrder = "old" | "new" | "name" | "annotated";
export const IMAGE_ORDERS: ImageOrder[] = ["old", "new", "name", "annotated"];

export function orderImages(items: GalleryItem[], order: ImageOrder): GalleryItem[] {
  if (order === "new") return [...items].reverse();
  if (order === "name")
    return [...items].sort((a, b) =>
      a.image.name.localeCompare(b.image.name, "ja", { numeric: true }),
    );
  if (order === "annotated") {
    const at = (item: GalleryItem) => (annotated(item) ? (item.badge.record_at ?? "") : "");
    return [...items].sort((a, b) => at(b).localeCompare(at(a)));
  }
  return items;
}

export function shownImages(
  items: GalleryItem[],
  stage: StageName,
  filter: string | null,
  find: { text: string; mode: string; column?: string | null; up?: boolean } | null,
  order: ImageOrder,
  labels: PutLabel[] | null,
): string[] {
  const kept = orderImages(
    filter ? items.filter((item) => groupOf(item, stage) === filter) : items,
    order,
  );
  if (!find) return kept.map((item) => item.image.id);
  // In the table's sort too, so the loupe's "next" is the next row's image.
  const rows = sortRows(
    findRows(buildRows(kept), find.text, find.mode as Mode, attributeColumns(kept, labels), labels),
    find.column ?? null,
    find.up ?? true,
  );
  return [...new Set(rows.map((row) => row.imageId))];
}
