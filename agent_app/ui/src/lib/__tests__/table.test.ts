import { describe, expect, it } from "vite-plus/test";
import type { GalleryItem } from "@/api/types";
import { attributeColumns, buildRows, findRows, noAnswer, sortRows } from "../table";

const box = { type: "bbox" as const, xywh: [0, 0, 1, 1] as [number, number, number, number] };
const ann = (
  id: string,
  label: string,
  number: number,
  parent: string | null,
  attributes = {},
) => ({
  id,
  label,
  number,
  parent_id: parent,
  geometry: box,
  attributes,
});
const item = (id: string, annotations: ReturnType<typeof ann>[]) =>
  ({
    image: { id, name: `${id}.png` },
    badge: { kind: "detected", succeeded: true },
    annotations,
  }) as unknown as GalleryItem;

describe("gallery table", () => {
  it("puts children under their parent, finds empty and repeated values", () => {
    const items = [
      item("a", [
        ann("r1", "row", 2, "t", { item: "Salt", amount: "0.8 g" }),
        ann("t", "table", 1, null),
        ann("r2", "row", 1, "t", { item: "Fat", amount: "" }),
      ]),
      item("b", []),
      item("c", [ann("x", "row", 1, null, { item: "Salt", amount: "1 g" })]),
    ];
    const rows = buildRows(items);
    expect(rows.map((r) => [r.label, r.number, r.depth, r.parent])).toEqual([
      ["table", 1, 0, ""],
      ["row", 1, 1, "table 1"],
      ["row", 2, 1, "table 1"],
      ["", null, 0, ""],
      ["row", 1, 0, ""],
    ]);
    const columns = ["item", "amount"];
    // The table has no attributes of its own: not "empty"; r2's amount is.
    expect(findRows(rows, "", "empty", columns, null).map((r) => r.annotationId)).toEqual(["r2"]);
    expect(findRows(rows, "", "same", columns, null).map((r) => r.annotationId)).toEqual([
      "r1",
      "x",
    ]);
    expect(findRows(rows, "salt", "all", columns, null).map((r) => r.annotationId)).toEqual([
      "r1",
      "x",
    ]);
    // An attribute of the plan none has a value of yet is a column, its values empty (2026-10-30:
    // boxes carried over, the attribute added had no column and nothing said a value was missing).
    const plan = [{ name: "row", shape: "bbox", attributes: ["item", "amount", "unit"] }];
    expect(attributeColumns(items, plan)).toEqual(["item", "amount", "unit"]);
    expect(
      findRows(rows, "", "empty", attributeColumns(items, plan), plan).map((r) => r.annotationId),
    ).toEqual(["r2", "r1", "x"]);
    expect(sortRows(rows, "amount", true).map((r) => r.values.amount ?? "")).toEqual([
      "",
      "",
      "",
      "0.8 g",
      "1 g",
    ]);
  });
});

describe("no result to show", () => {
  it("is said for a stopped image, not for a run that found nothing", () => {
    const item = (kind: string) =>
      ({ image: { id: "a" }, badge: { kind }, annotations: [] }) as unknown as GalleryItem;
    expect(noAnswer(item("interrupted"), "run")).toBe(true);
    expect(noAnswer(item("none"), "adoption")).toBe(true);
    expect(
      noAnswer(
        { ...item("not_detected"), badge: { kind: "not_detected", succeeded: true } },
        "run",
      ),
    ).toBe(false);
    expect(noAnswer(item("interrupted"), "images")).toBe(false);
  });

  it("is not said for a left out image with the result it would use, with no objects", () => {
    const left = (badge: object) =>
      ({ image: { id: "a" }, badge, annotations: [] }) as unknown as GalleryItem;
    expect(noAnswer(left({ kind: "excluded", result_id: "r1", ran: true }), "adoption")).toBe(
      false,
    );
    expect(noAnswer(left({ kind: "excluded" }), "adoption")).toBe(true);
  });
});

describe("the table's row keys", () => {
  it("differ for objects of two images with the same id (result samples are s-0, s-1…)", () => {
    const rows = buildRows([
      item("a", [ann("s-0", "box", 1, null)]),
      item("b", [ann("s-0", "box", 1, null)]),
    ]);
    const keys = rows.map((r) => r.key);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
