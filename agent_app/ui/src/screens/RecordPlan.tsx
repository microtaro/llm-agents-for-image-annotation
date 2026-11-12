// A record's plan (definition 11.10): the way it ran (version, model, effort) and what the plan
// says now differently from it, with the way to open that version. What is needed, looking at a
// record's results, to decide whether to fix the plan; nothing added when the plan is the same.
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { useModelName } from "@/lib/runChoice";
import { planChangeItems } from "@/lib/decisions";
import { useApi } from "@/lib/useApi";

interface PlanNow {
  revision: number;
  model: string | null;
  effort: string | null;
  changes: Record<string, unknown> | null;
}

export function RecordPlan({
  recordId,
  runNumber,
  onOpen,
}: {
  recordId: string;
  /** The record's number, to name it (user 2026-10-17: never "this record"). */
  runNumber?: number;
  /** Open the record's version in making and fixing. */
  onOpen: (revision: number) => void;
}) {
  const nameOf = useModelName();
  const found = useApi<PlanNow>(`/v1/runs/${recordId}/plan-now`);
  if (!found.data || !found.data.revision) return null;
  const plan = found.data;
  const items = planChangeItems(plan.changes, nameOf);
  return (
    <div className="flex w-full flex-wrap items-baseline gap-x-2.5 gap-y-0.5 text-body">
      <span>
        {t("record.plan.title", {
          run: runNumber ?? "?",
          revision: plan.revision,
          model: nameOf(plan.model ?? ""),
          effort: plan.effort ?? "—",
        })}
      </span>
      <span className="text-muted-foreground">
        {t(items.length ? "record.plan.changed" : "record.plan.same", { run: runNumber ?? "?" })}
      </span>
      {items.map(([key, values], index) => (
        <span key={`${key}-${index}`} className="break-words">
          {t(key, values)}
        </span>
      ))}
      <Button variant="link" size="small" onClick={() => onOpen(plan.revision)}>
        {t("record.plan.open")}
      </Button>
    </div>
  );
}
