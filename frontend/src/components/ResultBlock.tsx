"use client";

import { Copy, Download, Table as TableIcon, BarChart3 } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ResultPayload } from "@/lib/types";

interface ResultBlockProps {
  result: ResultPayload;
}

const PALETTE = [
  "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#0ea5e9",
  "#8b5cf6", "#84cc16", "#ec4899", "#f97316", "#14b8a6",
];

const AXIS_COLOR = "var(--color-text-tertiary)";
const GRID_COLOR = "var(--color-border-tertiary)";

export function ResultBlock({ result }: ResultBlockProps) {
  const [chartType, setChartType] = useState<ResultPayload["viz"]>(result.viz);
  const refinedResult = useMemo(() => ({ ...result, viz: chartType }), [result, chartType]);
  const shape = useMemo(() => analyze(refinedResult), [refinedResult]);
  // BI default: a time × category breakdown is most readable as a crosstab — long-format tables of 50+ rows are unreadable.
  const defaultToTable = shape.kind === "bar" && !!shape.crosstab && shape.crosstab.colsArePeriod;
  const [showTable, setShowTable] = useState(defaultToTable);
  const hasChart = shape.kind !== "table" && shape.kind !== "card";
  const hasChartControls = result.viz !== "card" && result.rows.length > 0;

  return (
    <div
      className="mt-2 fade-in"
      style={{
        background: "var(--color-background-secondary)",
        border: "0.5px solid var(--color-border-tertiary)",
        borderRadius: 14,
        padding: 14,
        boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
      }}
    >
      <div className="flex items-center justify-between mb-2.5">
        <div className="text-[11px]" style={{ color: "var(--color-text-tertiary)" }}>
          {result.title} · {result.row_count.toLocaleString()} rows · queried in {result.elapsed_ms} ms
        </div>
        <div className="flex items-center gap-1.5">
          {hasChartControls && (
            <label className="flex items-center gap-1 text-[11px]" style={{ color: "var(--color-text-secondary)" }}>
              <span className="hidden sm:inline">Chart</span>
              <select
                aria-label="Chart type"
                value={chartType}
                onChange={(e) => {
                  setShowTable(false);
                  setChartType(e.target.value as ResultPayload["viz"]);
                }}
                className="rounded-md px-1.5 py-[3px] text-[11px] outline-none"
                style={{
                  background: "var(--color-background-primary)",
                  border: "0.5px solid var(--color-border-tertiary)",
                  color: "var(--color-text-secondary)",
                }}
              >
                <option value="bar">Bar</option>
                <option value="line">Line</option>
                <option value="pie">Pie</option>
                <option value="table">Table</option>
              </select>
            </label>
          )}
          <IconBtn onClick={() => downloadCsv(result)} title="Download CSV" icon={<Download size={11} strokeWidth={1.4} />} label="CSV" />
          {result.sql && (
            <IconBtn onClick={() => navigator.clipboard?.writeText(result.sql)} title="Copy SQL" icon={<Copy size={11} strokeWidth={1.4} />} label="SQL" />
          )}
          {hasChartControls && (
            <IconBtn
              onClick={() => setShowTable((s) => !s)}
              title={showTable ? "Show chart" : "Show table"}
              icon={showTable ? <BarChart3 size={11} strokeWidth={1.4} /> : <TableIcon size={11} strokeWidth={1.4} />}
              label={showTable ? "Chart" : "Table"}
            />
          )}
        </div>
      </div>

      {!showTable && chartType !== "table" && shape.kind === "card" && <CardViz shape={shape} />}
      {!showTable && chartType !== "table" && shape.kind === "bar" && <BarViz shape={shape} />}
      {!showTable && chartType !== "table" && shape.kind === "pie" && <PieViz shape={shape} />}
      {!showTable && chartType !== "table" && shape.kind === "line" && <LineViz shape={shape} />}
      {(showTable || chartType === "table" || shape.kind === "table") && (
        shape.kind === "bar" && shape.crosstab
          ? <CrosstabTable data={shape.crosstab} />
          : <DataTable result={result} />
      )}

      {result.how && (
        <details className="mt-3">
          <summary className="text-[11px] cursor-pointer" style={{ color: "var(--color-text-tertiary)" }}>
            How I answered
          </summary>
          <div className="text-[11px] mt-1 space-y-1" style={{ color: "var(--color-text-secondary)" }}>
            <div>{result.how}</div>
            <pre
              className="text-[10.5px] p-2 rounded overflow-x-auto"
              style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)" }}
            >
              {result.sql}
            </pre>
          </div>
        </details>
      )}
    </div>
  );
}

function IconBtn({ onClick, title, icon, label }: { onClick: () => void; title: string; icon: React.ReactNode; label: string }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="flex items-center gap-1 text-[11px] px-2 py-[3px] rounded-md transition-colors hover:opacity-80"
      style={{
        color: "var(--color-text-secondary)",
        border: "0.5px solid var(--color-border-tertiary)",
        background: "var(--color-background-primary)",
      }}
    >
      {icon}
      {label}
    </button>
  );
}

interface CrosstabData {
  rowKey: string;
  colKey: string;
  valueKey: string;
  rowLabels: string[];
  colLabels: string[];
  cells: Map<string, Map<string, number>>;
  colsArePeriod: boolean;
}

type Shape =
  | { kind: "table" }
  | { kind: "card"; label: string; value: any; sublabel?: string }
  | { kind: "line"; data: Array<Record<string, any>>; xKey: string; xIsPeriod: boolean; series: string[] }
  | { kind: "pie"; data: Array<{ name: string; value: number }>; valueKey: string }
  | {
      kind: "bar";
      data: Array<Record<string, any>>;
      xKey: string;
      xIsPeriod: boolean;
      series: string[];
      stacked: boolean;
      crosstab?: CrosstabData;
    };

function analyze(result: ResultPayload): Shape {
  const { viz, columns, rows } = result;
  if (rows.length === 0) return { kind: "table" };

  if (viz === "card" || (rows.length === 1 && columns.length <= 3)) {
    if (columns.length === 1) {
      return { kind: "card", label: columns[0], value: rows[0][0] };
    }
    const valueCol = columns[columns.length - 1];
    const valueIdx = columns.length - 1;
    if (columns.length === 2) {
      return { kind: "card", label: valueCol, value: rows[0][valueIdx], sublabel: String(rows[0][0] ?? "") };
    }
    return { kind: "card", label: valueCol, value: rows[0][valueIdx], sublabel: columns.slice(0, -1).map((c, i) => `${c}: ${rows[0][i]}`).join(" · ") };
  }

  // Pure time series: exactly one time-like dim + numeric series, no other string dims.
  // We deliberately ignore the backend's viz="line" hint here — if there are extra string
  // dims, we want the crosstab path (months × category) to handle it instead.
  const periodLikeIdx = columns.findIndex((c, i) => isPeriodColumn(c, rows.map((r) => r[i])));
  const otherStringDims = columns.filter((c, i) => i !== periodLikeIdx && !rows.every((r) => r[i] === null || r[i] === undefined || isNumeric(r[i])));
  const isPureTimeSeries = periodLikeIdx >= 0 && otherStringDims.length === 0;
  if (isPureTimeSeries) {
    const xKey = periodLikeIdx >= 0 ? columns[periodLikeIdx] : columns[0];
    const xIdx = columns.indexOf(xKey);
    const numericIdx: number[] = [];
    for (let i = 0; i < columns.length; i++) {
      if (i === xIdx) continue;
      if (rows.some((r) => isNumeric(r[i]))) numericIdx.push(i);
    }
    const series = numericIdx.map((i) => columns[i]);
    const data = rows.map((r) => {
      const o: Record<string, any> = { [xKey]: r[xIdx] };
      for (const i of numericIdx) o[columns[i]] = Number(r[i]);
      return o;
    });
    return { kind: "line", data, xKey, xIsPeriod: isPeriodColumn(xKey, rows.map((r) => r[xIdx])), series: series.slice(0, 5) };
  }

  // Identify columns by dtype heuristic
  const numericIdx: number[] = [];
  const dimIdx: number[] = [];
  for (let i = 0; i < columns.length; i++) {
    if (rows.every((r) => r[i] === null || r[i] === undefined || isNumeric(r[i]))) numericIdx.push(i);
    else dimIdx.push(i);
  }
  const valueIdx = numericIdx[numericIdx.length - 1] ?? columns.length - 1;
  const valueKey = columns[valueIdx];

  if (viz === "pie" && dimIdx.length >= 1) {
    const labelIdx = dimIdx[0];
    const data = rows.slice(0, 12).map((r) => ({ name: String(r[labelIdx] ?? "—"), value: Number(r[valueIdx]) || 0 }));
    return { kind: "pie", data, valueKey };
  }

  // 2-dim stacked bar: pivot col0 (x) × col1 (series) → numeric
  if (dimIdx.length >= 2 && numericIdx.length >= 1) {
    // BI convention: when one dim is time, time goes on COLUMNS of the crosstab and X-axis of the bar.
    const periodDimIdx = dimIdx.find((i) => isPeriodColumn(columns[i], rows.map((r) => r[i])));
    const xIdx = periodDimIdx ?? dimIdx[0];
    const seriesIdx = dimIdx.find((i) => i !== xIdx) ?? dimIdx[1];
    const xKey = columns[xIdx];
    const seriesKey = columns[seriesIdx];

    const buckets = new Map<string, Record<string, any>>();
    const seriesSet = new Set<string>();
    const cells = new Map<string, Map<string, number>>();
    const colSet = new Set<string>();
    for (const r of rows) {
      const x = String(r[xIdx] ?? "—");
      const s = String(r[seriesIdx] ?? "—");
      const v = Number(r[valueIdx]);
      if (!Number.isFinite(v)) continue;
      seriesSet.add(s);
      colSet.add(x);
      if (!buckets.has(x)) buckets.set(x, { [xKey]: x });
      const bucket = buckets.get(x)!;
      bucket[s] = (bucket[s] || 0) + v;
      if (!cells.has(s)) cells.set(s, new Map());
      const row = cells.get(s)!;
      row.set(x, (row.get(x) || 0) + v);
    }
    const data = Array.from(buckets.values()).slice(0, 20);
    const series = Array.from(seriesSet).slice(0, 8);
    const xIsPeriod = periodDimIdx !== undefined;
    const colLabels = xIsPeriod
      ? Array.from(colSet).sort()
      : Array.from(colSet);
    const rowLabels = Array.from(cells.keys()).sort((a, b) => {
      const sa = Array.from(cells.get(a)!.values()).reduce((s, n) => s + n, 0);
      const sb = Array.from(cells.get(b)!.values()).reduce((s, n) => s + n, 0);
      return sb - sa;
    });
    const crosstab: CrosstabData = {
      rowKey: seriesKey,
      colKey: xKey,
      valueKey,
      rowLabels,
      colLabels,
      cells,
      colsArePeriod: xIsPeriod,
    };
    return { kind: "bar", data, xKey, xIsPeriod, series, stacked: true, crosstab };
  }

  // Simple bar
  const xIdx = dimIdx[0] ?? 0;
  const xKey = columns[xIdx];
  const data = rows.slice(0, 20).map((r) => ({ [xKey]: String(r[xIdx] ?? "—"), [valueKey]: Number(r[valueIdx]) || 0 }));
  return { kind: "bar", data, xKey, xIsPeriod: isPeriodColumn(xKey, rows.map((r) => r[xIdx])), series: [valueKey], stacked: false };
}

function CardViz({ shape }: { shape: Extract<Shape, { kind: "card" }> }) {
  return (
    <div className="flex flex-col items-start gap-1 py-3">
      <div className="text-[11px] uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>
        {prettyLabel(shape.label)}
      </div>
      <div className="text-[28px] font-medium tabular-nums" style={{ color: "var(--color-text-primary)" }}>
        {formatCell(shape.value)}
      </div>
      {shape.sublabel && (
        <div className="text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
          {shape.sublabel}
        </div>
      )}
    </div>
  );
}

function BarViz({ shape }: { shape: Extract<Shape, { kind: "bar" }> }) {
  const height = Math.min(360, 60 + shape.data.length * 22);
  const yTickFormatter = shape.xIsPeriod ? formatPeriod : undefined;
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={shape.data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} horizontal={false} />
          <XAxis type="number" tick={{ fill: AXIS_COLOR, fontSize: 11 }} tickFormatter={formatNumber} stroke={GRID_COLOR} />
          <YAxis type="category" dataKey={shape.xKey} tick={{ fill: AXIS_COLOR, fontSize: 11 }} tickFormatter={yTickFormatter} width={120} stroke={GRID_COLOR} />
          <Tooltip content={<ChartTooltip labelFormatter={yTickFormatter} />} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
          {shape.stacked && shape.series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />}
          {shape.series.map((key, i) => (
            <Bar
              key={key}
              dataKey={key}
              stackId={shape.stacked ? "a" : undefined}
              fill={PALETTE[i % PALETTE.length]}
              radius={shape.stacked ? 0 : [0, 4, 4, 0]}
            >
              {!shape.stacked &&
                shape.data.map((_, idx) => <Cell key={idx} fill={PALETTE[idx % PALETTE.length]} />)}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function PieViz({ shape }: { shape: Extract<Shape, { kind: "pie" }> }) {
  const total = shape.data.reduce((s, d) => s + (d.value || 0), 0) || 1;
  return (
    <div style={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <PieChart margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
          <Pie
            data={shape.data}
            dataKey="value"
            nameKey="name"
            cx="40%"
            cy="50%"
            innerRadius={50}
            outerRadius={95}
            paddingAngle={2}
            stroke="var(--color-background-secondary)"
            strokeWidth={1.5}
            label={({ percent }) => `${((percent ?? 0) * 100).toFixed(0)}%`}
            labelLine={false}
          >
            {shape.data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip totalForPct={total} />} />
          <Legend
            layout="vertical"
            align="right"
            verticalAlign="middle"
            iconType="circle"
            wrapperStyle={{ fontSize: 11, color: "var(--color-text-secondary)" }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function LineViz({ shape }: { shape: Extract<Shape, { kind: "line" }> }) {
  const xTickFormatter = shape.xIsPeriod ? formatPeriod : undefined;
  return (
    <div style={{ width: "100%", height: 240 }}>
      <ResponsiveContainer>
        <LineChart data={shape.data} margin={{ top: 8, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
          <XAxis dataKey={shape.xKey} tick={{ fill: AXIS_COLOR, fontSize: 11 }} tickFormatter={xTickFormatter} stroke={GRID_COLOR} />
          <YAxis tick={{ fill: AXIS_COLOR, fontSize: 11 }} tickFormatter={formatNumber} stroke={GRID_COLOR} width={50} />
          <Tooltip content={<ChartTooltip labelFormatter={xTickFormatter} />} />
          {shape.series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />}
          {shape.series.map((key, i) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={PALETTE[i % PALETTE.length]}
              strokeWidth={2}
              dot={{ r: 2, fill: PALETTE[i % PALETTE.length] }}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ChartTooltip({ active, payload, label, totalForPct, labelFormatter }: any) {
  if (!active || !payload?.length) return null;
  const displayLabel = label !== undefined ? (labelFormatter ? labelFormatter(label) : String(label)) : null;
  return (
    <div
      style={{
        background: "var(--color-background-primary)",
        border: "0.5px solid var(--color-border-secondary)",
        borderRadius: 8,
        padding: "6px 10px",
        fontSize: 11,
        boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
        color: "var(--color-text-primary)",
      }}
    >
      {displayLabel && (
        <div style={{ color: "var(--color-text-tertiary)", marginBottom: 3 }}>{displayLabel}</div>
      )}
      {payload.map((p: any, i: number) => {
        const v = Number(p.value);
        const pct = totalForPct ? ` (${((v / totalForPct) * 100).toFixed(1)}%)` : "";
        return (
          <div key={i} className="flex items-center gap-1.5">
            <span style={{ width: 7, height: 7, borderRadius: 99, background: p.color || p.fill }} />
            <span style={{ color: "var(--color-text-secondary)" }}>{p.name}</span>
            <span className="tabular-nums" style={{ marginLeft: "auto" }}>
              {formatNumber(v)}{pct}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function DataTable({ result }: { result: ResultPayload }) {
  const rows = result.rows.slice(0, 50);
  const periodColIdx = useMemo(
    () => result.columns.map((c, i) => (isPeriodColumn(c, result.rows.map((r) => r[i])) ? i : -1)).filter((i) => i >= 0),
    [result.columns, result.rows],
  );
  const isPeriodCol = (j: number) => periodColIdx.includes(j);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr>
            {result.columns.map((c) => (
              <th
                key={c}
                className="text-left py-1.5 px-2 font-medium"
                style={{
                  color: "var(--color-text-tertiary)",
                  borderBottom: "0.5px solid var(--color-border-tertiary)",
                }}
              >
                {prettyLabel(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              style={{ background: i % 2 === 1 ? "var(--color-background-primary)" : "transparent" }}
            >
              {row.map((v, j) => (
                <td
                  key={j}
                  className="py-[5px] px-2 tabular-nums"
                  style={{
                    color: "var(--color-text-primary)",
                    borderBottom: i === rows.length - 1 ? "none" : "0.5px solid var(--color-border-tertiary)",
                  }}
                >
                  {isPeriodCol(j) ? formatPeriod(v) : formatCell(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const _PERIOD_NAME_RE = /^(period|date|datetime|month|quarter|year|_at|timestamp|delivery|created_at|updated_at)$/i;
const _ISO_PREFIX_RE = /^\d{4}-\d{2}-\d{2}/;
const _MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function isPeriodColumn(name: string, samples: any[]): boolean {
  if (_PERIOD_NAME_RE.test(name)) return true;
  for (const s of samples) {
    if (s == null) continue;
    if (typeof s === "string" && _ISO_PREFIX_RE.test(s)) return true;
    return false;
  }
  return false;
}

function formatPeriod(value: any): string {
  if (value == null) return "—";
  const s = String(value);
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return s;
  const month = _MONTHS[parseInt(m[2], 10) - 1];
  if (!month) return s;
  // If full year span is single year, show "Mon DD"; else "Mon YYYY". Default safer: "Mon YYYY".
  return `${month} ${m[1]}`;
}

function CrosstabTable({ data }: { data: CrosstabData }) {
  const totalsCol = data.rowLabels.map((r) => {
    const row = data.cells.get(r);
    if (!row) return 0;
    let s = 0;
    for (const v of row.values()) s += v;
    return s;
  });
  const totalsRow = data.colLabels.map((c) => {
    let s = 0;
    for (const r of data.rowLabels) {
      const row = data.cells.get(r);
      if (row?.has(c)) s += row.get(c) || 0;
    }
    return s;
  });
  const grandTotal = totalsRow.reduce((s, n) => s + n, 0);

  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-[12px]" style={{ minWidth: "100%" }}>
        <thead>
          <tr>
            <th
              className="text-left py-1.5 px-2 font-medium sticky left-0"
              style={{
                color: "var(--color-text-tertiary)",
                background: "var(--color-background-secondary)",
                borderBottom: "0.5px solid var(--color-border-tertiary)",
              }}
            >
              {prettyLabel(data.rowKey)}
            </th>
            {data.colLabels.map((c) => (
              <th
                key={c}
                className="text-right py-1.5 px-2 font-medium tabular-nums whitespace-nowrap"
                style={{
                  color: "var(--color-text-tertiary)",
                  borderBottom: "0.5px solid var(--color-border-tertiary)",
                }}
              >
                {data.colsArePeriod ? formatPeriod(c) : c}
              </th>
            ))}
            <th
              className="text-right py-1.5 px-2 font-medium tabular-nums"
              style={{
                color: "var(--color-text-tertiary)",
                borderBottom: "0.5px solid var(--color-border-tertiary)",
                borderLeft: "0.5px solid var(--color-border-tertiary)",
              }}
            >
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rowLabels.map((r, i) => {
            const row = data.cells.get(r);
            return (
              <tr key={r} style={{ background: i % 2 === 1 ? "var(--color-background-primary)" : "transparent" }}>
                <td
                  className="py-[5px] px-2 font-medium whitespace-nowrap sticky left-0"
                  style={{
                    color: "var(--color-text-primary)",
                    background: i % 2 === 1 ? "var(--color-background-primary)" : "var(--color-background-secondary)",
                    borderBottom: "0.5px solid var(--color-border-tertiary)",
                  }}
                >
                  {r}
                </td>
                {data.colLabels.map((c) => (
                  <td
                    key={c}
                    className="py-[5px] px-2 text-right tabular-nums"
                    style={{
                      color: "var(--color-text-primary)",
                      borderBottom: "0.5px solid var(--color-border-tertiary)",
                    }}
                  >
                    {row?.has(c) ? formatNumber(row.get(c) || 0) : "—"}
                  </td>
                ))}
                <td
                  className="py-[5px] px-2 text-right tabular-nums font-medium"
                  style={{
                    color: "var(--color-text-primary)",
                    borderBottom: "0.5px solid var(--color-border-tertiary)",
                    borderLeft: "0.5px solid var(--color-border-tertiary)",
                  }}
                >
                  {formatNumber(totalsCol[i])}
                </td>
              </tr>
            );
          })}
          <tr style={{ borderTop: "0.5px solid var(--color-border-secondary)" }}>
            <td
              className="py-[5px] px-2 font-medium sticky left-0"
              style={{
                color: "var(--color-text-secondary)",
                background: "var(--color-background-secondary)",
                borderTop: "0.5px solid var(--color-border-secondary)",
              }}
            >
              Total
            </td>
            {data.colLabels.map((c, j) => (
              <td
                key={c}
                className="py-[5px] px-2 text-right tabular-nums font-medium"
                style={{
                  color: "var(--color-text-secondary)",
                  borderTop: "0.5px solid var(--color-border-secondary)",
                }}
              >
                {formatNumber(totalsRow[j])}
              </td>
            ))}
            <td
              className="py-[5px] px-2 text-right tabular-nums font-medium"
              style={{
                color: "var(--color-text-primary)",
                borderTop: "0.5px solid var(--color-border-secondary)",
                borderLeft: "0.5px solid var(--color-border-tertiary)",
              }}
            >
              {formatNumber(grandTotal)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function isNumeric(v: any): boolean {
  if (v === null || v === undefined || v === "") return false;
  const n = Number(v);
  return Number.isFinite(n) && typeof v !== "boolean";
}

function prettyLabel(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function formatNumber(v: number): string {
  if (!Number.isFinite(v)) return "—";
  if (Math.abs(v) < 1 && v !== 0) return v.toFixed(3);
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatCell(v: any): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return formatNumber(v);
  if (typeof v === "string" && isNumeric(v)) return formatNumber(Number(v));
  return String(v);
}

function downloadCsv(result: ResultPayload) {
  const header = result.columns.join(",");
  const lines = result.rows.map((r) =>
    r.map((v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v))).join(","),
  );
  const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${result.title.replace(/\s+/g, "_").toLowerCase()}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
