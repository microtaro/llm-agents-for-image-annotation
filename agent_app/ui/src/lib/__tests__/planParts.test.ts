import { describe, expect, it } from "vite-plus/test";
import type { Run } from "@/api/types";
import { planChoice, newestTrial, planChoices, planOfChoice } from "../planParts";

describe("the plans a screen can be looked at by (definition 56)", () => {
  // User 2026-10-27: which version the plan was was not said, and an earlier one could not be
  // looked at.
  const versions = [
    { revision: 3, created_at: "2026-10-23T07:29:00Z" },
    { revision: 2, created_at: "2026-10-23T07:07:00Z" },
  ];
  it("puts the plan now first and says each version once", () => {
    const draft = planChoices({ write: 20 }, versions);
    expect(draft.map((c) => c.value)).toEqual(["", "revision=3", "revision=2"]);
    expect(draft[0].label).toContain("3");
    // No draft: the newest version is the plan now, not said twice.
    expect(planChoices({ revision: 3 }, versions).map((c) => c.value)).toEqual(["", "revision=2"]);
    // No plan begun: nothing to choose.
    expect(planChoices({ blank: true }, versions)).toEqual([]);
  });
  it("goes between a choice and the plan looked at", () => {
    expect(planChoice({ revision: 3 }, { revision: 3 })).toBe("");
    expect(planChoice({ write: 20 }, { revision: 2 })).toBe("revision=2");
    expect(planOfChoice("revision=2")).toEqual({ revision: 2 });
    expect(planOfChoice("")).toBeNull();
  });
});

describe("the samples the plan's screen shows (user 2026-10-27)", () => {
  it("are the newest, whatever version made them, the ones going first", () => {
    const run = (id: string, trial: boolean, revision: number) =>
      ({ id, trial, instruction_revision: revision }) as unknown as Run;
    // Newest first: a run of version 2 (not samples), the samples of version 1, older samples.
    const runs = [run("r3", false, 2), run("r2", true, 1), run("r1", true, 1)];
    expect(newestTrial(runs, null)?.id).toBe("r2");
    expect(newestTrial(runs, "r1")?.id).toBe("r1");
    expect(newestTrial([run("r3", false, 2)], null)).toBeUndefined();
  });
});
