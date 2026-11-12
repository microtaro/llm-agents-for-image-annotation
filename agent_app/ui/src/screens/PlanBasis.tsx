// The plan the right judges its images by (definition 36.1, 56), out of the top row into the
// screen's own second row, beside what it puts on (user 2026-10-28: the top row held five kinds
// of things and cut the purpose to one character): chosen while annotating, else said.
import type { ReactNode } from "react";
import type { Instruction, PlanState } from "@/api/types";
import { t } from "@/i18n";
import { basisWords, planChoice, planChoices, planOfChoice } from "@/lib/planParts";
import { type PlanRef, planOf } from "@/lib/route";
import { useApi } from "@/lib/useApi";

export function PlanBasis({
  datasetId,
  plan,
  shown,
  onPlan,
  row = false,
}: {
  datasetId: string;
  /** The plan the talk judges by; none: the plan now. */
  plan: PlanRef | null;
  /** The plan the screen judges by when it is not the talk's (training's latest version). */
  shown?: PlanRef | null;
  /** Another plan chosen to look by; none: said, not chosen. */
  onPlan?: (plan: PlanRef | null) => void;
  /** As a row of its own under the top row (the plan screen's), none with nothing to say. */
  row?: boolean;
}) {
  const shownAs = (node: ReactNode) =>
    row ? <div className="border-b border-line bg-sheet px-5 py-2">{node}</div> : node;
  const state = useApi<PlanState>(`/v1/datasets/${datasetId}/plan/state`);
  const now = state.data ? planOf(state.data) : null;
  const versions = useApi<{ instructions: Instruction[] }>(
    onPlan ? `/v1/datasets/${datasetId}/instructions` : null,
  );
  const choices = onPlan ? planChoices(now, versions.data?.instructions ?? [], plan) : [];
  if (onPlan && choices.length > 0)
    return shownAs(
      <label className="flex shrink-0 items-center gap-1.5 text-body text-muted-foreground">
        {t("basis.menu")}
        <select
          className="rounded-md border border-line bg-surface px-2 py-0.5 text-body text-ink"
          value={planChoice(now, plan)}
          onChange={(e) => onPlan(planOfChoice(e.target.value))}
        >
          {choices.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </label>,
    );
  const by = shown ?? plan ?? now;
  return by
    ? shownAs(<span className="shrink-0 text-body text-muted-foreground">{basisWords(by)}</span>)
    : null;
}
