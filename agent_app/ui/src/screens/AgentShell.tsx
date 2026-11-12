// The agent app's frame inside a dataset (docs/2026-10-09-agent-app-design.md 4.1): the workers
// and the talk on one side, the right on the other (chosen at its top or by what the steward
// shows, definition 35.3), the line between them dragged (or ← →) to change the width. Wide: one
// screen tall, each side scrolling on its own; narrow: the workers and the talk above, the page
// scrolling.
import type { PlanTarget } from "@/lib/decisions";
import { MessageSquare } from "lucide-react";
import type { ReactNode } from "react";
import { t } from "@/i18n";
import type { LookingAt } from "@/lib/talk";
import { useSideLayout } from "@/lib/viewState";
import { AgentSide } from "./AgentSide";

const MIN = 260;
const MAX = 640;
const clampWidth = (width: number) => Math.round(Math.min(MAX, Math.max(MIN, width)));

export function AgentShell({
  datasetId,
  looking,
  onSeePlan,
  side,
  children,
}: {
  datasetId: string;
  looking: LookingAt;
  /** Open the plan a proposal runs, as it holds it (the screen's plan window, if it has one). */
  onSeePlan?: (target: PlanTarget, from?: string) => void;
  /** The left itself (the library's reception, types design 16.2); else the dataset's. */
  side?: ReactNode;
  children: ReactNode;
}) {
  const [layout, setLayout] = useSideLayout();
  const width = layout.folded ? 84 : layout.width;
  const drag = (event: React.PointerEvent<HTMLDivElement>) => {
    const line = event.currentTarget;
    line.setPointerCapture(event.pointerId);
    const move = (e: PointerEvent) =>
      setLayout({ width: clampWidth(layout.right ? window.innerWidth - e.clientX : e.clientX) });
    const up = () => {
      line.removeEventListener("pointermove", move);
      line.removeEventListener("pointerup", up);
    };
    line.addEventListener("pointermove", move);
    line.addEventListener("pointerup", up);
  };
  return (
    <div
      className={`flex min-h-screen flex-col bg-background min-[1000px]:h-screen ${layout.right ? "min-[1000px]:flex-row-reverse" : "min-[1000px]:flex-row"}`}
      style={{ "--side-w": `${width}px` } as React.CSSProperties}
    >
      <div
        className={`flex min-h-0 shrink-0 flex-col border-line max-[999px]:border-b min-[1000px]:w-(--side-w) ${layout.right ? "min-[1000px]:border-l" : "min-[1000px]:border-r"}`}
      >
        {side ?? <AgentSide datasetId={datasetId} looking={looking} onSeePlan={onSeePlan} />}
      </div>
      {!layout.folded && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={t("side.split")}
          aria-valuenow={width}
          aria-valuemin={MIN}
          aria-valuemax={MAX}
          tabIndex={0}
          onPointerDown={drag}
          onKeyDown={(e) => {
            const by = e.key === "ArrowLeft" ? -20 : e.key === "ArrowRight" ? 20 : 0;
            if (!by) return;
            e.preventDefault();
            setLayout({ width: clampWidth(width + (layout.right ? -by : by)) });
          }}
          // A line in its middle, so the two sides are told apart (Sol 2026-10-12: the boundary
          // was transparent); the whole handle in the action colour when touched.
          className="w-1.5 shrink-0 cursor-col-resize bg-[linear-gradient(var(--color-line),var(--color-line))] bg-[length:1px_100%] bg-center bg-no-repeat hover:bg-action focus-visible:bg-action focus-visible:outline-none max-[999px]:hidden"
        />
      )}
      {/* Narrow: room at the foot so the round button never covers the last control. */}
      <div className="min-w-0 flex-1 max-[999px]:pb-16 min-[1000px]:overflow-y-auto">
        {children}
      </div>
      {/* Narrow (one column): the talk is at the top; a press brings its input back from
        anywhere below (Sol 2026-10-12: at 320px, scrolling down took the talk off the screen). */}
      <button
        type="button"
        onClick={() => {
          window.scrollTo({ top: 0, behavior: "smooth" });
          document
            .querySelector<HTMLTextAreaElement>("form textarea")
            ?.focus({ preventScroll: true });
        }}
        aria-label={t("side.toTalk")}
        title={t("side.toTalk")}
        // A small round button, not a wide one (Sol 2026-10-13: at 320px it covered "clear the
        // search", and pressing it went to the talk).
        className="fixed right-2 bottom-2 z-40 grid size-11 cursor-pointer place-items-center rounded-full border border-line bg-sheet text-ink shadow-md min-[1000px]:hidden"
      >
        <MessageSquare className="size-5" aria-hidden />
      </button>
    </div>
  );
}
