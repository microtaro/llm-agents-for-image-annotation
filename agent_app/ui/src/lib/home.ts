// The left and the right of a dataset (definition 35.2, 35.3; user 2026-10-22): inside a dataset
// the left is its steward, at the library the reception; the right is chosen at its top or by
// what the steward shows, and opens at the dataset's stage now. The right never decides the left.
import type { AgentKey, Progress, StageName, WorkerPlace } from "@/api/types";
import type { Route } from "@/lib/route";

/** Each worker's place, one worker each (definition 48.1, 48.11; the server's agents.AGENTS):
 * what is a place's worker's is found by the place, never by a worker's name. */
const PLACES: Record<AgentKey, WorkerPlace> = { reception: "library", steward: "dataset" };

/** The workers, in their order on the left. */
export const WORKERS = Object.keys(PLACES) as AgentKey[];

export function placeOfWorker(agent: AgentKey): WorkerPlace | undefined {
  return PLACES[agent];
}

/** The worker of a place: the library's, or a dataset's (the left inside it). */
export function workerAt(place: WorkerPlace): AgentKey {
  return WORKERS.find((key) => PLACES[key] === place) as AgentKey;
}

/** The stage a dataset opens at: the map's stage now (Apply once the plan is done). */
export function stageNow(progress: Progress | null | undefined): StageName {
  return progress?.stages.find((s) => s.state === "now")?.stage ?? "production";
}

/** Where talking with a worker is: the reception's at the library, the steward's in its
 * dataset (at its stage now). */
export function homeOf(agent: AgentKey, datasetId: string): Route {
  if (placeOfWorker(agent) === "library") return { screen: "library" };
  return { screen: "gallery", datasetId, stage: null, recordId: null };
}
