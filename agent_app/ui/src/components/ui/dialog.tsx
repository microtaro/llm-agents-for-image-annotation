// The app's dialog (Radix): role, modal and the title label come from the parts (AGENTS.md).
import { Dialog as Primitive } from "radix-ui";
import type { ReactNode } from "react";
import { t } from "@/i18n";
import { Button } from "./button";
import { CloseButton } from "./close-button";

export function Dialog({
  open,
  onOpenChange,
  title,
  children,
  footer,
  wide = false,
  full = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  /** The whole window (things compared side by side, opened large). */
  full?: boolean;
}) {
  return (
    <Primitive.Root open={open} onOpenChange={onOpenChange}>
      <Primitive.Portal>
        <Primitive.Overlay className="fixed inset-0 z-40 bg-[rgba(30,38,50,0.45)]" />
        <Primitive.Content
          aria-describedby={undefined}
          aria-modal="true"
          // Opened, the first field takes the keys, not the close at the top (user 2026-10-16:
          // the ✕ looked chosen); with no field, the window itself.
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            const content = event.currentTarget as HTMLElement | null;
            (
              content?.querySelector<HTMLElement>("input, textarea, select") ??
              content?.querySelector<HTMLElement>("[data-dialog-scroll]") ??
              content
            )?.focus();
          }}
          className={`fixed z-40 flex flex-col rounded-md border border-line bg-sheet ${full ? "inset-3" : `left-1/2 top-16 max-h-[calc(100vh-6rem)] w-[calc(100%-2rem)] -translate-x-1/2 ${wide ? "max-w-[860px]" : "max-w-[560px]"}`}`}
        >
          <div className="flex items-center gap-3 border-b border-line px-5 py-3">
            <Primitive.Title className="m-0 text-title font-semibold">{title}</Primitive.Title>
            <span className="flex-1" />
            <Primitive.Close asChild>
              <CloseButton />
            </Primitive.Close>
          </div>
          {/* Focused when there is no field, so the keys scroll it (PageDown, arrows). */}
          <div
            data-dialog-scroll
            tabIndex={-1}
            className={`overflow-y-auto outline-none ${full ? "min-h-0 flex-1" : ""}`}
          >
            {children}
          </div>
          {footer && (
            <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>
          )}
        </Primitive.Content>
      </Primitive.Portal>
    </Primitive.Root>
  );
}

/** Asks before something that cannot be undone (DESIGN.md 3: never window.confirm). What one
 * pressed it for comes first, then the way out (user 2026-10-23: it was pressed meaning to do
 * it); a title alone says it when there is nothing more to say. */
export function Confirm({
  open,
  title,
  message,
  confirm,
  cancel,
  destructive = false,
  onConfirm,
  onCancel,
  children,
}: {
  open: boolean;
  title: string;
  message?: string;
  /** What it covers, below the message. */
  children?: ReactNode;
  confirm: string;
  /** The way out's words (none: Cancel). */
  cancel?: string;
  /** Deletes or takes out: the confirm button is red. */
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && onCancel()}
      title={title}
      footer={
        <>
          <Button variant={destructive ? "destructive" : "primary"} onClick={onConfirm}>
            {confirm}
          </Button>
          <Button onClick={onCancel}>{cancel ?? t("common.cancel")}</Button>
        </>
      }
    >
      {message && <p className="m-0 px-5 py-4">{message}</p>}
      {children}
    </Dialog>
  );
}
