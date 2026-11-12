// The row over a list (user 2026-10-28: the way it is shown belongs right over the list, not in
// the filters' row above the decisions): its title on the left, and at the right end how it is
// shown, the order first. The same in every list: the library's datasets, and every list of
// images (ImageListHead: the gallery's, the plan's sets, a set shown) with cards or table and the
// eye last.
import type { ReactNode } from "react";
import { SetEye } from "@/components/LooksMenu";
import { t } from "@/i18n";
import { listShows, setDisplay, useDisplay } from "@/lib/display";
import type { PlanRef } from "@/lib/route";
import { IMAGE_ORDERS, type ImageOrder } from "@/lib/shown";
import { useImageOrder } from "@/lib/viewState";

export function ListHead({
  title,
  note,
  children,
}: {
  title?: string;
  /** Beside the title (how many are done, how much is kept). */
  note?: string;
  /** At the right end: how the list is shown. */
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {title && <h2 className="m-0 text-large">{title}</h2>}
      {note && <span className="text-body text-muted-foreground">{note}</span>}
      <span className="flex-1" />
      {children}
    </div>
  );
}

/** The order of a list, in the same words and form wherever a list has one. */
export function OrderChoice<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 text-body text-muted-foreground">
      {t("list.order")}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="rounded-md border border-line bg-surface px-2 py-0.5 text-ink"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** A list of images' row: the dataset's image order, cards or table, and the eye. */
export function ImageListHead({
  datasetId,
  plan,
  title,
  note,
  cardMax,
  table = true,
  valuesShown = false,
}: {
  datasetId: string;
  /** The plan the images are judged by: its label colors in the eye. */
  plan: PlanRef | null;
  title?: string;
  note?: string;
  /** The biggest card the eye's size slider goes to. */
  cardMax?: number;
  /** Cards or table offered (not while a box shown has its own switches). */
  table?: boolean;
  /** The results shown read values: the table is on until the person turns it off. */
  valuesShown?: boolean;
}) {
  const [order, setOrder] = useImageOrder(datasetId);
  return (
    <ListHead title={title} note={note}>
      <OrderChoice<ImageOrder>
        value={order}
        options={IMAGE_ORDERS.map((o) => ({ value: o, label: t(`gallery.order.${o}`) }))}
        onChange={setOrder}
      />
      {table && <CardsOrTable valuesShown={valuesShown} />}
      <SetEye datasetId={datasetId} plan={plan} cardMax={cardMax} />
    </ListHead>
  );
}

/** Cards, table or both, one choice for every list of images (user 2026-10-28: the plan's
 * images had the eye only): each on or off, at least one on, as a decision's image and data. */
function CardsOrTable({ valuesShown }: { valuesShown: boolean }) {
  const shows = listShows(useDisplay(), true, valuesShown);
  return (
    <div className="flex gap-1" role="group" aria-label={t("table.layout")}>
      {(["cards", "table"] as const).map((key) => {
        const other = key === "cards" ? "table" : "cards";
        return (
          <button
            key={key}
            type="button"
            aria-pressed={shows[key]}
            title={shows[key] && !shows[other] ? t("decision.shown.last") : undefined}
            onClick={() => {
              if (shows[key] && !shows[other]) return;
              // Both written: the table's state is the person's choice from now on.
              setDisplay({ ...shows, [key]: !shows[key] });
            }}
            className={`cursor-pointer rounded-md border px-2.5 py-0.5 text-body ${shows[key] ? "border-ink bg-selected font-semibold text-ink" : "border-line bg-surface"}`}
          >
            {t(key === "table" ? "table.layout.table" : "table.layout.cards")}
          </button>
        );
      })}
    </div>
  );
}
