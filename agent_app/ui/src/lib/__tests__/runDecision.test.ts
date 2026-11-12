import { describe, expect, it } from "vite-plus/test";
import type { Proposal } from "@/api/types";
import { changesOf, openRunBox, runImages } from "../runDecision";
import { changedText } from "../work";

const box = (id: string, state: string, stage: string, args: Record<string, unknown>) =>
  ({
    id,
    state,
    waiting: state === "open",
    stage,
    tool: "run_start",
    args,
    preview: {},
  }) as unknown as Proposal;

describe("the run being decided on annotating with AI", () => {
  it("is the steward's waiting run, its rings its images with the person's changes", () => {
    // User 2026-10-23: the steward's 47 images had no rings, the person's choice had (40.2).
    const waiting = box("p2", "open", "production", { image_ids: ["a", "b", "c"] });
    const found = openRunBox([
      box("p0", "applied", "production", { image_ids: ["x"] }),
      box("p1", "open", "instruction", { image_ids: ["s"], trial: true }),
      waiting,
    ]);
    expect(found?.id).toBe("p2");
    expect(runImages(found, {}, ["mine"])).toEqual(["a", "b", "c"]);
    expect(runImages(found, { image_ids: ["a", "c"] }, ["mine"])).toEqual(["a", "c"]);
    // None waiting: the person's own rings.
    expect(runImages(openRunBox([]), {}, ["mine"])).toEqual(["mine"]);
  });
});

describe("what the person changed on a waiting box", () => {
  it("is said as deciding records it (user 2026-10-27: the title said 44 with 2 chosen)", () => {
    const waiting = box("p", "open", "production", { image_ids: ["a", "b", "c"], model: "m" });
    expect(changesOf(waiting, { image_ids: ["a"], model: "m" })).toEqual({
      image_ids: [["a", "b", "c"], ["a"]],
    });
    expect(changedText(changesOf(waiting, { image_ids: ["a"] }), (model) => model ?? "")).toContain(
      "3",
    );
  });
});
