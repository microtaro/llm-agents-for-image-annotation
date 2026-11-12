// Deleting datasets, from the library's decision (user 2026-10-15): one or several together, with
// the images no other dataset uses.
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { DatasetSummary, Deletion } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { formatBytes } from "@/lib/bytes";
import { errorText } from "@/lib/errorText";
import { queryClient } from "@/lib/useApi";

async function tried<T>(work: () => Promise<T>): Promise<T | null> {
  try {
    return await work();
  } catch (reason) {
    toast.error(errorText(reason));
    return null;
  }
}

/** Deleting one or several datasets: what goes, what other datasets keep, what cannot come
 * back (user 2026-10-15), from the server's preview of them all together. */
export function DeleteDialog({
  datasets,
  onClose,
  onDeleted,
}: {
  datasets: DatasetSummary[];
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [seen, setSeen] = useState<Deletion | null>(null);
  const [busy, setBusy] = useState(false);
  const open = datasets.length > 0;
  const key = datasets.map((d) => d.id).join(",");
  useEffect(() => {
    setSeen(null);
    if (!key) return;
    void tried(() =>
      api<Deletion>("/v1/datasets/deletion", { body: { dataset_ids: key.split(",") } }),
    ).then(setSeen);
  }, [key]);
  const one = datasets.length === 1 ? datasets[0] : null;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={one ? t("dataset.delete") : t("dataset.delete.many", { count: datasets.length })}
      footer={
        <>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            variant="destructive"
            disabled={!seen || seen.active_run || busy}
            onClick={async () => {
              setBusy(true);
              let images = 0;
              let done = 0;
              for (const dataset of datasets) {
                const gone = await tried(() =>
                  api<{ removed_images: number }>(`/v1/datasets/${dataset.id}`, {
                    method: "DELETE",
                  }),
                );
                if (!gone) break;
                images += gone.removed_images;
                done += 1;
              }
              setBusy(false);
              if (done)
                toast.success(
                  // The image files only when some went (0 read as something removed).
                  `${one ? t("dataset.deleted", { name: one.name }) : t("dataset.deleted.many", { count: done })}${images ? t("dataset.deleted.images", { images }) : ""}`,
                );
              void queryClient.invalidateQueries();
              onDeleted();
            }}
          >
            {one ? t("dataset.delete") : t("dataset.delete.many", { count: datasets.length })}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-2 px-5 py-4">
        <p className="m-0">
          {one
            ? t("dataset.delete.message", { name: one.name })
            : t("dataset.delete.message.many", {
                names: datasets.map((d) => d.name).join("、"),
              })}
        </p>
        {seen && (
          <ul className="m-0 flex flex-col gap-1 pl-5 text-body">
            <li>
              {t("dataset.delete.counts", {
                runs: seen.runs,
                trials: seen.trials,
                instructions: seen.instructions,
              })}
            </li>
            <li>
              {t("dataset.delete.freed", {
                count: seen.freed_images,
                size: formatBytes(seen.freed_bytes),
              })}
            </li>
            {seen.shared.length > 0 && (
              <li>
                {t("dataset.delete.kept", {
                  list: seen.shared
                    .map((s) =>
                      t("library.shared.item", {
                        name: s.name,
                        count: s.images,
                        size: formatBytes(s.bytes),
                      }),
                    )
                    .join("、"),
                })}
              </li>
            )}
            {seen.unrecoverable > 0 && (
              <li className="text-failed">
                {t("dataset.delete.unrecoverable", { count: seen.unrecoverable })}
              </li>
            )}
          </ul>
        )}
        {seen?.active_run && <p className="m-0 text-failed">{t("dataset.delete.active")}</p>}
      </div>
    </Dialog>
  );
}
