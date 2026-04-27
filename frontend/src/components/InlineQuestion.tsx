"use client";

import { useState } from "react";
import clsx from "clsx";

interface InlineQuestionProps {
  label: string;
  options: { label: string; value: string }[];
  onChoose: (value: string) => void;
  disabled?: boolean;
}

export function InlineQuestion({ label, options, onChoose, disabled }: InlineQuestionProps) {
  const [chosen, setChosen] = useState<string | null>(null);

  const pick = (value: string) => {
    if (disabled || chosen) return;
    setChosen(value);
    onChoose(value);
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
    </div>
  );
}
