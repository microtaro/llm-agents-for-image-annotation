import { describe, expect, it } from "vite-plus/test";
import type { Annotation } from "@/api/types";
import type { EditShape } from "@/lib/editing";
import { markChanged, numberShapes } from "../ResultEditor";

const base: Annotation[] = [
  {
    id: "a",
    label: "circle",
    geometry: { type: "bbox", xywh: [0, 0, 5, 5] },
    attributes: { color: "red" },
    parent_id: null,
  },
];

describe("a fix of a result", () => {
  it("marks what a person made or changed against where the draft started", () => {
    const shapes: EditShape[] = [
      {
        id: "a",
        label: "circle",
        geometry: base[0].geometry,
        attributes: { color: "red" },
        parent: null,
        changed: true,
      },
      {
        id: "b",
        label: "circle",
        geometry: base[0].geometry,
        attributes: {},
        parent: null,
        changed: false,
      },
    ];
    expect(markChanged(shapes, base).map((s) => s.changed)).toEqual([false, true]);
    const moved: EditShape[] = [
      {
        ...shapes[0],
        geometry: { type: "bbox" as const, xywh: [1, 0, 5, 5] as [number, number, number, number] },
      },
    ];
    expect(markChanged(moved, base)[0].changed).toBe(true);
  });

  it("calls objects by the server's number, new ones until saved", () => {
    const shape = (id: string, number: number | null): EditShape => ({
      id,
      label: "circle",
      geometry: base[0].geometry,
      attributes: {},
      parent: null,
      changed: false,
      number,
    });
    expect(numberShapes([shape("1", 7), shape("2", null)])).toEqual({
      "1": "circle 7",
      "2": "circle （新）",
    });
  });
});
