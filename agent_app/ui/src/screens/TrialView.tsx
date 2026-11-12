// The trial of the plan (definition 26.7, 36.2): the few images it is tried on, judged by the plan
// it runs (a result of that plan's requirement drawn, none for a new requirement), then its
// record's results, each with the same line as a run's card in Apply (time, cost, record; user
// 2026-10-22: a trial and a run do the same, yet only one said its cost), the labels of the plan
// none of them has (definition 38.5) and, on each card done, choosing it as the reference (38.1).
// Drawn as every set of images is (ImageSet). Deciding the trial is in the steward's line on the
// left.
import type { GalleryPage } from "@/api/types";
import { ReferenceChoice } from "@/components/ReferenceChoice";
import { t } from "@/i18n";
import { type PlanRef, planQuery } from "@/lib/route";
import { versionOf } from "@/lib/runChoice";
import { useApi } from "@/lib/useApi";
import { ImageSet } from "./ImageSet";

export function TrialView({
  datasetId,
  runId,
  imageIds,
  plan = null,
  title,
}: {
  datasetId: string;
  /** The record whose results are shown; none: the images, before it runs. */
  runId: string | null;
  /** The images shown before it runs (a waiting decision's); with a record, none is all of it. */
  imageIds: string[];
  /** Before it runs: the plan it runs, its images are judged by (none: the plan now). */
  plan?: PlanRef | null;
  /** A set's own title (the steward's words for it). */
  title?: string;
}) {
  const by = planQuery(plan);
  const page = useApi<GalleryPage>(
    `/v1/datasets/${datasetId}/gallery?${runId ? `view=run&record_id=${runId}` : `view=production${by ? `&${by}` : ""}`}`,
  );
  const only = new Set(imageIds);
  const items = (page.data?.items ?? []).filter((i) =>
    runId
      ? i.badge.record_id === runId && (only.size === 0 || only.has(i.image.id))
      : only.has(i.image.id),
  );
  const done = items.filter((i) => i.badge.succeeded);
  const missing = runId ? (page.data?.missing_labels ?? []) : [];
  // A record's samples are said by their record and version, as the plan's book says them (user
  // 2026-10-27: any record's samples can be shown now, not only the newest).
  const ran = items[0]?.badge;
  const named = runId
    ? t("trial.record", {
        run: ran?.record_number ?? "",
        version: ran?.record_revision == null ? "" : versionOf(ran.record_revision),
        count: items.length,
      })
    : t("trial.images", { count: items.length });
  return (
    <ImageSet
      datasetId={datasetId}
      items={items}
      view={runId ? "run" : "adoption"}
      colors={page.data?.label_colors ?? {}}
      // A record's results are of the version it ran; before it runs, the plan it runs.
      plan={
        runId
          ? items[0]?.badge.record_revision
            ? { revision: items[0].badge.record_revision }
            : null
          : plan
      }
      title={title || named}
      note={runId ? t("trial.done", { done: done.length, total: items.length }) : undefined}
      warning={
        missing.length ? t("trial.missing", { labels: missing.join(t("tree.join")) }) : undefined
      }
      cardAction={(item) =>
        runId && item.badge.result_id && item.badge.succeeded ? (
          <ReferenceChoice
            datasetId={datasetId}
            imageId={item.image.id}
            resultId={item.badge.result_id}
          />
        ) : null
      }
    />
  );
}
