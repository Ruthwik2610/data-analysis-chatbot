"use client";

import { Layers3, X } from "lucide-react";
import { ResultBlock } from "./ResultBlock";
import { artifactItems } from "@/lib/artifacts";
import type { Message } from "@/lib/types";

interface ArtifactsPanelProps {
  messages: Message[];
  open: boolean;
  selectedArtifactId: string | null;
  onSelectArtifact: (artifactId: string) => void;
  onClose: () => void;
}

export function ArtifactsPanel({
  messages,
  open,
  selectedArtifactId,
  onSelectArtifact,
  onClose,
}: ArtifactsPanelProps) {
  const artifacts = artifactItems(messages);
  const selected = artifacts.find((artifact) => artifact.id === selectedArtifactId) || artifacts[artifacts.length - 1] || null;
  const selectedMessage = selected
    ? messages.find((message) => message.id === selected.messageId && message.role === "assistant")
    : null;

  if (!open) return null;

  return (
    <aside
      className="fixed inset-y-0 right-0 z-50 flex h-full min-h-0 w-[min(92vw,460px)] flex-shrink-0 animate-in slide-in-from-right-2 flex-col border-l shadow-2xl duration-300 xl:static xl:z-auto xl:w-[460px] xl:shadow-none"
      style={{
        background: "var(--color-background-primary)",
        borderColor: "var(--color-border-tertiary)",
      }}
      aria-label="Artifacts panel"
    >
      <div
        className="flex items-center justify-between gap-3 px-4 py-3.5"
        style={{
          borderBottom: "1px solid var(--color-border-tertiary)",
          background: "var(--glass-background)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
        }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-[10px]" style={{ background: "var(--color-background-info)", color: "var(--color-text-info)" }}>
            <Layers3 size={16} strokeWidth={1.8} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold" style={{ color: "var(--color-text-primary)" }}>Artifacts</div>
            <div className="text-[11px]" style={{ color: "var(--color-text-tertiary)" }}>{artifacts.length} artifact{artifacts.length === 1 ? "" : "s"}</div>
          </div>
        </div>
        <button
          type="button"
          aria-label="Close artifacts panel"
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-full"
          style={{ color: "var(--color-text-tertiary)" }}
        >
          <X size={15} strokeWidth={1.8} />
        </button>
      </div>

      {artifacts.length > 1 && (
        <div className="flex gap-2 overflow-x-auto px-4 py-3" style={{ borderBottom: "1px solid var(--color-border-tertiary)" }}>
          {artifacts.map((artifact, index) => (
            <button
              key={artifact.id}
              type="button"
              onClick={() => onSelectArtifact(artifact.id)}
              className="min-w-[140px] rounded-[10px] px-3 py-2 text-left text-[11px] transition-colors"
              style={{
                background: selected?.id === artifact.id ? "var(--color-background-info)" : "var(--color-background-secondary)",
                border: `1px solid ${selected?.id === artifact.id ? "var(--color-border-info)" : "var(--color-border-tertiary)"}`,
                color: "var(--color-text-secondary)",
              }}
            >
              <div className="truncate font-semibold" style={{ color: "var(--color-text-primary)" }}>{artifact.result.title || `Artifact ${index + 1}`}</div>
              <div className="mt-1 uppercase tracking-[0.08em]" style={{ color: "var(--color-text-tertiary)" }}>
                {artifact.result.viz} · {artifact.result.row_count.toLocaleString()} rows
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 scrollbar-thin">
        {selected?.result ? (
          <ResultBlock result={selected.result} narrative={selectedMessage?.role === "assistant" ? selectedMessage.content : null} />
        ) : (
          <div className="rounded-[14px] border px-4 py-5 text-[13px]" style={{ borderColor: "var(--color-border-secondary)", color: "var(--color-text-tertiary)" }}>
            Visual results will appear here when a query returns a chart or large table.
          </div>
        )}
      </div>
    </aside>
  );
}
