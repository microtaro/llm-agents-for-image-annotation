// An image with its objects drawn over it, each tagged by its path in the annotation's tree and
// its label ("1-2 fragile": the tag says which box a mark is in; definition 26.7), zoomed as the
// gallery's cards are. The objects' colors are the dataset's label colors (DESIGN.md 6).
import { useEffect, useRef, useState } from "react";
import { thumbnailUrl } from "@/api/client";
import type { Annotation, LabelDefinition } from "@/api/types";
import { Shapes, Tags } from "@/components/Shapes";
import { useDisplay } from "@/lib/display";
import { answerRows } from "@/lib/requirementTree";
import { ZoomBox } from "./ZoomBox";

export interface FigureImage {
  id: string;
  name: string;
  width: number;
  height: number;
}

function useHeight() {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(300);
  useEffect(() => {
    const box = ref.current;
    if (!box) return;
    const observer = new ResizeObserver(() => setHeight(box.clientHeight));
    observer.observe(box);
    setHeight(box.clientHeight);
    return () => observer.disconnect();
  }, []);
  return { ref, height };
}

export function PlanFigure({
  image,
  objects,
  definitions,
  colors,
  label,
  onOpen,
  className = "",
}: {
  image: FigureImage;
  objects: Annotation[];
  definitions: LabelDefinition[];
  colors: Record<string, string>;
  /** What a click opens, said to a screen reader. */
  label: string;
  onOpen?: () => void;
  className?: string;
}) {
  const { ref, height } = useHeight();
  // The tags follow the display settings, as the cards' (DESIGN.md 5).
  const display = useDisplay();
  const { paths } = answerRows(objects, definitions);
  const tagged = objects.map((o) => ({ ...o, text: `${paths.get(o.id) ?? ""} ${o.label}` }));
  return (
    <ZoomBox label={label} onOpen={onOpen} className={`rounded-sm bg-backdrop ${className}`}>
      {(scale) => (
        <div
          ref={ref}
          className="relative w-full"
          style={{ aspectRatio: `${image.width} / ${image.height}` }}
        >
          <img
            src={thumbnailUrl(image.id, 1024)}
            alt={image.name}
            draggable={false}
            className="block size-full object-contain"
          />
          <Shapes
            width={image.width}
            height={image.height}
            annotations={objects}
            colors={colors}
            shownHeight={height}
            zoom={scale}
            tags={false}
          />
          {display.overlay && display.tags && (
            <Tags
              objects={tagged}
              width={image.width}
              height={image.height}
              shownHeight={height}
              zoom={scale}
              colors={colors}
            />
          )}
        </div>
      )}
    </ZoomBox>
  );
}
