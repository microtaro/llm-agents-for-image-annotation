// The library's bar, as a dataset's (definition 60.2): on every screen the datasets are chosen
// with their rings (not recorded) and the screen's one decision is made (recorded). Taking in
// opens its window whatever is chosen (what to do is chosen there); deleting needs some chosen;
// writing out, no decision (nothing changes), heads its line with its own name.
import type { DatasetSummary } from "@/api/types";
import { ChooseLine, DecideLine } from "@/components/ChooseLine";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import type { LibraryScreen } from "@/lib/viewState";
import { useState } from "react";
import { DeleteDialog } from "./DatasetDialogs";
import { ExportDialog } from "./LibraryExport";
import { ImportDialog } from "./LibraryImport";

type Open = LibraryScreen | null;

/** The bar of the datasets chosen for the screen's decision, as the gallery's selection bar. */
export function LibrarySelectionBar({
  screen,
  chosen,
  onClear,
  shown,
  found,
  onChosen,
}: {
  screen: LibraryScreen;
  chosen: DatasetSummary[];
  onClear: () => void;
  /** The datasets the finding shows, and choosing them at once (19.0). */
  shown: string[];
  /** The finding narrows what is shown (a search written). */
  found: boolean;
  onChosen: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState<Open>(null);
  const one = chosen.length === 1 ? chosen[0] : null;
  return (
    <div
      role="region"
      aria-label={t("library.chosen.label")}
      className="sticky top-0 z-20 flex flex-col gap-1.5 border-b-2 border-ink bg-sheet px-5 py-2 text-body"
    >
      {/* Choosing (not recorded) and deciding (recorded), each its line, as the gallery's. */}
      <ChooseLine
        who={
          chosen.length
            ? t("library.chosen.count", { count: chosen.length })
            : t("library.chosen.none")
        }
        hint={!chosen.length}
        by={{ found }}
        datasets
        shown={shown}
        chosen={chosen.map((d) => d.id)}
        onChosen={onChosen}
        onClear={onClear}
      />
      <DecideLine name={screen === "export" ? t("library.screen.export") : undefined}>
        {screen === "import" && (
          <>
            <Button size="small" variant="primary" onClick={() => setOpen("import")}>
              {t("library.import")}…
            </Button>
            {/* What it will do first, by how many are chosen (the window's first choice). */}
            <span className="text-muted-foreground">
              {one
                ? t("library.import.hint.one", { name: one.name })
                : chosen.length
                  ? t("library.import.hint.many", { count: chosen.length })
                  : t("library.import.hint.none")}
            </span>
          </>
        )}
        {screen === "delete" && (
          <Button
            size="small"
            variant="destructive"
            disabled={!chosen.length}
            title={chosen.length ? undefined : t("library.why.some")}
            onClick={() => setOpen("delete")}
          >
            {t("library.delete")}…
          </Button>
        )}
        {screen === "export" && (
          <>
            <Button
              size="small"
              variant="primary"
              disabled={!chosen.length}
              title={chosen.length ? undefined : t("library.why.some")}
              onClick={() => setOpen("export")}
            >
              {t("library.export")}…
            </Button>
            <span className="text-muted-foreground">{t("library.export.hint")}</span>
          </>
        )}
      </DecideLine>
      <ImportDialog open={open === "import"} datasets={chosen} onClose={() => setOpen(null)} />
      <ExportDialog open={open === "export"} datasets={chosen} onClose={() => setOpen(null)} />
      <DeleteDialog
        datasets={open === "delete" ? chosen : []}
        onClose={() => setOpen(null)}
        onDeleted={() => (setOpen(null), onClear())}
      />
    </div>
  );
}
