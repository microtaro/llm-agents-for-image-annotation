// A value the server sends as JSON of no fixed shape (a box's args and preview, a line's data),
// read the one way everywhere on the screen.

/** A value as text: a string or a number as it is, anything else none. */
export function textOf(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

/** The objects of a value that is a list (none when it is not one). */
export function objectsOf<T extends object>(value: unknown): T[] {
  return Array.isArray(value)
    ? value.filter((v): v is T => Boolean(v) && typeof v === "object")
    : [];
}
