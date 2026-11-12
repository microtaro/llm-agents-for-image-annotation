// The bar of using for training (types design 17.4, 19.0): the ring is the state, so the bar only
// changes the shown images at once (user 2026-10-15: 100 images were 100 rings to press), with
// the notice to take it back as for one image.
import { toast } from "sonner";
import type { GalleryItem } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { markOf, setUsed } from "@/lib/imageUse";
import { type Narrowing, shownWhich, usedAfter } from "@/lib/selection";

/** Using for training: the shown images used or left out at once, each changed one taken back
 * from the notice. */
export function UseBar({
  datasetId,
  items,
  shown,
  by,
}: {
  datasetId: string;
  items: GalleryItem[];
  shown: string[];
  /** What narrows what is shown, said on the bar (as the choosing bar says it). */
  by: Narrowing;
}) {
  const inView = items.filter((i) => shown.includes(i.image.id));
  // As the rings: using takes back a left-out image with a record to use, leaving out an used
  // one; one never annotated has nothing to use and no ring, so it is not counted (found
  // 2026-10-16: all six left out, "use the shown" counted the three never annotated too).
  const toUse = inView.filter((i) => markOf(i) === "ran").map((i) => i.image.id);
  const toLeave = inView.filter((i) => markOf(i) === "adopted").map((i) => i.image.id);
  const used = inView.filter((i) => i.badge.kind === "result").length;
  const which = shownWhich(inView.length, by);
  const change = async (ids: string[], on: boolean) => {
    try {
      for (const id of ids) await setUsed(datasetId, id, on);
      toast.success(t(on ? "select.use.done" : "select.unuse.done", { count: ids.length }), {
        action: {
          label: t("select.undo"),
          onClick: () =>
            void Promise.all(ids.map((id) => setUsed(datasetId, id, !on))).catch((reason) =>
              toast.error(errorText(reason)),
            ),
        },
      });
    } catch (reason) {
      toast.error(errorText(reason));
    }
  };
  return (
    <div
      role="region"
      aria-label={t("select.label")}
      className="sticky top-(--gallery-head) z-20 flex min-h-11 flex-wrap items-center gap-2 border-b-2 border-ink bg-sheet px-5 py-2 text-body"
    >
      <b className="min-w-[7em]">{t("select.useBar", { which, used })}</b>
      <span className="flex-1" />
      {/* What training will be, of all the images, and why on hover when nothing changes (user
          2026-10-16: "0 change" said how many a press moves, not what one wants to know). */}
      <Button
        size="small"
        variant="use"
        disabled={!toUse.length}
        title={toUse.length ? undefined : t("select.useShown.why")}
        onClick={() => void change(toUse, true)}
      >
        {t("select.useShown", { which, after: usedAfter(items, toUse, true), total: items.length })}
      </Button>
      <Button
        size="small"
        disabled={!toLeave.length}
        title={toLeave.length ? undefined : t("select.unuseShown.why")}
        onClick={() => void change(toLeave, false)}
      >
        {t("select.unuseShown", {
          which,
          after: usedAfter(items, toLeave, false),
          total: items.length,
        })}
      </Button>
    </div>
  );
}
