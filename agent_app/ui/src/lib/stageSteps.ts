// The step of a box on its stage (the server's `step`, design 3.4). The row of steps under the
// map became the stage's card (types design 17.4, StageCard); a box still says its step.
import type { StageName } from "@/api/types";

/** The box steps of each step id. */
const BOX: Record<string, Record<string, string>> = {
  instruction: { trial: "trial", save: "save" },
  production: { run: "run", exclude: "drop" },
};

/** The step id a box belongs to on its stage. */
export function stepOfBox(stage: StageName, boxStep: string | null | undefined): string | null {
  const found = Object.entries(BOX[stage]).find(([, box]) => box === boxStep);
  return found ? found[0] : null;
}
