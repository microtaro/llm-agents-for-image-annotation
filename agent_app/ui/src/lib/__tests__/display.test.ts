import { describe, expect, it } from "vite-plus/test";
import { CARD, inkOn, labelCounts, ratioStep, valueAt } from "../display";

describe("inkOn", () => {
  it("writes dark on a light label color and white on a dark one", () => {
    expect(inkOn("#ffe119")).toBe("#1b1f24");
    expect(inkOn("#42d4f4")).toBe("#1b1f24");
    expect(inkOn("#4363d8")).toBe("#ffffff");
    expect(inkOn("#c0392b")).toBe("#ffffff");
    // Sol 2026-10-12: white on the palette's orange was 2.6:1.
    expect(inkOn("#f58231")).toBe("#1b1f24");
  });
});

describe("the card size's slider", () => {
  it("is even in ratio, so the start size is near a quarter, not at the left end", () => {
    // User 2026-10-07: on an even slider, 220px of 120-1600 sat at the left end.
    expect(ratioStep(CARD.initial, CARD)).toBe(23);
    expect(valueAt(ratioStep(CARD.initial, CARD), CARD)).toBe(CARD.initial);
    expect([valueAt(0, CARD), valueAt(100, CARD)]).toEqual([CARD.min, CARD.max]);
  });
});

describe("labelCounts", () => {
  it("counts in the labels' one order, not as they come", () => {
    // Astra 2026-10-07: the colors, the counts and the table each had their own order.
    const shown = [
      { label: "見出し" },
      { label: "図" },
      { label: "見出し" },
      { label: "キャプション" },
    ];
    const order = ["キャプション", "図", "見出し"].sort((a, b) => a.localeCompare(b));
    expect(labelCounts(shown)).toBe(order.map((l) => `${l} ${l === "見出し" ? 2 : 1}`).join(" · "));
  });
});
