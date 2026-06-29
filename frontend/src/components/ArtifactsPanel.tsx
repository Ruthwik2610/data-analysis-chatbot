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
      className="fixed inset-y-0 right-0 z-50 flex flex-col shadow-xl"
      style={{
        width: 480,
        background: "var(--color-background-primary)",
        borderLeft: "0.5px solid var(--color-border-secondary)",
      }}
      aria-label="Artifacts panel"
    >
      <div
        className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: "0.5px solid var(--color-border-tertiary)" }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-[10px]"
            style={{ background: "var(--color-background-info)", color: "var(--color-text-info)" }}
          >
            <Layers3 size={16} strokeWidth={1.8} />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-[14px] font-medium" style={{ color: "var(--color-text-primary)" }}>
              Artifacts
            </h2>
            <div className="text-[11px]" style={{ color: "var(--color-text-tertiary)" }}>
              {artifacts.length} graph{artifacts.length === 1 ? "" : "s"}
            </div>
          </div>
        </div>
        <button
          type="button"
          aria-label="Close artifacts panel"
          onClick={onClose}
          className="rounded p-1 transition-colors"
          style={{ color: "var(--color-text-secondary)" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-background-secondary)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          <X size={16} strokeWidth={1.5} />
        </button>
      </div>

      {artifacts.length > 1 && (
        <div className="flex gap-2 overflow-x-auto px-5 py-3" style={{ borderBottom: "0.5px solid var(--color-border-tertiary)" }}>
          {artifacts.map((artifact, index) => (
            <button
              key={artifact.id}
              type="button"
              onClick={() => onSelectArtifact(artifact.id)}
              className="min-w-[150px] rounded-[10px] px-3 py-2 text-left text-[11px] transition-colors"
              style={{
                background: selected?.id === artifact.id ? "var(--color-background-info)" : "var(--color-background-secondary)",
                border: `0.5px solid ${selected?.id === artifact.id ? "var(--color-border-info)" : "var(--color-border-tertiary)"}`,
                color: "var(--color-text-secondary)",
              }}
            >
              <div className="truncate font-semibold" style={{ color: "var(--color-text-primary)" }}>
                {artifact.result.title || `Graph ${index + 1}`}
              </div>
              <div className="mt-1 uppercase tracking-[0.08em]" style={{ color: "var(--color-text-tertiary)" }}>
                {artifact.result.viz} · {artifact.result.row_count.toLocaleString()} rows
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto p-5 scrollbar-thin">
        {selected?.result ? (
          <ResultBlock result={selected.result} narrative={selectedMessage?.role === "assistant" ? selectedMessage.content : null} />
        ) : (
          <div
            className="rounded-[14px] border px-4 py-5 text-[13px]"
            style={{ borderColor: "var(--color-border-secondary)", color: "var(--color-text-tertiary)" }}
          >
            Multiple graph results will appear here when an answer returns more than one chart.
          </div>
        )}
      </div>
    </aside>
  );
}
