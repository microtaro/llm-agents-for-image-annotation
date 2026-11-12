// A run's decision card as a figure (definition 16, 18; user 2026-10-17: people do not read
// long text, a technical document has figures; things are named by name or number, never "this"
// or "the last"): what is used (the plan, the model, the images) as boxes with arrows, the
// record it is compared with by its number, the counts as short tags, and how the plans were
// used as a small table with "—" where nothing is known. Made from the server's card alone;
// the worker's line on the left and the decide window on the right show the same.
import type { RunCard, Usage } from "@/api/types";
import { t } from "@/i18n";
import { planChangeItems, type Said } from "./decisions";
import { budgetWords } from "./selection";

export interface UseRow {
  /** What was used, by name and number. */
  label: Said;
  /** Its use; null: nothing is known (shown as "—"). */
  usage: Usage | null;
}

export interface RunCardView {
  heavy: boolean;
  trial: boolean;
  /** The plan box: its version, or the version the draft becomes. */
  plan: Said;
  /** The shared notes for every worker AI it adds, by version (definition 18.15). */
  shared: Said | null;
  model: string;
  effort: string;
  images: { ids: string[]; count: number };
  /** The record it is compared with, by number; null when nothing ran before. */
  against: { said: Said; changes: Said[] } | null;
  tags: Said[];
  /** The images whose annotation a success replaces. */
  replaces: string[];
  uses: UseRow[];
  trials: { id: string; name: string; status: string }[];
  /** Another decided run holds some of the images: why it cannot be decided now. */
  held: Said | null;
}

/** A run in one line: its plan, model and effort, the cost expected and its limit. Beside the bar's
 * button and in the confirm before a run starts (user 2026-10-27: the confirm said only that
 * what starts cannot be undone, not how many images, by which plan, for how much). */
export function runLine(view: RunCardView): string {
  return [
    t(...view.plan),
    `${view.model} · ${view.effort}`,
    ...view.tags
      .filter(([key]) => key.startsWith("card.tag.cost") || key === "card.tag.noCost")
      .map((tag) => t(...tag)),
    ...view.tags.filter(([key]) => key === "card.tag.budget").map((tag) => t(...tag)),
  ].join(t("decide.bar.join"));
}

/** Why a run cannot be decided now: the records that hold its images (waiting in the line or
 * annotating), by number and name (definition 18.13). Null when none does. */
export function heldSaid(card: RunCard | null | undefined): Said | null {
  const held = card?.happens.held ?? [];
  if (!held.length) return null;
  const runs = [...new Set(held.map((h) => h.run_number ?? "?"))].join(t("text.list"));
  return ["card.held", { runs, images: held.map((h) => h.name).join(t("text.list")) }];
}

export function runCardView(
  card: RunCard,
  targets: string[],
  modelName: (model: string) => string,
): RunCardView {
  const { fixes, happens, grounds } = card;
  const plan = fixes.plan;
  const model = modelName(fixes.model ?? "");
  const effort = fixes.effort ?? "";
  const planSaid: Said =
    plan.kind === "write" && plan.revision === null
      ? ["card.plan.new", { next: plan.next_revision ?? "?" }]
      : plan.kind === "write"
        ? ["card.plan.same", { revision: plan.revision ?? "?" }]
        : ["card.plan.version", { revision: plan.revision ?? "?" }];
  let against: RunCardView["against"] = null;
  if (fixes.against) {
    const run = fixes.against.run_number ?? "?";
    if (!fixes.changes) against = { said: ["card.against.same", { run }], changes: [] };
    else {
      const items = planChangeItems(fixes.changes, modelName);
      against = {
        said: [
          "card.against.other",
          {
            run,
            revision: fixes.against.revision,
            model: modelName(fixes.against.model),
            effort: fixes.against.effort,
          },
        ],
        changes: [
          ...items.slice(0, 2),
          ...(items.length > 2
            ? [["plan.diff.moreLines", { count: items.length - 2 }] as Said]
            : []),
        ],
      };
    }
  }
  const usd = happens.estimate_usd ? Number(happens.estimate_usd).toFixed(2) : null;
  const tags: Said[] = [
    ["card.tag.new", { count: happens.new }],
    ["card.tag.redo", { count: happens.redo }],
    // Said only when there are some (a person's choice stays, definition 19.6).
    ...(happens.kept.length ? [["card.tag.kept", { count: happens.kept.length }] as Said] : []),
    // By this plan's criteria, the earlier ones are not done; training still uses them (85.6).
    ...(happens.other.images
      ? [["card.tag.other", { count: happens.other.images, again: happens.other.in_run }] as Said]
      : []),
    [
      card.decision === "run_trial" ? "card.tag.usedTrial" : "card.tag.used",
      { count: happens.used_after.length },
    ],
    usd
      ? happens.estimate_from
        ? [
            "card.tag.costFrom",
            {
              usd,
              name: happens.estimate_from.map((d) => d.name ?? "?").join(t("text.list")),
            },
          ]
        : ["card.tag.cost", { usd }]
      : ["card.tag.noCost", {}],
    ["card.tag.budget", budgetWords(happens.budget_per_image_usd, happens.images)],
  ];
  // A way is its version, model, effort and shared notes' version (definition 18.15).
  const way = { model, effort, shared: fixes.shared_revision ?? "?" };
  const uses: UseRow[] = [
    {
      label:
        plan.revision !== null
          ? ["card.use.way", { revision: plan.revision, ...way }]
          : ["card.use.wayNew", { next: plan.next_revision ?? "?", ...way }],
      usage: grounds.way?.runs ? grounds.way : null,
    },
  ];
  const origin = grounds.line.origin;
  const from = origin?.kind === "version" ? origin : grounds.line.based_on?.[0];
  if (from)
    uses.push({
      label: ["card.use.origin", { name: from.name ?? "?", revision: from.revision }],
      usage:
        origin?.kind === "version" && grounds.line.origin_usage?.runs
          ? grounds.line.origin_usage
          : null,
    });
  if (grounds.line.derived_total?.runs)
    uses.push({ label: ["card.use.derived", {}], usage: grounds.line.derived_total });
  return {
    heavy: card.weight === "heavy",
    trial: card.decision === "run_trial",
    plan: planSaid,
    shared: fixes.shared_revision ? ["card.box.shared", { revision: fixes.shared_revision }] : null,
    model,
    effort,
    images: { ids: targets, count: happens.images },
    against,
    tags,
    replaces: happens.replaces,
    uses,
    trials: grounds.trials.map((x) => ({ id: x.image_id, name: x.name, status: x.status })),
    held: heldSaid(card),
  };
}

/** A person's answer typed in the talk: "1" or "2" chooses that option of the newest waiting
 * proposal (18.1); anything else is words to the worker. */
export function typedChoice(text: string): 1 | 2 | null {
  // Full-width digits, the full stops and "ban" (the number's word) as typed with a Japanese
  // input, made from their code points (a formatter writes escapes back as the characters).
  const [one, two, stop, wideStop, ban] = [0xff11, 0xff12, 0x3002, 0xff0e, 0x756a].map((c) =>
    String.fromCharCode(c),
  );
  const found = new RegExp(`^\\s*([12${one}${two}])\\s*[.${stop}${wideStop}${ban}]?\\s*$`).exec(
    text,
  );
  if (!found) return null;
  return found[1] === "1" || found[1] === one ? 1 : 2;
}
