// A run going: how far it is, and stop (user 2026-10-06: the first app showed a progress bar).
// The same line where the run was decided (definition 40.2): the steward's line on the left and
// the bar of annotating with AI, and above the plan's screen. Its record is reached from the
// left's line ("see on the right") and the record filter, which stay when it has ended (user
// 2026-10-27: the bar's way to it showed what the right showed already, and went with the bar).
import { toast } from "sonner";
import { api } from "@/api/client";
import type { Run } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { canStop } from "@/lib/actions";
import { errorText } from "@/lib/errorText";
import { versionOf, useModelName } from "@/lib/runChoice";

export function RunBar({ run, onChanged }: { run: Run; onChanged: () => void }) {
  const modelName = useModelName();
  const share = run.total ? Math.round((run.processed / run.total) * 100) : 0;
  async function stop() {
    try {
      await api(`/v1/runs/${run.id}/stop`, { body: {} });
      onChanged();
    } catch (reason) {
      toast.error(errorText(reason));
    }
  }
  return (
    <div role="status" className="flex basis-full flex-wrap items-center gap-x-3 gap-y-1 text-body">
      <span className="font-semibold">
        {t(
          `runbar.${run.status === "stopping" || run.status === "queued" ? run.status : "running"}`,
          {
            done: run.processed,
            total: run.total,
            version: versionOf(run.instruction_revision),
            model: modelName(run.settings.model),
          },
        )}
      </span>
      <span
        aria-hidden="true"
        className="h-1.5 min-w-24 flex-1 overflow-hidden rounded-full bg-track"
      >
        <span className="block h-full bg-processing" style={{ width: `${share}%` }} />
      </span>
      {canStop(run) && (
        <Button size="small" onClick={() => void stop()}>
          {t("run.stop")}
        </Button>
      )}
    </div>
  );
}
