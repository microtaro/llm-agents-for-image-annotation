// Whether a result is its image's reference, and the press that changes it (definition 38.1): on
// a sample's card and in the loupe, as the plan now says it. It says where it goes (the plan) and,
// on the pointer, what a reference is (user 2026-10-28: "make it the reference" did not say what it means).
import { toast } from "sonner";
import type { PlanState } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { chooseReference } from "@/lib/reference";
import { useApi } from "@/lib/useApi";

export function ReferenceChoice({
  datasetId,
  imageId,
  resultId,
}: {
  datasetId: string;
  imageId: string;
  resultId: string;
}) {
  const state = useApi<PlanState>(`/v1/datasets/${datasetId}/plan/state`);
  const chosen = (state.data?.plan?.references ?? []).some(
    (r) => r.image_id === imageId && r.result_id === resultId,
  );
  const choose = (result: string | null) =>
    void chooseReference(datasetId, imageId, result).catch((reason) =>
      toast.error(errorText(reason)),
    );
  return chosen ? (
    <span className="inline-flex flex-wrap items-baseline gap-x-2 text-body" title={t("ref.why")}>
      <span className="text-muted-foreground">{t("ref.chosen")}</span>
      <Button variant="link" size="small" onClick={() => choose(null)}>
        {t("ref.unset")}
      </Button>
    </span>
  ) : (
    <Button size="small" title={t("ref.why")} onClick={() => choose(resultId)}>
      {t("ref.set")}
    </Button>
  );
}
