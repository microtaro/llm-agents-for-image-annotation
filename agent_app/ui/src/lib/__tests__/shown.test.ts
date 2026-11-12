import { describe, expect, it } from "vite-plus/test";
import type { GalleryItem } from "@/api/types";
import { orderImages, shownImages } from "../shown";
import { toggled } from "../viewState";

const item = (id: string, kind: string, color?: string) =>
  ({
    image: { id, name: `${id}.png` },
    badge: { kind, succeeded: kind === "detected" },
    annotations: color
      ? [
          {
            id: `${id}-1`,
            label: "box",
            geometry: { type: "bbox", xywh: [0, 0, 1, 1] },
            attributes: { color },
            parent_id: null,
            number: 1,
          },
        ]
      : [],
  }) as unknown as GalleryItem;

describe("shown images", () => {
  it("are the filtered cards, or the found rows' images, for picking and stepping (found 2026-10-06: all 20 were picked and stepped through)", () => {
    const items = [
      item("a", "detected", "red"),
      item("b", "failed"),
      item("c", "detected", "blue"),
    ];
    expect(shownImages(items, "production", null, null, "old", null)).toEqual(["a", "b", "c"]);
    expect(shownImages(items, "production", "succeeded", null, "old", null)).toEqual(["a", "c"]);
    expect(
      shownImages(items, "production", "succeeded", { text: "blue", mode: "all" }, "old", null),
    ).toEqual(["c"]);
    expect(toggled(["a"], "c", true)).toEqual(["a", "c"]);
    expect(toggled(["a", "c"], "a", false)).toEqual(["c"]);
  });

  it("follow the table's sort, so the loupe steps as the rows go (found 2026-10-06: next ignored a descending sort)", () => {
    const items = [
      item("a", "detected", "red"),
      item("b", "detected", "blue"),
      item("c", "detected", "green"),
    ];
    expect(
      shownImages(
        items,
        "production",
        null,
        { text: "", mode: "all", column: "image", up: false },
        "old",
        null,
      ),
    ).toEqual(["c", "b", "a"]);
  });
});

describe("image order", () => {
  it("orders as taken in, reversed, by name or by the newest annotation (user 2026-10-28)", () => {
    const at = (id: string, kind: string, when?: string) =>
      ({
        image: { id, name: `${id}.png` },
        badge: { kind, succeeded: kind === "detected", record_at: when },
      }) as GalleryItem;
    const items = [
      at("b10", "detected", "2026-10-28T01:00:00Z"),
      at("b2", "no_result"),
      at("b1", "detected", "2026-10-28T03:00:00Z"),
    ];
    const ids = (list: GalleryItem[]) => list.map((i) => i.image.id);
    expect(ids(orderImages(items, "old"))).toEqual(["b10", "b2", "b1"]);
    expect(ids(orderImages(items, "new"))).toEqual(["b1", "b2", "b10"]);
    expect(ids(orderImages(items, "name"))).toEqual(["b1", "b2", "b10"]);
    expect(ids(orderImages(items, "annotated"))).toEqual(["b1", "b10", "b2"]);
  });
});
