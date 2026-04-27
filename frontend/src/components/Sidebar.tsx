"use client";

import { Plus, X, Circle } from "lucide-react";
import type { ChatSummary, Source } from "@/lib/types";
import clsx from "clsx";

interface SidebarProps {
  chats: ChatSummary[];
  currentChatId: string | null;
  sources: Source[];
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onActivateSource: (id: string) => void;
  onDeleteSource: (id: string) => void;
}

const KIND_COLOR: Record<string, string> = {
  csv: "var(--color-text-success)",
  xlsx: "var(--color-text-success)",
  json: "var(--color-text-success)",
  duckdb: "var(--color-text-warning)",
  api: "var(--color-text-info)",
  mcp: "var(--color-text-warning)",
};

export function Sidebar(p: SidebarProps) {
  return (
    <aside
      className="flex flex-col flex-shrink-0"
      style={{
        width: 240,
        background: "var(--color-background-secondary)",
        borderRight: "0.5px solid var(--color-border-tertiary)",
      }}
    >
      <div
        className="flex items-center gap-2 px-4 pb-3 pt-4 text-[13px] font-medium"
        style={{ borderBottom: "0.5px solid var(--color-border-tertiary)", color: "var(--color-text-primary)" }}
      >
        <div
          className="rounded-full w-5 h-5 flex items-center justify-center"
          style={{ background: "var(--color-text-primary)" }}
        >
          <Circle size={10} stroke="var(--color-background-primary)" strokeWidth={1.5} fill="transparent" />
        </div>
        Data Chat
      </div>

      <div className="px-3 pt-3 pb-2">
        <button
          onClick={p.onNewChat}
          className="w-full flex items-center gap-2 px-3 py-[7px] text-[13px] rounded-[10px] transition-colors"
          style={{
            border: "0.5px solid var(--color-border-secondary)",
            color: "var(--color-text-secondary)",
            background: "transparent",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-background-primary)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          <Plus size={12} strokeWidth={1.5} />
          New chat
        </button>
      </div>

      <SectionLabel>Recents</SectionLabel>

      <div className="flex flex-col flex-1 overflow-y-auto scrollbar-thin">
        {p.chats.length === 0 && (
          <div className="px-4 py-2 text-[12px]" style={{ color: "var(--color-text-tertiary)" }}>
            No chats yet
          </div>
        )}
        {p.chats.map((chat) => (
          <ChatRow
            key={chat.id}
            chat={chat}
            isActive={chat.id === p.currentChatId}
            onSelect={() => p.onSelectChat(chat.id)}
            onDelete={() => p.onDeleteChat(chat.id)}
          />
        ))}
      </div>

      <div
        className="px-4 py-3"
        style={{ borderTop: "0.5px solid var(--color-border-tertiary)" }}
      >
        <div
          className="text-[11px] font-medium uppercase mb-2 tracking-wider"
          style={{ color: "var(--color-text-tertiary)", letterSpacing: "0.06em" }}
        >
          Knowledge base
        </div>
        {p.sources.length === 0 && (
          <div className="text-[12px]" style={{ color: "var(--color-text-tertiary)" }}>
            No sources attached
          </div>
        )}
        {p.sources.map((src) => (
          <KbRow
            key={src.id}
            source={src}
            onActivate={() => p.onActivateSource(src.id)}
            onDelete={() => p.onDeleteSource(src.id)}
          />
        ))}
      </div>
    </aside>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="px-4 pt-3 pb-1 text-[11px] font-medium uppercase"
      style={{ color: "var(--color-text-tertiary)", letterSpacing: "0.06em" }}
    >
      {children}
    </div>
  );
}

function ChatRow({
  chat,
  isActive,
  onSelect,
  onDelete,
}: {
  chat: ChatSummary;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={clsx("group flex items-center pr-1 transition-colors", isActive && "bg-active")}
      style={{ background: isActive ? "var(--color-background-primary)" : "transparent" }}
    >
      <button
        onClick={onSelect}
        className="flex-1 truncate text-left px-4 py-[7px] text-[13px]"
        style={{ color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)" }}
        title={chat.title}
      >
        {chat.title || "New chat"}
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-black/5"
        title="Delete"
      >
        <X size={12} stroke="var(--color-text-tertiary)" />
      </button>
    </div>
  );
}

function KbRow({
  source,
  onActivate,
  onDelete,
}: {
  source: Source;
  onActivate: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="group flex items-center gap-1.5 py-[5px]">
      <button
        onClick={onActivate}
        className="flex items-center gap-1.5 flex-1 min-w-0 text-left text-[12px]"
        style={{ color: "var(--color-text-secondary)" }}
        title={`${source.kind.toUpperCase()} · ${source.rows.toLocaleString()} rows`}
      >
        <div
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{
            background: source.active ? KIND_COLOR[source.kind] || "var(--color-text-success)" : "var(--color-border-secondary)",
          }}
        />
        <span className="truncate" style={{ color: source.active ? "var(--color-text-primary)" : undefined }}>
          {source.name}
        </span>
      </button>
      <button
        onClick={onDelete}
        className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-black/5"
        title="Remove"
      >
        <X size={11} stroke="var(--color-text-tertiary)" />
      </button>
    </div>
  );
}
