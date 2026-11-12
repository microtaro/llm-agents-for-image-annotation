import { describe, expect, it } from "vite-plus/test";
import type { DatasetSummary } from "@/api/types";
import { arrange, firstIntent, intentWhyNot } from "../library";

const ds = (name: string, purpose: string, at: string) =>
  ({ id: name, name, purpose, created_at: at }) as DatasetSummary;

describe("library list", () => {
  it("finds by name or purpose and orders", () => {
    const all = [
      ds("Box B", "read lot", "2"),
      ds("box a", "find dents", "3"),
      ds("Pills", "count", "1"),
    ];
    expect(arrange(all, "box", "name").map((d) => d.name)).toEqual(["box a", "Box B"]);
    expect(arrange(all, "LOT", "new").map((d) => d.name)).toEqual(["Box B"]);
    expect(arrange(all, "", "old").map((d) => d.name)).toEqual(["Pills", "Box B", "box a"]);
  });
});

describe("taking in (definition 60.3)", () => {
  it("chooses what to do first by how many are chosen, and says why one cannot be chosen", () => {
    // 2026-10-28: what to do is chosen first; the first choice and what cannot be chosen are by
    // the datasets chosen with their rings.
    expect([0, 1, 2].map(firstIntent)).toEqual(["images", "add", "from"]);
    expect(intentWhyNot("add", 2)).not.toBeNull();
    expect(intentWhyNot("from", 0)).not.toBeNull();
    expect([intentWhyNot("add", 1), intentWhyNot("from", 2), intentWhyNot("images", 3)]).toEqual([
      null,
      null,
      null,
    ]);
  });
});

describe("the library's order by the last work", () => {
  it("puts the datasets worked on now first, not the newest made (user 2026-10-28)", () => {
    const made = (name: string, created_at: string, last_at: string) =>
      ({ id: name, name, purpose: "", created_at, last_at }) as DatasetSummary;
    const all = [
      made("old, worked today", "2026-10-01", "2026-10-28"),
      made("new, untouched", "2026-10-20", "2026-10-20"),
    ];
    expect(arrange(all, "", "worked").map((d) => d.name)).toEqual([
      "old, worked today",
      "new, untouched",
    ]);
  });
});
