import { describe, expect, it } from "vite-plus/test";
import type { StateCounts } from "@/api/types";
import { barParts, labelsLine } from "../stateCounts";

const counts: StateCounts = {
  images: 50,
  done: 4,
  other: 0,
  checked: 0,
  running: 1,
  failed: 2,
  stale: 1,
  none: 42,
  used: 3,
  excluded: 1,
};

describe("the images by state in one bar (definition 57)", () => {
  // User 2026-10-27: "annotated n/N, used n/N" in words is not seen at a glance, and how far the
  // annotation came is a question of its own, before training.
  it("puts every image in one part, annotating's and training's apart", () => {
    for (const kind of ["annotation", "training"] as const) {
      const parts = barParts(counts, kind);
      expect(parts.reduce((s, p) => s + p.count, 0)).toBe(counts.images);
    }
    expect(barParts(counts, "annotation")[0]).toMatchObject({ count: 4, color: "annotated" });
    expect(barParts(counts, "training")[0]).toMatchObject({ count: 3, color: "annotated" });
  });
  it("says what is put on in one line", () => {
    const labels = ["ゾウ", "シマウマ", "キリン", "カバ"].map((name) => ({
      name,
      shape: "polygon",
    }));
    expect(labelsLine(labels)).toContain("ゾウ");
    expect(labelsLine(labels)).not.toContain("カバ");
  });
});

describe("what a label holds", () => {
  it("is said by its shape, the label it is in and its attributes (user 2026-10-28)", () => {
    const line = labelsLine([
      { name: "label", shape: "bbox", parent: null, attributes: [] },
      { name: "field", shape: "bbox", parent: "label", attributes: ["name", "text"] },
    ]);
    expect(line).toContain("field（枠・labelの中・属性: name・text）");
    expect(line).not.toContain("付ける");
  });
});
