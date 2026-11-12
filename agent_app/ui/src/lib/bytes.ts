// A size of files for people: MB below a gigabyte, else GB (user 2026-10-15: to choose what to
// delete by how big it is).
export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 KB";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${Math.round(bytes / 1024 ** 2)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}
