"use client";

import { ArrowUp, Mic, Paperclip, Plug, Square } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { FilePickButton } from "./FilePickButton";
import { ConnectorPopover } from "./ConnectorPopover";
import { SourceContextDrawer } from "./SourceContextDrawer";
import type { ModelMode, Source } from "@/lib/types";
import { displaySourceName } from "@/lib/displayNames";

interface InputBarProps {
  onSend: (q: string) => void;
  onStop?: () => void;
  onPickFile: (file: File) => void;
  onAttached: (s: Source) => void;
  loading?: boolean;
  disabled: boolean;
  placeholder?: string;
  currentProjectId?: string | null;
  selectedSources?: Source[];
  modelMode?: ModelMode;
  onModelModeChange?: (mode: ModelMode) => void;
}

export function InputBar({
  onSend,
  onStop,
  onPickFile,
  onAttached,
  loading,
  disabled,
  placeholder,
  currentProjectId,
  selectedSources = [],
  modelMode = "flash",
  onModelModeChange,
}: InputBarProps) {
  const [value, setValue] = useState("");
  const [popOpen, setPopOpen] = useState(false);
  const [sourceDrawerOpen, setSourceDrawerOpen] = useState(false);
  const [listening, setListening] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const plugRef = useRef<HTMLButtonElement>(null);
  const recognitionRef = useRef<any>(null);
  const firstSource = selectedSources[0];
  const sourceOverflow = Math.max(0, selectedSources.length - 1);

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

  useEffect(() => {
    const handler = () => ref.current?.focus();
    window.addEventListener("data-chat:focus-input", handler as EventListener);
    return () => window.removeEventListener("data-chat:focus-input", handler as EventListener);
  }, []);

  const toggleListening = () => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Voice input is not supported in this browser.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onstart = () => setListening(true);
    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setValue((prev) => (prev ? `${prev} ${transcript}` : transcript));
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    recognition.start();
  };

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="px-6 py-4 relative z-30" style={{ background: "transparent" }}>
      <div
        className="mx-auto flex max-w-[920px] flex-col gap-2 px-4 py-3 relative glass"
        style={{
          borderRadius: 22,
          boxShadow: "var(--shadow-xl)",
        }}
      >
        <div role="toolbar" aria-label="Composer actions" className="flex flex-wrap items-center gap-1.5">
          <FilePickButton
            onPick={onPickFile}
            disabled={disabled}
            title="Attach a file (CSV, Excel, PDF, ZIP/7z, database, JSON)"
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
              background: popOpen ? "var(--color-background-secondary)" : "transparent",
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
          <button
            type="button"
            onClick={toggleListening}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded-[8px] text-[11.5px] transition-colors"
            style={{
              color: listening ? "#ef4444" : "var(--color-text-secondary)",
              background: listening ? "rgba(239, 68, 68, 0.1)" : "transparent",
            }}
            title={listening ? "Stop listening" : "Voice to chat"}
          >
            <Mic size={13} strokeWidth={1.5} className={listening ? "animate-pulse" : ""} />
            <span className="hidden sm:inline">{listening ? "Listening…" : "Voice"}</span>
          </button>
          <label
            className="ml-auto inline-flex items-center gap-1.5 rounded-[8px] px-1.5 py-1 text-[11.5px]"
            style={{
              color: "var(--color-text-secondary)",
              background: "var(--color-background-secondary)",
              border: "0.5px solid var(--color-border-tertiary)",
            }}
          >
            <span className="hidden sm:inline">Model</span>
            <select
              aria-label="Query model"
              value={modelMode}
              onChange={(e) => onModelModeChange?.(e.target.value as ModelMode)}
              className="bg-transparent text-[11.5px] outline-none"
              style={{ color: "var(--color-text-primary)" }}
              title={modelMode === "pro" ? "Deeper reasoning, higher cost" : "Normal reasoning, lower cost"}
            >
              <option value="flash">Flash</option>
              <option value="pro">Pro</option>
            </select>
          </label>
          {firstSource && (
            <button
              type="button"
              aria-label="Show selected sources"
              onClick={() => setSourceDrawerOpen((open) => !open)}
              className="flex min-w-0 max-w-full items-center gap-1.5 text-[11.5px] sm:max-w-[42%]"
              title={selectedSources.map((s) => displaySourceName(s.name)).join(", ")}
            >
              <span
                className="inline-flex min-w-0 items-center gap-1.5 rounded-full px-2 py-[3px]"
                style={{
                  background: "var(--color-background-info)",
                  border: "0.5px solid var(--color-border-info)",
                  color: "var(--color-text-info)",
                }}
              >
                <span className="h-[5px] w-[5px] flex-shrink-0 rounded-full" style={{ background: "var(--color-text-info)" }} />
                <span className="truncate">{displaySourceName(firstSource.name)}</span>
              </span>
              {sourceOverflow > 0 && (
                <span
                  className="flex-shrink-0 rounded-full px-2 py-[3px]"
                  style={{
                    background: "var(--color-background-primary)",
                    border: "0.5px solid var(--color-border-tertiary)",
                    color: "var(--color-text-secondary)",
                  }}
                >
                  +{sourceOverflow}
                </span>
              )}
            </button>
          )}
        </div>
        <SourceContextDrawer
          open={sourceDrawerOpen}
          sources={selectedSources}
          onClose={() => setSourceDrawerOpen(false)}
        />
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
            className="flex-1 resize-none bg-transparent outline-none text-[15px] leading-[1.5] py-2 focus:ring-2 focus:ring-[var(--color-border-info)] focus:rounded-sm transition-shadow"
            style={{ color: "var(--color-text-primary)" }}
          />
          {loading && onStop ? (
            <button
              onClick={onStop}
              className="w-9 h-9 rounded-[12px] flex items-center justify-center flex-shrink-0 transition-colors"
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
              className="w-9 h-9 rounded-[12px] flex items-center justify-center flex-shrink-0 transition-all duration-200 ease-in-out hover:scale-105 active:scale-95 shadow-lg shadow-blue-500/20"
              style={{
                background: "var(--color-text-info)",
                color: "#ffffff",
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
