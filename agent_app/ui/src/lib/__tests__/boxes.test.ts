import { describe, expect, it } from "vite-plus/test";
import { boundsOf, fitInside, objectAt, svgPoints, tagPlaces } from "../boxes";
import { zoomAt } from "../useZoomPan";

describe("boxes", () => {
  it("gives the bounds and SVG points of a box and a polygon", () => {
    expect(
      boundsOf({
        type: "polygon",
        points: [
          [2, 3],
          [10, 5],
          [4, 9],
        ],
      }),
    ).toEqual([2, 3, 8, 6]);
    expect(svgPoints({ type: "bbox", xywh: [1, 2, 3, 4] })).toBe("1,2 4,2 4,6 1,6");
  });

  it("puts a tag above a box, or inside when the box touches the top", () => {
    const [above, top] = tagPlaces(
      [
        { geometry: { type: "bbox", xywh: [100, 500, 50, 50] }, text: "box 1" },
        { geometry: { type: "bbox", xywh: [600, 5, 50, 50] }, text: "box 2" },
      ],
      1000,
      1000,
      500,
    );
    expect(above.top).toBeLessThan(50);
    expect(top).toEqual({ left: 60, top: 0.5 });
  });

  it("stacks a tag that would cover another, and moves one in from the right edge", () => {
    // Astra 2026-10-20: two marks side by side had their tags over each other.
    const mark = (x: number) => ({
      geometry: {
        type: "bbox" as const,
        xywh: [x, 500, 20, 20] as [number, number, number, number],
      },
      text: "注意の印",
    });
    const [first, second] = tagPlaces([mark(100), mark(110)], 1000, 1000, 500);
    expect(second.top).toBeLessThan(first.top);
    const [edge] = tagPlaces([mark(990)], 1000, 1000, 500);
    expect(edge.left).toBeLessThan(99);
  });

  it("zooms around the pointer and never below the whole image", () => {
    const view = zoomAt({ scale: 1, x: 0, y: 0 }, 2, 100, 50);
    expect(view).toEqual({ scale: 2, x: -100, y: -50 });
    expect(zoomAt(view, 0.25, 0, 0)).toEqual({ scale: 1, x: 0, y: 0 });
  });
});

describe("display settings", () => {
  it("keeps a saved value inside its range and drops what it does not know", async () => {
    const { readDisplay, INITIAL } = await import("../display");
    expect(
      readDisplay({ lineWidth: 40, tagSize: 2, cardSize: "x", overlay: false, other: 1 }),
    ).toEqual({
      ...INITIAL,
      lineWidth: 12,
      tagSize: 8,
      overlay: false,
    });
    expect(readDisplay(null)).toEqual(INITIAL);
  });

  it("shows the table with the images where the results read values, until it is turned off (user 2026-10-29)", async () => {
    const { listShows, INITIAL } = await import("../display");
    expect(listShows(INITIAL, true, true)).toEqual({ table: true, cards: true });
    expect(listShows(INITIAL, true, false)).toEqual({ table: false, cards: true });
    expect(listShows({ ...INITIAL, table: false }, true, true)).toEqual({
      table: false,
      cards: true,
    });
    expect(listShows(INITIAL, false, true)).toEqual({ table: false, cards: true });
  });

  it("finds the smallest object under a point, a field before its box (found 2026-10-06: the loupe could not choose by the image)", () => {
    const box = (id: string, xywh: [number, number, number, number]) =>
      ({ id, geometry: { type: "bbox", xywh } }) as const;
    const objects = [
      box("box", [0, 0, 100, 100]),
      box("field", [10, 10, 20, 10]),
      box("empty", [0, 0, 0, 0]),
    ];
    expect(objectAt(objects, 15, 15)).toBe("field");
    expect(objectAt(objects, 80, 80)).toBe("box");
    expect(objectAt(objects, 150, 15)).toBeNull();
  });
});

describe("the loupe's view", () => {
  // User 2026-10-07: a tall page left a narrow view, zoomed in or not.
  it("fits the image whole and centered in the area it has", () => {
    expect(fitInside(1400, 600, 600, 900)).toEqual({ left: 500, top: 0, width: 400, height: 600 });
    expect(fitInside(1000, 800, 1536, 1024)).toEqual({
      left: 0,
      top: (800 - 1000 / 1.5) / 2,
      width: 1000,
      height: 1000 / 1.5,
    });
  });
});
