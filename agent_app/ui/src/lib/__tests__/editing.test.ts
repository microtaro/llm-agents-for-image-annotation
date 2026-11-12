import { describe, expect, it } from "vite-plus/test";
import {
  boxFrom,
  closes,
  crossesItself,
  dragged,
  type EditShape,
  handleAt,
  hit,
  moveGeometry,
  moveVertex,
  remember,
  resizeBox,
  toImage,
} from "../editing";

const box = (id: string, xywh: [number, number, number, number]): EditShape => ({
  id,
  label: "circle",
  geometry: { type: "bbox", xywh },
  attributes: {},
  parent: null,
  changed: false,
});

describe("editing", () => {
  it("turns a point on the shown image into original pixels, inside the image", () => {
    const rect = { left: 100, top: 50, width: 500, height: 250 };
    expect(toImage(350, 175, rect, 2000, 1000)).toEqual([1000, 500]);
    expect(toImage(0, 0, rect, 2000, 1000)).toEqual([0, 0]);
  });

  it("hits the smallest shape around the point", () => {
    const shapes = [box("big", [0, 0, 100, 100]), box("small", [40, 40, 10, 10])];
    expect(hit(shapes, [45, 45])).toBe("small");
    expect(hit(shapes, [5, 5])).toBe("big");
    expect(hit(shapes, [500, 500])).toBeNull();
  });

  it("hits a line pressed near, outside or inside, the line's own box first (user 2026-10-16)", () => {
    const shapes = [box("big", [0, 0, 100, 100]), box("small", [40, 40, 10, 10])];
    expect(hit(shapes, [103, 50], 4)).toBe("big"); // just outside the big box's line
    expect(hit(shapes, [5, 5], 4)).toBe("big");
    expect(hit(shapes, [38, 45], 4)).toBe("small"); // near the small box's line, inside the big
    expect(hit(shapes, [110, 50], 4)).toBeNull();
  });

  it("finds a corner and resizes from it, keeping the opposite corner", () => {
    const g = { type: "bbox" as const, xywh: [10, 10, 20, 20] as [number, number, number, number] };
    expect(handleAt(g, [30, 31], 2)).toBe("se");
    expect(resizeBox(g, "se", [50, 40])).toEqual({ type: "bbox", xywh: [10, 10, 40, 30] });
    expect(resizeBox(g, "nw", [40, 40])).toEqual({ type: "bbox", xywh: [30, 30, 10, 10] });
  });

  it("moves a shape but never out of the image", () => {
    const g = { type: "bbox" as const, xywh: [10, 10, 20, 20] as [number, number, number, number] };
    expect(moveGeometry(g, -50, 5, 100, 100)).toEqual({ type: "bbox", xywh: [0, 15, 20, 20] });
  });

  it("draws boxes only above the smallest size", () => {
    expect(boxFrom([10, 10], [12, 30])).toBeNull();
    expect(boxFrom([30, 30], [10, 10])).toEqual({ type: "bbox", xywh: [10, 10, 20, 20] });
  });

  it("keeps polygons from crossing themselves", () => {
    expect(
      crossesItself([
        [0, 0],
        [10, 0],
        [10, 10],
        [0, 10],
      ]),
    ).toBe(false);
    expect(
      crossesItself([
        [0, 0],
        [10, 10],
        [10, 0],
        [0, 10],
      ]),
    ).toBe(true);
    const square = {
      type: "polygon" as const,
      points: [
        [0, 0],
        [10, 0],
        [10, 10],
        [0, 10],
      ] as [number, number][],
    };
    expect(moveVertex(square, 0, [20, 5])).toBe(square);
    expect(
      closes(
        [
          [0, 0],
          [10, 0],
          [10, 10],
        ],
        [1, 1],
        2,
      ),
    ).toBe(true);
    expect(
      closes(
        [
          [0, 0],
          [10, 0],
        ],
        [0, 0],
        2,
      ),
    ).toBe(false);
  });

  it("takes a press that wanders a few pixels as a press, not a move", () => {
    // User 2026-10-27: the loupe looks and fixes on one image; pressing an object to look at it
    // must not start a fix.
    expect(dragged([100, 100], [103, 102])).toBe(false);
    expect(dragged([100, 100], [106, 100])).toBe(true);
  });

  it("keeps a bounded undo history", () => {
    expect(remember([1, 2, 3], 4, 3)).toEqual([2, 3, 4]);
  });
});
