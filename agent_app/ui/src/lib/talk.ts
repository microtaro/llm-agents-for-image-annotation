// The agent app's talk and decisions (docs/2026-10-09-agent-app-design.md 4): pure functions
// the left panel and the decision band share. Workers are loose (any one may make any box);
// a box is of the map's place by what it changes (its stage), its author is the worker that
// made it. The right (map and view) and the left (whom you talk with) are chosen apart.
import type {
  AgentEvent,
  AgentInfo,
  Badge,
  AgentKey,
  EntryStep,
  ObjectType,
  PastRequirement,
  Proposal,
  QuestionOption,
  Shown,
  StageName,
} from "@/api/types";
import { t } from "@/i18n";
import { calledName } from "@/lib/library";
import { basisWords, definitionsOf, summaryLine } from "./planParts";
import type { Purpose } from "./selection";
import { placeOfWorker } from "./home";
import { screenName, stageOf } from "./stages";
import {
  imageLoupe,
  type LoupeAt,
  type PlanRef,
  planOf,
  planQuery,
  resultLoupe,
  type Route,
  whereQuery,
} from "./route";
import { objectsOf, textOf } from "./values";

/** What the person looks at, sent with the words (the server keeps it on the line). */
export interface LookingAt {
  stage?: StageName;
  /** Apply's screen chosen on the right (definition 35.3). */
  screen?: Purpose;
  image_id?: string;
  image_name?: string;
  /** The loupe's images before and after it, as its ← → go (definition 59.3), by name. */
  previous_image?: string;
  next_image?: string;
  /** The images ticked on the cards, by name. */
  picked?: string[];
  /** The worker whose talk the person came from (a box's author). */
  came_from?: AgentKey;
  /** The set of a type shown on the right (types design 3.4). */
  showing?: { type: ObjectType; where: Shown["where"]; title: string };
  /** The record chosen on the right (definition 36.6). */
  record_id?: string;
  record_number?: number;
  /** The plan the right's images are judged by (36.6): a draft write's or a version's. */
  write?: number;
  revision?: number;
}

/** The corner marks of a worker's button: the count of its things waiting, a trouble mark,
 * the ring while it works. */
export function marksOf(agent: AgentInfo | undefined): {
  count: number;
  trouble: boolean;
  working: boolean;
} {
  if (!agent) return { count: 0, trouble: false, working: false };
  return {
    count: agent.waiting + agent.trouble,
    trouble: agent.trouble > 0,
    working: agent.running + agent.queued > 0,
  };
}

/** Whether a worker's talk has lines the person has not seen (newer than the last seen id). */
export function hasNew(lastId: number | undefined, seenId: number | undefined): boolean {
  return lastId !== undefined && lastId > (seenId ?? 0);
}

/** A worker's first box waiting on the person (waiting, or trouble): where its turn is, in its
 * talk. */
export function turnBoxOf(proposals: Proposal[], agent: AgentKey): Proposal | undefined {
  return proposals.find((p) => p.agent === agent && (p.waiting || p.trouble));
}

/** The boxes waiting on a stage of the map, oldest first (outdated ones too: they need a
 * look). Folded ones ("later") are kept apart by the caller. */
export function boxesOn(proposals: Proposal[], stage: StageName): Proposal[] {
  return proposals.filter((p) => p.waiting && p.stage === stage);
}

/** The images a box is about (its targets, shown with a thick frame and a tag). */
export function targetsOf(proposal: Pick<Proposal, "args" | "preview">): string[] {
  const args = proposal.args;
  if (Array.isArray(args.image_ids)) return args.image_ids.map(String);
  if (typeof args.image_id === "string") return [args.image_id];
  const preview = proposal.preview ?? {};
  if (Array.isArray(preview.images)) {
    return preview.images
      .map((image) => (image && typeof image === "object" ? (image as { id?: string }).id : null))
      .filter((id): id is string => typeof id === "string");
  }
  return [];
}

/** The lines of a band's "after": [key, values] for t(). */
export function afterOf(proposal: Proposal): [string, Record<string, string | number>][] {
  const preview = proposal.preview ?? {};
  const lines: [string, Record<string, string | number>][] = [];
  const targets = targetsOf(proposal);
  if (targets.length) lines.push(["band.after.images", { count: targets.length }]);
  if (proposal.tool === "run_start") {
    const model = textOf(proposal.args.model) || textOf(preview.model);
    if (model) lines.push(["band.after.model", { model }]);
    const cost = textOf(preview.estimate_usd);
    if (cost) lines.push(["band.after.cost", { cost }]);
    // What follows a run, always (Sol 2026-10-09: the Haiku line took the place of "its
    // results go to training", and they did). A trial's results are looked at, not adopted.
    // Not for one that did not run (withdrawn, declined).
    if (proposal.waiting || proposal.state === "applied")
      lines.push([proposal.step === "trial" ? "band.after.then.trial" : "band.after.then.run", {}]);
    // Which plan it follows: the one the box holds, a trial's and a run's alike (definition
    // 11.4; Sol 2026-10-12: the version a trial would use could not be told).
    // Decided: the version it ran (none when it did not run).
    const revision = proposal.waiting
      ? textOf(preview.revision)
      : proposal.state === "applied"
        ? textOf((proposal.outcome ?? {}).revision ?? preview.revision)
        : "";
    if (revision)
      lines.push([
        (preview.trial ?? proposal.args.trial) ? "band.after.version.trial" : "band.after.version",
        { revision },
      ]);
  }
  if (proposal.tool === "mark") {
    // What training gets, before and after (it was only in "details", user 2026-10-09).
    const now = preview.adopted_now;
    const after = preview.adopted_after;
    if (typeof now === "number" && typeof after === "number" && now !== after)
      lines.push(["band.after.adopted", { now, after }]);
    lines.push(["band.after.then.mark", {}]);
  }
  lines.push(...dataAfter(proposal.tool, preview));
  return lines;
}

/** What the decisions of definition 22.2 other than a run and a mark do, from their preview
 * (the server's data_facts). */
function dataAfter(
  tool: string,
  preview: Record<string, unknown>,
): [string, Record<string, string | number>][] {
  const num = (value: unknown) => (typeof value === "number" ? value : 0);
  const image = textOf((preview.image as { name?: string } | undefined)?.name);
  switch (tool) {
    case "run_stop":
      return [
        [
          "band.after.stop",
          { run: textOf(preview.run_number), done: num(preview.done), left: num(preview.left) },
        ],
      ];
    case "pick":
      if (preview.rule) return [["band.after.pick.rule", { image }]];
      return [
        ["band.after.pick", { image, after: textOf(preview.after_run) }],
        ...(preview.excluded_now
          ? [["band.after.pick.in", {}] as [string, Record<string, string>]]
          : []),
      ];
    case "carry": {
      const from = (preview.from ?? {}) as Record<string, unknown>;
      const skipped = Object.values((preview.skipped ?? {}) as Record<string, number>).reduce(
        (a, b) => a + b,
        0,
      );
      const lines: [string, Record<string, string | number>][] = [
        ["band.after.carry", { from: textOf(from.name), revision: textOf(from.revision) }],
      ];
      if (skipped) lines.push(["band.after.carry.skipped", { count: skipped }]);
      if (num(preview.left_out))
        lines.push(["band.after.carry.leftOut", { count: num(preview.left_out) }]);
      if (num(preview.other)) lines.push(["band.after.carry.other", { count: num(preview.other) }]);
      return lines;
    }
    case "confirm":
      return [
        ["band.after.confirm", { count: num(preview.images), revision: textOf(preview.revision) }],
      ];
    case "dataset_add_images":
      return [
        ["band.after.add", { found: num(preview.found), skipped: num(preview.skipped) }],
        ...kept(preview),
      ];
    case "dataset_remove_images":
      return [
        [
          "band.after.remove",
          {
            images: namesText(
              objectsOf<{ id: string; name: string }>(preview.images).map((i) => i.name),
            ),
          },
        ],
        ...(num(preview.used_now)
          ? [
              ["band.after.remove.used", { used: num(preview.used_now) }] as [
                string,
                Record<string, number>,
              ],
            ]
          : []),
      ];
    case "label_rename":
      return [
        [
          "band.after.label",
          { from: textOf(preview.from), to: textOf(preview.to), datasets: num(preview.datasets) },
        ],
      ];
    case "label_change":
      // Of this dataset only (definition 79): its annotations now made again, the rest as they are.
      return [
        [
          "band.after.label_change",
          {
            from: textOf(preview.from),
            to: textOf(preview.to),
            images: num(preview.images),
            revision: num(preview.next_revision),
          },
        ],
        ...(num(preview.without)
          ? [["band.after.label_change.without", { count: num(preview.without) }]]
          : []),
      ] as [string, Record<string, string | number>][];
    case "dataset_rename":
      return [["band.after.rename", { from: textOf(preview.from), to: textOf(preview.to) }]];
    case "dataset_create":
      return [
        [
          "band.after.create",
          {
            name: textOf(preview.name),
            found: num(preview.found),
            purpose: textOf(preview.purpose),
          },
        ],
        ...kept(preview),
      ];
    case "dataset_from": {
      const sources = objectsOf<{ id: string; name: string }>(preview.sources);
      return [
        [
          "band.after.from",
          {
            name: textOf(preview.name),
            sources: sources.map((d) => calledName(d)).join(t("text.list")),
            images: num(preview.images),
          },
        ],
        ...(!preview.instruction
          ? [["band.after.from.noplan", {}] as [string, Record<string, string>]]
          : []),
        ...(preview.instruction && sources[0]
          ? [
              ["band.after.from.plan", { source: calledName(sources[0]) }] as [
                string,
                Record<string, string>,
              ],
            ]
          : []),
      ];
    }
    case "dataset_import":
      return [
        [
          "band.after.import",
          {
            path: textOf(preview.path),
            names: objectsOf<{ id: string; name: string }>(preview.datasets)
              .map((d) => d.name)
              .join(t("text.list")),
            images: num(preview.images),
          },
        ],
      ];
    case "dataset_delete":
      return [
        [
          "band.after.delete",
          {
            name: calledName(preview.dataset as { number?: number; name: string }),
            runs: num(preview.runs),
            trials: num(preview.trials),
            versions: num(preview.instructions),
            freed: num(preview.freed_images),
          },
        ],
        ...(num(preview.unrecoverable)
          ? [
              ["band.after.delete.lost", { count: num(preview.unrecoverable) }] as [
                string,
                Record<string, number>,
              ],
            ]
          : []),
      ];
    default:
      return [];
  }
}

/** Images by name: the first three and how many more. */
function namesText(names: string[]): string {
  const shown = names.slice(0, 3).join(t("text.list"));
  return names.length > 3 ? t("work.note.more", { names: shown, count: names.length - 3 }) : shown;
}

/** Files imported before with the other origin (a photograph or a made image): they keep theirs. */
function kept(preview: Record<string, unknown>): [string, Record<string, number>][] {
  const count = typeof preview.kept === "number" ? preview.kept : 0;
  return count ? [["band.after.kept", { count }]] : [];
}

/** Why the server withdrew a waiting box, as [key, values] for t(), by name (definition
 * 18.13): the plan written again, or what another decision changed first. */
export function withdrawnWhy(
  outcome: Record<string, unknown> | null | undefined,
): [string, Record<string, string>] {
  const cause = (outcome?.cause ?? null) as {
    kind?: string;
    images?: { name: string; record_number: number | null; going?: boolean }[];
    /** The images by name (what an image of a record uses changed). */
    names?: string[];
    image?: string;
    revision?: number;
  } | null;
  switch (cause?.kind) {
    case "results":
      return [
        "withdrawn.cause.results",
        {
          images: (cause.images ?? [])
            .map((i) =>
              t(
                !i.record_number
                  ? "withdrawn.cause.image"
                  : i.going
                    ? "withdrawn.cause.image.going"
                    : "withdrawn.cause.image.done",
                { name: i.name, run: String(i.record_number ?? "") },
              ),
            )
            .join(t("text.list")),
        },
      ];
    case "revision":
      return ["withdrawn.cause.revision", { revision: textOf(cause.revision) }];
    case "draft":
      return ["withdrawn.cause.draft", {}];
    case "done":
      return ["withdrawn.cause.done", { image: textOf(cause.image) }];
    case "excluded":
      return ["withdrawn.cause.excluded", { image: textOf(cause.image) }];
    case "use":
      // What an image of a record uses changed first (definition 19.5).
      return ["withdrawn.cause.use", { images: (cause.names ?? []).join(t("text.list")) }];
    case "plan":
      // The plan written again (definition 11.10).
      return ["withdrawn.cause.plan", {}];
    case "replaced":
      // The worker made a newer run of the same kind (definition 40.1).
      return ["withdrawn.cause.replaced", {}];
    // The decisions of definition 22.2: what they name gone, a record ended, images taken
    // out, a name changed, the datasets made from or the one deleted changed.
    case "gone":
      return ["withdrawn.cause.gone", {}];
    case "ended":
      return [
        "withdrawn.cause.ended",
        { run: textOf((cause as { run_number?: number }).run_number) },
      ];
    case "removed":
      return ["withdrawn.cause.removed", { images: (cause.names ?? []).join(t("text.list")) }];
    case "renamed":
      return ["withdrawn.cause.renamed", { name: textOf((cause as { name?: string }).name) }];
    case "sources":
      return ["withdrawn.cause.sources", { names: (cause.names ?? []).join(t("text.list")) }];
    case "dataset":
      return ["withdrawn.cause.dataset", { name: textOf((cause as { name?: string }).name) }];
    default:
      // One stopped as outdated before it was withdrawn instead (a row of before 10-17).
      return ["withdrawn.cause.unknown", {}];
  }
}

/** What a sent line was written looking at (null: nothing kept). */
export function lookingOf(event: AgentEvent): LookingAt | null {
  const looking = event.data?.looking_at as LookingAt | undefined;
  return looking && (looking.image_name || looking.stage) ? looking : null;
}

/** A run's images by how they are: succeeded, failed (or stopped short: ended, not made), being
 * worked on, and waiting (not begun; also those the page has not listed yet). */
export function runParts(
  badges: Pick<Badge, "kind" | "succeeded" | "waiting">[],
  total: number,
): { succeeded: number; failed: number; working: number; waiting: number } {
  const succeeded = badges.filter((b) => b.succeeded).length;
  const failed = badges.filter((b) => !b.succeeded && !b.waiting).length;
  const working = badges.filter((b) => b.kind === "running").length;
  return { succeeded, failed, working, waiting: Math.max(0, total - succeeded - failed - working) };
}

/** A line's link to what it showed, counted in what the right shows (definition 39.1): images
 * (images, results, or the images of one record pointed at) as images, several records as
 * records, one thing pointed at with no count, anything else as things. */
export function showLinkWords(shown: Shown): string {
  const title = shown.title || t(`object.${shown.type}`);
  if (shown.type === "run" && shown.id) return t("side.show.images", { title, count: shown.count });
  if (shown.id) return t("side.show.one", { title });
  if (shown.type === "image" || shown.type === "result")
    return t("side.show.images", { title, count: shown.count });
  if (shown.type === "run") return t("side.show.records", { title, count: shown.count });
  return t("side.show", { title, count: shown.count });
}

/** A question's words: the server's own (the plan's entry, definition 34.2) worded here, in the
 * screen's language; a worker's as it wrote them. */
export function questionText(event: AgentEvent): string {
  const entry = event.data?.entry as
    | { step?: EntryStep; n?: number; count?: number; shown?: number }
    | undefined;
  if (!entry?.step) return event.text;
  // More existing plans than options: the rest are on the right (2026-10-29: 4 said, 3 shown).
  const more = entry.step === "which" && (entry.count ?? 0) > (entry.shown ?? 0);
  return t(more ? "entry.q.which.more" : `entry.q.${entry.step}`, {
    n: entry.n ?? "",
    count: entry.count ?? 0,
    shown: entry.shown ?? 0,
  });
}

/** An option's words as the screen shows them (and as the person's line says them when chosen):
 * the server's own worded here, a worker's as it wrote them. */
export function optionWords(option: QuestionOption): string {
  if (!option.say) return option.label;
  const values = option.values ?? {};
  if (option.say === "plan") {
    const labels = (values.labels ?? []) as PastRequirement["labels"];
    const done = Number(values.done ?? 0);
    return t(done ? "entry.o.plan" : "entry.o.plan.none", {
      what: summaryLine(definitionsOf(labels)),
      done,
      total: Number(values.total ?? 0),
    });
  }
  return t(`entry.o.${option.say}`, {
    n: Number(values.n ?? 0),
    count: Number(values.count ?? 0),
  });
}

/** What the right showed, in words (definition 35.3): an image, else Apply's screen chosen,
 * else the place (a line from before the stages were renamed says today's name). */
export function rightWords(looking: LookingAt): string {
  const stage = looking.stage ? (stageOf(String(looking.stage)) ?? "production") : null;
  const place = looking.image_name
    ? t("side.looking.image", { image: looking.image_name })
    : stage
      ? t("side.looking.stage", { stage: screenName(stage, looking.screen) })
      : "";
  // The record chosen and the plan seen, as the right's header says them (definition 36.6).
  const plan = planOf(looking);
  return [
    place,
    looking.record_number ? t("run.number", { number: looking.record_number }) : "",
    plan ? basisWords(plan) : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

/** What the plan's screen shows above the plan (definition 37.4): a line of the talk (its open
 * question's facts, what it showed, its trial) or a box (the trial). */
export type About = { line: number } | { box: string };

/** The right's state for what the person chose on the left (definition 35.4, 37.4): a line that
 * came, an option, a line's "see", a box's "see". Only these functions compute it, and every
 * one of them goes through it (user 2026-10-23: the buttons went straight to screens of their
 * own). The thing it is about, by its type's view, judged by the plan it is about (36.1). The
 * plan's (its questions, its parts, a trial) on the plan's screen, with what it shows above; a
 * box of Apply on its screen, in its band (37: a run on annotating with AI, before it is decided
 * and while it goes); a run on annotating with AI (its record when one is named); a record of
 * samples above the plan it ran; any other set the steward showed on the type's own screen (its
 * conditions name its plan). */
export type RightTarget =
  | {
      stage: "instruction";
      plan: PlanRef | null;
      about: About | null;
      /** A record of samples, shown above the plan it ran (whatever the plan is now). */
      recordId?: string;
    }
  | {
      stage: "production";
      screen: Purpose;
      recordId?: string;
      plan: PlanRef | null;
      /** The box it is about, shown in the screen's band. */
      box?: string;
    }
  | { objects: Shown }
  /** One image or result, large (definition 59.2). */
  | { loupe: LoupeAt }
  | { library: true };

const PLAN_TYPES: ObjectType[] = ["requirement", "label", "version", "draft"];

/** The screen of Apply a box is at (definition 37): what training uses (the step "drop": mark,
 * pick) on its screen, any other (a run, stopping it, the images, the name) on annotating with
 * AI. The band, the waiting counts and the talk's right all take it from here. */
export function screenOfBox(box: Proposal): Purpose {
  return box.step === "drop" ? "use" : "annotate";
}

/** The plan a run's box runs (definition 11.4), to open and judge it by: decided, the version it
 * ran; else the version it holds, or its draft write while no version holds it (Sol 2026-10-17:
 * opened as "the plan now", it changed under the reader; 2026-10-27: a decided trial kept the
 * write the version it made replaced, and the plan's screen took it for an earlier plan). */
export function planOfBox(
  box: Pick<Proposal, "args" | "preview"> & Partial<Pick<Proposal, "state" | "outcome">>,
): PlanRef | null {
  const ran = box.state === "applied" ? box.outcome?.revision : undefined;
  if (typeof ran === "number") return { revision: ran };
  const held = (box.preview?.plan as { revision?: unknown } | null | undefined)?.revision;
  if (typeof held === "number") return { revision: held };
  return planOf({ write: box.args.draft_write_id, revision: box.args.revision });
}

/** The place of a box (what deciding it does), with the plan it runs: a trial is the plan's, a
 * box of Apply its screen, the box in its band; a run decided, the record it made (user
 * 2026-10-27: "see on the right" and "see the record" showed the same, and an old trial's
 * showed neither its samples). */
export function rightOfBox(box: Proposal): RightTarget | null {
  const plan = planOfBox(box);
  const record = box.tool === "run_start" && box.state === "applied" ? box.outcome?.id : undefined;
  if (typeof record === "string") return rightOfRecord(record, box.stage === "instruction", plan);
  if (box.stage === "instruction") return { stage: "instruction", plan, about: { box: box.id } };
  if (box.stage === "production")
    return { stage: "production", screen: screenOfBox(box), plan, box: box.id };
  return null;
}

/** The right for a record: a trial's samples above the plan it ran, a run's on annotating with
 * AI with its record chosen. */
function rightOfRecord(recordId: string, trial: boolean, plan: PlanRef | null): RightTarget {
  return trial
    ? { stage: "instruction", plan, about: null, recordId }
    : { stage: "production", screen: "annotate", recordId, plan };
}

/** The right for a set the steward showed on a line (the line's "see" too): the plan's parts on
 * the plan's screen, one image or result in the loupe (the image by the plan of the show, a result
 * at its record), a box its place, a record's results its trial's plan or annotating with AI, any
 * other its type's screen. */
export function rightOfShown(
  shown: Shown,
  line: number,
  boxOf: (id: string) => Proposal | undefined,
  runOf: (runId: string) => { trial: boolean; revision: number } | undefined,
): RightTarget | null {
  if (PLAN_TYPES.includes(shown.type))
    return { stage: "instruction", plan: planOf(shown.where), about: { line } };
  const { image_id: image, record } = shown;
  if (shown.id && image && record)
    return {
      loupe: resultLoupe({
        image_id: image,
        record_id: record.id,
        trial: record.trial,
        revision: record.revision,
      }),
    };
  if (shown.id && image) return { loupe: imageLoupe(image, planOf(shown.where)) };
  // A box shown is the box: its place, by the plan it runs.
  const shownBox = shown.type === "proposal" && shown.id ? boxOf(shown.id) : undefined;
  if (shownBox) return rightOfBox(shownBox);
  const id = shown.type === "run" ? shown.id : (shown.where.run as string | undefined);
  const run = id ? runOf(id) : undefined;
  if ((shown.type === "run" || shown.type === "result") && id && run)
    return rightOfRecord(id, run.trial, { revision: run.revision });
  return { objects: shown };
}

/** The right for a line: a question of the plan (the entry's too) is the plan's; what it showed
 * (the steward's choice of the right) before the box it asks to decide (decided in the line
 * itself); a box made or decided is its place; a run ended its trial's plan or annotating with
 * AI, by the version it ran; a request handed to the reception the library (definition 36.7). */
export function rightOf(
  line: AgentEvent,
  boxOf: (id: string) => Proposal | undefined,
  runOf: (runId: string) => { trial: boolean; revision: number } | undefined,
): RightTarget | null {
  const data = line.data ?? {};
  const options = Array.isArray(data.options) ? data.options : [];
  if (
    line.kind === "question" &&
    (data.entry || data.item || options.some((o) => o?.plan || o?.start))
  )
    return {
      stage: "instruction",
      plan: planOf((data.premise ?? {}) as Record<string, unknown>),
      about: { line: line.id },
    };
  const shown = data.show && typeof data.show === "object" ? (data.show as Shown) : null;
  if (shown) return rightOfShown(shown, line.id, boxOf, runOf);
  const boxes = Array.isArray(data.proposal_ids) ? (data.proposal_ids as string[]) : [];
  const box = boxOf(boxes[0] ?? (data.note === "box_applied" ? String(data.proposal_id) : ""));
  if (box) return rightOfBox(box);
  if (data.note === "run_ended") {
    const plan = planOf({ revision: data.revision });
    return data.trial && typeof data.run_id === "string"
      ? rightOfRecord(data.run_id, true, plan)
      : { stage: "production", screen: "annotate", plan };
  }
  // Handed to the library's worker: the right goes to the library (by its place, 48.11).
  if (data.note === "handed" && placeOfWorker(String(data.to_agent) as AgentKey) === "library")
    return { library: true };
  return null;
}

/** What the plan's screen shows above the plan (definition 26.7, 37.4): what the right was sent
 * to, else what the newest line whose right is the plan's screen sends it to (an entry question
 * only while it is open: its facts go with it). */
export function planAbout(
  lines: AgentEvent[],
  about: About | null,
  boxOf: (id: string) => Proposal | undefined,
  runOf: (runId: string) => { trial: boolean; revision: number } | undefined,
): About | null {
  if (about) return about;
  for (const line of [...lines].reverse()) {
    if (line.data?.entry && line.closed_at) continue;
    const target = rightOf(line, boxOf, runOf);
    if (target && "stage" in target && target.stage === "instruction") return target.about;
  }
  return null;
}

/** What the plan's screen draws above the plan for what it is about (definition 37.4): a line's
 * open entry question's facts, what it showed, else the trial; a box, the trial. */
export type PlanShows =
  | { kind: "entry"; line: AgentEvent }
  | { kind: "show"; show: Shown; line: AgentEvent }
  | { kind: "trial" };

export function planShows(about: About | null, lines: AgentEvent[]): PlanShows | null {
  if (!about) return null;
  if ("box" in about) return { kind: "trial" };
  const line = lines.find((l) => l.id === about.line);
  if (!line) return null;
  if (line.data?.entry) return line.closed_at ? null : { kind: "entry", line };
  const show = line.data?.show as Shown | undefined;
  return show ? { kind: "show", show, line } : { kind: "trial" };
}

/** The same drawing is the same thing on the right: a set shown from two lines is one. */
function planShowsKey(shows: PlanShows | null): string {
  if (!shows) return "";
  if (shows.kind === "trial") return "trial";
  if (shows.kind === "entry") return `entry:${JSON.stringify(shows.line.data?.entry ?? null)}`;
  const { show } = shows;
  return `show:${show.type}:${show.id ?? ""}:${new URLSearchParams(whereQuery(show.where))}`;
}

/** What the right shows now (definition 37.5): the route, with what it leaves to the screen
 * filled in (the stage now, the plan now, what the plan's screen shows by itself), and the
 * boxes it shows in the band (unfolded) or with their result. */
export interface RightNow {
  screen: Route["screen"];
  stage: StageName | null;
  purpose: Purpose;
  recordId: string | null;
  /** The loupe's image. */
  imageId: string | null;
  /** The plan the screen is judged by, as a query ("write=5"). */
  plan: string;
  about: About | null;
  /** The talk the plan's screen reads what it draws from. */
  lines: AgentEvent[];
  objects: { type: ObjectType; where: string; id: string | null } | null;
  boxes: string[];
  viewed: string | null;
}

/** Whether the right shows a state already (definition 37.5): its link says "on the right", not
 * pressed; and the left moves the right only to a state it does not show. planNow: the plan a
 * state that names none is judged by. */
export function onRight(target: RightTarget, now: RightNow, planNow: PlanRef | null): boolean {
  if ("library" in target) return now.screen === "library";
  if ("loupe" in target)
    return (
      now.screen === "loupe" &&
      now.imageId === target.loupe.imageId &&
      now.stage === target.loupe.stage &&
      now.recordId === target.loupe.recordId &&
      now.plan === planQuery(target.loupe.plan ?? planNow)
    );
  if ("objects" in target)
    return (
      now.objects !== null &&
      now.screen === "objects" &&
      now.objects.type === target.objects.type &&
      now.objects.id === (target.objects.id ?? null) &&
      now.objects.where === new URLSearchParams(whereQuery(target.objects.where)).toString()
    );
  if (now.screen !== "gallery" || now.stage !== target.stage) return false;
  if (now.plan !== planQuery(target.plan ?? planNow)) return false;
  if (now.recordId !== (target.recordId ?? null)) return false;
  if (target.stage === "instruction")
    return (
      target.recordId !== undefined ||
      planShowsKey(planShows(now.about, now.lines)) ===
        planShowsKey(planShows(target.about, now.lines))
    );
  if (now.purpose !== target.screen) return false;
  return !target.box || now.boxes.includes(target.box) || now.viewed === target.box;
}

/** A run's end whose box's card is in the same talk: the card's "see" goes to what the run made
 * already, so the line has no "see" of its own (definition 59.1; one way to one place, as
 * toldByCard). */
export function runEndCarded(
  event: AgentEvent,
  carded: Map<string, number>,
  boxOf: (id: string) => Proposal | undefined,
): boolean {
  const run = event.data?.note === "run_ended" ? event.data.run_id : null;
  return typeof run === "string" && [...carded.keys()].some((id) => boxOf(id)?.outcome?.id === run);
}

/** The cursor into the left's field, where the person writes to the worker (an option's "other",
 * a band pointing to the talk). */
export function focusAsk() {
  document.querySelector<HTMLTextAreaElement>("[data-ask]")?.focus();
}

/** The history's words: the chats besides the one open (user 2026-10-28: a new dataset's only
 * chat counted itself as its history); with none, the word alone. */
export function historyWords(chats: { id: number }[], current: number | null): string {
  const past = chats.filter((c) => c.id !== current).length;
  return past ? t("side.chat.history", { count: past }) : t("side.chat.historyNone");
}

/** A line telling what became of a box (decided, declined, failed, withdrawn) whose card is in
 * the same talk: the card says it as its record (user 2026-10-27: the same thing twice), so the
 * line is not shown there. A talk without the card (the one it was handed from) keeps it. */
export function toldByCard(event: AgentEvent, carded: Map<string, number>): boolean {
  const note = event.kind === "note" ? event.data?.note : null;
  const id = event.data?.proposal_id;
  return (
    typeof note === "string" &&
    note.startsWith("box_") &&
    note !== "box_made" &&
    typeof id === "string" &&
    carded.has(id)
  );
}
