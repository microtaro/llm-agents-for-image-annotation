// Quitting the app, at the right end of every screen's top row, a space apart from the settings
// and the light and dark switch (user 2026-10-29: the zip's app runs with no window; the same
// screen everywhere, the work's own too; a power sign is understood by itself, and an end goes
// at the end, as a window's close does): what stops with it is said first; once quit, the page
// says the tab can be closed. Not red: nothing is deleted (DESIGN.md, red is for deleting and
// taking out).
import { Power } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { JobList } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { useApi } from "@/lib/useApi";
import { IN_APP_WINDOW } from "@/lib/appWindow";
import { Stopped } from "./Stopped";

export function QuitButton() {
  const [asking, setAsking] = useState(false);
  const [quit, setQuit] = useState(false);
  const jobs = useApi<JobList>(asking ? "/v1/jobs" : null);
  const going = (jobs.data?.running ?? 0) + (jobs.data?.queued ?? 0);
  return (
    <>
      <button
        type="button"
        aria-label={t("quit.button")}
        title={t("quit.button")}
        onClick={() => setAsking(true)}
        className="ml-3 inline-flex size-8 cursor-pointer items-center justify-center rounded-md border border-line bg-surface text-ink hover:bg-hover"
      >
        <Power className="size-4" aria-hidden />
      </button>
      <Dialog
        open={asking}
        onOpenChange={setAsking}
        title={t("quit.title")}
        footer={
          <>
            <Button onClick={() => setAsking(false)}>{t("common.cancel")}</Button>
            <Button
              variant="primary"
              onClick={async () => {
                try {
                  await api("/v1/quit", { body: {} });
                  setAsking(false);
                  // The app's window closes by itself (lib/appWindow).
                  if (!IN_APP_WINDOW) setQuit(true);
                } catch (reason) {
                  toast.error(errorText(reason));
                }
              }}
            >
              {t("quit.confirm")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-2 px-5 py-4">
          <p className="m-0">{t("quit.body")}</p>
          {going > 0 && <p className="m-0 text-failed">{t("quit.going", { count: going })}</p>}
        </div>
      </Dialog>
      {quit && <Stopped title={t("quit.done")} />}
    </>
  );
}
