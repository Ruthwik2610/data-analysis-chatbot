export interface ParsedMarkdownTable {
  columns: string[];
  rows: string[][];
}

const SEPARATOR_RE = /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/;

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

export function extractFirstMarkdownTable(text: string | null | undefined): ParsedMarkdownTable | null {
  if (!text) return null;
  const lines = text.split("\n");
  for (let i = 0; i < lines.length - 1; i++) {
    if (!lines[i].includes("|") || !SEPARATOR_RE.test(lines[i + 1] ?? "")) continue;
    const columns = splitRow(lines[i]).filter(Boolean);
    if (columns.length === 0) continue;

    const rows: string[][] = [];
    let j = i + 2;
    while (j < lines.length && lines[j].includes("|") && lines[j].trim()) {
      const row = splitRow(lines[j]);
      if (row.some(Boolean)) rows.push(row);
      j++;
    }
    return { columns, rows };
  }
  return null;
}

function normalizeHeader(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function tableCoversResult(tableColumns: readonly string[], resultColumns: readonly string[]): boolean {
  if (!tableColumns.length || !resultColumns.length) return false;
  const tableSet = new Set(tableColumns.map(normalizeHeader).filter(Boolean));
  if (tableSet.size === 0) return false;

  let hits = 0;
  for (const column of resultColumns) {
    if (tableSet.has(normalizeHeader(column))) hits++;
  }
  return hits >= Math.max(1, Math.ceil(resultColumns.length / 2));
}

export function tableToCsv(table: ParsedMarkdownTable): string {
  const escape = (cell: string): string => {
    if (/[",\n\r]/.test(cell)) return `"${cell.replace(/"/g, '""')}"`;
    return cell;
  };
  const lines = [table.columns.map(escape).join(",")];
  for (const row of table.rows) {
    const padded: string[] = [];
    for (let i = 0; i < table.columns.length; i++) {
      padded.push(escape(row[i] ?? ""));
    }
    lines.push(padded.join(","));
  }
  return lines.join("\n");
}
