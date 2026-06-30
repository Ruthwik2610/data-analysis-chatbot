"use client";

import React, { useEffect, useRef } from "react";
import { AlertTriangle, ArrowRight, Sparkles } from "lucide-react";
import type { Message, ModelFallbackNotice, ResultPayload } from "@/lib/types";
import { ResultBlock } from "./ResultBlock";
import { InlineQuestion } from "./InlineQuestion";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { AssistantMarkdown } from "./AssistantMarkdown";
import { AnswerActions } from "./AnswerActions";
import { TravelResultPanel } from "./TravelResultPanel";
import { FollowUpChips } from "./FollowUpChips";
import { artifactItems } from "@/lib/artifacts";

interface MessageListProps {
  messages: Message[];
  loading: boolean;
  onPendingChoice: (messageId: string, value: string | string[]) => void;
  onPickFile: (file: File) => void;
  onConnectClick: () => void;
  currentChatId?: string | null;
  currentProjectId?: string | null;
  onSaveProjectNote?: (message: Extract<Message, { role: "assistant" }>) => void;
  onAskFollowUp?: (content: string) => void;
  onRetryQuestion?: (content: string) => void;
  onFeedback?: (message: Extract<Message, { role: "assistant" }>, rating: number, category: string) => void;
  onOpenArtifact?: (artifactId: string) => void;
}

function formatRelative(ts?: number): string {
  if (!ts) return "";
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

export function MessageList({ messages, loading, onPendingChoice, currentChatId, currentProjectId, onSaveProjectNote, onAskFollowUp, onRetryQuestion, onFeedback, onOpenArtifact }: MessageListProps) {
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
    return <Greeting />;
  }

  return (
    <div ref={ref} className="flex-1 overflow-y-auto scrollbar-thin px-6 py-10 flex flex-col min-h-0">
      <div className="chat-content-frame flex flex-col gap-6 mt-auto justify-end">
        {messages.map((msg, idx) => {
            const isConsecutive = idx > 0 && messages[idx - 1].role === msg.role;
            const previousUserMessage = msg.role === "assistant"
              ? [...messages.slice(0, idx)].reverse().find((item) => item.role === "user")
              : undefined;
            return (
            <div key={msg.id} className={`flex flex-col w-full ${isConsecutive ? "mt-1.5" : ""}`}>
                <Bubble
                message={msg}
                onChoose={onPendingChoice}
                currentChatId={currentChatId}
                currentProjectId={currentProjectId}
                onSaveProjectNote={onSaveProjectNote}
                onAskFollowUp={onAskFollowUp}
                onRetryQuestion={previousUserMessage && onRetryQuestion ? () => onRetryQuestion(previousUserMessage.content) : undefined}
                onFeedback={onFeedback}
                onOpenArtifact={onOpenArtifact}
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
    </div>
  );
}

const Bubble = React.memo(function Bubble({
  message,
  onChoose,
  currentChatId,
  currentProjectId,
  onSaveProjectNote,
  onAskFollowUp,
  onRetryQuestion,
  onFeedback,
  onOpenArtifact,
}: {
  message: Message;
  onChoose: (messageId: string, value: string | string[]) => void;
  currentChatId?: string | null;
  currentProjectId?: string | null;
  onSaveProjectNote?: (message: Extract<Message, { role: "assistant" }>) => void;
  onAskFollowUp?: (content: string) => void;
  onRetryQuestion?: () => void;
  onFeedback?: (message: Extract<Message, { role: "assistant" }>, rating: number, category: string) => void;
  onOpenArtifact?: (artifactId: string) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="group self-end max-w-[640px] animate-in slide-in-from-right-2 duration-300 flex flex-col items-end">
        <div
          className="px-4 py-2.5 text-[14px] leading-[1.6] whitespace-pre-wrap glass shadow-lg"
          style={{
            background: "rgba(37, 99, 235, 0.15)",
            color: "var(--color-text-primary)",
            borderRadius: "18px 18px 4px 18px",
            borderColor: "rgba(37, 99, 235, 0.2)",
          }}
        >
          {message.content}
        </div>
        {message.created_at && (
          <time
            className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] mt-1 pr-1 font-bold uppercase tracking-widest"
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

  const hasTravelData = !!message.travel_intent && (
    (message.travel_offers?.length ?? 0) > 0 ||
    (message.hotel_offers?.length ?? 0) > 0
  );
  const hasResultPayload = !!message.result || (message.artifacts?.length ?? 0) > 0;

  return (
    <div className="self-start max-w-[720px] w-full animate-in slide-in-from-left-2 duration-500">
      <div className="text-[14px] leading-[1.7]" style={{ color: "var(--color-text-primary)" }}>
        {showThinking && <ThinkingIndicator step={message.thinking} progress={message.progress} />}
        {message.content && !message.error && (
          <div className="whitespace-pre-wrap flex flex-col gap-2">
            <div className="flex items-center gap-2 mb-1">
                <div className="p-1 rounded-lg bg-blue-500/10 text-blue-400">
                    <Sparkles size={14} strokeWidth={2} />
                </div>
                <span className="text-[10px] font-bold uppercase tracking-[0.2em] opacity-40" style={{ color: "var(--color-text-tertiary)" }}>Intelligence Engine</span>
            </div>
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
            onRetry={onRetryQuestion}
            onFeedback={(rating, category) => onFeedback?.(message, rating, category)}
          />
        )}
        {message.result && (() => {
          const messageArtifacts = artifactItems([message]);
          if (!message.streaming && onOpenArtifact && messageArtifacts.length > 1) {
            const primaryArtifact = messageArtifacts[0];
            return (
              <ArtifactReference
                result={primaryArtifact.result}
                artifactCount={messageArtifacts.length}
                onOpen={() => onOpenArtifact(primaryArtifact.id)}
              />
            );
          }
          return <ResultBlock result={message.result} narrative={message.content} />;
        })()}
        {hasTravelData && message.travel_intent && (
          <TravelResultPanel
            offers={message.travel_offers || []}
            hotels={message.hotel_offers || []}
            intent={message.travel_intent}
            chatId={currentChatId}
            onRefresh={onAskFollowUp ? () => {
              const wantsF = message.travel_intent?.wants_flights;
              const wantsH = message.travel_intent?.wants_hotels;
              const refreshSubject = (wantsF && wantsH) ? "flight and hotel prices" : wantsH ? "hotel prices" : "flight prices";
              onAskFollowUp(`Refresh the ${refreshSubject} for this search`);
            } : undefined}
          />
        )}
        {message.pending && !message.resolved && (
          <div className="mt-4 p-6 rounded-[24px] glass border-blue-500/10 bg-blue-500/[0.02]">
            <InlineQuestion
                label={message.pending.hint || "Strategic Input Required"}
                options={message.pending.options}
                onChoose={(v) => onChoose(message.id, v)}
                allowCustom={message.pending.resolver === "clarify_text"}
                multiSelect={message.pending.multiSelect}
            />
          </div>
        )}
        {message.error && !hasResultPayload && (
          <div
            className="mt-2 text-[12px] px-4 py-3 rounded-xl glass border-red-500/20 bg-red-500/[0.02] flex items-start gap-3"
            style={{
              color: "var(--color-text-warning)",
            }}
          >
            <AlertTriangle size={16} className="text-red-500 mt-0.5" />
            <div className="flex flex-col gap-1">
                <span className="font-bold uppercase tracking-widest text-[10px]">Processing Fault</span>
                <span className="opacity-80">{message.content}</span>
            </div>
          </div>
        )}
        {message.notice && <FallbackNotice notice={message.notice} />}
      </div>
    </div>
  );
});

function ArtifactReference({
  result,
  artifactCount,
  onOpen,
}: {
  result: ResultPayload;
  artifactCount: number;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="mt-3 flex w-full items-center justify-between gap-3 rounded-[14px] px-4 py-3 text-left transition-all hover:-translate-y-[1px]"
      style={{
        background: "var(--color-background-secondary)",
        border: "1px solid var(--color-border-secondary)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <div className="min-w-0">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--color-text-tertiary)" }}>
          {artifactCount} artifacts · {result.viz}
        </div>
        <div className="mt-1 truncate text-[13px] font-semibold" style={{ color: "var(--color-text-primary)" }}>
          {result.title}
        </div>
        <div className="mt-1 text-[11px]" style={{ color: "var(--color-text-secondary)" }}>
          Multiple graph results · open side panel
        </div>
      </div>
      <ArrowRight size={16} strokeWidth={1.8} style={{ color: "var(--color-text-tertiary)" }} />
    </button>
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

function Greeting() {
  return (
    <div className="hero-stage flex-1 flex flex-col items-center justify-center px-4 py-8 fade-in sm:px-8">
      <div className="w-full max-w-[880px] text-center">
        <div
          className="mx-auto mb-7 inline-flex items-center gap-2 rounded-full px-4 py-2 text-[12px] font-bold uppercase tracking-widest glass"
          style={{
            color: "var(--color-text-secondary)",
          }}
        >
          <Sparkles size={13} strokeWidth={2} className="text-blue-500" />
          Unipro AI Workspace
        </div>
        <h1 className="mx-auto max-w-[820px] text-[42px] font-bold leading-[1.1] sm:text-[64px] tracking-tight" style={{ color: "var(--color-text-primary)" }}>
          The intelligent layer for your <span className="text-blue-500">business data.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-[680px] text-[16px] leading-[1.7] sm:text-[20px] opacity-60" style={{ color: "var(--color-text-secondary)" }}>
          Connect your CSVs, Databases, or APIs and start chatting with your information in seconds.
        </p>
      </div>
    </div>
  );
}
