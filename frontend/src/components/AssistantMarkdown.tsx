"use client";

import { useMemo } from "react";

interface AssistantMarkdownProps {
  content: string;
  streaming?: boolean;
}

export function AssistantMarkdown({ content, streaming = false }: AssistantMarkdownProps) {
  const rendered = useMemo(
    () => (streaming ? renderStreaming(content) : renderMarkdown(content)),
    [content, streaming],
  );

  return <div className="assistant-markdown">{rendered}</div>;
}

function renderStreaming(text: string): React.ReactNode {
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line, i) => (
      <p key={i}>
        {renderInline(line.replace(/^#{1,4}\s+/, "").replace(/^>\s?/, ""))}
      </p>
    ));
}

function renderMarkdown(text: string): React.ReactNode {
  if (!text) return null;
  const lines = text.split("\n");
  const out: React.ReactNode[] = [];
  let sectionTitle: string | null = null;
  let sectionLines: string[] = [];
  let prelude: string[] = [];

  const flushPrelude = () => {
    if (!prelude.length) return;
    out.push(<div key={`pre-${out.length}`}>{renderFlow(prelude, `pre-${out.length}`)}</div>);
    prelude = [];
  };

  const flushSection = () => {
    if (!sectionTitle) return;
    out.push(
      <section key={`section-${out.length}`} className="assistant-section">
        <h2>{renderInline(sectionTitle)}</h2>
        {renderFlow(sectionLines, `section-${out.length}`)}
      </section>,
    );
    sectionTitle = null;
    sectionLines = [];
  };

  for (const raw of lines) {
    const heading = raw.match(/^##\s+(.*)$/);
    if (heading) {
      flushPrelude();
      flushSection();
      sectionTitle = heading[1].trim();
      continue;
    }
    if (sectionTitle) sectionLines.push(raw);
    else prelude.push(raw);
  }

  flushPrelude();
  flushSection();
  return out;
}

function renderFlow(lines: string[], keyPrefix: string): React.ReactNode {
  const out: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const trimmed = lines[i].trim();
    if (!trimmed || /^-{3,}$/.test(trimmed)) {
      i++;
      continue;
    }

    if (/^#{3,4}\s+/.test(trimmed)) {
      out.push(<h3 key={`${keyPrefix}-h-${out.length}`}>{renderInline(trimmed.replace(/^#{3,4}\s+/, ""))}</h3>);
      i++;
      continue;
    }

    if (isMarkdownTableStart(lines, i)) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        tableLines.push(lines[i]);
        i++;
      }
      out.push(renderTable(tableLines, `${keyPrefix}-table-${out.length}`));
      continue;
    }

    const bullet = trimmed.match(/^[-*•]\s+(.*)$/);
    if (bullet) {
      if (looksLikeMetricRow(bullet[1])) {
        out.push(renderMetrics(bullet[1], `${keyPrefix}-metrics-${out.length}`));
        i++;
        continue;
      }
      const items: string[] = [];
      while (i < lines.length) {
        const item = lines[i].trim().match(/^[-*•]\s+(.*)$/);
        if (!item) break;
        items.push(item[1]);
        i++;
      }
      out.push(renderList(items, false, `${keyPrefix}-list-${out.length}`));
      continue;
    }

    const ordered = trimmed.match(/^\d+\.\s+(.*)$/);
    if (ordered) {
      const items: string[] = [];
      while (i < lines.length) {
        const item = lines[i].trim().match(/^\d+\.\s+(.*)$/);
        if (!item) break;
        items.push(item[1]);
        i++;
      }
      out.push(renderList(items, true, `${keyPrefix}-list-${out.length}`));
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quotes: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quotes.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      out.push(
        <blockquote key={`${keyPrefix}-quote-${out.length}`} data-testid="assistant-callout">
          {quotes.map((quote, j) => <div key={j}>{renderInline(quote)}</div>)}
        </blockquote>,
      );
      continue;
    }

    if (looksLikeMetricRow(trimmed)) {
      out.push(renderMetrics(trimmed, `${keyPrefix}-metrics-${out.length}`));
      i++;
      continue;
    }

    out.push(<p key={`${keyPrefix}-p-${out.length}`}>{renderInline(trimmed)}</p>);
    i++;
  }

  return out;
}

function renderList(items: string[], ordered: boolean, key: string): React.ReactNode {
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag key={key}>
      {items.map((item, i) => <li key={i}>{renderInline(item)}</li>)}
    </Tag>
  );
}

function isMarkdownTableStart(lines: string[], i: number): boolean {
  return !!lines[i]?.includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i + 1] ?? "");
}

function renderTable(lines: string[], key: string): React.ReactNode {
  const parse = (line: string) =>
    line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
  const header = parse(lines[0] ?? "");
  const rows = lines.slice(2).map(parse).filter((row) => row.some(Boolean));

  return (
    <div key={key} className="assistant-table-wrap">
      <table className="assistant-table">
        <thead>
          <tr>{header.map((cell, i) => <th key={i}>{renderInline(cell)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>{header.map((_, j) => <td key={j}>{renderInline(row[j] ?? "")}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderMetrics(line: string, key: string): React.ReactNode {
  return (
    <div key={key} className="assistant-metrics">
      {line.split("|").map((part, i) => (
        <span key={i} className="assistant-metric" data-testid="assistant-metric">
          {renderInline(part.trim().replace(/^-+\s*/, ""))}
        </span>
      ))}
    </div>
  );
}

function looksLikeMetricRow(line: string): boolean {
  const parts = line.split("|").map((part) => part.trim()).filter(Boolean);
  return parts.length >= 3 && parts.some((part) => /[$%]|\d/.test(part));
}

function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < text.length) {
    const token = findNextInlineToken(text, i);
    const next = token?.index ?? -1;
    const kind = token?.kind ?? null;
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
    } else if (kind === "code") {
      const close = text.indexOf("`", next + 1);
      if (close < 0) {
        parts.push(text.slice(next));
        break;
      }
      parts.push(<code key={key++}>{text.slice(next + 1, close)}</code>);
      i = close + 1;
    } else {
      const marker = text[next];
      const close = findClosingEmphasis(text, marker, next + 1);
      if (close < 0) {
        parts.push(marker);
        i = next + 1;
        continue;
      }
      parts.push(<em key={key++}>{text.slice(next + 1, close)}</em>);
      i = close + 1;
    }
  }
  return parts;
}

function findNextInlineToken(text: string, start: number): { kind: "bold" | "code" | "italic"; index: number } | null {
  let best: { kind: "bold" | "code" | "italic"; index: number } | null = null;
  const candidates: Array<{ kind: "bold" | "code"; marker: string }> = [
    { kind: "bold", marker: "**" },
    { kind: "code", marker: "`" },
  ];

  for (const candidate of candidates) {
    const index = text.indexOf(candidate.marker, start);
    if (index >= 0 && (!best || index < best.index)) {
      best = { kind: candidate.kind, index };
    }
  }

  for (let index = start; index < text.length; index += 1) {
    const marker = text[index];
    if ((marker === "*" || marker === "_") && text[index + 1] !== marker && canOpenEmphasis(text, index)) {
      if (!best || index < best.index) best = { kind: "italic", index };
      break;
    }
  }

  return best;
}

function findClosingEmphasis(text: string, marker: string, start: number): number {
  for (let index = start; index < text.length; index += 1) {
    if (text[index] === marker && text[index + 1] !== marker && canCloseEmphasis(text, index)) {
      return index;
    }
  }
  return -1;
}

function canOpenEmphasis(text: string, index: number): boolean {
  const marker = text[index];
  const prev = text[index - 1] ?? "";
  const next = text[index + 1] ?? "";
  if (!next || /\s/.test(next)) return false;
  if (marker === "_" && /\w/.test(prev)) return false;
  return true;
}

function canCloseEmphasis(text: string, index: number): boolean {
  const marker = text[index];
  const prev = text[index - 1] ?? "";
  const next = text[index + 1] ?? "";
  if (!prev || /\s/.test(prev)) return false;
  if (marker === "_" && /\w/.test(next)) return false;
  return true;
}
