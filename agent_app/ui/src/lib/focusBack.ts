// Where the keyboard goes back to after leaving a screen (Sol 2026-10-13: closing the loupe left
// the focus on the page's body, and the place in the cards was lost). Kept in memory for the
// next screen of this tab; taken once.
let pending: string | null = null;

/** Remember the image whose card takes the focus on the next gallery. */
export function focusImageNext(imageId: string) {
  pending = imageId;
}

/** The image to focus now, once. */
export function takeFocusImage(): string | null {
  const id = pending;
  pending = null;
  return id;
}
