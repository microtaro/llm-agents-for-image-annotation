// A line of the loupe's side kept in sight by scrolling the side alone (2026-11-05: in a narrow
// window the side stands below the image, and scrollIntoView moved the whole page too, so
// choosing an object sent the image out of the window).
type Span = { top: number; bottom: number };

/** Where the panel's scroll goes for the line to be seen; where it is, when it already is. */
export function nearestTop(scrollTop: number, line: Span, panel: Span): number {
  if (line.top < panel.top) return scrollTop - (panel.top - line.top);
  if (line.bottom > panel.bottom) return scrollTop + (line.bottom - panel.bottom);
  return scrollTop;
}

/** Shows the line in the side that holds it, moving nothing else. */
export function showInSide(line: Element | null | undefined) {
  const panel = line?.closest("aside");
  if (!line || !panel) return;
  panel.scrollTop = nearestTop(
    panel.scrollTop,
    line.getBoundingClientRect(),
    panel.getBoundingClientRect(),
  );
}
