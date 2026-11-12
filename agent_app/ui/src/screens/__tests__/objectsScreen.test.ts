import { describe, expect, it } from "vite-plus/test";
import { conditions } from "../ObjectsScreen";

describe("conditions", () => {
  it("names the images it names by id", () => {
    // 2026-10-28: a set opened from the talk said "指定した物: img-46e8…,img-37ed…".
    const names = new Map([
      ["img-a", "B001.png"],
      ["img-b", "B002.png"],
    ]);
    const said = conditions({ ids: "img-a,img-b" }, (id) => names.get(id) ?? id);
    expect(said).toContain("B001.png");
    expect(said).toContain("B002.png");
    expect(said).not.toContain("img-a");
  });

  it("names a record by its number and never shows its id", () => {
    // 2026-11-05: samples opened from the talk said "Annotation record: 8d8d2c25-e0d3-…".
    const id = "8d8d2c25-e0d3-43e5-a388-72b1a572bed1";
    expect(conditions({ run: id }, () => "Record 1")).toBe("Record 1");
    expect(conditions({ run: id }, (known) => known)).not.toContain(id);
  });
});
