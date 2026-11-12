// Where the app keeps its data and how big it is (user 2026-10-28: the app keeps its own copy of
// every image, so it grows): the database, the files by kind and the room left on the disk.
import { t } from "@/i18n";
import { formatBytes } from "@/lib/bytes";
import { useApi } from "@/lib/useApi";

interface Kept {
  count: number;
  bytes: number;
}

interface Storage {
  database: { path: string; bytes: number };
  files: { path: string; images: Kept; masks: Kept; sheets: Kept };
  disk: { free: number; total: number };
}

const KINDS = ["images", "masks", "sheets"] as const;

export function StorageSection() {
  const found = useApi<Storage>("/v1/storage");
  const storage = found.data;
  if (!storage) return null;
  return (
    <section
      aria-labelledby="settings-storage"
      className="flex flex-col gap-2 rounded-md border border-line bg-sheet p-4"
    >
      <h2 id="settings-storage" className="m-0 text-base">
        {t("settings.storage")}
      </h2>
      <dl className="m-0 grid grid-cols-[auto_auto_1fr] items-baseline gap-x-4 gap-y-1.5">
        <dt>{t("settings.storage.database")}</dt>
        <dd className="m-0 text-right tabular-nums">{formatBytes(storage.database.bytes)}</dd>
        <dd className="m-0 text-xs text-muted-foreground [overflow-wrap:anywhere]">
          {storage.database.path}
        </dd>
        {KINDS.map((kind) => (
          <div key={kind} className="contents">
            <dt>{t(`settings.storage.${kind}`, { count: storage.files[kind].count })}</dt>
            <dd className="m-0 text-right tabular-nums">
              {formatBytes(storage.files[kind].bytes)}
            </dd>
            <dd className="m-0 text-xs text-muted-foreground [overflow-wrap:anywhere]">
              {kind === "images" ? storage.files.path : ""}
            </dd>
          </div>
        ))}
        <dt>{t("settings.storage.free")}</dt>
        <dd className="m-0 text-right tabular-nums">{formatBytes(storage.disk.free)}</dd>
        <dd className="m-0 text-xs text-muted-foreground">
          {t("settings.storage.total", { size: formatBytes(storage.disk.total) })}
        </dd>
      </dl>
    </section>
  );
}
