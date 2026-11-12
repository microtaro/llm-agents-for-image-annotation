import { describe, expect, it } from "vite-plus/test";
import { spentText, wayText } from "../runChoice";

describe("spentText", () => {
  // User 2026-10-27: the loupe's records said a result's cost but not how long it took.
  it("says a result's time and cost, each when known", () => {
    expect(spentText(20400, "0.0501986")).toBe("20s · $0.050");
    expect(spentText(20400, null)).toBe("20s");
    expect(spentText(null, "0.0501986")).toBe("$0.050");
    expect(spentText(null, null)).toBe("");
  });
});

describe("wayText", () => {
  // User 2026-10-27: the run's bar and the records said "claude-opus-5-5" where the box said
  // "Claude Opus 5.5"; every screen names a model by the one function.
  it("names the model by its name, and a person's fix as a person's", () => {
    const name = (model: string | null | undefined) =>
      model === "claude-opus-5-5" ? "Claude Opus 5.5" : (model ?? "");
    const run = {
      instruction_revision: 2,
      settings: { model: "claude-opus-5-5", effort: "medium" },
      kind: "run",
    } as unknown as Parameters<typeof wayText>[0];
    expect(wayText(run, name)).toContain("Claude Opus 5.5");
    expect(wayText({ ...run, kind: "fix" }, name)).not.toContain("Claude Opus 5.5");
  });
});
