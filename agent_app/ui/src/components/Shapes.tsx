// Annotations drawn by the screen over an image (DESIGN.md 5): lines in screen px (the
// display setting) whatever the zoom, in their label's color, tags outside the top left. "marked" ones are drawn in the
// failure color (a check's difference); "ghosts" are another set to compare with, dotted.
import type { Annotation } from "@/api/types";
import { svgPoints, tagPlaces } from "@/lib/boxes";
import { inkOn, useDisplay } from "@/lib/display";

const FAILED = "#c0392b";
const FALLBACK = "#4363D8";

export function Shapes({
  width,
  height,
  annotations,
  colors,
  shownHeight,
  zoom = 1,
  marked = new Set<string>(),
  ghosts = [],
  tags = true,
  selected,
  onTag,
}: {
  width: number;
  height: number;
  annotations: Annotation[];
  colors: Record<string, string>;
  shownHeight: number;
  zoom?: number;
  marked?: Set<string>;
  ghosts?: Annotation[];
  tags?: boolean;
  selected?: string | null;
  onTag?: (id: string) => void;
}) {
  const display = useDisplay();
  // People can hide every annotation to see the image itself (DESIGN.md 5).
  if (!display.overlay) return null;
  const stroke = display.lineWidth / zoom;
  const showTags = tags && display.tags;
  // Objects with values only (an empty box) have no place to draw;
  // their tags piled up in the corner (found 2026-10-05).
  const drawn = annotations.filter(
    (a) => !(a.geometry.type === "bbox" && a.geometry.xywh[2] === 0 && a.geometry.xywh[3] === 0),
  );
  return (
    <>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="pointer-events-none absolute inset-0 size-full"
        aria-hidden="true"
      >
        {ghosts.map((a) => (
          <polygon
            key={`ghost-${a.id}`}
            points={svgPoints(a.geometry)}
            fill="none"
            stroke={marked.has(a.id) ? FAILED : "#fafbfc"}
            // A master's object chosen (a miss of the check) stands out as the result's do.
            strokeWidth={(a.id === selected ? 2.5 : 1) * stroke}
            strokeDasharray={`${3 / zoom} ${3 / zoom}`}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {drawn.map((a) => (
          <polygon
            key={a.id}
            points={svgPoints(a.geometry)}
            // The selected object (opened from the table) is thick and lightly filled, so it
            // stands out among many of the same label.
            fill={
              a.geometry.type === "mask" || a.id === selected
                ? (colors[a.label] ?? FALLBACK)
                : "none"
            }
            fillOpacity={a.id === selected ? 0.18 : a.geometry.type === "mask" ? 0.25 : undefined}
            stroke={marked.has(a.id) ? FAILED : (colors[a.label] ?? FALLBACK)}
            strokeWidth={(a.id === selected ? 2.5 : marked.has(a.id) ? 1.5 : 1) * stroke}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
      {showTags && (
        <Tags
          objects={drawn}
          width={width}
          height={height}
          shownHeight={shownHeight}
          zoom={zoom}
          colors={colors}
          marked={marked}
          onPick={onTag}
        />
      )}
    </>
  );
}

/** The "label number" tags over the objects: the same on cards, in the loupe and while
 * editing (Astra 2026-10-06: editing dropped them, and the listed "field 12" had to be found). */
export function Tags({
  objects,
  width,
  height,
  shownHeight,
  zoom = 1,
  colors,
  marked = new Set<string>(),
  onPick,
}: {
  objects: {
    id: string;
    label: string;
    number?: number | null;
    geometry: Annotation["geometry"];
    /** The words, when not "label number" (a reference's objects). */
    text?: string;
  }[];
  width: number;
  height: number;
  shownHeight: number;
  zoom?: number;
  colors: Record<string, string>;
  marked?: Set<string>;
  /** Choose an object by its tag: a tag sits outside its box, over whatever is there, so a
   * click on it chose that instead (Astra 2026-10-06: "field 2" chose "box 1"). */
  onPick?: (id: string) => void;
}) {
  const display = useDisplay();
  const words = (a: (typeof objects)[number]) =>
    a.text ?? (a.number ? `${a.label} ${a.number}` : a.label);
  const places = tagPlaces(
    objects.map((a) => ({ geometry: a.geometry, text: words(a) })),
    width,
    height,
    shownHeight * zoom,
    display.tagSize,
  );
  return (
    <>
      {objects.map((a, index) => {
        const place = places[index];
        const color = marked.has(a.id) ? FAILED : (colors[a.label] ?? FALLBACK);
        return (
          <span
            key={`tag-${a.id}`}
            className={`absolute whitespace-nowrap px-1 leading-[1.4] ${onPick ? "pointer-events-auto cursor-pointer" : "pointer-events-none"}`}
            onPointerDown={onPick && ((e) => e.stopPropagation())}
            onPointerUp={
              onPick &&
              ((e) => {
                e.stopPropagation();
                onPick(a.id);
              })
            }
            style={{
              left: `${place.left}%`,
              top: `${place.top}%`,
              fontSize: display.tagSize / zoom,
              background: color,
              color: inkOn(color),
            }}
          >
            {words(a)}
          </span>
        );
      })}
    </>
  );
}
