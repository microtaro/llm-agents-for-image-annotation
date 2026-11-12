import { describe, expect, it } from "vite-plus/test";
import type { RunCard } from "@/api/types";
import { typedChoice, runCardView, runLine } from "../cardView";

const usage = (runs: number, adopted: number) => ({
  runs,
  trials: runs,
  images: runs,
  trial_images: runs,
  succeeded: runs,
  failed: 0,
  adopted,
  fixed: 0,
});

const trial: RunCard = {
  decision: "run_trial",
  weight: "light",
  fixes: {
    plan: { kind: "write", write_id: 71, revision: null, next_revision: 1 },
    model: "m",
    effort: "medium",
    against: null,
    changes: null,
  },
  happens: {
    images: 2,
    new: 2,
    redo: 0,
    replaces: [],
    kept: [],
    used_after: ["a", "b"],
    other: { images: 0, in_run: 0 },
    estimate_usd: "0.1316",
    estimate_from: [{ dataset_id: "d", name: "前の棚" }],
    budget_per_image_usd: "1",
  },
  grounds: {
    way: null,
    version: null,
    line: {
      origin: { kind: "version", dataset_id: "d", revision: 3, name: "前の棚" },
      origin_usage: usage(2, 2),
    },
    trials: [],
  },
  blanks: ["first_run", "not_tried"],
};

const view = (card: RunCard) => runCardView(card, ["a", "b"], (model) => model.toUpperCase());

describe("a run's card as a figure", () => {
  it("names what is used and tags that a trial's success is used for training", () => {
    // Astra 2026-10-17: a trial's card did not say its results become what training uses;
    // user 2026-10-17: things by name or number, the counts as tags, nothing known as "—".
    const found = view(trial);
    expect(found.plan).toEqual(["card.plan.new", { next: 1 }]);
    expect(found.against).toBeNull();
    expect(found.tags).toContainEqual(["card.tag.usedTrial", { count: 2 }]);
    expect(found.tags).toContainEqual(["card.tag.costFrom", { usd: "0.13", name: "前の棚" }]);
    expect(found.uses.map((row) => [row.label[0], row.usage?.runs ?? null])).toEqual([
      ["card.use.wayNew", null],
      ["card.use.origin", 2],
    ]);
    expect(found.heavy).toBe(false);
  });

  it("names the record a run is compared with by its number", () => {
    const rest: RunCard = {
      ...trial,
      decision: "run",
      weight: "heavy",
      fixes: {
        ...trial.fixes,
        plan: { kind: "version", revision: 1, next_revision: null },
        against: { revision: 1, model: "m", effort: "medium", run_number: 3 },
      },
      grounds: {
        way: usage(1, 2),
        version: usage(1, 2),
        line: {},
        trials: [{ image_id: "a", name: "a.png", status: "detected", result_id: "r" }],
      },
      blanks: [],
    };
    const found = view(rest);
    expect(found.against?.said).toEqual(["card.against.same", { run: 3 }]);
    expect(found.uses[0].label).toEqual([
      "card.use.way",
      { revision: 1, model: "M", effort: "medium", shared: "?" },
    ]);
    expect(found.trials).toEqual([{ id: "a", name: "a.png", status: "detected" }]);
    expect(found.heavy).toBe(true);
  });
});

describe("an answer typed in the talk", () => {
  it("chooses an option only when it is the number alone", () => {
    expect([
      typedChoice("1"),
      typedChoice(" ２ "),
      typedChoice("1."),
      typedChoice("1枚で"),
      typedChoice("10"),
    ]).toEqual([1, 2, 1, null, null]);
  });
});

describe("a run in one line", () => {
  it("says the plan, the model by its name, the cost and the limit (user 2026-10-27: the confirm said none of them)", () => {
    const line = runLine(view(trial));
    expect(line).toContain("M · medium");
    // The plan, the model and effort, the cost and the limit.
    expect(line.split(" · ").length).toBeGreaterThanOrEqual(4);
  });
});
