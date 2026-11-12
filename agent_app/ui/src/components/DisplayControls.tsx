// How annotations look (DESIGN.md 5), the same behind every eye (definition 37.2): card size,
// showing annotations, line width, label tags and their size, and putting all of it back.
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import {
  CARD,
  LINE,
  ratioStep,
  RATIO_STEPS,
  resetDisplay,
  setDisplay,
  TAG,
  useDisplay,
  valueAt,
} from "@/lib/display";

export function DisplayControls({
  cardMax,
}: {
  /** The widest card the gallery has room for: the slider's big end. */
  cardMax?: number;
}) {
  const display = useDisplay();
  const own = useId();
  const card = {
    ...CARD,
    max: Math.min(CARD.max, Math.max(CARD.min * 2, cardMax ?? CARD.max)),
  };
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-body">
      <Slider
        id={`card-size-${own}`}
        label={t("display.cardSize")}
        range={card}
        value={Math.min(display.cardSize, card.max)}
        shown={t("display.px", { value: Math.min(display.cardSize, card.max) })}
        onChange={(cardSize) => setDisplay({ cardSize })}
      />
      <label className="flex items-center gap-1.5">
        <input
          type="checkbox"
          checked={display.overlay}
          onChange={(e) => setDisplay({ overlay: e.target.checked })}
        />
        {t("display.overlay")}
      </label>
      <Slider
        id={`line-width-${own}`}
        label={t("display.lineWidth")}
        title={t("display.lineWidth.hint")}
        range={LINE}
        value={display.lineWidth}
        shown={t("display.px", { value: display.lineWidth })}
        onChange={(lineWidth) => setDisplay({ lineWidth })}
      />
      {
        <>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={display.tags}
              onChange={(e) => setDisplay({ tags: e.target.checked })}
            />
            {t("display.tags")}
          </label>
          <Slider
            id={`tag-size-${own}`}
            label={t("display.tagSize")}
            range={TAG}
            value={display.tagSize}
            shown={t("display.px", { value: display.tagSize })}
            onChange={(tagSize) => setDisplay({ tagSize })}
          />
        </>
      }
      <Button size="small" onClick={resetDisplay}>
        {t("display.reset")}
      </Button>
    </div>
  );
}

/** A setting's slider, its value beside it (the card sizes even in ratio). */
export function Slider({
  id,
  label,
  title,
  range,
  value,
  shown,
  onChange,
}: {
  id: string;
  label: string;
  title?: string;
  /** ratio: the slider is even in ratio, not in value (the card size). */
  range: { min: number; max: number; step: number; ratio?: boolean };
  value: number;
  shown: string;
  onChange: (value: number) => void;
}) {
  return (
    <span className="flex items-center gap-1.5" title={title}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="range"
        min={range.ratio ? 0 : range.min}
        max={range.ratio ? RATIO_STEPS : range.max}
        step={range.ratio ? 1 : range.step}
        value={range.ratio ? ratioStep(value, range) : value}
        onChange={(e) => {
          const at = Number(e.target.value);
          onChange(range.ratio ? valueAt(at, range) : at);
        }}
        className="w-28"
      />
      <span className="w-12 text-muted-foreground">{shown}</span>
    </span>
  );
}
