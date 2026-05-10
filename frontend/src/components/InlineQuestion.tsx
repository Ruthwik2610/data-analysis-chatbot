"use client";

import { useState } from "react";
import clsx from "clsx";

interface InlineQuestionProps {
  label: string;
  options: { label: string; value: string }[];
  onChoose: (value: string | string[]) => void;
  disabled?: boolean;
  allowCustom?: boolean;
  multiSelect?: boolean;
}

export function InlineQuestion({ label, options, onChoose, disabled, allowCustom, multiSelect }: InlineQuestionProps) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [customValue, setCustomValue] = useState("");

  const pick = (value: string) => {
    if (disabled || chosen) return;
    if (multiSelect) {
      setSelected((prev) => prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]);
      return;
    }
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
          const isSelected = multiSelect ? selected.includes(opt.value) : chosen === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => pick(opt.value)}
              disabled={!!chosen || disabled}
              className={clsx(
                "px-3 py-[5px] rounded-full text-[12px] transition-colors",
                "disabled:cursor-default",
              )}
              style={{
                border: isSelected
                  ? "0.5px solid var(--color-text-primary)"
                  : "0.5px solid var(--color-border-secondary)",
                background: isSelected ? "var(--color-text-primary)" : "var(--color-background-primary)",
                color: isSelected ? "var(--color-background-primary)" : "var(--color-text-primary)",
                opacity: chosen && !isSelected ? 0.45 : 1,
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      {multiSelect && (
        <button
          type="button"
          onClick={() => {
            if (selected.length === 0 || disabled || chosen) return;
            setChosen(selected.join(","));
            onChoose(selected);
          }}
          disabled={selected.length === 0 || !!chosen || disabled}
          className="mt-3 rounded-[8px] px-3 py-1.5 text-[12px] font-medium disabled:opacity-40"
          style={{
            background: "var(--color-text-primary)",
            color: "var(--color-background-primary)",
          }}
        >
          Load {selected.length} {selected.length === 1 ? "sheet" : "sheets"}
        </button>
      )}
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
