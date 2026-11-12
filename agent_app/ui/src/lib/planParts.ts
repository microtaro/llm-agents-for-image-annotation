// A plan's parts as the screens say them: its labels in one line, the plans a screen can be
// looked at by (definition 56), what a plan puts on the images (definition 57).
import type {
  Instruction,
  LabelDefinition,
  PastRequirement,
  PlanState as PlanNow,
  PutLabel,
  Run,
} from "@/api/types";
import { t, when } from "@/i18n";
import { type PlanRef, planOf, planQuery } from "@/lib/route";
import { useApi } from "@/lib/useApi";

/** A plan's labels in one line: each with its shape, the values read and the label it is in. */
export function summaryLine(definitions: LabelDefinition[]): string {
  return definitions
    .map(
      (d) =>
        `${d.name}${t(`tree.shape.${d.shape}`)}` +
        (d.attributes.length
          ? t("book.summary.attrs", { attrs: d.attributes.map((a) => a.name).join(t("tree.join")) })
          : "") +
        (d.parent ? ` ${t("tree.inside", { label: d.parent })}` : ""),
    )
    .join(t("book.summary.join"));
}

/** An existing plan's labels (a past requirement's) as a plan's definitions. */
export function definitionsOf(labels: PastRequirement["labels"]): LabelDefinition[] {
  return labels.map((l) => ({
    id: l.id,
    name: l.name,
    shape: l.shape,
    parent: l.parent,
    description: "",
    attributes: l.attributes.map((a) => ({ ...a, choices: a.choices ?? null, description: "" })),
  }));
}

/** The plan a screen's images are judged by: the one it names, else the plan now (the draft's
 * write, else the latest version; definition 36.1). Said in its header and sent with the words
 * (36.6). */
/** What a plan puts on the images, each label and how it is taken (definition 57): a version's,
 * or a draft's write as it was; none for a blank plan or none named. */
export function usePlanLabels(datasetId: string, plan: PlanRef | null): PutLabel[] | null {
  const path =
    !plan || "blank" in plan
      ? null
      : "revision" in plan
        ? `/v1/datasets/${datasetId}/instructions/${plan.revision}`
        : `/v1/datasets/${datasetId}/drafts/instruction/writes/${plan.write}`;
  const found = useApi<{ label_definitions: LabelDefinition[] }>(path);
  return found.data
    ? found.data.label_definitions.map((d) => ({
        name: d.name,
        shape: d.shape,
        parent: d.parent,
        attributes: (d.attributes ?? []).map((a) => a.name),
      }))
    : null;
}

export function usePlanSeen(datasetId: string, plan: PlanRef | null): PlanRef | null {
  const now = useApi<PlanNow>(plan ? null : `/v1/datasets/${datasetId}/plan/state`);
  return plan ?? (now.data ? planOf(now.data) : null);
}

export interface PlanChoice {
  /** The plan's query ("revision=2"); "" for the plan now. */
  value: string;
  label: string;
}

/** The plans a dataset's screen can be looked at by (definition 56, user 2026-10-27: which
 * version the plan was was not said, and an earlier one could not be looked at): the plan now
 * first (a draft says the version it was made from), then each saved version, newest first; the
 * version that is the plan now is said once. A plan looked at that is none of them (a draft's
 * write a line linked to) is added. None while no plan is begun. */
export function planChoices(
  now: PlanRef | null,
  versions: Pick<Instruction, "revision" | "created_at">[],
  shown: PlanRef | null = null,
): PlanChoice[] {
  if (!now || "blank" in now) return [];
  const newest = versions[0]?.revision;
  const choices: PlanChoice[] = [];
  if ("write" in now)
    choices.push({
      value: "",
      label: newest ? t("basis.choice.draft", { revision: newest }) : t("basis.choice.draftNew"),
    });
  for (const v of versions)
    choices.push(
      "revision" in now && now.revision === v.revision
        ? { value: "", label: t("basis.choice.now", { revision: v.revision }) }
        : {
            value: planQuery({ revision: v.revision }),
            label: t("basis.choice.version", { revision: v.revision, time: when(v.created_at) }),
          },
    );
  const value = planChoice(now, shown);
  if (value && !choices.some((c) => c.value === value))
    choices.push({ value, label: shown ? basisWords(shown) : value });
  return choices;
}

/** The choice of a plan looked at: "" for none or the plan now. */
export function planChoice(now: PlanRef | null, shown: PlanRef | null): string {
  if (!shown) return "";
  return planQuery(shown) === planQuery(now) ? "" : planQuery(shown);
}

/** A choice back as a plan: none for the plan now. */
export function planOfChoice(value: string): PlanRef | null {
  return value ? planOf(Object.fromEntries(new URLSearchParams(value))) : null;
}

/** The plan a set of images is judged by, in words (definition 36.2): the header's and a set's
 * conditions alike. */
export function basisWords(plan: PlanRef): string {
  if ("blank" in plan) return t("basis.blank");
  return "write" in plan ? t("basis.draft") : t("basis.version", { revision: plan.revision });
}

/** The samples the plan's screen shows: the newest, whatever version made them (user
 * 2026-10-27: once the plan was a version newer, the samples of the one before were gone), the
 * ones going first. The runs as the server lists them, the newest first. */
export function newestTrial(runs: Run[], going: string | null | undefined): Run | undefined {
  const trials = runs.filter((r) => r.trial);
  return trials.find((r) => r.id === going) ?? trials[0];
}
