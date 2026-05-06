"use client";

import { useState, useEffect } from "react";
import { Sun, Moon } from "lucide-react";
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
      className="flex items-center justify-between px-5 py-2.5"
      style={{ borderBottom: "0.5px solid var(--color-border-tertiary)" }}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-[13px] font-medium truncate" style={{ color: "var(--color-text-primary)" }}>
          {title}
        </span>
        {projectName && (
           <span
             className="text-[11px] px-2 py-[3px] rounded-full truncate max-w-[180px]"
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
            className="inline-flex items-center gap-1.5 min-w-0 max-w-[220px] text-[11px] px-2 py-[3px] rounded-full"
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

      {/* Dark mode toggle */}
      <button
        onClick={handleToggle}
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        className="p-1.5 rounded-lg transition-colors flex-shrink-0"
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
    </div>
  );
}

