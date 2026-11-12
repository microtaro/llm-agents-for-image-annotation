// The gallery as a table (step 13 design 1): one row per object of what is looked at, children
// indented under their parent, attribute values as columns. Sort by a column, find by words,
// empty or repeated values; a row opens the loupe on that object.
import { useEffect, useMemo, useRef } from "react";
import type { GalleryItem, PutLabel, View } from "@/api/types";
import { failuresOf, shownPills } from "./GalleryCard";
import { ChooseRing } from "@/components/ChooseRing";
import { LabelDot } from "@/components/LabelColors";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import {
  attributeColumns,
  buildRows,
  findRows,
  labelColumns,
  type Mode,
  noAnswer,
  sortRows,
} from "@/lib/table";

export function GalleryTable({
  items,
  labels,
  view,
  find,
  picking,
  onOpen,
  lastObject = null,
  colors = {},
}: {
  items: GalleryItem[];
  /** The labels of the plan the images are judged by (usePlanLabels): their attributes are
   * the columns, empty where no value is yet. */
  labels: PutLabel[] | null;
  /** Label -> color, for the mark beside each object's label. */
  colors?: Record<string, string>;
  /** What is looked at, for each image's state as on its card. */
  view: View;
  /** The finding words and mode, kept for the tab (lib/viewState). */
  find: {
    text: string;
    mode: string;
    column: string | null;
    up: boolean;
    set: (text: string, mode: string) => void;
    sort: (column: string | null, up: boolean) => void;
  };
  /** The card's ring here too (user 2026-10-13: one with it): choosing, or "use for
   * training" while using for training. */
  picking?: {
    /** Using for training (else choosing images). */
    use: boolean;
    /** The image's ring as on its card; none: nothing to use. */
    ringOf: (
      imageId: string,
    ) => { on: boolean; done?: boolean; label: string; set: (on: boolean) => void } | null;
  };
  onOpen: (imageId: string, annotationId: string | null) => void;
  /** The object last chosen in the loupe: its row brought into view. */
  lastObject?: string | null;
}) {
  const text = find.text;
  const mode = find.mode as Mode;
  const { column, up } = find;
  const columns = useMemo(() => attributeColumns(items, labels), [items, labels]);
  const rows = useMemo(() => buildRows(items), [items]);
  const own = useMemo(() => labelColumns(rows, labels), [rows, labels]);
  const shown = sortRows(findRows(rows, text, mode, columns, labels), column, up);
  // Each image's state on its first row, the card's pill (Astra 2026-10-06: in the table
  // "not made", "stopped", "not adopted" and "no objects" all looked the same).
  const stateOf = useMemo(
    () => new Map(items.map((item) => [item.image.id, shownPills(item, view)])),
    [items, view],
  );
  const failed = useMemo(
    () => new Map(items.map((item) => [item.image.id, failuresOf(item)])),
    [items],
  );
  const body = useRef<HTMLTableSectionElement>(null);
  // Once per object, when its row is there: the rows come after the screen opens (found
  // 2026-10-16: back from the loupe the row was below the window), and a later reload of the
  // data does not scroll again.
  const scrolled = useRef<string | null>(null);
  useEffect(() => {
    if (!lastObject || scrolled.current === lastObject) return;
    const row = body.current?.querySelector(`[data-object="${CSS.escape(lastObject)}"]`);
    if (!row) return;
    scrolled.current = lastObject;
    row.scrollIntoView({ block: "center" });
  }, [lastObject, rows]);
  const unanswered = useMemo(
    () => new Set(items.filter((i) => noAnswer(i, view)).map((i) => i.image.id)),
    [items, view],
  );
  // The rows that begin an image (its first, or one sorted apart from the row above): its ring
  // and name there only, the rows under it left empty (user 2026-10-16: a second row with its
  // own ring and name read as another image; one image, one ring).
  const opens = new Set(
    shown.filter((row, i) => i === 0 || shown[i - 1].imageId !== row.imageId).map((r) => r.key),
  );
  const ringCell = (imageId: string) => {
    const ring = picking?.ringOf(imageId);
    if (ring)
      return (
        <ChooseRing
          inline
          chosen={ring.on}
          label={ring.label}
          use={Boolean(picking?.use)}
          done={Boolean(ring.done)}
          onChoose={ring.set}
        />
      );
    // Nothing to use: the cell left empty, the names lined up beside it (user 2026-10-16).
    return null;
  };
  const head = (key: string, label: string) => (
    <th key={key} className="sticky top-0 bg-sheet px-2 py-1 text-left font-semibold">
      <button
        type="button"
        className="cursor-pointer whitespace-nowrap"
        onClick={() => find.sort(key, column === key ? !up : true)}
      >
        {label}
        {column === key ? (up ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );
  return (
    // Its room around is the place's that shows it (the gallery's edges, a set's section).
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-body">
        <input
          aria-label={t("table.find")}
          placeholder={t("table.find")}
          value={text}
          onChange={(e) => find.set(e.target.value, mode)}
          className="w-64 rounded-md border border-line bg-surface px-2 py-1"
        />
        {/* Named apart from the image-state filter above (Astra 2026-10-06: two "filter ·
            all" and which to clear). */}
        <span className="text-muted-foreground">{t("table.mode")}</span>
        <select
          aria-label={t("table.mode")}
          value={mode}
          onChange={(e) => find.set(text, e.target.value)}
          className="rounded-md border border-line bg-surface px-2 py-1"
        >
          <option value="all">{t("table.mode.all")}</option>
          <option value="empty">{t("table.mode.empty")}</option>
          <option value="same">{t("table.mode.same")}</option>
        </select>
        <span className="text-muted-foreground">
          {t("table.count", { count: shown.length, total: rows.length })}
        </span>
        <span className="text-xs text-muted-foreground">{t("table.open")}</span>
      </div>
      <div className="max-h-[70vh] overflow-auto rounded-md border border-line bg-surface">
        <table className="w-full border-collapse text-body">
          <thead>
            <tr className="border-b border-line">
              {picking && (
                <th className="sticky top-0 w-8 bg-sheet px-2 py-1">
                  <span className="sr-only">{t("table.ring")}</span>
                </th>
              )}
              {head("image", t("table.image"))}
              {head("label", t("table.label"))}
              {head("number", t("table.number"))}
              {head("parent", t("table.parent"))}
              {columns.map((c) => head(c, c))}
            </tr>
          </thead>
          <tbody ref={body}>
            {rows.length > 0 && shown.length === 0 && (
              <tr>
                <td
                  colSpan={(picking ? 6 : 5) + columns.length}
                  className="px-2 py-3 text-muted-foreground"
                >
                  {t("common.noneFound")}{" "}
                  {/* The same button as the library's (Astra 2026-10-06: a link here). */}
                  <Button size="small" onClick={() => find.set("", "all")}>
                    {t("common.clearFind")}
                  </Button>
                </td>
              </tr>
            )}
            {shown.map((row) => (
              <tr
                key={row.key}
                onClick={() => onOpen(row.imageId, row.annotationId)}
                title={t("table.open")}
                data-object={row.annotationId ?? undefined}
                // The object last looked at in the loupe is only scrolled to, not coloured (user
                // 2026-10-16: one row coloured with nothing saying why).
                className="cursor-pointer border-b border-line last:border-0 hover:bg-hover"
              >
                {picking && (
                  // The image's ring, as on its card, in a column of its own so the names line
                  // up with nothing before them, told apart by shape, not words (user
                  // 2026-10-16).
                  <td className="w-8 px-2 py-1" onClick={(e) => e.stopPropagation()}>
                    {opens.has(row.key) && ringCell(row.imageId)}
                  </td>
                )}
                <td
                  // Narrow, the notes wrapping, so the attribute columns stay in view (Astra
                  // 2026-10-07: the image column took 460 of 611px in ①).
                  // relative: the name kept for a screen reader under the first row is placed
                  // here, not at the page (found 2026-10-16: it made the page itself scroll, a
                  // second scrollbar beside the right side's).
                  className="relative max-w-64 min-w-40 px-2 py-1 text-body"
                >
                  {/* As on the card: the name in plain bold, the whole row opens it (Astra
                      2026-10-07: a small underlined code font read as a side note). */}
                  {/* Under the image's first row, said to a screen reader only. */}
                  <span
                    className={opens.has(row.key) ? "whitespace-nowrap font-semibold" : "sr-only"}
                  >
                    {row.imageName}
                  </span>
                  {opens.has(row.key) &&
                    stateOf.get(row.imageId)?.map((pill) => (
                      <span key={pill.text} className={`ml-2 ${pill.look}`}>
                        {pill.text}
                      </span>
                    ))}
                  {/* As on the card: the failures since the last success, the reason on hover. */}
                  {opens.has(row.key) && failed.get(row.imageId) && (
                    <span
                      className="ml-2 text-xs text-failed"
                      title={failed.get(row.imageId)?.full}
                    >
                      {failed.get(row.imageId)?.short}
                    </span>
                  )}
                </td>
                <td className="px-2 py-1" style={{ paddingLeft: `${0.5 + row.depth * 1.25}rem` }}>
                  {row.annotationId ? (
                    <>
                      <LabelDot color={colors[row.label]} />
                      {row.label}
                    </>
                  ) : unanswered.has(row.imageId) ? (
                    // As the gallery says it (Sol 2026-10-13: "earlier requirement only" and
                    // "no result" side by side).
                    items.find((i) => i.image.id === row.imageId)?.badge.kind === "stale" ? (
                      t("filter.stale")
                    ) : (
                      t("table.noResult")
                    )
                  ) : (
                    t("table.none")
                  )}
                </td>
                <td className="px-2 py-1">{row.number ?? ""}</td>
                <td className="px-2 py-1 text-muted-foreground">{row.parent}</td>
                {columns.map((c) => (
                  <td key={c} className="px-2 py-1">
                    {row.values[c] ??
                      (row.annotationId && !own.get(row.label)?.has(c) ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        ""
                      ))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
