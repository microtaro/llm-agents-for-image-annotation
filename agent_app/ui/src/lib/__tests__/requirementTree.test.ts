import { describe, expect, it } from "vite-plus/test";
import type { LabelDefinition } from "@/api/types";
import { answerRows, schemaRows, unionOf } from "../requirementTree";

const label = (
  name: string,
  attributes: string[],
  parent: string | null = null,
): LabelDefinition => ({
  name,
  shape: "bbox",
  parent,
  description: "",
  attributes: attributes.map((a) => ({ name: a, type: "text", choices: null, description: "" })),
});
const shown = (rows: ReturnType<typeof schemaRows>) =>
  rows
    .slice(1)
    .map(
      (r) => `${"  ".repeat(r.depth - 1)}${r.blank ? "·" : r.name}${r.mark ? ` ${r.mark}` : ""}`,
    );

describe("the requirement's tree", () => {
  it("marks what the plan adds and drops, a child label under its parent", () => {
    const before = [label("箱", ["郵便番号", "個数"])];
    const now = [label("箱", ["個数", "会社名"]), label("印", ["種類"], "箱")];
    expect(shown(schemaRows(now, { base: before }))).toEqual([
      "箱 same",
      "  郵便番号 drop",
      "  個数 same",
      "  会社名 add",
      "  印 add",
      "    種類 add",
    ]);
    expect(schemaRows(now)[4]).toMatchObject({ name: "印", inside: "箱", depth: 2 });
  });

  it("keeps the rows of cards side by side aligned, the ones a card lacks blank", () => {
    const one = [label("箱", ["郵便番号"])];
    const two = [label("箱", ["郵便番号", "理由"])];
    const union = unionOf([one, two]);
    expect(shown(schemaRows(one, { union, others: [two] }))).toEqual(["箱", "  郵便番号", "  ·"]);
    expect(shown(schemaRows(two, { union, others: [one] }))).toEqual([
      "箱",
      "  郵便番号",
      "  理由 only",
    ]);
  });
});

describe("an image's annotation", () => {
  it("numbers each object by its path, a child in the smallest parent holding its middle", () => {
    const box = (id: string, xywh: [number, number, number, number], name = "箱") => ({
      id,
      label: name,
      geometry: { type: "bbox" as const, xywh },
      attributes: {},
      parent_id: null,
    });
    const objects = [
      box("a", [0, 0, 100, 100]),
      box("b", [200, 0, 100, 100]),
      box("m1", [210, 10, 10, 10], "印"),
      box("m2", [10, 10, 10, 10], "印"),
      box("m3", [400, 400, 10, 10], "印"),
      { ...box("m4", [220, 10, 10, 10], "印"), parent_id: "a" },
    ];
    const { rows, paths } = answerRows(objects, [label("箱", []), label("印", ["種類"], "箱")]);
    expect(Object.fromEntries(paths)).toEqual({
      a: "1",
      m2: "1-1",
      m4: "1-2",
      b: "2",
      m1: "2-1",
      m3: "3",
    });
    expect(rows.find((r) => r.path === "3")).toMatchObject({ outside: true, depth: 1 });
    expect(rows.find((r) => r.path === "1-1")).toMatchObject({ depth: 2 });
  });
});
