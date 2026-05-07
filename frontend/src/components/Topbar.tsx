"use client";

import { useState, useEffect } from "react";
import { Bell, Moon, Search, Settings, Sun, UserRound } from "lucide-react";
import type { Source } from "@/lib/types";
import { displaySourceName } from "@/lib/displayNames";
import { getTheme, toggleTheme, type Theme } from "@/lib/theme";

interface TopbarProps {
  title: string;
  activeSource: Source | undefined;
  selectedSources?: Source[];
  projectName?: string | null;
}

export function Topbar({ title, activeSource, selectedSources, projectName }: TopbarProps) {
  const sources = selectedSources?.length ? selectedSources : activeSource ? [activeSource] : [];
  const firstSource = sources[0];
  const overflow = Math.max(0, sources.length - 1);
  const [theme, setThemeState] = useState<Theme>("light");

  useEffect(() => {
    setThemeState(getTheme());
  }, []);

  const handleToggle = () => {
    toggleTheme();
    setThemeState((t) => (t === "dark" ? "light" : "dark"));
  };

  return (
    <div
      className="flex items-center justify-between gap-4 px-6 py-3.5"
      style={{ borderBottom: "1px solid var(--color-border-tertiary)", background: "var(--color-background-primary)" }}
    >
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <label
          className="flex h-10 w-full max-w-[576px] items-center gap-2 rounded-[14px] px-3"
          style={{
            background: "var(--color-background-secondary)",
            border: "1px solid var(--color-border-secondary)",
            color: "var(--color-text-tertiary)",
          }}
        >
          <Search size={16} strokeWidth={1.7} />
          <input
            type="search"
            placeholder="Search conversations..."
            className="min-w-0 flex-1 bg-transparent text-[14px] outline-none"
            style={{ color: "var(--color-text-primary)" }}
          />
        </label>
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
        {firstSource && (
          <span
            className="hidden items-center gap-1.5 min-w-0 max-w-[220px] text-[11px] px-2 py-[3px] rounded-full md:inline-flex"
            title={`${firstSource.kind.toUpperCase()} · ${firstSource.rows.toLocaleString()} rows`}
            style={{
              background: "var(--color-background-info)",
              border: "0.5px solid var(--color-border-info)",
              color: "var(--color-text-info)",
            }}
          >
            <span className="w-[5px] h-[5px] rounded-full" style={{ background: "var(--color-text-info)" }} />
            <span className="truncate">{displaySourceName(firstSource.name)}</span>
          </span>
        )}
        {overflow > 0 && (
          <span
            className="text-[11px] px-2 py-[3px] rounded-full"
            title={sources.slice(1).map((s) => displaySourceName(s.name)).join(", ")}
            style={{
              background: "var(--color-background-secondary)",
              border: "0.5px solid var(--color-border-tertiary)",
              color: "var(--color-text-tertiary)",
            }}
          >
            +{overflow}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
      <button
        onClick={handleToggle}
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
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
      <IconOnly title="Notifications" icon={<Bell size={15} strokeWidth={1.7} />} />
      <IconOnly title="Settings" icon={<Settings size={15} strokeWidth={1.7} />} />
      <button
        title="Account"
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
      </div>
    </div>
  );
}

function IconOnly({ title, icon }: { title: string; icon: React.ReactNode }) {
  return (
    <button
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
