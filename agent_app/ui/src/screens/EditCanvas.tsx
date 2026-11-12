// Editing on the loupe's image (step 7 design 4): select, move, resize with corner handles,
// draw boxes, place polygon vertices, move vertices; wheel zoom and drag the empty image to
// move it, a double click to fit it again. Every finished change goes to onCommit; the parent
// keeps history and the draft. The loupe looks and fixes on this one image (user 2026-10-27), so
// an object only moves once the pointer goes past a press's slop.
import { type ReactNode, useEffect, useRef, useState } from "react";
import { imageUrl } from "@/api/client";
import { fitInside, svgPoints } from "@/lib/boxes";
import { Tags } from "@/components/Shapes";
import { useDisplay } from "@/lib/display";
import {
  boxFrom,
  closes,
  type Corner,
  crossesItself,
  dragged,
  type EditShape,
  handleAt,
  hit,
  moveGeometry,
  moveVertex,
  type Point,
  resizeBox,
  toImage,
} from "@/lib/editing";
import { useViewArea, useZoomPan } from "@/lib/useZoomPan";

export type Tool = "select" | "bbox" | "polygon";

// at: where it was pressed on the screen; moved: past the slop, so it moves what it holds.
type Held = { at: [number, number]; moved: boolean };
type Drag =
  | ({ kind: "move"; id: string; from: Point } & Held)
  | ({ kind: "corner"; id: string; corner: Corner } & Held)
  | ({ kind: "vertex"; id: string; index: number } & Held)
  | { kind: "draw"; from: Point; to: Point }
  | { kind: "pan"; x: number; y: number };

const HANDLE = 8; // screen px

export function EditCanvas({
  imageId,
  width,
  height,
  shapes,
  colors,
  selected,
  tool,
  onSelect,
  onCommit,
  onAdd,
  onToolDone,
  names,
  overlay = null,
}: {
  imageId: string;
  width: number;
  height: number;
  shapes: EditShape[];
  colors: Record<string, string>;
  selected: string | null;
  tool: Tool;
  onSelect: (id: string | null) => void;
  onCommit: (id: string, shape: EditShape) => void;
  onAdd: (geometry: EditShape["geometry"]) => void;
  onToolDone: () => void;
  /** The tags' words by object, when the objects have no numbers of their own (references:
   * "label 1" as in the list beside; Astra 2026-10-06). */
  names?: Record<string, string>;
  /** Over the view's top left, not moved by the zoom (the loupe's mark, as on the card). */
  overlay?: ReactNode;
}) {
  const zoom = useZoomPan<HTMLDivElement>();
  const picture = useRef<HTMLImageElement | null>(null);
  // The whole area left, the image fitted inside (as the loupe; user 2026-10-07).
  const area = useViewArea(zoom.ref);
  const fitted = fitInside(area.width, area.height, width, height);
  const shownWidth = fitted.width;
  const [drag, setDrag] = useState<Drag | null>(null);
  const [preview, setPreview] = useState<EditShape | null>(null);
  const [points, setPoints] = useState<Point[]>([]);
  const [pointer, setPointer] = useState<Point | null>(null);
  const display = useDisplay();
  const { setView, reset } = zoom;
  const scale = (shownWidth * zoom.view.scale) / width; // screen px per image px
  const tolerance = HANDLE / scale;

  const { epoch } = display;
  useEffect(() => reset(), [imageId, epoch, reset]);
  // Esc stops drawing a polygon, Backspace takes back its last vertex.
  useEffect(() => {
    if (tool !== "polygon") setPoints([]);
    const key = (event: KeyboardEvent) => {
      if (tool !== "polygon" || points.length === 0) return;
      if (event.key === "Escape") setPoints([]);
      if (event.key === "Backspace") {
        event.preventDefault();
        setPoints((now) => now.slice(0, -1));
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [tool, points.length]);

  const at = (event: React.PointerEvent): Point =>
    toImage(event.clientX, event.clientY, picture.current!.getBoundingClientRect(), width, height);
  const shapeOf = (id: string) => shapes.find((s) => s.id === id)!;

  function down(event: React.PointerEvent) {
    if (event.button !== 0) return;
    try {
      // Keep receiving the drag when the pointer leaves the image.
      (event.currentTarget as Element).setPointerCapture(event.pointerId);
    } catch {
      // A pointer the browser does not track (made by a script) cannot be captured.
    }
    const point = at(event);
    if (tool === "bbox") return setDrag({ kind: "draw", from: point, to: point });
    if (tool === "polygon") {
      if (closes(points, point, tolerance)) {
        if (!crossesItself(points)) {
          onAdd({ type: "polygon", points });
          setPoints([]);
          onToolDone();
        }
        return;
      }
      return setPoints([...points, point]);
    }
    const chosen = selected ? shapes.find((s) => s.id === selected) : undefined;
    const handle = chosen ? handleAt(chosen.geometry, point, tolerance) : null;
    const held: Held = { at: [event.clientX, event.clientY], moved: false };
    if (chosen && typeof handle === "number")
      return setDrag({ kind: "vertex", id: chosen.id, index: handle, ...held });
    if (chosen && typeof handle === "string")
      return setDrag({ kind: "corner", id: chosen.id, corner: handle, ...held });
    const id = hit(shapes, point, tolerance);
    onSelect(id);
    if (id) return setDrag({ kind: "move", id, from: point, ...held });
    setDrag({ kind: "pan", x: event.clientX, y: event.clientY });
  }

  function move(event: React.PointerEvent) {
    const point = at(event);
    setPointer(point);
    if (!drag) return;
    if (drag.kind === "pan") {
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (zoom.view.scale > 1) setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
      return setDrag({ ...drag, x: event.clientX, y: event.clientY });
    }
    if (drag.kind === "draw") return setDrag({ ...drag, to: point });
    // A press that wanders a little is still a press: it chose, it does not move.
    if (!drag.moved) {
      if (!dragged(drag.at, [event.clientX, event.clientY])) return;
      setDrag({ ...drag, moved: true });
    }
    const base = shapeOf(drag.id);
    const geometry =
      drag.kind === "move"
        ? moveGeometry(
            base.geometry,
            point[0] - drag.from[0],
            point[1] - drag.from[1],
            width,
            height,
          )
        : drag.kind === "corner"
          ? resizeBox(base.geometry, drag.corner, point)
          : moveVertex(base.geometry, drag.index, point);
    setPreview({ ...base, geometry, changed: true });
  }

  function up() {
    if (drag?.kind === "draw") {
      const geometry = boxFrom(drag.from, drag.to);
      if (geometry) {
        onAdd(geometry);
        onToolDone();
      }
    } else if (drag && drag.kind !== "pan" && preview) {
      onCommit(preview.id, preview);
    }
    setDrag(null);
    setPreview(null);
  }

  const drawn = shapes.map((s) => (preview && s.id === preview.id ? preview : s));
  const stroke = display.lineWidth / zoom.view.scale;
  const chosen = drawn.find((s) => s.id === selected);
  const handleSize = HANDLE / scale;
  const corners = (shape: EditShape): Point[] =>
    shape.geometry.type === "bbox"
      ? (() => {
          const [x, y, w, h] = shape.geometry.xywh;
          return [
            [x, y],
            [x + w, y],
            [x, y + h],
            [x + w, y + h],
          ] as Point[];
        })()
      : shape.geometry.type === "polygon"
        ? shape.geometry.points
        : [];
  const drawing = drag?.kind === "draw" ? boxFrom(drag.from, drag.to, 0) : null;

  return (
    <div className="flex flex-1 px-5 pb-4 pt-4">
      <div
        ref={zoom.ref}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onDoubleClick={() => tool === "select" && reset()}
        className={`relative w-full touch-none overflow-hidden bg-backdrop ${tool === "select" ? "cursor-default" : "cursor-crosshair"}`}
        style={{ height: area.height }}
      >
        {overlay && (
          // As the loupe's view has it: the box lets clicks through but its own.
          <div className="pointer-events-none absolute inset-0 z-10">
            <div className="pointer-events-auto w-fit">{overlay}</div>
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
              ref={picture}
              src={imageUrl(imageId)}
              alt=""
              draggable={false}
              className="block size-full select-none"
            />
            <svg
              viewBox={`0 0 ${width} ${height}`}
              preserveAspectRatio="none"
              className="absolute inset-0 size-full"
            >
              {display.overlay &&
                drawn.map((shape) => (
                  <polygon
                    key={shape.id}
                    points={svgPoints(shape.geometry)}
                    fill={shape.id === selected ? "rgba(31,87,195,0.08)" : "none"}
                    stroke={colors[shape.label] ?? "#4363D8"}
                    strokeWidth={(shape.id === selected ? 1.6 : 1) * stroke}
                    strokeDasharray={
                      shape.changed ? `${4 / zoom.view.scale} ${3 / zoom.view.scale}` : undefined
                    }
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
              {chosen &&
                corners(chosen).map(([x, y], i) => (
                  <rect
                    key={i}
                    x={x - handleSize / 2}
                    y={y - handleSize / 2}
                    width={handleSize}
                    height={handleSize}
                    fill="#ffffff"
                    style={{ stroke: "var(--action)" }}
                    strokeWidth={1.5 / zoom.view.scale}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
              {drawing && (
                <polygon
                  points={svgPoints(drawing)}
                  fill="none"
                  style={{ stroke: "var(--action)" }}
                  strokeWidth={stroke}
                  strokeDasharray={`${4 / zoom.view.scale} ${3 / zoom.view.scale}`}
                  vectorEffect="non-scaling-stroke"
                />
              )}
              {points.length > 0 && (
                <polyline
                  points={[...points, ...(pointer ? [pointer] : [])]
                    .map(([x, y]) => `${x},${y}`)
                    .join(" ")}
                  fill="none"
                  style={{ stroke: "var(--action)" }}
                  strokeWidth={stroke}
                  vectorEffect="non-scaling-stroke"
                />
              )}
              {points.map(([x, y], i) => (
                <rect
                  key={`p${i}`}
                  x={x - handleSize / 2}
                  y={y - handleSize / 2}
                  width={handleSize}
                  height={handleSize}
                  // The marks of work on the image take the operations' color, not a label's.
                  style={{ stroke: "var(--action)", fill: i === 0 ? "var(--action)" : "#ffffff" }}
                />
              ))}
            </svg>
            {display.overlay && display.tags && (
              <Tags
                objects={names ? drawn.map((d) => ({ ...d, text: names[d.id] })) : drawn}
                width={width}
                height={height}
                shownHeight={(shownWidth * height) / width}
                zoom={zoom.view.scale}
                colors={colors}
                onPick={tool === "select" ? onSelect : undefined}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
