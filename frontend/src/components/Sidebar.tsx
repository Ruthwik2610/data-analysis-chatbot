"use client";

import { Bug, Folder, MessageSquare, Plus, X, ChevronLeft, UserRound, LayoutGrid } from "lucide-react";
import type { ChatSummary, Project } from "@/lib/types";
import { SkeletonChatList } from "./SkeletonLoader";
import Link from "next/link";
import clsx from "clsx";

interface SidebarProps {
  chats: ChatSummary[];
  currentChatId: string | null;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  projects: Project[];
  currentProjectId: string | null;
  onSelectProject: (id: string) => void;
  onNewProject: () => void;
  onDeleteProject: (id: string) => void;
  chatLoading?: boolean;
  userEmail?: string;
  onToggleCollapse?: () => void;
  isAdmin?: boolean;
}

export function Sidebar(p: SidebarProps) {
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

      <div className="flex flex-col flex-1 overflow-y-auto min-h-0 scrollbar-thin pb-3">
        <div className="flex items-center justify-between pr-3">
          <SectionLabel>Today</SectionLabel>
          <button
            onClick={p.onNewChat}
            className="p-1.5 rounded-full transition-colors"
            title="New chat"
            aria-label="New chat"
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
          <button onClick={p.onNewProject} className="p-1.5 rounded-full transition-colors" title="New Project" aria-label="New project" style={{ color: "var(--color-text-tertiary)" }}>
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
        {p.isAdmin && (
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
        )}
        {p.isAdmin && (
          <Link
            href="/admin/feedback"
            className="mt-1 flex items-center gap-2 w-full px-3 py-2 rounded-[10px] text-[13px] transition-colors"
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
            <Bug size={13} strokeWidth={1.5} className="text-amber-500" />
            Debug review inbox
          </Link>
        )}
      </div>
    </aside>
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
  const title = project.title || "Untitled project";
  return (
    <div
      className={clsx("group mx-3 mb-1 flex items-center pr-1 transition-colors")}
      style={{
        background: isActive ? "var(--color-background-info)" : "transparent",
        border: `1px solid ${isActive ? "var(--color-border-info)" : "transparent"}`,
        borderRadius: 12,
        boxShadow: isActive ? "var(--shadow-sm)" : "none",
      }}
    >
      <button
        onClick={onSelect}
        className="flex-1 truncate text-left px-3 py-2.5 text-[13px] flex items-center gap-2"
        style={{ color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)" }}
        title={title}
      >
        <Folder size={12} strokeWidth={1.5} />
        {title}
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-black/5"
        title="Delete Project"
        aria-label={`Delete project ${title}`}
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
  const title = chat.title || "Untitled chat";
  return (
    <div
      className={clsx("group mx-3 mb-1 flex items-center pr-1 transition-colors")}
      style={{
        background: isActive ? "var(--color-background-info)" : "transparent",
        border: `1px solid ${isActive ? "var(--color-border-info)" : "transparent"}`,
        borderRadius: 12,
        boxShadow: isActive ? "var(--shadow-sm)" : "none",
      }}
    >
      <button
        onClick={onSelect}
        className="flex-1 truncate text-left px-3 py-2.5 text-[13px] flex items-center gap-2"
        style={{ color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)" }}
        title={title}
      >
        <MessageSquare size={13} strokeWidth={1.6} />
        <span className="truncate">{title}</span>
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-black/5"
        title="Delete"
        aria-label={`Delete ${title}`}
      >
        <X size={12} stroke="var(--color-text-tertiary)" />
      </button>
    </div>
  );
}
