import { describe, expect, it } from "vite-plus/test";
import type { GalleryItem } from "@/api/types";
import { groupCounts, groupOf } from "../filters";

const item = (
  kind: string,
  extra: Partial<GalleryItem["badge"]> = {},
  excluded = false,
): GalleryItem => ({
  image: { id: kind, name: kind, width: 1, height: 1, origin: "real", source_path: null, excluded },
  badge: { kind, ...extra },
  annotations: [],
});

describe("filters", () => {
  it("groups a run's results", () => {
    expect(groupOf(item("detected", { succeeded: true }), "production")).toBe("succeeded");
    expect(groupOf(item("pending", { waiting: true }), "production")).toBe("unfinished");
  });

  it("counts the groups, an excluded image apart in what training gets", () => {
    expect(
      groupCounts([item("failed"), item("result"), item("excluded", {}, true)], "production"),
    ).toEqual([
      ["result", 1],
      ["failed", 1],
      ["excluded", 1],
    ]);
  });
});
