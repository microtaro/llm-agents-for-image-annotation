// Shapes in original-image pixels, drawn on an image of any shown size (DESIGN.md 5).
import type { Geometry } from "@/api/types";

/** [x, y, w, h] around a geometry, in original pixels. */
export function boundsOf(geometry: Geometry): [number, number, number, number] {
  if (geometry.type === "bbox") return geometry.xywh;
  if (geometry.type === "mask") return geometry.bbox_xywh;
  const xs = geometry.points.map((p) => p[0]);
  const ys = geometry.points.map((p) => p[1]);
  const left = Math.min(...xs);
  const top = Math.min(...ys);
  return [left, top, Math.max(...xs) - left, Math.max(...ys) - top];
}

/** The object under a point (original pixels): the smallest whose bounds hold it, so a field
 * inside its box is found before the box; null when none. Empty boxes (values only) never. */
export function objectAt(
  objects: { id: string; geometry: Geometry }[],
  x: number,
  y: number,
): string | null {
  let found: string | null = null;
  let least = Infinity;
  for (const o of objects) {
    const [left, top, w, h] = boundsOf(o.geometry);
    if (w * h === 0 || x < left || y < top || x > left + w || y > top + h) continue;
    if (w * h < least) {
      least = w * h;
      found = o.id;
    }
  }
  return found;
}

/** SVG points ("x,y x,y …") of a polygon or a box, in original pixels (the SVG's viewBox). */
export function svgPoints(geometry: Geometry): string {
  if (geometry.type === "polygon") return geometry.points.map(([x, y]) => `${x},${y}`).join(" ");
  const [x, y, w, h] = boundsOf(geometry);
  return `${x},${y} ${x + w},${y} ${x + w},${y + h} ${x},${y + h}`;
}

/** A tag's width in screen px: its letters (a wide letter, as kana and kanji, a full size) and
 * its padding. */
function tagWidth(text: string, tagSize: number): number {
  let width = 8;
  for (const letter of text) width += letter.codePointAt(0)! > 0x2e80 ? tagSize : tagSize * 0.6;
  return width;
}

/**
 * Where the label tags go, in percent of the image (DESIGN.md 5): each outside its box at its
 * top left, or just inside when the outside would leave the top of the image; one that would
 * cover a tag already placed is stacked above it (below, when the top is reached); one past the
 * right edge is moved in (Astra 2026-10-20: the marks' tags covered each other, and a tag at the
 * right edge was cut). shownHeight is the image's height on screen in px (times the zoom),
 * tagSize the tags' font size in px.
 */
export function tagPlaces(
  tags: { geometry: Geometry; text: string }[],
  imageWidth: number,
  imageHeight: number,
  shownHeight: number,
  tagSize = 11,
): { left: number; top: number }[] {
  const scale = imageHeight / shownHeight;
  const height = tagSize * 1.4 * scale;
  const placed: [number, number, number, number][] = [];
  return tags.map(({ geometry, text }) => {
    const [x, y] = boundsOf(geometry);
    const width = tagWidth(text, tagSize) * scale;
    const left = Math.max(0, Math.min(x, imageWidth - width));
    const covers = (top: number) =>
      placed.some(
        ([l, t, w, h]) => left < l + w && l < left + width && top < t + h && t < top + height,
      );
    let top = y < height ? y : y - height;
    let up = top;
    while (covers(up) && up - height >= 0) up -= height;
    if (!covers(up)) top = up;
    else while (covers(top) && top + height <= imageHeight) top += height;
    placed.push([left, top, width, height]);
    return { left: (left / imageWidth) * 100, top: (top / imageHeight) * 100 };
  });
}

/** An image fitted whole inside an area, centered (the loupe's view: the area is the zoom's
 * window, so a tall page leaves room at its sides and zooming in fills them; user
 * 2026-10-07: the loupe's view was the image's own narrow shape). */
export function fitInside(
  areaWidth: number,
  areaHeight: number,
  imageWidth: number,
  imageHeight: number,
): { left: number; top: number; width: number; height: number } {
  const scale = Math.min(areaWidth / imageWidth, areaHeight / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  return { left: (areaWidth - width) / 2, top: (areaHeight - height) / 2, width, height };
}
