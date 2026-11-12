// Choosing found images by their names (Astra 2026-10-05: 20 of 100 were ticked one by one).
// Names are written apart by spaces, commas or new lines; a name without its extension, or
// its start ("S3_"), chooses every file that starts so.

/** The paths of the files no name chooses, to leave out; null when no name was written. */
export function leftOutBy(
  files: { path: string; name: string }[],
  text: string,
): Set<string> | null {
  const names = text
    .split(/[\s,\u3001\uff0c]+/)
    .map((n) => n.trim())
    .filter(Boolean);
  if (!names.length) return null;
  return new Set(files.filter((f) => !names.some((n) => f.name.startsWith(n))).map((f) => f.path));
}
