// The run being decided on Apply's annotating screen (definition 40.2): one thing whoever made
// it, seen as the steward's line on the left and as the bar and the cards' rings on the right.
// A worker's waiting run (at most one, 40.1) with the person's changes, else the person's own
// run of the images they ringed. Its preview is read once for both sides (the same body).
import type { Proposal } from "@/api/types";
import { t } from "@/i18n";
import {
  applyBox,
  type DecisionBody,
  decidedBody,
  decideNow,
  declineBox,
  runBody,
} from "./propose";
import { targetsOf } from "./talk";
import { invalidate, useApi, usePosted } from "./useApi";
import {
  dropRunChanges,
  type RunChanges,
  runChangesOf,
  usePicks,
  useRunChanges,
} from "./viewState";

/** A run of Apply (samples are the plan's): the rings and the bar show it, not a band. */
export function isApplyRun(p: Proposal): boolean {
  return p.tool === "run_start" && p.stage === "production" && !p.args.trial;
}

/** The worker's run waiting on Apply: at most one, 40.1. */
export function openRunBox(proposals: Proposal[]): Proposal | null {
  return proposals.find((p) => p.waiting && isApplyRun(p)) ?? null;
}

/** The values the person changed on a box, as deciding records them ({key: [before, after]},
 * the server's proposals.changes): said on the box while it waits as its record says them once
 * decided (user 2026-10-27: the box's title still said 44 images with 2 chosen). */
export function changesOf(box: Proposal, changes: RunChanges): Record<string, [unknown, unknown]> {
  return Object.fromEntries(
    Object.entries(changes)
      .filter(([key, value]) => JSON.stringify(box.args[key]) !== JSON.stringify(value))
      .map(([key, value]) => [key, [box.args[key], value]]),
  );
}

/** Its images: the worker's with the person's changes, else the person's own. */
export function runImages(box: Proposal | null, changes: RunChanges, picks: string[]): string[] {
  if (!box) return picks;
  return changes.image_ids ?? targetsOf(box);
}

/** What is decided: the box's values with the person's changes, or the person's own run. */
export function runDecisionBody(
  datasetId: string,
  box: Proposal | null,
  changes: RunChanges,
  picks: string[],
): DecisionBody {
  if (box)
    return {
      tool: box.tool,
      args: { ...box.args, ...changes },
      title: box.title,
      reason: box.reason,
    };
  const own = runBody(datasetId, picks);
  return { ...own, args: { ...own.args, ...changes } };
}

export type Preview = { args: Record<string, unknown>; preview: Record<string, unknown> };

/** The run being decided on Apply, with its changes and the ways to change it. */
export function useRunDecision(datasetId: string) {
  const proposals = useApi<{ proposals: Proposal[] }>(`/v1/datasets/${datasetId}/proposals`);
  const box = openRunBox(proposals.data?.proposals ?? []);
  const [picks, setPicks] = usePicks(datasetId, "production.annotate");
  const [changes, setChanges] = useRunChanges(datasetId, box?.id ?? null);
  const images = runImages(box, changes, picks);
  return {
    box,
    images,
    changes,
    body: images.length ? runDecisionBody(datasetId, box, changes, picks) : null,
    setImages: (ids: string[]) =>
      box ? setChanges({ ...changes, image_ids: ids }) : setPicks(ids),
    setValues: (values: RunChanges) => setChanges({ ...changes, ...values }),
  };
}

/** What a run would do, as the server says it (nothing kept): the same for the left and the
 * right, read again with the dataset. */
export function useRunPreview(datasetId: string | null, body: DecisionBody | null) {
  return usePosted<Preview>(
    datasetId && body ? `/v1/datasets/${datasetId}/proposals/preview` : null,
    body,
  );
}

/** Whether starting it needs the one check (a run, not samples; definition 40.1). */
export function heavyOf(preview: Record<string, unknown> | null | undefined): boolean {
  return (preview?.card as { weight?: string } | undefined)?.weight === "heavy";
}

/** Decide it: a worker's box with the person's changes (definition 40.1), or the person's own
 * run as its preview showed it (definition 11.6). The changes go with it; chat: the chat it is
 * decided in (definition 81). */
export async function decideRun(
  datasetId: string,
  box: Proposal | null,
  body: DecisionBody,
  shown: Preview | null,
  chat?: number | null,
): Promise<void> {
  if (box) {
    const changes = runChangesOf(datasetId, box.id);
    await applyBox(box.id, Object.keys(changes).length ? changes : undefined, chat);
  } else {
    await decideNow(datasetId, decidedBody(body, shown?.args ?? body.args, null), chat);
  }
  dropRunChanges(datasetId, box?.id ?? null);
  invalidate(datasetId);
}

/** Not decided: a worker's box declined, the person's own run let go. */
export async function letGo(
  datasetId: string,
  box: Proposal | null,
  clearPicks: () => void,
  chat?: number | null,
) {
  if (box) await declineBox(box.id, chat);
  else clearPicks();
  dropRunChanges(datasetId, box?.id ?? null);
  invalidate(datasetId);
}

/** The bar's first line: whose run and how many images. */
export function runWho(box: Proposal | null, changes: RunChanges, count: number): string {
  if (!box) return t("decide.bar.own", { count });
  return t(Object.keys(changes).length ? "decide.bar.boxChanged" : "decide.bar.box", { count });
}
