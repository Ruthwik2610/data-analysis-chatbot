"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, ArrowRight, Paperclip, Plug, Sparkles } from "lucide-react";
import type { Message, ModelFallbackNotice } from "@/lib/types";
import { ResultBlock } from "./ResultBlock";
import { InlineQuestion } from "./InlineQuestion";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { FilePickButton } from "./FilePickButton";
import { AssistantMarkdown } from "./AssistantMarkdown";
import { AnswerActions } from "./AnswerActions";
import { FollowUpChips } from "./FollowUpChips";

interface MessageListProps {
  messages: Message[];
  loading: boolean;
  onPendingChoice: (messageId: string, value: string) => void;
  onPickFile: (file: File) => void;
  onConnectClick: () => void;
  currentProjectId?: string | null;
  onSaveProjectNote?: (message: Extract<Message, { role: "assistant" }>) => void;
  onAskFollowUp?: (content: string) => void;
}

function formatRelative(ts?: number): string {
  if (!ts) return "";
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

export function MessageList({ messages, loading, onPendingChoice, onPickFile, onConnectClick, currentProjectId, onSaveProjectNote, onAskFollowUp }: MessageListProps) {
  const ref = useRef<HTMLDivElement>(null);
  const isStreaming = messages.some((m) => m.role === "assistant" && m.streaming);

  // Index of the last non-streaming assistant message with a result
  const lastResultIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "assistant" && m.result && !m.streaming) return i;
    }
    return -1;
  })();

  useEffect(() => {
    ref.current?.scrollTo({
      top: ref.current.scrollHeight,
      behavior: isStreaming ? "auto" : "smooth",
    });
  }, [messages, loading, isStreaming]);

  if (messages.length === 0 && !loading) {
    return <Greeting onPickFile={onPickFile} onConnectClick={onConnectClick} />;
  }

  return (
    <div ref={ref} className="flex-1 overflow-y-auto scrollbar-thin px-6 py-5 flex flex-col">
      {messages.map((msg, idx) => {
        const isConsecutive = idx > 0 && messages[idx - 1].role === msg.role;
        const isFirst = idx === 0;
        return (
          <div key={msg.id} className={`flex flex-col w-full ${isFirst ? "" : isConsecutive ? "mt-1.5" : "mt-6"}`}>
            <Bubble
              message={msg}
              onChoose={(v) => onPendingChoice(msg.id, v)}
              currentProjectId={currentProjectId}
              onSaveProjectNote={onSaveProjectNote}
              onAskFollowUp={onAskFollowUp}
            />
            {idx === lastResultIdx && onAskFollowUp && (
              <div className="mt-4">
                <FollowUpChips key={`chips-${msg.id}`} onSelect={onAskFollowUp} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Bubble({
  message,
  onChoose,
  currentProjectId,
  onSaveProjectNote,
  onAskFollowUp,
}: {
  message: Message;
  onChoose: (value: string) => void;
  currentProjectId?: string | null;
  onSaveProjectNote?: (message: Extract<Message, { role: "assistant" }>) => void;
  onAskFollowUp?: (content: string) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="group self-end max-w-[640px] fade-in flex flex-col items-end">
        <div
          className="px-3.5 py-2.5 text-[13px] leading-[1.6] whitespace-pre-wrap"
          style={{
            background: "var(--color-background-secondary)",
            color: "var(--color-text-primary)",
            borderRadius: "14px 14px 4px 14px",
          }}
        >
          {message.content}
        </div>
        {message.created_at && (
          <time
            className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] mt-0.5 pr-1"
            style={{ color: "var(--color-text-tertiary)" }}
            title={new Date(message.created_at * 1000).toISOString()}
          >
            {formatRelative(message.created_at)}
          </time>
        )}
      </div>
    );
  }

  const showThinking =
    message.thinking && !message.content && !message.result && !message.pending;

  return (
    <div className="self-start max-w-[680px] w-full fade-in">
      <div className="text-[13px] leading-[1.65]" style={{ color: "var(--color-text-primary)" }}>
        {showThinking && <ThinkingIndicator step={message.thinking} progress={message.progress} />}
        {message.content && !message.error && (
          <div className="whitespace-pre-wrap">
            <AssistantMarkdown content={message.content} streaming={!!message.streaming} />
            {message.streaming && (
              <span
                className="inline-block w-[6px] h-[12px] ml-[1px] align-middle"
                style={{ background: "var(--color-text-primary)", animation: "blink 1s steps(1,end) infinite" }}
              />
            )}
          </div>
        )}
        {message.content && !message.error && !message.streaming && (
          <AnswerActions
            content={message.content}
            canSave={!!currentProjectId}
            onSave={() => onSaveProjectNote?.(message)}
            onFollowUp={() => onAskFollowUp?.(`Follow up on this: ${message.content.slice(0, 240)}`)}
          />
        )}
        {message.result && <ResultBlock result={message.result} />}
        {message.pending && !message.resolved && (
          <InlineQuestion
            label={message.pending.hint || "Pick one:"}
            options={message.pending.options}
            onChoose={onChoose}
            allowCustom={message.pending.resolver === "clarify_text"}
          />
        )}
        {message.error && (
          <div
            className="mt-2 text-[12px] px-3 py-2 rounded-[10px]"
            style={{
              background: "rgba(217, 119, 6, 0.06)",
              color: "var(--color-text-warning)",
              border: "0.5px solid rgba(217, 119, 6, 0.2)",
            }}
          >
            {message.content}
          </div>
        )}
        {message.notice && <FallbackNotice notice={message.notice} />}
      </div>
    </div>
  );
}

function FallbackNotice({ notice }: { notice: ModelFallbackNotice }) {
  const reasonText =
    notice.reason === "rate_limit"
      ? `${notice.from} hit its rate limit`
      : `${notice.from} was unavailable`;
  return (
    <div
      className="mt-2 inline-flex items-center gap-1.5 text-[11px] px-2 py-[3px] rounded-md"
      style={{
        background: "rgba(217, 119, 6, 0.06)",
        color: "var(--color-text-warning)",
        border: "0.5px solid rgba(217, 119, 6, 0.2)",
      }}
      title={`Switched from ${notice.from} to ${notice.to} (${notice.reason})`}
    >
      <AlertTriangle size={11} strokeWidth={1.6} />
      Switched to <strong>{notice.to}</strong> — {reasonText}
    </div>
  );
}

function Greeting({ onPickFile, onConnectClick }: { onPickFile: (f: File) => void; onConnectClick: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-5 py-10 fade-in sm:px-8">
      <div className="w-full max-w-[880px] text-center">
        <div
          className="mx-auto mb-7 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] font-medium"
          style={{
            background: "var(--color-background-secondary)",
            border: "1px solid var(--color-border-secondary)",
            color: "var(--color-text-secondary)",
          }}
        >
          <Sparkles size={13} strokeWidth={1.7} />
          Unipro AI Workspace
        </div>
        <h1 className="mx-auto max-w-[820px] text-[42px] font-bold leading-[1.08] sm:text-[58px]" style={{ color: "var(--color-text-primary)", letterSpacing: 0 }}>
          Analyze your business data with AI.
        </h1>
        <p className="mx-auto mt-7 max-w-[680px] text-[18px] leading-[1.65]" style={{ color: "var(--color-text-secondary)" }}>
          Upload files, connect APIs, and generate intelligent insights instantly.
        </p>
      </div>

      <div
        data-testid="empty-action-grid"
        className="mt-14 flex w-full max-w-[864px] flex-col gap-0 overflow-hidden rounded-[22px] sm:flex-row"
        style={{
          background: "var(--color-background-elevated)",
          border: "1px solid var(--color-border-secondary)",
          boxShadow: "var(--shadow-xl)",
        }}
      >
        <div className="flex flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-2 px-6 py-4" style={{ borderBottom: "1px solid var(--color-border-tertiary)" }}>
            <FilePickButton
              onPick={onPickFile}
              variant="card"
              title="Attach a file"
              className="inline-flex items-center gap-2 rounded-[12px] px-3 py-2 text-[13px] font-medium transition-colors"
            >
              <Paperclip size={15} strokeWidth={1.7} />
              Upload
            </FilePickButton>
            <button
              onClick={onConnectClick}
              className="inline-flex items-center gap-2 rounded-[12px] px-3 py-2 text-[13px] font-medium transition-colors"
              style={{
                border: "1px solid var(--color-border-secondary)",
                background: "var(--color-background-secondary)",
                color: "var(--color-text-secondary)",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--color-border-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--color-border-secondary)")}
            >
              <Plug size={15} strokeWidth={1.7} />
              Connect API
            </button>
            <span
              className="ml-auto hidden rounded-[12px] px-3 py-2 text-[13px] font-medium sm:inline-flex"
              style={{
                background: "#eff6ff",
                border: "1px solid rgba(37, 99, 235, 0.18)",
                color: "#1d4ed8",
              }}
            >
              Flash / Pro ready
            </span>
          </div>
          <div className="flex items-center gap-3 px-6 py-6 text-left">
            <div className="min-w-0 flex-1 text-[18px]" style={{ color: "var(--color-text-tertiary)" }}>
              Ask anything about your data...
            </div>
            <button
              onClick={() => window.dispatchEvent(new CustomEvent("data-chat:focus-input"))}
              className="h-10 w-10 flex-shrink-0 rounded-[12px] flex items-center justify-center transition-colors"
              title="Focus composer"
              style={{ background: "#2563eb", color: "#ffffff", boxShadow: "0 14px 26px -18px rgba(37, 99, 235, 0.9)" }}
            >
              <ArrowRight size={18} strokeWidth={2} />
            </button>
          </div>
        </div>
      </div>

      <div className="mt-5 text-[13px]" style={{ color: "var(--color-text-tertiary)" }}>
        Powered by advanced AI • Secure • Private
      </div>

      <div className="mt-6 flex flex-wrap justify-center gap-2 text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
        <span className="rounded-full px-3 py-1.5" style={{ background: "var(--color-background-secondary)", border: "1px solid var(--color-border-tertiary)" }}>Top 10 by revenue</span>
        <span className="rounded-full px-3 py-1.5" style={{ background: "var(--color-background-secondary)", border: "1px solid var(--color-border-tertiary)" }}>Find anomalies</span>
        <span className="rounded-full px-3 py-1.5" style={{ background: "var(--color-background-secondary)", border: "1px solid var(--color-border-tertiary)" }}>Compare periods</span>
      </div>
    </div>
  );
}
