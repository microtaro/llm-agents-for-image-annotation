// How a record is said on the screen: who made it, its version, its way, what it took.
import type { RecordKind, Run, RunModels } from "@/api/types";
import { t } from "@/i18n";
import { useApi } from "./useApi";

/** A model by its name, as every screen says it (user 2026-10-27: the run's bar and the cards
 * said "claude-opus-5-5" where the box said "Claude Opus 5.5"; eight screens each looked the
 * name up): its display name, else its id. */
export type ModelName = (model: string | null | undefined) => string;

export function useModelName(): ModelName {
  const models = useApi<RunModels>("/v1/run-models");
  return (model) =>
    model ? (models.data?.models.find((m) => m.model === model)?.display_name ?? model) : "";
}

/** A record on the screen by its kind: a person's fix, one taken in, a label change or results
 * carried over says so (definition 21.4, 60.11, 79, 85.15), a run the AI's model by its name. */
export function modelLabel(
  model: string | null | undefined,
  kind: RecordKind | null | undefined,
  name: ModelName,
): string {
  return kind === "fix"
    ? t("run.human")
    : kind === "import"
      ? t("run.imported")
      : kind === "relabel"
        ? t("run.relabeled")
        : kind === "carry"
          ? t("run.carried")
          : name(model);
}

/** The version a run used; a trial (revision 0) ran the draft, which has no version. */
export function versionOf(revision: number): string {
  return revision === 0 ? t("instruction.version.trial") : t("instruction.version.n", { revision });
}

/** The way a record ran, "v2 · gpt-6.1-terra · medium": its version, its model (a person's fix
 * says so) and its effort (the records' table and "filter by record" say it alike, 54). */
export function wayText(
  run: Pick<Run, "instruction_revision" | "settings" | "kind">,
  name: ModelName,
): string {
  return [
    versionOf(run.instruction_revision),
    modelLabel(run.settings.model, run.kind, name),
    run.settings.effort,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** What one image's result took, "20s · $0.050": its time and its cost, each when known (the
 * card, the loupe's facts and its records say it alike; user 2026-10-27: the records did not). */
export function spentText(
  elapsedMs: number | null | undefined,
  costUsd: string | null | undefined,
): string {
  return [
    elapsedMs != null ? `${Math.round(elapsedMs / 1000)}s` : null,
    costUsd ? `$${Number(costUsd).toFixed(3)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}
