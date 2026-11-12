// The buttons of a type's things, from the server's list of each type's actions (types design 8:
// the same list gives a worker's decisions). Which of them a thing offers now is decided here.
import type { ObjectType, Run } from "@/api/types";

export interface Action {
  name: string;
  /** A worker's proposal of it is this decision's tool (a person's press is done at once). */
  decision_tool: string | null;
  method: string | null;
  path: string | null;
}

export type TypeActions = Partial<Record<ObjectType, { where: string[]; actions: Action[] }>>;

/** A run can be stopped while it waits or goes, until it is stopping (definition 40.2). */
export function canStop(run: Run): boolean {
  return run.going && run.status !== "stopping";
}

/** The actions a person can press for a run now: stop while it goes; use its images' results
 * (a version's run that made some; definition 19.5). */
export function runActions(all: TypeActions, run: Run): Action[] {
  // A person's fix is a record but not a run (definition 21.4): a run's actions are not its.
  if (run.kind === "fix") return [];
  // A record of an earlier requirement cannot be used for training (Sol 2026-10-14: offered,
  // pressed, nothing changed): the server says whether it can (run.usable).
  const offered: Record<string, boolean> = { stop: canStop(run), use: run.usable };
  return (all.run?.actions ?? []).filter((a) => a.path && offered[a.name]);
}

/** The start of a run of one image again by the record's own way (definition 11.1): its plan's
 * version, the shared notes' version, a trial or not, the model, effort and limit (2026-10-30
 * review: only the model went, so a failure of version 1 ran by the plan now). None for a record
 * whose plan is no version (an early trial of a draft): it cannot be run so again. */
export function againBody(run: Run, imageId: string): Record<string, unknown> | null {
  if (run.instruction_revision < 1) return null;
  return {
    image_ids: [imageId],
    trial: run.trial ?? false,
    revision: run.instruction_revision,
    shared_revision: run.settings.shared_revision ?? null,
    model: run.settings.model ?? null,
    effort: run.settings.effort ?? null,
    tier: run.settings.tier ?? null,
    budget_per_image_usd: run.budget_per_image_usd ?? null,
  };
}

/** The path of a person's press for one thing. */
export function actionPath(action: Action, datasetId: string, id: string): string {
  return (action.path ?? "").replace("{dataset_id}", datasetId).replace("{id}", id);
}
