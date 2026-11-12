// A worker's chats (user 2026-10-09: as in any chat app): the history under the talk's title,
// the latest first, each with its first words, when and how long. Pressing one goes on in it;
// Delete asks first, then the chat and its lines go (boxes, notes and data stay).
import { useState } from "react";
import type { AgentChat } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Confirm } from "@/components/ui/dialog";
import { t, when } from "@/i18n";
import { historyWords } from "@/lib/talk";

export function ChatList({
  chats,
  current,
  onOpen,
  onDelete,
}: {
  chats: AgentChat[];
  current: number | null;
  onOpen: (chat: number) => void;
  onDelete: (chat: number) => void;
}) {
  const [asking, setAsking] = useState<AgentChat | null>(null);
  const titleOf = (chat: AgentChat) => chat.title ?? t("side.chat.untitled");
  return (
    <section
      aria-label={historyWords(chats, current)}
      className="flex max-h-60 flex-col gap-0.5 overflow-y-auto border-b border-line bg-sheet px-2 py-1.5"
    >
      {chats.map((chat) => (
        <div
          key={chat.id}
          className={`flex items-center gap-2 rounded-md px-2 py-1 text-body ${chat.id === current ? "bg-selected" : "hover:bg-hover"}`}
        >
          <button
            type="button"
            aria-current={chat.id === current ? "true" : undefined}
            onClick={() => onOpen(chat.id)}
            className="flex min-w-0 flex-1 cursor-pointer flex-col items-start text-left"
          >
            <span className={`w-full truncate ${chat.id === current ? "font-semibold" : ""}`}>
              {titleOf(chat)}
            </span>
            <span className="text-note text-muted-foreground">
              {when(chat.updated_at)} · {t("side.chat.lines", { count: chat.lines })}
            </span>
          </button>
          <Button
            variant="link"
            size="small"
            className="text-failed"
            onClick={() => setAsking(chat)}
          >
            {t("side.chat.delete")}
          </Button>
        </div>
      ))}
      <Confirm
        open={asking !== null}
        title={asking ? t("side.chat.deleteTitle", { title: titleOf(asking) }) : ""}
        message={asking ? t("side.chat.deleteBody", { title: titleOf(asking) }) : ""}
        confirm={t("side.chat.delete")}
        destructive
        onConfirm={() => {
          if (asking) onDelete(asking.id);
          setAsking(null);
        }}
        onCancel={() => setAsking(null)}
      />
    </section>
  );
}
