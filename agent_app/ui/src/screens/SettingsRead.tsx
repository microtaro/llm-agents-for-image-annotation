// The app's settings on the right, read only, as a worker shows them (definition 71; user
// 2026-10-29: "read only, mind"): each group's settings in the settings screen's words, with their
// value, range and default, then this machine's facts, in one table so the columns line up. They
// are changed only on the settings screen.
import { t } from "@/i18n";
import { formatBytes } from "@/lib/bytes";
import { useModelName } from "@/lib/runChoice";
import { StorageSection } from "./SettingsStorage";

export interface SettingRow {
  key: string;
  group: string;
  value: unknown;
  effort?: string;
  default?: unknown;
  range?: [number, number];
}

const settingText = (value: unknown) =>
  typeof value === "string" || typeof value === "number" || typeof value === "boolean"
    ? String(value)
    : "";

export function SettingsRead({ items }: { items: SettingRow[] }) {
  const modelName = useModelName();
  const groups = [...new Set(items.map((row) => row.group))];
  const named = (row: SettingRow) =>
    row.group === "machine" ? `objects.settings.${row.key}` : `settings.${row.key}`;
  const value = (row: SettingRow) =>
    row.effort
      ? `${modelName(settingText(row.value))} · ${row.effort}`
      : row.key === "free_memory_mb"
        ? formatBytes(Number(row.value) * 1024 * 1024)
        : settingText(row.value);
  const about = (row: SettingRow) =>
    [
      row.range ? t("settings.range", { min: row.range[0], max: row.range[1] }) : "",
      row.default !== undefined && !row.effort
        ? t("objects.settings.default", { value: settingText(row.default) })
        : "",
    ]
      .filter(Boolean)
      .join(" · ");
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <p className="m-0 text-muted-foreground">{t("objects.settings.read")}</p>
      <dl className="m-0 grid grid-cols-[auto_auto_1fr] items-baseline gap-x-4 gap-y-1.5">
        {groups.map((group) => (
          <div key={group} className="contents">
            <h2 className="col-span-3 m-0 mt-2 text-base first:mt-0">
              {group === "machine" ? t("objects.settings.machine") : t(`settings.group.${group}`)}
            </h2>
            {items
              .filter((row) => row.group === group && row.key !== "storage")
              .map((row) => (
                <div key={row.key} className="contents">
                  {/* What it does, as on the settings screen (definition 72). */}
                  <dt title={t(`${named(row)}.tip`)}>{t(named(row))}</dt>
                  <dd className="m-0 tabular-nums">{value(row)}</dd>
                  <dd className="m-0 text-xs text-muted-foreground">{about(row)}</dd>
                </div>
              ))}
          </div>
        ))}
      </dl>
      {/* Where the data is kept, as the settings screen shows it. */}
      {items.some((row) => row.key === "storage") && <StorageSection />}
    </div>
  );
}
