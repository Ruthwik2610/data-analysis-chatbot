"use client";

import { Copy, CornerDownRight, RotateCcw, Save, ThumbsDown, ThumbsUp } from "lucide-react";

interface AnswerActionsProps {
  content?: string;
  canSave?: boolean;
  onSave?: () => void;
  onFollowUp?: () => void;
  onRetry?: () => void;
  onFeedback?: (rating: number, category: string) => void;
}

export function AnswerActions({ content, canSave, onSave, onFollowUp, onRetry, onFeedback }: AnswerActionsProps) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1">
      {content && (
        <button
          type="button"
          aria-label="Copy answer"
          title="Copy answer"
          onClick={() => navigator.clipboard?.writeText(content)}
          className="inline-flex items-center gap-1 rounded-[8px] px-2 py-1 text-[11.5px] hover:bg-black/5"
          style={{ color: "var(--color-text-secondary)" }}
        >
          <Copy size={12} />
          Copy
        </button>
      )}
      {onFollowUp && (
        <button
          type="button"
          aria-label="Ask follow-up"
          title="Ask follow-up"
          onClick={onFollowUp}
          className="inline-flex items-center gap-1 rounded-[8px] px-2 py-1 text-[11.5px] hover:bg-black/5"
          style={{ color: "var(--color-text-secondary)" }}
        >
          <CornerDownRight size={12} />
          Follow-up
        </button>
      )}
      {onRetry && (
        <button
          type="button"
          aria-label="Rerun answer"
          title="Rerun answer"
          onClick={onRetry}
          className="inline-flex items-center gap-1 rounded-[8px] px-2 py-1 text-[11.5px] hover:bg-black/5"
          style={{ color: "var(--color-text-secondary)" }}
        >
          <RotateCcw size={12} />
          Rerun
        </button>
      )}
      {canSave && onSave && (
        <button
          type="button"
          aria-label="Save to project notes"
          title="Save to project notes"
          onClick={onSave}
          className="inline-flex items-center gap-1 rounded-[8px] px-2 py-1 text-[11.5px] hover:bg-black/5"
          style={{ color: "var(--color-text-secondary)" }}
        >
          <Save size={12} />
          Save
        </button>
      )}
      {onFeedback && (
        <>
          <button
            type="button"
            aria-label="Mark answer helpful"
            title="Mark answer helpful"
            onClick={() => onFeedback(1, "helpful")}
            className="inline-flex items-center gap-1 rounded-[8px] px-2 py-1 text-[11.5px] hover:bg-black/5"
            style={{ color: "var(--color-text-secondary)" }}
          >
            <ThumbsUp size={12} />
            Helpful
          </button>
          <button
            type="button"
            aria-label="Mark answer not helpful"
            title="Mark answer not helpful"
            onClick={() => onFeedback(-1, "not_helpful")}
            className="inline-flex items-center gap-1 rounded-[8px] px-2 py-1 text-[11.5px] hover:bg-black/5"
            style={{ color: "var(--color-text-secondary)" }}
          >
            <ThumbsDown size={12} />
            Not helpful
          </button>
        </>
      )}
    </div>
  );
}
