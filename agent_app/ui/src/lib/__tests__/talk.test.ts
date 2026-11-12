import { describe, expect, it } from "vite-plus/test";
import type { AgentEvent, Proposal, Shown } from "@/api/types";
import {
  afterOf,
  boxesOn,
  onRight,
  planAbout,
  rightOf,
  rightOfBox,
  rightOfShown,
  type RightNow,
  runParts,
  withdrawnWhy,
  targetsOf,
  runEndCarded,
  toldByCard,
  historyWords,
  questionText,
} from "../talk";

function box(over: Partial<Proposal>): Proposal {
  return {
    id: "p1",
    dataset_id: "d",
    bot: "production",
    agent: "steward",
    tool: "run_start",
    args: {},
    title: "t",
    reason: "r",
    made_by: "ai",
    state: "open",
    waiting: true,
    trouble: false,
    decided: false,
    created_at: "",
    decided_at: null,
    decided_by: null,
    outcome: null,
    stage: "production",
    ...over,
  };
}

describe("talk", () => {
  it("puts a box on the map's place it changes, whoever made it", () => {
    // User 2026-10-09: a run is a box of Apply's place, a trial of the plan's, whoever made it.
    const boxes = [box({ id: "a", agent: "steward" }), box({ id: "b", stage: "instruction" })];
    expect(boxesOn(boxes, "production").map((p) => p.id)).toEqual(["a"]);
    expect(boxesOn(boxes, "instruction").map((p) => p.id)).toEqual(["b"]);
    const decided = box({ id: "c", state: "withdrawn", waiting: false });
    expect(boxesOn([decided, box({ id: "d" })], "production").map((p) => p.id)).toEqual(["d"]);
  });

  it("says what follows a run on Haiku 5.5 and which images it is for", () => {
    const run = box({
      args: { image_ids: ["i1", "i2"], model: "claude-haiku-5-5" },
      preview: { warning: "haiku_accuracy", estimate_usd: "0.04" },
    });
    expect(targetsOf(run)).toEqual(["i1", "i2"]);
    expect(afterOf(run).map(([key]) => key)).toEqual([
      "band.after.images",
      "band.after.model",
      "band.after.cost",
      "band.after.then.run",
    ]);
  });

  it("says which record went first when a waiting box was withdrawn", () => {
    // User 2026-10-17: the box asked for a remake and did not say why; the first decided wins
    // and the box says what went first, by name and number (definition 18.13).
    const cause = {
      kind: "results",
      images: [{ name: "A006.png", record_number: 3, going: true }],
    };
    expect(withdrawnWhy({ withdrawn: "changed", cause })).toEqual([
      "withdrawn.cause.results",
      { images: "A006.png を記録 3 で先にアノテーションすると決めた" },
    ]);
    expect(withdrawnWhy({ withdrawn: "changed", cause: { kind: "plan" } })).toEqual([
      "withdrawn.cause.plan",
      {},
    ]);
  });

  it("says what training gets before and after leaving an image out", () => {
    // User 2026-10-09: "details" meant nothing; the band itself says it.
    const mark = box({
      tool: "mark",
      args: { target: "image", image_id: "i1", excluded: true },
      preview: { adopted_now: 8, adopted_after: 7 },
    });
    expect(afterOf(mark)).toContainEqual(["band.after.adopted", { now: 8, after: 7 }]);
  });

  it("says a dataset made of others carries no plan unless asked (the reception's test R02)", () => {
    const from = box({
      tool: "dataset_from",
      dataset_id: null,
      preview: { name: "R02", sources: [], images: 4, instruction: false },
    });
    expect(afterOf(from).map(([key]) => key)).toContain("band.after.from.noplan");
  });

  it("says the existing plans not among the options are on the right (2026-10-29: 4 said, 3 shown)", () => {
    const asked = {
      id: 1,
      kind: "question",
      text: "Which existing plan is used?",
      data: { entry: { step: "which", count: 4, shown: 3 } },
    } as unknown as AgentEvent;
    expect(questionText(asked)).toContain("全部の 4つは右に");
  });

  it("tells a run's images apart by how they went", () => {
    const badges = [
      { kind: "detected", succeeded: true, waiting: false },
      { kind: "failed", succeeded: false, waiting: false },
      { kind: "running", succeeded: false, waiting: true },
      { kind: "pending", succeeded: false, waiting: true },
    ];
    expect(runParts(badges, 5)).toEqual({
      succeeded: 1,
      failed: 1,
      working: 1,
      waiting: 2,
    });
  });
});

describe("the right follows the talk", () => {
  it("shows the thing a line is about, judged by the plan it is about (definition 35.4, 36.1)", () => {
    // User 2026-10-22: answering the plan's questions, the right stayed on "use for training";
    // making another plan, the right judged the images by the latest version.
    const line = (kind: AgentEvent["kind"], data: Record<string, unknown>) =>
      ({ id: 1, kind, data }) as unknown as AgentEvent;
    const trial = box({
      id: "t",
      stage: "instruction",
      step: "trial",
      args: { trial: true, draft_write_id: 7 },
    });
    const run = box({ id: "r", step: "run", args: { revision: 4 } });
    const use = box({ id: "u", tool: "mark", step: "drop", args: { revision: 4 } });
    const boxOf = (id: string) => [trial, run, use].find((b) => b.id === id);
    const runOf = (id: string) =>
      id === "run-t" ? { trial: true, revision: 5 } : { trial: false, revision: 4 };
    const question = line("question", {
      item: "requirement",
      premise: { write_id: 7, revision: 4 },
    });
    expect(rightOf(question, boxOf, runOf)).toEqual({
      stage: "instruction",
      plan: { write: 7 },
      about: { line: 1 },
    });
    expect(rightOf(line("ai", { proposal_ids: ["t"] }), boxOf, runOf)).toEqual({
      stage: "instruction",
      plan: { write: 7 },
      about: { box: "t" },
    });
    // A run is annotating with AI's, in its band, before it is decided and while it goes
    // (definition 37, user 2026-10-23: a run went to the progress, apart from its screen).
    expect(rightOf(line("ai", { proposal_ids: ["r"] }), boxOf, runOf)).toEqual({
      stage: "production",
      screen: "annotate",
      plan: { revision: 4 },
      box: "r",
    });
    // What a line showed is the steward's choice of the right, before a box it points to (decided
    // in the line itself; definition 37.4: talking of a sample with the trial pointed to, the
    // right showed the trial).
    const asked = { type: "label", id: "lab-1", where: {}, count: 1, title: "" };
    expect(rightOf(line("ai", { proposal_ids: ["t"], show: asked }), boxOf, runOf)).toEqual({
      stage: "instruction",
      plan: null,
      about: { line: 1 },
    });
    expect(rightOf(line("ai", { proposal_ids: ["u"] }), boxOf, runOf)).toEqual({
      stage: "production",
      screen: "use",
      plan: { revision: 4 },
      box: "u",
    });
    const shownTrial = { type: "result", id: null, where: { run: "run-t" }, count: 3, title: "" };
    expect(rightOf(line("ai", { show: shownTrial }), boxOf, runOf)).toEqual({
      stage: "instruction",
      plan: { revision: 5 },
      about: null,
      recordId: "run-t",
    });
    expect(
      rightOf(line("note", { note: "run_ended", trial: false, revision: 4 }), boxOf, runOf),
    ).toEqual({ stage: "production", screen: "annotate", plan: { revision: 4 } });
    expect(rightOf(line("human", {}), boxOf, runOf)).toBeNull();
    // A box shown is the box (its place, the plan it runs).
    const shownBox = { type: "proposal", id: "t", where: {}, count: 1, title: "" };
    expect(rightOf(line("ai", { show: shownBox }), boxOf, runOf)).toEqual({
      stage: "instruction",
      plan: { write: 7 },
      about: { box: "t" },
    });
    // A set of images is shown on its type's screen; its conditions name its plan.
    const images = { type: "image", id: null, where: { write: 7 }, count: 3, title: "" };
    expect(rightOf(line("ai", { show: images }), boxOf, runOf)).toEqual({ objects: images });
  });

  it("goes by the same computation for a line's see and for what the plan's screen shows", () => {
    // User 2026-10-23: the see of a label went straight to a table of one row, while the talk's
    // right was the plan's screen comparing it; the plan's screen chose its own way too.
    const line = (id: number, kind: AgentEvent["kind"], data: Record<string, unknown>) =>
      ({ id, kind, data }) as unknown as AgentEvent;
    const trial = box({ id: "t", stage: "instruction", step: "trial", args: { trial: true } });
    const boxOf = (id: string) => [trial].find((b) => b.id === id);
    const runOf = () => undefined;
    const label: Shown = { type: "label", id: "lbl-1", where: {}, count: 1, title: "" };
    expect(rightOfShown(label, 3, boxOf, runOf)).toEqual({
      stage: "instruction",
      plan: null,
      about: { line: 3 },
    });
    const images = { type: "image", id: null, where: {}, count: 3, title: "" };
    const lines = [
      line(1, "ai", { proposal_ids: ["t"] }),
      line(2, "ai", { show: label, proposal_ids: ["t"] }),
      line(3, "ai", { show: images }),
    ];
    // The newest line of the plan's screen (images are their type's screen): its label.
    expect(planAbout(lines, null, boxOf, runOf)).toEqual({ line: 2 });
    expect(planAbout(lines.slice(0, 1), null, boxOf, runOf)).toEqual({ box: "t" });
    // What the right was sent to wins.
    expect(planAbout(lines, { box: "t" }, boxOf, runOf)).toEqual({ box: "t" });
  });

  it("tells whether the right shows a line's thing or a box already (definition 37.5)", () => {
    // User 2026-10-23: the see of what the right showed already changed nothing; it should be
    // pressed only for what the right does not show.
    const trial = box({ id: "t", stage: "instruction", step: "trial", args: { trial: true } });
    const run = box({ id: "r", step: "run", args: { revision: 4 } });
    const boxOf = (id: string) => [trial, run].find((b) => b.id === id);
    const runOf = () => undefined;
    const label: Shown = { type: "label", id: "lbl-1", where: {}, count: 1, title: "" };
    const other: Shown = { type: "label", id: "lbl-2", where: {}, count: 1, title: "" };
    const said = (id: number, show: Shown) =>
      ({ id, kind: "ai", data: { show } }) as unknown as AgentEvent;
    const plan: RightNow = {
      screen: "gallery",
      stage: "instruction",
      purpose: "annotate",
      recordId: null,
      imageId: null,
      plan: "write=7",
      about: { line: 29 },
      lines: [said(27, label), said(28, other), said(29, label)],
      objects: null,
      boxes: [],
      viewed: null,
    };
    const now = { write: 7 };
    expect(onRight(rightOfShown(label, 29, boxOf, runOf)!, plan, now)).toBe(true);
    // The same set shown from another line is the same thing on the right.
    expect(onRight(rightOfShown(label, 27, boxOf, runOf)!, plan, now)).toBe(true);
    expect(onRight(rightOfShown(other, 28, boxOf, runOf)!, plan, now)).toBe(false);
    expect(onRight(rightOfBox(trial)!, plan, now)).toBe(false);
    const apply: RightNow = { ...plan, stage: "production", plan: "revision=4", about: null };
    expect(onRight(rightOfBox(run)!, apply, now)).toBe(false);
    expect(onRight(rightOfBox(run)!, { ...apply, boxes: ["r"] }, now)).toBe(true);
  });

  it("opens one image or result the steward named in the loupe (definition 59.2)", () => {
    // 2026-10-28: one result named showed a table of one row, one image a set of one card; each
    // opens large, as its card and its row open it, and the line knows the loupe shows it.
    const boxOf = () => undefined;
    const runOf = () => undefined;
    const image: Shown = {
      type: "image",
      id: "img-a",
      image_id: "img-a",
      where: { revision: 4 },
      count: 1,
      title: "",
    };
    expect(rightOfShown(image, 1, boxOf, runOf)).toEqual({
      loupe: { imageId: "img-a", stage: "production", recordId: null, plan: { revision: 4 } },
    });
    const result: Shown = {
      type: "result",
      id: "res-1",
      image_id: "img-a",
      record: { id: "run-3", trial: true, revision: 2 },
      where: {},
      count: 1,
      title: "",
    };
    const target = rightOfShown(result, 2, boxOf, runOf)!;
    expect(target).toEqual({
      loupe: { imageId: "img-a", stage: "instruction", recordId: "run-3", plan: { revision: 2 } },
    });
    const loupe: RightNow = {
      screen: "loupe",
      stage: "instruction",
      purpose: "annotate",
      recordId: "run-3",
      imageId: "img-a",
      plan: "revision=2",
      about: null,
      lines: [],
      objects: null,
      boxes: [],
      viewed: null,
    };
    expect(onRight(target, loupe, null)).toBe(true);
    expect(onRight(target, { ...loupe, imageId: "img-b" }, null)).toBe(false);
  });

  it("opens a decided box as the record it made, by the version it ran", () => {
    // 2026-10-27: a decided trial kept its write, and the plan's screen took it for an
    // earlier plan (the samples left the top); "see on the right" and "see the record" were the
    // same, and an old trial's showed the newest samples.
    const trial = {
      id: "t",
      stage: "instruction",
      tool: "run_start",
      args: { trial: true, draft_write_id: 30 },
      preview: { plan: { kind: "write", revision: null, next_revision: 1 } },
      state: "open",
      waiting: true,
      outcome: null,
    } as unknown as Proposal;
    expect(rightOfBox(trial)).toMatchObject({ plan: { write: 30 } });
    const decided = {
      ...trial,
      state: "applied",
      waiting: false,
      decided: true,
      outcome: { id: "r1", revision: 1 },
    } as Proposal;
    expect(rightOfBox(decided)).toEqual({
      stage: "instruction",
      plan: { revision: 1 },
      about: null,
      recordId: "r1",
    });
  });
});

describe("a box's outcome said once (user 2026-10-27)", () => {
  it("leaves the line out where the box's card is in the talk, and keeps it elsewhere", () => {
    const note = (name: string) =>
      ({ id: 9, kind: "note", data: { note: name, proposal_id: "b1" } }) as unknown as AgentEvent;
    const carded = new Map([["b1", 3]]);
    expect(toldByCard(note("box_applied"), carded)).toBe(true);
    expect(toldByCard(note("box_withdrawn"), carded)).toBe(true);
    expect(toldByCard(note("box_made"), carded)).toBe(false);
    expect(toldByCard(note("box_applied"), new Map())).toBe(false);
  });

  it("gives a run's end no see of its own where its box's card is in the talk", () => {
    // 2026-10-28: a trial's end had "show on the right" just under its card's, to one record.
    const ended = { id: 9, kind: "note", data: { note: "run_ended", run_id: "r1" } };
    const box = { id: "b1", outcome: { id: "r1" } } as unknown as Proposal;
    const boxOf = (id: string) => (id === "b1" ? box : undefined);
    const line = ended as unknown as AgentEvent;
    expect(runEndCarded(line, new Map([["b1", 3]]), boxOf)).toBe(true);
    expect(runEndCarded(line, new Map(), boxOf)).toBe(false);
  });
});

describe("historyWords", () => {
  it("counts the chats besides the one open", () => {
    // 2026-10-28: a new dataset's only chat said "履歴（1）", counting itself.
    expect(historyWords([{ id: 7 }], 7)).toBe("履歴");
    expect(historyWords([{ id: 7 }, { id: 5 }], 7)).toBe("履歴（1）");
  });
});
