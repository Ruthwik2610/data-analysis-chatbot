"use client";

import { useState } from "react";
import clsx from "clsx";

interface InlineQuestionProps {
  label: string;
  options: { label: string; value: string }[];
  onChoose: (value: string) => void;
  disabled?: boolean;
  allowCustom?: boolean;
}

export function InlineQuestion({ label, options, onChoose, disabled, allowCustom }: InlineQuestionProps) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [customValue, setCustomValue] = useState("");

  const pick = (value: string) => {
    if (disabled || chosen) return;
    setChosen(value);
    onChoose(value);
  };
  const submitCustom = () => {
    const trimmed = customValue.trim();
    if (!trimmed || disabled || chosen) return;
    setChosen(trimmed);
    onChoose(trimmed);
  };

  return (
    <div
      className="rounded-[10px] p-3 mt-2 fade-in"
      style={{
        background: "var(--color-background-secondary)",
        border: "0.5px solid var(--color-border-tertiary)",
      }}
    >
      <div className="text-[11px] mb-2" style={{ color: "var(--color-text-tertiary)" }}>
        {label}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((opt) => {
          const selected = chosen === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => pick(opt.value)}
              disabled={!!chosen}
              className={clsx(
                "px-3 py-[5px] rounded-full text-[12px] transition-colors",
                "disabled:cursor-default",
              )}
              style={{
                border: selected
                  ? "0.5px solid var(--color-text-primary)"
                  : "0.5px solid var(--color-border-secondary)",
                background: selected ? "var(--color-text-primary)" : "var(--color-background-primary)",
                color: selected ? "var(--color-background-primary)" : "var(--color-text-primary)",
                opacity: chosen && !selected ? 0.45 : 1,
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      {allowCustom && (
        <div className="mt-2 flex gap-2">
          <input
            aria-label="Clarification answer"
            value={customValue}
            onChange={(e) => setCustomValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                submitCustom();
              }
            }}
            disabled={!!chosen || disabled}
            className="min-w-0 flex-1 rounded-[8px] px-2.5 py-1.5 text-[12.5px] outline-none"
            style={{
              background: "var(--color-background-primary)",
              border: "0.5px solid var(--color-border-secondary)",
              color: "var(--color-text-primary)",
            }}
            placeholder="Type the missing detail"
          />
          <button
            type="button"
            aria-label="Send clarification"
            onClick={submitCustom}
            disabled={!customValue.trim() || !!chosen || disabled}
            className="rounded-[8px] px-3 py-1.5 text-[12px] disabled:opacity-40"
            style={{
              background: "var(--color-text-primary)",
              color: "var(--color-background-primary)",
            }}
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
