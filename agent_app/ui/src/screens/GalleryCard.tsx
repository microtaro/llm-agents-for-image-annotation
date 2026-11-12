// One image of the gallery: thumbnail, its annotations, the badge of what is being looked at,
// and wheel zoom with drag (DESIGN.md 5). A click without a drag opens the loupe.
import { type ReactNode, useEffect } from "react";
import { thumbnailUrl } from "@/api/client";
import type { Badge, GalleryItem, View } from "@/api/types";
import { Shapes } from "@/components/Shapes";
import { ChooseRing } from "@/components/ChooseRing";
import { t, when } from "@/i18n";
import { labelCounts, useDisplay } from "@/lib/display";
import { useZoomPan } from "@/lib/useZoomPan";
import { type ModelName, modelLabel, spentText, useModelName, versionOf } from "@/lib/runChoice";

const PILL = "whitespace-nowrap rounded-md px-1.5 text-note leading-[1.6]";
const LOOK: Record<string, string> = {
  good: `${PILL} bg-annotated text-fill-ink`,
  bad: `${PILL} bg-failed text-fill-ink`,
  busy: `${PILL} bg-processing text-bright-fill-ink`,
  // The adopted result: the green of the same result's "succeeded".
  run: `${PILL} bg-annotated text-fill-ink`,
  none: `${PILL} border border-line bg-surface text-muted-foreground`,
  // Annotated (the green's outline): the state before "used for training" (user 2026-10-13).
  // Not green (Sol 2026-10-13: both pills read as green): the plain outline of a state.
  annotated: `${PILL} border border-ink bg-surface text-ink`,
};

/** The state pills on the name's line (user 2026-10-13): annotated first, then whether it is
 * used for training beside it ([annotated][used]); a person's fix says so in the first. */
export function pillsOf(item: GalleryItem): { look: string; text: string }[] | null {
  const { badge } = item;
  const first = {
    look: badge.by === "human" ? LOOK.good : LOOK.annotated,
    // Who made it (user 2026-10-14: a person's fix is annotated too; "annotated" meant the AI's;
    // definition 60.11: one taken in is neither).
    text: t(
      badge.by === "human"
        ? "badge.result.human"
        : badge.by === "import"
          ? "badge.result.imported"
          : "badge.byAi",
    ),
  };
  if (badge.kind === "result") return [first, { look: LOOK.run, text: t("badge.result.short") }];
  // The newest annotation (annotating with AI): who made it only, not whether training uses it
  // (user 2026-10-14: that is the other decision's).
  if (badge.succeeded) return [first];
  if (badge.kind === "excluded")
    return [
      // Who made the record it would use (found 2026-10-16: a person's fix said "by the AI").
      ...(badge.ran ? [first] : []),
      { look: LOOK.none, text: t("badge.excluded") },
    ];
  return null;
}

/** The pills of an image's state, the same on its card, in the loupe and in the table (user
 * 2026-10-16: the table said "annotated" where the card said "by the AI"). */
export function shownPills(item: GalleryItem, view: View): { look: string; text: string }[] {
  const pills = view === "run" || view === "adoption" ? pillsOf(item) : null;
  if (pills) return pills;
  const { look, text } = describe(item, view);
  return text ? [{ look, text }] : [];
}

/** The runs that failed since the image's last success, by version, said on its card and in
 * the table so retrying or fixing the plan is decided there (user 2026-10-16: a failure after
 * a success was hidden, and the loupe is not where one decides). */
export function failuresOf(item: GalleryItem): { short: string; full: string } | null {
  return failuresText(item.badge.failures);
}

/** The failures of an image's state (image_state.py), as the card says them; a decision's
 * images say them the same way. */
export function failuresText(failures: Badge["failures"]): { short: string; full: string } | null {
  if (!failures?.parts.length) return null;
  const parts = failures.parts
    .map((p) => t("failures.part", { revision: p.revision, count: p.count }))
    .join(t("failures.join"));
  return {
    short: t("failures.short", { parts }),
    full: failures.reason ? t("failures.line", { parts, reason: failures.reason }) : "",
  };
}

/** Whether the card says "in the run going now" on its image: not when its own pill says the
 * same (user 2026-10-15: "annotating" twice on one image). */
export function showGoing(going: string | undefined, badge: Pick<Badge, "waiting">): boolean {
  return Boolean(going) && !badge.waiting;
}

/** The badge's look and words: the same on the card, in the loupe and in the table. */
export function describe(item: GalleryItem, view: View): { look: string; text: string } {
  const { badge } = item;
  const look =
    {
      detected: LOOK.good,
      not_detected: LOOK.good,
      failed: LOOK.bad,
      running: LOOK.busy,
      result: LOOK.run,
    }[badge.kind] ?? LOOK.none;
  // The adopted result: a short badge, the run under the name (Astra 2026-10-06: the long badge
  // cut the file name down to "C..").
  const text =
    badge.kind === "result"
      ? t(badge.by === "human" ? "badge.result.human" : "badge.result.short")
      : view === "images"
        ? ""
        : // Which version's labels, by number (user 2026-10-13: "an earlier requirement").
          badge.kind === "stale" && badge.earlier_revision
          ? t("badge.stale.version", { revision: badge.earlier_revision })
          : t(`badge.${badge.kind}`);
  return { look, text };
}

/** The line under the card's name (step 18: the long badge cut the name to "S2_00…"): what it
 * took, the record it came from with its model by its name, the objects. */
export function cardLine(item: GalleryItem, view: View, name: ModelName): string {
  const { badge, annotations } = item;
  // Time and cost first on the line, so a long list never hides them (Astra 2026-10-06).
  const took =
    view === "run" && badge.elapsed_ms ? spentText(badge.elapsed_ms, badge.cost_usd) : "";
  // The adopted result, and a run's: which run it came from.
  const from =
    badge.kind === "result" ||
    (badge.kind === "stale" && badge.record_at) ||
    (view === "run" && badge.record_at)
      ? t("badge.result", {
          number: badge.record_number ?? "",
          version: badge.record_revision == null ? "" : versionOf(badge.record_revision),
          time: when(badge.record_at),
          model: modelLabel(badge.model, badge.record_kind, name),
        })
      : "";
  return [
    took,
    // Tried in ① (user 2026-10-13: a trial is a run of the version, shown in ② as one), before
    // the record so a narrow card keeps it (user 2026-10-27: the plan's images).
    badge.trial ? t("badge.trial") : "",
    // Made by other criteria and not checked: not done by this one (85.4); before
    // the record (which says its version) so a narrow card keeps it, as a trial.
    badge.other ? t("badge.otherCriteria") : "",
    from,
    // A person's choice, and a newer annotation after it (types design 7.2).
    badge.picked && badge.by !== "human" ? t("badge.picked") : "",
    badge.newer ? t("badge.newer") : "",
    labelCounts(annotations),
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * The thumbnail's longer side for a card of this size: sharp, but not the original. A card
 * stretches to fill its row, up to about twice the chosen size.
 */
export function thumbnailSide(cardSize: number): number {
  return cardSize <= 240 ? 480 : cardSize <= 500 ? 1024 : 2048;
}

export function GalleryCard({
  item,
  view,
  chosen,
  ringLabel,
  ringUse = false,
  ringDone = false,
  onChoose,
  targeted = false,
  colors,
  onOpen,
  highlighted = false,
  going,
  tag,
  children,
}: {
  item: GalleryItem;
  view: View;
  /** Chosen for a button of the selection bar, by the ring at the top left (none: no choosing
   * here). */
  chosen?: boolean;
  /** What the ring says (choosing, or "use for training" while using for training). */
  ringLabel?: string;
  /** The ring is "used for training" (green when on, as the pill), not a choice (indigo). */
  ringUse?: boolean;
  /** The state now, on the ring's edge (annotated: green), apart from its fill (chosen). */
  ringDone?: boolean;
  onChoose?: (on: boolean) => void;
  /** A touched button of the selection bar works on this image: its frame says so. */
  targeted?: boolean;
  colors: Record<string, string>;
  onOpen: () => void;
  /** In the run going now (seen from another view): waiting or being worked on. */
  going?: string;
  /** Touched by the AI's last answer: marked for a moment. */
  highlighted?: boolean;
  /** What the decision shown does to this image ("Run", "Leave out"; agent app 4.3). */
  tag?: string;
  /** Below the name: an operation of the view the card is in (a failed run's "Again"). */
  children?: ReactNode;
}) {
  const zoom = useZoomPan<HTMLDivElement>();
  // "Reset display" also puts each card's own zoom back.
  const { epoch, cardSize } = useDisplay();
  const { reset } = zoom;
  useEffect(() => reset(), [epoch, reset]);
  const line = cardLine(item, view, useModelName());
  // No image is faded (user 2026-10-16): one left out of training says so by its ring and its
  // "not used for training" pill, and stays an image like the others (Astra 2026-10-07: faded
  // looked unusable; the loupe never faded it).
  return (
    <div
      data-image={item.image.id}
      // The frame: a touched button's target in the action color, a chosen one thick.
      className={`flex flex-col overflow-hidden rounded-md border bg-sheet ${targeted ? "border-action ring-4 ring-action" : chosen ? "border-ink ring-2 ring-ink" : highlighted ? "border-action ring-2 ring-action" : "border-line"}`}
    >
      <div
        ref={zoom.ref}
        role="button"
        tabIndex={0}
        aria-label={t("gallery.open", { name: item.image.name })}
        onKeyDown={(event) => event.key === "Enter" && onOpen()}
        onPointerDown={zoom.onPointerDown}
        onPointerMove={zoom.onPointerMove}
        onPointerUp={() => !zoom.onPointerUp() && onOpen()}
        onDoubleClick={zoom.reset}
        className="relative aspect-square cursor-pointer touch-none overflow-hidden bg-backdrop"
      >
        {chosen !== undefined && (
          <ChooseRing
            chosen={chosen}
            label={ringLabel ?? t("select.one", { name: item.image.name })}
            use={ringUse}
            done={ringDone}
            onChoose={(on) => onChoose?.(on)}
          />
        )}
        {tag && (
          <span className="absolute bottom-1.5 left-1.5 z-10 rounded bg-processing px-1.5 text-note font-bold text-ink">
            {tag}
          </span>
        )}
        {/* Not when the card's own pill says it already (user 2026-10-15: "annotating" twice on
            one image once the newest annotation was shown while annotating with AI). */}
        {showGoing(going, item.badge) && (
          <span
            className={`absolute right-1.5 bottom-1.5 z-10 ${going === "running" ? LOOK.busy : LOOK.none}`}
          >
            {t(`badge.${going}`)}
          </span>
        )}
        <div
          className="absolute inset-0 origin-top-left"
          style={{
            transform: `translate(${zoom.view.x}px, ${zoom.view.y}px) scale(${zoom.view.scale})`,
          }}
        >
          <img
            src={thumbnailUrl(item.image.id, thumbnailSide(cardSize))}
            alt={item.image.name}
            // Cards out of view load as they come near (review 2026-10-07: 120 thumbnails,
            // 3.1MB, were all asked for at once).
            loading="lazy"
            decoding="async"
            draggable={false}
            className="block size-full object-contain"
          />
          <ShapesInBox item={item} colors={colors} zoom={zoom.view.scale} cardSize={cardSize} />
        </div>
      </div>
      <div className="flex flex-col gap-px px-2.5 py-1.5">
        {/* The pills go under the name when the card is narrow (10-13: two pills cut the name
            to "C0…"). */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className="min-w-[6rem] flex-1 truncate text-body font-semibold"
            title={item.image.name}
          >
            {item.image.name}
          </span>
          {shownPills(item, view).map((pill) => (
            <span key={pill.text} className={pill.look}>
              {pill.text}
            </span>
          ))}
        </div>
        {/* Cut to one line; the whole of it on hover, as the failures' line (user 2026-10-16:
            the model and the label counts were cut off with no way to read them). */}
        <div className="truncate text-xs text-muted-foreground" title={line || undefined}>
          {line || "—"}
        </div>
        {failuresOf(item) && (
          <div className="truncate text-xs text-failed" title={failuresOf(item)?.full}>
            {failuresOf(item)?.full || failuresOf(item)?.short}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

/** The annotations over an object-contain image, in a box of the image's own shape. */
function ShapesInBox({
  item,
  colors,
  zoom,
  cardSize,
}: {
  item: GalleryItem;
  colors: Record<string, string>;
  zoom: number;
  cardSize: number;
}) {
  const { width, height } = item.image;
  const wide = width >= height;
  return (
    <div
      className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
      style={{
        width: wide ? "100%" : `${(width / height) * 100}%`,
        height: wide ? `${(height / width) * 100}%` : "100%",
      }}
    >
      <Shapes
        width={width}
        height={height}
        annotations={item.annotations}
        colors={colors}
        // "label number" on the cards too, as in the loupe (user 2026-10-05); the display row's
        // "label names" and their size decide, the same as there.
        shownHeight={wide ? (cardSize * height) / width : cardSize}
        zoom={zoom}
      />
    </div>
  );
}
