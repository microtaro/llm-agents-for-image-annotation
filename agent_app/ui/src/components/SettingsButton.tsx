// The app's settings, from every screen's top row: a gear in a button's frame, as the light and
// dark switch beside it (user 2026-10-14: a bare link sank into the background, and the gear
// says it without the word). Its name shows on hover.
import { Settings } from "lucide-react";
import { t } from "@/i18n";

export function SettingsButton() {
  return (
    <a
      href="#/settings"
      aria-label={t("settings.title")}
      title={t("settings.title")}
      className="inline-flex size-8 items-center justify-center rounded-md border border-line bg-surface text-ink no-underline hover:bg-hover"
    >
      <Settings className="size-4" aria-hidden />
    </a>
  );
}
