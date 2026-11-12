// The shared notes for every worker AI (definition 18.15): what the worker AI of every dataset
// reads with the plan, kept as versions. Seen and changed with the rest of what the worker AI
// reads, under the plan (definition 55; user 2026-10-27: on the annotating screen they were
// large and asked nothing of the person there; a run's card says the version it reads and a
// change since the last run). A run holds the version it used, so changing them never changes
// a run already decided.
import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { t, when } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { useApi } from "@/lib/useApi";

interface Notes {
  revision: number;
  text: string;
  created_at: string;
}

export function SharedNotes() {
  const found = useApi<{ latest: Notes | null }>("/v1/shared-notes");
  const latest = found.data?.latest ?? null;
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = () => {
    setBusy(true);
    void api<Notes>("/v1/shared-notes", { method: "PUT", body: { text: draft ?? "" } })
      .then((saved) => {
        toast.success(t("notes.saved", { revision: saved.revision }));
        setDraft(null);
        found.reload();
      })
      .catch((reason) => toast.error(errorText(reason)))
      .finally(() => setBusy(false));
  };
  // Nothing said until read (user 2026-10-27: "none" showed while they were being read).
  if (found.error) return <p className="m-0 text-body text-failed">{errorText(found.error)}</p>;
  if (!found.data) return null;
  return (
    <section
      aria-label={t("notes.title")}
      className="flex flex-col gap-1 rounded-md border border-line bg-surface px-2.5 py-1.5"
    >
      <span className="flex flex-wrap items-baseline gap-x-2">
        <b>
          {latest ? t("plan.gets.notes", { revision: latest.revision }) : t("plan.gets.notes.none")}
        </b>
        {latest && <span className="text-xs text-muted-foreground">{when(latest.created_at)}</span>}
        {draft === null && (
          <Button size="small" variant="link" onClick={() => setDraft(latest?.text ?? "")}>
            {t("notes.edit")}
          </Button>
        )}
      </span>
      {draft === null ? (
        latest && <p className="m-0 whitespace-pre-wrap">{latest.text || t("notes.empty")}</p>
      ) : (
        <>
          <textarea
            rows={4}
            value={draft}
            maxLength={4000}
            aria-label={t("notes.title")}
            onChange={(e) => setDraft(e.target.value)}
            className="resize-y rounded-md border border-line bg-surface px-2 py-1.5"
          />
          <span className="flex gap-2">
            <Button
              size="small"
              variant="primary"
              disabled={busy || draft.trim() === (latest?.text ?? "")}
              onClick={save}
            >
              {t("notes.save", { revision: (latest?.revision ?? 0) + 1 })}
            </Button>
            <Button size="small" onClick={() => setDraft(null)}>
              {t("notes.cancel")}
            </Button>
          </span>
        </>
      )}
    </section>
  );
}
