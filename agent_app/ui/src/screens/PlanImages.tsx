// The dataset's images on the plan's screen, under the plan, whatever the right is about (user
// 2026-10-27: asked about what the photos hold, the right showed the plan's text alone): judged
// by the plan looked at, a blank plan before any (definition 49.2), as a set of images is shown
// anywhere (ImageSet: the gallery's cards with the samples marked, a card opens the loupe), read
// as the right's set of images is (the image type's conditions).
import type { GalleryItem, ObjectSet } from "@/api/types";
import { t } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { planQuery, type PlanRef } from "@/lib/route";
import { useApi } from "@/lib/useApi";
import { ImageSet } from "./ImageSet";

const BLANK: PlanRef = { blank: true };

export function PlanImages({ datasetId, plan }: { datasetId: string; plan: PlanRef | null }) {
  const judged = plan ?? BLANK;
  const found = useApi<ObjectSet>(`/v1/datasets/${datasetId}/objects/image?${planQuery(judged)}`);
  const colors = useApi<{ colors: Record<string, string> }>(
    `/v1/datasets/${datasetId}/label-colors${"blank" in judged ? "" : `?${planQuery(judged)}`}`,
  );
  if (found.error) return <p className="m-0 text-failed">{errorText(found.error)}</p>;
  if (!found.data) return null;
  return (
    <ImageSet
      datasetId={datasetId}
      items={found.data.items as unknown as GalleryItem[]}
      view="adoption"
      colors={colors.data?.colors ?? {}}
      plan={judged}
      title={t("compare.dataset")}
      note={t("objects.count", { count: found.data.items.length })}
    />
  );
}
