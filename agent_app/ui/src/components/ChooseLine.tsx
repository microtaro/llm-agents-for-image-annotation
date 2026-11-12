// The bar's two lines, the same in every bar (types design 19.0; user 2026-10-27: choosing is not
// a decision and is not recorded, deciding is, so each has its line, named). Choosing: how many
// are chosen, what to do while none is, what is shown chosen at once (user 2026-10-15: after
// narrowing to 100 images, 100 rings to press; said by what narrows them) and the choice
// emptied. Deciding: the bar's one button, and what goes with it.
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { type Narrowing, shownWhich } from "@/lib/selection";

export function ChooseLine({
  who,
  hint,
  by,
  datasets = false,
  shown,
  chosen,
  onChosen,
  onClear,
  children,
}: {
  /** How many are chosen, or whose they are (a worker's box). */
  who: string;
  /** Nothing chosen and nothing proposed: say what to do. */
  hint: boolean;
  /** What narrows what is shown. */
  by: Narrowing;
  /** Counted as datasets (the library), not images. */
  datasets?: boolean;
  /** What the filter shows now. */
  shown: string[];
  chosen: string[];
  onChosen: (ids: string[]) => void;
  onClear: () => void;
  children?: ReactNode;
}) {
  const missing = shown.filter((id) => !chosen.includes(id));
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-2">
      <Step name={t("select.step.choose")} />
      <b>{who}</b>
      {hint && (
        <span className="text-muted-foreground">
          {t(datasets ? "select.hint.datasets" : "select.hint")}
        </span>
      )}
      <Button
        size="small"
        disabled={!missing.length}
        title={missing.length ? undefined : t("select.shown.all")}
        onClick={() => onChosen([...chosen, ...missing])}
      >
        {t("select.shown", { which: shownWhich(shown.length, by, datasets) })}
      </Button>
      <Button size="small" disabled={!chosen.length} onClick={onClear}>
        {t("select.clear")}
      </Button>
      {children}
    </div>
  );
}

/** The bar's second line: deciding (recorded); an operation that changes no data (writing
 * out) heads its line with its own name instead (definition 60.7). */
export function DecideLine({ children, name }: { children: ReactNode; name?: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Step name={name ?? t("select.step.decide")} />
      {children}
    </div>
  );
}

function Step({ name }: { name: string }) {
  // Wide enough for the longest head (writing out's), so the lines' buttons stay in one column.
  return (
    <span className="w-[4.6em] shrink-0 whitespace-nowrap text-small text-muted-foreground">
      {name}
    </span>
  );
}
