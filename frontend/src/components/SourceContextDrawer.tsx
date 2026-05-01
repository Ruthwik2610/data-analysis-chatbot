"use client";

import { CheckCircle2, CircleAlert, Database, X } from "lucide-react";
import type { Source } from "@/lib/types";

interface SourceContextDrawerProps {
  open: boolean;
  sources: Source[];
  onClose: () => void;
}

export function SourceContextDrawer({ open, sources, onClose }: SourceContextDrawerProps) {
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label="Selected sources"
      className="absolute bottom-full right-0 z-20 mb-2 w-[min(430px,calc(100vw-32px))] rounded-[12px] p-3 shadow-lg"
      style={{
        background: "var(--color-background-elevated)",
        border: "0.5px solid var(--color-border-primary)",
      }}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-[13px] font-medium" style={{ color: "var(--color-text-primary)" }}>
            Selected sources
          </div>
          <div className="text-[11.5px]" style={{ color: "var(--color-text-tertiary)" }}>
            Queries will use this context.
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close selected sources"
          className="rounded-[8px] p-1 hover:bg-black/5"
          style={{ color: "var(--color-text-secondary)" }}
        >
          <X size={14} />
        </button>
      </div>
      <div className="flex flex-col gap-1.5">
        {sources.map((source) => {
          const healthy = source.loaded !== false;
          return (
            <div
              key={source.id}
              className="flex items-center justify-between gap-3 rounded-[8px] px-2 py-1.5"
              style={{ background: "var(--color-background-secondary)" }}
            >
              <div className="flex min-w-0 items-center gap-2">
                <Database size={14} style={{ color: "var(--color-text-info)" }} />
                <div className="min-w-0">
                  <div className="truncate text-[12.5px]" style={{ color: "var(--color-text-primary)" }}>
                    {source.name}
                  </div>
                  <div className="text-[11.5px] uppercase" style={{ color: "var(--color-text-tertiary)" }}>
                    {source.kind}
                  </div>
                </div>
              </div>
              <div className="flex flex-shrink-0 items-center gap-2 text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
                <span>{source.rows.toLocaleString()} {source.kind === "mcp" ? "tools" : "rows"}</span>
                {healthy ? (
                  <CheckCircle2 aria-label="Source ready" size={13} style={{ color: "var(--color-text-success)" }} />
                ) : (
                  <CircleAlert aria-label="Source needs reload" size={13} style={{ color: "var(--color-text-warning)" }} />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
