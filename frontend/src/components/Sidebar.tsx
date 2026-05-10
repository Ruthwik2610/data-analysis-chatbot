"use client";

import { useState } from "react";
import { Database, Folder, MessageSquare, Plus, X, Eye, ChevronLeft, UserRound, LayoutGrid } from "lucide-react";
import type { ChatSummary, Source, Project } from "@/lib/types";
import { displaySourceName } from "@/lib/displayNames";
import { SkeletonChatList } from "./SkeletonLoader";
import Link from "next/link";
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
  onPreviewSource?: (id: string) => void;
  userEmail?: string;
  onToggleCollapse?: () => void;
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
  const [clearConfirm, setClearConfirm] = useState(false);
  return (
    <aside
      className="flex flex-col h-full flex-shrink-0 relative z-20"
      style={{
        width: 280,
        background: "var(--glass-background)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderRight: "1px solid var(--color-border-tertiary)",
      }}
    >
      <div
        className="flex items-center justify-between px-5 py-5"
        style={{ borderBottom: "1px solid var(--color-border-tertiary)" }}
      >
        <Link href="/" className="min-w-0" aria-label="Go to start">
          <img src="/unipro-full-logo.svg" alt="Unipro" className="logo-light" style={{ width: 126, height: "auto", objectFit: "contain" }} />
          <img src="/unipro-full-logo-dark.svg" alt="Unipro" className="logo-dark" style={{ width: 126, height: "auto", objectFit: "contain" }} />
        </Link>
        <button
          onClick={p.onToggleCollapse}
          className="h-8 w-8 rounded-full flex items-center justify-center transition-colors"
          title="Collapse sidebar"
          aria-label="Collapse sidebar"
          style={{ color: "var(--color-text-tertiary)", background: "transparent" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-background-primary)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          <ChevronLeft size={16} strokeWidth={1.7} />
        </button>
      </div>

      <div className="relative px-3 pt-4 pb-3">
        <button
          onClick={() => setClearConfirm(true)}
          className="w-full flex items-center justify-center gap-2 px-3 py-3 text-[15px] font-semibold rounded-[12px] transition-colors"
          style={{
            border: "1px solid #1d4ed8",
            color: "#ffffff",
            background: "#2563eb",
            boxShadow: "0 16px 30px -22px rgba(37, 99, 235, 0.9)",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#1d4ed8")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "#2563eb")}
        >
          <Plus size={18} strokeWidth={1.9} />
          <span>Clear screen</span>
        </button>
        {clearConfirm && (
          <ConfirmPopover
            title="Clear this screen?"
            body="Your saved chat history stays available."
            onCancel={() => setClearConfirm(false)}
            onConfirm={() => {
              setClearConfirm(false);
              p.onNewChat();
            }}
          />
        )}
      </div>

      <div className="flex flex-col flex-1 overflow-y-auto min-h-0 scrollbar-thin pb-3">
        <div className="flex items-center justify-between pr-3">
          <SectionLabel>Today</SectionLabel>
          <button
            onClick={p.onNewChat}
            className="p-1.5 rounded-full transition-colors"
            title="New chat"
            style={{ color: "var(--color-text-tertiary)" }}
          >
            <Plus size={13} />
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

        <div className="mt-4 flex items-center justify-between pr-3">
          <SectionLabel>Projects</SectionLabel>
          <button onClick={p.onNewProject} className="p-1.5 rounded-full transition-colors" title="New Project" style={{ color: "var(--color-text-tertiary)" }}>
            <Plus size={13} />
          </button>
        </div>
        {p.projects.length === 0 && (
          <EmptyState>No projects</EmptyState>
        )}
        {p.projects.slice(0, 5).map((project) => (
          <ProjectRow
            key={project.id}
            project={project}
            isActive={project.id === p.currentProjectId}
            onSelect={() => p.onSelectProject(project.id)}
            onDelete={() => p.onDeleteProject(project.id)}
          />
        ))}

        <div className="mt-4">
          <SectionLabel>Sources</SectionLabel>
        </div>
        {p.sources.length === 0 && (
          <EmptyState>No sources attached</EmptyState>
        )}
        <div className="px-3">
          {p.sources.slice(0, 7).map((src) => (
            <KbRow
              key={src.id}
              source={src}
              selected={p.selectedSourceIds.includes(src.id)}
              onToggle={() => p.onToggleSource(src.id)}
              onDelete={() => p.onDeleteSource(src.id)}
              onPreview={() => p.onPreviewSource?.(src.id)}
            />
          ))}
        </div>
      </div>

      {/* Footer / Admin */}
      <div className="px-4 pt-3 pb-4" style={{ borderTop: "1px solid var(--color-border-tertiary)" }}>
        <div className="mb-3 flex items-center gap-3">
          <div className="h-9 w-9 rounded-full flex items-center justify-center" style={{ background: "#4f46e5", color: "#ffffff" }}>
            <UserRound size={16} strokeWidth={1.7} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold" style={{ color: "var(--color-text-primary)" }}>{p.userEmail || "User Account"}</div>
            <div className="text-[11.5px]" style={{ color: "var(--color-text-tertiary)" }}>Private workspace</div>
          </div>
        </div>
        <Link
          href="/admin"
          className="flex items-center gap-2 w-full px-3 py-2 rounded-[10px] text-[13px] transition-colors"
          style={{
            color: "var(--color-text-secondary)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--color-background-primary)";
            e.currentTarget.style.color = "var(--color-text-primary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "var(--color-text-secondary)";
          }}
        >
          <LayoutGrid size={13} strokeWidth={1.5} className="text-blue-500" />
          Admin Control Center
        </Link>
      </div>
    </aside>
  );
}

function ConfirmPopover({
  title,
  body,
  onCancel,
  onConfirm,
}: {
  title: string;
  body: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="absolute left-3 right-3 top-[76px] z-20 rounded-[12px] p-3 text-[12px]"
      style={{ background: "var(--color-background-elevated)", border: "1px solid var(--color-border-secondary)", boxShadow: "var(--shadow-lg)" }}
    >
      <div className="font-semibold" style={{ color: "var(--color-text-primary)" }}>{title}</div>
      <div className="mt-1" style={{ color: "var(--color-text-tertiary)" }}>{body}</div>
      <div className="mt-3 flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-[8px] px-2.5 py-1.5" style={{ color: "var(--color-text-secondary)", border: "1px solid var(--color-border-tertiary)" }}>Cancel</button>
        <button type="button" onClick={onConfirm} className="rounded-[8px] px-2.5 py-1.5 font-medium" style={{ background: "#2563eb", color: "#ffffff" }}>Clear</button>
      </div>
    </div>
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
      className={clsx("group mx-3 mb-1 flex items-center pr-1 transition-colors")}
      style={{
        background: isActive ? "#eef4ff" : "transparent",
        border: `1px solid ${isActive ? "rgba(37, 99, 235, 0.18)" : "transparent"}`,
        borderRadius: 12,
        boxShadow: isActive ? "var(--shadow-sm)" : "none",
      }}
    >
      <button
        onClick={onSelect}
        className="flex-1 truncate text-left px-3 py-2.5 text-[13px] flex items-center gap-2"
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
      className={clsx("group mx-3 mb-1 flex items-center pr-1 transition-colors")}
      style={{
        background: isActive ? "#eef4ff" : "transparent",
        border: `1px solid ${isActive ? "rgba(37, 99, 235, 0.18)" : "transparent"}`,
        borderRadius: 12,
        boxShadow: isActive ? "var(--shadow-sm)" : "none",
      }}
    >
      <button
        onClick={onSelect}
        className="flex-1 truncate text-left px-3 py-2.5 text-[13px] flex items-center gap-2"
        style={{ color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)" }}
        title={chat.title}
      >
        <MessageSquare size={13} strokeWidth={1.6} />
        <span className="truncate">{chat.title || "New chat"}</span>
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
  onPreview,
}: {
  source: Source;
  selected: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onPreview?: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  return (
    <div className="group relative flex items-center gap-1.5 py-1.5">
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
        </button>
      {source.kind !== "mcp" && onPreview && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onPreview();
          }}
          className="p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
          style={{ color: "var(--color-text-tertiary)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "var(--color-text-primary)";
            e.currentTarget.style.background = "var(--color-background-secondary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--color-text-tertiary)";
            e.currentTarget.style.background = "transparent";
          }}
          title="Preview Data"
        >
          <Eye size={13} strokeWidth={1.5} />
        </button>
      )}
      {source.kind !== "mcp" && (
        <button
          onClick={() => setConfirming(true)}
          className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-black/5"
          title="Remove"
        >
          <X size={11} stroke="var(--color-text-tertiary)" />
        </button>
      )}
      {confirming && (
        <div className="absolute right-0 top-7 z-20 w-[220px] rounded-[10px] p-3 text-[12px]" style={{ background: "var(--color-background-elevated)", border: "1px solid var(--color-border-secondary)", boxShadow: "var(--shadow-lg)" }}>
          <div className="font-semibold" style={{ color: "var(--color-text-primary)" }}>Delete this file?</div>
          <div className="mt-1" style={{ color: "var(--color-text-tertiary)" }}>This removes it from your workspace.</div>
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" onClick={() => setConfirming(false)} className="rounded-[8px] px-2.5 py-1.5" style={{ color: "var(--color-text-secondary)", border: "1px solid var(--color-border-tertiary)" }}>Cancel</button>
            <button type="button" onClick={() => { setConfirming(false); onDelete(); }} className="rounded-[8px] px-2.5 py-1.5 font-medium" style={{ background: "#dc2626", color: "#ffffff" }}>Delete</button>
          </div>
        </div>
      )}
    </div>
  );
}
