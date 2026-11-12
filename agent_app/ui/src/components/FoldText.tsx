// A text that may be long, shown to a few lines (user 2026-11-10: a long one must fold);
// only when it goes past them, "Show all" under it opens it in place and "Close" folds it again.
// The text is shown once: before, the plan's text folded to its first line cut with "…" kept
// that line above the opened text. A short one is shown whole, with nothing under it.
import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import { t } from "@/i18n";

/** A plan's text and a label's description, folded past these lines (2026-11-10: the plans then
 * had texts of 133 characters at the median, 991 at most, and descriptions of 27, 70 at most:
 * nearly all shown whole). */
export const TEXT_LINES = 4;
export const DESCRIPTION_LINES = 2;

export function FoldText({
  lines,
  className = "",
  children,
}: {
  /** The lines shown while folded. */
  lines: number;
  className?: string;
  children: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [over, setOver] = useState(false);
  // Whether it goes past its lines, measured while folded and again when its width changes.
  useLayoutEffect(() => {
    const element = box.current;
    if (!element || open) return;
    const measure = () => setOver(element.scrollHeight > element.clientHeight + 1);
    measure();
    const watch = new ResizeObserver(measure);
    watch.observe(element);
    return () => watch.disconnect();
  }, [open, lines, children]);
  return (
    <div className={className}>
      <div ref={box} style={open ? undefined : { maxHeight: `${lines}lh`, overflow: "hidden" }}>
        {children}
      </div>
      {(over || open) && (
        <button
          type="button"
          aria-expanded={open}
          className="mt-0.5 cursor-pointer text-xs text-action underline"
          onClick={() => setOpen(!open)}
        >
          {open ? t("common.close") : t("common.showAll")}
        </button>
      )}
    </div>
  );
}
