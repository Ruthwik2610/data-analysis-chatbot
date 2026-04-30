"use client";

import { ArrowUp, Paperclip, Plug, Square } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { FilePickButton } from "./FilePickButton";
import { ConnectorPopover } from "./ConnectorPopover";
import type { Source } from "@/lib/types";

interface InputBarProps {
  onSend: (q: string) => void;
  onStop?: () => void;
  onPickFile: (file: File) => void;
  onAttached: (s: Source) => void;
  loading?: boolean;
  disabled: boolean;
  placeholder?: string;
  currentProjectId?: string | null;
}

export function InputBar({ onSend, onStop, onPickFile, onAttached, loading, disabled, placeholder, currentProjectId }: InputBarProps) {
  const [value, setValue] = useState("");
  const [popOpen, setPopOpen] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const plugRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = Math.min(ref.current.scrollHeight, 160) + "px";
    }
  }, [value]);

  useEffect(() => {
    const handler = () => setPopOpen(true);
    window.addEventListener("data-chat:open-connector", handler as EventListener);
    return () => window.removeEventListener("data-chat:open-connector", handler as EventListener);
  }, []);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="px-4 py-3 relative" style={{ borderTop: "0.5px solid var(--color-border-tertiary)" }}>
      <div
        className="flex flex-col gap-2 px-3 py-2 relative"
        style={{
          background: "var(--color-background-secondary)",
          border: "0.5px solid var(--color-border-secondary)",
          borderRadius: 14,
        }}
      >
        <div role="toolbar" aria-label="Composer actions" className="flex items-center gap-1">
          <FilePickButton
            onPick={onPickFile}
            disabled={disabled}
            title="Attach a file (CSV, Excel, database, JSON)"
            variant="card"
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded-[8px] text-[11.5px] transition-colors"
          >
            <Paperclip size={13} strokeWidth={1.5} />
            <span className="hidden sm:inline">Attach</span>
          </FilePickButton>
          <button
            ref={plugRef}
            type="button"
            title="Connect a source"
            aria-label="Connect"
            onClick={() => setPopOpen((s) => !s)}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded-[8px] text-[11.5px] transition-colors flex-shrink-0"
            style={{
              color: popOpen ? "var(--color-text-primary)" : "var(--color-text-secondary)",
              background: popOpen ? "var(--color-background-primary)" : "transparent",
            }}
          >
            <Plug size={13} strokeWidth={1.5} />
            <span className="hidden sm:inline">Connect</span>
          </button>
          <ConnectorPopover
            open={popOpen}
            onClose={() => setPopOpen(false)}
            onAttached={onAttached}
            anchorRef={plugRef}
            currentProjectId={currentProjectId}
          />
        </div>
        <div className="flex items-end gap-2">
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder={placeholder || "Ask about your data, drop a file, or paste a URL…"}
            disabled={disabled}
            className="flex-1 resize-none bg-transparent outline-none text-[13px] leading-[1.5] py-1"
            style={{ color: "var(--color-text-primary)" }}
          />
          {loading && onStop ? (
            <button
              onClick={onStop}
              className="w-7 h-7 rounded-[8px] flex items-center justify-center flex-shrink-0 transition-colors"
              style={{
                background: "var(--color-text-primary)",
                color: "var(--color-background-primary)",
                cursor: "pointer",
              }}
              title="Stop"
            >
              <Square size={11} strokeWidth={0} fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={disabled || !value.trim()}
              className="w-7 h-7 rounded-[8px] flex items-center justify-center flex-shrink-0 transition-opacity"
              style={{
                background: "var(--color-text-primary)",
                color: "var(--color-background-primary)",
                opacity: !value.trim() || disabled ? 0.3 : 1,
                cursor: !value.trim() || disabled ? "default" : "pointer",
              }}
              title="Send"
            >
              <ArrowUp size={14} strokeWidth={2} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
