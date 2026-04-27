"use client";

import type { Source } from "@/lib/types";

interface TopbarProps {
  title: string;
  activeSource: Source | undefined;
}

export function Topbar({ title, activeSource }: TopbarProps) {
  return (
    <div
      className="flex items-center justify-between px-5 py-3"
      style={{ borderBottom: "0.5px solid var(--color-border-tertiary)" }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-[13px] font-medium truncate" style={{ color: "var(--color-text-primary)" }}>
          {title}
        </span>
        {activeSource && (
          <span
            className="inline-flex items-center gap-1.5 text-[11px] px-2 py-[3px] rounded-full"
            title={`${activeSource.kind.toUpperCase()} · ${activeSource.rows.toLocaleString()} rows`}
            style={{
              background: "var(--color-background-info)",
              border: "0.5px solid var(--color-border-info)",
              color: "var(--color-text-info)",
            }}
          >
            <span className="w-[5px] h-[5px] rounded-full" style={{ background: "var(--color-text-info)" }} />
            {stripExt(activeSource.name)}
          </span>
        )}
      </div>
    </div>
  );
}

function stripExt(name: string): string {
  return name.replace(/\.[^./\\]+$/, "") || name;
}
