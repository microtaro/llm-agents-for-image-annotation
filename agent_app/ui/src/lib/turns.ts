// The person's turns (definition 44): read from one place on the server (/v1/turns), the
// reception's number every place's, the steward's its dataset's; clearing them clears the same.
import type { TurnPlace, Turns } from "@/api/types";

/** The places a clear covers: every one (the reception's), or the dataset's (the steward's). */
export function placesOf(turns: Turns | null, datasetId: string | null): TurnPlace[] {
  const places = turns?.places ?? [];
  return datasetId === null ? places : places.filter((p) => p.dataset_id === datasetId);
}

/** How many wait in those places. */
export function countOf(places: TurnPlace[]): number {
  return places.reduce((n, p) => n + p.count, 0);
}
