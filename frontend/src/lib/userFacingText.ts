const DEFAULT_ERROR = "Something went wrong. Please try again.";
const DEFAULT_THINKING = "Working on your answer";

const SQL_STATEMENT_RE =
  /\b(?:select|with)\b[\s\S]{0,240}\b(?:from|where|join|group\s+by|order\s+by|limit)\b|\b(?:insert|update|delete|create|drop|alter)\b[\s\S]{0,160}\b(?:table|into|from|set|where)\b/i;

const INTERNAL_DETAIL_PATTERNS = [
  SQL_STATEMENT_RE,
  /\bsql\s*(?:query|statement|used|:)/i,
  /\b(?:traceback|stack trace|syntaxerror|typeerror|referenceerror|valueerror|exception|uncaught)\b/i,
  /\b(?:api[_-]?key|token|secret|password|credential|bearer)\b/i,
  /(?:^|\s)(?:\/[^\s:]+){2,}(?::\d+)?/,
  /\b[A-Za-z]:\\[^\s]+/,
  /```|`[^`]+`/,
  /\{["'][\w.-]+["']\s*:/,
];

export function isLikelyInternalDetail(text?: string | null): boolean {
  if (!text) return false;
  return INTERNAL_DETAIL_PATTERNS.some((pattern) => pattern.test(text));
}

export function sanitizeUserVisibleError(message?: string | null, fallback = DEFAULT_ERROR): string {
  const value = message?.trim();
  if (!value) return fallback;
  if (value.length > 220 || isLikelyInternalDetail(value)) return fallback;
  return value;
}

export function sanitizeThinkingStep(step?: string | null): string | null {
  const value = step?.trim();
  if (!value) return null;
  if (value.length > 90 || isLikelyInternalDetail(value)) return DEFAULT_THINKING;
  return value;
}

export function sanitizeAssistantContent(content: string): string {
  const withoutInternalCodeBlocks = content.replace(/```[\s\S]*?```/g, (block) =>
    isLikelyInternalDetail(block) ? "" : block,
  );
  return withoutInternalCodeBlocks
    .split("\n")
    .filter((line) => !isLikelyInternalDetail(line.trim()))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
