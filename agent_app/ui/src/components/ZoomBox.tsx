// A picture zoomed as the gallery's cards are (DESIGN.md 5; user 2026-10-20: "the same as the
// gallery's zoom"): the wheel zooms around the pointer, a drag moves, a double click goes back,
// and a click without a drag opens it large.
import type { ReactNode } from "react";
import { useZoomPan } from "@/lib/useZoomPan";

export function ZoomBox({
  label,
  onOpen,
  className = "",
  children,
}: {
  /** What a click opens, said to a screen reader. */
  label: string;
  onOpen?: () => void;
  className?: string;
  /** What is zoomed; given the scale, lines and tags keep their size on the screen. */
  children: ReactNode | ((scale: number) => ReactNode);
}) {
  const zoom = useZoomPan<HTMLDivElement>();
  return (
    <div
      ref={zoom.ref}
      role={onOpen ? "button" : "img"}
      tabIndex={onOpen ? 0 : undefined}
      aria-label={label}
      onKeyDown={(event) => onOpen && event.key === "Enter" && onOpen()}
      onPointerDown={zoom.onPointerDown}
      onPointerMove={zoom.onPointerMove}
      onPointerUp={() => !zoom.onPointerUp() && onOpen?.()}
      onDoubleClick={zoom.reset}
      className={`relative touch-none overflow-hidden ${onOpen ? "cursor-zoom-in" : ""} ${className}`}
    >
      {/* As tall as the box when the box's height is set (a picture fits it with max-h-full). */}
      <div
        className="h-full origin-top-left"
        style={{
          transform: `translate(${zoom.view.x}px, ${zoom.view.y}px) scale(${zoom.view.scale})`,
        }}
      >
        {typeof children === "function" ? children(zoom.view.scale) : children}
      </div>
    </div>
  );
}
