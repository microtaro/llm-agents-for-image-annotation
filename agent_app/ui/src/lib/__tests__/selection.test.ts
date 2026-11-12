import { describe, expect, it } from "vite-plus/test";
import type { GalleryItem } from "@/api/types";
import {
  annotated,
  annotatedAfter,
  budgetWords,
  runSplit,
  shownWhich,
  usedAfter,
} from "../selection";

const item = (id: string, badge: GalleryItem["badge"]): GalleryItem => ({
  image: { id, name: id, width: 1, height: 1, origin: "real", source_path: null, excluded: false },
  badge,
  annotations: [],
});

describe("choosing images, then a button (types design 17.4)", () => {
  it("counts for each button only the chosen images it works on", () => {
    const items = [
      item("a", { kind: "result", picked: true }),
      item("b", { kind: "excluded", ran: true }),
      item("c", { kind: "no_result" }),
      item("d", { kind: "result" }),
    ];
    // Choosing what training uses shows only the annotated ones (user 2026-10-13).
    expect(items.filter(annotated).map((i) => i.image.id)).toEqual(["a", "b", "d"]);
    // The bars say the total after a press, of all the images (user 2026-10-16).
    expect(annotatedAfter(items, ["c"])).toBe(4);
    // Made by an earlier plan's criteria: done only once made again (2026-10-30: the bar said
    // "done 4/4" running 2 of the 4 by the new criteria).
    const earlier = items.map((i) => ({ ...i, badge: { ...i.badge, other: true } }));
    expect(annotatedAfter(earlier, ["a", "c"])).toBe(2);
    expect(usedAfter(items, ["b"], true)).toBe(3);
    expect(usedAfter(items, ["a", "d"], false)).toBe(0);
    // A limit per image is said in all too (user 2026-10-28: $0.50 an image, 50 images).
    expect(budgetWords("0.5", 50)).toEqual({ budget: "0.50", total: "25.00" });
  });
});

describe("annotating again (user 2026-10-14)", () => {
  it("splits new from again", () => {
    const items = [
      item("a", { kind: "no_result" }),
      item("b", { kind: "result" }),
      item("c", { kind: "result", by: "human", picked: true }),
      item("d", { kind: "excluded", ran: true }),
    ];
    expect(runSplit(items, ["a", "b", "c", "d"])).toEqual({ fresh: 1, again: 3 });
  });
});

describe("which images the bars work on (user 2026-10-27)", () => {
  it("says them by what narrows them, and the shown when more than one does", () => {
    expect(shownWhich(50, {})).toBe("全部の 50枚");
    expect(shownWhich(46, { state: "no_result" })).toBe("まだ結果なし の 46枚");
    expect(shownWhich(3, { found: true })).toBe("探した 3枚");
    expect(shownWhich(2, { state: "no_result", found: true })).toBe("表示中の 2枚");
    expect(shownWhich(5, { targets: true })).toBe("表示中の 5枚");
    expect(shownWhich(31, {}, true)).toBe("全部の 31件");
    expect(shownWhich(2, { found: true }, true)).toBe("探した 2件");
  });
});
