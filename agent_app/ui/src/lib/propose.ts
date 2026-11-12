// The decisions a person makes from a button (types design 17.4, 18): annotating images with AI
// and trying the plan (saving went, types design 20.1). A person's own run is not put in the line
// to be decided again (user 2026-10-13): the bar shows what it would do (lib/runDecision) and
// deciding there does it, kept like any decided box; a worker's waiting run is the same thing
// in the bar and in its line (definition 40.2).
import { api } from "@/api/client";
import type { Decision, Proposal } from "@/api/types";
import { t } from "@/i18n";
import { invalidate } from "./useApi";

/** What the server takes for a decision (the tool, its arguments, its title). */
export interface DecisionBody {
  tool: Proposal["tool"];
  args: Record<string, unknown>;
  title: string;
  reason: string;
}

export function runBody(datasetId: string, ids: string[], trial = false): DecisionBody {
  return {
    tool: "run_start",
    args: {
      dataset_id: datasetId,
      image_ids: ids,
      ...(trial ? { trial: true } : {}),
    },
    title: t(trial ? "propose.trial.title" : "propose.run.title", { count: ids.length }),
    reason: t("propose.reason"),
  };
}

/** What the person decides: the values the preview showed (the plan it points at, the model
 * and the effort, as the server made them values), with the ones changed since. Not the body
 * asked for: a draft written between the preview and the press would run in its place
 * (definition 11.6). */
export function decidedBody(
  body: DecisionBody,
  shown: Record<string, unknown>,
  changed: Record<string, unknown> | null,
): DecisionBody {
  return { ...body, args: { ...shown, ...changed } };
}

/** "?chat=n": the chat a decision is made in, told what came of it (definition 81); none: the
 * worker's latest. */
function inChat(chat?: number | null): string {
  return chat ? `?chat=${chat}` : "";
}

/** The person decides it: done at once, a decision with no proposal (definition 21.3). */
export async function decideNow(
  datasetId: string,
  body: DecisionBody,
  chat?: number | null,
): Promise<Decision> {
  const done = await api<Decision>(`/v1/datasets/${datasetId}/decisions${inChat(chat)}`, { body });
  invalidate(datasetId);
  return done;
}

/** A worker's proposal answered (definition 18.1): decided as it holds, declined, or seen when
 * it can no longer be decided. The same calls wherever it is answered. */
export function applyBox(
  id: string,
  args?: Record<string, unknown>,
  chat?: number | null,
): Promise<unknown> {
  return api(`/v1/proposals/${id}/apply${inChat(chat)}`, { body: args ? { args } : {} });
}

export function declineBox(id: string, chat?: number | null): Promise<unknown> {
  return api(`/v1/proposals/${id}/decline${inChat(chat)}`, { body: {} });
}

export function seenBox(id: string): Promise<unknown> {
  return api(`/v1/proposals/${id}/seen`, { body: {} });
}
