// The label colors of the dataset (a run takes them when it starts): changed here, put back to
// the palette. The same row in the gallery and the loupe; the loupe adds how many of each the
// image has, as the first app's enlarged view did ("■ right foot 2").
import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Confirm } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { byLabel } from "@/lib/display";
import { errorText } from "@/lib/errorText";

export function LabelColors({
  datasetId,
  colors,
  onColors,
  counts,
}: {
  datasetId: string;
  colors: Record<string, string>;
  onColors: () => void;
  /** How many objects of each label the shown image has (the loupe). */
  counts?: Record<string, number>;
}) {
  const [resetting, setResetting] = useState(false);
  if (!Object.keys(colors).length) return null;

  async function setColor(label: string, color: string) {
    try {
      await api(`/v1/datasets/${datasetId}/label-colors`, {
        method: "PUT",
        body: { colors: { [label]: color } },
      });
      onColors();
    } catch (reason) {
      toast.error(errorText(reason));
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-body">
      <span className="text-muted-foreground">{t("colors.title")}</span>
      {Object.entries(colors)
        .sort(([a], [b]) => byLabel(a, b))
        .map(([label, color]) => (
          <label
            key={label}
            className="flex items-center gap-1"
            title={t("colors.label", { label })}
          >
            <input
              type="color"
              value={color.toLowerCase()}
              aria-label={t("colors.label", { label })}
              onChange={(e) => void setColor(label, e.target.value)}
              className="h-5 w-6 cursor-pointer border-0 bg-transparent p-0"
            />
            {label}
            {counts && <span className="text-muted-foreground">{counts[label] ?? 0}</span>}
          </label>
        ))}
      <Button size="small" onClick={() => setResetting(true)}>
        {t("colors.reset")}
      </Button>
      <Confirm
        open={resetting}
        title={t("colors.reset")}
        message={t("colors.reset.message")}
        confirm={t("colors.reset")}
        onConfirm={async () => {
          setResetting(false);
          try {
            await api(`/v1/datasets/${datasetId}/label-colors/reset`, { body: {} });
            onColors();
          } catch (reason) {
            toast.error(errorText(reason));
          }
        }}
        onCancel={() => setResetting(false)}
      />
    </div>
  );
}

/** The label's color as a small mark beside its name, in the table and the lists of objects,
 * so an object found by its color on the image is found there too (Astra 2026-10-07). */
export function LabelDot({ color }: { color?: string }) {
  if (!color) return null;
  return (
    <span
      aria-hidden="true"
      className="mr-1 inline-block size-2.5 shrink-0 rounded-sm align-[-1px]"
      style={{ background: color }}
    />
  );
}
