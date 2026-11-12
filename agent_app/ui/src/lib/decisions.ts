// What a decision does, as the data it makes (types design 16.3.1, criterion S-M11): one row
// per image it touches, with the image's state now and after, and the decide button named by
// what it does ("take C006 out of training", "run 13 images") instead of "decide". Read from the box's
// own preview (box_facts.py), which the server makes when the box is made.
import type { AgentInfo, Proposal } from "@/api/types";
import { t } from "@/i18n";
import { calledName } from "./library";
import { planOfBox, targetsOf } from "./talk";
import { objectsOf, textOf } from "./values";

/** For t(): a key and its values. */
export type Said = [string, Record<string, string | number>];

/** Which views a decision shows: its images, its data, or both side by side. */
export interface Shown {
  image: boolean;
  data: boolean;
}

/** At first: a decision's images are the gallery's cards (as before). */
export const FIRST_SHOWN: Shown = { image: true, data: false };

/** Whether a decision's own view takes the place of the gallery's cards: a box shown with its
 * data (its image view is the cards). */
export function viewReplacesCards(boxed: boolean, shown: Shown): boolean {
  return boxed && shown.data;
}

export interface DecisionRow {
  imageId: string;
  /** The image's name as the box has it ("" when the box does not say: the screen's). */
  name: string;
  now: Said | null;
  after: Said;
}

type Listed = {
  id?: unknown;
  name?: unknown;
  result?: unknown;
  adopted?: unknown;
  now_run?: unknown;
  after_run?: unknown;
};

/** What training uses for an image now, before a run (adoption's source). */
function usedNow(image: Listed): Said {
  if (image.adopted === "result") return ["decision.now.result", {}];
  if (image.adopted === "excluded") return ["decision.now.out", {}];
  return image.result ? ["decision.now.resultUnused", {}] : ["decision.now.none", {}];
}

export function rowsOf(proposal: Proposal): DecisionRow[] {
  const preview = proposal.preview ?? {};
  const args = proposal.args;
  if (proposal.tool === "run_start") {
    const after: Said = preview.trial
      ? ["decision.after.trial", {}]
      : ["decision.after.result", {}];
    return objectsOf<Listed>(preview.images).map((image) => ({
      imageId: textOf(image.id),
      name: textOf(image.name),
      now: usedNow(image),
      after,
    }));
  }
  if (proposal.tool === "mark" && args.target === "run") {
    // A record's images that change: from the record they use to this one (definition 19.5).
    return objectsOf<Listed>(preview.rows).map((row) => ({
      imageId: textOf(row.id),
      name: textOf(row.name),
      now: row.now_run
        ? ["decision.now.record", { run: textOf(row.now_run) }]
        : ["decision.now.none", {}],
      after: ["decision.after.record", { run: textOf(row.after_run) }],
    }));
  }
  if (proposal.tool === "mark") {
    const image = (preview.image ?? null) as Listed | null;
    if (!image || !image.id) return [];
    const out = (on: unknown): Said => (on ? ["decision.now.out", {}] : ["decision.now.in", {}]);
    return [
      {
        imageId: textOf(image.id),
        name: textOf(image.name),
        now: out(preview.excluded_now),
        after: args.excluded ? ["decision.after.out", {}] : ["decision.after.in", {}],
      },
    ];
  }
  return [];
}

/** The decide button's words: what deciding does. nameOf: an image's name the box lacks. */
export function decideLabel(
  proposal: Pick<Proposal, "tool" | "args" | "preview">,
  nameOf: (id: string) => string | undefined,
): Said {
  const preview = proposal.preview ?? {};
  const args = proposal.args;
  const one = (id: string | undefined, fallback: string) =>
    (id && (nameOf(id) ?? objectsOf<Listed>(preview.images).find((i) => i.id === id)?.name)) ||
    fallback;
  if (proposal.tool === "run_start") {
    const targets = targetsOf(proposal);
    const trial = Boolean(preview.trial ?? args.trial);
    if (targets.length === 1) {
      const name = textOf(one(targets[0], ""));
      if (name) return [trial ? "decision.do.trialOne" : "decision.do.runOne", { name }];
    }
    return [trial ? "decision.do.trial" : "decision.do.run", { count: targets.length }];
  }
  if (proposal.tool === "mark") {
    const image = (preview.image ?? null) as Listed | null;
    const name = textOf(image?.name) || (image?.id ? textOf(nameOf(textOf(image.id))) : "");
    if (!name) return ["decision.do.inRun", { run: textOf(preview.run_number) || "?" }];
    return [args.excluded ? "decision.do.out" : "decision.do.in", { name }];
  }
  return dataLabel(proposal.tool, preview) ?? ["band.decide", {}];
}

/** The button of a decision of definition 22.2 other than a run and a mark: what it does, by
 * name. */
function dataLabel(tool: string, preview: Record<string, unknown>): Said | null {
  const name = (value: unknown) => textOf((value as { name?: string } | undefined)?.name);
  switch (tool) {
    case "run_stop":
      return ["decision.do.stop", { run: textOf(preview.run_number) }];
    case "pick":
      return preview.rule
        ? ["decision.do.pick.rule", { name: name(preview.image) }]
        : ["decision.do.pick", { name: name(preview.image), run: textOf(preview.after_run) }];
    case "confirm":
      return [
        "decision.do.confirm",
        { count: textOf(preview.images), revision: textOf(preview.revision) },
      ];
    case "carry": {
      // What is copied: the version's annotations (its dataset is in the box's words).
      const from = (preview.from ?? {}) as Record<string, unknown>;
      return [
        "decision.do.carry",
        { count: textOf(preview.images), revision: textOf(from.revision) },
      ];
    }
    case "dataset_add_images":
      return ["decision.do.add", { count: textOf(preview.found) }];
    case "dataset_remove_images":
      return ["decision.do.remove", { count: objectsOf<Listed>(preview.images).length }];
    case "label_rename":
      return ["decision.do.label", { from: textOf(preview.from), to: textOf(preview.to) }];
    case "label_change":
      return ["decision.do.label_change", { from: textOf(preview.from), to: textOf(preview.to) }];
    case "dataset_rename":
      return ["decision.do.rename", { to: textOf(preview.to) }];
    case "dataset_create":
    case "dataset_from":
      return ["decision.do.create", { name: textOf(preview.name) }];
    case "dataset_import":
      return ["decision.do.import", { count: objectsOf<Listed>(preview.datasets).length }];
    case "dataset_delete":
      return [
        "decision.do.delete",
        { name: calledName(preview.dataset as { number?: number; name: string }) },
      ];
    default:
      return null;
  }
}

/** The plan a run's box runs, by value (definition 11.4): a draft write (the version it makes)
 * or a version. A box from before the plan was held says what it said then. */
export function planSaid(proposal: Proposal): Said {
  const preview = proposal.preview ?? {};
  // Decided: the version it ran, or none (Sol 2026-10-17: a withdrawn box kept "version 3",
  // which another plan became).
  if (proposal.state === "applied") {
    // A box applied before the version it ran was kept says the one it foresaw (Astra
    // 2026-10-17: an applied box said "not run").
    const ran = (proposal.outcome ?? {}).revision ?? preview.revision;
    if (ran) return ["work.decision.revision", { revision: textOf(ran) }];
  } else if (!proposal.waiting) return ["work.decision.notRun", {}];
  const plan = (preview.plan ?? null) as Record<string, unknown> | null;
  if (!plan || !plan.kind) {
    if (preview.draft)
      return ["work.decision.revisionDraft", { revision: Number(preview.revision ?? 0) + 1 }];
    return preview.revision
      ? ["work.decision.revision", { revision: textOf(preview.revision) }]
      : ["work.decision.none", {}];
  }
  if (plan.kind === "write" && plan.next_revision)
    return ["work.decision.planDraft", { revision: textOf(plan.next_revision) }];
  if (plan.kind === "write") return ["work.decision.planSame", { revision: textOf(plan.revision) }];
  return ["work.decision.revision", { revision: textOf(plan.revision) }];
}

/** Whether a worker of the dataset is answering (its answer may write the plan): no run is
 * decided meanwhile (definition 11.10). */
export function workersAnswering(agents: AgentInfo[]): boolean {
  // Any worker bound to the dataset, whichever its role (definition 48.10).
  return agents.some((a) => (a.bound ?? 0) > 0);
}

type Changes = Record<string, unknown>;
const list = (value: unknown): string[] =>
  Array.isArray(value) ? value.map((v) => textOf(v)) : [];
const pair = (value: unknown): [string, string] | null =>
  Array.isArray(value) && value.length === 2 ? [textOf(value[0]), textOf(value[1])] : null;

/** What a plan says differently (the server's plan_changes), as lines for t() (definition 11.10):
 * the sentences added and taken out, the labels, what is left out, the references, the model
 * and effort. The one way a plan's changes are said: a decision, a record, a version, the right. */
export function planChangeText(changes: Changes | null, nameOf: (model: string) => string): string {
  return planChangeItems(changes, nameOf)
    .map(([key, values]) => t(key, values))
    .join(t("plan.diff.separator"));
}

/** What a plan says differently, as lines for t() (definition 11.10): the sentences added and
 * taken out, the labels, what is left out, the references, the model and effort. */
export function planChangeItems(
  changes: Changes | null,
  nameOf: (model: string) => string,
): Said[] {
  if (!changes) return [];
  const lines: Said[] = [];
  for (const sentence of list(changes.text_added))
    lines.push(["plan.diff.textAdded", { text: sentence }]);
  for (const sentence of list(changes.text_removed))
    lines.push(["plan.diff.textRemoved", { text: sentence }]);
  if (Number(changes.text_more) > 0)
    lines.push(["plan.diff.textMore", { count: Number(changes.text_more) }]);
  lines.push(...planPartItems(changes));
  const model = pair(changes.model);
  if (model) lines.push(["plan.diff.model", { from: nameOf(model[0]), to: nameOf(model[1]) }]);
  const effort = pair(changes.effort);
  if (effort) lines.push(["plan.diff.effort", { from: effort[0] || "—", to: effort[1] || "—" }]);
  // The shared notes for every worker AI are a part of the way (definition 18.15).
  const shared = pair(changes.shared);
  if (shared) lines.push(["plan.diff.shared", { from: shared[0], to: shared[1] }]);
  return lines;
}

/** What two plans say differently besides their text's sentences: the labels, what is left out,
 * the references (the version's and the draft's screens mark the sentences in the text). The
 * draft's whole difference and a box's short one say these alike. */
export function planPartItems(difference: object): Said[] {
  const changes = difference as Changes;
  const lines: Said[] = [];
  const labels: [string, string][] = [
    ["added", "plan.diff.labelsAdded"],
    ["removed", "plan.diff.labelsRemoved"],
    ["changed", "plan.diff.labelsChanged"],
    ["described", "plan.diff.labelsDescribed"],
  ];
  for (const [key, said] of labels)
    if (list(changes[key]).length) lines.push([said, { labels: list(changes[key]).join(", ") }]);
  // A label of the library renamed (2026-10-30: it said one label added and one removed).
  for (const renamed of Array.isArray(changes.renamed) ? changes.renamed : []) {
    const [from, to] = list(renamed);
    lines.push(["plan.diff.labelsRenamed", { from, to }]);
  }
  const leave = (changes.leave_out ?? {}) as Changes;
  if (list(leave.added).length)
    lines.push(["plan.diff.leaveAdded", { rules: list(leave.added).join(t("book.summary.join")) }]);
  if (list(leave.removed).length)
    lines.push([
      "plan.diff.leaveRemoved",
      { rules: list(leave.removed).join(t("book.summary.join")) },
    ]);
  const references = pair(changes.references);
  if (references && references[0] !== references[1])
    lines.push(["plan.diff.references", { from: references[0], to: references[1] }]);
  return lines;
}

/** What a run's box is compared with (definition 11.10): the way the dataset last ran, and
 * whether it runs the same; none when it ran before nothing. */
export function planAgainst(proposal: Proposal, nameOf: (model: string) => string): Said | null {
  const plan = (proposal.preview?.plan ?? null) as Changes | null;
  if (!plan || !plan.kind) return null;
  if (plan.first) return ["plan.diff.first", {}];
  const way = (plan.against ?? {}) as Changes;
  const values = {
    run: textOf(way.run_number) || "?",
    revision: textOf(way.revision),
    model: nameOf(textOf(way.model)),
    effort: textOf(way.effort) || "—",
  };
  return [plan.same_way ? "plan.diff.same" : "plan.diff.against", values];
}

/** The boxes seen waiting that were withdrawn since (the plan written
 * again, definition 11.10): said where the person looks, not only in the worker's talk (Sol
 * 2026-10-17: the box went as it was pressed, its reason only on the left). */
export function newlyWithdrawn(waiting: Set<string>, proposals: Proposal[]): Proposal[] {
  return proposals.filter((p) => p.state === "withdrawn" && waiting.has(p.id));
}

/** A plan opened to read: a version or a draft write. */
export interface PlanTarget {
  revision?: number;
  write?: number;
}

/** The plan a run's box runs, opened (talk.planOfBox). */
export function planToOpen(proposal: Parameters<typeof planOfBox>[0]): PlanTarget {
  const plan = planOfBox(proposal);
  return plan && !("blank" in plan) ? plan : {};
}
