// A list of images, the one way images are listed everywhere (definition 36.2; user 2026-10-28:
// "if they are boxes, they would be the same"): the gallery, the plan's sets, a set shown and a
// record's images. Each image judged by the plan of the list (a result of that plan's requirement
// drawn; one of another plan's only, "version n's result only", undrawn), the list's head row
// (ImageListHead: the order, cards or table and the eye), the cards and the table (one row per
// object), and a card or a row opens the loupe. A place adds only what its work needs: the
// gallery its rings and marks (GalleryItems), a record its "Again", a sample its "make it the
// reference". The layout is the same whatever the states (DESIGN.md: same place, same form; user
// 2026-10-22: the screen stays, what it shows changes).
import { type ReactNode, useEffect, useMemo, useState } from "react";
import type { GalleryItem, StageName, View } from "@/api/types";
import { listShows, useDisplay } from "@/lib/display";
import { takeFocusImage } from "@/lib/focusBack";
import { go, imageLoupe, type PlanRef } from "@/lib/route";
import { orderImages } from "@/lib/shown";
import { useViewArea } from "@/lib/useZoomPan";
import { useImageOrder, useLastObject, useTableFind } from "@/lib/viewState";
import { GalleryCard } from "./GalleryCard";
import { GalleryTable } from "./GalleryTable";
import { ImageListHead } from "./ListHead";
import { attributeColumns } from "@/lib/table";
import { usePlanLabels, usePlanSeen } from "@/lib/planParts";

/** An image's ring: chosen for a button, or used for training (the card's ring, the row's tick). */
export interface Ring {
  on: boolean;
  /** Annotated already (the ring's edge), apart from being chosen. */
  done?: boolean;
  label: string;
  set: (on: boolean) => void;
}

/** What a place marks on a card (the gallery: a box's targets, the run going, the AI's touch). */
export interface CardMarks {
  highlighted?: boolean;
  tag?: string;
  going?: string;
  targeted?: boolean;
}

export function ImageSet({
  datasetId,
  items,
  view,
  colors,
  plan,
  eyePlan = plan,
  title,
  note,
  warning,
  stage,
  recordId,
  table: tableOffered = true,
  picking,
  marks,
  cardAction,
}: {
  datasetId: string;
  /** The images, judged by the plan (the gallery's or a type's query with it). */
  items: GalleryItem[];
  /** How a card reads: a record's results ("run"), else each image as it is ("adoption"). */
  view: View;
  colors: Record<string, string>;
  /** The plan they are judged by: the loupe opened from a card keeps it. */
  plan: PlanRef | null;
  /** The plan of the eye's label colors, when not that one (the gallery's record shown: its
   * version). */
  eyePlan?: PlanRef | null;
  title?: string;
  /** Beside the title (how many are done). */
  note?: string;
  /** Under the title: what the set lacks. */
  warning?: string;
  /** The gallery's stage: the loupe opens at it and the table's finding is its own. */
  stage?: StageName;
  /** The record the loupe opens at (the gallery's record shown, a record's images); none: each
   * card's own record in a record's view. */
  recordId?: string | null;
  /** Cards or table offered (not while a box shown has its own switches: cards then). */
  table?: boolean;
  /** Choosing images, or using them for training: the card's ring and the row's tick are one. */
  picking?: { use: boolean; ringOf: (item: GalleryItem) => Ring | null };
  marks?: (item: GalleryItem) => CardMarks;
  /** Under a card's name: an operation of the place on that image. */
  cardAction?: (item: GalleryItem) => ReactNode;
}) {
  const display = useDisplay();
  // The plan's labels: their attributes are the table's columns (definition 85).
  const labels = usePlanLabels(datasetId, usePlanSeen(datasetId, plan));
  const valuesShown = useMemo(() => attributeColumns(items, labels).length > 0, [items, labels]);
  const shows = listShows(display, tableOffered, valuesShown);
  const [order] = useImageOrder(datasetId);
  const find = useTableFind(datasetId, stage ?? "set");
  const [lastObject] = useLastObject(datasetId);
  const shown = orderImages(items, order);
  // The cards' room: the size's slider ends at one card across (user 2026-10-07: the big end of
  // the slider, of no use, was most of it).
  const [cards, setCards] = useState<HTMLDivElement | null>(null);
  const cardsRef = useMemo(() => ({ current: cards }), [cards]);
  const cardsWidth = useViewArea(cardsRef).width;
  // Back from the loupe: its card takes the focus again; with the table shown and an object
  // looked at, without scrolling to the card, so the table's scroll to that object's row stays
  // (found 2026-10-16: the card's focus scrolled back over it).
  useEffect(() => {
    const id = takeFocusImage();
    if (id)
      document
        .querySelector<HTMLElement>(`[data-image="${CSS.escape(id)}"] [role="button"]`)
        ?.focus({ preventScroll: shows.table && Boolean(lastObject) });
    // Only on coming back, not when the view changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const open = (imageId: string, objectId: string | null = null) => {
    const item = items.find((i) => i.image.id === imageId);
    const record = recordId ?? (view === "run" ? (item?.badge.record_id ?? null) : null);
    go({
      screen: "loupe",
      datasetId,
      ...imageLoupe(imageId, plan, record, stage),
      ...(objectId ? { objectId } : {}),
    });
  };
  return (
    <section className="flex flex-col gap-3">
      <ImageListHead
        datasetId={datasetId}
        plan={eyePlan}
        title={title}
        note={note}
        // A size over half the room is one card across (gap-3 12px).
        cardMax={shows.cards && cards ? Math.round((cardsWidth - 12) / 2) + 10 : undefined}
        table={tableOffered}
        valuesShown={valuesShown}
      />
      {warning && <p className="m-0 text-body">{warning}</p>}
      {shows.cards && (
        <div
          ref={setCards}
          className="grid gap-3"
          style={{
            gridTemplateColumns: `repeat(auto-fill, minmax(min(${display.cardSize}px, 100%), 1fr))`,
          }}
        >
          {shown.map((item) => {
            const ring = picking?.ringOf(item) ?? null;
            return (
              <GalleryCard
                key={item.image.id}
                item={item}
                view={view}
                colors={colors}
                chosen={ring?.on}
                ringLabel={ring?.label}
                ringUse={picking?.use}
                ringDone={ring?.done}
                onChoose={ring ? (on) => ring.set(on) : undefined}
                {...marks?.(item)}
                onOpen={() => open(item.image.id)}
              >
                {cardAction?.(item)}
              </GalleryCard>
            );
          })}
        </div>
      )}
      {shows.table && (
        <GalleryTable
          items={shown}
          labels={labels}
          view={view}
          colors={colors}
          find={find}
          lastObject={lastObject}
          picking={
            picking && {
              use: picking.use,
              ringOf: (imageId) => {
                const item = items.find((i) => i.image.id === imageId);
                return item ? picking.ringOf(item) : null;
              },
            }
          }
          onOpen={open}
        />
      )}
    </section>
  );
}
