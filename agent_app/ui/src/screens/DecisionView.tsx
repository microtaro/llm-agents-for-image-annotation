// What a decision makes, as data (types design 16.3.1, criterion S-M11; user 2026-10-12: "what
// deciding changes is not clear"; "I want to see where results go and where they do not, in the
// image and the table at once"). Two switches, the image and the data; both on shows each image
// with its values beside it. A run's and a mark's image view is the gallery's cards
// of its targets (as before); their data is each target's state now and after with its objects.
import type { GalleryItem, GalleryPage, Proposal } from "@/api/types";
import { t } from "@/i18n";
import { rowsOf, type Shown } from "@/lib/decisions";
import { useApi } from "@/lib/useApi";
import { Drawn } from "./DrawnImage";
import { ObjectTable } from "./ObjectTable";

const SWITCHES = ["image", "data"] as const;

export function DecisionSwitches({
  shown,
  onShown,
}: {
  shown: Shown;
  onShown: (next: Shown) => void;
}) {
  return (
    <div
      role="group"
      aria-label={t("decision.shown")}
      className="flex flex-wrap items-center gap-1.5 text-body"
    >
      <span className="text-muted-foreground">{t("decision.shown")}</span>
      {SWITCHES.map((key) => {
        const on = shown[key];
        // One of the two stays on (nothing shown is not a view).
        const last = on && !shown[key === "image" ? "data" : "image"];
        return (
          <button
            key={key}
            type="button"
            aria-pressed={on}
            disabled={last}
            title={last ? t("decision.shown.last") : undefined}
            onClick={() => onShown({ ...shown, [key]: !on })}
            className={`cursor-pointer rounded-md border px-2.5 py-0.5 disabled:cursor-default ${on ? "border-ink bg-selected font-semibold text-ink" : "border-line bg-surface"}`}
          >
            {t(`decision.shown.${key}`)}
          </button>
        );
      })}
    </div>
  );
}

export function DecisionView({
  datasetId,
  proposal,
  items,
  colors,
  shown,
  nowQuery,
}: {
  datasetId: string;
  proposal: Proposal;
  items: GalleryItem[];
  colors: Record<string, string>;
  shown: Shown;
  /** The gallery's query for the images now (route.galleryQuery, no record chosen). */
  nowQuery: string;
}) {
  // "Now" is the images as the gallery shows them now, with no record chosen (Sol 2026-10-12:
  // ①'s samples were drawn as "now"; definition 14: annotating with AI showed the newest
  // annotation on the cards and what training uses here).
  const used = useApi<GalleryPage>(`/v1/datasets/${datasetId}/gallery?${nowQuery}`);
  const usedById = new Map((used.data?.items ?? []).map((i) => [i.image.id, i]));
  // The image only: the gallery's cards of the targets.
  if (!shown.data) return null;
  const rows = rowsOf(proposal);
  const byId = new Map(items.map((i) => [i.image.id, i]));
  const objectsNow = (imageId: string) => usedById.get(imageId)?.annotations ?? [];
  return (
    <section aria-label={t("decision.rows")} className="flex flex-col gap-2 px-5 py-3 text-body">
      {rows.length === 0 && <p className="m-0 text-muted-foreground">{t("decision.rows.none")}</p>}
      {rows.map((row) => {
        const item = byId.get(row.imageId);
        return (
          <div
            key={row.imageId}
            className="flex flex-wrap items-start gap-3 rounded-md border border-line bg-surface p-2"
          >
            {shown.image && item && (
              <Drawn
                image={item.image}
                objects={objectsNow(row.imageId)}
                colors={colors}
                width={300}
              />
            )}
            <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-1">
              <b>{row.name || item?.image.name || row.imageId}</b>
              <span>
                {row.now
                  ? t("decision.change", { now: t(...row.now), after: t(...row.after) })
                  : t(...row.after)}
              </span>
              {item && (
                <ObjectTable image={item.image} objects={objectsNow(row.imageId)} colors={colors} />
              )}
            </div>
          </div>
        );
      })}
    </section>
  );
}
