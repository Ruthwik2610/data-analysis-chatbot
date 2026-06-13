"use client";

import { sanitizeThinkingStep } from "@/lib/userFacingText";

interface ThinkingIndicatorProps {
  step: string | null | undefined;
  progress?: number | null;
}

export function ThinkingIndicator({ step, progress }: ThinkingIndicatorProps) {
  const safeStep = sanitizeThinkingStep(step);
  if (!safeStep) return null;
  const showProgress = typeof progress === "number" && progress >= 0 && progress <= 100;
  return (
    <div
      className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-[10px] fade-in soft-pulse"
      style={{
        background: "var(--color-background-secondary)",
        border: "0.5px solid var(--color-border-tertiary)",
      }}
    >
      <span className="flex items-center gap-1">
        <span
          className="dot-typing w-[5px] h-[5px] rounded-full"
          style={{ background: "var(--color-text-tertiary)" }}
        />
        <span
          className="dot-typing w-[5px] h-[5px] rounded-full"
          style={{ background: "var(--color-text-tertiary)" }}
        />
        <span
          className="dot-typing w-[5px] h-[5px] rounded-full"
          style={{ background: "var(--color-text-tertiary)" }}
        />
      </span>
      <span className="text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
        {safeStep}
        {showProgress ? ` · ${progress}%` : "…"}
      </span>
      {showProgress && (
        <div
          className="ml-1 h-[3px] rounded-full overflow-hidden"
          style={{ width: 80, background: "var(--color-border-tertiary)" }}
        >
          <div
            className="h-full transition-all"
            style={{ width: `${progress}%`, background: "var(--color-text-primary)" }}
          />
        </div>
      )}
    </div>
  );
}
