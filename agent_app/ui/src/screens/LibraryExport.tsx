// Writing out (definition 60.4): no decision, nothing in the app changes. The datasets chosen go
// each into a new folder under the folder chosen, in this app's form (to give to another person
// using the app, the first choice) or COCO's JSON (to open and analyse in other tools).
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { DatasetSummary, PickedFolder } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { formatBytes } from "@/lib/bytes";
import { errorText } from "@/lib/errorText";
import { useExportFolder } from "@/lib/viewState";
import { Missing } from "./NewDatasetFields";

type Format = "app" | "coco";

export function ExportDialog({
  open,
  datasets,
  onClose,
}: {
  open: boolean;
  /** The datasets chosen with their rings. */
  datasets: DatasetSummary[];
  onClose: () => void;
}) {
  const [last, setLast] = useExportFolder();
  const [format, setFormat] = useState<Format>("app");
  const [which, setWhich] = useState<"used" | "now">("used");
  const [images, setImages] = useState(true);
  const [dest, setDest] = useState("");
  const [busy, setBusy] = useState(false);
  const [choosing, setChoosing] = useState(false);
  useEffect(() => {
    if (!open) return;
    setFormat("app");
    setDest(last ?? "");
    // Begun again each time it opens; the folder is the one written into last.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  const count = datasets.reduce((n, d) => n + d.image_count, 0);
  const size = formatBytes(datasets.reduce((n, d) => n + d.bytes, 0));
  const names = datasets.map((d) => t("library.export.name", { name: d.name })).join("");

  async function choose() {
    setChoosing(true);
    try {
      const picked = await api<PickedFolder>("/v1/local-images/select", {
        body: {
          directory: dest.trim() || last,
          title: t("library.export.window"),
          whole_folder: t("picker.window.whole"),
        },
      });
      if (!picked.cancelled) setDest(picked.directory);
    } catch (reason) {
      toast.error(errorText(reason));
    } finally {
      setChoosing(false);
    }
  }

  async function write() {
    setBusy(true);
    try {
      const done = await api<{ written: { path: string }[] }>("/v1/library/export", {
        body: {
          dataset_ids: datasets.map((d) => d.id),
          format,
          dest: dest.trim(),
          which,
          images,
        },
      });
      setLast(dest.trim());
      toast.success(
        t("library.export.done", {
          count: done.written.length,
          paths: done.written.map((w) => w.path).join("、"),
        }),
        { duration: 10000 },
      );
      onClose();
    } catch (reason) {
      toast.error(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  const radio = (on: boolean, set: () => void, label: string, how?: string) => (
    <label className="text-body">
      <input type="radio" className="mr-2" checked={on} onChange={set} />
      {label}
      {how && <span className="text-muted-foreground"> — {how}</span>}
    </label>
  );
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={t("library.export.title", { count: datasets.length })}
      wide
      footer={
        <>
          <Missing items={dest.trim() ? [] : [t("library.export.missing.dest")]} />
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button variant="primary" disabled={!dest.trim() || busy} onClick={write}>
            {t("library.export.submit")}
          </Button>
        </>
      }
    >
      <section className="flex flex-col gap-2 border-b border-line px-5 py-4">
        <label className="flex items-center gap-2">
          <span className="text-heading">{t("library.export.format")}</span>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as Format)}
            className="rounded-md border border-line bg-surface px-2 py-1"
          >
            <option value="app">{t("library.export.format.app")}</option>
            <option value="coco">{t("library.export.format.coco")}</option>
          </select>
        </label>
        {format === "app" ? (
          <>
            <ul className="m-0 pl-5 text-body">
              <li>{t("library.export.app.images", { count, size })}</li>
              <li>{t("library.export.app.plan")}</li>
              <li>{t("library.export.app.records")}</li>
              <li>{t("library.export.app.readable")}</li>
            </ul>
            <p className="m-0 text-body text-muted-foreground">{t("library.export.app.note")}</p>
          </>
        ) : (
          <>
            <div role="radiogroup" aria-label={t("library.export.which")} className="flex flex-col">
              <span className="text-body text-muted-foreground">{t("library.export.which")}</span>
              {radio(
                which === "used",
                () => setWhich("used"),
                t("library.export.which.used"),
                t("library.export.which.used.how"),
              )}
              {radio(
                which === "now",
                () => setWhich("now"),
                t("library.export.which.now"),
                t("library.export.which.now.how"),
              )}
            </div>
            <div
              role="radiogroup"
              aria-label={t("library.export.images")}
              className="flex flex-col"
            >
              <span className="text-body text-muted-foreground">{t("library.export.images")}</span>
              {radio(images, () => setImages(true), t("library.export.images.with", { size }))}
              {radio(
                !images,
                () => setImages(false),
                t("library.export.images.without"),
                t("library.export.images.without.how"),
              )}
            </div>
            <p className="m-0 text-body text-muted-foreground">{t("library.export.coco.note")}</p>
          </>
        )}
      </section>
      <section className="flex flex-col gap-2 border-b border-line px-5 py-4">
        <h3 className="m-0 text-heading">{t("library.export.dest")}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <input
            aria-label={t("library.export.dest")}
            value={dest}
            onChange={(e) => setDest(e.target.value)}
            className="min-w-64 flex-1 rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs"
          />
          <Button onClick={() => void choose()} disabled={choosing}>
            {t("picker.window.open")}
          </Button>
        </div>
        <p className="m-0 text-body text-muted-foreground">{t("library.export.made", { names })}</p>
      </section>
    </Dialog>
  );
}
