"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Bell, Database, Layers3, LogOut, Menu, Moon, Settings, Sun, UserRound, Zap } from "lucide-react";
import type { Source } from "@/lib/types";
import { getTheme, toggleTheme, type Theme } from "@/lib/theme";

interface TopbarProps {
  title: string;
  activeSource: Source | undefined;
  selectedSources?: Source[];
  projectName?: string | null;
  userEmail?: string;
  onLogout?: () => void;
  onOpenSidebar?: () => void;
  sidebarOpen?: boolean;
  onOpenSettings?: () => void;
  isAdmin?: boolean;
  artifactCount?: number;
  artifactsOpen?: boolean;
  onToggleArtifacts?: () => void;
  sourceCount?: number;
  sourcesOpen?: boolean;
  onToggleSources?: () => void;
}

export function Topbar({
  title,
  projectName,
  userEmail,
  onLogout,
  onOpenSidebar,
  sidebarOpen,
  onOpenSettings,
  isAdmin = false,
  artifactCount = 0,
  artifactsOpen = false,
  onToggleArtifacts,
  sourceCount = 0,
  sourcesOpen = false,
  onToggleSources,
}: TopbarProps) {
  const [theme, setThemeState] = useState<Theme>("light");

  useEffect(() => {
    setThemeState(getTheme());
  }, []);

  const handleToggle = () => {
    toggleTheme();
    setThemeState((t) => (t === "dark" ? "light" : "dark"));
  };
  const themeToggleLabel = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";

  return (
    <div
      className="flex items-center justify-between gap-4 px-6 py-3.5 relative z-30"
      style={{ 
        borderBottom: "1px solid var(--color-border-tertiary)", 
        background: "var(--glass-background)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <div className="chat-content-frame flex min-w-0 flex-1 items-center justify-between gap-4">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {!sidebarOpen && (
          <button
            onClick={onOpenSidebar}
            title="Open sidebar"
            aria-label="Open sidebar"
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[10px]"
            style={{ border: "1px solid var(--color-border-secondary)", color: "var(--color-text-secondary)" }}
          >
            <Menu size={17} strokeWidth={1.8} />
          </button>
        )}
        <span className="hidden text-[13px] font-medium truncate xl:inline" style={{ color: "var(--color-text-primary)" }}>
          {title}
        </span>
        {projectName && (
           <span
             className="hidden text-[11px] px-2 py-[3px] rounded-full truncate max-w-[180px] lg:inline"
             style={{
               background: "var(--color-background-secondary)",
               border: "0.5px solid var(--color-border-tertiary)",
               color: "var(--color-text-secondary)",
             }}
             title={projectName}
           >
             {projectName}
           </span>
        )}
      </div>

      <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={onToggleSources}
        aria-label="Toggle sources panel"
        aria-pressed={sourcesOpen}
        title="Sources"
        className="inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-[11px] font-semibold transition-colors"
        style={{
          background: sourcesOpen ? "var(--color-background-info)" : "transparent",
          border: `0.5px solid ${sourcesOpen ? "var(--color-border-info)" : "var(--color-border-secondary)"}`,
          color: sourcesOpen ? "var(--color-text-info)" : "var(--color-text-secondary)",
        }}
      >
        <Database size={14} strokeWidth={1.8} />
        <span className="hidden sm:inline">Sources</span>
        <span
          className="rounded-full px-1.5 py-[1px] text-[10px] tabular-nums"
          style={{
            background: "var(--color-background-secondary)",
            color: "var(--color-text-tertiary)",
          }}
        >
          {sourceCount}
        </span>
      </button>
      <button
        type="button"
        onClick={onToggleArtifacts}
        aria-label="Toggle artifacts panel"
        aria-pressed={artifactsOpen}
        title="Artifacts"
        className="inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-[11px] font-semibold transition-colors"
        style={{
          background: artifactsOpen ? "var(--color-background-info)" : "transparent",
          border: `0.5px solid ${artifactsOpen ? "var(--color-border-info)" : "var(--color-border-secondary)"}`,
          color: artifactsOpen ? "var(--color-text-info)" : "var(--color-text-secondary)",
        }}
      >
        <Layers3 size={14} strokeWidth={1.8} />
        <span className="hidden sm:inline">Artifacts</span>
        <span
          className="rounded-full px-1.5 py-[1px] text-[10px] tabular-nums"
          style={{
            background: "var(--color-background-secondary)",
            color: "var(--color-text-tertiary)",
          }}
        >
          {artifactCount}
        </span>
      </button>
      <button
        onClick={handleToggle}
        title={themeToggleLabel}
        aria-label={themeToggleLabel}
        className="h-9 w-9 rounded-full transition-colors flex-shrink-0 flex items-center justify-center"
        style={{
          background: "transparent",
          border: "0.5px solid var(--color-border-secondary)",
          color: "var(--color-text-tertiary)",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-background-secondary)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        {theme === "dark" ? <Sun size={13} strokeWidth={1.5} /> : <Moon size={13} strokeWidth={1.5} />}
      </button>
      {isAdmin && <LinkIcon title="Feedback inbox" href="/admin/feedback" icon={<Bell size={15} strokeWidth={1.7} />} />}
      <IconOnly title="Settings" icon={<Settings size={15} strokeWidth={1.7} />} onClick={onOpenSettings} />
      <div className="group relative">
        <button
          title={userEmail || "Account"}
          aria-label="Account"
          className="h-9 w-9 rounded-full flex items-center justify-center"
          style={{
            background: "#4f46e5",
            color: "#ffffff",
            boxShadow: "0 12px 24px -16px rgba(79, 70, 229, 0.9)",
          }}
        >
          <UserRound size={16} strokeWidth={1.8} />
        </button>
        <div className="pointer-events-none absolute right-0 top-10 z-20 w-[220px] rounded-[12px] p-2 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100" style={{ background: "var(--color-background-elevated)", border: "1px solid var(--color-border-secondary)", boxShadow: "var(--shadow-lg)" }}>
          <div className="truncate px-2 py-2 text-[12px]" style={{ color: "var(--color-text-secondary)" }}>{userEmail}</div>
          {isAdmin && (
            <a href="/admin" className="flex w-full items-center gap-2 rounded-[8px] px-2 py-2 text-left text-[12px] font-medium" style={{ color: "var(--color-text-primary)" }}>
              <Zap size={13} className="text-amber-500" /> Admin Dashboard
            </a>
          )}
          <button type="button" onClick={onLogout} className="flex w-full items-center gap-2 rounded-[8px] px-2 py-2 text-left text-[12px] font-medium" style={{ color: "var(--color-text-primary)" }}>
            <LogOut size={13} /> Logout
          </button>
        </div>
      </div>
      </div>
      </div>
    </div>
  );
}

function IconOnly({ title, icon, onClick }: { title: string; icon: React.ReactNode; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className="hidden h-9 w-9 rounded-full transition-colors sm:flex flex-shrink-0 items-center justify-center"
      style={{
        background: "transparent",
        border: "1px solid transparent",
        color: "var(--color-text-secondary)",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "var(--color-background-secondary)";
        e.currentTarget.style.borderColor = "var(--color-border-tertiary)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.borderColor = "transparent";
      }}
    >
      {icon}
    </button>
  );
}

function LinkIcon({ title, icon, href }: { title: string; icon: React.ReactNode; href: string }) {
  return (
    <Link
      title={title}
      aria-label={title}
      href={href}
      className="hidden h-9 w-9 rounded-full transition-colors sm:flex flex-shrink-0 items-center justify-center"
      style={{
        background: "transparent",
        border: "1px solid transparent",
        color: "var(--color-text-secondary)",
      }}
    >
      {icon}
    </Link>
  );
}
