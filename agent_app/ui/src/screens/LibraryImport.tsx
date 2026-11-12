// Taking in (definition 60.3): what to do is chosen first, and it decides what is asked after.
// A new dataset from a folder's images; images added to the one chosen (so datasets do not pile
// up, user 2026-10-15); a dataset made from the chosen ones' images (one: the same images for
// another purpose, the purpose being fixed once made; several: their images together); or a
// folder written out (this app's form: its datasets as they were). The first choice is by how
// many are chosen; the folder stays as chosen when the choice changes. What the folder holds is
// told by the scan, not chosen: when it is not what the choice takes, it is said, with the way
// to the choice that takes it.
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type ApiError } from "@/api/client";
import type { Dataset, DatasetSummary, Written } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { firstIntent, type ImportIntent, intentWhyNot } from "@/lib/library";
import { go } from "@/lib/route";
import { queryClient } from "@/lib/useApi";
import { enterToTalk } from "@/lib/viewState";
import { skipText } from "@/lib/skips";
import { FolderPicker, type Picked } from "./FolderPicker";
import { Missing, NewDatasetFields } from "./NewDatasetFields";

const NONE: Picked = { paths: [], origin: null, count: 0, written: null };

export function ImportDialog({
  open,
  datasets,
  onClose,
}: {
  open: boolean;
  /** The datasets chosen with their rings. */
  datasets: DatasetSummary[];
  onClose: () => void;
}) {
  const one = datasets.length === 1 ? datasets[0] : null;
  const [intent, setIntent] = useState<ImportIntent>(firstIntent(datasets.length));
  const [picked, setPicked] = useState<Picked>(NONE);
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [instruction, setInstruction] = useState(true);
  const [busy, setBusy] = useState(false);
  // Why it was refused, kept in the dialog (Astra 2026-10-15: the notice was cut off at the
  // bottom of the screen, so the reason could not be read).
  const [refused, setRefused] = useState<string | null>(null);
  const onPick = useCallback((next: Picked) => setPicked(next), []);
  const key = datasets.map((d) => d.id).join(",");
  useEffect(() => {
    if (!open) return;
    setIntent(firstIntent(datasets.length));
    setPicked(NONE);
    setName("");
    setPurpose("");
    setInstruction(true);
    setRefused(null);
    // Begun again each time it opens, by what is chosen then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, key]);
  const images = datasets.reduce((n, d) => n + d.image_count, 0);
  // Another purpose with the same images: named so at first (the name only while it is that).
  const copyName = one ? t("dataset.copy.name", { name: one.name }) : "";
  const choose = (next: ImportIntent) => {
    setIntent(next);
    if (next === "from" && copyName && !name.trim()) setName(copyName);
    if (next !== "from" && copyName && name === copyName) setName("");
  };
  const written = picked.written;
  // What the folder holds against what was chosen to do (none while nothing is found).
  const mismatch: ImportIntent | null =
    intent !== "written" && written
      ? "written"
      : intent === "written" && !written && picked.count
        ? "images"
        : null;
  const app = intent === "written" && written?.kind === "app" ? written : null;
  // COCO's JSON: one new dataset the person names (its first version made from it, 60.11).
  const coco = intent === "written" && written?.kind === "coco" ? written : null;
  const naming = intent === "images" || intent === "from" || Boolean(coco);
  const missing = [
    ...(naming && !name.trim() ? [t("create.name")] : []),
    ...(naming && !purpose.trim() ? [t("create.purpose")] : []),
    // Made of the chosen datasets, the folder's images are more (optional); a folder written
    // out is said by the mismatch instead.
    ...((intent === "images" || intent === "add") && !picked.count && !written
      ? [t("create.missing.folder")]
      : []),
    ...(intent === "written" && !written && !mismatch ? [t("library.import.missing.written")] : []),
    ...(mismatch ? [t("library.import.missing.match")] : []),
  ];

  async function take() {
    setBusy(true);
    setRefused(null);
    try {
      if (app || coco) {
        const done = await api<{
          datasets: {
            id: string;
            name: string;
            unannotated?: number;
            skipped?: { images: number; objects: number };
          }[];
        }>("/v1/library/import", {
          body: coco
            ? { path: coco.path, name, purpose, origin: picked.origin }
            : { path: app?.path },
        });
        toast.success(t("library.import.done", { count: done.datasets.length }));
        // COCO's: what was left (an image with no object has no result; what could not be read).
        for (const made of done.datasets)
          if (made.unannotated || made.skipped?.images || made.skipped?.objects)
            toast.warning(
              t("library.import.left", {
                unannotated: made.unannotated ?? 0,
                images: made.skipped?.images ?? 0,
                objects: made.skipped?.objects ?? 0,
              }),
              { duration: 10000 },
            );
        if (done.datasets.length === 1) opened(done.datasets[0].id);
        else {
          void queryClient.invalidateQueries();
          onClose();
        }
        return;
      }
      if (intent === "images") {
        const made = await api<Dataset & { skipped: { reason: string }[] }>("/v1/datasets", {
          body: { name, purpose, paths: picked.paths, origin: picked.origin },
        });
        toast.success(t("create.done", { name: made.name, count: made.image_count }));
        if (made.skipped.length)
          toast.warning(
            t("create.skipped", { count: made.skipped.length, why: skipText(made.skipped) }),
          );
        opened(made.id);
        return;
      }
      let target = one?.id ?? "";
      if (intent === "from") {
        const made = await api<Dataset>("/v1/datasets/from", {
          body: {
            name,
            purpose,
            dataset_ids: datasets.map((d) => d.id),
            instruction: Boolean(one) && instruction,
          },
        });
        target = made.id;
      }
      if (picked.count) {
        const done = await api<{ added: string[]; already: string[] }>(
          `/v1/datasets/${target}/images/import`,
          { body: { paths: picked.paths, origin: picked.origin } },
        );
        toast.success(t("add.done", { added: done.added.length, already: done.already.length }));
      }
      if (intent === "from") opened(target);
      else {
        void queryClient.invalidateQueries();
        onClose();
      }
    } catch (reason) {
      const error = reason as ApiError;
      const skipped = (error.details?.skipped ?? []) as { reason: string }[];
      const why =
        error.code === "nothing_imported"
          ? t("create.nothing", { why: skipText(skipped) })
          : errorText(error);
      setRefused(why);
      toast.error(why);
    } finally {
      setBusy(false);
    }
  }

  // A new dataset has no plan yet: it opens at its plan with its steward (user 2026-10-20).
  function opened(datasetId: string) {
    void queryClient.invalidateQueries();
    onClose();
    enterToTalk(datasetId);
    go({ screen: "gallery", datasetId, stage: "instruction", recordId: null });
  }

  const intents: [ImportIntent, string][] = [
    ["images", t("library.import.images")],
    ["add", t("library.import.add")],
    ["from", t("library.import.from")],
    ["written", t("library.import.written")],
  ];
  const what: Record<ImportIntent, string> = {
    written: t("library.import.written.how"),
    images: "",
    add: one ? t("library.import.add.to", { name: one.name }) : "",
    from: one
      ? t("library.import.from.one")
      : t("library.import.from.many", { count: datasets.length }),
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={t("library.import.title")}
      wide
      footer={
        <>
          <Missing items={missing} />
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button variant="primary" disabled={missing.length > 0 || busy} onClick={take}>
            {coco
              ? t("create.submit", { count: coco.images })
              : app
                ? t("library.import.submit.written", {
                    count: app.datasets.length,
                    images: app.datasets.reduce((n, d) => n + d.images, 0),
                  })
                : intent === "add"
                  ? t("add.submit", { count: picked.count })
                  : t("create.submit", {
                      count: picked.count + (intent === "from" ? images : 0),
                    })}
          </Button>
        </>
      }
    >
      {refused && (
        <p
          role="alert"
          className="m-0 border-b border-line bg-draft px-5 py-3 text-body text-failed"
        >
          {refused}
        </p>
      )}
      <section className="flex flex-col gap-1 border-b border-line px-5 py-4">
        <h3 className="m-0 text-heading">{t("library.import.what")}</h3>
        <div role="radiogroup" aria-label={t("library.import.what")} className="flex flex-col">
          {intents.map(([key, label]) => {
            const why = intentWhyNot(key, datasets.length);
            return (
              <label key={key} className={`py-0.5 text-body ${why ? "text-muted-foreground" : ""}`}>
                <input
                  type="radio"
                  className="mr-2"
                  checked={intent === key}
                  disabled={Boolean(why)}
                  onChange={() => choose(key)}
                />
                {label}
                {(why ?? what[key]) && (
                  <span className="text-muted-foreground"> — {why ?? what[key]}</span>
                )}
              </label>
            );
          })}
        </div>
      </section>
      {/* What it makes, first (user 2026-10-15), then where the images come from. */}
      <section className="flex flex-col gap-2 border-b border-line px-5 py-4">
        {intent === "written" ? (
          <>
            {coco && (
              <NewDatasetFields
                purpose={purpose}
                name={name}
                onPurpose={setPurpose}
                onName={setName}
              />
            )}
            <WrittenHolds written={written} />
          </>
        ) : intent === "add" && one ? (
          <p className="m-0 text-body">
            {t("library.import.add.target", { name: one.name, count: one.image_count })}{" "}
            <span className="text-muted-foreground">{t("add.note")}</span>
          </p>
        ) : (
          <>
            <NewDatasetFields
              purpose={purpose}
              name={name}
              onPurpose={setPurpose}
              onName={setName}
            />
            {intent === "from" &&
              (one ? (
                <label className="flex items-center gap-2 text-body">
                  <input
                    type="checkbox"
                    checked={instruction}
                    onChange={(e) => setInstruction(e.target.checked)}
                  />
                  {t("dataset.copy.instruction")}
                </label>
              ) : (
                <p className="m-0 text-body text-muted-foreground">
                  {t("library.from.note", { names: datasets.map((d) => d.name).join("、") })}
                </p>
              ))}
          </>
        )}
      </section>
      {/* One place for the folder whatever is done, so it stays as chosen. */}
      <section className="flex flex-col gap-2.5 border-b border-line px-5 py-4">
        <h3 className="m-0 text-heading">
          {t(intent === "from" ? "create.step.source.optional" : "create.step.source")}
        </h3>
        <FolderPicker onChange={onPick} />
        {mismatch && (
          <div
            role="alert"
            className="flex flex-col items-start gap-1.5 rounded-md border border-line border-l-4 border-l-failed bg-surface px-3 py-2 text-body"
          >
            <b>
              {mismatch === "written" && written
                ? t("library.import.mismatch.written", {
                    kind: t(`library.import.kind.${written.kind}`),
                  })
                : t("library.import.mismatch.images")}
            </b>
            <Button size="small" onClick={() => choose(mismatch)}>
              {t("library.import.switch", {
                intent: intents.find(([key]) => key === mismatch)?.[1] ?? "",
              })}
            </Button>
          </div>
        )}
      </section>
    </Dialog>
  );
}

/** What a folder written out holds, as the scan told it: this app's datasets as they come in
 * (their names and purposes as they are), or COCO's JSON (one dataset, its first version made
 * from it and one record taken in, definition 60.11). */
function WrittenHolds({ written }: { written: Written | null }) {
  if (!written)
    return (
      <p className="m-0 text-body text-muted-foreground">{t("library.import.written.wait")}</p>
    );
  if (written.kind === "coco")
    return (
      <p className="m-0 text-body">
        {t("library.import.coco", {
          file: written.file,
          images: written.images,
          annotations: written.annotations,
          labels: written.categories.length,
        })}{" "}
        <span className="text-muted-foreground">{t("library.import.coco.how")}</span>
      </p>
    );
  return (
    <div className="flex flex-col gap-1 text-body">
      <h3 className="m-0 text-heading">{t("library.import.written.list")}</h3>
      <ul className="m-0 flex flex-col gap-0.5 pl-5">
        {written.datasets.map((d) => (
          <li key={d.folder}>
            <b>{d.name}</b>{" "}
            <span className="text-muted-foreground">
              {t("library.import.written.item", {
                purpose: d.purpose,
                images: d.images,
                plan: d.revision
                  ? t("library.import.written.plan", { revision: d.revision })
                  : t("library.import.written.noPlan"),
                records: d.records,
              })}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
