import { describe, expect, it } from "vite-plus/test";
import { secondsSince, toolName } from "../elapsed";

describe("elapsed", () => {
  it("counts whole seconds since an answer was asked for, never below 0", () => {
    // User 2026-10-22: a spinner alone did not say how long the worker had been at it.
    const asked = "2026-10-22T03:00:00.000Z";
    expect(secondsSince(asked, Date.parse("2026-10-22T03:00:18.900Z"))).toBe(18);
    expect(secondsSince(asked, Date.parse("2026-10-22T02:59:59.000Z"))).toBe(0);
  });
});

describe("a tool call in words", () => {
  it("says the type a call reads or looks at (definition 51.6: one read tool for every type)", () => {
    expect(toolName("read:version")).toBe("計画書の版を読む");
    expect(toolName("look:dataset", { page: 2 })).toBe("データセットを見る（2ページ目）");
    expect(toolName("draft_write")).toBe("計画書の下書きを書く");
  });
});
