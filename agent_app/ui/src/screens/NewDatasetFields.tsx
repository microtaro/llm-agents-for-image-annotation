// The new dataset's name and purpose (the name first), first in the dialog, before where its
// images come from (user 2026-10-15: below the folders they were hidden; naming came last).
import { t } from "@/i18n";

const FIELD = "min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1.5";

export function NewDatasetFields({
  purpose,
  name,
  onPurpose,
  onName,
}: {
  purpose: string;
  name: string;
  onPurpose: (value: string) => void;
  onName: (value: string) => void;
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      {/* The words in view: a name filled in already hid its placeholder. Each field keeps room
          for its words, a line of its own where the place is narrow (a decision in the talk,
          2026-10-29: side by side there, each showed three letters). */}
      <label className="flex min-w-0 flex-[1_1_16rem] items-center gap-1.5">
        {t("create.name")}
        <span className="text-xs text-muted-foreground">{t("common.required")}</span>
        <input
          required
          value={name}
          maxLength={100}
          onChange={(e) => onName(e.target.value)}
          className={FIELD}
        />
      </label>
      <label className="flex min-w-0 flex-[1_1_16rem] items-center gap-1.5">
        {t("create.purpose")}
        <span className="text-xs text-muted-foreground">{t("common.required")}</span>
        <input
          required
          title={t("create.purpose.fixed")}
          value={purpose}
          maxLength={200}
          onChange={(e) => onPurpose(e.target.value)}
          className={FIELD}
        />
      </label>
    </div>
  );
}

/** What is still missing before making: shown beside the button, so a button that cannot be
 * pressed says why (user 2026-10-15: refusing an empty one must be seen to refuse). */
export function Missing({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <span className="mr-auto text-body text-muted-foreground">
      {t("create.missing", { items: items.join(t("box.plan.separator")) })}
    </span>
  );
}
