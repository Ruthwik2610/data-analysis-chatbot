"use client";

import { Paperclip } from "lucide-react";
import { useRef } from "react";

interface FilePickButtonProps {
  onPick: (file: File) => void;
  disabled?: boolean;
  size?: number;
  className?: string;
  title?: string;
  variant?: "icon" | "card";
  children?: React.ReactNode;
}

const ACCEPT = ".csv,.xlsx,.xls,.pdf,.zip,.7z,.duckdb,.db,.json";

export function FilePickButton({
  onPick,
  disabled,
  size = 15,
  className,
  title = "Attach a file",
  variant = "icon",
  children,
}: FilePickButtonProps) {
  const ref = useRef<HTMLInputElement>(null);

  const click = () => {
    if (disabled) return;
    ref.current?.click();
  };

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onPick(file);
    if (ref.current) ref.current.value = "";
  };

  if (variant === "card") {
    return (
      <>
        <button
          onClick={click}
          disabled={disabled}
          className={className}
          title={title}
          type="button"
        >
          {children}
        </button>
        <input ref={ref} type="file" accept={ACCEPT} onChange={onChange} className="hidden" />
      </>
    );
  }

  return (
    <>
      <button
        type="button"
        title={title}
        onClick={click}
        disabled={disabled}
        className="w-[26px] h-[26px] rounded-[8px] flex items-center justify-center transition-colors flex-shrink-0"
        style={{ color: "var(--color-text-secondary)" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-background-primary)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        <Paperclip size={size} strokeWidth={1.4} />
      </button>
      <input ref={ref} type="file" accept={ACCEPT} onChange={onChange} className="hidden" />
    </>
  );
}
