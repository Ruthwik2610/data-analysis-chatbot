"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, Paperclip, Plug } from "lucide-react";
import type { Message, ModelFallbackNotice } from "@/lib/types";
import { ResultBlock } from "./ResultBlock";
import { InlineQuestion } from "./InlineQuestion";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { FilePickButton } from "./FilePickButton";

interface MessageListProps {
  messages: Message[];
  loading: boolean;
  onPendingChoice: (messageId: string, value: string) => void;
  onPickFile: (file: File) => void;
  onConnectClick: () => void;
}

export function MessageList({ messages, loading, onPendingChoice, onPickFile, onConnectClick }: MessageListProps) {
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
        <Bubble key={msg.id} message={msg} onChoose={(v) => onPendingChoice(msg.id, v)} />
      ))}
    </div>
  );
}

function Bubble({ message, onChoose }: { message: Message; onChoose: (value: string) => void }) {
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
          <div className="md-content whitespace-pre-wrap">
            {renderMarkdown(message.content)}
            {message.streaming && (
              <span
                className="inline-block w-[6px] h-[12px] ml-[1px] align-middle"
                style={{ background: "var(--color-text-primary)", animation: "blink 1s steps(1,end) infinite" }}
              />
            )}
          </div>
        )}
        {message.result && <ResultBlock result={message.result} />}
        {message.pending && !message.resolved && (
          <InlineQuestion
            label={message.pending.hint || "Pick one:"}
            options={message.pending.options}
            onChoose={onChoose}
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
    <div className="flex-1 flex flex-col items-center justify-center px-8 py-10 gap-6 fade-in">
      <div className="text-center max-w-[480px]">
        <h2 className="text-[26px] font-medium mb-2" style={{ color: "var(--color-text-primary)" }}>
          {timeOfDayGreeting()}
        </h2>
        <p className="text-[14px]" style={{ color: "var(--color-text-secondary)" }}>
          Ask plain-English questions about your data — I&apos;ll write the SQL, run it, and chart the result.
        </p>
        <ul className="text-[12.5px] mt-4 space-y-1 text-left inline-block" style={{ color: "var(--color-text-tertiary)" }}>
          <li>• Analyze CSV / Excel uploads — totals, trends, top-N, breakdowns</li>
          <li>• Query connected sources like Salesforce</li>
          <li>• Connect to APIs on the fly by pasting a URL</li>
        </ul>
      </div>

      <div className="flex gap-3 w-full max-w-[480px]">
        <FilePickButton
          onPick={onPickFile}
          variant="card"
          title="Attach a file"
          className="flex-1 flex flex-col items-center gap-2 px-4 py-5 rounded-[14px] transition-all"
        >
          <CardInner icon={<Paperclip size={18} strokeWidth={1.4} />} label="Attach a file" sub="CSV, Excel, database, JSON" />
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
        Tip: paste a URL in chat to connect to an API on the fly.
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
      <div className="text-[11.5px]" style={{ color: "var(--color-text-tertiary)" }}>
        {sub}
      </div>
    </div>
  );
}

function renderMarkdown(text: string): React.ReactNode {
  if (!text) return null;
  const lines = text.split("\n");
  const out: React.ReactNode[] = [];
  let listBuf: string[] = [];

  const flushList = () => {
    if (listBuf.length) {
      out.push(
        <ol key={`l-${out.length}`} className="list-decimal pl-5 my-1">
          {listBuf.map((item, i) => (
            <li key={i}>{renderInline(item)}</li>
          ))}
        </ol>,
      );
      listBuf = [];
    }
  };

  for (const line of lines) {
    const m = line.match(/^\s*\d+\.\s+(.*)$/);
    if (m) {
      listBuf.push(m[1]);
      continue;
    }
    flushList();
    if (line.trim() === "") {
      out.push(<div key={`b-${out.length}`} className="h-2" />);
      continue;
    }
    out.push(<div key={`p-${out.length}`}>{renderInline(line)}</div>);
  }
  flushList();
  return out;
}

function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < text.length) {
    const boldStart = text.indexOf("**", i);
    const codeStart = text.indexOf("`", i);
    let next = -1;
    let kind: "bold" | "code" | null = null;
    if (boldStart >= 0 && (codeStart < 0 || boldStart < codeStart)) {
      next = boldStart;
      kind = "bold";
    } else if (codeStart >= 0) {
      next = codeStart;
      kind = "code";
    }
    if (next < 0 || kind === null) {
      parts.push(text.slice(i));
      break;
    }
    if (next > i) parts.push(text.slice(i, next));
    if (kind === "bold") {
      const close = text.indexOf("**", next + 2);
      if (close < 0) {
        parts.push(text.slice(next));
        break;
      }
      parts.push(<strong key={key++}>{text.slice(next + 2, close)}</strong>);
      i = close + 2;
    } else {
      const close = text.indexOf("`", next + 1);
      if (close < 0) {
        parts.push(text.slice(next));
        break;
      }
      parts.push(<code key={key++}>{text.slice(next + 1, close)}</code>);
      i = close + 1;
    }
  }
  return parts;
}
