// The page over every screen once the app has stopped (2026-10-30: quit from its small window,
// the page stayed and its buttons could be pressed): what to do next. Quit from the page it says
// so; stopped otherwise (the small window, the app ending), it says the app has stopped. It goes
// once the app answers again.
import { t } from "@/i18n";

export function Stopped({ title }: { title: string }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="app-stopped"
      className="fixed inset-0 z-50 flex items-center justify-center bg-table p-6"
    >
      <div className="flex max-w-md flex-col gap-2 rounded-md border border-line bg-sheet p-6">
        <strong id="app-stopped" className="text-lg">
          {title}
        </strong>
        <p className="m-0 text-muted-foreground">{t("quit.again")}</p>
      </div>
    </div>
  );
}
