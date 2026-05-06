"use client";

import { useState } from "react";
import { Database, Folder, MessageSquare, Plus, X } from "lucide-react";
import type { ChatSummary, Source, Project } from "@/lib/types";
import { displaySourceName } from "@/lib/displayNames";
import { SkeletonChatList } from "./SkeletonLoader";
import clsx from "clsx";

interface SidebarProps {
  chats: ChatSummary[];
  currentChatId: string | null;
  sources: Source[];
  selectedSourceIds: string[];
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onToggleSource: (id: string) => void;
  onDeleteSource: (id: string) => void;
  projects: Project[];
  currentProjectId: string | null;
  onSelectProject: (id: string) => void;
  onNewProject: () => void;
  onDeleteProject: (id: string) => void;
  chatLoading?: boolean;
}

const KIND_COLOR: Record<string, string> = {
  csv: "var(--color-text-success)",
  xlsx: "var(--color-text-success)",
  json: "var(--color-text-success)",
  pdf: "var(--color-text-success)",
  duckdb: "var(--color-text-warning)",
  api: "var(--color-text-info)",
  mcp: "var(--color-text-warning)",
  multi: "var(--color-text-warning)",
};

export function Sidebar(p: SidebarProps) {
  const [tab, setTab] = useState<"chats" | "projects" | "sources">("chats");

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
        <img src="/unipro-icon.svg" alt="Unipro" className="w-6 h-6" />
        Unipro Chat
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
          Clear screen
        </button>
      </div>

      <div role="tablist" aria-label="Sidebar sections" className="grid grid-cols-3 gap-1 px-3 py-2">
        <SidebarTab label="Chats" icon={<MessageSquare size={12} />} selected={tab === "chats"} onClick={() => setTab("chats")} />
        <SidebarTab label="Projects" icon={<Folder size={12} />} selected={tab === "projects"} onClick={() => setTab("projects")} />
        <SidebarTab label="Sources" icon={<Database size={12} />} selected={tab === "sources"} onClick={() => setTab("sources")} />
      </div>

      <div className="flex flex-col flex-1 overflow-y-auto scrollbar-thin pb-3">
        {tab === "chats" && (
          <>
            <div className="flex items-center justify-between pr-3">
              <SectionLabel>Recents</SectionLabel>
              <button
                onClick={p.onNewChat}
                className="p-1 rounded hover:bg-black/5"
                title="New chat"
              >
                <Plus size={12} stroke="var(--color-text-tertiary)" />
              </button>
            </div>
            {p.chatLoading ? (
              <SkeletonChatList />
            ) : (
              <>
                {p.chats.length === 0 && <EmptyState>No chats yet</EmptyState>}
                {p.chats.map((chat) => (
                  <ChatRow
                    key={chat.id}
                    chat={chat}
                    isActive={chat.id === p.currentChatId}
                    onSelect={() => p.onSelectChat(chat.id)}
                    onDelete={() => p.onDeleteChat(chat.id)}
                  />
                ))}
              </>
            )}
          </>
        )}

        {tab === "projects" && (
          <>
            <div className="flex items-center justify-between pr-3">
              <SectionLabel>Projects</SectionLabel>
              <button onClick={p.onNewProject} className="p-1 rounded hover:bg-black/5" title="New Project">
                <Plus size={12} stroke="var(--color-text-tertiary)" />
              </button>
            </div>
            {p.projects.length === 0 && (
              <EmptyState>No projects</EmptyState>
            )}
            {p.projects.map((project) => (
              <ProjectRow
                key={project.id}
                project={project}
                isActive={project.id === p.currentProjectId}
                onSelect={() => p.onSelectProject(project.id)}
                onDelete={() => p.onDeleteProject(project.id)}
              />
            ))}
          </>
        )}

        {tab === "sources" && (
          <>
            <SectionLabel>Sources</SectionLabel>
            {p.sources.length === 0 && (
              <EmptyState>No sources attached</EmptyState>
            )}
            <div className="px-3">
              {p.sources.map((src) => (
                <KbRow
                  key={src.id}
                  source={src}
                  selected={p.selectedSourceIds.includes(src.id)}
                  onToggle={() => p.onToggleSource(src.id)}
                  onDelete={() => p.onDeleteSource(src.id)}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </aside>
  );
}

function SidebarTab({ label, icon, selected, onClick }: { label: string; icon: React.ReactNode; selected: boolean; onClick: () => void }) {
  return (
    <button
      role="tab"
      aria-selected={selected}
      onClick={onClick}
      className="flex items-center justify-center gap-1 rounded-[8px] px-1.5 py-1.5 text-[11.5px] transition-colors"
      style={{
        background: selected ? "var(--color-background-primary)" : "transparent",
        border: selected ? "0.5px solid var(--color-border-tertiary)" : "0.5px solid transparent",
        color: selected ? "var(--color-text-primary)" : "var(--color-text-tertiary)",
      }}
    >
      {icon}
      {label}
    </button>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-4 py-2 text-[12px]" style={{ color: "var(--color-text-tertiary)" }}>
      {children}
    </div>
  );
}

function ProjectRow({
  project,
  isActive,
  onSelect,
  onDelete,
}: {
  project: Project;
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
        className="flex-1 truncate text-left px-4 py-[7px] text-[13px] flex items-center gap-2"
        style={{ color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)" }}
        title={project.title}
      >
        <Folder size={12} strokeWidth={1.5} />
        {project.title}
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-black/5"
        title="Delete Project"
      >
        <X size={12} stroke="var(--color-text-tertiary)" />
      </button>
    </div>
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
  selected,
  onToggle,
  onDelete,
}: {
  source: Source;
  selected: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="group flex items-center gap-1.5 py-[5px]">
        <button
          onClick={onToggle}
          className="flex items-center gap-1.5 flex-1 min-w-0 text-left text-[12px]"
          style={{ color: "var(--color-text-secondary)" }}
          title={`${source.kind.toUpperCase()} · ${source.rows.toLocaleString()} ${source.kind === "mcp" ? "tools" : "rows"}`}
        >
          <div
            className="w-3 h-3 rounded-[4px] flex-shrink-0"
            style={{
              background: selected ? KIND_COLOR[source.kind] || "var(--color-text-success)" : "transparent",
              border: `1px solid ${selected ? KIND_COLOR[source.kind] || "var(--color-text-success)" : "var(--color-border-secondary)"}`,
            }}
          />
          <span className="truncate" style={{ color: selected ? "var(--color-text-primary)" : undefined }}>
            {displaySourceName(source.name)}
          </span>
          <span
            style={{
              fontSize: 8,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.07em",
              padding: "1px 4px",
              borderRadius: 3,
              flexShrink: 0,
              background: KIND_COLOR[source.kind] ? `${KIND_COLOR[source.kind]}20` : "var(--color-background-tertiary)",
              color: KIND_COLOR[source.kind] || "var(--color-text-tertiary)",
            }}
          >
            {source.kind}
          </span>
        </button>
      {source.kind !== "mcp" && (
        <button
          onClick={onDelete}
          className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-black/5"
          title="Remove"
        >
          <X size={11} stroke="var(--color-text-tertiary)" />
        </button>
      )}
    </div>
  );
}
