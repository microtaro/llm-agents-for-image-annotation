// The loupe's image: the original with its annotations, wheel zoom and drag.
import { useEffect, useRef } from "react";
import { imageUrl } from "@/api/client";
import type { GalleryItem } from "@/api/types";
import { fitInside, objectAt } from "@/lib/boxes";
import { Shapes } from "@/components/Shapes";
import { useDisplay } from "@/lib/display";
import type { UseMark as Mark } from "@/lib/imageUse";
import { useViewArea, useZoomPan } from "@/lib/useZoomPan";
import { UseMark } from "@/components/UseMark";

/** ②'s mark over the image as on its card; pressing it adopts or leaves out, and while annotating
 * with AI the cards' choosing ring. */
export type LoupeMark = {
  mark: Mark;
  onToggle: (adopt: boolean) => void;
  choose?: { chosen: boolean; done: boolean; label: string; onChoose: (on: boolean) => void };
} | null;

export function LoupeView({
  item,
  colors,
  selected = null,
  onSelect,
  mark = null,
}: {
  item: GalleryItem;
  colors: Record<string, string>;
  /** An object to show selected (opened from the table). */
  selected?: string | null;
  /** Choose the object under a click, or none. */
  onSelect?: (id: string | null) => void;
  mark?: LoupeMark;
}) {
  const zoom = useZoomPan<HTMLDivElement>();
  const box = useRef<HTMLDivElement | null>(null);
  // The view is the whole area left on the screen, the image fitted inside it (user
  // 2026-10-07: a tall page left a narrow view).
  const area = useViewArea(box);
  const { width, height } = item.image;
  const { reset } = zoom;

  const fitted = fitInside(area.width, area.height, item.image.width, item.image.height);
  const { epoch } = useDisplay();
  useEffect(() => reset(), [item.image.id, epoch, reset]);

  return (
    <>
      <div className="flex flex-1 px-5 pb-4 pt-4">
        <div
          ref={(element) => {
            zoom.ref.current = element;
            box.current = element;
          }}
          onPointerDown={zoom.onPointerDown}
          onPointerMove={zoom.onPointerMove}
          onPointerUp={(event) => {
            // A click, not a drag: choose what is under it, as the list on the right does
            // (Astra 2026-10-06: the image and the list did not choose each other).
            if (zoom.onPointerUp() || !onSelect) return;
            const rect = event.currentTarget.getBoundingClientRect();
            const x =
              (((event.clientX - rect.left - zoom.view.x) / zoom.view.scale - fitted.left) /
                fitted.width) *
              width;
            const y =
              (((event.clientY - rect.top - zoom.view.y) / zoom.view.scale - fitted.top) /
                fitted.height) *
              height;
            onSelect(objectAt(item.annotations, x, y));
          }}
          onDoubleClick={zoom.reset}
          className="relative w-full touch-none overflow-hidden bg-backdrop"
          style={{ height: area.height }}
        >
          {mark && (
            // At the view's top left as on the gallery's card (user 2026-10-16: on the image's own
            // corner it floated in the dark band, apart from where the card has it), not moved by
            // the zoom; the box lets clicks through but its own.
            <div className="pointer-events-none absolute inset-0 z-10">
              <div className="pointer-events-auto">
                <UseMark mark={mark.mark} onToggle={mark.onToggle} choose={mark.choose} />
              </div>
            </div>
          )}
          <div
            className="absolute inset-0 origin-top-left"
            style={{
              transform: `translate(${zoom.view.x}px, ${zoom.view.y}px) scale(${zoom.view.scale})`,
            }}
          >
            <div
              className="absolute"
              style={{
                left: fitted.left,
                top: fitted.top,
                width: fitted.width,
                height: fitted.height,
              }}
            >
              <img
                src={imageUrl(item.image.id)}
                alt={item.image.name}
                draggable={false}
                className="block size-full"
              />
              <Shapes
                selected={selected}
                onTag={onSelect}
                width={width}
                height={height}
                annotations={item.annotations}
                colors={colors}
                shownHeight={fitted.height}
                zoom={zoom.view.scale}
              />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
