import { describe, expect, it } from "vite-plus/test";
import { leftOutBy } from "../pickNames";

const files = ["L_001.png", "L_002.png", "L_011.png", "S3_001.png"].map((name) => ({
  path: `/d/${name}`,
  name,
}));

describe("pickNames", () => {
  it("chooses by names or their start, the rest left out (found 2026-10-05: 20 of 100 ticked one by one)", () => {
    expect(leftOutBy(files, "L_001, L_011\nS3_")).toEqual(new Set(["/d/L_002.png"]));
    expect(leftOutBy(files, "  ")).toBeNull();
  });
});
