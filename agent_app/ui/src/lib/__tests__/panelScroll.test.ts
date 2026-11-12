import { describe, expect, it } from "vite-plus/test";
import { nearestTop } from "../panelScroll";

describe("nearestTop", () => {
  it("moves the side only as far as the line needs", () => {
    // 2026-11-05: choosing an object in a narrow window scrolled the whole page.
    const panel = { top: 100, bottom: 500 };
    expect(nearestTop(40, { top: 200, bottom: 230 }, panel)).toBe(40);
    expect(nearestTop(40, { top: 480, bottom: 530 }, panel)).toBe(70);
    expect(nearestTop(40, { top: 80, bottom: 110 }, panel)).toBe(20);
  });
});
