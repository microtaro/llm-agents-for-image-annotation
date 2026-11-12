import { describe, expect, it } from "vite-plus/test";
import { problemOf } from "../settingsForm";

describe("settings numbers", () => {
  it("never takes an empty field as 0 (found 2026-10-05)", () => {
    expect(problemOf("retry_count", "", [0, 5])).toBe("empty");
    expect(problemOf("retry_count", "abc", [0, 5])).toBe("empty");
    expect(problemOf("target_timeout_seconds", "60.5", [60, 3600])).toBe("whole");
    expect(problemOf("usd_to_jpy", "1.5", [1, 1000])).toBeNull();
    expect(problemOf("retry_count", "9", [0, 5])).toBe("range");
    expect(problemOf("retry_count", "0", [0, 5])).toBeNull();
  });
});
