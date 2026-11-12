// The arithmetic of editing in the loupe (step 7 design 4), apart from the screen so it can be
// tested: positions in original-image pixels, what a press hits, moving and resizing boxes,
// polygon vertices and whether a polygon crosses itself.
import type { Annotation, Geometry } from "@/api/types";
import { byLabel } from "./display";

export type Point = [number, number];
export type Corner = "nw" | "ne" | "sw" | "se";

export interface EditShape {
  id: string;
  label: string;
  geometry: Geometry;
  attributes: Record<string, string | number>;
  parent: string | null;
  /** Made or changed by a person in this draft (drawn dashed, DESIGN.md 5). */
  changed: boolean;
  /** The server's number (null until a new object is saved). */
  number?: number | null;
}

/** The objects in the order the loupe and the table list them: parents first, each followed
 * by its children one level deeper; by label, then number (Astra 2026-10-06: the editor's
 * list was flat, the fields apart from their box). */
export function nested(shapes: EditShape[]): { shape: EditShape; depth: number }[] {
  const ids = new Set(shapes.map((s) => s.id));
  const order = (a: EditShape, b: EditShape) =>
    byLabel(a.label, b.label) || (a.number ?? 1e9) - (b.number ?? 1e9);
  const out: { shape: EditShape; depth: number }[] = [];
  const place = (parent: string | null, depth: number) => {
    for (const shape of shapes
      .filter((s) => (s.parent && ids.has(s.parent) ? s.parent : null) === parent)
      .sort(order)) {
      out.push({ shape, depth });
      place(shape.id, depth + 1);
    }
  };
  place(null, 0);
  return out;
}

/** How a person calls an object: its label and number ("circle 7"). */
export function nameOf(label: string, number: number | null | undefined, unsaved: string): string {
  return number ? `${label} ${number}` : `${label} ${unsaved}`;
}

export const round = (value: number) => Math.round(value * 10) / 10;
const clampTo = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

/** A point on the shown image (its box on screen, zoom included) in original pixels, kept inside. */
export function toImage(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  width: number,
  height: number,
): Point {
  return [
    round(clampTo(((clientX - rect.left) / rect.width) * width, 0, width)),
    round(clampTo(((clientY - rect.top) / rect.height) * height, 0, height)),
  ];
}

export function boxOf(geometry: Geometry): [number, number, number, number] {
  if (geometry.type === "bbox") return geometry.xywh;
  if (geometry.type === "mask") return geometry.bbox_xywh;
  const xs = geometry.points.map((p) => p[0]);
  const ys = geometry.points.map((p) => p[1]);
  return [
    Math.min(...xs),
    Math.min(...ys),
    Math.max(...xs) - Math.min(...xs),
    Math.max(...ys) - Math.min(...ys),
  ];
}

export function insidePolygon(points: Point[], [x, y]: Point): boolean {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i];
    const [xj, yj] = points[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** The shape a press at this point hits: the smallest one around it, or null. */
/** The object at a point: one whose outline is within tolerance (original pixels) is taken
 * first, the nearest outline (user 2026-10-16: a box had to be pressed exactly on its line, and
 * where boxes overlap the line's box was not the one chosen); else the smallest one around it. */
export function hit(shapes: EditShape[], point: Point, tolerance = 0): string | null {
  let nearest: { id: string; distance: number } | null = null;
  for (const shape of shapes) {
    const distance = outlineDistance(shape.geometry, point);
    if (distance <= tolerance && (!nearest || distance < nearest.distance))
      nearest = { id: shape.id, distance };
  }
  if (nearest) return nearest.id;
  const around = shapes.filter((shape) => {
    const g = shape.geometry;
    if (g.type === "polygon") return insidePolygon(g.points, point);
    const [x, y, w, h] = boxOf(g);
    return point[0] >= x && point[0] <= x + w && point[1] >= y && point[1] <= y + h;
  });
  around.sort((a, b) => area(a.geometry) - area(b.geometry));
  return around[0]?.id ?? null;
}

/** How far a point is from a shape's outline (its edges, not its inside). */
function outlineDistance(geometry: Geometry, point: Point): number {
  let corners: Point[];
  if (geometry.type === "polygon") corners = geometry.points;
  else if (geometry.type === "bbox") {
    const [x, y, w, h] = geometry.xywh;
    corners = [
      [x, y],
      [x + w, y],
      [x + w, y + h],
      [x, y + h],
    ];
  } else return Infinity;
  let best = Infinity;
  corners.forEach((from, index) => {
    best = Math.min(best, segmentDistance(point, from, corners[(index + 1) % corners.length]));
  });
  return best;
}

function segmentDistance([px, py]: Point, [ax, ay]: Point, [bx, by]: Point): number {
  const dx = bx - ax;
  const dy = by - ay;
  const length = dx * dx + dy * dy;
  const at = length ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length)) : 0;
  return Math.hypot(px - (ax + at * dx), py - (ay + at * dy));
}

function area(geometry: Geometry): number {
  const [, , w, h] = boxOf(geometry);
  return w * h;
}

/** A box corner or a polygon vertex near the point (within tolerance original pixels). */
export function handleAt(
  geometry: Geometry,
  [x, y]: Point,
  tolerance: number,
): Corner | number | null {
  const near = ([px, py]: Point) => Math.abs(px - x) <= tolerance && Math.abs(py - y) <= tolerance;
  if (geometry.type === "polygon") {
    const index = geometry.points.findIndex((p) => near(p));
    return index >= 0 ? index : null;
  }
  if (geometry.type !== "bbox") return null;
  const [bx, by, bw, bh] = geometry.xywh;
  const corners: [Corner, Point][] = [
    ["nw", [bx, by]],
    ["ne", [bx + bw, by]],
    ["sw", [bx, by + bh]],
    ["se", [bx + bw, by + bh]],
  ];
  return corners.find(([, p]) => near(p))?.[0] ?? null;
}

/** A geometry moved by (dx, dy), kept wholly inside the image. */
export function moveGeometry(
  geometry: Geometry,
  dx: number,
  dy: number,
  width: number,
  height: number,
): Geometry {
  const [x, y, w, h] = boxOf(geometry);
  const mx = clampTo(dx, -x, width - (x + w));
  const my = clampTo(dy, -y, height - (y + h));
  if (geometry.type === "bbox") return { type: "bbox", xywh: [round(x + mx), round(y + my), w, h] };
  if (geometry.type === "polygon") {
    return {
      type: "polygon",
      points: geometry.points.map(([px, py]) => [round(px + mx), round(py + my)]),
    };
  }
  return geometry;
}

/** A box from two corners, normalized, or null when smaller than minimum pixels a side. */
export function boxFrom([x1, y1]: Point, [x2, y2]: Point, minimum = 4): Geometry | null {
  const w = Math.abs(x2 - x1);
  const h = Math.abs(y2 - y1);
  if (w < minimum || h < minimum) return null;
  return {
    type: "bbox",
    xywh: [round(Math.min(x1, x2)), round(Math.min(y1, y2)), round(w), round(h)],
  };
}

/** A box with one corner dragged to the point; the opposite corner stays. */
export function resizeBox(geometry: Geometry, corner: Corner, point: Point): Geometry {
  if (geometry.type !== "bbox") return geometry;
  const [x, y, w, h] = geometry.xywh;
  const fixed: Point = {
    nw: [x + w, y + h] as Point,
    ne: [x, y + h] as Point,
    sw: [x + w, y] as Point,
    se: [x, y] as Point,
  }[corner];
  return boxFrom(fixed, point, 1) ?? geometry;
}

function cross(a: Point, b: Point, c: Point): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function segmentsCross(a: Point, b: Point, c: Point, d: Point): boolean {
  const d1 = cross(a, b, c);
  const d2 = cross(a, b, d);
  const d3 = cross(c, d, a);
  const d4 = cross(c, d, b);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

/** Whether the closed polygon's edges cross (the server refuses such a polygon). */
export function crossesItself(points: Point[]): boolean {
  const n = points.length;
  for (let i = 0; i < n; i++) {
    for (let j = i + 2; j < n; j++) {
      if (i === 0 && j === n - 1) continue;
      if (segmentsCross(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n]))
        return true;
    }
  }
  return false;
}

/** A polygon with one vertex moved, or the same polygon when the move would make it cross. */
export function moveVertex(geometry: Geometry, index: number, point: Point): Geometry {
  if (geometry.type !== "polygon") return geometry;
  const points = geometry.points.map((p, i) => (i === index ? point : p)) as Point[];
  return crossesItself(points) ? geometry : { type: "polygon", points };
}

/** Whether pressing the point closes the polygon being drawn: on its first vertex, 3 or more. */
export function closes(points: Point[], point: Point, tolerance: number): boolean {
  if (points.length < 3) return false;
  const [fx, fy] = points[0];
  return Math.abs(fx - point[0]) <= tolerance && Math.abs(fy - point[1]) <= tolerance;
}

/** Screen pixels a press may wander and still be a press, not a move (user 2026-10-27: the
 * loupe looks and fixes on one image, so pressing an object to look at it must not move it). */
export const SLOP = 4;

/** Whether the pointer went far enough from where it was pressed to move what it holds. */
export function dragged(from: [number, number], to: [number, number]): boolean {
  return Math.hypot(to[0] - from[0], to[1] - from[1]) > SLOP;
}

/** Undo history: past states, newest last, at most limit kept. */
export function remember<T>(history: T[], state: T, limit = 100): T[] {
  return [...history, state].slice(-limit);
}

/** Whether a shape says what a saved object says (its label, place, values and parent). */
export function unchanged(was: Annotation, shape: EditShape): boolean {
  return (
    was.label === shape.label &&
    JSON.stringify(was.geometry) === JSON.stringify(shape.geometry) &&
    JSON.stringify(was.attributes ?? {}) === JSON.stringify(shape.attributes) &&
    (was.parent_id ?? null) === shape.parent
  );
}
