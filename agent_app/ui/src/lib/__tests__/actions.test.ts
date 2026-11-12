import { describe, expect, it } from "vite-plus/test";
import type { Run } from "@/api/types";
import { actionPath, againBody, runActions, type TypeActions } from "../actions";

const all: TypeActions = {
  run: {
    where: [],
    actions: ["stop", "use"].map((name) => ({
      name,
      decision_tool: null,
      method: "POST",
      path: `/v1/runs/{id}/${name}`,
    })),
  },
};
const run = (over: Partial<Run>) =>
  ({ status: "succeeded", going: false, usable: true, succeeded: 2, ...over }) as Run;

describe("a run's buttons from the types' actions (types design 8)", () => {
  it("offers what fits the run now", () => {
    // Its images use its results (definition 19.5).
    expect(runActions(all, run({})).map((a) => a.name)).toEqual(["use"]);
    expect(
      runActions(all, run({ status: "running", going: true, usable: false })).map((a) => a.name),
    ).toEqual(["stop"]);
    expect(runActions(all, run({ status: "stopping", going: true, usable: false }))).toEqual([]);
    // A person's fix is a record, not a run (definition 21.4).
    expect(runActions(all, run({ kind: "fix" }))).toEqual([]);
    // An earlier requirement's record is not offered for training (Sol 2026-10-14): as the
    // server says.
    expect(runActions(all, run({ usable: false, earlier: true }))).toEqual([]);
    expect(actionPath(all.run!.actions[0], "d", "r1")).toBe("/v1/runs/r1/stop");
  });
});

describe("an image run again (definition 11.1)", () => {
  // 2026-10-30 review: only the model went, so a failure of version 1 ran by the plan now.
  it("runs by the record's own plan and shared notes", () => {
    const record = run({
      instruction_revision: 1,
      trial: true,
      settings: { model: "m", effort: "low", shared_revision: 2 },
    });
    expect(againBody(record, "i")).toMatchObject({
      image_ids: ["i"],
      revision: 1,
      shared_revision: 2,
      trial: true,
      model: "m",
    });
    // An early trial of a draft has no version to run again by.
    expect(againBody(run({ instruction_revision: 0, settings: {} }), "i")).toBeNull();
  });
});
