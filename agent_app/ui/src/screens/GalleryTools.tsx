// The filters' row (definition 37.2): which images are shown, the record and the state chips
// with counts; how they are shown (the order, cards or table, the eye) is the list's head right
// over them (ListHead; user 2026-10-28). While a decision's targets are shown, its own chips
// stand in the filter's place (the agent app, 10-09).
import type { ReactNode } from "react";
import type { GalleryItem, StageName } from "@/api/types";
import { t } from "@/i18n";
import { groupCounts } from "@/lib/filters";

export function GalleryTools({
  stage,
  items,
  filter,
  onFilter,
  targets,
  targetsOnly = false,
}: {
  stage: StageName;
  items: GalleryItem[];
  filter: string | null;
  onFilter: (group: string | null) => void;
  /** A decision's "targets / the others" chips, in the filter's place. */
  targets?: ReactNode;
  /** Only the targets shown: the filter chips stand aside. */
  targetsOnly?: boolean;
}) {
  const groups = stage === "instruction" ? [] : groupCounts(items, stage);
  const chip = (on: boolean) =>
    // Looking, not deciding: the operation's colour is for what changes things (DESIGN.md;
    // user 2026-10-13: a chosen filter looked as weighty as a decision).
    `cursor-pointer rounded-md border px-2.5 py-0.5 text-body ${on ? "border-ink bg-selected font-semibold text-ink" : "border-line bg-surface text-ink"}`;

  return (
    <>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line bg-sheet px-5 py-2">
        {targets}
        {!targetsOnly && groups.length > 0 && (
          <div
            className="flex flex-wrap items-center gap-1.5"
            role="group"
            aria-label={t("filter.title")}
          >
            <span className="text-body text-muted-foreground">{t("filter.title")}</span>
            <button
              type="button"
              aria-pressed={filter === null}
              className={chip(filter === null)}
              onClick={() => onFilter(null)}
            >
              {t("filter.all")} {items.length}
            </button>
            {groups.map(([group, count]) => (
              <button
                key={group}
                type="button"
                aria-pressed={filter === group}
                className={chip(filter === group)}
                onClick={() => onFilter(group)}
              >
                {t(`filter.${group}`)} {count}
              </button>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
