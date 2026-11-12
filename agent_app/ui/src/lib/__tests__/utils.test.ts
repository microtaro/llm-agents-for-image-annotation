import { describe, expect, it } from "vite-plus/test";
import { cn } from "../utils";

describe("cn", () => {
  it("keeps a text color beside a text step (user 2026-10-14: dark text on the purple)", () => {
    expect(cn("bg-action text-white", "text-body")).toBe("bg-action text-white text-body");
    expect(cn("text-small", "text-body")).toBe("text-body");
  });
});
