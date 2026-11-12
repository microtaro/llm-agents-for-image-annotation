// Wheel zoom around the pointer and drag to move, for a gallery card or the loupe
// (DESIGN.md 5: the cards' zoom is a must). A click without a drag still clicks.
import { useCallback, useEffect, useRef, useState } from "react";

export interface ZoomPan {
  scale: number;
  x: number;
  y: number;
}

const START: ZoomPan = { scale: 1, x: 0, y: 0 };

/** The view after zooming by factor around the point (px, py) of the box. */
export function zoomAt(view: ZoomPan, factor: number, px: number, py: number, max = 16): ZoomPan {
  const scale = Math.min(max, Math.max(1, view.scale * factor));
  if (scale === 1) return START;
  const k = scale / view.scale;
  return { scale, x: px - (px - view.x) * k, y: py - (py - view.y) * k };
}

export function useZoomPan<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [view, setView] = useState<ZoomPan>(START);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  useEffect(() => {
    const box = ref.current;
    if (!box) return;
    // A passive listener cannot stop the page from scrolling, so it is added by hand.
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = box.getBoundingClientRect();
      const factor = event.deltaY < 0 ? 1.2 : 1 / 1.2;
      setView((v) => zoomAt(v, factor, event.clientX - rect.left, event.clientY - rect.top));
    };
    box.addEventListener("wheel", wheel, { passive: false });
    return () => box.removeEventListener("wheel", wheel);
  }, []);

  const onPointerDown = useCallback((event: React.PointerEvent) => {
    drag.current = { x: event.clientX, y: event.clientY, moved: false };
  }, []);
  const onPointerMove = useCallback(
    (event: React.PointerEvent) => {
      const start = drag.current;
      if (!start || view.scale === 1) return;
      const dx = event.clientX - start.x;
      const dy = event.clientY - start.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) start.moved = true;
      drag.current = { ...start, x: event.clientX, y: event.clientY };
      setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
    },
    [view.scale],
  );
  const onPointerUp = useCallback(() => {
    const moved = drag.current?.moved ?? false;
    drag.current = null;
    return moved;
  }, []);
  const reset = useCallback(() => setView(START), []);

  return { ref, view, setView, reset, onPointerDown, onPointerMove, onPointerUp };
}

/** The size of the zoom's window: the element's width and the window's height below it
 * (the loupe and the editor: the whole area left, not the image's own shape; user
 * 2026-10-07, as the first app's viewer did). Measured again as the page or window changes. */
export function useViewArea(element: React.RefObject<HTMLElement | null>, bottom = 16) {
  const [area, setArea] = useState({ width: 800, height: 600 });
  useEffect(() => {
    const box = element.current;
    if (!box) return;
    const measure = () => {
      const top = box.getBoundingClientRect().top + window.scrollY;
      setArea({
        width: box.clientWidth,
        height: Math.max(320, window.innerHeight - top - bottom),
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [element, bottom]);
  return area;
}
