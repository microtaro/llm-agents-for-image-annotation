// The way back from a screen that is not a level below (user 2026-10-14: "A › B" read as going
// into a folder; a set of things, the decisions, the settings are looked at and left): a button
// with an arrow, back where it was opened from.
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";

export function BackButton({ fallback }: { fallback: () => void }) {
  return (
    <Button
      size="small"
      onClick={() => (window.history.length > 1 ? window.history.back() : fallback())}
    >
      <ArrowLeft className="size-4" aria-hidden />
      {t("common.back")}
    </Button>
  );
}
