import { describe, expect, it } from "vite-plus/test";
import type { Proposal } from "@/api/types";
import type { AgentInfo } from "@/api/types";
import {
  decideLabel,
  planAgainst,
  newlyWithdrawn,
  planChangeItems,
  planSaid,
  planToOpen,
  rowsOf,
  workersAnswering,
} from "../decisions";
import { decidedBody } from "../propose";

const box = (tool: Proposal["tool"], args: Record<string, unknown>, preview = {}): Proposal =>
  ({ id: "p", tool, args, preview, state: "open", waiting: true }) as Proposal;

describe("decisions", () => {
  it("shows what each image becomes, and names the button by what deciding does", () => {
    const run = box(
      "run_start",
      { image_ids: ["a", "b"] },
      {
        images: [
          { id: "a", name: "C005.png", result: "succeeded", adopted: "result" },
          { id: "b", name: "C006.png", result: "succeeded", adopted: "none" },
        ],
      },
    );
    expect(rowsOf(run).map((r) => [r.name, r.now?.[0], r.after[0]])).toEqual([
      ["C005.png", "decision.now.result", "decision.after.result"],
      ["C006.png", "decision.now.resultUnused", "decision.after.result"],
    ]);
    expect(decideLabel(run, () => undefined)).toEqual(["decision.do.run", { count: 2 }]);

    const out = box(
      "mark",
      { target: "image", image_id: "a", excluded: true },
      { image: { id: "a", name: "C006.png" }, excluded_now: false },
    );
    expect(rowsOf(out).map((r) => [r.now?.[0], r.after[0]])).toEqual([
      ["decision.now.in", "decision.after.out"],
    ]);
    expect(decideLabel(out, () => undefined)).toEqual(["decision.do.out", { name: "C006.png" }]);
  });

  it("decides the plan the preview showed, and says when the draft moved on", () => {
    // Review problem 2 (10-16): the decision sent the body asked for, without the plan the
    // preview had made a value; a draft written in between ran in its place.
    const asked = {
      tool: "run_start" as const,
      args: { image_ids: ["a"], budget_per_image_usd: "1" },
      title: "t",
      reason: "r",
    };
    const shown = {
      ...asked.args,
      draft_write_id: 7,
      model: "claude-sonnet-5-5",
      effort: "medium",
    };
    expect(decidedBody(asked, shown, { budget_per_image_usd: "2" }).args).toEqual({
      ...shown,
      budget_per_image_usd: "2",
    });

    const fromDraft = box(
      "run_start",
      { draft_write_id: 7 },
      { plan: { kind: "write", write_id: 7, revision: null, next_revision: 3 } },
    );
    expect(planSaid(fromDraft)).toEqual(["work.decision.planDraft", { revision: "3" }]);

    const ofVersion = box("run_start", { revision: 2 }, { plan: { kind: "version", revision: 2 } });
    expect(planSaid(ofVersion)).toEqual(["work.decision.revision", { revision: "2" }]);

    // What it runs differently from the way last run (10-17: the content shown where it is
    // decided, not only its version's number; Sol could tell it only from the worker's words).
    const changed = box(
      "run_start",
      { draft_write_id: 7 },
      {
        plan: {
          kind: "write",
          against: { revision: 2, model: "m1", effort: "medium", run_number: 4 },
          same_way: false,
          changes: {
            text_added: ["確かめの印: 赤"],
            text_removed: ["確かめの印: 青"],
            added: [],
            removed: ["枠"],
            references: [0, 0],
            effort: ["medium", "high"],
          },
        },
      },
    );
    const name = (id: string) => ({ m1: "Sonnet" })[id] ?? id;
    expect(planAgainst(changed, name)).toEqual([
      "plan.diff.against",
      // Named by the record's number (user 2026-10-17: never "the last one").
      { run: "4", revision: "2", model: "Sonnet", effort: "medium" },
    ]);
    expect(
      planChangeItems(
        (changed.preview as { plan: { changes: Record<string, unknown> } }).plan.changes,
        name,
      ),
    ).toEqual([
      ["plan.diff.textAdded", { text: "確かめの印: 赤" }],
      ["plan.diff.textRemoved", { text: "確かめの印: 青" }],
      ["plan.diff.labelsRemoved", { labels: "枠" }],
      ["plan.diff.effort", { from: "medium", to: "high" }],
    ]);
    const same = box(
      "run_start",
      { revision: 2 },
      {
        plan: {
          kind: "version",
          same_way: true,
          against: { revision: 2, model: "m1", effort: "medium" },
        },
      },
    );
    expect(planAgainst(same, name)?.[0]).toBe("plan.diff.same");
    // No run is decided while a worker bound to the dataset answers, whichever its role (48.10:
    // the reception reading the dataset may write its plan too).
    const info = (agent: string, bound: number) => ({ agent, bound }) as AgentInfo;
    expect(workersAnswering([info("reception", 0), info("steward", 0)])).toBe(false);
    expect(workersAnswering([info("reception", 1), info("steward", 0)])).toBe(true);
  });

  it("says a box withdrawn where it was waiting, and opens the plan a box runs", () => {
    // Sol 2026-10-17: the box went as it was pressed, its reason only in the worker's talk.
    const gone = {
      ...box("run_start", { draft_write_id: 7 }),
      id: "a",
      state: "withdrawn",
      waiting: false,
    } as Proposal;
    const other = {
      ...box("run_start", {}),
      id: "b",
      state: "withdrawn",
      waiting: false,
    } as Proposal;
    expect(newlyWithdrawn(new Set(["a"]), [gone, other]).map((p) => p.id)).toEqual(["a"]);
    // A first run's box said only "first": its plan is opened from the box, as the box holds
    // it (Sol 2026-10-17: opened as the plan now, it changed under the reader).
    expect(
      planToOpen(box("run_start", { draft_write_id: 7 }, { plan: { kind: "write" } })),
    ).toEqual({
      write: 7,
    });
    expect(
      planToOpen(box("run_start", { draft_write_id: 7 }, { plan: { kind: "write", revision: 3 } })),
    ).toEqual({ revision: 3 });
    expect(
      planToOpen(box("run_start", { revision: 3 }, { plan: { kind: "version", revision: 3 } })),
    ).toEqual({
      revision: 3,
    });
  });

  it("says a decided box's version as it ran, none when it did not run", () => {
    // Sol 2026-10-17: a withdrawn box kept "version 3", which another plan became.
    const plan = { plan: { kind: "write", next_revision: 3 } };
    const ran = {
      ...box("run_start", { draft_write_id: 7 }, plan),
      state: "applied",
      waiting: false,
      decided: true,
      outcome: { revision: 4 },
    } as Proposal;
    const gone = {
      ...box("run_start", { draft_write_id: 7 }, plan),
      state: "withdrawn",
      waiting: false,
    } as Proposal;
    expect(planSaid(ran)).toEqual(["work.decision.revision", { revision: "4" }]);
    expect(planSaid(gone)).toEqual(["work.decision.notRun", {}]);
    // Astra 2026-10-17: a box applied before the version it ran was kept said "not run".
    const older = {
      ...box("run_start", { draft_write_id: 7 }, { ...plan, revision: 2 }),
      state: "applied",
      waiting: false,
      decided: true,
      outcome: { id: "r" },
    } as Proposal;
    expect(planSaid(older)).toEqual(["work.decision.revision", { revision: "2" }]);
  });
});
