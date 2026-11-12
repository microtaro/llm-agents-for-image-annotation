import { describe, expect, it } from "vite-plus/test";
import { isAppWindow } from "../appWindow";

describe("the app's own window", () => {
  it("is the page the launcher opened with ?window=app (2026-10-30: it said the app quit, and stayed)", () => {
    expect(isAppWindow("?window=app")).toBe(true);
    expect(isAppWindow("")).toBe(false);
  });
});
