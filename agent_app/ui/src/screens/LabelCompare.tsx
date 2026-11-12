// Is it the same thing? (definition 25.2-18, 26.7): a label of the library, as other datasets
// annotated it, beside this dataset's images, each in one image of many (its tiles numbered;
// the dataset's 16 a page, definition 42.4). The sheets are shown here only: what the worker
// compared, seen as it saw them (definition 49); the dataset's images elsewhere are a set of
// images (ImageSet).
// Compared side by side, also when opened large (user 2026-10-20: "comparing is side by side").
import { type ReactNode, useState } from "react";
import type { DatasetSheet, LibraryLabel, Sheet } from "@/api/types";
import { ZoomBox } from "@/components/ZoomBox";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { useApi } from "@/lib/useApi";

/** The dataset's sheets, 16 images a page (definition 42.4): shown when there is more than one. */
function Pager({ sheet, onPage }: { sheet: DatasetSheet | null; onPage: (page: number) => void }) {
  if (!sheet || sheet.pages < 2) return null;
  return (
    <span className="flex items-center gap-2">
      <Button size="small" disabled={sheet.page <= 1} onClick={() => onPage(sheet.page - 1)}>
        {t("compare.prev")}
      </Button>
      <span className="text-body tabular-nums" title={t("compare.order")}>
        {t("compare.page", { page: sheet.page, pages: sheet.pages, total: sheet.count })}
      </span>
      <Button
        size="small"
        disabled={sheet.page >= sheet.pages}
        onClick={() => onPage(sheet.page + 1)}
      >
        {t("compare.next")}
      </Button>
    </span>
  );
}

function Panel({
  title,
  note,
  pager,
  sheet,
  onOpen,
  tall,
}: {
  title: string;
  note: string;
  pager?: ReactNode;
  sheet: Sheet | null | undefined;
  onOpen?: () => void;
  tall?: boolean;
}) {
  return (
    <section className="flex min-h-0 flex-col gap-2 rounded-md border border-line bg-surface px-3 py-2.5">
      <h3 className="m-0 text-title">{title}</h3>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-body text-muted-foreground">{note}</span>
        {pager}
      </div>
      {sheet && (
        <ZoomBox
          label={onOpen ? t("compare.open", { title }) : title}
          onOpen={onOpen}
          className={`rounded-sm bg-backdrop ${tall ? "min-h-0 flex-1" : ""}`}
        >
          <img
            src={sheet.image}
            alt={title}
            draggable={false}
            className={`mx-auto block w-auto max-w-full ${tall ? "max-h-full" : "max-h-[calc(100vh-16rem)]"}`}
          />
        </ZoomBox>
      )}
    </section>
  );
}

export function LabelCompare({
  datasetId,
  labelId,
}: {
  datasetId: string;
  /** The library's label. */
  labelId: string;
}) {
  const label = useApi<LibraryLabel>(`/v1/labels/${labelId}`);
  const labelSheet = useApi<Sheet>(`/v1/labels/${labelId}/sheet`);
  const [page, setPage] = useState(1);
  const datasetSheet = useApi<DatasetSheet>(`/v1/datasets/${datasetId}/sheet?page=${page}`);
  const [open, setOpen] = useState(false);
  const panels = (tall: boolean) => (
    <>
      <Panel
        title={t("compare.label", { name: label.data?.name ?? "" })}
        note={t("compare.labelNote", {
          datasets: label.data?.datasets ?? 0,
          count: labelSheet.data?.tiles.length ?? 0,
        })}
        sheet={labelSheet.data}
        onOpen={tall ? undefined : () => setOpen(true)}
        tall={tall}
      />
      <Panel
        title={t("compare.dataset")}
        note={t("compare.datasetNote", { count: datasetSheet.data?.tiles.length ?? 0 })}
        pager={<Pager sheet={datasetSheet.data} onPage={setPage} />}
        sheet={datasetSheet.data}
        onOpen={tall ? undefined : () => setOpen(true)}
        tall={tall}
      />
    </>
  );
  return (
    <section aria-labelledby="compare-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="compare-title" className="m-0 text-large">
          {t("compare.title")}
        </h2>
        <span className="text-body text-muted-foreground">{t("compare.how")}</span>
      </div>
      <div className="grid grid-cols-2 items-start gap-3.5 max-[700px]:grid-cols-1">
        {panels(false)}
      </div>
      <Dialog open={open} onOpenChange={setOpen} title={t("compare.title")} full>
        <div className="grid h-full grid-cols-2 gap-3 p-3">{panels(true)}</div>
      </Dialog>
    </section>
  );
}
