"use client";

import React, { useEffect, useRef } from "react";
import { AlertTriangle, Paperclip, Plug } from "lucide-react";
import type { Message, ModelFallbackNotice } from "@/lib/types";
import { ResultBlock } from "./ResultBlock";
import { InlineQuestion } from "./InlineQuestion";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { FilePickButton } from "./FilePickButton";
import { AssistantMarkdown } from "./AssistantMarkdown";
import { AnswerActions } from "./AnswerActions";

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

export function MessageList({ messages, loading, onPendingChoice, onPickFile, onConnectClick, currentProjectId, onSaveProjectNote, onAskFollowUp }: MessageListProps) {
  const ref = useRef<HTMLDivElement>(null);
  const isStreaming = messages.some((m) => m.role === "assistant" && m.streaming);

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
    <div ref={ref} className="flex-1 overflow-y-auto scrollbar-thin px-6 py-5 flex flex-col gap-4">
      {messages.map((msg) => (
        <Bubble
          key={msg.id}
          message={msg}
          onChoose={onPendingChoice}
          currentProjectId={currentProjectId}
          onSaveProjectNote={onSaveProjectNote}
          onAskFollowUp={onAskFollowUp}
        />
      ))}
    </div>
  );
}

const Bubble = React.memo(function Bubble({
  message,
  onChoose,
  currentProjectId,
  onSaveProjectNote,
  onAskFollowUp,
}: {
  message: Message;
  onChoose: (messageId: string, value: string) => void;
  currentProjectId?: string | null;
  onSaveProjectNote?: (message: Extract<Message, { role: "assistant" }>) => void;
  onAskFollowUp?: (content: string) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="self-end max-w-[640px] fade-in">
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
            onChoose={(v) => onChoose(message.id, v)}
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
});

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

function timeOfDayGreeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Working late?";
  if (h < 12) return "Good morning.";
  if (h < 17) return "Good afternoon.";
  if (h < 21) return "Good evening.";
  return "Hi there.";
}

function Greeting({ onPickFile, onConnectClick }: { onPickFile: (f: File) => void; onConnectClick: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-5 py-10 gap-6 fade-in sm:px-8">
      <div className="text-center max-w-[480px] flex flex-col items-center">
        <img src="/unipro-full-logo.svg" alt="Unipro Technologies Limited" className="h-24 max-w-[320px] object-contain mb-6 sm:h-28" />
        <h2 className="text-[26px] font-medium mb-2" style={{ color: "var(--color-text-primary)" }}>
          {timeOfDayGreeting()}
        </h2>
        <p className="text-[14px]" style={{ color: "var(--color-text-secondary)" }}>
          Ask plain-English questions about your data. I&apos;ll analyze it, summarize what matters, and chart the result.
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-1.5 text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
          <span className="rounded-full px-2 py-1" style={{ background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)" }}>Top 10 by revenue</span>
          <span className="rounded-full px-2 py-1" style={{ background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)" }}>Find anomalies</span>
          <span className="rounded-full px-2 py-1" style={{ background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)" }}>Compare periods</span>
        </div>
      </div>

      <div data-testid="empty-action-grid" className="flex flex-col gap-3 w-full max-w-[480px] sm:flex-row">
        <FilePickButton
          onPick={onPickFile}
          variant="card"
          title="Attach a file"
          className="flex-1 flex flex-col items-center gap-2 px-4 py-5 rounded-[14px] transition-all"
        >
          <CardInner icon={<Paperclip size={18} strokeWidth={1.4} />} label="Attach a file" sub="CSV, Excel, PDF, ZIP/7z, database, JSON" />
        </FilePickButton>
        <button
          onClick={onConnectClick}
          className="flex-1 flex flex-col items-center gap-2 px-4 py-5 rounded-[14px] transition-all"
          style={{
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-primary)",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--color-border-primary)")}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--color-border-secondary)")}
        >
          <CardInner icon={<Plug size={18} strokeWidth={1.4} />} label="Connect an API" sub="URL, with optional bearer" />
        </button>
      </div>

      <div className="text-[11.5px] text-center" style={{ color: "var(--color-text-tertiary)" }}>
        Paste a URL in chat to connect to an API on the fly.
      </div>
    </div>
  );
}

function CardInner({ icon, label, sub }: { icon: React.ReactNode; label: string; sub: string }) {
  return (
    <div
      className="w-full flex flex-col items-center gap-2"
      style={{ color: "var(--color-text-primary)" }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 10,
          background: "var(--color-background-secondary)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {icon}
      </div>
      <div className="text-[13.5px] font-medium">{label}</div>
      <div className="max-w-full text-center text-[11.5px]" style={{ color: "var(--color-text-secondary)" }}>
        {sub}
      </div>
    </div>
  );
}
