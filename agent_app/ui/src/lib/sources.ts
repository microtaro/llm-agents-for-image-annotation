// Where a dataset's images came from, one line per folder, for the library card and the
// dataset's header alike (2026-10-29: the card left a folder not recorded blank).
import type { DatasetSummary } from "@/api/types";
import { t } from "@/i18n";

export function sourceLines(sources: DatasetSummary["sources"]): string[] {
  return sources.map(
    (s) =>
      `${t("dataset.source")} ${s.folder ?? t("dataset.source.unknown")} ${t("common.images", { count: s.count })}`,
  );
}
