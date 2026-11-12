// Closing what is open over the screen, as is usual (user 2026-10-16): an ✕ at its top right,
// "close" in its hover and for screen readers. Not coloured because a window's top right ✕ is
// the usual form and its place is known; the loupe keeps a purple "close" before the image
// steps, found at once on a busy screen.
import { X } from "lucide-react";
import type { ComponentProps } from "react";
import { t } from "@/i18n";

export function CloseButton(props: ComponentProps<"button">) {
  return (
    <button
      type="button"
      aria-label={t("common.close")}
      title={t("common.close")}
      {...props}
      className="grid size-8 shrink-0 cursor-pointer place-items-center rounded-md text-muted-foreground hover:bg-hover hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-1"
    >
      <X className="size-5" aria-hidden />
    </button>
  );
}
