// What the person writes to the worker (user 2026-10-12, types design 16.1): whom it goes to and
// what the right shows, above the field; the field grows with the words up to six lines (two
// rows hid a short request of several lines). Enter sends, Shift+Enter is a new line, not while
// the Japanese input is still converting.
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";

const MAX_LINES = 6;

export function AskForm({
  name,
  right,
  text,
  onText,
  onSend,
}: {
  /** The worker talked with. */
  name: string;
  /** What the right shows now (empty: not said). */
  right: string;
  text: string;
  onText: (next: string) => void;
  onSend: (words: string) => void;
}) {
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    const cs = getComputedStyle(el);
    const line = parseFloat(cs.lineHeight) || 21;
    const border = parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
    const padding = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    el.style.height = `${Math.min(el.scrollHeight + border, line * MAX_LINES + padding + border)}px`;
  }, [text]);
  const send = () => {
    if (text.trim()) onSend(text.trim());
  };
  const scope = right ? t("side.scope", { agent: name, right }) : name;
  return (
    <form
      className="flex flex-col gap-1 border-t border-line px-3 py-2 max-[999px]:sticky max-[999px]:bottom-0 max-[999px]:bg-surface"
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
    >
      <p className="m-0 flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
        <span className="truncate" title={scope}>
          {scope}
        </span>
      </p>
      <div className="flex items-end gap-2">
        <textarea
          ref={field}
          data-ask
          value={text}
          onChange={(e) => onText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send();
            }
          }}
          rows={2}
          aria-label={t("work.ask", { agent: name })}
          placeholder={t("work.ask", { agent: name })}
          className="min-w-0 flex-1 resize-none overflow-y-auto rounded-md border border-line bg-sheet px-2.5 py-1.5 text-sm"
        />
        <Button type="submit" variant="primary" disabled={!text.trim()}>
          {t("work.send")}
        </Button>
      </div>
    </form>
  );
}
